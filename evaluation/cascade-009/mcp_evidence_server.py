#!/usr/bin/env python3
"""MCP server that exposes CASCADE-009 evidence as tools for Claude Code.

Run via Claude Code MCP config (stdio transport):
  python3 mcp_evidence_server.py

Exposes tools: slack_read_channel, slack_search, sentry_list_issues,
sentry_get_issue, pagerduty_list_incidents, prometheus_query, prometheus_list_metrics,
logs_search, logs_get_service_logs, featureflags_get_flag, featureflags_list_flags,
git_log, git_blame
"""

import json
from pathlib import Path

import yaml
from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

EVIDENCE_FILE = Path(__file__).parent / "CASCADE-009-evidence-map.yaml"

# Load evidence data at import time
with open(EVIDENCE_FILE) as f:
    EVIDENCE = yaml.safe_load(f)

app = Server("cascade-009-evidence")


@app.list_tools()
async def list_tools():
    return [
        # Slack
        Tool(
            name="slack_list_channels",
            description="List available Slack channels",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="slack_read_channel",
            description="Read messages from a Slack channel. Use this to see team communication during the incident.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name (e.g. '#incidents', '#address-validation', '#platform-general')"},
                    "limit": {"type": "integer", "description": "Max messages to return", "default": 50},
                },
                "required": ["channel"],
            },
        ),
        Tool(
            name="slack_search",
            description="Search Slack messages across all channels for a keyword or phrase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        ),
        # Sentry
        Tool(
            name="sentry_list_projects",
            description="List all Sentry projects and their issue counts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sentry_list_issues",
            description="List Sentry issues, optionally filtered by project. Shows error tracking data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Filter by project name (e.g. 'checkout-service', 'shipping-service')"},
                },
            },
        ),
        Tool(
            name="sentry_get_issue",
            description="Get detailed Sentry issue including stacktrace and breadcrumbs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "description": "Issue ID (e.g. 'CHKOUT-4827')"},
                },
                "required": ["issue_id"],
            },
        ),
        # PagerDuty
        Tool(
            name="pagerduty_list_incidents",
            description="List PagerDuty incidents and their timelines.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="pagerduty_get_timeline",
            description="Get the timeline of a specific PagerDuty incident.",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string", "description": "Incident ID (e.g. 'PD-89247')"},
                },
                "required": ["incident_id"],
            },
        ),
        # Prometheus / Metrics
        Tool(
            name="prometheus_query",
            description="Query a Prometheus metric. Returns current value and historical context. Use this to check service health, resource usage, error rates, connection pools, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Metric name or PromQL query (e.g. 'checkout_success_rate', 'http_client_pool_active_connections', 'go_goroutines')"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="prometheus_list_metrics",
            description="List all available Prometheus metrics and their descriptions.",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Application Logs
        Tool(
            name="logs_list_services",
            description="List services that have application logs available.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="logs_get_service_logs",
            description="Get application logs for a specific service, with optional filtering by level, time range, or search term.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'checkout-service')"},
                    "level": {"type": "string", "description": "Filter by log level: ERROR, WARN, INFO, DEBUG"},
                    "since": {"type": "string", "description": "Only show logs after this timestamp (ISO format)"},
                    "grep": {"type": "string", "description": "Search for keyword in log messages"},
                    "limit": {"type": "integer", "description": "Max entries to return", "default": 50},
                },
                "required": ["service"],
            },
        ),
        Tool(
            name="logs_search",
            description="Search application logs across ALL services for a keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (searches in message and function fields)"},
                },
                "required": ["query"],
            },
        ),
        # Feature Flags
        Tool(
            name="featureflags_list",
            description="List all feature flags and their current values.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="featureflags_get",
            description="Get the current value and metadata of a specific feature flag.",
            inputSchema={
                "type": "object",
                "properties": {
                    "flag": {"type": "string", "description": "Flag name (e.g. 'addressValidationProvider', 'paymentUnreachable')"},
                },
                "required": ["flag"],
            },
        ),
        # Git
        Tool(
            name="git_recent_commits",
            description="Show recent git commits, optionally filtered by file path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Filter commits that touched this file path"},
                    "since": {"type": "string", "description": "Only show commits after this date (YYYY-MM-DD)"},
                },
            },
        ),
        Tool(
            name="git_blame",
            description="Show which commits last touched a specific file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to blame"},
                },
                "required": ["file"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _text(data) -> list[TextContent]:
    """Format response as JSON text content."""
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    slack = EVIDENCE.get("slack", {})
    sentry = EVIDENCE.get("sentry", {})
    pagerduty = EVIDENCE.get("pagerduty", {})
    metrics = EVIDENCE.get("metrics", {})
    logs = EVIDENCE.get("logs", {})
    flags = EVIDENCE.get("feature_flags", [])
    git = EVIDENCE.get("git", {})

    # --- Slack ---
    if name == "slack_list_channels":
        channels = slack.get("channels", [])
        return _text({"channels": [
            {"name": ch["name"], "message_count": len(ch.get("messages", []))}
            for ch in channels
        ]})

    if name == "slack_read_channel":
        channel_name = arguments.get("channel", "").lstrip("#")
        limit = arguments.get("limit", 50)
        for ch in slack.get("channels", []):
            if ch["name"].lstrip("#") == channel_name:
                msgs = ch.get("messages", [])[:limit]
                return _text({"channel": channel_name, "messages": msgs, "total": len(ch.get("messages", []))})
        return _text({"error": f"Channel not found: {channel_name}", "available": [ch["name"] for ch in slack.get("channels", [])]})

    if name == "slack_search":
        query = arguments.get("query", "").lower()
        results = []
        for ch in slack.get("channels", []):
            for msg in ch.get("messages", []):
                if query in msg.get("text", "").lower():
                    results.append({"channel": ch["name"], "user": msg.get("user"), "text": msg["text"], "timestamp": msg.get("timestamp")})
        return _text({"query": query, "results": results, "total": len(results)})

    # --- Sentry ---
    if name == "sentry_list_projects":
        projects = sentry.get("projects", [])
        return _text({"projects": [
            {"name": p["name"], "issue_count": len(p.get("issues", []))}
            for p in projects
        ]})

    if name == "sentry_list_issues":
        project_filter = arguments.get("project")
        all_issues = []
        for p in sentry.get("projects", []):
            if project_filter and p["name"] != project_filter:
                continue
            for issue in p.get("issues", []):
                entry = dict(issue)
                entry["project"] = p["name"]
                all_issues.append(entry)
        if not all_issues and project_filter:
            return _text({"issues": [], "total": 0, "project": project_filter, "note": f"No issues found for project '{project_filter}'"})
        return _text({"issues": all_issues, "total": len(all_issues)})

    if name == "sentry_get_issue":
        issue_id = arguments.get("issue_id", "")
        for p in sentry.get("projects", []):
            for issue in p.get("issues", []):
                if issue.get("id") == issue_id:
                    result = dict(issue)
                    result["project"] = p["name"]
                    return _text(result)
        return _text({"error": f"Issue not found: {issue_id}"})

    # --- PagerDuty ---
    if name == "pagerduty_list_incidents":
        incidents = pagerduty.get("incidents", [])
        return _text({"incidents": incidents, "total": len(incidents)})

    if name == "pagerduty_get_timeline":
        inc_id = arguments.get("incident_id", "")
        for inc in pagerduty.get("incidents", []):
            if inc.get("id") == inc_id:
                return _text({"incident_id": inc_id, "timeline": inc.get("timeline", [])})
        return _text({"error": f"Incident not found: {inc_id}"})

    # --- Prometheus ---
    if name == "prometheus_query":
        query_str = arguments.get("query", "").lower()
        queries = metrics.get("queries", [])
        # Exact match
        for q in queries:
            if q["query"].lower() == query_str:
                return _text({"query": q["query"], "result": q["result"]})
        # Fuzzy match
        matches = []
        for q in queries:
            if any(term in q["query"].lower() for term in query_str.split("_")):
                matches.append({"query": q["query"], "result": q["result"]})
        if matches:
            return _text({"query": query_str, "matches": matches})
        return _text({"query": query_str, "matches": [], "available_metrics": [q["query"] for q in queries]})

    if name == "prometheus_list_metrics":
        queries = metrics.get("queries", [])
        return _text({"metrics": [
            {"name": q["query"], "description": q["result"].get("note", "")}
            for q in queries
        ]})

    # --- Logs ---
    if name == "logs_list_services":
        services = logs.get("services", [])
        return _text({"services": [
            {"name": s["name"], "log_file": s.get("log_file", ""), "entry_count": len(s.get("entries", []))}
            for s in services
        ]})

    if name == "logs_get_service_logs":
        svc_name = arguments.get("service", "")
        level_filter = arguments.get("level", "").upper()
        since = arguments.get("since", "")
        grep = arguments.get("grep", "").lower()
        limit = arguments.get("limit", 50)
        for svc in logs.get("services", []):
            if svc["name"] == svc_name:
                entries = svc.get("entries", [])
                if level_filter:
                    entries = [e for e in entries if e.get("level", "").upper() == level_filter]
                if since:
                    entries = [e for e in entries if e.get("timestamp", "") >= since]
                if grep:
                    entries = [e for e in entries if grep in e.get("message", "").lower() or grep in e.get("function", "").lower()]
                return _text({"service": svc_name, "entries": entries[:limit], "total": len(entries)})
        return _text({"error": f"Service not found: {svc_name}"})

    if name == "logs_search":
        query = arguments.get("query", "").lower()
        results = []
        for svc in logs.get("services", []):
            for entry in svc.get("entries", []):
                if query in entry.get("message", "").lower():
                    result = dict(entry)
                    result["service"] = svc["name"]
                    results.append(result)
        return _text({"results": results, "total": len(results)})

    # --- Feature Flags ---
    if name == "featureflags_list":
        return _text({"flags": flags})

    if name == "featureflags_get":
        flag_name = arguments.get("flag", "")
        for f in flags:
            if f.get("flag") == flag_name:
                return _text(f)
        return _text({"error": f"Flag not found: {flag_name}", "available": [f["flag"] for f in flags]})

    # --- Git ---
    if name == "git_recent_commits":
        commits = git.get("recent_commits", [])
        file_filter = arguments.get("file", "")
        since = arguments.get("since", "")
        if file_filter:
            commits = [c for c in commits if any(file_filter in f for f in c.get("files", []))]
        if since:
            commits = [c for c in commits if c.get("date", "") >= since]
        return _text({"commits": commits, "total": len(commits)})

    if name == "git_blame":
        file_path = arguments.get("file", "")
        commits = git.get("recent_commits", [])
        relevant = [c for c in commits if any(file_path in f for f in c.get("files", []))]
        return _text({"file": file_path, "commits": relevant})

    return _text({"error": f"Unknown tool: {name}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
