"""Application log artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class LogArtifactGenerator(ArtifactGenerator):
    """Generates realistic application logs (structured and plaintext)."""

    def generate(self) -> dict[str, Any]:
        """Generate log entries."""
        return {
            "structured": self._generate_structured_logs(),
            "plaintext": self._generate_plaintext_logs(),
            "error_logs": self._generate_error_logs(),
        }

    def _generate_structured_logs(self) -> list[dict[str, Any]]:
        """Generate structured JSON logs."""
        logs = []

        # Generate normal request logs
        for i in range(20):
            logs.append(self._normal_request_log(offset=-120 + i * 3))

        # Generate error logs based on pattern symptoms
        symptoms = self.pattern.observable_symptoms
        log_patterns = symptoms.log_messages if symptoms else []

        for i in range(10):
            offset = -100 + i * 5
            logs.append(self._error_log(offset, log_patterns))

        # Sort by timestamp
        logs.sort(key=lambda x: x["timestamp"])
        return logs

    def _normal_request_log(self, offset: int) -> dict[str, Any]:
        """Generate a normal request log entry."""
        duration = self.rng.randint(10, 100)
        return {
            "timestamp": self.random_timestamp(offset_minutes=offset),
            "level": "INFO",
            "message": "Request completed",
            "service": self.pattern.target_codebase.name,
            "logger": "http::server",
            "request_id": self.random_uuid()[:16],
            "method": "POST",
            "path": "/api/buffers/acquire",
            "status": 200,
            "duration_ms": duration,
            "user_id": self.random_uuid()[:8],
            "buffer_id": f"buf_{self.rng.randint(1000, 9999)}",
            "span_id": self.random_uuid()[:16],
            "trace_id": self.random_uuid(),
        }

    def _error_log(self, offset: int, log_patterns: list) -> dict[str, Any]:
        """Generate an error log entry based on pattern symptoms."""
        # Use pattern-defined log messages if available
        if log_patterns:
            pattern = self.random_choice(log_patterns)
            level = pattern.level.upper()
            message = pattern.pattern.replace(".*", " ").replace("\\d+", str(self.rng.randint(1000, 9999)))
        else:
            level = "ERROR"
            message = "Buffer lock acquisition failed"

        return {
            "timestamp": self.random_timestamp(offset_minutes=offset),
            "level": level,
            "message": message,
            "service": self.pattern.target_codebase.name,
            "logger": self._get_logger_name(),
            "request_id": self.random_uuid()[:16],
            "error": {
                "type": "LockAcquisitionError",
                "message": message,
                "stack_trace": self._generate_stack_trace(),
            },
            "context": {
                "buffer_id": f"buf_{self.rng.randint(1000, 9999)}",
                "user_id": self.random_uuid()[:8],
                "concurrent_requests": self.rng.randint(2, 10),
            },
            "span_id": self.random_uuid()[:16],
            "trace_id": self.random_uuid(),
        }

    def _get_logger_name(self) -> str:
        """Get logger name from injection files."""
        if self.pattern.injection and self.pattern.injection.files:
            path = self.pattern.injection.files[0].path
            return path.replace("/", "::").replace(".rs", "").replace("crates/", "")
        return "app::handler"

    def _generate_stack_trace(self) -> str:
        """Generate a realistic stack trace."""
        files = self.pattern.injection.files if self.pattern.injection else []

        frames = []
        for f in files[:3]:
            module = f.path.replace("/", "::").replace(".rs", "").replace("crates/", "")
            frames.append(f"  at {module}::process (line {self.rng.randint(50, 200)})")

        frames.extend([
            f"  at tokio::runtime::task::harness (line 312)",
            f"  at std::thread::local (line 167)",
        ])

        return "\n".join(frames)

    def _generate_plaintext_logs(self) -> str:
        """Generate traditional plaintext log output."""
        lines = []

        for i in range(50):
            offset = -120 + i * 2
            ts = self.random_timestamp(offset_minutes=offset)

            if i % 5 == 0:  # Some errors
                level = "ERROR"
                msg = self._get_error_message()
            elif i % 3 == 0:  # Some warnings
                level = "WARN"
                msg = "Lock acquisition taking longer than expected"
            else:
                level = "INFO"
                msg = f"Request completed in {self.rng.randint(10, 100)}ms"

            lines.append(f"{ts} [{level}] [{self._get_logger_name()}] {msg}")

        return "\n".join(lines)

    def _get_error_message(self) -> str:
        """Get error message from pattern."""
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.log_messages:
            return symptoms.log_messages[0].pattern.replace(".*", " ")
        return "Buffer lock acquisition failed"

    def _generate_error_logs(self) -> list[dict[str, Any]]:
        """Generate just the error logs (filtered view)."""
        all_logs = self._generate_structured_logs()
        return [log for log in all_logs if log["level"] in ("ERROR", "WARN")]

    def save(self, output_dir: Path) -> list[Path]:
        """Save log artifacts to files."""
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save structured logs (JSONL format - one JSON per line)
        structured_path = logs_dir / "app.jsonl"
        with structured_path.open("w") as f:
            for log in artifacts["structured"]:
                f.write(json.dumps(log) + "\n")
        files.append(structured_path)

        # Save plaintext logs
        plaintext_path = logs_dir / "app.log"
        plaintext_path.write_text(artifacts["plaintext"])
        files.append(plaintext_path)

        # Save error-only logs
        errors_path = logs_dir / "errors.jsonl"
        with errors_path.open("w") as f:
            for log in artifacts["error_logs"]:
                f.write(json.dumps(log) + "\n")
        files.append(errors_path)

        return files
