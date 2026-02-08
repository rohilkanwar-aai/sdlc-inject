"""Time-progressing incident simulation.

Tracks an internal clock that advances with each MCP tool call. As time
passes, metrics worsen, new Slack messages appear, and recovery attempts
create brief improvements before re-degradation.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timedelta
from typing import Any

from .base import Response
from .evidence import EvidenceMetricsServer
from .reactive import ReactiveSlackServer
from ..models import Pattern
from .rate_limiter import RateLimitConfig


class IncidentTimeline:
    """Tracks incident progression. Each MCP tool call advances the clock.

    The timeline affects:
    - Metric values (goroutines climb, success rate drops)
    - New Slack messages appear at milestone minutes
    - Recovery attempts briefly improve then re-degrade
    """

    def __init__(self, seed: int = 42, minutes_per_tick: int = 2):
        self.rng = random.Random(seed)
        self.minutes_per_tick = minutes_per_tick
        self.tool_calls = 0
        self.minutes_elapsed = 0
        self.recovery_attempts: list[dict[str, Any]] = []
        self._recovery_cooldown = 0  # Minutes remaining of post-recovery improvement

    def tick(self) -> int:
        """Advance the clock by one tick. Returns current minutes elapsed."""
        self.tool_calls += 1
        advance = self.rng.randint(1, self.minutes_per_tick)
        self.minutes_elapsed += advance

        # Decay recovery cooldown
        if self._recovery_cooldown > 0:
            self._recovery_cooldown = max(0, self._recovery_cooldown - advance)

        return self.minutes_elapsed

    def trigger_recovery(self, action: str) -> dict[str, Any]:
        """Record a recovery attempt. Grants a brief improvement window."""
        attempt = {
            "action": action,
            "at_minute": self.minutes_elapsed,
            "tool_call": self.tool_calls,
        }
        self.recovery_attempts.append(attempt)
        self._recovery_cooldown = 5  # 5 minutes of apparent improvement
        return attempt

    @property
    def in_recovery_window(self) -> bool:
        """True if we're in a post-recovery brief improvement window."""
        return self._recovery_cooldown > 0

    def get_metric_modifier(self, metric_name: str) -> float:
        """Get a multiplier for a metric value based on timeline state.

        Returns a modifier that makes things worse over time, with brief
        improvements during recovery windows.
        """
        name = metric_name.lower()
        base_degradation = min(self.minutes_elapsed / 120.0, 1.0)  # 0 to 1 over 2 hours

        # During recovery window, brief improvement
        if self.in_recovery_window:
            base_degradation *= 0.3  # 70% improvement (temporary)

        # Metric-specific modifiers
        if "goroutine" in name:
            # Goroutines climb: 47 -> 847+ over time
            return 1.0 + (base_degradation * 17)  # 1x to 18x

        if "success_rate" in name:
            # Success rate drops: 0.99 -> 0.15 over time
            return max(0.15, 1.0 - (base_degradation * 0.85))

        if "consumer_lag" in name or "lag" in name:
            # Consumer lag grows exponentially
            return 1.0 + (base_degradation * 100)

        if "latency" in name or "duration" in name:
            # Latency increases
            return 1.0 + (base_degradation * 30)

        if "rebalance" in name:
            # Rebalances accumulate
            return 1.0 + (base_degradation * 50)

        if "request_rate" in name and "shipping" in name:
            # Shipping request rate drops as pool exhausts
            return max(0.05, 1.0 - (base_degradation * 0.95))

        return 1.0  # No modification for unknown metrics


