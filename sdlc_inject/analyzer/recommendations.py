"""Pattern recommendation engine based on codebase analysis."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..catalog import PatternCatalog
from ..models import Pattern
from .tools import (
    AnalysisTools,
    CodebaseStructure,
    ConcurrencyPattern,
    DistributedPattern,
    StatePattern,
    TimeSensitivePattern,
)


@dataclass
class PatternRecommendation:
    """A recommended pattern for injection."""

    pattern_id: str
    pattern_name: str
    score: float  # 0.0 to 1.0
    rationale: str
    injection_targets: list[str] = field(default_factory=list)
    matching_code: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Complete analysis report for a codebase."""

    codebase_path: str
    structure: CodebaseStructure
    concurrency_patterns: list[ConcurrencyPattern]
    distributed_patterns: list[DistributedPattern]
    state_patterns: list[StatePattern]
    time_patterns: list[TimeSensitivePattern]
    recommendations: list[PatternRecommendation]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "codebase": {
                "path": self.codebase_path,
                "languages": self.structure.languages,
                "frameworks": self.structure.frameworks,
                "architecture": self.structure.architecture_hints,
                "total_files": self.structure.total_files,
                "total_lines": self.structure.total_lines,
                "has_tests": self.structure.has_tests,
                "has_ci": self.structure.has_ci,
                "has_docker": self.structure.has_docker,
            },
            "patterns_found": {
                "concurrency": len(self.concurrency_patterns),
                "distributed": len(self.distributed_patterns),
                "state_management": len(self.state_patterns),
                "time_sensitive": len(self.time_patterns),
            },
            "recommendations": [
                {
                    "pattern_id": r.pattern_id,
                    "pattern_name": r.pattern_name,
                    "score": round(r.score, 3),
                    "rationale": r.rationale,
                    "injection_targets": r.injection_targets,
                    "matching_code_samples": r.matching_code[:3],
                }
                for r in self.recommendations
            ],
        }


