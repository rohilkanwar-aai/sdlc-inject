"""Extract tool profiles from Exa enrichment results.

Analyzes incident reports and postmortems found by Exa to identify which
observability, monitoring, incident management, and communication tools
were involved. Uses Claude (via Agent SDK) for structured extraction.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any

from claude_agent_sdk import query, AssistantMessage, ResultMessage

from ..sdk_utils import create_agent_options, extract_json_from_text, collect_text_from_messages
from .service_config import ToolProfile


# Services we already have hardcoded mock servers for -- skip these
BUILTIN_SERVICES = frozenset({
    "sentry", "slack", "github", "pagerduty", "prometheus",
    # Common aliases
    "github_actions", "slack_bot",
})


EXTRACTION_PROMPT = """Analyze the following incident reports and postmortem excerpts. \
Identify all observability, monitoring, incident management, alerting, communication, \
and CI/CD tools mentioned.

For each tool found, extract:
- name: snake_case identifier (e.g. "datadog", "incident_io", "ms_teams", "grafana")
- display_name: Human-readable name (e.g. "Datadog", "Incident.io", "Microsoft Teams")
- category: One of: monitoring, incident_management, communication, logging, apm, \
alerting, ci_cd, other
- description: 1-2 sentences describing how this tool was used in the incidents
- mention_count: How many distinct incidents mentioned this tool

Return a JSON object:
{{
  "tools": [
    {{
      "name": "datadog",
      "display_name": "Datadog",
      "category": "monitoring",
      "description": "Used for infrastructure monitoring and APM tracing to identify ...",
      "mention_count": 3
    }}
  ]
}}

IMPORTANT: Do NOT include these tools (we already have mock servers for them):
- Sentry, Slack, GitHub, PagerDuty, Prometheus

Only include tools that are NOT in that list.

--- INCIDENT DATA ---

{incident_text}
"""


class ToolExtractor:
    """Extracts ToolProfile objects from Exa enrichment results.

    Takes the incident reports and similar vulnerability data collected
    during Exa enrichment and uses Claude to identify which external
    tools/services were mentioned.
    """

    def __init__(self, model: str = "claude-opus-4-20250514"):
        self.model = model

    async def extract_tools_async(
        self,
        vulnerability_points: list[Any],
        pattern_ids: list[str] | None = None,
        max_tools: int = 10,
    ) -> list[ToolProfile]:
        """Extract tool profiles from vulnerability enrichment data.

        Args:
            vulnerability_points: VulnerabilityPoint objects with enrichment data
            pattern_ids: Optional pattern IDs for context
            max_tools: Maximum number of tool profiles to return

        Returns:
            List of ToolProfile objects, sorted by relevance
        """
        # Collect all incident text from enrichment data
        incident_texts = []
        source_urls_by_tool: dict[str, list[str]] = {}

        for vuln in vulnerability_points:
            for incident in getattr(vuln, "related_incidents", []):
                text = incident.get("text", "")
                title = incident.get("title", "")
                url = incident.get("url", "")
                if text or title:
                    incident_texts.append(
                        f"### {title}\nSource: {url}\n{text[:2000]}"
                    )

            for similar in getattr(vuln, "similar_vulnerabilities", []):
                text = similar.get("text", "")
                title = similar.get("title", "")
                url = similar.get("url", "")
                if text or title:
                    incident_texts.append(
                        f"### {title}\nSource: {url}\n{text[:1500]}"
                    )

        if not incident_texts:
            return []

        # Truncate to avoid exceeding context limits
        combined_text = "\n\n".join(incident_texts[:30])
        if len(combined_text) > 50000:
            combined_text = combined_text[:50000] + "\n... (truncated)"

        # Call Claude to extract tools
        prompt = EXTRACTION_PROMPT.format(incident_text=combined_text)

        options = create_agent_options(
            model=self.model,
            max_turns=1,
        )

        all_messages: list = []
        async for message in query(prompt=prompt, options=options):
            all_messages.append(message)

        full_text = collect_text_from_messages(all_messages)
        result_data = extract_json_from_text(full_text)

        if result_data is None:
            return []

        # Parse into ToolProfile objects
        raw_tools = result_data.get("tools", [])
        profiles = []

        for raw in raw_tools:
            name = raw.get("name", "").lower().strip()
            if not name or name in BUILTIN_SERVICES:
                continue

            mention_count = raw.get("mention_count", 1)
            total_incidents = max(len(incident_texts), 1)
            relevance = min(1.0, mention_count / total_incidents * 2)

            # Collect source URLs from incidents that mentioned this tool
            tool_urls = []
            tool_name_lower = name.replace("_", "").lower()
            display_lower = raw.get("display_name", "").lower()
            for incident in incident_texts:
                if tool_name_lower in incident.lower() or display_lower in incident.lower():
                    for line in incident.split("\n"):
                        if line.startswith("Source: ") and line[8:].startswith("http"):
                            tool_urls.append(line[8:])

            profiles.append(ToolProfile(
                name=name,
                display_name=raw.get("display_name", name.replace("_", " ").title()),
                category=raw.get("category", "other"),
                description=raw.get("description", ""),
                relevance_score=relevance,
                source_urls=tool_urls[:5],
                mentioned_in_patterns=pattern_ids or [],
            ))

        # Sort by relevance and limit
        profiles.sort(key=lambda p: p.relevance_score, reverse=True)
        return profiles[:max_tools]

    def extract_tools(
        self,
        vulnerability_points: list[Any],
        pattern_ids: list[str] | None = None,
        max_tools: int = 10,
    ) -> list[ToolProfile]:
        """Synchronous wrapper for extract_tools_async."""
        return asyncio.run(
            self.extract_tools_async(vulnerability_points, pattern_ids, max_tools)
        )