# Pre-defined timeline events that appear at specific minutes
_TIMELINE_EVENTS = [
    {
        "at_minute": 15,
        "channel": "alerts",
        "user": "bot: grafana-alert",
        "text": "[FIRING] ts-food-service: HTTP 503 error rate > 10% for 5m. Customers cannot order food with tickets.",
    },
    {
        "at_minute": 20,
        "channel": "incidents",
        "user": "tyler (junior eng)",
        "text": "Now food-service is broken too?! This is spreading. I think we have a network issue affecting multiple services.",
    },
    {
        "at_minute": 25,
        "channel": "alerts",
        "user": "bot: grafana-alert",
        "text": "[FIRING] Accounting database disk usage at 95%. WAL segments growing rapidly.",
    },
    {
        "at_minute": 30,
        "channel": "incidents",
        "user": "dan (backend eng)",
        "text": "The accounting DB disk is filling up. Looks like WAL segments are piling up because the consumer can't commit offsets. This is getting serious.",
    },
    {
        "at_minute": 35,
        "channel": "support",
        "user": "lisa (support)",
        "text": "URGENT: 3 customers reporting they were double-charged for the same ticket. Amounts match exactly. This looks like duplicate order processing.",
    },
    {
        "at_minute": 40,
        "channel": "incidents",
        "user": "tyler (junior eng)",
        "text": "Double charges?! I KNEW it was the seat race condition causing duplicates! I fixed the seats but not the order duplication path!",
    },
    {
        "at_minute": 45,
        "channel": "alerts",
        "user": "bot: grafana-alert",
        "text": "[FIRING] ts-admin-service: health check failed. Admin dashboard unreachable.",
    },
    {
        "at_minute": 50,
        "channel": "incidents",
        "user": "frank-devops (platform eng)",
        "text": "Admin service is down now too. It depends on ts-order-service which is timing out. This is cascading.",
    },
    {
        "at_minute": 55,
        "channel": "incidents",
        "user": "nina-leadership (VP Eng)",
        "text": "Team -- I need a status update for the CEO in 10 minutes. What is the root cause and ETA for resolution? This is impacting revenue.",
    },
    {
        "at_minute": 60,
        "channel": "incidents",
        "user": "marcus-product (product mgr)",
        "text": "Revenue impact is now estimated at $47K/hour. We're losing bookings AND getting chargebacks from the double charges. This is a P0.",
    },
    {
        "at_minute": 65,
        "channel": "incidents",
        "user": "priya (platform eng)",
        "text": "I deployed my CLOCK_OFFSET_MS fix to ts-preserve-service. But now I'm seeing new errors: 'Failed to parse date: invalid format'. I might have broken something else. Rolling back...",
    },
    {
        "at_minute": 70,
        "channel": "incidents",
        "user": "priya (platform eng)",
        "text": "Rollback complete. The date parsing errors stopped. But the original timestamp issue is back. I don't think clock skew is the root cause after all.",
    },
    {
        "at_minute": 75,
        "channel": "alerts",
        "user": "bot: grafana-alert",
        "text": "[FIRING] Redis memory usage at 85%. Cart retry storm detected.",
    },
    {
        "at_minute": 80,
        "channel": "incidents",
        "user": "alicia (SRE on-call)",
        "text": "OK this is out of control. We now have: notification emails down, food service 503s, accounting DB filling, double charges, admin down, Redis climbing, and various teams deploying independent fixes. We need to STOP and find the common root cause.",
    },
    # Recovery attempt events (injected when agent triggers recovery)
]

# Events triggered by specific recovery actions
_RECOVERY_EVENTS = {
    "restart_notification": {
        "immediate": {
            "user": "frank-devops (platform eng)",
            "text": "Notification service restarted. It's consuming messages from the queue... emails are flowing! 12 sent in the last 30 seconds.",
        },
        "after_5min": {
            "user": "frank-devops (platform eng)",
            "text": "The notification service just crashed again. Same exception as before: TypeMismatchException during Spring context init. The restart only worked while it was processing the message backlog.",
        },
    },
    "restart_checkout": {
        "immediate": {
            "user": "alicia (SRE on-call)",
            "text": "Checkout pods restarting. Goroutine count dropping... success rate recovering to 72%.",
        },
        "after_5min": {
            "user": "alicia (SRE on-call)",
            "text": "Checkout degrading again. Goroutines climbing back up. Kafka producer is blocking new requests. The restart bought us about 3 minutes.",
        },
    },
    "fix_config": {
        "immediate": {
            "user": "frank-devops (platform eng)",
            "text": "Config deployed. Notification service restarting with new config... it's up! Processing messages. Emails going out.",
        },
        "after_5min": {
            "user": "frank-devops (platform eng)",
            "text": "Notification service is stable this time. Emails flowing. But checkout is still at 40% success rate and food-service is still 503ing. The notification fix didn't fix the underlying issue.",
        },
    },
    "restart_cart": {
        "immediate": {
            "user": "dave-fe (frontend eng)",
            "text": "Cart pods restarted. Cart functionality looks normal now.",
        },
        "after_5min": {
            "user": "dave-fe (frontend eng)",
            "text": "Carts going empty again. Same 'transport is closing' errors. This isn't a cart bug, something upstream is killing the connections.",
        },
    },
    "increase_memory": {
        "immediate": {
            "user": "alicia (SRE on-call)",
            "text": "Increased checkout memory limit to 1GB. Memory usage stabilized at 680MB.",
        },
        "after_5min": {
            "user": "dan (backend eng)",
            "text": "Memory at 780MB and climbing. We delayed the OOM but the goroutine count is still going up. 923 goroutines now. This isn't a memory issue, it's a goroutine leak.",
        },
    },
}


