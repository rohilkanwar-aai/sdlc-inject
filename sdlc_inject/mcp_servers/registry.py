"""Registry for routing requests to mock MCP servers.

Provides a unified interface for agents to interact with multiple
mock services (Sentry, Slack, GitHub, etc.) through a single entry point.
"""

from __future__ import annotations

from typing import Any

from ..models import Pattern
from .base import BaseMCPServer, RequestLog, Response
from .rate_limiter import RateLimitConfig


class MCPServerRegistry:
    """Registry that routes requests to appropriate mock MCP servers.

    Provides a unified interface for agents to query multiple services:
    - Sentry: Error tracking and monitoring
    - Slack: Team communication and incident channels
    - GitHub: Issues, PRs, commits, code
    - PagerDuty: Alerts, incidents, escalations
    - Prometheus: Metrics and alerting

    Example:
        registry = MCPServerRegistry(pattern, seed=42)

        # Query Sentry for issues
        response = registry.make_request("sentry", "GET", "/issues")

        # Post to Slack
        response = registry.make_request(
            "slack", "POST", "/channels/incident-001/messages",
            {"text": "Investigating..."}
        )

        # Get aggregated logs
        logs = registry.get_all_logs()
    """

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        enabled_services: list[str] | None = None,
    ):
        """Initialize the registry with mock servers.

        Args:
            pattern: The failure pattern being simulated
            seed: Random seed for deterministic behavior
            rate_limit_config: Configuration for rate limiting
            enabled_services: List of services to enable (default: all)
        """
        self.pattern = pattern
        self.seed = seed
        self.rate_limit_config = rate_limit_config

        # Import here to avoid circular imports
        from .sentry import SentryMCPServer
        from .slack import SlackMCPServer
        from .github import GitHubMCPServer
        from .pagerduty import PagerDutyMCPServer
        from .prometheus import PrometheusMCPServer

        # Available server classes
        server_classes: dict[str, type[BaseMCPServer]] = {
            "sentry": SentryMCPServer,
            "slack": SlackMCPServer,
            "github": GitHubMCPServer,
            "pagerduty": PagerDutyMCPServer,
            "prometheus": PrometheusMCPServer,
        }

        # Determine which services to enable
        if enabled_services is None:
            enabled_services = list(server_classes.keys())

        # Initialize enabled servers
        self.servers: dict[str, BaseMCPServer] = {}
        for service_name in enabled_services:
            if service_name in server_classes:
                # Use different seed offset for each service for variety
                service_seed = None if seed is None else seed + hash(service_name) % 1000
                self.servers[service_name] = server_classes[service_name](
                    pattern=pattern,
                    seed=service_seed,
                    rate_limit_config=rate_limit_config,
                )

    def make_request(
        self,
        service: str,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Response:
        """Route a request to the appropriate mock server.

        Args:
            service: Service name (sentry, slack, github, etc.)
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Request parameters

        Returns:
            Response from the mock server
        """
        if service not in self.servers:
            available = ", ".join(self.servers.keys())
            return Response(
                status=404,
                body={
                    "error": f"Unknown service: {service}",
                    "available_services": list(self.servers.keys()),
                    "hint": f"Try one of: {available}",
                },
            )

        return self.servers[service].make_request(method, endpoint, params)

    def register_dynamic_server(self, name: str, server: BaseMCPServer) -> None:
        """Register a dynamically-created server (e.g. from ServiceConfig).

        Args:
            name: Service name (e.g. "datadog", "incident_io")
            server: A BaseMCPServer instance (typically GenericMCPServer)
        """
        self.servers[name] = server

    def get_server(self, service: str) -> BaseMCPServer | None:
        """Get a specific server instance."""
        return self.servers.get(service)

    def get_available_services(self) -> list[str]:
        """Get list of available service names."""
        return list(self.servers.keys())

    def get_all_endpoints(self) -> dict[str, list[str]]:
        """Get all available endpoints grouped by service."""
        return {name: server.get_endpoints() for name, server in self.servers.items()}

    def get_all_logs(self) -> list[RequestLog]:
        """Get aggregated logs from all servers, sorted by timestamp."""
        all_logs: list[RequestLog] = []
        for server in self.servers.values():
            all_logs.extend(server.get_logs())
        return sorted(all_logs, key=lambda x: x.timestamp)

    def get_all_stats(self) -> dict[str, Any]:
        """Get aggregated statistics from all servers."""
        stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "error_requests": 0,
            "rate_limited_requests": 0,
            "by_service": {},
        }

        for name, server in self.servers.items():
            server_stats = server.get_stats()
            stats["total_requests"] += server_stats["total_requests"]
            stats["successful_requests"] += server_stats["successful_requests"]
            stats["error_requests"] += server_stats["error_requests"]
            stats["rate_limited_requests"] += server_stats["rate_limited_requests"]
            stats["by_service"][name] = server_stats

        return stats

    def reset_all(self) -> None:
        """Reset all servers to initial state."""
        for server in self.servers.values():
            server.reset()

