"""Codebase analyzer agent using Claude for intelligent analysis."""

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .recommendations import AnalysisReport, PatternRecommender
from .tools import AnalysisTools


class CodebaseAnalyzer:
    """
    AI-powered codebase analyzer that recommends failure patterns.

    Uses local analysis tools combined with optional Claude API for
    deeper understanding and more intelligent recommendations.
    """

    SYSTEM_PROMPT = """You are an expert software reliability engineer analyzing codebases
to identify potential failure injection points for training purposes.

Your task is to:
1. Analyze the codebase structure and patterns found
2. Identify areas vulnerable to specific failure types
3. Recommend the most appropriate failure patterns to inject
4. Explain why each recommendation is suitable

Focus on:
- Race conditions in concurrent code
- Split-brain scenarios in distributed systems
- Clock skew issues in time-sensitive operations
- Coordination failures in distributed locks/consensus

Be specific about file paths and code patterns when making recommendations."""

    ANALYSIS_PROMPT = """Analyze this codebase for failure pattern injection opportunities.

## Codebase Overview
- Languages: {languages}
- Frameworks: {frameworks}
- Architecture: {architecture}
- Total Files: {total_files}
- Total Lines: {total_lines}

## Patterns Found
- Concurrency patterns: {concurrency_count}
- Distributed patterns: {distributed_count}
- State management patterns: {state_count}
- Time-sensitive patterns: {time_count}

## Sample Code Patterns

### Concurrency
{concurrency_samples}

### Distributed
{distributed_samples}

### State Management
{state_samples}

### Time-Sensitive
{time_samples}

## Available Failure Patterns
{available_patterns}

Based on this analysis, provide:
1. Top 5 recommended patterns to inject and why
2. Specific files/locations for each pattern
3. Expected difficulty level for each injection
4. Potential alternative patterns to consider

Format your response as JSON with the following structure:
{{
  "recommendations": [
    {{
      "pattern_id": "RACE-001",
      "confidence": 0.85,
      "rationale": "explanation",
      "suggested_files": ["path/to/file.rs"],
      "difficulty_adjustment": "none|easier|harder"
    }}
  ],
  "overall_assessment": "summary of codebase characteristics",
  "warnings": ["any concerns about injection feasibility"]
}}"""

    def __init__(
        self,
        patterns_dir: str | Path,
        api_key: str | None = None,
        use_ai: bool = True,
    ):
        """
        Initialize the analyzer.

        Args:
            patterns_dir: Directory containing pattern YAML files
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            use_ai: Whether to use Claude for enhanced analysis
        """
        self.patterns_dir = Path(patterns_dir)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.use_ai = use_ai and bool(self.api_key)
        self.recommender = PatternRecommender(patterns_dir)

        if self.use_ai:
            self.client = httpx.Client(timeout=120.0)
            self.base_url = "https://api.anthropic.com/v1/messages"

    def analyze(
        self,
        codebase_path: str | Path,
        top_k: int = 10,
        output_file: str | Path | None = None,
    ) -> AnalysisReport:
        """
        Analyze a codebase and generate recommendations.

        Args:
            codebase_path: Path to the codebase to analyze
            top_k: Number of top recommendations to return
            output_file: Optional file to write JSON report

        Returns:
            AnalysisReport with findings and recommendations
        """
        codebase_path = Path(codebase_path)

        # Run local analysis
        report = self.recommender.analyze_and_recommend(codebase_path, top_k=top_k)

        # Enhance with AI if available
        if self.use_ai:
            try:
                ai_recommendations = self._get_ai_recommendations(report)
                report = self._merge_recommendations(report, ai_recommendations)
            except Exception as e:
                print(f"Warning: AI analysis failed, using local analysis only: {e}")

        # Write output file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report.to_dict(), f, indent=2)

        return report

    def _get_ai_recommendations(self, report: AnalysisReport) -> dict[str, Any]:
        """Get AI-enhanced recommendations from Claude."""
        # Build the prompt
        prompt = self._build_analysis_prompt(report)

        # Call Claude
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": "claude-opus-4-20250514",
            "max_tokens": 4096,
            "system": self.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = self.client.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["content"][0]["text"]

        # Parse JSON from response
        try:
            # Find JSON in response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

        return {}

    def _build_analysis_prompt(self, report: AnalysisReport) -> str:
        """Build the analysis prompt from the report."""

        def format_samples(patterns: list, max_samples: int = 5) -> str:
            if not patterns:
                return "None found"
            samples = []
            for p in patterns[:max_samples]:
                if hasattr(p, "file_path"):
                    samples.append(f"- {p.file_path}:{p.line_number} - {p.pattern_type}")
            return "\n".join(samples) if samples else "None found"

        # Get available patterns
        all_patterns = self.recommender.catalog.list_patterns()
        pattern_list = "\n".join(
            [f"- {p.id}: {p.name} ({p.category})" for p in all_patterns[:20]]
        )

        return self.ANALYSIS_PROMPT.format(
            languages=", ".join(report.structure.languages) or "Unknown",
            frameworks=", ".join(report.structure.frameworks) or "None detected",
            architecture=", ".join(report.structure.architecture_hints) or "Unknown",
            total_files=report.structure.total_files,
            total_lines=report.structure.total_lines,
            concurrency_count=len(report.concurrency_patterns),
            distributed_count=len(report.distributed_patterns),
            state_count=len(report.state_patterns),
            time_count=len(report.time_patterns),
            concurrency_samples=format_samples(report.concurrency_patterns),
            distributed_samples=format_samples(report.distributed_patterns),
            state_samples=format_samples(report.state_patterns),
            time_samples=format_samples(report.time_patterns),
            available_patterns=pattern_list,
        )

    def _merge_recommendations(
        self, report: AnalysisReport, ai_recommendations: dict[str, Any]
    ) -> AnalysisReport:
        """Merge AI recommendations into the report."""
        if not ai_recommendations or "recommendations" not in ai_recommendations:
            return report

        # Update scores and rationales based on AI analysis
        ai_recs = {r["pattern_id"]: r for r in ai_recommendations.get("recommendations", [])}

        for rec in report.recommendations:
            if rec.pattern_id in ai_recs:
                ai_rec = ai_recs[rec.pattern_id]
                # Blend scores (60% AI, 40% local)
                ai_confidence = ai_rec.get("confidence", rec.score)
                rec.score = 0.6 * ai_confidence + 0.4 * rec.score
                # Enhance rationale
                if ai_rec.get("rationale"):
                    rec.rationale = f"{rec.rationale}. AI: {ai_rec['rationale']}"
                # Add suggested files
                if ai_rec.get("suggested_files"):
                    for f in ai_rec["suggested_files"]:
                        if f not in rec.injection_targets:
                            rec.injection_targets.append(f"(AI suggested) {f}")

        # Re-sort by updated scores
        report.recommendations.sort(key=lambda r: r.score, reverse=True)

        return report

    def quick_scan(self, codebase_path: str | Path) -> dict[str, Any]:
        """
        Perform a quick scan without full analysis.

        Args:
            codebase_path: Path to the codebase

        Returns:
            Quick summary of codebase characteristics
        """
        tools = AnalysisTools(codebase_path)
        structure = tools.analyze_structure()

        return {
            "path": str(codebase_path),
            "languages": structure.languages,
            "frameworks": structure.frameworks,
            "architecture": structure.architecture_hints,
            "total_files": structure.total_files,
            "total_lines": structure.total_lines,
            "has_tests": structure.has_tests,
            "has_ci": structure.has_ci,
            "has_docker": structure.has_docker,
            "suitable_for_injection": bool(
                structure.languages and structure.total_files > 10
            ),
        }

    def close(self) -> None:
        """Clean up resources."""
        if self.use_ai and hasattr(self, "client"):
            self.client.close()