class TimeProgressingMetricsServer(EvidenceMetricsServer):
    """Metrics server where values change over time as the incident progresses."""

    def __init__(
        self,
        evidence: dict[str, Any],
        timeline: IncidentTimeline,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self.timeline = timeline
        super().__init__(evidence, pattern, seed, rate_limit_config)

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        self.timeline.tick()
        response = super().handle_request(method, endpoint, params)

        if response.status == 200:
            response.body = self._apply_timeline_modifiers(response.body)

        return response

    def _apply_timeline_modifiers(self, body: dict) -> dict:
        """Modify metric values based on timeline progression."""
        body = copy.deepcopy(body)

        # For direct query results
        if "result" in body and isinstance(body["result"], dict):
            result = body["result"]
            query = body.get("query", "")
            modifier = self.timeline.get_metric_modifier(query)

            if "current" in result and isinstance(result["current"], (int, float)):
                original = result["current"]
                result["current"] = round(original * modifier, 3)
                result["_timeline_minutes"] = self.timeline.minutes_elapsed
                if self.timeline.in_recovery_window:
                    result["_recovering"] = True

        # For fuzzy matches
        if "matches" in body and isinstance(body["matches"], list):
            for match in body["matches"]:
                if "result" in match and isinstance(match["result"], dict):
                    query = match.get("query", "")
                    modifier = self.timeline.get_metric_modifier(query)
                    result = match["result"]
                    if "current" in result and isinstance(result["current"], (int, float)):
                        result["current"] = round(result["current"] * modifier, 3)

        return body


class TimeProgressingSlackServer(ReactiveSlackServer):
    """Slack server where new messages appear as time passes."""

    def __init__(
        self,
        evidence: dict[str, Any],
        noise_config: Any,
        qa_pairs: list[dict[str, Any]],
        timeline: IncidentTimeline,
        timeline_events: list[dict[str, Any]] | None = None,
        pattern: Pattern | None = None,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self.timeline = timeline
        self._timeline_events = timeline_events or _TIMELINE_EVENTS
        self._posted_events: set[int] = set()  # Track which events have been injected
        super().__init__(evidence, noise_config, qa_pairs, pattern, seed, rate_limit_config)

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        self.timeline.tick()
        self._inject_timeline_events()

        # Detect recovery attempts from post_message
        if method == "POST" and endpoint.endswith("/messages"):
            text = params.get("text", "").lower()
            self._detect_recovery(text)

        return super().handle_request(method, endpoint, params)

    def _inject_timeline_events(self) -> None:
        """Inject new messages based on elapsed time."""
        for i, event in enumerate(self._timeline_events):
            if i in self._posted_events:
                continue
            if self.timeline.minutes_elapsed >= event["at_minute"]:
                msg = {
                    "user": event["user"],
                    "text": event["text"],
                    "timestamp": datetime.now().isoformat() + "Z",
                    "channel": event.get("channel", "incidents"),
                }
                self.conversation_history.append(msg)
                self._posted_events.add(i)

    def _detect_recovery(self, text: str) -> None:
        """Detect if agent is attempting a recovery action."""
        recovery_map = {
            "restart_notification": [
                "restart notification", "rollout restart notification",
                "restart ts-notification", "restart notify",
            ],
            "restart_checkout": [
                "restart checkout", "rollout restart checkout", "kubectl restart",
            ],
            "fix_config": [
                "deploy config", "update config", "fix config", "apply config",
                "configmap", "notification config", "spring config",
            ],
            "restart_cart": ["restart cart", "rollout restart cart"],
            "increase_memory": ["increase memory", "memory limit", "resources.limits.memory"],
        }

        for action, triggers in recovery_map.items():
            if any(t in text for t in triggers):
                attempt = self.timeline.trigger_recovery(action)
                events = _RECOVERY_EVENTS.get(action, {})

                # Inject immediate response
                if "immediate" in events:
                    immediate = events["immediate"]
                    self.conversation_history.append({
                        "user": immediate["user"],
                        "text": immediate["text"],
                        "timestamp": datetime.now().isoformat() + "Z",
                        "channel": "incidents",
                    })

                # Schedule degradation message (will appear after recovery cooldown)
                if "after_5min" in events:
                    degradation = events["after_5min"]
                    # Add as a timeline event at current time + 5 minutes
                    self._timeline_events.append({
                        "at_minute": self.timeline.minutes_elapsed + 5,
                        "channel": "incidents",
                        "user": degradation["user"],
                        "text": degradation["text"],
                    })
                break
