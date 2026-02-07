"""Multi-pattern injection for complex debugging scenarios.

This module enables injecting multiple patterns into a single codebase,
creating realistic cascading failure scenarios with root causes,
contributing factors, and red herrings.
"""

import random
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from rich.console import Console

from .catalog import PatternCatalog
from .models import (
    MultiPatternConfig,
    MultiPatternEntry,
    MultiPatternGrading,
    Pattern,
)

console = Console()


class MultiPatternLoader:
    """Loads and validates multi-pattern configurations."""

    def __init__(self, configs_dir: str | Path, catalog: PatternCatalog):
        self.configs_dir = Path(configs_dir)
        self.catalog = catalog
        self.configs: dict[str, MultiPatternConfig] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all multi-pattern configs from the configs directory."""
        if not self.configs_dir.exists():
            return

        for path in self.configs_dir.glob("*.yaml"):
            try:
                config = self._parse_config(path)
                self.configs[config.id] = config
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to load {path}: {e}[/yellow]")

        for path in self.configs_dir.glob("*.yml"):
            try:
                config = self._parse_config(path)
                self.configs[config.id] = config
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to load {path}: {e}[/yellow]")

    def _parse_config(self, path: Path) -> MultiPatternConfig:
        """Parse a single multi-pattern config file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        return MultiPatternConfig.model_validate(data)

    def get(self, config_id: str) -> MultiPatternConfig | None:
        """Get a multi-pattern config by ID."""
        return self.configs.get(config_id)

    def list(self) -> list[MultiPatternConfig]:
        """List all multi-pattern configs."""
        return sorted(self.configs.values(), key=lambda c: c.id)

    def validate(self, config: MultiPatternConfig) -> tuple[bool, list[str]]:
        """Validate a multi-pattern config against the catalog."""
        errors = []

        # Check all patterns exist
        for entry in config.patterns:
            if not self.catalog.get(entry.pattern_id):
                errors.append(f"Pattern not found in catalog: {entry.pattern_id}")

        # Check root cause pattern exists in patterns list
        if config.grading:
            root_ids = [p.pattern_id for p in config.patterns]
            if config.grading.root_cause_pattern not in root_ids:
                errors.append(
                    f"Root cause pattern '{config.grading.root_cause_pattern}' "
                    "not in patterns list"
                )

            # Check partial credit patterns exist
            for pattern_id in config.grading.partial_credit:
                if pattern_id not in root_ids:
                    errors.append(
                        f"Partial credit pattern '{pattern_id}' not in patterns list"
                    )

        # Validate weights
        total_weight = sum(e.weight for e in config.patterns)
        if total_weight < 0.99 or total_weight > 2.0:
            errors.append(f"Total pattern weights ({total_weight:.2f}) seem unusual")

        return len(errors) == 0, errors


