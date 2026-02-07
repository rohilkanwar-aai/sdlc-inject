"""Neural code analysis using Claude Agent SDK for semantic understanding.

Uses the Claude Agent SDK to give Claude direct access to codebase exploration
tools (Read, Glob, Grep), enabling it to follow imports, trace data flows,
and identify cross-file vulnerabilities -- rather than analyzing files in isolation.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from claude_agent_sdk import query, ResultMessage

from ..sdk_utils import (
    SDKUsageStats,
    create_agent_options,
    extract_json_from_text,
    collect_text_from_messages,
    DEFAULT_MODEL,
)


@dataclass
class VulnerabilityPoint:
    """A semantically identified vulnerability point in code."""

    file_path: str
    start_line: int
    end_line: int
    code_snippet: str
    vulnerability_type: str  # "race_condition", "state_corruption", etc.
    confidence: float  # 0.0 to 1.0
    explanation: str
    suggested_injection: str
    affected_functions: list[str] = field(default_factory=list)
    data_flow: str | None = None
    # Enrichment fields (populated by Exa search)
    similar_vulnerabilities: list[dict[str, Any]] = field(default_factory=list)
    related_incidents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NeuralAnalysisResult:
    """Result of neural code analysis."""

    codebase_path: str
    files_analyzed: int
    total_tokens_used: int
    vulnerability_points: list[VulnerabilityPoint]
    architecture_summary: str
    concurrency_model: str
    recommended_patterns: list[dict[str, Any]]
    total_cost_usd: float = 0.0
    # Tool discovery results (populated by enrich_with_similar_code with discover_tools=True)
    discovered_tools: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "codebase_path": self.codebase_path,
            "files_analyzed": self.files_analyzed,
            "total_tokens_used": self.total_tokens_used,
            "total_cost_usd": self.total_cost_usd,
            "architecture_summary": self.architecture_summary,
            "concurrency_model": self.concurrency_model,
            "vulnerability_points": [
                {
                    "file_path": v.file_path,
                    "lines": f"{v.start_line}-{v.end_line}",
                    "type": v.vulnerability_type,
                    "confidence": v.confidence,
                    "explanation": v.explanation,
                    "suggested_injection": v.suggested_injection,
                    "affected_functions": v.affected_functions,
                    "data_flow": v.data_flow,
                    "similar_vulnerabilities": v.similar_vulnerabilities,
                    "related_incidents": v.related_incidents,
                }
                for v in self.vulnerability_points
            ],
            "recommended_patterns": self.recommended_patterns,
            "discovered_tools": self.discovered_tools,
        }


class NeuralCodeAnalyzer:
    """
    Neural code analyzer that uses the Claude Agent SDK to semantically
    understand code and identify vulnerability injection points.

    Unlike the previous implementation that analyzed files in isolation,
    this version gives Claude direct access to Read, Glob, and Grep tools
    so it can explore the codebase, follow imports, and identify cross-file
    vulnerabilities.
    """

    SYSTEM_PROMPT = """You are an expert security researcher and systems programmer \
analyzing code for potential failure injection points.

Your task is to deeply understand the code's logic, concurrency model, and data flow \
to identify where realistic bugs could be injected for training purposes.

You have access to tools to explore the codebase. Use them to:
- Browse the directory structure to understand the project layout
- Read files that look relevant to concurrency, state management, or distributed systems
- Search for patterns like locks, mutexes, channels, shared state, async operations
- Follow imports and function calls across files to understand data flow

Focus on:
1. **Race conditions**: Check-then-act patterns, non-atomic operations, shared mutable state
2. **State corruption**: Inconsistent state updates, missing locks, partial writes
3. **Distributed failures**: Network assumptions, split-brain scenarios, clock dependencies
4. **Resource leaks**: Unclosed handles in error paths, connection pool issues
5. **Coordination bugs**: Lock ordering, deadlock potential, consensus issues

