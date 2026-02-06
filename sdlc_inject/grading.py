"""Grading infrastructure generation and trajectory evaluation."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from .models import Pattern

console = Console()


def generate_grading_setup(pattern: Pattern, target_dir: Path, output_dir: Path) -> None:
    """Generate grading infrastructure for a pattern."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate verification scripts
    scripts_dir = output_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)

    generate_verification_script(pattern, scripts_dir)
    generate_process_criteria(pattern, scripts_dir)

    # Generate rubric
    generate_rubric(pattern, output_dir)

    # Generate test harness
    generate_test_harness(pattern, target_dir, output_dir)

    # Generate report template
    generate_report_template(pattern, output_dir)


def generate_verification_script(pattern: Pattern, scripts_dir: Path) -> None:
    """Generate outcome verification script."""
    script = f"""#!/bin/bash
# Outcome verification for {pattern.id}

set -e
RESULT=0

"""

    if pattern.grading:
        for i, criterion in enumerate(pattern.grading.outcome_based, 1):
            script += f'# Criterion {i}: {criterion.criterion}\n'
            script += f'echo "Checking: {criterion.criterion}"\n'

            if criterion.verification and criterion.verification.command:
                script += f'if {criterion.verification.command}; then\n'
                script += '  echo "  PASS"\n'
                script += 'else\n'
                script += '  echo "  FAIL"\n'
                script += '  RESULT=1\n'
                script += 'fi\n\n'
            else:
                script += 'echo "  MANUAL CHECK REQUIRED"\n\n'

    script += 'exit $RESULT\n'

    script_path = scripts_dir / "verify_outcome.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)


def generate_process_criteria(pattern: Pattern, scripts_dir: Path) -> None:
    """Generate process criteria documentation."""
    content = f"# Process-based criteria for {pattern.id}\n\n"

    if pattern.grading:
        for criterion in pattern.grading.process_based:
            content += f"## {criterion.criterion} (weight: {criterion.weight*100:.0f}%)\n"
            if criterion.evidence:
                content += f"Evidence to look for: {criterion.evidence}\n"
            for ep in criterion.evidence_patterns:
                content += f"- Pattern: `{ep}`\n"
            content += "\n"

    (scripts_dir / "process_criteria.md").write_text(content)


def generate_rubric(pattern: Pattern, output_dir: Path) -> None:
    """Generate grading rubric YAML."""
    rubric = {
        "pattern_id": pattern.id,
        "pattern_name": pattern.name,
        "total_points": 100,
        "outcome_criteria": [],
        "process_criteria": [],
    }

    if pattern.grading:
        for c in pattern.grading.outcome_based:
            rubric["outcome_criteria"].append({
                "criterion": c.criterion,
                "points": int(c.weight * 100),
                "weight": c.weight,
                "verification_type": c.verification.type if c.verification else None,
                "evidence_patterns": c.evidence_patterns,
            })

        for c in pattern.grading.process_based:
            rubric["process_criteria"].append({
                "criterion": c.criterion,
                "points": int(c.weight * 100),
                "weight": c.weight,
                "evidence_patterns": c.evidence_patterns,
            })

    (output_dir / "rubric.yaml").write_text(yaml.dump(rubric, default_flow_style=False))


def generate_test_harness(pattern: Pattern, target_dir: Path, output_dir: Path) -> None:
    """Generate test harness for grading."""
    harness_dir = output_dir / "harness"
    harness_dir.mkdir(exist_ok=True)

    # Docker Compose
    compose = f"""version: '3.8'

services:
  test-runner:
    build:
      context: {target_dir}
      dockerfile: Dockerfile
    volumes:
      - ./results:/results
    environment:
      - PATTERN_ID={pattern.id}
      - TARGET_DIR=/app
    command: /scripts/run_tests.sh
"""
    (harness_dir / "docker-compose.yaml").write_text(compose)

    # Test runner script
    runner = f"""#!/bin/bash
# Test runner for {pattern.id}

echo "Running tests for pattern: {pattern.id}"
echo "================================"

cd /app

# Run outcome verification
echo "Running outcome verification..."
/scripts/verify_outcome.sh
OUTCOME_RESULT=$?

# Save results
echo '{{"pattern_id": "{pattern.id}", "outcome_pass": '$OUTCOME_RESULT'}}' > /results/results.json

echo "Tests complete."
"""
    runner_path = harness_dir / "run_tests.sh"
    runner_path.write_text(runner)
    runner_path.chmod(0o755)


