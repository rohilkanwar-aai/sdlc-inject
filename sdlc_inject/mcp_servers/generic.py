"""Generic template-based MCP server driven by a ServiceConfig.

Unlike the hardcoded SentryMCPServer, SlackMCPServer etc., this server
generates its endpoints and mock data entirely from a ServiceConfig object,
allowing it to simulate any tool discovered during neural analysis.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern

# Avoid circular import -- import at usage time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..discovery.service_config import ServiceConfig, EndpointConfig


class GenericMCPServer(BaseMCPServer):
    """Template-based MCP server driven by a ServiceConfig.

    The server:
    1. Reads endpoint definitions from the config
    2. Generates mock data by mutating sample_response templates with
       pattern-aware substitutions (error messages, file paths, timestamps)
    3. Mixes a primary signal entry (related to the actual bug) with noise
    4. Uses deterministic RNG from BaseMCPServer for reproducibility

    This follows the same pattern as the hardcoded servers: primary issue
    generated from the pattern's observable symptoms, plus noise entries.
    """

    def __init__(
        self,
        service_config: "ServiceConfig",
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self.service_config = service_config
        self.service_name = service_config.name
        # Build endpoint lookup before super().__init__ calls _initialize_data
        self._endpoint_map: dict[str, "EndpointConfig"] = {}
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        """Return list of supported API endpoints."""
        return [
            f"{ep.method} {ep.path}"
            for ep in self.service_config.endpoints
        ]

    def _initialize_data(self) -> None:
        """Initialize mock data from service config + pattern context."""
        # Build endpoint lookup: name -> config
        for ep in self.service_config.endpoints:
            self._endpoint_map[ep.name] = ep

        # Extract pattern context for substitutions
        self.state["primary_error"] = ""
        self.state["pattern_id"] = getattr(self.pattern, "id", "UNKNOWN")
        self.state["pattern_category"] = getattr(self.pattern, "category", "unknown")

        symptoms = getattr(self.pattern, "observable_symptoms", None)
        if symptoms:
            error_msgs = getattr(symptoms, "error_messages", [])
            if error_msgs and isinstance(error_msgs, list) and len(error_msgs) > 0:
                self.state["primary_error"] = str(error_msgs[0])

            log_patterns = getattr(symptoms, "log_patterns", [])
            if log_patterns and isinstance(log_patterns, list):
                self.state["log_patterns"] = [str(p) for p in log_patterns]
            else:
                self.state["log_patterns"] = []

        # Pre-generate responses for each endpoint
        self.state["responses"] = {}
        for ep in self.service_config.endpoints:
            self.state["responses"][ep.name] = self._generate_endpoint_data(ep)

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Process a request by matching endpoint and returning mock data."""
        # Try to match by path
        matched_ep = self._match_endpoint(method, endpoint, params)

        if matched_ep is None:
            return Response(
                status=404,
                body={
                    "error": f"Unknown endpoint: {method} {endpoint}",
                    "available_endpoints": self.get_endpoints(),
                },
            )

        # Return pre-generated or dynamically filtered data
        response_data = self.state["responses"].get(matched_ep.name)
        if response_data is None:
            response_data = matched_ep.sample_response or {"status": "ok"}

        # Apply parameter-based filtering if applicable
        filtered = self._apply_filters(response_data, params, matched_ep)

        return Response(status=200, body=filtered)

    def _match_endpoint(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> "EndpointConfig | None":
        """Match an incoming request to a configured endpoint."""
        endpoint_clean = endpoint.strip("/")

        for ep in self.service_config.endpoints:
            ep_path_clean = ep.path.strip("/")

            # Direct name match (tool-style call)
            if endpoint_clean == ep.name:
                return ep

            # Exact path match
            if endpoint_clean == ep_path_clean:
                return ep

            # Path pattern match with {param} placeholders
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", ep_path_clean)
            if re.fullmatch(pattern, endpoint_clean):
                return ep

        # Fallback: try matching just the endpoint name part
        for ep in self.service_config.endpoints:
            if endpoint_clean.endswith(ep.name):
                return ep

        return None

    def _generate_endpoint_data(self, ep: "EndpointConfig") -> Any:
        """Generate mock data for an endpoint from its sample_response template."""
        if not ep.sample_response:
            return {"message": f"No data available for {ep.name}"}

        # Deep copy the sample and apply substitutions
        data = copy.deepcopy(ep.sample_response)
        data = self._apply_substitutions(data)

        # If the response contains a list, add noise entries
        data = self._inject_noise(data, ep)

        return data

    def _apply_substitutions(self, obj: Any) -> Any:
        """Recursively replace {{placeholder}} values with pattern context."""
        if isinstance(obj, str):
            # Replace known placeholders
            obj = obj.replace("{{primary_error}}", self.state.get("primary_error", "Error"))
            obj = obj.replace("{{pattern_id}}", self.state.get("pattern_id", "UNKNOWN"))
            obj = obj.replace(
                "{{pattern_category}}", self.state.get("pattern_category", "unknown")
            )
            obj = obj.replace("{{timestamp}}", datetime.now().isoformat())
            obj = obj.replace(
                "{{recent_timestamp}}",
                (datetime.now() - timedelta(hours=self._random_int(1, 12))).isoformat(),
            )
            obj = obj.replace("{{random_id}}", self._random_id(length=8))
            return obj
        elif isinstance(obj, dict):
            return {k: self._apply_substitutions(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._apply_substitutions(item) for item in obj]
        return obj

    def _inject_noise(self, data: Any, ep: "EndpointConfig") -> Any:
        """Add noise entries to list-type responses.

        If the response contains a top-level key with an array value,
        generate additional noise entries alongside the primary one.
        """
        if not isinstance(data, dict):
            return data

        noise_count = self.service_config.mock_data_hints.get("noise_count", 3)

        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                primary_entry = value[0]
                noise_entries = []

                for i in range(noise_count):
                    noise = copy.deepcopy(primary_entry)
                    noise = self._mutate_noise_entry(noise, i)
                    noise_entries.append(noise)

                # Primary entry first, then noise
                data[key] = [value[0]] + noise_entries
                break  # Only process the first list found

        return data

    def _mutate_noise_entry(self, entry: Any, index: int) -> Any:
        """Mutate a noise entry to differentiate it from the primary."""
        if not isinstance(entry, dict):
            return entry

        noise_errors = [
            "Connection timeout to upstream service",
            "Rate limit exceeded on external API",
            "Temporary disk space warning",
            "Health check flapping on worker node",
            "Slow query detected in analytics pipeline",
        ]

        for key, value in entry.items():
            if key == "id" and isinstance(value, str):
                entry[key] = self._random_id(length=8)
            elif key in ("title", "message", "summary", "description") and isinstance(value, str):
                entry[key] = self._random_choice(noise_errors)
            elif key in ("severity", "urgency", "priority") and isinstance(value, str):
                entry[key] = self._random_choice(["low", "medium", "warning", "info"])
            elif key in ("status", "state") and isinstance(value, str):
                entry[key] = self._random_choice(["resolved", "closed", "acknowledged"])
            elif key in ("created_at", "timestamp", "time") and isinstance(value, str):
                entry[key] = self._random_timestamp(
                    start_hours_ago=72, end_hours_ago=2
                ).isoformat()

        return entry

    def _apply_filters(
        self, data: Any, params: dict[str, Any], ep: "EndpointConfig"
    ) -> Any:
        """Apply query parameter filters to response data."""
        if not isinstance(data, dict) or not params:
            return data

        # Handle limit parameter
        limit = params.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = None

        if limit is not None:
            for key, value in data.items():
                if isinstance(value, list):
                    data[key] = value[:limit]

        # Handle status/state filter
        status_filter = params.get("status") or params.get("state")
        if status_filter and isinstance(status_filter, str):
            for key, value in data.items():
                if isinstance(value, list):
                    data[key] = [
                        item for item in value
                        if not isinstance(item, dict)
                        or item.get("status", "") == status_filter
                        or item.get("state", "") == status_filter
                    ]

        return data