For each vulnerability, explain:
- WHY this code is vulnerable (the semantic reason, not just pattern matching)
- HOW the bug would manifest in production
- WHAT injection would create a realistic, hard-to-debug failure

Be specific about line numbers, function names, and data flow.

When you have finished analyzing, output your complete findings as a single JSON object \
with this exact structure:
{
  "files_analyzed": ["path/to/file1.rs", "path/to/file2.rs"],
  "vulnerabilities": [
    {
      "file_path": "relative/path/to/file.rs",
      "start_line": 45,
      "end_line": 52,
      "code_snippet": "the relevant code",
      "function_name": "acquire_buffer",
      "vulnerability_type": "race_condition",
      "confidence": 0.85,
      "explanation": "The buffer ownership check and acquisition are separate operations...",
      "data_flow": "User request -> check_ownership() -> acquire() -> buffer state",
      "suggested_injection": "Add a yield/delay between check and acquire to widen race window",
      "production_impact": "Under load, two users can acquire same buffer causing edit conflicts"
    }
  ],
  "architecture_summary": "This codebase is a collaborative editor with...",
  "concurrency_model": "Uses async/await with shared mutable state protected by...",
  "vulnerability_hotspots": [
    {"component": "buffer_manager", "vulnerable_to": ["race_condition", "state_corruption"]}
  ],
  "recommended_patterns": [
    {"pattern_id": "RACE-001", "confidence": 0.9, "target_files": ["src/db/buffers.rs"], \
"rationale": "..."}
  ]
}

