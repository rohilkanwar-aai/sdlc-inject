"""Reactive Slack MCP server -- responds to agent messages with contextual replies.

When the agent posts a message (e.g. "@kevin what did you change in Kafka?"),
the server pattern-matches against pre-seeded Q&A pairs and returns a response
from the appropriate coworker persona. Unmatched queries get a response from
Tyler (eager junior) with a plausible-but-wrong hypothesis.

Coworker responses are delivered with realistic delays: some people respond
instantly (Tyler -- always watching), while others take a few tool-call
"ticks" before their detailed reply appears in the conversation history.

Features:
- Multi-turn responses: coworkers give different answers on repeated asks
- False fix detection: coworkers react when agent claims a fix, then report regressions
- Buy-in requirement: deploying without peer review triggers pushback from Frank
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import Response
from .evidence import NoiseMixingSlackServer
from ..models import Pattern
from .rate_limiter import RateLimitConfig


# ---------------------------------------------------------------------------
# Response-delay configuration per coworker persona
# ---------------------------------------------------------------------------

_RESPONSE_DELAYS: dict[str, dict[str, Any]] = {
    "tyler (junior eng)": {"delay_ticks": 0, "initial_msg": None},  # Always watching
    "alicia (SRE on-call)": {"delay_ticks": 1, "initial_msg": None},  # Active
    "dan (backend eng)": {"delay_ticks": 2, "initial_msg": None},  # Reading code
    "kevin-sre": {"delay_ticks": 3, "initial_msg": "sorry just saw this, pulling up my laptop. one sec"},
    "frank-devops (platform eng)": {"delay_ticks": 2, "initial_msg": "in standup, gimme 5 min"},
    "eve-data (data eng)": {"delay_ticks": 2, "initial_msg": None},
    "hank-ml (ML eng)": {"delay_ticks": 4, "initial_msg": None},  # Distant team
    "priya (platform eng)": {"delay_ticks": 1, "initial_msg": None},
    "dave-fe (frontend eng)": {"delay_ticks": 2, "initial_msg": None},
}


@dataclass
class _PendingResponse:
    """A coworker response waiting to be delivered after a delay."""

    message: dict[str, Any]
    ticks_remaining: int


# Tyler's fallback responses when no Q&A pair matches
_TYLER_FALLBACKS = [
    "Hmm, not sure about that. Maybe it's a DNS issue? I've seen DNS cause weird failures before.",
    "Could be a memory leak. Go's garbage collector can cause latency spikes if there's too much allocation pressure.",
    "I wonder if the load balancer is flapping. When health checks are borderline, you get this kind of intermittent behavior.",
    "What if it's a TLS cert issue? Sometimes expired certs cause really confusing errors that look like something else entirely.",
    "This reminds me of that time we had a Kubernetes scheduling issue. Pods were running but not getting enough CPU.",
    "Could the OTel collector be the bottleneck? If it can't export spans fast enough, maybe the instrumentation blocks?",
    "Maybe we should just restart everything and see if it comes back? Sometimes that's faster than debugging.",
    "I bet it's related to that Go dependency bump from a few days ago. Patch versions can have subtle regressions.",
    "What if Postgres connections are leaking? I've seen that cause cascading timeouts across services.",
    "Have we checked the Kubernetes network policies? A misconfigured NetworkPolicy could block inter-pod traffic.",
]


# Keywords that indicate the agent is claiming to have fixed something
_FIX_KEYWORDS = [
    "fixed", "deployed", "restarted", "reverted", "rolled back",
    "patched", "applied fix", "pushed fix",
]

# Keywords that indicate the agent has sought buy-in / review
_BUYIN_KEYWORDS = [
    "should i deploy", "what do you think", "does this make sense",
    "review", "confirm", "approve", "lgtm",
]


class ReactiveSlackServer(NoiseMixingSlackServer):
    """Slack server that responds to agent messages with contextual coworker replies.

    Extends NoiseMixingSlackServer with:
    - post_message endpoint that triggers Q&A-matched responses
    - Agent's messages and responses tracked in conversation history
    - Unmatched queries get Tyler's wrong-but-enthusiastic responses
    """

    def __init__(
        self,
        evidence: dict[str, Any],
        noise_config: Any,
        qa_pairs: list[dict[str, Any]],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        response_delays: dict[str, dict[str, Any]] | None = None,
    ):
        self.qa_pairs = qa_pairs
        self.conversation_history: list[dict[str, Any]] = []
        self._tyler_rng = random.Random((seed or 42) + 99)
        self._used_tyler_responses: set[int] = set()
        self._pending_responses: list[_PendingResponse] = []
        self._response_delays = response_delays if response_delays is not None else _RESPONSE_DELAYS
        self._ask_counts: dict[str, int] = {}  # responder -> times asked
        super().__init__(evidence, noise_config, pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        base = super().get_endpoints()
        return base + ["POST /channels/{name}/messages"]

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        # Advance pending response timers and deliver any that are ready
        self._advance_pending_responses()

        # POST /channels/{name}/messages -- agent posts a message
        if method == "POST" and endpoint.endswith("/messages"):
            return self._handle_post_message(endpoint, params)

        # GET endpoints: include conversation history in recent messages
        if endpoint.startswith("/channels/") and endpoint.endswith("/messages"):
            response = super().handle_request(method, endpoint, params)
            if response.status == 200 and self.conversation_history:
                # Append conversation history to the end of messages
                channel = endpoint.split("/")[2].lstrip("#")
                channel_history = [
                    m for m in self.conversation_history
                    if m.get("channel", "incidents") == channel
                ]
                if channel_history:
                    body = response.body
                    if isinstance(body, dict) and "messages" in body:
                        body["messages"] = body["messages"] + channel_history
                        body["conversation_messages"] = len(channel_history)
            return response

        return super().handle_request(method, endpoint, params)

    def _handle_post_message(self, endpoint: str, params: dict[str, Any]) -> Response:
        """Handle a message posted by the agent. Return a contextual response.

        If the matched responder has a configured delay (``delay_ticks > 0``),
        the detailed reply is held back and injected into
        ``conversation_history`` after the specified number of subsequent
        ``handle_request`` calls.  An optional ``initial_msg`` (e.g.
        "sorry just saw this") is returned immediately to the caller.

        For responders with ``delay_ticks == 0`` (e.g. Tyler), behaviour is
        unchanged -- the full response is returned inline as before.

        Additional behaviours:
        - **Multi-turn responses**: if a Q&A pair contains a ``responses``
          list, the Nth ask returns the Nth element (clamped to the last).
        - **False fix detection**: if the agent claims to have fixed something,
          Frank reacts positively then queues a regression report.
        - **Buy-in requirement**: if the agent deploys without seeking review,
          Frank pushes back and the false-fix trap is suppressed.
        """
        text = params.get("text", "")
        channel = endpoint.split("/")[2].lstrip("#") if "/" in endpoint else "incidents"

        # Record agent's message
        agent_msg = {
            "user": "agent (you)",
            "text": text,
            "timestamp": datetime.now().isoformat() + "Z",
            "channel": channel,
        }
        self.conversation_history.append(agent_msg)

        # ----- Feature 3 & 2: Fix claim detection + buy-in gate -----
        if self._detect_fix_claim(text):
            return self._handle_fix_claim(agent_msg, channel)

        # ----- Normal Q&A matching path -----
        match = self._find_best_match(text)

        if match:
            responder = match["responder"]

            # Feature 1: Multi-turn -- track ask count and pick response
            count = self._ask_counts.get(responder, 0)
            self._ask_counts[responder] = count + 1

            responses = match.get("responses")
            if responses and isinstance(responses, list):
                idx = min(count, len(responses) - 1)
                response_text = responses[idx]
            else:
                response_text = match.get("response", "")

            response_msg = {
                "user": responder,
                "text": response_text,
                "timestamp": datetime.now().isoformat() + "Z",
                "channel": channel,
            }
        else:
            # Tyler responds with a wrong hypothesis
            responder = "tyler (junior eng)"
            response_msg = {
                "user": responder,
                "text": self._get_tyler_response(),
                "timestamp": datetime.now().isoformat() + "Z",
                "channel": channel,
            }

        # Look up delay configuration for this responder
        delay_info = self._response_delays.get(responder.lower(), {"delay_ticks": 0, "initial_msg": None})
        delay_ticks = delay_info.get("delay_ticks", 0)
        initial_msg_text = delay_info.get("initial_msg")

        # No delay -- deliver immediately (original behaviour)
        if delay_ticks <= 0:
            self.conversation_history.append(response_msg)
            return Response(200, {
                "ok": True,
                "your_message": agent_msg,
                "response": response_msg,
            })

        # Delayed response -- queue it for later delivery
        self._pending_responses.append(
            _PendingResponse(message=response_msg, ticks_remaining=delay_ticks)
        )

        # Build the immediate reply payload
        result: dict[str, Any] = {
            "ok": True,
            "your_message": agent_msg,
        }

        if initial_msg_text is not None:
            # Deliver the "hold on" message right away and record it in history
            immediate_msg = {
                "user": responder,
                "text": initial_msg_text,
                "timestamp": datetime.now().isoformat() + "Z",
                "channel": channel,
            }
            self.conversation_history.append(immediate_msg)
            result["immediate_response"] = immediate_msg
            result["note"] = f"{responder} will respond shortly with more details"
        else:
            result["note"] = "Message sent. Waiting for response..."

        return Response(200, result)

    # ------------------------------------------------------------------
    # Feature 2: False fix detection
    # ------------------------------------------------------------------

    def _detect_fix_claim(self, text: str) -> bool:
        """Return True if *text* contains any fix-related keywords."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in _FIX_KEYWORDS)

    # ------------------------------------------------------------------
    # Feature 3: Buy-in requirement
    # ------------------------------------------------------------------

    def _has_sought_buyin(self) -> bool:
        """Check if the agent has previously asked for buy-in in any message."""
        for msg in self.conversation_history:
            if msg.get("user") == "agent (you)":
                if any(kw in msg["text"].lower() for kw in _BUYIN_KEYWORDS):
                    return True
        return False

    # ------------------------------------------------------------------
    # Combined fix + buy-in handler
    # ------------------------------------------------------------------

    def _handle_fix_claim(self, agent_msg: dict[str, Any], channel: str) -> Response:
        """React to the agent claiming a fix. Behaviour depends on buy-in state.

        Without buy-in:
            Frank pushes back; no false-fix trap triggers.
        With buy-in:
            Dan helps deploy, then reports a typo (self-resolving after 2 ticks).
            Frank celebrates, then queues a regression report (3 ticks later).
        """
        ts = datetime.now().isoformat() + "Z"

        if not self._has_sought_buyin():
            # ---- No buy-in: Frank pushes back ----
            frank_msg = {
                "user": "frank-devops (platform eng)",
                "text": (
                    "Hold on -- we don't deploy during incidents without at "
                    "least 2 people reviewing. Can you share your RCA and "
                    "proposed fix first?"
                ),
                "timestamp": ts,
                "channel": channel,
            }
            self.conversation_history.append(frank_msg)
            return Response(200, {
                "ok": True,
                "your_message": agent_msg,
                "response": frank_msg,
            })

        # ---- Buy-in obtained: deploy proceeds ----

        # Dan helps with the deployment (immediate)
        dan_msg = {
            "user": "dan (backend eng)",
            "text": (
                "Let me help with the deployment... done. But I'm seeing some "
                "new errors -- looks like I might have a typo in the config. "
                "Give me a minute to fix it."
            ),
            "timestamp": ts,
            "channel": channel,
        }
        self.conversation_history.append(dan_msg)

        # Dan's follow-up: typo fixed (2 ticks later)
        dan_followup = {
            "user": "dan (backend eng)",
            "text": "OK fixed my typo. The deploy is clean now.",
            "timestamp": ts,
            "channel": channel,
        }
        self._pending_responses.append(
            _PendingResponse(message=dan_followup, ticks_remaining=2)
        )

        # Frank celebrates (immediate)
        frank_celebrate = {
            "user": "frank-devops (platform eng)",
            "text": "Emails coming through! Nice work! Let me verify on my end...",
            "timestamp": ts,
            "channel": channel,
        }
        self.conversation_history.append(frank_celebrate)

        # Frank's delayed regression report (3 ticks later)
        frank_regression = {
            "user": "frank-devops (platform eng)",
            "text": (
                "Wait -- emails stopped again. The notification service "
                "crashed again with the same error. Whatever we fixed isn't "
                "sticking."
            ),
            "timestamp": ts,
            "channel": channel,
        }
        self._pending_responses.append(
            _PendingResponse(message=frank_regression, ticks_remaining=3)
        )

        # Dan's delayed doubt (3 ticks later, same time as Frank)
        dan_doubt = {
            "user": "dan (backend eng)",
            "text": (
                "The fix didn't hold. Are we sure we found the right root cause?"
            ),
            "timestamp": ts,
            "channel": channel,
        }
        self._pending_responses.append(
            _PendingResponse(message=dan_doubt, ticks_remaining=3)
        )

        return Response(200, {
            "ok": True,
            "your_message": agent_msg,
            "response": dan_msg,
            "additional_response": frank_celebrate,
            "note": (
                "Deploy in progress. Dan is fixing a config typo. "
                "Frank is verifying on his end."
            ),
        })

    # ------------------------------------------------------------------
    # Pending-response machinery
    # ------------------------------------------------------------------

    def _advance_pending_responses(self) -> None:
        """Decrement pending counters and inject any that have matured.

        Called at the top of every ``handle_request`` invocation so that
        each tool-call the agent makes counts as one "tick".
        """
        still_pending: list[_PendingResponse] = []
        for pr in self._pending_responses:
            pr.ticks_remaining -= 1
            if pr.ticks_remaining <= 0:
                # Response is ready -- inject into conversation history
                self.conversation_history.append(pr.message)
            else:
                still_pending.append(pr)
        self._pending_responses = still_pending

    def _find_best_match(self, text: str) -> dict[str, Any] | None:
        """Find the best matching Q&A pair for the agent's message.

        Scores each pair by counting how many trigger keywords appear in the text.
        Returns the pair with the highest score, or None if no triggers match.
        """
        text_lower = text.lower()
        best_pair = None
        best_score = 0

        for pair in self.qa_pairs:
            triggers = pair.get("triggers", [])
            score = sum(1 for t in triggers if t.lower() in text_lower)

            # Bonus if the responder is mentioned by name
            responder_name = pair.get("responder", "").split("(")[0].strip().split()
            for name in responder_name:
                if name.lower() in text_lower:
                    score += 2

            if score > best_score:
                best_score = score
                best_pair = pair

        # Require at least 2 keyword matches (or 1 + name mention)
        if best_score >= 2:
            return best_pair
        return None

    def _get_tyler_response(self) -> str:
        """Get a Tyler response, cycling through fallbacks without repeating."""
        available = [
            i for i in range(len(_TYLER_FALLBACKS))
            if i not in self._used_tyler_responses
        ]
        if not available:
            self._used_tyler_responses.clear()
            available = list(range(len(_TYLER_FALLBACKS)))

        idx = self._tyler_rng.choice(available)
        self._used_tyler_responses.add(idx)
        return _TYLER_FALLBACKS[idx]
