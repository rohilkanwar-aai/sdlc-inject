"""Analytics pipeline for evaluating agent trajectories."""

from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
from collections import Counter
from typing import Any

from .trajectory import AgentTrajectory, Outcome, FailureModeType


@dataclass
class FailureModeAnalysis:
    """Analysis of a specific failure mode."""
    mode: FailureModeType
    count: int
    frequency: float                    # As fraction of failures
    example_trajectory_ids: list[str]
    common_patterns: list[str]          # Common tool sequences or behaviors


@dataclass
class AnalyticsResult:
    """Complete analytics result for an evaluation run."""

    # Metadata
    pattern_id: str
    run_id: str
    num_trajectories: int
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    # Core metrics
    pass_rate: float = 0.0
    pass_rate_ci_lower: float = 0.0     # 95% CI lower bound
    pass_rate_ci_upper: float = 0.0     # 95% CI upper bound
    partial_rate: float = 0.0           # Partial success rate

    # Time analysis
    median_time_success: float = 0.0    # seconds
    median_time_failure: float = 0.0
    mean_time_success: float = 0.0
    mean_time_failure: float = 0.0

    # Failure analysis
    failure_modes: list[FailureModeAnalysis] = field(default_factory=list)
    most_common_failure: str = ""

    # Process analysis
    root_cause_identified_rate: float = 0.0
    avg_files_read_success: float = 0.0
    avg_files_read_failure: float = 0.0
    avg_tool_calls_success: float = 0.0
    avg_tool_calls_failure: float = 0.0

    # Tool usage
    tool_usage_frequency: dict[str, int] = field(default_factory=dict)
    common_success_sequences: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "run_id": self.run_id,
            "num_trajectories": self.num_trajectories,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "summary": {
                "pass_rate": round(self.pass_rate, 3),
                "pass_rate_ci_95": [round(self.pass_rate_ci_lower, 3), round(self.pass_rate_ci_upper, 3)],
                "partial_rate": round(self.partial_rate, 3),
                "root_cause_identified_rate": round(self.root_cause_identified_rate, 3),
            },
            "time_analysis": {
                "median_time_success_seconds": round(self.median_time_success, 1),
                "median_time_failure_seconds": round(self.median_time_failure, 1),
                "mean_time_success_seconds": round(self.mean_time_success, 1),
                "mean_time_failure_seconds": round(self.mean_time_failure, 1),
            },
            "process_analysis": {
                "avg_files_read_success": round(self.avg_files_read_success, 1),
                "avg_files_read_failure": round(self.avg_files_read_failure, 1),
                "avg_tool_calls_success": round(self.avg_tool_calls_success, 1),
                "avg_tool_calls_failure": round(self.avg_tool_calls_failure, 1),
            },
            "failure_modes": [
                {
                    "mode": fm.mode.value,
                    "count": fm.count,
                    "frequency": round(fm.frequency, 3),
                    "example_trajectory_ids": fm.example_trajectory_ids[:3],
                    "common_patterns": fm.common_patterns[:5],
                }
                for fm in self.failure_modes
            ],
            "tool_usage": self.tool_usage_frequency,
            "common_success_sequences": self.common_success_sequences[:5],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# Evaluation Report: {self.pattern_id}",
            "",
            f"**Run ID:** {self.run_id}",
            f"**Trajectories Analyzed:** {self.num_trajectories}",
            f"**Analysis Date:** {self.analysis_timestamp.strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Pass Rate | {self.pass_rate*100:.1f}% (95% CI: {self.pass_rate_ci_lower*100:.1f}%-{self.pass_rate_ci_upper*100:.1f}%) |",
            f"| Partial Success | {self.partial_rate*100:.1f}% |",
            f"| Root Cause Identified | {self.root_cause_identified_rate*100:.1f}% |",
            "",
            "## Time Analysis",
            "",
            f"| Outcome | Median Time | Mean Time |",
            f"|---------|-------------|-----------|",
            f"| Success | {self.median_time_success/60:.1f} min | {self.mean_time_success/60:.1f} min |",
            f"| Failure | {self.median_time_failure/60:.1f} min | {self.mean_time_failure/60:.1f} min |",
            "",
            "## Failure Modes",
            "",
        ]

        if self.failure_modes:
            lines.append("| Mode | Count | Frequency |")
            lines.append("|------|-------|-----------|")
            for fm in self.failure_modes:
                lines.append(f"| {fm.mode.value} | {fm.count} | {fm.frequency*100:.1f}% |")
        else:
            lines.append("No failures to analyze.")

        lines.extend([
            "",
            "## Process Analysis",
            "",
            f"| Metric | Success | Failure |",
            f"|--------|---------|---------|",
            f"| Avg Files Read | {self.avg_files_read_success:.1f} | {self.avg_files_read_failure:.1f} |",
            f"| Avg Tool Calls | {self.avg_tool_calls_success:.1f} | {self.avg_tool_calls_failure:.1f} |",
        ])

        return "\n".join(lines)