class MultiPatternInjector:
    """Orchestrates injection of multiple patterns into a codebase."""

    def __init__(
        self,
        catalog: PatternCatalog,
        seed: int | None = None,
    ):
        self.catalog = catalog
        self.rng = random.Random(seed)
        self.injected_patterns: list[str] = []

    def inject(
        self,
        config: MultiPatternConfig,
        target_dir: Path,
        output_dir: Path,
        dry_run: bool = False,
    ) -> MultiPatternResult:
        """Inject multiple patterns according to configuration.

        Args:
            config: Multi-pattern configuration
            target_dir: Source codebase directory
            output_dir: Where to write the injected codebase
            dry_run: If True, just report what would be done

        Returns:
            MultiPatternResult with details of what was injected
        """
        console.print(
            f"[bold]Multi-pattern injection: {config.name}[/bold]\n"
            f"Patterns: {len(config.patterns)}\n"
        )

        result = MultiPatternResult(
            config_id=config.id,
            config_name=config.name,
        )

        # Determine which patterns to inject based on probability
        patterns_to_inject: list[tuple[MultiPatternEntry, Pattern]] = []

        for entry in config.patterns:
            pattern = self.catalog.get(entry.pattern_id)
            if not pattern:
                console.print(
                    f"[red]Error: Pattern {entry.pattern_id} not found[/red]"
                )
                result.errors.append(f"Pattern not found: {entry.pattern_id}")
                continue

            # Check injection probability
            if self.rng.random() < entry.injection_probability:
                patterns_to_inject.append((entry, pattern))
                console.print(
                    f"  [green]✓[/green] Will inject: {pattern.id} "
                    f"(weight={entry.weight:.2f})"
                )
            else:
                console.print(
                    f"  [yellow]○[/yellow] Skipped (probability): {pattern.id}"
                )
                result.skipped.append(pattern.id)

        if dry_run:
            console.print("\n[yellow]Dry run - no changes made[/yellow]")
            result.dry_run = True
            result.would_inject = [p.id for _, p in patterns_to_inject]
            return result

        # Copy target to output
        import shutil
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(target_dir, output_dir)
        console.print(f"\n[dim]Copied {target_dir} to {output_dir}[/dim]")

        # Inject patterns in order (root cause first for determinism)
        # Sort by weight descending so root cause (weight=1.0) goes first
        patterns_to_inject.sort(key=lambda x: x[0].weight, reverse=True)

        for entry, pattern in patterns_to_inject:
            console.print(f"\n[bold]Injecting {pattern.id}...[/bold]")
            try:
                self._inject_single_pattern(pattern, output_dir)
                result.injected.append(
                    InjectedPattern(
                        pattern_id=pattern.id,
                        weight=entry.weight,
                        is_root_cause=(
                            config.grading is not None
                            and pattern.id == config.grading.root_cause_pattern
                        ),
                    )
                )
                self.injected_patterns.append(pattern.id)
            except Exception as e:
                console.print(f"[red]Failed to inject {pattern.id}: {e}[/red]")
                result.errors.append(f"Injection failed for {pattern.id}: {e}")

        # Generate combined grading info
        if config.grading:
            result.grading_info = self._build_grading_info(config, result.injected)

        console.print(f"\n[green]Multi-pattern injection complete[/green]")
        console.print(f"  Injected: {len(result.injected)}")
        console.print(f"  Skipped: {len(result.skipped)}")
        console.print(f"  Errors: {len(result.errors)}")

        return result

    def _inject_single_pattern(self, pattern: Pattern, output_dir: Path) -> None:
        """Inject a single pattern into the codebase."""
        # Check if pattern has v1.0 codebase-specific injection
        if pattern.injection and pattern.injection.files:
            self._inject_v1(pattern, output_dir)
        # Check if pattern has v2.0 template-based injection
        elif pattern.injection_template:
            self._inject_v2(pattern, output_dir)
        else:
            raise ValueError(f"Pattern {pattern.id} has no injection configuration")

    def _inject_v1(self, pattern: Pattern, output_dir: Path) -> None:
        """Apply v1.0 codebase-specific injection."""
        from .injection import apply_patch, apply_config_change

        for file_inj in pattern.injection.files:
            target_path = output_dir / file_inj.path

            if not target_path.exists():
                console.print(
                    f"  [yellow]Skipping (not found): {file_inj.path}[/yellow]"
                )
                continue

            console.print(f"  [green]Patching:[/green] {file_inj.path}")
            content = target_path.read_text()
            for patch in file_inj.patches:
                try:
                    content = apply_patch(content, patch)
                except ValueError as e:
                    console.print(f"    [yellow]Patch failed: {e}[/yellow]")
            target_path.write_text(content)

        for config_change in pattern.injection.config_changes:
            config_path = output_dir / config_change.file
            if not config_path.exists():
                continue
            console.print(f"  [green]Config:[/green] {config_change.file}")
            content = config_path.read_text()
            for change in config_change.changes:
                try:
                    content = apply_config_change(content, change)
                except ValueError as e:
                    console.print(f"    [yellow]Config change failed: {e}[/yellow]")
            config_path.write_text(content)

    def _inject_v2(self, pattern: Pattern, output_dir: Path) -> None:
        """Apply v2.0 template-based injection using pattern matching."""
        import re
        import fnmatch

        template = pattern.injection_template

        # Detect language from file extensions
        detected_langs = self._detect_languages(output_dir)
        console.print(f"  [dim]Detected languages: {detected_langs}[/dim]")

        for lang in detected_langs:
            lang_injection = getattr(template, lang, None)
            if not lang_injection:
                continue

            console.print(f"  [cyan]Processing {lang} files...[/cyan]")

            # Find matching files
            for file_pattern in lang_injection.file_patterns:
                for file_path in output_dir.rglob("*"):
                    if not file_path.is_file():
                        continue

                    # Check if file matches pattern
                    rel_path = str(file_path.relative_to(output_dir))
                    if not fnmatch.fnmatch(rel_path, file_pattern):
                        continue

                    # Try to find and inject pattern
                    content = file_path.read_text()
                    match = re.search(lang_injection.target_pattern, content)

                    if match:
                        console.print(
                            f"    [green]Match found:[/green] {rel_path}"
                        )

                        # Build injection code with named group substitution
                        injection_code = lang_injection.injection_code
                        for name, value in match.groupdict().items():
                            if value:
                                injection_code = injection_code.replace(
                                    f"{{{name}}}", value
                                )

                        # Insert after the matched line
                        match_end = content.find("\n", match.end())
                        if match_end == -1:
                            match_end = len(content)

                        new_content = (
                            content[: match_end + 1]
                            + injection_code
                            + content[match_end + 1 :]
                        )

                        file_path.write_text(new_content)
                        console.print(f"    [green]Injected code[/green]")

    def _detect_languages(self, directory: Path) -> list[str]:
        """Detect programming languages used in a directory."""
        extensions = {
            ".rs": "rust",
            ".py": "python",
            ".go": "go",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".java": "java",
        }

        detected = set()
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in extensions:
                    detected.add(extensions[ext])

        return list(detected)

    def _build_grading_info(
        self,
        config: MultiPatternConfig,
        injected: list["InjectedPattern"],
    ) -> dict[str, Any]:
        """Build combined grading information for multi-pattern scenario."""
        grading_info = {
            "root_cause": config.grading.root_cause_pattern,
            "total_patterns": len(injected),
            "scoring": {
                "root_cause_identification": 0.5,  # 50% for finding root cause
                "contributing_factors": {},
                "red_herrings_avoided": 0.1,  # 10% for not blaming red herrings
            },
        }

        # Add partial credit scoring
        for pattern in injected:
            if pattern.pattern_id == config.grading.root_cause_pattern:
                continue

            credit = config.grading.partial_credit.get(pattern.pattern_id, 0.0)
            if credit > 0:
                grading_info["scoring"]["contributing_factors"][
                    pattern.pattern_id
                ] = credit

        return grading_info


