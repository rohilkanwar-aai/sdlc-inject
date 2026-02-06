"""Sentry error report artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class SentryArtifactGenerator(ArtifactGenerator):
    """Generates realistic Sentry error reports and events."""

    def generate(self) -> dict[str, Any]:
        """Generate a Sentry issue with events."""
        issue = self._generate_issue()
        events = [self._generate_event(i) for i in range(self.rng.randint(5, 15))]
        breadcrumbs = self._generate_breadcrumbs()

        return {
            "issue": issue,
            "events": events,
            "breadcrumbs": breadcrumbs,
        }

    def _generate_issue(self) -> dict[str, Any]:
        """Generate a Sentry issue (aggregated error)."""
        # Use pattern symptoms to create realistic error
        symptoms = self.pattern.observable_symptoms
        log_messages = symptoms.log_messages if symptoms else []

        error_message = self._derive_error_message()

        return {
            "id": self.random_uuid()[:8],
            "shortId": f"{self.pattern.target_codebase.name.upper()}-{self.rng.randint(1000, 9999)}",
            "title": error_message,
            "culprit": self._get_culprit(),
            "metadata": {
                "type": self._get_error_type(),
                "value": error_message,
                "filename": self._get_filename(),
                "function": self._get_function_name(),
            },
            "count": self.rng.randint(50, 500),
            "userCount": self.rng.randint(10, 100),
            "firstSeen": self.random_timestamp(offset_minutes=-120),
            "lastSeen": self.random_timestamp(offset_minutes=-5),
            "level": "error",
            "status": "unresolved",
            "isUnhandled": True,
            "platform": self._get_platform(),
            "project": {
                "id": self.random_uuid()[:6],
                "name": self.pattern.target_codebase.name,
                "slug": self.pattern.target_codebase.name.lower(),
            },
            "tags": self._generate_tags(),
            "assignedTo": None,
            "annotations": [],
        }

    def _generate_event(self, index: int) -> dict[str, Any]:
        """Generate a single Sentry event (one occurrence)."""
        return {
            "eventID": self.random_uuid(),
            "context": self._generate_context(),
            "contexts": {
                "os": {"name": "Linux", "version": "5.15.0"},
                "runtime": self._get_runtime_context(),
                "trace": {
                    "trace_id": self.random_uuid(),
                    "span_id": self.random_uuid()[:16],
                    "op": "http.server",
                    "status": "internal_error",
                },
            },
            "dateCreated": self.random_timestamp(offset_minutes=-120 + index * 10),
            "dateReceived": self.random_timestamp(offset_minutes=-120 + index * 10),
            "entries": [
                {"type": "exception", "data": self._generate_exception_entry()},
                {"type": "breadcrumbs", "data": {"values": self._generate_breadcrumbs()}},
                {"type": "request", "data": self._generate_request_entry()},
            ],
            "errors": [],
            "fingerprints": [self.random_uuid()[:16]],
            "message": self._derive_error_message(),
            "sdk": {"name": "sentry.rust", "version": "0.31.0"},
            "tags": self._generate_tags(),
            "user": self._generate_user(),
        }

    def _generate_exception_entry(self) -> dict[str, Any]:
        """Generate exception data with stack trace."""
        frames = self._generate_stack_frames()
        return {
            "values": [
                {
                    "type": self._get_error_type(),
                    "value": self._derive_error_message(),
                    "mechanism": {
                        "type": "generic",
                        "handled": False,
                    },
                    "stacktrace": {"frames": frames},
                }
            ]
        }

    def _generate_stack_frames(self) -> list[dict[str, Any]]:
        """Generate realistic stack frames based on pattern."""
        # Get injection files to create relevant stack
        files = self.pattern.injection.files if self.pattern.injection else []

        frames = []
        for file_inj in files[:3]:  # Use first 3 injection files
            frames.append({
                "filename": file_inj.path,
                "absPath": f"/app/{file_inj.path}",
                "function": self._get_function_name(),
                "module": file_inj.path.replace("/", "::").replace(".rs", ""),
                "lineNo": self.rng.randint(20, 200),
                "colNo": self.rng.randint(1, 40),
                "context": self._generate_code_context(),
                "inApp": True,
            })

        # Add some framework frames
        framework_frames = [
            {"filename": "tokio/runtime/scheduler.rs", "function": "block_on", "inApp": False},
            {"filename": "axum/routing/mod.rs", "function": "call", "inApp": False},
            {"filename": "tower/service.rs", "function": "poll_ready", "inApp": False},
        ]
        for frame in framework_frames:
            frame["lineNo"] = self.rng.randint(50, 500)
            frame["inApp"] = False

        return framework_frames + frames

    def _generate_code_context(self) -> list[list]:
        """Generate code context around error line."""
        # Simplified - in real implementation would extract from actual code
        return [
            [-3, "    async fn process_request(&self, req: Request) -> Result<Response> {"],
            [-2, "        let buffer_id = req.buffer_id();"],
            [-1, "        // Check availability before acquiring"],
            [0, "        let lock = self.acquire_buffer_lock(buffer_id).await?;  // <-- ERROR"],
            [1, "        let result = self.process_buffer(&lock).await;"],
            [2, "        Ok(result)"],
        ]

    def _generate_breadcrumbs(self) -> list[dict[str, Any]]:
        """Generate breadcrumbs leading up to error."""
        breadcrumbs = []
        categories = ["http", "query", "info", "debug"]

        # Create breadcrumbs that tell the story
        breadcrumb_templates = [
            ("http", "HTTP request received", {"method": "POST", "url": "/api/buffers"}),
            ("query", "Database query", {"query": "SELECT * FROM buffers WHERE id = $1"}),
            ("info", "Buffer availability check", {"buffer_id": "12345", "available": True}),
            ("debug", "Attempting lock acquisition", {"buffer_id": "12345"}),
            ("query", "Database query", {"query": "UPDATE buffers SET locked_by = $1"}),
            ("error", "Lock acquisition failed", {"reason": "already_locked"}),
        ]

        for i, (cat, msg, data) in enumerate(breadcrumb_templates):
            breadcrumbs.append({
                "timestamp": self.random_timestamp(offset_minutes=-5 + i),
                "type": "default",
                "category": cat,
                "message": msg,
                "data": data,
                "level": "error" if cat == "error" else "info",
            })

        return breadcrumbs

    def _generate_request_entry(self) -> dict[str, Any]:
        """Generate HTTP request context."""
        return {
            "method": "POST",
            "url": f"https://api.{self.pattern.target_codebase.name}.dev/v1/buffers/acquire",
            "headers": [
                ["Content-Type", "application/json"],
                ["Authorization", "Bearer [REDACTED]"],
                ["X-Request-ID", self.random_uuid()],
            ],
            "data": {"buffer_id": "12345", "project_id": "67890"},
            "inferredContentType": "application/json",
        }

    def _generate_context(self) -> dict[str, Any]:
        """Generate custom context."""
        return {
            "pattern_id": self.pattern.id,
            "buffer_state": {
                "buffer_id": "12345",
                "locked_by": None,
                "lock_acquired_at": None,
            },
            "request_context": {
                "user_id": self.random_uuid()[:8],
                "project_id": "67890",
                "concurrent_users": self.rng.randint(2, 10),
            },
        }

    def _generate_tags(self) -> list[list[str]]:
        """Generate Sentry tags."""
        return [
            ["environment", "production"],
            ["server_name", f"collab-{self.rng.randint(1, 5)}"],
            ["release", f"v0.{self.rng.randint(120, 130)}.{self.rng.randint(0, 9)}"],
            ["transaction", "/api/buffers/acquire"],
            ["pattern_category", self.pattern.category],
        ]

    def _generate_user(self) -> dict[str, Any]:
        """Generate user context."""
        return {
            "id": self.random_uuid()[:8],
            "email": f"user{self.rng.randint(1, 1000)}@example.com",
            "ip_address": f"192.168.{self.rng.randint(1, 255)}.{self.rng.randint(1, 255)}",
        }

    def _derive_error_message(self) -> str:
        """Derive error message from pattern."""
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.log_messages:
            # Use pattern from log messages
            return symptoms.log_messages[0].pattern.replace(".*", " ").replace("\\d+", "12345")
        return f"Error in {self.pattern.name}"

    def _get_error_type(self) -> str:
        """Get error type based on pattern category."""
        type_map = {
            "Race Conditions": "ConcurrencyError",
            "Split-Brain": "ConsistencyError",
            "Clock Skew": "TimeSyncError",
            "Consensus": "QuorumError",
        }
        for key, val in type_map.items():
            if key.lower() in self.pattern.subcategory.lower():
                return val
        return "RuntimeError"

    def _get_culprit(self) -> str:
        """Get culprit function/location."""
        if self.pattern.injection and self.pattern.injection.files:
            return self.pattern.injection.files[0].path
        return "unknown"

    def _get_filename(self) -> str:
        """Get primary filename."""
        if self.pattern.injection and self.pattern.injection.files:
            return self.pattern.injection.files[0].path.split("/")[-1]
        return "unknown.rs"

    def _get_function_name(self) -> str:
        """Get function name from golden path or pattern."""
        if self.pattern.golden_path and self.pattern.golden_path.steps:
            for step in self.pattern.golden_path.steps:
                if step.search_queries:
                    return step.search_queries[0]
        return "process_request"

    def _get_platform(self) -> str:
        """Get platform from target codebase."""
        lang = self.pattern.target_codebase.language
        return lang if lang else "rust"

    def _get_runtime_context(self) -> dict[str, Any]:
        """Get runtime context based on language."""
        lang = self.pattern.target_codebase.language
        if lang == "rust":
            return {"name": "rustc", "version": "1.75.0"}
        elif lang == "python":
            return {"name": "CPython", "version": "3.11.0"}
        return {"name": "unknown", "version": "1.0.0"}

    def save(self, output_dir: Path) -> list[Path]:
        """Save Sentry artifacts to files."""
        sentry_dir = output_dir / "sentry"
        sentry_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save issue
        issue_path = sentry_dir / "issue.json"
        issue_path.write_text(json.dumps(artifacts["issue"], indent=2))
        files.append(issue_path)

        # Save events
        events_path = sentry_dir / "events.json"
        events_path.write_text(json.dumps(artifacts["events"], indent=2))
        files.append(events_path)

        # Save breadcrumbs
        breadcrumbs_path = sentry_dir / "breadcrumbs.json"
        breadcrumbs_path.write_text(json.dumps(artifacts["breadcrumbs"], indent=2))
        files.append(breadcrumbs_path)

        # Save combined view (what you'd export from Sentry)
        combined_path = sentry_dir / "sentry_export.json"
        combined_path.write_text(json.dumps(artifacts, indent=2))
        files.append(combined_path)

        return files