class AnalyticsPipeline:
    """Pipeline for analyzing agent trajectories."""

    def __init__(self):
        pass

    def analyze(
        self,
        trajectories: list[AgentTrajectory],
        pattern_id: str,
        run_id: str,
    ) -> AnalyticsResult:
        """
        Analyze a set of trajectories and compute metrics.

        Args:
            trajectories: List of agent trajectories to analyze
            pattern_id: ID of the pattern being evaluated
            run_id: ID of the evaluation run

        Returns:
            AnalyticsResult with computed metrics
        """
        if not trajectories:
            return AnalyticsResult(
                pattern_id=pattern_id,
                run_id=run_id,
                num_trajectories=0,
            )

        result = AnalyticsResult(
            pattern_id=pattern_id,
            run_id=run_id,
            num_trajectories=len(trajectories),
        )

        # Separate successes and failures
        successes = [t for t in trajectories if t.outcome == Outcome.SUCCESS]
        partials = [t for t in trajectories if t.outcome == Outcome.PARTIAL]
        failures = [t for t in trajectories if t.outcome in [Outcome.FAILURE, Outcome.TIMEOUT, Outcome.ERROR]]

        # Core metrics
        result.pass_rate = len(successes) / len(trajectories)
        result.partial_rate = len(partials) / len(trajectories)

        # 95% confidence interval using Wilson score
        result.pass_rate_ci_lower, result.pass_rate_ci_upper = self._wilson_ci(
            len(successes), len(trajectories)
        )

        # Time analysis
        success_times = [t.duration_seconds for t in successes if t.duration_seconds > 0]
        failure_times = [t.duration_seconds for t in failures if t.duration_seconds > 0]

        if success_times:
            result.median_time_success = self._median(success_times)
            result.mean_time_success = sum(success_times) / len(success_times)

        if failure_times:
            result.median_time_failure = self._median(failure_times)
            result.mean_time_failure = sum(failure_times) / len(failure_times)

        # Root cause identification rate
        identified = [t for t in trajectories if t.root_cause_identified]
        result.root_cause_identified_rate = len(identified) / len(trajectories)

        # Process metrics
        if successes:
            result.avg_files_read_success = sum(t.num_file_reads for t in successes) / len(successes)
            result.avg_tool_calls_success = sum(t.num_tool_calls for t in successes) / len(successes)

        if failures:
            result.avg_files_read_failure = sum(t.num_file_reads for t in failures) / len(failures)
            result.avg_tool_calls_failure = sum(t.num_tool_calls for t in failures) / len(failures)

        # Tool usage
        tool_counter: Counter[str] = Counter()
        for t in trajectories:
            for tc in t.tool_calls:
                tool_counter[tc.tool_name] += 1
        result.tool_usage_frequency = dict(tool_counter.most_common(20))

        # Failure mode analysis
        result.failure_modes = self._analyze_failure_modes(failures)
        if result.failure_modes:
            result.most_common_failure = result.failure_modes[0].mode.value

        # Common success sequences
        result.common_success_sequences = self._extract_common_sequences(successes)

        return result

    def _wilson_ci(self, successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
        """Calculate Wilson score 95% confidence interval."""
        if total == 0:
            return 0.0, 0.0

        p = successes / total
        denominator = 1 + z**2 / total
        center = (p + z**2 / (2 * total)) / denominator
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator

        return max(0, center - spread), min(1, center + spread)

    def _median(self, values: list[float]) -> float:
        """Calculate median of a list."""
        sorted_values = sorted(values)
        n = len(sorted_values)
        if n == 0:
            return 0.0
        if n % 2 == 1:
            return sorted_values[n // 2]
        return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2

    def _analyze_failure_modes(self, failures: list[AgentTrajectory]) -> list[FailureModeAnalysis]:
        """Cluster failures into modes."""
        if not failures:
            return []

        mode_groups: dict[FailureModeType, list[AgentTrajectory]] = {}

        for t in failures:
            mode = t.failure_mode or self._classify_failure_mode(t)
            if mode not in mode_groups:
                mode_groups[mode] = []
            mode_groups[mode].append(t)

        analyses = []
        total_failures = len(failures)

        for mode, trajectories in sorted(mode_groups.items(), key=lambda x: -len(x[1])):
            analyses.append(FailureModeAnalysis(
                mode=mode,
                count=len(trajectories),
                frequency=len(trajectories) / total_failures,
                example_trajectory_ids=[t.trajectory_id for t in trajectories[:5]],
                common_patterns=self._extract_common_patterns(trajectories),
            ))

        return analyses

    def _classify_failure_mode(self, trajectory: AgentTrajectory) -> FailureModeType:
        """Classify a trajectory's failure mode based on heuristics."""
        # Check for symptom chasing (timeout/retry changes)
        symptom_keywords = ["timeout", "retry", "sleep", "delay", "increase", "pool_size"]
        for fc in trajectory.file_changes:
            if fc.diff:
                diff_lower = fc.diff.lower()
                if any(kw in diff_lower for kw in symptom_keywords):
                    return FailureModeType.SYMPTOM_CHASING

        # Check if they gave up (no file changes, no conclusion)
        if not trajectory.file_changes and trajectory.num_tool_calls < 5:
            return FailureModeType.GAVE_UP

        # Check for partial fix (some changes but tests still fail)
        if trajectory.file_changes and trajectory.tests_passed_after is False:
            return FailureModeType.PARTIAL_FIX

        # Default to unknown
        return FailureModeType.UNKNOWN

    def _extract_common_patterns(self, trajectories: list[AgentTrajectory]) -> list[str]:
        """Extract common patterns from failed trajectories."""
        patterns: Counter[str] = Counter()

        for t in trajectories:
            # Look at file changes
            for fc in t.file_changes:
                if fc.diff:
                    # Extract key changes
                    for line in fc.diff.split("\n"):
                        if line.startswith("+") and not line.startswith("+++"):
                            # Simple pattern extraction
                            line_clean = line[1:].strip()[:50]
                            if line_clean:
                                patterns[f"add: {line_clean}"] += 1

            # Look at commands run
            for cmd in t.commands_run[:10]:
                patterns[f"cmd: {cmd[:30]}"] += 1

        return [p for p, _ in patterns.most_common(5)]

    def _extract_common_sequences(self, successes: list[AgentTrajectory]) -> list[list[str]]:
        """Extract common tool sequences from successful trajectories."""
        if not successes:
            return []

        # Get first N tool calls from each success
        sequences = []
        for t in successes:
            seq = [tc.tool_name for tc in t.tool_calls[:10]]
            if seq:
                sequences.append(seq)

        # Return most common (simple approach - just return first few)
        return sequences[:3]


def load_trajectories(path: Path) -> list[AgentTrajectory]:
    """Load trajectories from a directory or file."""
    trajectories = []

    if path.is_file():
        with open(path) as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    trajectories.append(AgentTrajectory.from_dict(item))
            else:
                trajectories.append(AgentTrajectory.from_dict(data))

    elif path.is_dir():
        for file_path in path.glob("*.json"):
            with open(file_path) as f:
                data = json.load(f)
                trajectories.append(AgentTrajectory.from_dict(data))

    return trajectories


def analyze_trajectories(
    trajectories_path: Path,
    pattern_id: str,
    run_id: str,
    output_path: Path | None = None,
) -> AnalyticsResult:
    """
    Load and analyze trajectories.

    Args:
        trajectories_path: Path to trajectories (file or directory)
        pattern_id: Pattern ID
        run_id: Run ID
        output_path: Optional path to write results

    Returns:
        AnalyticsResult
    """
    trajectories = load_trajectories(trajectories_path)
    pipeline = AnalyticsPipeline()
    result = pipeline.analyze(trajectories, pattern_id, run_id)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == ".md":
            with open(output_path, "w") as f:
                f.write(result.to_markdown())
        else:
            with open(output_path, "w") as f:
                f.write(result.to_json())

    return result