class InjectedPattern:
    """Information about an injected pattern."""

    def __init__(
        self,
        pattern_id: str,
        weight: float,
        is_root_cause: bool = False,
    ):
        self.pattern_id = pattern_id
        self.weight = weight
        self.is_root_cause = is_root_cause

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "weight": self.weight,
            "is_root_cause": self.is_root_cause,
        }


class MultiPatternResult:
    """Result of a multi-pattern injection."""

    def __init__(
        self,
        config_id: str,
        config_name: str,
    ):
        self.config_id = config_id
        self.config_name = config_name
        self.injected: list[InjectedPattern] = []
        self.skipped: list[str] = []
        self.errors: list[str] = []
        self.dry_run: bool = False
        self.would_inject: list[str] = []
        self.grading_info: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "config_name": self.config_name,
            "injected": [p.to_dict() for p in self.injected],
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "would_inject": self.would_inject,
            "grading_info": self.grading_info,
        }

    @property
    def success(self) -> bool:
        """Check if injection was successful (at least one pattern injected)."""
        return len(self.injected) > 0 and len(self.errors) == 0


def create_multi_pattern_config(
    config_id: str,
    name: str,
    pattern_ids: list[str],
    root_cause_id: str,
    partial_credit: dict[str, float] | None = None,
    description: str | None = None,
) -> MultiPatternConfig:
    """Helper to create a multi-pattern configuration programmatically.

    Args:
        config_id: Unique identifier for this config (e.g., "COMPLEX-001")
        name: Human-readable name
        pattern_ids: List of pattern IDs to include
        root_cause_id: Pattern ID that is the actual root cause
        partial_credit: Optional dict of pattern_id -> credit for contributing factors
        description: Optional description

    Returns:
        MultiPatternConfig ready for use
    """
    entries = []
    for pid in pattern_ids:
        weight = 1.0 if pid == root_cause_id else 0.5
        entries.append(
            MultiPatternEntry(
                pattern_id=pid,
                weight=weight,
                hints_enabled=True,
                injection_probability=1.0,
            )
        )

    grading = MultiPatternGrading(
        root_cause_pattern=root_cause_id,
        partial_credit=partial_credit or {},
    )

    return MultiPatternConfig(
        id=config_id,
        name=name,
        description=description,
        patterns=entries,
        grading=grading,
    )