class PatternRecommender:
    """Recommends failure patterns based on codebase analysis."""

    # Category weights for scoring
    CATEGORY_WEIGHTS = {
        "race": {"concurrency": 0.6, "state": 0.3, "distributed": 0.1},
        "split-brain": {"distributed": 0.6, "state": 0.3, "concurrency": 0.1},
        "clock-skew": {"time": 0.6, "distributed": 0.3, "state": 0.1},
        "coordination": {"distributed": 0.4, "concurrency": 0.4, "state": 0.2},
    }

    def __init__(self, patterns_dir: Path | str):
        """
        Initialize the recommender.

        Args:
            patterns_dir: Directory containing pattern YAML files
        """
        self.patterns_dir = Path(patterns_dir)
        self.catalog = PatternCatalog(patterns_dir)

    def analyze_and_recommend(
        self, codebase_path: str | Path, top_k: int = 10
    ) -> AnalysisReport:
        """
        Analyze a codebase and recommend patterns.

        Args:
            codebase_path: Path to the codebase
            top_k: Number of top recommendations to return

        Returns:
            AnalysisReport with findings and recommendations
        """
        codebase_path = Path(codebase_path)
        tools = AnalysisTools(codebase_path)

        # Analyze the codebase
        structure = tools.analyze_structure()
        concurrency = tools.find_concurrency_patterns()
        distributed = tools.find_distributed_patterns()
        state = tools.find_state_patterns()
        time_patterns = tools.find_time_sensitive_patterns()

        # Score all patterns
        all_patterns = self.catalog.list_patterns()
        scored_patterns: list[tuple[Pattern, float, str, list[dict]]] = []

        for pattern in all_patterns:
            score, rationale, matches = self._score_pattern(
                pattern, structure, concurrency, distributed, state, time_patterns
            )
            if score > 0.1:  # Only include patterns with meaningful scores
                scored_patterns.append((pattern, score, rationale, matches))

        # Sort by score and take top k
        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        top_patterns = scored_patterns[:top_k]

        # Build recommendations
        recommendations = [
            PatternRecommendation(
                pattern_id=p.id,
                pattern_name=p.name,
                score=score,
                rationale=rationale,
                injection_targets=self._get_injection_targets(p, matches),
                matching_code=matches,
            )
            for p, score, rationale, matches in top_patterns
        ]

        return AnalysisReport(
            codebase_path=str(codebase_path),
            structure=structure,
            concurrency_patterns=concurrency,
            distributed_patterns=distributed,
            state_patterns=state,
            time_patterns=time_patterns,
            recommendations=recommendations,
        )

    def _score_pattern(
        self,
        pattern: Pattern,
        structure: CodebaseStructure,
        concurrency: list[ConcurrencyPattern],
        distributed: list[DistributedPattern],
        state: list[StatePattern],
        time_patterns: list[TimeSensitivePattern],
    ) -> tuple[float, str, list[dict]]:
        """
        Score a pattern's applicability to the codebase.

        Returns:
            Tuple of (score, rationale, matching_code)
        """
        score = 0.0
        reasons: list[str] = []
        matches: list[dict] = []

        # Determine pattern category
        pattern_category = self._get_pattern_category(pattern.id)
        weights = self.CATEGORY_WEIGHTS.get(
            pattern_category, {"concurrency": 0.25, "distributed": 0.25, "state": 0.25, "time": 0.25}
        )

        # Score based on concurrency patterns
        if concurrency:
            conc_score = min(len(concurrency) / 10, 1.0) * weights.get("concurrency", 0.25)
            score += conc_score
            if conc_score > 0.1:
                high_risk = [c for c in concurrency if c.risk_level == "high"]
                reasons.append(f"Found {len(concurrency)} concurrency patterns ({len(high_risk)} high-risk)")
                matches.extend(
                    [
                        {"file": c.file_path, "line": c.line_number, "type": c.pattern_type, "snippet": c.code_snippet}
                        for c in concurrency[:5]
                    ]
                )

        # Score based on distributed patterns
        if distributed:
            dist_score = min(len(distributed) / 10, 1.0) * weights.get("distributed", 0.25)
            score += dist_score
            if dist_score > 0.1:
                reasons.append(f"Found {len(distributed)} distributed system patterns")
                matches.extend(
                    [
                        {"file": d.file_path, "line": d.line_number, "type": d.pattern_type, "snippet": d.code_snippet}
                        for d in distributed[:5]
                    ]
                )

        # Score based on state patterns
        if state:
            state_score = min(len(state) / 5, 1.0) * weights.get("state", 0.25)
            score += state_score
            if state_score > 0.1:
                high_risk = [s for s in state if s.risk_level == "high"]
                reasons.append(f"Found {len(state)} state management patterns ({len(high_risk)} high-risk)")
                matches.extend(
                    [
                        {"file": s.file_path, "line": s.line_number, "type": s.pattern_type, "snippet": s.code_snippet}
                        for s in state[:5]
                    ]
                )

        # Score based on time patterns
        if time_patterns:
            time_score = min(len(time_patterns) / 5, 1.0) * weights.get("time", 0.25)
            score += time_score
            if time_score > 0.1:
                reasons.append(f"Found {len(time_patterns)} time-sensitive patterns")
                matches.extend(
                    [
                        {"file": t.file_path, "line": t.line_number, "type": t.pattern_type, "snippet": t.code_snippet}
                        for t in time_patterns[:5]
                    ]
                )

        # Boost score based on language/framework match
        if pattern.target_codebase:
            target_lang = pattern.target_codebase.language
            if target_lang and target_lang.lower() in [l.lower() for l in structure.languages]:
                score *= 1.2
                reasons.append(f"Target language ({target_lang}) matches")

        # Cap score at 1.0
        score = min(score, 1.0)

        rationale = "; ".join(reasons) if reasons else "General applicability"

        return score, rationale, matches

    def _get_pattern_category(self, pattern_id: str) -> str:
        """Extract category from pattern ID."""
        prefix = pattern_id.split("-")[0].lower()
        category_map = {
            "race": "race",
            "split": "split-brain",
            "clock": "clock-skew",
            "coord": "coordination",
        }
        return category_map.get(prefix, "race")

    def _get_injection_targets(self, pattern: Pattern, matches: list[dict]) -> list[str]:
        """Get suggested injection targets based on pattern and matches."""
        targets: list[str] = []

        # Get files from matches
        seen_files: set[str] = set()
        for match in matches:
            file_path = match.get("file", "")
            if file_path and file_path not in seen_files:
                targets.append(file_path)
                seen_files.add(file_path)

        # Add injection files from pattern definition
        if pattern.injection and pattern.injection.files:
            for file_inj in pattern.injection.files:
                if file_inj.path not in seen_files:
                    targets.append(f"(template) {file_inj.path}")

        return targets[:10]  # Limit to 10 targets