def generate_report_template(pattern: Pattern, output_dir: Path) -> None:
    """Generate markdown report template."""
    outcome_rows = ""
    process_rows = ""
    outcome_total = 0
    process_total = 0

    if pattern.grading:
        for c in pattern.grading.outcome_based:
            outcome_rows += f"| {c.criterion} | {c.weight*100:.0f} | | |\n"
            outcome_total += int(c.weight * 100)

        for c in pattern.grading.process_based:
            process_rows += f"| {c.criterion} | {c.weight*100:.0f} | | |\n"
            process_total += int(c.weight * 100)

    template = f"""# Grading Report: {pattern.id}

## Pattern Information
- **ID:** {pattern.id}
- **Name:** {pattern.name}
- **Category:** {pattern.category}
- **Difficulty:** {pattern.difficulty.estimated_human_time_hours} hours, {pattern.difficulty.frontier_model_pass_rate_percent}% pass rate

## Outcome Assessment

| Criterion | Points | Score | Notes |
|-----------|--------|-------|-------|
{outcome_rows}

## Process Assessment

| Criterion | Points | Score | Evidence |
|-----------|--------|-------|----------|
{process_rows}

## Total Score

| Category | Points | Score |
|----------|--------|-------|
| Outcome-based | {outcome_total} | |
| Process-based | {process_total} | |
| **Total** | 100 | |

## Notes

(Add evaluator notes here)

## Trajectory Summary

(Summarize the agent's approach)
"""
    (output_dir / "report_template.md").write_text(template)


def evaluate_trajectory(
    pattern: Pattern,
    trajectory_path: Path,
    environment_state: Path | None = None,
) -> dict[str, Any]:
    """Evaluate an agent's trajectory against a pattern."""
    # Load trajectory
    trajectory = load_trajectory(trajectory_path)

    # Evaluate outcomes
    outcome_results = evaluate_outcomes(pattern, environment_state)

    # Evaluate process
    process_results = evaluate_process(pattern, trajectory)

    # Calculate totals
    outcome_score = sum(r["score"] * r["weight"] for r in outcome_results)
    process_score = sum(r["score"] * r["weight"] for r in process_results)

    return {
        "pattern_id": pattern.id,
        "pattern_name": pattern.name,
        "total_score": outcome_score + process_score,
        "outcome_score": outcome_score,
        "process_score": process_score,
        "outcome_results": outcome_results,
        "process_results": process_results,
    }


def load_trajectory(path: Path) -> dict:
    """Load trajectory from file."""
    content = path.read_text()

    # Try JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        pass

    # Try JSONL
    messages = []
    for line in content.strip().split("\n"):
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if messages:
        return {"messages": messages, "actions": []}

    raise ValueError(f"Could not parse trajectory file: {path}")


def evaluate_outcomes(pattern: Pattern, environment_state: Path | None) -> list[dict]:
    """Evaluate outcome-based criteria."""
    results = []

    if not pattern.grading:
        return results

    for criterion in pattern.grading.outcome_based:
        result = {
            "criterion": criterion.criterion,
            "weight": criterion.weight,
            "score": 0.0,
            "evidence": None,
            "notes": None,
        }

        if environment_state and criterion.verification:
            if criterion.verification.command:
                try:
                    proc = subprocess.run(
                        criterion.verification.command,
                        shell=True,
                        cwd=environment_state,
                        capture_output=True,
                        text=True,
                        timeout=criterion.verification.timeout_seconds or 30,
                    )
                    expected = criterion.verification.expected_exit_code or 0
                    if proc.returncode == expected:
                        result["score"] = 1.0
                        result["evidence"] = proc.stdout[:500]
                    else:
                        result["notes"] = proc.stderr[:500]
                except subprocess.TimeoutExpired:
                    result["notes"] = "Command timed out"
                except Exception as e:
                    result["notes"] = str(e)
            else:
                result["notes"] = "Manual verification required"
        else:
            result["notes"] = "Environment state not provided"

        results.append(result)

    return results


def evaluate_process(pattern: Pattern, trajectory: dict) -> list[dict]:
    """Evaluate process-based criteria from trajectory."""
    results = []

    if not pattern.grading:
        return results

    # Combine all trajectory content
    all_content = ""
    for msg in trajectory.get("messages", []):
        if isinstance(msg, dict):
            all_content += msg.get("content", "") + "\n"
        elif isinstance(msg, str):
            all_content += msg + "\n"

    for action in trajectory.get("actions", []):
        if isinstance(action, dict):
            all_content += action.get("content", "") + "\n"

    all_content = all_content.lower()

    for criterion in pattern.grading.process_based:
        result = {
            "criterion": criterion.criterion,
            "weight": criterion.weight,
            "score": 0.0,
            "evidence": None,
        }

        evidence = []

        # Check evidence patterns
        for ep in criterion.evidence_patterns:
            if ep.lower() in all_content:
                result["score"] = 1.0
                evidence.append(f"Found: {ep}")

        # Check evidence string
        if criterion.evidence and criterion.evidence.lower() in all_content:
            result["score"] = 1.0
            evidence.append(f"Found: {criterion.evidence}")

        if evidence:
            result["evidence"] = "; ".join(evidence)

        results.append(result)

    return results
