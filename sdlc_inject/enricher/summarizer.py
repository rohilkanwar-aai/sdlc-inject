"""LLM-based summarization of incident solutions."""

import os
from dataclasses import dataclass

import httpx


@dataclass
class IncidentSummary:
    """Summary of how engineers solved an incident."""

    url: str
    title: str
    solution_summary: str
    key_learnings: list[str]
    tags: list[str]


class IncidentSummarizer:
    """Uses Claude API to summarize how engineers solved incidents."""

    SYSTEM_PROMPT = """You are an expert at analyzing engineering incident reports and postmortems.
Your task is to extract the key information about how engineers identified and solved the problem.

Focus on:
1. Root cause identification process
2. The actual fix implemented
3. Preventive measures taken
4. Key debugging techniques used

Be concise but technically accurate. Use specific technical terms."""

    SUMMARY_PROMPT = """Analyze this incident and provide a summary of how engineers solved it.

Incident URL: {url}
Incident Title: {title}
Incident Description/Snippet: {snippet}
Related Pattern Type: {pattern_type}

Provide your response in the following format:

SOLUTION SUMMARY:
[2-4 sentences describing how engineers identified the root cause and fixed the issue]

KEY LEARNINGS:
- [Learning 1]
- [Learning 2]
- [Learning 3]

TAGS:
[comma-separated list of relevant technical tags like: race-condition, distributed-systems, database, networking, etc.]"""

    def __init__(self, api_key: str | None = None):
        """
        Initialize the summarizer.

        Args:
            api_key: Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = httpx.Client(timeout=60.0)
        self.base_url = "https://api.anthropic.com/v1/messages"

    def summarize_incident(
        self,
        url: str,
        title: str,
        snippet: str,
        pattern_type: str,
        fetch_content: bool = False,
    ) -> IncidentSummary | None:
        """
        Generate a summary of how engineers solved an incident.

        Args:
            url: URL of the incident report
            title: Title of the incident
            snippet: Short description or snippet
            pattern_type: Type of pattern (e.g., "race", "split-brain")
            fetch_content: Whether to fetch full content from URL

        Returns:
            IncidentSummary or None if summarization fails
        """
        if not self.api_key:
            # Return a default summary when no API key is available
            return self._generate_default_summary(url, title, snippet, pattern_type)

        # Build the prompt
        prompt = self.SUMMARY_PROMPT.format(
            url=url,
            title=title,
            snippet=snippet,
            pattern_type=pattern_type,
        )

        try:
            response = self._call_claude(prompt)
            return self._parse_response(url, title, response)
        except Exception as e:
            print(f"Warning: Failed to summarize incident: {e}")
            return self._generate_default_summary(url, title, snippet, pattern_type)

    def _call_claude(self, prompt: str) -> str:
        """Call Claude API to generate summary."""
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": "claude-opus-4-20250514",
            "max_tokens": 1024,
            "system": self.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = self.client.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["content"][0]["text"]

    def _parse_response(
        self, url: str, title: str, response: str
    ) -> IncidentSummary | None:
        """Parse the LLM response into structured data."""
        solution_summary = ""
        key_learnings: list[str] = []
        tags: list[str] = []

        # Parse solution summary
        if "SOLUTION SUMMARY:" in response:
            parts = response.split("SOLUTION SUMMARY:")
            if len(parts) > 1:
                summary_part = parts[1].split("KEY LEARNINGS:")[0].strip()
                solution_summary = summary_part

        # Parse key learnings
        if "KEY LEARNINGS:" in response:
            parts = response.split("KEY LEARNINGS:")
            if len(parts) > 1:
                learnings_part = parts[1].split("TAGS:")[0].strip()
                for line in learnings_part.split("\n"):
                    line = line.strip()
                    if line.startswith("-"):
                        learning = line[1:].strip()
                        if learning:
                            key_learnings.append(learning)

        # Parse tags
        if "TAGS:" in response:
            parts = response.split("TAGS:")
            if len(parts) > 1:
                tags_part = parts[1].strip().split("\n")[0]
                tags = [t.strip() for t in tags_part.split(",") if t.strip()]

        if not solution_summary:
            return None

        return IncidentSummary(
            url=url,
            title=title,
            solution_summary=solution_summary,
            key_learnings=key_learnings,
            tags=tags,
        )

    def _generate_default_summary(
        self, url: str, title: str, snippet: str, pattern_type: str
    ) -> IncidentSummary:
        """Generate a default summary when API is not available."""
        # Map pattern types to default tags
        pattern_tags = {
            "race": ["race-condition", "concurrency", "synchronization"],
            "split-brain": ["distributed-systems", "network-partition", "consensus"],
            "clock-skew": ["time-synchronization", "distributed-systems", "clock-drift"],
            "coordination": ["distributed-locks", "coordination", "consensus"],
        }

        tags = pattern_tags.get(pattern_type, ["distributed-systems"])

        return IncidentSummary(
            url=url,
            title=title,
            solution_summary=f"Engineers identified the root cause related to {pattern_type} issues and implemented fixes. See the full incident report for detailed analysis.",
            key_learnings=[
                "Root cause analysis is critical for understanding failures",
                "Monitoring and alerting help detect issues early",
                "Testing under realistic conditions prevents production issues",
            ],
            tags=tags,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