Catalog patterns available:
- RACE-001 to RACE-005: Race conditions (buffer ownership, ID generation, cache invalidation)
- SPLIT-001 to SPLIT-005: Split-brain (network partition, state divergence, reconnection)
- CLOCK-001 to CLOCK-005: Clock skew (timestamp ordering, cache expiration, rate limiting)
- COORD-001 to COORD-005: Coordination (distributed locks, CRDT merge, operation ordering)"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        exa_api_key: str | None = None,
        max_budget_usd: float = 5.0,
        # Kept for backward compatibility but no longer used for SDK auth
        api_key: str | None = None,
    ):
        """
        Initialize the neural analyzer.

        Args:
            model: Claude model to use
            exa_api_key: Optional Exa API key for semantic search enrichment
            max_budget_usd: Maximum cost budget per analysis run
            api_key: Deprecated -- SDK reads ANTHROPIC_API_KEY from env
        """
        self.model = model
        self.exa_api_key = exa_api_key or os.environ.get("EXA_API_KEY")
        self.max_budget_usd = max_budget_usd
        self.usage_stats = SDKUsageStats()

        # httpx client kept only for Exa API calls
        self._exa_client: httpx.Client | None = None

    @property
    def _exa_http_client(self) -> httpx.Client:
        """Lazy-init httpx client for Exa API calls only."""
        if self._exa_client is None:
            self._exa_client = httpx.Client(timeout=60.0)
        return self._exa_client

    @property
    def total_tokens(self) -> int:
        """Backward-compatible token count."""
        return self.usage_stats.total_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_codebase_async(
        self,
        codebase_path: str | Path,
        max_files: int = 20,
        focus_patterns: list[str] | None = None,
        output_file: str | Path | None = None,
    ) -> NeuralAnalysisResult:
        """
        Perform deep neural analysis of a codebase using the Agent SDK.

        The agent explores the codebase using Read, Glob, and Grep tools,
        identifies vulnerability injection points, and produces a structured
        analysis result.

        Args:
            codebase_path: Path to the codebase
            max_files: Suggested maximum files to analyze
            focus_patterns: Pattern types to focus on (e.g., ["race", "coordination"])
            output_file: Optional file to write results

        Returns:
            NeuralAnalysisResult with identified vulnerabilities
        """
        codebase_path = Path(codebase_path)

        # Build seed hints from heuristic file selector
        seed_files = self._find_relevant_files(codebase_path, max_files)
        seed_hints = "\n".join(
            f"- {f.relative_to(codebase_path)}" for f in seed_files[:max_files]
        )

        # Build the exploration prompt
        focus_str = ""
        if focus_patterns:
            focus_str = (
                f"\n\nFocus especially on these vulnerability types: "
                f"{', '.join(focus_patterns)}"
            )

        prompt = f"""Analyze the codebase at the current working directory for potential \
failure injection points.

Here are some files that look relevant based on their names (but explore beyond these \
if you find interesting leads):

{seed_hints}

Analyze up to {max_files} files. For each file you read, identify specific vulnerability \
points where realistic bugs could be injected.{focus_str}

After exploring, output your complete findings as the JSON structure described in your \
instructions."""

        # Run the agent with exploration tools
        options = create_agent_options(
            system_prompt=self.SYSTEM_PROMPT,
            allowed_tools=["Read", "Glob", "Grep"],
            model=self.model,
            max_turns=max_files * 3,  # ~3 tool calls per file
            max_budget_usd=self.max_budget_usd,
            cwd=str(codebase_path),
        )

        # Collect all messages to extract the final JSON
        all_messages: list = []
        async for message in query(prompt=prompt, options=options):
            all_messages.append(message)
            if isinstance(message, ResultMessage):
                self.usage_stats.record_result(message)

        # Extract the analysis JSON from agent's output
        full_text = collect_text_from_messages(all_messages)
        analysis_data = extract_json_from_text(full_text)

        if analysis_data is None:
            analysis_data = {
                "files_analyzed": [],
                "vulnerabilities": [],
                "architecture_summary": "Analysis did not produce structured output",
                "concurrency_model": "Unknown",
                "recommended_patterns": [],
            }

        # Build result
        vulnerabilities = self._parse_vulnerabilities(analysis_data, codebase_path)

        # Filter by focus patterns if specified
        if focus_patterns:
            vulnerabilities = [
                v for v in vulnerabilities
                if any(fp in v.vulnerability_type for fp in focus_patterns)
            ]

        # Sort by confidence
        vulnerabilities.sort(key=lambda v: v.confidence, reverse=True)

        files_analyzed_count = len(analysis_data.get("files_analyzed", []))

        result = NeuralAnalysisResult(
            codebase_path=str(codebase_path),
            files_analyzed=files_analyzed_count or len(seed_files),
            total_tokens_used=self.usage_stats.total_tokens,
            total_cost_usd=self.usage_stats.total_cost_usd,
            vulnerability_points=vulnerabilities,
            architecture_summary=analysis_data.get("architecture_summary", ""),
            concurrency_model=analysis_data.get("concurrency_model", ""),
            recommended_patterns=analysis_data.get("recommended_patterns", []),
        )

        if output_file:
            with open(output_file, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

        return result

    def analyze_codebase(
        self,
        codebase_path: str | Path,
        max_files: int = 20,
        focus_patterns: list[str] | None = None,
        output_file: str | Path | None = None,
    ) -> NeuralAnalysisResult:
        """
        Synchronous wrapper for analyze_codebase_async.

        Provided for backward compatibility with CLI code that doesn't
        use async/await directly.
        """
        return asyncio.run(
            self.analyze_codebase_async(
                codebase_path=codebase_path,
                max_files=max_files,
                focus_patterns=focus_patterns,
                output_file=output_file,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_vulnerabilities(
        self, data: dict[str, Any], codebase_path: Path
    ) -> list[VulnerabilityPoint]:
        """Parse vulnerability data from the agent's JSON output."""
        vulnerabilities = []
        for vuln in data.get("vulnerabilities", []):
            vulnerabilities.append(
                VulnerabilityPoint(
                    file_path=vuln.get("file_path", ""),
                    start_line=vuln.get("start_line", 0),
                    end_line=vuln.get("end_line", 0),
                    code_snippet=vuln.get("code_snippet", ""),
                    vulnerability_type=vuln.get("vulnerability_type", "unknown"),
                    confidence=vuln.get("confidence", 0.5),
                    explanation=vuln.get("explanation", ""),
                    suggested_injection=vuln.get("suggested_injection", ""),
                    affected_functions=(
                        [vuln.get("function_name", "")]
                        if vuln.get("function_name")
                        else []
                    ),
                    data_flow=vuln.get("data_flow"),
                )
            )
        return vulnerabilities

    def _find_relevant_files(self, codebase_path: Path, max_files: int) -> list[Path]:
        """Find the most relevant files for analysis (heuristic seed).

        This provides a starting point for the agent's exploration. The agent
        may read additional files beyond these based on what it discovers.
        """
        priority_patterns = [
            # Concurrency-related
            "**/mutex*", "**/lock*", "**/sync*", "**/async*", "**/thread*",
            "**/channel*", "**/atomic*", "**/concurrent*",
            # State management
            "**/state*", "**/cache*", "**/session*", "**/buffer*",
            # Distributed systems
            "**/rpc*", "**/grpc*", "**/consensus*", "**/replica*",
            "**/partition*", "**/cluster*",
            # Database/storage
            "**/db*", "**/database*", "**/storage*", "**/pool*",
            # Core logic
            "**/core*", "**/service*", "**/handler*", "**/api*",
        ]

        extensions = {".rs", ".py", ".go", ".ts", ".js", ".java"}
        exclude_dirs = {"node_modules", "target", ".git", "vendor", "venv", "__pycache__"}

        all_files: list[tuple[Path, int]] = []

        for ext in extensions:
            for file_path in codebase_path.rglob(f"*{ext}"):
                if any(excl in file_path.parts for excl in exclude_dirs):
                    continue

                score = 0
                path_str = str(file_path).lower()

                for pattern in priority_patterns:
                    pattern_clean = pattern.replace("**/", "").replace("*", "")
                    if pattern_clean in path_str:
                        score += 10

                try:
                    size = file_path.stat().st_size
                    if size < 5000:
                        score += 5
                    elif size < 20000:
                        score += 2
                except OSError:
                    pass

                all_files.append((file_path, score))

        all_files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in all_files[:max_files]]

    # ------------------------------------------------------------------
    # Exa enrichment (unchanged -- direct HTTP, not Claude)
    # ------------------------------------------------------------------

    def search_similar_vulnerabilities(
        self, vulnerability: VulnerabilityPoint, max_results: int = 5
    ) -> list[dict]:
        """Use Exa semantic search to find similar vulnerabilities in open source."""
        if not self.exa_api_key:
            return []

        exa_query = self._build_exa_query(vulnerability)

        try:
            response = self._exa_http_client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": self.exa_api_key,
                    "content-type": "application/json",
                },
                json={
                    "query": exa_query,
                    "type": "neural",
                    "useAutoprompt": True,
                    "numResults": max_results,
                    "category": "github",
                    "contents": {
                        "text": {"maxCharacters": 2000},
                        "highlights": {"numSentences": 3},
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for result in data.get("results", []):
                results.append({
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "text": result.get("text", ""),
                    "highlights": result.get("highlights", []),
                    "score": result.get("score", 0.0),
                    "published_date": result.get("publishedDate"),
                })

            return results

        except Exception as e:
            print(f"Warning: Exa search failed: {e}")
            return []

    def search_incident_reports(
        self, vulnerability: VulnerabilityPoint, max_results: int = 5
    ) -> list[dict]:
        """Search for real-world incident reports related to a vulnerability."""
        if not self.exa_api_key:
            return []

        vuln_type_map = {
            "race_condition": "race condition concurrency bug incident postmortem",
            "state_corruption": "state corruption data inconsistency incident postmortem",
            "resource_leak": "memory leak connection pool exhaustion incident",
            "coordination_bug": "distributed lock consensus failure incident postmortem",
            "timing_issue": "clock skew timeout timing bug incident",
        }

        exa_query = vuln_type_map.get(
            vulnerability.vulnerability_type,
            f"{vulnerability.vulnerability_type} production incident postmortem",
        )

        try:
            response = self._exa_http_client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": self.exa_api_key,
                    "content-type": "application/json",
                },
                json={
                    "query": exa_query,
                    "type": "neural",
                    "useAutoprompt": True,
                    "numResults": max_results,
                    "includeDomains": [
                        "github.com",
                        "engineering.fb.com",
                        "netflixtechblog.com",
                        "eng.uber.com",
                        "blog.cloudflare.com",
                        "aws.amazon.com",
                        "cloud.google.com",
                        "medium.com",
                        "notion.site",
                    ],
                    "contents": {
                        "text": {"maxCharacters": 3000},
                        "highlights": {"numSentences": 5},
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for result in data.get("results", []):
                results.append({
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "text": result.get("text", ""),
                    "highlights": result.get("highlights", []),
                    "score": result.get("score", 0.0),
                    "published_date": result.get("publishedDate"),
                    "source_type": self._classify_source(result.get("url", "")),
                })

            return results

        except Exception as e:
            print(f"Warning: Exa incident search failed: {e}")
            return []

    def _build_exa_query(self, vulnerability: VulnerabilityPoint) -> str:
        """Build a semantic search query from a vulnerability."""
        concepts = [vulnerability.vulnerability_type.replace("_", " ")]

        if vulnerability.affected_functions:
            concepts.extend(vulnerability.affected_functions[:2])

        if vulnerability.data_flow:
            flow_terms = [
                term.strip()
                for term in vulnerability.data_flow.replace("->", " ").split()
                if len(term) > 3 and term.isalnum()
            ][:3]
            concepts.extend(flow_terms)

        return f"code vulnerability {' '.join(concepts)} bug fix solution"

    def _classify_source(self, url: str) -> str:
        """Classify the source type from URL."""
        url_lower = url.lower()

        if "github.com" in url_lower:
            if "/issues/" in url_lower or "/pull/" in url_lower:
                return "github_issue"
            return "github"
        elif any(blog in url_lower for blog in ["engineering", "techblog", "eng.", "blog"]):
            return "engineering_blog"
        elif "postmortem" in url_lower or "incident" in url_lower:
            return "postmortem"
        elif "aws.amazon.com" in url_lower or "cloud.google.com" in url_lower:
            return "cloud_provider"
        else:
            return "article"

    def enrich_with_similar_code(
        self,
        result: NeuralAnalysisResult,
        search_similar: bool = True,
        search_incidents: bool = True,
        discover_tools: bool = False,
    ) -> NeuralAnalysisResult:
        """Enrich analysis results with similar code and incidents from the web.

        Args:
            result: The analysis result to enrich
            search_similar: Search for similar vulnerabilities in open source
            search_incidents: Search for related incident reports
            discover_tools: Extract tool profiles from incident data for dynamic MCP servers

        Returns:
            Enriched result (with discovered_tools if discover_tools=True)
        """
        if not self.exa_api_key:
            return result

        for vuln in result.vulnerability_points[:10]:  # Limit API calls
            if search_similar:
                similar = self.search_similar_vulnerabilities(vuln, max_results=3)
                vuln.similar_vulnerabilities = similar

            if search_incidents:
                incidents = self.search_incident_reports(vuln, max_results=3)
                vuln.related_incidents = incidents

        # Run tool discovery on the enrichment data
        if discover_tools:
            try:
                from ..discovery.tool_extractor import ToolExtractor

                pattern_ids = [
                    p.get("pattern_id", "")
                    for p in result.recommended_patterns
                    if p.get("pattern_id")
                ]
                extractor = ToolExtractor(model=self.model)
                profiles = extractor.extract_tools(
                    result.vulnerability_points,
                    pattern_ids=pattern_ids,
                )
                result.discovered_tools = [p.to_dict() for p in profiles]
            except Exception as e:
                print(f"Warning: Tool discovery failed: {e}")

        return result

    def close(self) -> None:
        """Clean up resources."""
        if self._exa_client is not None:
            self._exa_client.close()
