"""MCP Server integration with the evaluation harness.

This module integrates mock MCP servers (Sentry, Slack, GitHub, PagerDuty,
Prometheus) with the agent evaluation loop, providing:

1. Tool definitions for agents to call MCP services
2. Rate limit enforcement and tracking
3. Request logging for grading and analytics
4. In-process SDK MCP server creation via create_sdk_mcp_server()
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from ..mcp_servers import MCPServerRegistry
from ..mcp_servers.rate_limiter import RateLimitConfig
from ..models import Pattern


@dataclass
class MCPConfig:
    """Configuration for MCP servers in an evaluation."""

    enabled: bool = True
    seed: int | None = None

    # Rate limiting configuration
    rate_limit_enabled: bool = True
    requests_per_minute: int = 30
    burst_limit: int = 5
    penalty_multiplier: float = 2.0

    # Services to enable (hardcoded)
    enable_sentry: bool = True
    enable_slack: bool = True
    enable_github: bool = True
    enable_pagerduty: bool = True
    enable_prometheus: bool = True

    # Dynamic service configs (from tool discovery pipeline)
    dynamic_service_configs: list = field(default_factory=list)  # list[ServiceConfig]


@dataclass
class MCPStats:
    """Statistics from MCP usage during evaluation."""

    total_requests: int = 0
    successful_requests: int = 0
    rate_limited_requests: int = 0
    failed_requests: int = 0
    requests_by_service: dict[str, int] = field(default_factory=dict)
    rate_limit_violations: int = 0
    total_response_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "rate_limited_requests": self.rate_limited_requests,
            "failed_requests": self.failed_requests,
            "requests_by_service": self.requests_by_service,
            "rate_limit_violations": self.rate_limit_violations,
            "avg_response_time_ms": (
                self.total_response_time_ms / self.total_requests
                if self.total_requests > 0 else 0
            ),
        }


class MCPToolProvider:
    """Provides MCP tools for agent use and tracks usage.

    Supports two modes:
    1. Legacy mode: get_tool_definitions() + execute_tool() for the old hand-rolled loop
    2. SDK mode: get_sdk_mcp_servers() returns in-process MCP servers for the Agent SDK
    """

    def __init__(
        self,
        pattern: Pattern,
        config: MCPConfig,
    ):
        self.pattern = pattern
        self.config = config
        self.stats = MCPStats()
        self._dynamic_server_names: list[str] = []

        # Create rate limit config
        rate_config = RateLimitConfig(
            requests_per_minute=config.requests_per_minute,
            burst_limit=config.burst_limit,
            penalty_multiplier=config.penalty_multiplier,
        ) if config.rate_limit_enabled else None

        # Initialize MCP registry (hardcoded servers)
        self.registry = MCPServerRegistry(pattern, config.seed, rate_config)

        # Register dynamic servers from ServiceConfigs
        if config.dynamic_service_configs:
            from ..mcp_servers.generic import GenericMCPServer

            for svc_config in config.dynamic_service_configs:
                service_seed = (
                    None if config.seed is None
                    else config.seed + hash(svc_config.name) % 1000
                )
                server = GenericMCPServer(
                    service_config=svc_config,
                    pattern=pattern,
                    seed=service_seed,
                    rate_limit_config=rate_config,
                )
                self.registry.register_dynamic_server(svc_config.name, server)
                self._dynamic_server_names.append(svc_config.name)

    # ------------------------------------------------------------------
    # SDK MCP server creation (new)
    # ------------------------------------------------------------------

    def get_sdk_mcp_servers(self) -> dict[str, Any]:
        """Create in-process SDK MCP servers for the Claude Agent SDK.

        Returns a dict of {server_name: sdk_server} suitable for passing
        to ClaudeAgentOptions(mcp_servers=...).

        Includes both hardcoded servers and dynamically-registered ones.
        Each tool call goes through the existing MCPServerRegistry,
        preserving rate limiting, logging, and stats tracking.
        """
        servers = {}

        # Hardcoded servers
        if self.config.enable_sentry:
            servers["sentry"] = self._create_sentry_sdk_server()

        if self.config.enable_slack:
            servers["slack"] = self._create_slack_sdk_server()

        if self.config.enable_github:
            servers["github"] = self._create_github_sdk_server()

        if self.config.enable_pagerduty:
            servers["pagerduty"] = self._create_pagerduty_sdk_server()

        if self.config.enable_prometheus:
            servers["prometheus"] = self._create_prometheus_sdk_server()

        # Dynamic servers from ServiceConfigs
        for name in self._dynamic_server_names:
            servers[name] = self._create_dynamic_sdk_server(name)

        return servers

    def get_sdk_allowed_tools(self) -> list[str]:
        """Get the list of allowed tool patterns for the SDK.

        Returns patterns like 'mcp__sentry__*' for each enabled service,
        including dynamically-registered services.
        """
        patterns = []
        if self.config.enable_sentry:
            patterns.append("mcp__sentry__*")
        if self.config.enable_slack:
            patterns.append("mcp__slack__*")
        if self.config.enable_github:
            patterns.append("mcp__github__*")
        if self.config.enable_pagerduty:
            patterns.append("mcp__pagerduty__*")
        if self.config.enable_prometheus:
            patterns.append("mcp__prometheus__*")

        # Dynamic servers
        for name in self._dynamic_server_names:
            patterns.append(f"mcp__{name}__*")

        return patterns

    def _execute_and_track(
        self, service: str, endpoint: str, params: dict
    ) -> dict[str, Any]:
        """Execute a request through the registry and track stats.

        Shared by both legacy execute_tool() and SDK tool handlers.
        """
        start_time = datetime.now()
        self.stats.total_requests += 1
        self.stats.requests_by_service[service] = (
            self.stats.requests_by_service.get(service, 0) + 1
        )

        response = self.registry.make_request(service, "GET", f"/{endpoint}", params)

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        self.stats.total_response_time_ms += duration_ms

        if response.status == 200:
            self.stats.successful_requests += 1
            return {"success": True, "data": response.body}
        elif response.status == 429:
            self.stats.rate_limited_requests += 1
            self.stats.rate_limit_violations += 1
            return {
                "error": "Rate limit exceeded",
                "retry_after": response.headers.get("Retry-After", "60"),
            }
        else:
            self.stats.failed_requests += 1
            return {
                "error": response.body.get("error", "Unknown error")
                if isinstance(response.body, dict) else "Unknown error",
            }

    def _make_sdk_tool_handler(self, service: str, endpoint: str):
        """Create a tool handler function that routes through the registry."""
        provider = self  # capture reference for closure

        async def handler(args: dict) -> dict:
            result = provider._execute_and_track(service, endpoint, args)
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, indent=2)}
                ]
            }

        return handler

    def _create_sentry_sdk_server(self):
        """Create in-process SDK MCP server for Sentry."""
        list_issues_handler = self._make_sdk_tool_handler("sentry", "issues")
        get_issue_handler = self._make_sdk_tool_handler("sentry", "issues/{issue_id}")
        get_events_handler = self._make_sdk_tool_handler("sentry", "issues/{issue_id}/events")

        @tool("list_issues", "List error issues from Sentry", {
            "query": {"type": "string", "description": "Search query"},
            "status": {"type": "string", "description": "Issue status filter"},
            "limit": {"type": "integer", "description": "Max issues to return"},
        })
        async def list_issues(args):
            return await list_issues_handler(args)

        @tool("get_issue", "Get detailed information about a specific Sentry issue", {
            "issue_id": {"type": "string", "description": "The Sentry issue ID"},
        })
        async def get_issue(args):
            return await get_issue_handler(args)

        @tool("get_events", "Get recent error events for a Sentry issue", {
            "issue_id": {"type": "string", "description": "The Sentry issue ID"},
            "limit": {"type": "integer", "description": "Max events to return"},
        })
        async def get_events(args):
            return await get_events_handler(args)

        return create_sdk_mcp_server(
            name="sentry",
            version="1.0.0",
            tools=[list_issues, get_issue, get_events],
        )

    def _create_slack_sdk_server(self):
        """Create in-process SDK MCP server for Slack."""
        list_channels_handler = self._make_sdk_tool_handler("slack", "channels")
        get_messages_handler = self._make_sdk_tool_handler("slack", "channels/{channel_id}/messages")
        get_thread_handler = self._make_sdk_tool_handler(
            "slack", "channels/{channel_id}/threads/{thread_ts}"
        )

        @tool("list_channels", "List Slack channels", {
            "filter": {"type": "string", "description": "Filter string"},
        })
        async def list_channels(args):
            return await list_channels_handler(args)

        @tool("get_messages", "Get messages from a Slack channel", {
            "channel_id": {"type": "string", "description": "The Slack channel ID"},
            "limit": {"type": "integer", "description": "Max messages to return"},
        })
        async def get_messages(args):
            return await get_messages_handler(args)

        @tool("get_thread", "Get replies in a Slack thread", {
            "channel_id": {"type": "string", "description": "The Slack channel ID"},
            "thread_ts": {"type": "string", "description": "Timestamp of parent message"},
        })
        async def get_thread(args):
            return await get_thread_handler(args)

        return create_sdk_mcp_server(
            name="slack",
            version="1.0.0",
            tools=[list_channels, get_messages, get_thread],
        )

    def _create_github_sdk_server(self):
        """Create in-process SDK MCP server for GitHub."""
        list_issues_handler = self._make_sdk_tool_handler("github", "repos/issues")
        get_issue_handler = self._make_sdk_tool_handler("github", "repos/issues/{issue_number}")
        list_commits_handler = self._make_sdk_tool_handler("github", "repos/commits")
        get_pr_handler = self._make_sdk_tool_handler("github", "repos/pulls/{pr_number}")

        @tool("list_issues", "List GitHub issues", {
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Filter by labels"},
            "state": {"type": "string", "description": "Issue state filter"},
            "limit": {"type": "integer", "description": "Max issues to return"},
        })
        async def list_issues(args):
            return await list_issues_handler(args)

        @tool("get_issue", "Get detailed information about a GitHub issue", {
            "issue_number": {"type": "integer", "description": "The issue number"},
        })
        async def get_issue(args):
            return await get_issue_handler(args)

        @tool("list_commits", "List recent commits", {
            "path": {"type": "string", "description": "Filter by file path"},
            "author": {"type": "string", "description": "Filter by author"},
            "limit": {"type": "integer", "description": "Max commits to return"},
        })
        async def list_commits(args):
            return await list_commits_handler(args)

        @tool("get_pull_request", "Get details of a pull request", {
            "pr_number": {"type": "integer", "description": "The PR number"},
        })
        async def get_pull_request(args):
            return await get_pr_handler(args)

        return create_sdk_mcp_server(
            name="github",
            version="1.0.0",
            tools=[list_issues, get_issue, list_commits, get_pull_request],
        )

    def _create_pagerduty_sdk_server(self):
        """Create in-process SDK MCP server for PagerDuty."""
        list_incidents_handler = self._make_sdk_tool_handler("pagerduty", "incidents")
        get_incident_handler = self._make_sdk_tool_handler("pagerduty", "incidents/{incident_id}")
        get_timeline_handler = self._make_sdk_tool_handler(
            "pagerduty", "incidents/{incident_id}/log_entries"
        )

        @tool("list_incidents", "List PagerDuty incidents", {
            "urgency": {"type": "string", "description": "Urgency filter (high/low)"},
            "status": {"type": "string", "description": "Status filter"},
            "limit": {"type": "integer", "description": "Max incidents to return"},
        })
        async def list_incidents(args):
            return await list_incidents_handler(args)

        @tool("get_incident", "Get detailed information about a PagerDuty incident", {
            "incident_id": {"type": "string", "description": "The incident ID"},
        })
        async def get_incident(args):
            return await get_incident_handler(args)

        @tool("get_timeline", "Get the timeline of events for an incident", {
            "incident_id": {"type": "string", "description": "The incident ID"},
        })
        async def get_timeline(args):
            return await get_timeline_handler(args)

        return create_sdk_mcp_server(
            name="pagerduty",
            version="1.0.0",
            tools=[list_incidents, get_incident, get_timeline],
        )

    def _create_prometheus_sdk_server(self):
        """Create in-process SDK MCP server for Prometheus."""
        query_handler = self._make_sdk_tool_handler("prometheus", "api/v1/query")
        query_range_handler = self._make_sdk_tool_handler("prometheus", "api/v1/query_range")
        list_alerts_handler = self._make_sdk_tool_handler("prometheus", "api/v1/alerts")

        @tool("query", "Execute a PromQL query against metrics data", {
            "query": {"type": "string", "description": "PromQL query expression"},
            "time": {"type": "string", "description": "Evaluation timestamp"},
        })
        async def prom_query(args):
            return await query_handler(args)

        @tool("query_range", "Execute a PromQL range query for time series data", {
            "query": {"type": "string", "description": "PromQL query expression"},
            "start": {"type": "string", "description": "Start timestamp"},
            "end": {"type": "string", "description": "End timestamp"},
            "step": {"type": "string", "description": "Query resolution step"},
        })
        async def prom_query_range(args):
            return await query_range_handler(args)

        @tool("list_alerts", "List currently firing or pending alerts", {
            "state": {"type": "string", "description": "Alert state filter"},
        })
        async def list_alerts(args):
            return await list_alerts_handler(args)

        return create_sdk_mcp_server(
            name="prometheus",
            version="1.0.0",
            tools=[prom_query, prom_query_range, list_alerts],
        )

    def _create_dynamic_sdk_server(self, service_name: str):
        """Create an in-process SDK MCP server for a dynamically-registered service.

        Reads endpoint definitions from the ServiceConfig and creates
        tool handlers that route through the registry.
        """
        # Find the ServiceConfig for this service
        svc_config = None
        for cfg in self.config.dynamic_service_configs:
            if cfg.name == service_name:
                svc_config = cfg
                break

        if svc_config is None:
            raise ValueError(f"No ServiceConfig found for dynamic service: {service_name}")

        tools = []
        for ep in svc_config.endpoints:
            handler = self._make_sdk_tool_handler(service_name, ep.name)

            # Build parameter schema
            param_schema = {}
            for param in ep.parameters:
                param_def: dict[str, Any] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.enum:
                    param_def["enum"] = param.enum
                param_schema[param.name] = param_def

            # Create the tool using the @tool decorator
            @tool(ep.name, ep.description, param_schema)
            async def tool_handler(args, _handler=handler):
                return await _handler(args)

            tools.append(tool_handler)

        return create_sdk_mcp_server(
            name=service_name,
            version="1.0.0",
            tools=tools,
        )

    # ------------------------------------------------------------------
    # Legacy interface (kept for backward compatibility)
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions for Claude to use (legacy interface)."""
        tools = []

        if self.config.enable_sentry:
            tools.extend(self._sentry_tools())
        if self.config.enable_slack:
            tools.extend(self._slack_tools())
        if self.config.enable_github:
            tools.extend(self._github_tools())
        if self.config.enable_pagerduty:
            tools.extend(self._pagerduty_tools())
        if self.config.enable_prometheus:
            tools.extend(self._prometheus_tools())

        return tools

    def _sentry_tools(self) -> list[dict]:
        return [
            {
                "name": "sentry_list_issues",
                "description": "List error issues from Sentry.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "status": {"type": "string", "enum": ["unresolved", "resolved", "ignored"]},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            },
            {
                "name": "sentry_get_issue",
                "description": "Get detailed information about a specific Sentry issue.",
                "input_schema": {
                    "type": "object",
                    "properties": {"issue_id": {"type": "string"}},
                    "required": ["issue_id"],
                },
            },
            {
                "name": "sentry_get_events",
                "description": "Get recent error events for a Sentry issue.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["issue_id"],
                },
            },
        ]

    def _slack_tools(self) -> list[dict]:
        return [
            {
                "name": "slack_list_channels",
                "description": "List Slack channels.",
                "input_schema": {
                    "type": "object",
                    "properties": {"filter": {"type": "string"}},
                    "required": [],
                },
            },
            {
                "name": "slack_get_messages",
                "description": "Get messages from a Slack channel.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["channel_id"],
                },
            },
            {
                "name": "slack_get_thread",
                "description": "Get replies in a Slack thread.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string"},
                        "thread_ts": {"type": "string"},
                    },
                    "required": ["channel_id", "thread_ts"],
                },
            },
        ]

    def _github_tools(self) -> list[dict]:
        return [
            {
                "name": "github_list_issues",
                "description": "List GitHub issues.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "state": {"type": "string", "enum": ["open", "closed", "all"]},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            },
            {
                "name": "github_get_issue",
                "description": "Get detailed information about a GitHub issue.",
                "input_schema": {
                    "type": "object",
                    "properties": {"issue_number": {"type": "integer"}},
                    "required": ["issue_number"],
                },
            },
            {
                "name": "github_list_commits",
                "description": "List recent commits.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "author": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": [],
                },
            },
            {
                "name": "github_get_pull_request",
                "description": "Get details of a pull request.",
                "input_schema": {
                    "type": "object",
                    "properties": {"pr_number": {"type": "integer"}},
                    "required": ["pr_number"],
                },
            },
        ]

    def _pagerduty_tools(self) -> list[dict]:
        return [
            {
                "name": "pagerduty_list_incidents",
                "description": "List PagerDuty incidents.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "urgency": {"type": "string", "enum": ["high", "low"]},
                        "status": {"type": "string", "enum": ["triggered", "acknowledged", "resolved"]},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            },
            {
                "name": "pagerduty_get_incident",
                "description": "Get detailed information about a PagerDuty incident.",
                "input_schema": {
                    "type": "object",
                    "properties": {"incident_id": {"type": "string"}},
                    "required": ["incident_id"],
                },
            },
            {
                "name": "pagerduty_get_timeline",
                "description": "Get the timeline of events for an incident.",
                "input_schema": {
                    "type": "object",
                    "properties": {"incident_id": {"type": "string"}},
                    "required": ["incident_id"],
                },
            },
        ]

    def _prometheus_tools(self) -> list[dict]:
        return [
            {
                "name": "prometheus_query",
                "description": "Execute a PromQL query against metrics data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "time": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "prometheus_query_range",
                "description": "Execute a PromQL range query for time series data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "step": {"type": "string"},
                    },
                    "required": ["query", "start", "end", "step"],
                },
            },
            {
                "name": "prometheus_list_alerts",
                "description": "List currently firing or pending alerts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "state": {"type": "string", "enum": ["firing", "pending", "inactive"]},
                    },
                    "required": [],
                },
            },
        ]

    def execute_tool(self, tool_name: str, params: dict) -> dict[str, Any]:
        """Execute an MCP tool and return the result (legacy interface)."""
        service, endpoint = self._parse_tool_name(tool_name)
        result = self._execute_and_track(service, endpoint, params)

        # Map to legacy format
        if "error" in result and "retry_after" in result:
            return {
                "success": False,
                "error": result["error"],
                "rate_limited": True,
                "retry_after": result["retry_after"],
            }
        elif "error" in result:
            return {
                "success": False,
                "error": result["error"],
                "rate_limited": False,
            }
        else:
            return {
                "success": True,
                "data": result.get("data"),
                "rate_limited": False,
            }

    def _parse_tool_name(self, tool_name: str) -> tuple[str, str]:
        """Parse tool name into service and endpoint."""
        parts = tool_name.split("_", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", tool_name

    def get_all_request_logs(self) -> list[dict]:
        """Get all request logs from MCP servers for analysis."""
        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "service": log.endpoint.split("/")[0] if "/" in log.endpoint else "unknown",
                "endpoint": log.endpoint,
                "params": log.params,
                "status": log.response_status,
                "duration_ms": log.duration_ms,
            }
            for log in self.registry.get_all_logs()
        ]

    def get_grading_score_adjustment(self) -> float:
        """Calculate grading score adjustment based on API usage efficiency."""
        penalty = 0.0

        if self.stats.rate_limit_violations > 0:
            penalty += min(0.1, self.stats.rate_limit_violations * 0.02)

        if self.stats.total_requests > 50:
            excess = self.stats.total_requests - 50
            penalty += min(0.1, excess * 0.002)

        if self.stats.total_requests > 0:
            success_rate = self.stats.successful_requests / self.stats.total_requests
            if success_rate < 0.8:
                penalty += (0.8 - success_rate) * 0.1

        return max(0.8, 1.0 - penalty)


