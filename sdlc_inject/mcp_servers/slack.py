"""Mock Slack MCP server for team communication simulation.

Generates realistic incident channels, messages, and threads
based on the failure pattern being debugged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern


class SlackMCPServer(BaseMCPServer):
    """Mock Slack API server.

    Simulates Slack's API with endpoints for:
    - Listing channels
    - Getting channel messages
    - Reading threads
    - Posting messages (stateful)

    Data is deterministically generated from the pattern's
    symptoms and incident context.
    """

    service_name = "slack"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /channels",
            "GET /channels/{channel_id}",
            "GET /channels/{channel_id}/messages",
            "GET /channels/{channel_id}/threads/{ts}",
            "POST /channels/{channel_id}/messages",
            "GET /users",
            "GET /users/{user_id}",
        ]

    def _initialize_data(self) -> None:
        """Generate Slack data from pattern context."""
        self.channels: list[dict[str, Any]] = []
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.threads: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.users: list[dict[str, Any]] = []

        # Generate users
        self._generate_users()

        # Generate incident channel
        incident_channel = self._generate_incident_channel()
        self.channels.append(incident_channel)
        self._generate_incident_messages(incident_channel["id"])

        # Generate related channels
        related_channels = [
            {"name": "engineering", "topic": "Engineering team discussion"},
            {"name": "alerts", "topic": "Automated alerts from monitoring"},
            {"name": "oncall", "topic": "On-call coordination"},
        ]

        for ch in related_channels:
            channel = self._generate_channel(ch["name"], ch["topic"])
            self.channels.append(channel)
            self._generate_channel_messages(channel["id"], ch["name"])

    def _generate_users(self) -> None:
        """Generate team members."""
        roles = [
            ("Sarah Chen", "Platform Lead", True),
            ("Mike Johnson", "SRE", True),
            ("Alex Rivera", "Backend Engineer", True),
            ("Jordan Kim", "DevOps", False),
            ("Pat Williams", "Engineering Manager", False),
            ("Casey Brown", "Database Admin", False),
        ]

        for i, (name, title, is_oncall) in enumerate(roles):
            user_id = f"U{self._random_id(length=9).upper()}"
            self.users.append({
                "id": user_id,
                "name": name.lower().replace(" ", "."),
                "real_name": name,
                "title": title,
                "is_oncall": is_oncall,
                "status": {
                    "emoji": ":fire:" if is_oncall else "",
                    "text": "On-call" if is_oncall else "",
                },
                "profile": {
                    "email": f"{name.lower().replace(' ', '.')}@company.com",
                    "image_24": f"https://avatars.example.com/{i}.png",
                },
            })

    def _generate_channel(self, name: str, topic: str) -> dict[str, Any]:
        """Generate a channel."""
        channel_id = f"C{self._random_id(length=9).upper()}"
        return {
            "id": channel_id,
            "name": name,
            "name_normalized": name.lower().replace("-", "_"),
            "topic": {"value": topic},
            "purpose": {"value": topic},
            "is_private": False,
            "is_archived": False,
            "num_members": self.rng.randint(10, 50),
            "created": int((datetime.now() - timedelta(days=365)).timestamp()),
        }

    def _generate_incident_channel(self) -> dict[str, Any]:
        """Generate the main incident channel."""
        now = datetime.now()
        incident_date = now.strftime("%Y-%m-%d")
        incident_num = self.rng.randint(100, 999)

        channel_id = f"C{self._random_id(length=9).upper()}"
        channel_name = f"incident-{incident_date}-{incident_num}"

        # Extract symptom for topic
        topic = f"Investigating: {self.pattern.name}"
        if self.pattern.observable_symptoms and self.pattern.observable_symptoms.user_visible:
            symptom = self.pattern.observable_symptoms.user_visible[0].symptom
            topic = f"Investigating: {symptom}"

        return {
            "id": channel_id,
            "name": channel_name,
            "name_normalized": channel_name.replace("-", "_"),
            "topic": {"value": topic},
            "purpose": {"value": f"Incident channel for {self.pattern.id}"},
            "is_private": False,
            "is_archived": False,
            "is_incident": True,
            "num_members": len(self.users),
            "created": int((now - timedelta(hours=2)).timestamp()),
        }

    def _generate_incident_messages(self, channel_id: str) -> None:
        """Generate incident channel messages."""
        messages = []
        threads: dict[str, list[dict[str, Any]]] = {}

        base_time = datetime.now() - timedelta(hours=2)
        oncall_users = [u for u in self.users if u["is_oncall"]]
        all_users = self.users

        # Incident timeline
        timeline = self._get_incident_timeline()

        for i, (minutes, user_type, message, has_thread) in enumerate(timeline):
            ts = base_time + timedelta(minutes=minutes)
            ts_str = f"{ts.timestamp():.6f}"

            if user_type == "oncall":
                user = self._random_choice(oncall_users)
            elif user_type == "bot":
                user = {"id": "USLACKBOT", "name": "slackbot", "real_name": "Slackbot"}
            else:
                user = self._random_choice(all_users)

            msg = {
                "type": "message",
                "ts": ts_str,
                "user": user["id"],
                "username": user.get("name", "unknown"),
                "text": message,
                "reply_count": 0,
                "reply_users_count": 0,
            }

            if has_thread:
                # Generate thread replies
                thread_messages = self._generate_thread_replies(ts, user)
                msg["reply_count"] = len(thread_messages)
                msg["reply_users_count"] = len(set(m["user"] for m in thread_messages))
                msg["latest_reply"] = thread_messages[-1]["ts"] if thread_messages else ts_str
                threads[ts_str] = thread_messages

            messages.append(msg)

        self.messages[channel_id] = messages
        self.threads[channel_id] = threads

    def _get_incident_timeline(self) -> list[tuple[int, str, str, bool]]:
        """Generate incident timeline based on pattern."""
        # (minutes_from_start, user_type, message, has_thread)
        timeline = [
            (0, "bot", ":rotating_light: *Alert triggered*: Production errors increasing", False),
            (2, "oncall", "Acknowledging, looking into this now", False),
        ]

        # Add pattern-specific messages
        category = (self.pattern.subcategory or self.pattern.category).lower()

        if "race" in category:
            timeline.extend([
                (5, "oncall", "Seeing intermittent errors in logs, looks like timing-related", False),
                (8, "engineer", "Could be a race condition? I saw similar issues last month", True),
                (15, "oncall", "Confirmed - multiple users hitting the same resource simultaneously", False),
                (20, "oncall", "Found check-then-act pattern without proper locking", True),
            ])
        elif "split" in category or "partition" in category:
            timeline.extend([
                (5, "oncall", "Cluster showing inconsistent state between nodes", False),
                (10, "engineer", "Network looks fine, but some nodes aren't syncing", True),
                (18, "oncall", "Found it - partition caused split-brain scenario", False),
                (25, "oncall", "Working on merge strategy for diverged state", True),
            ])
        elif "clock" in category or "time" in category:
            timeline.extend([
                (5, "oncall", "Weird - some records appear to be from the future?", False),
                (10, "engineer", "NTP sync looks off on some nodes", True),
                (15, "oncall", "Clock drift is causing timestamp comparison failures", False),
                (22, "oncall", "Need to handle clock skew in the comparison logic", True),
            ])
        else:
            timeline.extend([
                (5, "oncall", "Investigating error patterns in logs", False),
                (10, "engineer", "I might have seen this before, let me check", True),
                (18, "oncall", "Found suspicious code path", False),
                (25, "oncall", "Working on a fix", True),
            ])

        # Add common follow-up messages
        timeline.extend([
            (35, "manager", "What's the current status?", False),
            (38, "oncall", "Root cause identified, implementing fix", False),
            (50, "oncall", "Fix deployed to staging, testing now", False),
            (65, "oncall", "Staging looks good, requesting production deploy approval", True),
        ])

        return timeline

    def _generate_thread_replies(
        self, parent_ts: datetime, parent_user: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate replies to a thread."""
        replies = []
        other_users = [u for u in self.users if u["id"] != parent_user["id"]]

        num_replies = self.rng.randint(2, 5)
        for i in range(num_replies):
            reply_ts = parent_ts + timedelta(minutes=i * 2 + self.rng.randint(1, 5))
            user = self._random_choice(other_users)

            reply_messages = [
                "Good catch, I'll look into that",
                "Can you share the stack trace?",
                "I think I've seen this pattern before",
                "Let me check the logs on my end",
                "That makes sense, +1 on that approach",
                "Should we loop in the database team?",
                "I can help with testing once the fix is ready",
            ]

            replies.append({
                "type": "message",
                "ts": f"{reply_ts.timestamp():.6f}",
                "user": user["id"],
                "username": user["name"],
                "text": self._random_choice(reply_messages),
                "thread_ts": f"{parent_ts.timestamp():.6f}",
            })

        return replies

    def _generate_channel_messages(self, channel_id: str, channel_name: str) -> None:
        """Generate messages for a regular channel."""
        messages = []
        base_time = datetime.now() - timedelta(hours=24)

        if channel_name == "alerts":
            # Generate automated alert messages
            alert_templates = [
                ":warning: High memory usage on node-{n}",
                ":chart_with_upwards_trend: Response latency p99 > 500ms",
                ":rotating_light: Error rate spike detected",
                ":white_check_mark: Alert resolved: CPU normalized",
            ]
            for i in range(self.rng.randint(5, 10)):
                ts = base_time + timedelta(hours=self.rng.uniform(0, 24))
                messages.append({
                    "type": "message",
                    "ts": f"{ts.timestamp():.6f}",
                    "user": "USLACKBOT",
                    "username": "alertbot",
                    "text": self._random_choice(alert_templates).format(n=self.rng.randint(1, 10)),
                    "subtype": "bot_message",
                })
        else:
            # Generate team discussion messages
            for i in range(self.rng.randint(3, 8)):
                ts = base_time + timedelta(hours=self.rng.uniform(0, 24))
                user = self._random_choice(self.users)
                messages.append({
                    "type": "message",
                    "ts": f"{ts.timestamp():.6f}",
                    "user": user["id"],
                    "username": user["name"],
                    "text": self._random_choice([
                        "Has anyone seen the latest deployment?",
                        "PR looks good, merging now",
                        "Quick question about the API changes",
                        "Meeting notes shared in the doc",
                    ]),
                })

        messages.sort(key=lambda x: float(x["ts"]))
        self.messages[channel_id] = messages
        self.threads[channel_id] = {}

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Handle Slack API requests."""
        endpoint = endpoint.rstrip("/")

        # GET /channels
        if method == "GET" and endpoint == "/channels":
            return self._handle_list_channels(params)

        # GET /channels/{id}
        match = re.match(r"^/channels/([^/]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_channel(match.group(1))

        # GET /channels/{id}/messages
        match = re.match(r"^/channels/([^/]+)/messages$", endpoint)
        if match and method == "GET":
            return self._handle_get_messages(match.group(1), params)

        # GET /channels/{id}/threads/{ts}
        match = re.match(r"^/channels/([^/]+)/threads/([^/]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_thread(match.group(1), match.group(2))

        # POST /channels/{id}/messages
        match = re.match(r"^/channels/([^/]+)/messages$", endpoint)
        if match and method == "POST":
            return self._handle_post_message(match.group(1), params)

        # GET /users
        if method == "GET" and endpoint == "/users":
            return self._handle_list_users(params)

        # GET /users/{id}
        match = re.match(r"^/users/([^/]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_user(match.group(1))

        return Response(404, {"error": f"Endpoint not found: {method} {endpoint}"})

    def _handle_list_channels(self, params: dict[str, Any]) -> Response:
        """List all channels."""
        channels = self.channels.copy()

        # Filter by incident
        if params.get("incident_only"):
            channels = [c for c in channels if c.get("is_incident")]

        return Response(200, {"channels": channels})

    def _handle_get_channel(self, channel_id: str) -> Response:
        """Get a specific channel."""
        for channel in self.channels:
            if channel["id"] == channel_id or channel["name"] == channel_id:
                return Response(200, {"channel": channel})
        return Response(404, {"error": f"Channel not found: {channel_id}"})

    def _handle_get_messages(self, channel_id: str, params: dict[str, Any]) -> Response:
        """Get messages from a channel."""
        # Find channel by ID or name
        found_id = None
        for channel in self.channels:
            if channel["id"] == channel_id or channel["name"] == channel_id:
                found_id = channel["id"]
                break

        if not found_id or found_id not in self.messages:
            return Response(404, {"error": f"Channel not found: {channel_id}"})

        messages = self.messages[found_id]

        # Pagination
        limit = params.get("limit", 100)
        oldest = params.get("oldest")
        latest = params.get("latest")

        if oldest:
            messages = [m for m in messages if float(m["ts"]) >= float(oldest)]
        if latest:
            messages = [m for m in messages if float(m["ts"]) <= float(latest)]

        # Sort by timestamp descending (most recent first)
        messages = sorted(messages, key=lambda x: float(x["ts"]), reverse=True)[:limit]

        return Response(200, {"messages": messages, "has_more": len(messages) >= limit})

    def _handle_get_thread(self, channel_id: str, thread_ts: str) -> Response:
        """Get thread replies."""
        # Find channel
        found_id = None
        for channel in self.channels:
            if channel["id"] == channel_id or channel["name"] == channel_id:
                found_id = channel["id"]
                break

        if not found_id:
            return Response(404, {"error": f"Channel not found: {channel_id}"})

        channel_threads = self.threads.get(found_id, {})
        if thread_ts not in channel_threads:
            return Response(404, {"error": f"Thread not found: {thread_ts}"})

        return Response(200, {"messages": channel_threads[thread_ts]})

    def _handle_post_message(self, channel_id: str, params: dict[str, Any]) -> Response:
        """Post a message to a channel (stateful)."""
        # Find channel
        found_id = None
        for channel in self.channels:
            if channel["id"] == channel_id or channel["name"] == channel_id:
                found_id = channel["id"]
                break

        if not found_id:
            return Response(404, {"error": f"Channel not found: {channel_id}"})

        text = params.get("text", "")
        if not text:
            return Response(400, {"error": "Message text is required"})

        ts = f"{datetime.now().timestamp():.6f}"
        message = {
            "type": "message",
            "ts": ts,
            "user": "UAGENT",
            "username": "ai-agent",
            "text": text,
        }

        # Add thread_ts if replying to thread
        if params.get("thread_ts"):
            message["thread_ts"] = params["thread_ts"]

        # Store the message
        if found_id not in self.messages:
            self.messages[found_id] = []
        self.messages[found_id].append(message)

        return Response(200, {"ok": True, "ts": ts, "message": message})

    def _handle_list_users(self, params: dict[str, Any]) -> Response:
        """List all users."""
        users = self.users.copy()

        if params.get("oncall_only"):
            users = [u for u in users if u.get("is_oncall")]

        return Response(200, {"members": users})

    def _handle_get_user(self, user_id: str) -> Response:
        """Get a specific user."""
        for user in self.users:
            if user["id"] == user_id or user["name"] == user_id:
                return Response(200, {"user": user})
        return Response(404, {"error": f"User not found: {user_id}"})
