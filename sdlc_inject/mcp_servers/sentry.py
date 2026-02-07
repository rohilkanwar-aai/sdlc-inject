"""Mock Sentry MCP server for error tracking simulation.

Generates realistic error events, stack traces, and breadcrumbs
based on the failure pattern being debugged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern


class SentryMCPServer(BaseMCPServer):
    """Mock Sentry API server.

    Simulates Sentry's error tracking API with endpoints for:
    - Listing issues
    - Getting issue details
    - Viewing error events
    - Analyzing tags and breadcrumbs

    Data is deterministically generated from the pattern's
    observable symptoms and trigger conditions.
    """

    service_name = "sentry"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /issues",
            "GET /issues/{issue_id}",
            "GET /issues/{issue_id}/events",
            "GET /issues/{issue_id}/tags",
            "GET /issues/{issue_id}/breadcrumbs",
            "POST /issues/{issue_id}/resolve",
            "POST /issues/{issue_id}/ignore",
        ]

    def _initialize_data(self) -> None:
        """Generate Sentry data from pattern symptoms."""
        self.issues: list[dict[str, Any]] = []
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.tags: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.breadcrumbs: dict[str, list[dict[str, Any]]] = {}

        # Extract error messages from pattern
        log_messages = []
        if self.pattern.observable_symptoms:
            for symptom in self.pattern.observable_symptoms.log_messages or []:
                log_messages.append(symptom.pattern)

        # If no log messages, use pattern description
        if not log_messages:
            log_messages = [f"Error in {self.pattern.name}"]

        # Generate issues
        num_issues = self.rng.randint(3, 8)
        for i in range(num_issues):
            issue_id = self._random_id("ISSUE-")
            is_primary = i == 0  # First issue is the primary one (root cause)

            # Primary issue gets symptoms from pattern, others are noise
            if is_primary:
                title = self._random_choice(log_messages)
                culprit = self._generate_culprit()
                count = self.rng.randint(100, 500)
                user_count = self.rng.randint(20, 100)
            else:
                title = self._generate_noise_error()
                culprit = self._generate_noise_culprit()
                count = self.rng.randint(5, 50)
                user_count = self.rng.randint(1, 10)

            issue = {
                "id": issue_id,
                "shortId": f"SDLC-{100 + i}",
                "title": title,
                "culprit": culprit,
                "status": "unresolved" if i < 3 else "resolved",
                "level": "error" if is_primary else self._random_choice(["warning", "error", "info"]),
                "count": count,
                "userCount": user_count,
                "firstSeen": self._random_timestamp(168, 24).isoformat(),  # 1-7 days ago
                "lastSeen": self._random_timestamp(2, 0).isoformat(),  # Last 2 hours
                "isUnhandled": is_primary,
                "hasSeen": False,
                "isBookmarked": False,
                "project": {
                    "id": "12345",
                    "name": self.pattern.target_codebase.name if self.pattern.target_codebase else "project",
                    "slug": "main-service",
                },
                "metadata": {
                    "type": self._get_error_type(is_primary),
                    "value": title,
                    "filename": self._generate_filename(is_primary),
                    "function": self._generate_function_name(is_primary),
                },
            }

            self.issues.append(issue)
            self._generate_events_for_issue(issue_id, is_primary, title)
            self._generate_tags_for_issue(issue_id, is_primary)
            self._generate_breadcrumbs_for_issue(issue_id, is_primary)

    def _generate_culprit(self) -> str:
        """Generate a realistic culprit based on pattern category."""
        category = self.pattern.subcategory or self.pattern.category
        if "race" in category.lower():
            return self._random_choice([
                "concurrent/buffer.rs in acquire_lock",
                "sync/state.py in update_state",
                "workers/processor.go in ProcessConcurrent",
            ])
        elif "split" in category.lower() or "partition" in category.lower():
            return self._random_choice([
                "cluster/consensus.rs in sync_state",
                "replication/sync.py in replicate",
                "distributed/leader.go in ElectLeader",
            ])
        elif "clock" in category.lower() or "time" in category.lower():
            return self._random_choice([
                "time/ordering.rs in compare_timestamps",
                "cache/expiry.py in check_ttl",
                "sync/vector_clock.go in Merge",
            ])
        else:
            return self._random_choice([
                "core/handler.rs in process",
                "api/endpoint.py in handle_request",
                "service/worker.go in Execute",
            ])

    def _generate_noise_error(self) -> str:
        """Generate a non-relevant error for noise."""
        return self._random_choice([
            "Connection timeout to external service",
            "Failed to parse JSON response",
            "Rate limit exceeded on API call",
            "Database query timeout",
            "SSL certificate verification failed",
            "Memory allocation failed",
            "File not found during cache lookup",
            "Invalid UTF-8 sequence in input",
        ])

    def _generate_noise_culprit(self) -> str:
        """Generate a non-relevant culprit."""
        return self._random_choice([
            "http/client.rs in fetch",
            "json/parser.py in decode",
            "api/rate_limit.go in Check",
            "db/query.rs in execute",
            "tls/verify.py in validate",
        ])

    def _get_error_type(self, is_primary: bool) -> str:
        """Get error type based on pattern."""
        if is_primary:
            category = self.pattern.subcategory or self.pattern.category
            if "race" in category.lower():
                return self._random_choice(["DataRaceError", "ConcurrencyError", "LockContention"])
            elif "split" in category.lower():
                return self._random_choice(["ConsistencyError", "PartitionError", "SyncFailure"])
            elif "clock" in category.lower():
                return self._random_choice(["TimestampError", "ClockSkewError", "OrderingViolation"])
            else:
                return "RuntimeError"
        return self._random_choice(["TimeoutError", "IOError", "ParseError", "NetworkError"])

    def _generate_filename(self, is_primary: bool) -> str:
        """Generate a filename."""
        if is_primary and self.pattern.injection and self.pattern.injection.files:
            return self.pattern.injection.files[0].path
        return self._random_choice([
            "src/core/processor.rs",
            "lib/handlers/main.py",
            "pkg/service/worker.go",
            "src/api/routes.ts",
        ])

    def _generate_function_name(self, is_primary: bool) -> str:
        """Generate a function name."""
        if is_primary:
            category = self.pattern.subcategory or self.pattern.category
            if "race" in category.lower():
                return self._random_choice(["acquire_lock", "update_state", "sync_buffer"])
            elif "split" in category.lower():
                return self._random_choice(["replicate", "sync_cluster", "elect_leader"])
            elif "clock" in category.lower():
                return self._random_choice(["compare_time", "check_expiry", "merge_clocks"])
        return self._random_choice(["handle", "process", "execute", "run"])

    def _generate_events_for_issue(self, issue_id: str, is_primary: bool, title: str) -> None:
        """Generate error events for an issue."""
        events = []
        num_events = self.rng.randint(5, 15) if is_primary else self.rng.randint(2, 5)

        for i in range(num_events):
            event_id = self._random_id()
            timestamp = self._random_timestamp(24, 0)

            event = {
                "eventID": event_id,
                "id": event_id,
                "title": title,
                "message": title,
                "dateCreated": timestamp.isoformat(),
                "dateReceived": timestamp.isoformat(),
                "platform": self._get_platform(),
                "context": self._generate_context(is_primary),
                "entries": [
                    {
                        "type": "exception",
                        "data": {
                            "values": [
                                {
                                    "type": self._get_error_type(is_primary),
                                    "value": title,
                                    "stacktrace": self._generate_stacktrace(is_primary),
                                }
                            ]
                        },
                    }
                ],
                "tags": self._generate_event_tags(is_primary),
                "user": {
                    "id": f"user-{self.rng.randint(1000, 9999)}",
                    "email": f"user{self.rng.randint(1, 100)}@example.com",
                    "ip_address": f"10.0.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}",
                },
            }
            events.append(event)

        self.events[issue_id] = events

    def _get_platform(self) -> str:
        """Get platform based on pattern language."""
        if self.pattern.target_codebase and self.pattern.target_codebase.language:
            lang = self.pattern.target_codebase.language.lower()
            if lang == "rust":
                return "rust"
            elif lang == "python":
                return "python"
            elif lang in ["go", "golang"]:
                return "go"
            elif lang in ["typescript", "javascript"]:
                return "javascript"
        return "python"

    def _generate_context(self, is_primary: bool) -> dict[str, Any]:
        """Generate context for an event."""
        context: dict[str, Any] = {
            "runtime": {"name": "python", "version": "3.11.0"},
            "os": {"name": "Linux", "version": "5.15.0"},
            "device": {"family": "server"},
        }

        if is_primary:
            category = self.pattern.subcategory or self.pattern.category
            if "race" in category.lower():
                context["concurrency"] = {
                    "threads": self.rng.randint(4, 32),
                    "active_locks": self.rng.randint(1, 10),
                    "contention_detected": True,
                }
            elif "clock" in category.lower():
                context["time"] = {
                    "server_time": datetime.now().isoformat(),
                    "client_time": (datetime.now() - timedelta(seconds=self.rng.randint(1, 60))).isoformat(),
                    "drift_ms": self.rng.randint(100, 5000),
                }

        return context

    def _generate_stacktrace(self, is_primary: bool) -> dict[str, Any]:
        """Generate a realistic stack trace."""
        frames = []

        # Add relevant frames based on pattern
        if is_primary and self.pattern.injection and self.pattern.injection.files:
            for file_info in self.pattern.injection.files[:2]:
                frames.append({
                    "filename": file_info.path,
                    "function": self._generate_function_name(True),
                    "lineno": self.rng.randint(50, 500),
                    "colno": self.rng.randint(1, 80),
                    "in_app": True,
                    "context_line": "    # Error occurred here",
                    "pre_context": ["    // Previous line", "    // Setup"],
                    "post_context": ["    // Cleanup", "    // Return"],
                })

        # Add generic frames
        for _ in range(self.rng.randint(3, 6)):
            frames.append({
                "filename": self._random_choice([
                    "tokio/runtime/scheduler.rs",
                    "asyncio/base_events.py",
                    "runtime/proc.go",
                ]),
                "function": self._random_choice(["run", "execute", "spawn", "poll"]),
                "lineno": self.rng.randint(100, 1000),
                "in_app": False,
            })

        return {"frames": frames}

    def _generate_event_tags(self, is_primary: bool) -> list[dict[str, str]]:
        """Generate tags for an event."""
        tags = [
            {"key": "environment", "value": "production"},
            {"key": "server_name", "value": f"server-{self.rng.randint(1, 10)}"},
            {"key": "release", "value": f"v1.{self.rng.randint(0, 99)}.{self.rng.randint(0, 999)}"},
        ]

        if is_primary:
            tags.append({"key": "transaction", "value": "/api/critical"})
            category = self.pattern.subcategory or ""
            if "race" in category.lower():
                tags.append({"key": "concurrency", "value": "high"})

        return tags

    def _generate_tags_for_issue(self, issue_id: str, is_primary: bool) -> None:
        """Generate tag distribution for an issue."""
        tags: dict[str, list[dict[str, Any]]] = {
            "environment": [
                {"value": "production", "count": self.rng.randint(50, 200)},
                {"value": "staging", "count": self.rng.randint(5, 20)},
            ],
            "server_name": [
                {"value": f"server-{i}", "count": self.rng.randint(10, 50)}
                for i in range(1, self.rng.randint(3, 6))
            ],
            "release": [
                {"value": f"v1.{self.rng.randint(0, 99)}.{self.rng.randint(0, 999)}", "count": self.rng.randint(20, 100)}
                for _ in range(self.rng.randint(2, 4))
            ],
        }

        if is_primary:
            tags["transaction"] = [
                {"value": "/api/critical", "count": self.rng.randint(80, 150)},
                {"value": "/api/secondary", "count": self.rng.randint(10, 30)},
            ]

        self.tags[issue_id] = tags

    def _generate_breadcrumbs_for_issue(self, issue_id: str, is_primary: bool) -> None:
        """Generate breadcrumbs for debugging."""
        breadcrumbs = []
        base_time = datetime.now() - timedelta(minutes=5)

        # Generate sequence of breadcrumbs leading to error
        crumb_templates = [
            ("info", "http", "Request started: GET /api/resource"),
            ("info", "query", "Database query: SELECT * FROM resources"),
            ("info", "cache", "Cache lookup: resource_key"),
        ]

        if is_primary:
            category = self.pattern.subcategory or ""
            if "race" in category.lower():
                crumb_templates.extend([
                    ("info", "lock", "Attempting to acquire lock on resource"),
                    ("warning", "lock", "Lock contention detected"),
                    ("info", "lock", "Lock acquired after retry"),
                    ("warning", "concurrency", "Concurrent modification detected"),
                ])
            elif "clock" in category.lower():
                crumb_templates.extend([
                    ("info", "time", "Timestamp check: comparing versions"),
                    ("warning", "time", "Clock drift detected: 2.3s"),
                    ("info", "cache", "Cache entry appears expired"),
                ])

        crumb_templates.append(("error", "exception", "Error occurred"))

        for i, (level, category, message) in enumerate(crumb_templates):
            timestamp = base_time + timedelta(seconds=i * 2 + self.rng.random())
            breadcrumbs.append({
                "timestamp": timestamp.isoformat(),
                "type": "default",
                "category": category,
                "level": level,
                "message": message,
                "data": {},
            })

        self.breadcrumbs[issue_id] = breadcrumbs

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Handle Sentry API requests."""
        # Parse endpoint
        endpoint = endpoint.rstrip("/")

        # GET /issues
        if method == "GET" and endpoint == "/issues":
            return self._handle_list_issues(params)

        # GET /issues/{id}
        match = re.match(r"^/issues/([^/]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_issue(match.group(1))

        # GET /issues/{id}/events
        match = re.match(r"^/issues/([^/]+)/events$", endpoint)
        if match and method == "GET":
            return self._handle_get_events(match.group(1), params)

        # GET /issues/{id}/tags
        match = re.match(r"^/issues/([^/]+)/tags$", endpoint)
        if match and method == "GET":
            return self._handle_get_tags(match.group(1))

        # GET /issues/{id}/breadcrumbs
        match = re.match(r"^/issues/([^/]+)/breadcrumbs$", endpoint)
        if match and method == "GET":
            return self._handle_get_breadcrumbs(match.group(1))

        # POST /issues/{id}/resolve
        match = re.match(r"^/issues/([^/]+)/resolve$", endpoint)
        if match and method == "POST":
            return self._handle_resolve_issue(match.group(1))

        # POST /issues/{id}/ignore
        match = re.match(r"^/issues/([^/]+)/ignore$", endpoint)
        if match and method == "POST":
            return self._handle_ignore_issue(match.group(1))

        return Response(404, {"error": f"Endpoint not found: {method} {endpoint}"})

    def _handle_list_issues(self, params: dict[str, Any]) -> Response:
        """List all issues with optional filtering."""
        issues = self.issues.copy()

        # Filter by status
        status = params.get("status")
        if status:
            issues = [i for i in issues if i["status"] == status]

        # Filter by level
        level = params.get("level")
        if level:
            issues = [i for i in issues if i["level"] == level]

        # Sort by last seen (most recent first)
        issues.sort(key=lambda x: x["lastSeen"], reverse=True)

        # Pagination
        limit = params.get("limit", 10)
        offset = params.get("offset", 0)
        paginated = issues[offset : offset + limit]

        return Response(200, paginated)

    def _handle_get_issue(self, issue_id: str) -> Response:
        """Get a specific issue by ID."""
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                return Response(200, issue)
        return Response(404, {"error": f"Issue not found: {issue_id}"})

    def _handle_get_events(self, issue_id: str, params: dict[str, Any]) -> Response:
        """Get events for an issue."""
        # Find issue by ID or shortId
        found_id = None
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                found_id = issue["id"]
                break

        if not found_id or found_id not in self.events:
            return Response(404, {"error": f"Issue not found: {issue_id}"})

        events = self.events[found_id]
        limit = params.get("limit", 10)
        return Response(200, events[:limit])

    def _handle_get_tags(self, issue_id: str) -> Response:
        """Get tag distribution for an issue."""
        found_id = None
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                found_id = issue["id"]
                break

        if not found_id or found_id not in self.tags:
            return Response(404, {"error": f"Issue not found: {issue_id}"})

        return Response(200, self.tags[found_id])

    def _handle_get_breadcrumbs(self, issue_id: str) -> Response:
        """Get breadcrumbs for an issue."""
        found_id = None
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                found_id = issue["id"]
                break

        if not found_id or found_id not in self.breadcrumbs:
            return Response(404, {"error": f"Issue not found: {issue_id}"})

        return Response(200, {"values": self.breadcrumbs[found_id]})

    def _handle_resolve_issue(self, issue_id: str) -> Response:
        """Resolve an issue."""
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                issue["status"] = "resolved"
                return Response(200, issue)
        return Response(404, {"error": f"Issue not found: {issue_id}"})

    def _handle_ignore_issue(self, issue_id: str) -> Response:
        """Ignore an issue."""
        for issue in self.issues:
            if issue["id"] == issue_id or issue["shortId"] == issue_id:
                issue["status"] = "ignored"
                return Response(200, issue)
        return Response(404, {"error": f"Issue not found: {issue_id}"})
