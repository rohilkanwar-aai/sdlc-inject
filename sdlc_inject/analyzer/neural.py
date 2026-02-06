"""Neural code analysis using Claude for semantic understanding."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "codebase_path": self.codebase_path,
            "files_analyzed": self.files_analyzed,
            "total_tokens_used": self.total_tokens_used,
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
        }


class NeuralCodeAnalyzer:
    """
    Neural code analyzer that uses Claude to semantically understand code
    and identify vulnerability injection points.
    """

    SYSTEM_PROMPT = """You are an expert security researcher and systems programmer analyzing code for potential failure injection points.

Your task is to deeply understand the code's logic, concurrency model, and data flow to identify where realistic bugs could be injected for training purposes.

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

Be specific about line numbers, function names, and data flow."""

    CODE_ANALYSIS_PROMPT = """Analyze this code file for potential failure injection points.

File: {file_path}
Language: {language}

```{language}
{code_content}
```

Identify vulnerability points where realistic bugs could be injected. For each point, provide:

1. **Location**: Exact line numbers and function name
2. **Vulnerability Type**: (race_condition, state_corruption, resource_leak, coordination_bug, timing_issue)
3. **Confidence**: 0.0-1.0 based on how exploitable this is
4. **Explanation**: Why this is vulnerable (semantic understanding, not pattern matching)
5. **Data Flow**: How data flows through this vulnerable point
6. **Suggested Injection**: Specific code change that would create a realistic bug
7. **Production Impact**: How this would manifest as a hard-to-debug production issue

Return as JSON:
{{
  "vulnerabilities": [
    {{
      "start_line": 45,
      "end_line": 52,
      "function_name": "acquire_buffer",
      "vulnerability_type": "race_condition",
      "confidence": 0.85,
      "explanation": "The buffer ownership check and acquisition are separate operations...",
      "data_flow": "User request -> check_ownership() -> acquire() -> buffer state",
      "suggested_injection": "Add a yield/delay between check and acquire to widen race window",
      "production_impact": "Under load, two users can acquire same buffer causing edit conflicts"
    }}
  ],
  "file_summary": "This file handles buffer management with potential concurrency issues..."
}}"""

    ARCHITECTURE_PROMPT = """Based on these code files, provide a high-level architecture analysis:

Files analyzed:
{file_list}

Key code patterns found:
{patterns_summary}

Provide:
1. **Architecture Summary**: What does this codebase do? (2-3 sentences)
2. **Concurrency Model**: How does it handle concurrent operations?
3. **Vulnerability Hotspots**: Which components are most vulnerable to which failure types?
4. **Recommended Patterns**: Which failure patterns from our catalog would be most effective?

Catalog patterns available:
- RACE-001 to RACE-005: Race conditions (buffer ownership, ID generation, cache invalidation)
- SPLIT-001 to SPLIT-005: Split-brain (network partition, state divergence, reconnection)
- CLOCK-001 to CLOCK-005: Clock skew (timestamp ordering, cache expiration, rate limiting)
- COORD-001 to COORD-005: Coordination (distributed locks, CRDT merge, operation ordering)

