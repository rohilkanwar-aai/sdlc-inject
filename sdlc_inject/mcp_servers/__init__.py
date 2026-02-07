"""Mock MCP servers for SDLC debugging environments.

This package provides mock implementations of common observability
and collaboration tools that agents interact with during debugging:

- **Sentry**: Error tracking, stack traces, breadcrumbs
- **Slack**: Incident channels, team communication
- **GitHub**: Issues, PRs, commits, code review
- **PagerDuty**: Alerts, incidents, escalations
- **Prometheus**: Metrics, dashboards, alerting

Usage:
    from sdlc_inject.mcp_servers import MCPServerRegistry

    # Initialize with a pattern
    registry = MCPServerRegistry(pattern, seed=42)

    # Make requests
    response = registry.make_request("sentry", "GET", "/issues")

    # Get logs for analytics
    logs = registry.get_all_logs()
"""

from .base import BaseMCPServer, RequestLog, Response
from .rate_limiter import RateLimiter, RateLimitConfig, RateLimitStats
from .registry import MCPServerRegistry
from .sentry import SentryMCPServer
from .slack import SlackMCPServer
from .github import GitHubMCPServer
from .pagerduty import PagerDutyMCPServer
from .prometheus import PrometheusMCPServer
from .generic import GenericMCPServer

__all__ = [
    # Core classes
    "BaseMCPServer",
    "RequestLog",
    "Response",
    # Rate limiting
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitStats",
    # Registry
    "MCPServerRegistry",
    # Mock servers (hardcoded)
    "SentryMCPServer",
    "SlackMCPServer",
    "GitHubMCPServer",
    "PagerDutyMCPServer",
    "PrometheusMCPServer",
    # Mock servers (dynamic)
    "GenericMCPServer",
]
