"""Pattern catalog management."""

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Pattern, TriggerCondition


class PatternCatalog:
    """Manages loading and querying patterns."""

    def __init__(self, catalog_dir: str | Path):
        self.catalog_dir = Path(catalog_dir)
        self.patterns: dict[str, Pattern] = {}
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load all patterns from the catalog directory."""
        if not self.catalog_dir.exists():
            return

        for path in self.catalog_dir.rglob("*.yaml"):
            try:
                pattern = self._parse_pattern(path)
                self.patterns[pattern.id] = pattern
            except Exception as e:
                print(f"Warning: Failed to load {path}: {e}")

        for path in self.catalog_dir.rglob("*.yml"):
            try:
                pattern = self._parse_pattern(path)
                self.patterns[pattern.id] = pattern
            except Exception as e:
                print(f"Warning: Failed to load {path}: {e}")

    def _parse_pattern(self, path: Path) -> Pattern:
        """Parse a single pattern file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Handle trigger conditions that can be strings or dicts
        if "trigger" in data and data["trigger"]:
            conditions = data["trigger"].get("conditions", [])
            data["trigger"]["conditions"] = [
                TriggerCondition.from_yaml(c).model_dump() for c in conditions
            ]

        return Pattern.model_validate(data)

    def get(self, pattern_id: str) -> Pattern | None:
        """Get a pattern by ID."""
        return self.patterns.get(pattern_id)

    def list(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        phase: str | None = None,
    ) -> list[Pattern]:
        """List patterns with optional filtering."""
        patterns = list(self.patterns.values())

        if category:
            patterns = [
                p for p in patterns
                if category.lower() in p.category.lower()
                or category.lower() in p.subcategory.lower()
            ]

        if difficulty:
            patterns = [
                p for p in patterns
                if difficulty in str(p.difficulty.estimated_human_time_hours)
                or difficulty in str(p.difficulty.frontier_model_pass_rate_percent)
            ]

        if phase:
            patterns = [
                p for p in patterns
                if phase.lower() in p.sdlc_phases.primary.lower()
                or any(phase.lower() in s.lower() for s in p.sdlc_phases.secondary)
            ]

        return sorted(patterns, key=lambda p: p.id)

    def __len__(self) -> int:
        return len(self.patterns)


def validate_pattern_file(path: Path) -> tuple[bool, str | None]:
    """Validate a single pattern file. Returns (is_valid, error_message)."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        # Handle trigger conditions
        if "trigger" in data and data["trigger"]:
            conditions = data["trigger"].get("conditions", [])
            data["trigger"]["conditions"] = [
                TriggerCondition.from_yaml(c).model_dump() for c in conditions
            ]

        pattern = Pattern.model_validate(data)

        # Additional validation
        errors = []

        # Validate ID format
        if not re.match(r"^[A-Z]+-\d+$", pattern.id):
            errors.append(f"Invalid pattern ID format: {pattern.id}")

        # Validate version format
        if not re.match(r"^\d+\.\d+(\.\d+)?$", pattern.version):
            errors.append(f"Invalid version format: {pattern.version}")

        # Validate SDLC phases
        valid_phases = {
            "debugging", "maintenance", "verification",
            "deployment", "development", "testing", "code review"
        }
        if pattern.sdlc_phases.primary.lower() not in valid_phases:
            errors.append(f"Invalid primary SDLC phase: {pattern.sdlc_phases.primary}")

        # Validate difficulty
        if pattern.difficulty.frontier_model_pass_rate_percent > 100:
            errors.append("Pass rate cannot exceed 100%")

        # Validate grading weights
        if pattern.grading:
            total = sum(c.weight for c in pattern.grading.outcome_based)
            total += sum(c.weight for c in pattern.grading.process_based)
            if abs(total - 1.0) > 0.05:
                errors.append(f"Grading weights sum to {total:.2f}, expected ~1.0")

        if errors:
            return False, "; ".join(errors)

        return True, None

    except ValidationError as e:
        return False, str(e)
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"
    except Exception as e:
        return False, str(e)


def validate_catalog(catalog_dir: Path, specific_path: Path | None = None) -> dict:
    """Validate all patterns in a catalog directory."""
    results = {
        "valid": [],
        "invalid": [],
        "total": 0,
    }

    paths = [specific_path] if specific_path else list(catalog_dir.rglob("*.yaml")) + list(catalog_dir.rglob("*.yml"))

    for path in paths:
        results["total"] += 1
        is_valid, error = validate_pattern_file(path)

        if is_valid:
            results["valid"].append(str(path))
        else:
            results["invalid"].append({"path": str(path), "error": error})

    return results