Return as JSON:
{{
  "architecture_summary": "...",
  "concurrency_model": "...",
  "vulnerability_hotspots": [
    {{"component": "buffer_manager", "vulnerable_to": ["race_condition", "state_corruption"]}}
  ],
  "recommended_patterns": [
    {{"pattern_id": "RACE-001", "confidence": 0.9, "target_files": ["src/db/buffers.rs"], "rationale": "..."}}
  ]
}}"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        exa_api_key: str | None = None,
    ):
        """
        Initialize the neural analyzer.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            exa_api_key: Optional Exa API key for semantic search
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.exa_api_key = exa_api_key or os.environ.get("EXA_API_KEY")
        self.client = httpx.Client(timeout=120.0)
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.total_tokens = 0

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required for neural analysis")

    def analyze_codebase(
        self,
        codebase_path: str | Path,
        max_files: int = 20,
        focus_patterns: list[str] | None = None,
        output_file: str | Path | None = None,
    ) -> NeuralAnalysisResult:
        """
        Perform deep neural analysis of a codebase.

        Args:
            codebase_path: Path to the codebase
            max_files: Maximum files to analyze (most relevant first)
            focus_patterns: Pattern types to focus on (e.g., ["race", "coordination"])
            output_file: Optional file to write results

        Returns:
            NeuralAnalysisResult with identified vulnerabilities
        """
        codebase_path = Path(codebase_path)

        # Find relevant files
        files_to_analyze = self._find_relevant_files(codebase_path, max_files)

        # Analyze each file
        all_vulnerabilities: list[VulnerabilityPoint] = []
        file_summaries: list[str] = []

        for file_path in files_to_analyze:
            try:
                vulnerabilities, summary = self._analyze_file(file_path, codebase_path)
                all_vulnerabilities.extend(vulnerabilities)
                file_summaries.append(f"{file_path.relative_to(codebase_path)}: {summary}")
            except Exception as e:
                print(f"Warning: Failed to analyze {file_path}: {e}")

        # Get architecture-level analysis
        arch_analysis = self._analyze_architecture(
            codebase_path, files_to_analyze, file_summaries, all_vulnerabilities
        )

        # Filter by focus patterns if specified
        if focus_patterns:
            all_vulnerabilities = [
                v for v in all_vulnerabilities
                if any(fp in v.vulnerability_type for fp in focus_patterns)
            ]

        # Sort by confidence
        all_vulnerabilities.sort(key=lambda v: v.confidence, reverse=True)

        result = NeuralAnalysisResult(
            codebase_path=str(codebase_path),
            files_analyzed=len(files_to_analyze),
            total_tokens_used=self.total_tokens,
            vulnerability_points=all_vulnerabilities,
            architecture_summary=arch_analysis.get("architecture_summary", ""),
            concurrency_model=arch_analysis.get("concurrency_model", ""),
            recommended_patterns=arch_analysis.get("recommended_patterns", []),
        )

        if output_file:
            with open(output_file, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

        return result

    def _find_relevant_files(self, codebase_path: Path, max_files: int) -> list[Path]:
        """Find the most relevant files for analysis."""
        # Priority patterns for different vulnerability types
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
                # Skip excluded directories
                if any(excl in file_path.parts for excl in exclude_dirs):
                    continue

                # Calculate priority score
                score = 0
                path_str = str(file_path).lower()

                for pattern in priority_patterns:
                    pattern_clean = pattern.replace("**/", "").replace("*", "")
                    if pattern_clean in path_str:
                        score += 10

                # Boost for smaller files (likely more focused)
                try:
                    size = file_path.stat().st_size
                    if size < 5000:
                        score += 5
                    elif size < 20000:
                        score += 2
                except OSError:
                    pass

                all_files.append((file_path, score))

        # Sort by score and take top files
        all_files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in all_files[:max_files]]

    def _analyze_file(
        self, file_path: Path, codebase_root: Path
    ) -> tuple[list[VulnerabilityPoint], str]:
        """Analyze a single file for vulnerabilities."""
        content = file_path.read_text(errors="ignore")

        # Skip very large files
        if len(content) > 50000:
            content = content[:50000] + "\n... (truncated)"

        # Detect language
        ext = file_path.suffix
        lang_map = {
            ".rs": "rust",
            ".py": "python",
            ".go": "go",
            ".ts": "typescript",
            ".js": "javascript",
            ".java": "java",
        }
        language = lang_map.get(ext, "text")

        # Build prompt
        prompt = self.CODE_ANALYSIS_PROMPT.format(
            file_path=file_path.relative_to(codebase_root),
            language=language,
            code_content=content,
        )

        # Call Claude
        response = self._call_claude(prompt)

        # Parse response
        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
            else:
                return [], "Failed to parse analysis"

            vulnerabilities = []
            for vuln in data.get("vulnerabilities", []):
                vulnerabilities.append(
                    VulnerabilityPoint(
                        file_path=str(file_path.relative_to(codebase_root)),
                        start_line=vuln.get("start_line", 0),
                        end_line=vuln.get("end_line", 0),
                        code_snippet=self._extract_snippet(content, vuln.get("start_line", 0), vuln.get("end_line", 0)),
                        vulnerability_type=vuln.get("vulnerability_type", "unknown"),
                        confidence=vuln.get("confidence", 0.5),
                        explanation=vuln.get("explanation", ""),
                        suggested_injection=vuln.get("suggested_injection", ""),
                        affected_functions=[vuln.get("function_name", "")] if vuln.get("function_name") else [],
                        data_flow=vuln.get("data_flow"),
                    )
                )

            return vulnerabilities, data.get("file_summary", "")

        except json.JSONDecodeError:
            return [], "Failed to parse JSON response"

    def _analyze_architecture(
        self,
        codebase_path: Path,
        files: list[Path],
        summaries: list[str],
        vulnerabilities: list[VulnerabilityPoint],
    ) -> dict[str, Any]:
        """Perform architecture-level analysis."""
        # Build patterns summary from vulnerabilities
        vuln_summary = {}
        for v in vulnerabilities:
            vuln_summary[v.vulnerability_type] = vuln_summary.get(v.vulnerability_type, 0) + 1

        patterns_summary = "\n".join(
            f"- {vtype}: {count} potential points"
            for vtype, count in vuln_summary.items()
        )

        file_list = "\n".join(
            f"- {f.relative_to(codebase_path)}"
            for f in files[:20]
        )

        prompt = self.ARCHITECTURE_PROMPT.format(
            file_list=file_list,
            patterns_summary=patterns_summary or "No specific patterns identified yet",
        )

        response = self._call_claude(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError:
            pass

        return {
            "architecture_summary": "Analysis failed",
            "concurrency_model": "Unknown",
            "recommended_patterns": [],
        }

    def _call_claude(self, prompt: str) -> str:
        """Call Claude API."""
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": self.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = self.client.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        # Track token usage
        usage = data.get("usage", {})
        self.total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return data["content"][0]["text"]

    def _extract_snippet(self, content: str, start_line: int, end_line: int) -> str:
        """Extract code snippet from content."""
        lines = content.split("\n")
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        return "\n".join(lines[start:end])

    def search_similar_vulnerabilities(
        self, vulnerability: VulnerabilityPoint, max_results: int = 5
    ) -> list[dict]:
        """
        Use Exa semantic search to find similar vulnerabilities in open source.

        Args:
            vulnerability: The vulnerability to search for similar cases
            max_results: Maximum number of results to return

        Returns:
            List of similar vulnerabilities found in open-source projects
        """
        if not self.exa_api_key:
            return []

        # Build semantic query from vulnerability
        query = self._build_exa_query(vulnerability)

        try:
            response = self.client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": self.exa_api_key,
                    "content-type": "application/json",
                },
                json={
                    "query": query,
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
        """
        Search for real-world incident reports related to a vulnerability.

        Args:
            vulnerability: The vulnerability to find related incidents for
            max_results: Maximum number of results to return

        Returns:
            List of incident reports and postmortems
        """
        if not self.exa_api_key:
            return []

        # Build query focused on incident reports and postmortems
        vuln_type_map = {
            "race_condition": "race condition concurrency bug incident postmortem",
            "state_corruption": "state corruption data inconsistency incident postmortem",
            "resource_leak": "memory leak connection pool exhaustion incident",
            "coordination_bug": "distributed lock consensus failure incident postmortem",
            "timing_issue": "clock skew timeout timing bug incident",
        }

        query = vuln_type_map.get(
            vulnerability.vulnerability_type,
            f"{vulnerability.vulnerability_type} production incident postmortem"
        )

        try:
            response = self.client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": self.exa_api_key,
                    "content-type": "application/json",
                },
                json={
                    "query": query,
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
        # Extract key concepts for search
        concepts = [vulnerability.vulnerability_type.replace("_", " ")]

        # Add function context if available
        if vulnerability.affected_functions:
            concepts.extend(vulnerability.affected_functions[:2])

        # Add data flow keywords if available
        if vulnerability.data_flow:
            # Extract key terms from data flow
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
    ) -> NeuralAnalysisResult:
        """
        Enrich analysis results with similar code and incidents from the web.

        Args:
            result: The neural analysis result to enrich
            search_similar: Whether to search for similar vulnerabilities
            search_incidents: Whether to search for related incidents

        Returns:
            Enriched analysis result
        """
        if not self.exa_api_key:
            return result

        for vuln in result.vulnerability_points[:10]:  # Limit API calls
            if search_similar:
                similar = self.search_similar_vulnerabilities(vuln, max_results=3)
                vuln.similar_vulnerabilities = similar  # type: ignore

            if search_incidents:
                incidents = self.search_incident_reports(vuln, max_results=3)
                vuln.related_incidents = incidents  # type: ignore

        return result

    def close(self) -> None:
        """Clean up resources."""
        self.client.close()
