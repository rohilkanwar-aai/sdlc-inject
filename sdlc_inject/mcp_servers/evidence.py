"""Evidence-seeded MCP servers loaded from a cascade evidence map YAML.

Instead of generating mock data from pattern templates, these servers load
hand-crafted evidence directly from a YAML file. This gives precise control
over what the agent discovers at each step of the investigation.

Usage:
    from mcp_servers.evidence import load_evidence_servers

    servers = load_evidence_servers("CASCADE-009-evidence-map.yaml")
    registry.register_dynamic_server("slack", servers["slack"])
    registry.register_dynamic_server("sentry", servers["sentry"])
    # etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .noise import NoiseConfig


class EvidenceSlackServer(BaseMCPServer):
    """Slack MCP server seeded from evidence map."""

    service_name = "slack"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /channels",
            "GET /channels/{name}/messages",
            "GET /search",
        ]

    def _initialize_data(self) -> None:
        self.channels = self._evidence.get("channels", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        if endpoint == "/channels":
            return Response(200, {
                "channels": [
                    {"name": ch["name"], "message_count": len(ch.get("messages", []))}
                    for ch in self.channels
                ],
            })

        # GET /channels/{name}/messages
        if endpoint.startswith("/channels/") and endpoint.endswith("/messages"):
            channel_name = endpoint.split("/")[2]
            # Strip # prefix if present
            channel_name = channel_name.lstrip("#")

            for ch in self.channels:
                if ch["name"].lstrip("#") == channel_name:
                    messages = ch.get("messages", [])
                    # Apply limit/offset
                    limit = int(params.get("limit", 50))
                    offset = int(params.get("offset", 0))
                    return Response(200, {
                        "channel": channel_name,
                        "messages": messages[offset:offset + limit],
                        "total": len(messages),
                    })
            return Response(404, {"error": f"Channel not found: {channel_name}"})

        # GET /search?query=...
        if endpoint == "/search":
            query = params.get("query", "").lower()
            results = []
            for ch in self.channels:
                for msg in ch.get("messages", []):
                    if query in msg.get("text", "").lower():
                        results.append({
                            "channel": ch["name"],
                            "user": msg.get("user", "unknown"),
                            "text": msg["text"],
                            "timestamp": msg.get("timestamp", ""),
                        })
            return Response(200, {"results": results, "total": len(results)})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidenceSentryServer(BaseMCPServer):
    """Sentry MCP server seeded from evidence map."""

    service_name = "sentry"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /projects",
            "GET /issues",
            "GET /issues/{issue_id}",
        ]

    def _initialize_data(self) -> None:
        self.projects = self._evidence.get("projects", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        # GET /projects
        if endpoint == "/projects":
            return Response(200, {
                "projects": [
                    {
                        "name": p["name"],
                        "issue_count": len(p.get("issues", [])),
                    }
                    for p in self.projects
                ],
            })

        # GET /issues?project=...
        if endpoint == "/issues":
            project_name = params.get("project", None)
            all_issues = []
            for p in self.projects:
                if project_name and p["name"] != project_name:
                    continue
                for issue in p.get("issues", []):
                    issue_copy = dict(issue)
                    issue_copy["project"] = p["name"]
                    all_issues.append(issue_copy)

            if not all_issues and project_name:
                # Significant silence -- return empty with note
                return Response(200, {
                    "issues": [],
                    "total": 0,
                    "project": project_name,
                    "note": f"No issues found for project '{project_name}'",
                })

            return Response(200, {"issues": all_issues, "total": len(all_issues)})

        # GET /issues/{issue_id}
        if endpoint.startswith("/issues/") and not endpoint.endswith("/issues"):
            issue_id = endpoint.split("/")[-1]
            for p in self.projects:
                for issue in p.get("issues", []):
                    if issue.get("id") == issue_id:
                        result = dict(issue)
                        result["project"] = p["name"]
                        return Response(200, result)
            return Response(404, {"error": f"Issue not found: {issue_id}"})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidencePagerDutyServer(BaseMCPServer):
    """PagerDuty MCP server seeded from evidence map."""

    service_name = "pagerduty"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /incidents",
            "GET /incidents/{id}",
            "GET /incidents/{id}/timeline",
        ]

    def _initialize_data(self) -> None:
        self.incidents = self._evidence.get("incidents", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        if endpoint == "/incidents":
            return Response(200, {
                "incidents": self.incidents,
                "total": len(self.incidents),
            })

        if endpoint.startswith("/incidents/"):
            parts = endpoint.strip("/").split("/")
            inc_id = parts[1] if len(parts) >= 2 else ""
            for inc in self.incidents:
                if inc.get("id") == inc_id:
                    if len(parts) == 3 and parts[2] == "timeline":
                        return Response(200, {
                            "incident_id": inc_id,
                            "timeline": inc.get("timeline", []),
                        })
                    return Response(200, inc)
            return Response(404, {"error": f"Incident not found: {inc_id}"})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidenceMetricsServer(BaseMCPServer):
    """Prometheus/metrics MCP server seeded from evidence map."""

    service_name = "prometheus"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /query",
            "GET /metrics",
            "GET /alerts",
        ]

    def _initialize_data(self) -> None:
        self.queries = self._evidence.get("queries", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        # GET /query?q=... -- fuzzy match against seeded queries
        if endpoint == "/query":
            query_str = params.get("q", params.get("query", "")).lower()

            # Exact match first
            for q in self.queries:
                if q["query"].lower() == query_str:
                    return Response(200, {
                        "query": q["query"],
                        "result": q["result"],
                    })

            # Fuzzy match -- find queries containing search terms
            matches = []
            for q in self.queries:
                if any(term in q["query"].lower() for term in query_str.split()):
                    matches.append({
                        "query": q["query"],
                        "result": q["result"],
                    })

            if matches:
                return Response(200, {
                    "query": query_str,
                    "matches": matches,
                    "total": len(matches),
                })

            return Response(200, {
                "query": query_str,
                "matches": [],
                "total": 0,
                "available_metrics": [q["query"] for q in self.queries],
            })

        # GET /metrics -- list all available metrics
        if endpoint == "/metrics":
            return Response(200, {
                "metrics": [
                    {"name": q["query"], "note": q["result"].get("note", "")}
                    for q in self.queries
                ],
            })

        # GET /alerts
        if endpoint == "/alerts":
            firing = [
                q for q in self.queries
                if "alert" in q["query"].lower() or "rate" in q["query"].lower()
            ]
            return Response(200, {"firing_alerts": firing, "total": len(firing)})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidenceLogsServer(BaseMCPServer):
    """Application logs MCP server seeded from evidence map."""

    service_name = "logs"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /services",
            "GET /services/{name}/logs",
            "GET /search",
        ]

    def _initialize_data(self) -> None:
        self.services = self._evidence.get("services", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        # GET /services
        if endpoint == "/services":
            return Response(200, {
                "services": [
                    {"name": s["name"], "log_file": s.get("log_file", ""), "entry_count": len(s.get("entries", []))}
                    for s in self.services
                ],
            })

        # GET /services/{name}/logs
        if endpoint.startswith("/services/") and endpoint.endswith("/logs"):
            svc_name = endpoint.split("/")[2]
            level_filter = params.get("level", "").upper()
            since = params.get("since", "")
            grep = params.get("grep", params.get("search", "")).lower()
            limit = int(params.get("limit", 100))

            for svc in self.services:
                if svc["name"] == svc_name:
                    entries = svc.get("entries", [])
                    # Filter by level
                    if level_filter:
                        entries = [e for e in entries if e.get("level", "").upper() == level_filter]
                    # Filter by timestamp
                    if since:
                        entries = [e for e in entries if e.get("timestamp", "") >= since]
                    # Filter by grep pattern
                    if grep:
                        entries = [
                            e for e in entries
                            if grep in e.get("message", "").lower()
                            or grep in e.get("function", "").lower()
                        ]
                    return Response(200, {
                        "service": svc_name,
                        "entries": entries[:limit],
                        "total": len(entries),
                        "filtered": bool(level_filter or since or grep),
                    })

            return Response(404, {"error": f"Service not found: {svc_name}"})

        # GET /search?query=...
        if endpoint == "/search":
            query = params.get("query", params.get("q", "")).lower()
            results = []
            for svc in self.services:
                for entry in svc.get("entries", []):
                    if query in entry.get("message", "").lower():
                        result = dict(entry)
                        result["service"] = svc["name"]
                        results.append(result)
            return Response(200, {"results": results, "total": len(results)})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidenceFeatureFlagServer(BaseMCPServer):
    """Feature flag MCP server seeded from evidence map."""

    service_name = "featureflags"

    def __init__(
        self,
        evidence: list[dict[str, Any]],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /flags",
            "GET /flags/{name}",
        ]

    def _initialize_data(self) -> None:
        self.flags = {f["flag"]: f for f in self._evidence}

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        if endpoint == "/flags":
            return Response(200, {"flags": list(self.flags.values())})

        if endpoint.startswith("/flags/"):
            flag_name = endpoint.split("/")[-1]
            if flag_name in self.flags:
                return Response(200, self.flags[flag_name])
            return Response(404, {"error": f"Flag not found: {flag_name}"})

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


class EvidenceGitServer(BaseMCPServer):
    """Git history MCP server seeded from evidence map."""

    service_name = "git"

    def __init__(
        self,
        evidence: dict[str, Any],
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self._evidence = evidence
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /log",
            "GET /log/{hash}",
            "GET /blame/{file_path}",
        ]

    def _initialize_data(self) -> None:
        self.commits = self._evidence.get("recent_commits", [])

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        if endpoint == "/log":
            since = params.get("since", "")
            file_filter = params.get("file", "")
            commits = self.commits
            if since:
                commits = [c for c in commits if c.get("date", "") >= since]
            if file_filter:
                commits = [
                    c for c in commits
                    if any(file_filter in f for f in c.get("files", []))
                ]
            return Response(200, {"commits": commits, "total": len(commits)})

        if endpoint.startswith("/log/"):
            commit_hash = endpoint.split("/")[-1]
            for c in self.commits:
                if c.get("hash", "").startswith(commit_hash):
                    return Response(200, c)
            return Response(404, {"error": f"Commit not found: {commit_hash}"})

        if endpoint.startswith("/blame/"):
            file_path = "/".join(endpoint.split("/")[2:])
            # Find commits that touched this file
            relevant = [c for c in self.commits if any(file_path in f for f in c.get("files", []))]
            return Response(200, {
                "file": file_path,
                "commits": relevant,
            })

        return Response(404, {"error": f"Unknown endpoint: {endpoint}"})


# ---------------------------------------------------------------------------
# Loader: evidence map YAML → dict of MCP servers
# ---------------------------------------------------------------------------

def load_evidence_servers(
    evidence_path: str | Path,
    pattern: Pattern | None = None,
    seed: int | None = None,
    rate_limit_config: RateLimitConfig | None = None,
) -> dict[str, BaseMCPServer]:
    """Load an evidence map YAML and return per-service MCP servers.

    Args:
        evidence_path: Path to the evidence map YAML file
        pattern: Optional Pattern object (some servers use it for context)
        seed: Random seed for deterministic behavior
        rate_limit_config: Rate limit config for all servers

    Returns:
        Dict mapping service name to its MCP server instance.
        Ready to register with MCPServerRegistry.register_dynamic_server().
    """
    path = Path(evidence_path)
    with open(path) as f:
        evidence = yaml.safe_load(f)

    servers: dict[str, BaseMCPServer] = {}

    # Build a minimal Pattern if none provided
    if pattern is None:
        from ..models import Pattern, SdlcPhases, Difficulty
        pattern = Pattern(
            id=evidence.get("id", "UNKNOWN"),
            version="2.0",
            name=evidence.get("name", ""),
            category="Cascading Failures",
            subcategory="Evidence-Seeded",
            sdlc_phases=SdlcPhases(primary="Debugging"),
            description=evidence.get("task_prompt", ""),
            difficulty=Difficulty(
                estimated_human_time_hours=8,
                frontier_model_pass_rate_percent=7,
            ),
        )

    if "slack" in evidence:
        servers["slack"] = EvidenceSlackServer(
            evidence["slack"], pattern, seed, rate_limit_config,
        )

    if "sentry" in evidence:
        servers["sentry"] = EvidenceSentryServer(
            evidence["sentry"], pattern, seed, rate_limit_config,
        )

    if "pagerduty" in evidence:
        servers["pagerduty"] = EvidencePagerDutyServer(
            evidence["pagerduty"], pattern, seed, rate_limit_config,
        )

    if "metrics" in evidence:
        servers["prometheus"] = EvidenceMetricsServer(
            evidence["metrics"], pattern, seed, rate_limit_config,
        )

    if "logs" in evidence:
        servers["logs"] = EvidenceLogsServer(
            evidence["logs"], pattern, seed, rate_limit_config,
        )

    if "feature_flags" in evidence:
        servers["featureflags"] = EvidenceFeatureFlagServer(
            evidence["feature_flags"], pattern, seed, rate_limit_config,
        )

    if "git" in evidence:
        servers["git"] = EvidenceGitServer(
            evidence["git"], pattern, seed, rate_limit_config,
        )

    return servers


def load_evidence_registry(
    evidence_path: str | Path,
    pattern: Pattern | None = None,
    seed: int | None = None,
    rate_limit_config: RateLimitConfig | None = None,
) -> "MCPServerRegistry":
    """Load evidence map and return a fully-configured MCPServerRegistry.

    Convenience function that creates a registry with NO default servers,
    then populates it with evidence-seeded servers.
    """
    from .registry import MCPServerRegistry

    servers = load_evidence_servers(evidence_path, pattern, seed, rate_limit_config)

    # Create registry with no default services
    if pattern is None:
        from ..models import Pattern, SdlcPhases, Difficulty
        with open(evidence_path) as f:
            evidence = yaml.safe_load(f)
        pattern = Pattern(
            id=evidence.get("id", "UNKNOWN"),
            version="2.0",
            name=evidence.get("name", ""),
            category="Cascading Failures",
            subcategory="Evidence-Seeded",
            sdlc_phases=SdlcPhases(primary="Debugging"),
            description=evidence.get("task_prompt", ""),
            difficulty=Difficulty(
                estimated_human_time_hours=8,
                frontier_model_pass_rate_percent=7,
            ),
        )

    registry = MCPServerRegistry(
        pattern=pattern,
        seed=seed,
        rate_limit_config=rate_limit_config,
        enabled_services=[],  # Start empty -- we add evidence servers only
    )

    for name, server in servers.items():
        registry.register_dynamic_server(name, server)

    return registry


# ---------------------------------------------------------------------------
# Noise-mixing servers: evidence + generated noise at scale
# ---------------------------------------------------------------------------

class NoiseMixingSlackServer(EvidenceSlackServer):
    """Slack server that mixes hand-crafted evidence with generated noise.

    Evidence messages are inserted at configured positions within a sea of
    realistic generated Slack messages (standups, PR reviews, bot alerts, etc.).
    """

    def __init__(
        self,
        evidence: dict[str, Any],
        noise_config: "NoiseConfig",
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        from .noise import SlackNoiseGenerator

        from .noise import NoiseConfig as NC

        self._noise_config = noise_config
        # Build generators per channel
        self._channel_generators: dict[str, SlackNoiseGenerator] = {}

        for ch in evidence.get("channels", []):
            ch_name = ch["name"].lstrip("#")
            signals = ch.get("messages", [])
            positions = noise_config.signal_positions.get(ch_name, list(range(len(signals))))
            ch_config = NC(
                entries_per_source=noise_config.entries_per_source,
                signal_positions={"slack": positions},
                seed=(noise_config.seed or 42) + hash(ch_name) % 10000,
                time_range_hours=noise_config.time_range_hours,
                start_time=noise_config.start_time,
            )
            self._channel_generators[ch_name] = SlackNoiseGenerator(ch_config, signals)

        super().__init__(evidence, pattern, seed, rate_limit_config)

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        # Override channel messages to use noise generators
        if endpoint.startswith("/channels/") and endpoint.endswith("/messages"):
            channel_name = endpoint.split("/")[2].lstrip("#")
            gen = self._channel_generators.get(channel_name)
            if gen:
                cursor = int(params.get("cursor", params.get("offset", 0)))
                limit = int(params.get("limit", 50))
                page = gen.get_page(cursor=cursor, limit=limit)
                return Response(200, {
                    "channel": channel_name,
                    "messages": page.entries,
                    "total": page.total,
                    "next_cursor": page.next_cursor,
                    "has_more": page.has_more,
                })
            return Response(404, {"error": f"Channel not found: {channel_name}"})

        # Override search to use noise generators
        if endpoint == "/search":
            query = params.get("query", "").lower()
            limit = int(params.get("limit", 50))
            results = []
            for ch_name, gen in self._channel_generators.items():
                for entry in gen.search(query, limit=limit):
                    entry_copy = dict(entry)
                    entry_copy["channel"] = ch_name
                    results.append(entry_copy)
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
            return Response(200, {"results": results, "total": len(results)})

        # Channels list uses parent
        return super().handle_request(method, endpoint, params)


class NoiseMixingLogsServer(EvidenceLogsServer):
    """Logs server that mixes evidence with generated noise."""

    def __init__(
        self,
        evidence: dict[str, Any],
        noise_config: "NoiseConfig",
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        from .noise import LogNoiseGenerator, NoiseConfig as NC

        self._noise_config = noise_config
        self._service_generators: dict[str, LogNoiseGenerator] = {}

        lang_map = {
            "checkout-service": "go", "shipping-service": "rust",
            "recommendation-service": "python", "product-reviews": "python",
            "ad-service": "java", "cart-service": "go",
            "payment-service": "go", "email-service": "python",
            "frontend": "go", "accounting-service": "go",
            "otel-collector": "go",
        }

        for svc in evidence.get("services", []):
            svc_name = svc["name"]
            signals = svc.get("entries", [])
            positions = noise_config.signal_positions.get(svc_name, list(range(len(signals))))
            svc_config = NC(
                entries_per_source=noise_config.entries_per_source,
                signal_positions={"log": positions},
                seed=(noise_config.seed or 42) + hash(svc_name) % 10000,
                time_range_hours=noise_config.time_range_hours,
                start_time=noise_config.start_time,
            )
            lang = lang_map.get(svc_name, "go")
            self._service_generators[svc_name] = LogNoiseGenerator(
                svc_config, signals, service_name=svc_name, language=lang,
            )

        super().__init__(evidence, pattern, seed, rate_limit_config)

    def handle_request(self, method: str, endpoint: str, params: dict[str, Any]) -> Response:
        if endpoint.startswith("/services/") and endpoint.endswith("/logs"):
            svc_name = endpoint.split("/")[2]
            gen = self._service_generators.get(svc_name)
            if gen:
                cursor = int(params.get("cursor", params.get("offset", 0)))
                limit = int(params.get("limit", 50))
                filters = {}
                if params.get("level"):
                    filters["level"] = params["level"].upper()
                if params.get("grep") or params.get("search"):
                    filters["message"] = params.get("grep", params.get("search", ""))
                page = gen.get_page(cursor=cursor, limit=limit, **filters)
                return Response(200, {
                    "service": svc_name,
                    "entries": page.entries,
                    "total": page.total,
                    "next_cursor": page.next_cursor,
                    "has_more": page.has_more,
                })
            return Response(404, {"error": f"Service not found: {svc_name}"})

        if endpoint == "/search":
            query = params.get("query", params.get("q", "")).lower()
            limit = int(params.get("limit", 50))
            results = []
            for svc_name, gen in self._service_generators.items():
                for entry in gen.search(query, limit=limit):
                    entry_copy = dict(entry)
                    entry_copy["service"] = svc_name
                    results.append(entry_copy)
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
            return Response(200, {"results": results, "total": len(results)})

        return super().handle_request(method, endpoint, params)


def load_evidence_servers_with_noise(
    evidence_path: str | Path,
    noise_config: dict | None = None,
    pattern: Pattern | None = None,
    seed: int | None = None,
    rate_limit_config: RateLimitConfig | None = None,
) -> dict[str, BaseMCPServer]:
    """Load evidence map with noise generation for 1000x scale.

    If noise_config is present (in YAML or passed explicitly), uses
    NoiseMixing*Server variants. Otherwise falls back to standard
    Evidence*Server (backward compatible).

    Args:
        evidence_path: Path to evidence map YAML
        noise_config: Override noise config (or read from YAML's noise_config key)
        pattern: Optional Pattern object
        seed: Random seed
        rate_limit_config: Rate limiting config

    Returns:
        Dict of MCP servers with noise-mixed data.
    """
    from .noise import NoiseConfig

    path = Path(evidence_path)
    with open(path) as f:
        evidence = yaml.safe_load(f)

    # Read noise config from YAML or use passed config
    nc_data = noise_config or evidence.get("noise_config")
    if nc_data is None:
        # No noise config -- fall back to standard evidence servers
        return load_evidence_servers(evidence_path, pattern, seed, rate_limit_config)

    # Parse noise config
    if isinstance(nc_data, dict):
        nc = NoiseConfig(
            entries_per_source=nc_data.get("entries_per_source", 5000),
            signal_positions=nc_data.get("signal_positions", {}),
            seed=nc_data.get("seed", seed or 42),
            time_range_hours=nc_data.get("time_range_hours", 168),
        )
    else:
        nc = nc_data

    # Build minimal Pattern if needed
    if pattern is None:
        from ..models import Pattern as PatternModel, SdlcPhases, Difficulty
        pattern = PatternModel(
            id=evidence.get("id", "UNKNOWN"),
            version="2.0",
            name=evidence.get("name", ""),
            category="Cascading Failures",
            subcategory="Evidence-Seeded",
            sdlc_phases=SdlcPhases(primary="Debugging"),
            description=evidence.get("task_prompt", ""),
            difficulty=Difficulty(
                estimated_human_time_hours=16,
                frontier_model_pass_rate_percent=5,
            ),
        )

    servers: dict[str, BaseMCPServer] = {}

    # Use noise-mixing variants for Slack and Logs (highest volume)
    if "slack" in evidence:
        servers["slack"] = NoiseMixingSlackServer(
            evidence["slack"], nc, pattern, seed, rate_limit_config,
        )

    if "logs" in evidence:
        servers["logs"] = NoiseMixingLogsServer(
            evidence["logs"], nc, pattern, seed, rate_limit_config,
        )

    # Use standard evidence servers for lower-volume sources
    if "sentry" in evidence:
        servers["sentry"] = EvidenceSentryServer(
            evidence["sentry"], pattern, seed, rate_limit_config,
        )

    if "pagerduty" in evidence:
        servers["pagerduty"] = EvidencePagerDutyServer(
            evidence["pagerduty"], pattern, seed, rate_limit_config,
        )

    if "metrics" in evidence:
        servers["prometheus"] = EvidenceMetricsServer(
            evidence["metrics"], pattern, seed, rate_limit_config,
        )

    if "feature_flags" in evidence:
        servers["featureflags"] = EvidenceFeatureFlagServer(
            evidence["feature_flags"], pattern, seed, rate_limit_config,
        )

    if "git" in evidence:
        servers["git"] = EvidenceGitServer(
            evidence["git"], pattern, seed, rate_limit_config,
        )

    return servers


def load_evidence_servers_interactive(
    evidence_path: str | Path,
    noise_config: dict | None = None,
    pattern: Pattern | None = None,
    seed: int | None = None,
    rate_limit_config: RateLimitConfig | None = None,
) -> tuple[dict[str, BaseMCPServer], Any]:
    """Load evidence servers with reactive Slack + time-progressing simulation."""
    from .noise import NoiseConfig
    from .timeline import IncidentTimeline, TimeProgressingMetricsServer, TimeProgressingSlackServer

    path = Path(evidence_path)
    with open(path) as f:
        evidence = yaml.safe_load(f)

    nc_data = noise_config or evidence.get("noise_config", {})
    nc = NoiseConfig(
        entries_per_source=nc_data.get("entries_per_source", 5000),
        signal_positions=nc_data.get("signal_positions", {}),
        seed=nc_data.get("seed", seed or 42),
        time_range_hours=nc_data.get("time_range_hours", 168),
    )

    if pattern is None:
        from ..models import Pattern as PatternModel, SdlcPhases, Difficulty
        pattern = PatternModel(
            id=evidence.get("id", "UNKNOWN"), version="2.0",
            name=evidence.get("name", ""),
            category="Cascading Failures", subcategory="Interactive",
            sdlc_phases=SdlcPhases(primary="Debugging"),
            description=evidence.get("task_prompt", ""),
            difficulty=Difficulty(estimated_human_time_hours=16, frontier_model_pass_rate_percent=5),
        )

    timeline = IncidentTimeline(seed=seed or 42)
    qa_pairs = evidence.get("qa_pairs", [])
    servers: dict[str, BaseMCPServer] = {}

    if "slack" in evidence:
        servers["slack"] = TimeProgressingSlackServer(
            evidence["slack"], nc, qa_pairs, timeline,
            pattern=pattern, seed=seed, rate_limit_config=rate_limit_config,
        )
    if "logs" in evidence:
        servers["logs"] = NoiseMixingLogsServer(
            evidence["logs"], nc, pattern, seed, rate_limit_config,
        )
    if "metrics" in evidence:
        servers["prometheus"] = TimeProgressingMetricsServer(
            evidence["metrics"], timeline, pattern, seed, rate_limit_config,
        )
    if "sentry" in evidence:
        servers["sentry"] = EvidenceSentryServer(evidence["sentry"], pattern, seed, rate_limit_config)
    if "pagerduty" in evidence:
        servers["pagerduty"] = EvidencePagerDutyServer(evidence["pagerduty"], pattern, seed, rate_limit_config)
    if "feature_flags" in evidence:
        servers["featureflags"] = EvidenceFeatureFlagServer(evidence["feature_flags"], pattern, seed, rate_limit_config)
    if "git" in evidence:
        servers["git"] = EvidenceGitServer(evidence["git"], pattern, seed, rate_limit_config)

    return servers, timeline
