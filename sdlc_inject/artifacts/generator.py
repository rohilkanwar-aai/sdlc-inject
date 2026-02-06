"""Base artifact generator and orchestration."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import json
import random
import uuid

from ..models import Pattern


class ArtifactGenerator(ABC):
    """Base class for artifact generators."""

    def __init__(self, pattern: Pattern, seed: int | None = None):
        self.pattern = pattern
        self.rng = random.Random(seed)
        self.base_time = datetime.now() - timedelta(hours=2)  # Incident started 2h ago

    @abstractmethod
    def generate(self) -> dict[str, Any]:
        """Generate artifacts for this tool."""
        pass

    @abstractmethod
    def save(self, output_dir: Path) -> list[Path]:
        """Save artifacts to files."""
        pass

    def random_uuid(self) -> str:
        """Generate a deterministic UUID."""
        return str(uuid.UUID(int=self.rng.getrandbits(128)))

    def random_timestamp(self, offset_minutes: int = 0, jitter_minutes: int = 5) -> str:
        """Generate a timestamp with optional jitter."""
        delta = timedelta(
            minutes=offset_minutes + self.rng.randint(-jitter_minutes, jitter_minutes)
        )
        return (self.base_time + delta).isoformat() + "Z"

    def random_choice(self, options: list[Any]) -> Any:
        """Deterministic random choice."""
        return self.rng.choice(options)


def generate_artifacts_for_pattern(
    pattern: Pattern,
    output_dir: Path,
    include: list[str] | None = None,
    seed: int | None = None,
) -> dict[str, list[Path]]:
    """Generate all artifacts for a pattern.

    Args:
        pattern: The pattern to generate artifacts for
        output_dir: Directory to write artifacts
        include: List of artifact types to include (default: all)
        seed: Random seed for reproducibility

    Returns:
        Dict mapping artifact type to list of generated files
    """
    from .sentry import SentryArtifactGenerator
    from .slack import SlackArtifactGenerator
    from .linear import LinearArtifactGenerator
    from .pagerduty import PagerDutyArtifactGenerator
    from .logs import LogArtifactGenerator
    from .metrics import MetricsArtifactGenerator
    from .github import GitHubArtifactGenerator
    from .progressive import ProgressiveIncidentGenerator

    generators = {
        "sentry": SentryArtifactGenerator,
        "slack": SlackArtifactGenerator,
        "linear": LinearArtifactGenerator,
        "pagerduty": PagerDutyArtifactGenerator,
        "logs": LogArtifactGenerator,
        "metrics": MetricsArtifactGenerator,
        "github": GitHubArtifactGenerator,
        "progressive": ProgressiveIncidentGenerator,
    }

    if include is None:
        include = list(generators.keys())

    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for name in include:
        if name not in generators:
            continue
        gen = generators[name](pattern, seed=seed)
        files = gen.save(output_dir)
        results[name] = files

    return results
