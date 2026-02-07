"""CLI commands for sdlc-inject."""

import json
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    import os
    # Always try package directory first (most reliable location)
    package_dir = Path(__file__).parent.parent
    env_file = package_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)  # Don't override if already set
    # Also try current directory (for user convenience)
    load_dotenv(override=False)  # Don't override if already set from package dir
except ImportError:
    # python-dotenv not installed, skip loading .env
    pass

from .catalog import PatternCatalog, validate_catalog
from .injection import inject_pattern
from .multi_pattern import MultiPatternLoader, MultiPatternInjector
from .grading import generate_grading_setup, evaluate_trajectory
from .environment import generate_environment
from .artifacts import generate_artifacts_for_pattern
from .analyzer import CodebaseAnalyzer, NeuralCodeAnalyzer
from .enricher import PatternUpdater

console = Console()


@click.group()
@click.option("--catalog-dir", default="./patterns", help="Pattern catalog directory")
@click.pass_context
def main(ctx: click.Context, catalog_dir: str) -> None:
    """SDLC Inject - Inject failure patterns into codebases for training."""
    ctx.ensure_object(dict)
    ctx.obj["catalog_dir"] = catalog_dir
    ctx.obj["catalog"] = PatternCatalog(catalog_dir)


@main.command("list")
@click.option("-c", "--category", help="Filter by category")
@click.option("-d", "--difficulty", help="Filter by difficulty")
@click.option("--phase", help="Filter by SDLC phase")
@click.option("-f", "--format", "fmt", default="table", help="Output format (table, json, yaml)")
@click.pass_context
def list_patterns(ctx: click.Context, category: str | None, difficulty: str | None, phase: str | None, fmt: str) -> None:
    """List available patterns."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    patterns = catalog.list(category=category, difficulty=difficulty, phase=phase)

    if not patterns:
        console.print("[yellow]No patterns found matching filters.[/yellow]")
        return

    if fmt == "json":
        data = [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "subcategory": p.subcategory,
                "phase": p.sdlc_phases.primary,
                "hours": p.difficulty.estimated_human_time_hours,
                "pass_rate": p.difficulty.frontier_model_pass_rate_percent,
                "tags": p.tags,
            }
            for p in patterns
        ]
        console.print(json.dumps(data, indent=2))

    elif fmt == "yaml":
        data = [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "difficulty": {
                    "hours": p.difficulty.estimated_human_time_hours,
                    "pass_rate": p.difficulty.frontier_model_pass_rate_percent,
                },
            }
            for p in patterns
        ]
        console.print(yaml.dump(data, default_flow_style=False))

    else:  # table
        table = Table(title=f"Patterns ({len(patterns)} total)")
        table.add_column("ID", style="cyan")
        table.add_column("Name", max_width=40)
        table.add_column("Category", max_width=20)
        table.add_column("Hours", justify="right")
        table.add_column("Pass%", justify="right")

        for p in patterns:
            rate = p.difficulty.frontier_model_pass_rate_percent
            rate_style = "green" if rate >= 40 else "yellow" if rate >= 20 else "red"

            table.add_row(
                p.id,
                p.name[:38] + "..." if len(p.name) > 40 else p.name,
                p.subcategory[:18] + "..." if len(p.subcategory) > 20 else p.subcategory,
                f"{p.difficulty.estimated_human_time_hours:.1f}",
                f"[{rate_style}]{rate}%[/{rate_style}]",
            )

        console.print(table)


@main.command("show")
@click.argument("pattern_id")
@click.option("-f", "--format", "fmt", default="yaml", help="Output format (yaml, json, markdown)")
@click.pass_context
def show_pattern(ctx: click.Context, pattern_id: str, fmt: str) -> None:
    """Show details of a specific pattern."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    if fmt == "json":
        console.print(json.dumps(pattern.model_dump(by_alias=True), indent=2))

    elif fmt == "yaml":
        console.print(yaml.dump(pattern.model_dump(by_alias=True), default_flow_style=False, sort_keys=False))

    else:  # markdown
        console.print(f"# {pattern.id} - {pattern.name}\n")
        console.print(f"**Category:** {pattern.category} / {pattern.subcategory}")
        console.print(f"**SDLC Phase:** {pattern.sdlc_phases.primary}")
        console.print(f"**Version:** {pattern.version}\n")

        console.print("## Description\n")
        console.print(pattern.description)

        if pattern.target_codebase:
            console.print("\n## Target Codebase\n")
            console.print(f"- **Name:** {pattern.target_codebase.name}")
            if pattern.target_codebase.min_version:
                console.print(f"- **Min Version:** {pattern.target_codebase.min_version}")
            if pattern.target_codebase.language:
                console.print(f"- **Language:** {pattern.target_codebase.language}")

        console.print("\n## Difficulty\n")
        console.print(f"- **Estimated Time:** {pattern.difficulty.estimated_human_time_hours} hours")
        console.print(f"- **Model Pass Rate:** {pattern.difficulty.frontier_model_pass_rate_percent}%")

        if pattern.golden_path:
            console.print("\n## Golden Path\n")
            for step in pattern.golden_path.steps:
                console.print(f"{step.step}. {step.action}")
                if step.key_insight:
                    console.print(f"   > Key insight: {step.key_insight}")

        if pattern.grading:
            console.print("\n## Grading\n")
            console.print("### Outcome-based")
            for c in pattern.grading.outcome_based:
                console.print(f"- {c.criterion} ({c.weight*100:.0f}%)")
            console.print("\n### Process-based")
            for c in pattern.grading.process_based:
                console.print(f"- {c.criterion} ({c.weight*100:.0f}%)")

        if pattern.tags:
            console.print(f"\n## Tags\n\n{', '.join(f'`{t}`' for t in pattern.tags)}")


@main.command("inject")
@click.argument("pattern_id")
@click.option("-t", "--target", required=True, help="Target codebase directory")
@click.option("-o", "--output", required=True, help="Output directory")
@click.option("--obfuscation", default="medium", help="Obfuscation level (none, low, medium, high)")
@click.option("--commit/--no-commit", default=False, help="Create git commits")
@click.option("--dry-run", is_flag=True, help="Show what would be changed")
@click.pass_context
def inject(ctx: click.Context, pattern_id: str, target: str, output: str, obfuscation: str, commit: bool, dry_run: bool) -> None:
    """Inject a pattern into a target codebase."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    inject_pattern(
        pattern=pattern,
        target_dir=Path(target),
        output_dir=Path(output),
        obfuscation_level=obfuscation,
        create_commits=commit,
        dry_run=dry_run,
    )


# =============================================================================
# Multi-Pattern Commands
# =============================================================================


@main.command("multi-list")
@click.option("--configs-dir", default="./injection_configs", help="Multi-pattern configs directory")
@click.option("-f", "--format", "fmt", default="table", help="Output format (table, json, yaml)")
@click.pass_context
def multi_list(ctx: click.Context, configs_dir: str, fmt: str) -> None:
    """List available multi-pattern configurations."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    loader = MultiPatternLoader(configs_dir, catalog)

    configs = loader.list()

    if not configs:
        console.print("[yellow]No multi-pattern configurations found.[/yellow]")
        console.print(f"[dim]Looked in: {configs_dir}[/dim]")
        return

    if fmt == "json":
        data = [
            {
                "id": c.id,
                "name": c.name,
                "patterns": [p.pattern_id for p in c.patterns],
                "root_cause": c.grading.root_cause_pattern if c.grading else None,
                "difficulty_multiplier": c.total_difficulty_multiplier,
                "estimated_hours": c.estimated_human_time_hours,
            }
            for c in configs
        ]
        console.print(json.dumps(data, indent=2))

    elif fmt == "yaml":
        data = [
            {
                "id": c.id,
                "name": c.name,
                "patterns": len(c.patterns),
                "root_cause": c.grading.root_cause_pattern if c.grading else None,
            }
            for c in configs
        ]
        console.print(yaml.dump(data, default_flow_style=False))

    else:  # table
        table = Table(title=f"Multi-Pattern Configs ({len(configs)} total)")
        table.add_column("ID", style="cyan")
        table.add_column("Name", max_width=35)
        table.add_column("Patterns", justify="right")
        table.add_column("Root Cause", style="yellow")
        table.add_column("Hours", justify="right")

        for c in configs:
            root_cause = c.grading.root_cause_pattern if c.grading else "-"
            hours = f"{c.estimated_human_time_hours:.1f}" if c.estimated_human_time_hours else "-"

            table.add_row(
                c.id,
                c.name[:33] + "..." if len(c.name) > 35 else c.name,
                str(len(c.patterns)),
                root_cause,
                hours,
            )

        console.print(table)


@main.command("multi-show")
@click.argument("config_id")
@click.option("--configs-dir", default="./injection_configs", help="Multi-pattern configs directory")
@click.option("-f", "--format", "fmt", default="yaml", help="Output format (yaml, json, markdown)")
@click.pass_context
def multi_show(ctx: click.Context, config_id: str, configs_dir: str, fmt: str) -> None:
    """Show details of a multi-pattern configuration."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    loader = MultiPatternLoader(configs_dir, catalog)
    config = loader.get(config_id)

    if not config:
        console.print(f"[red]Multi-pattern config not found: {config_id}[/red]")
        raise SystemExit(1)

    if fmt == "json":
        console.print(json.dumps(config.model_dump(), indent=2))

    elif fmt == "yaml":
        console.print(yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False))

    else:  # markdown
        console.print(f"# {config.id} - {config.name}\n")
        if config.description:
            console.print(config.description)

        console.print("\n## Patterns\n")
        for entry in config.patterns:
            pattern = catalog.get(entry.pattern_id)
            root_cause = ""
            if config.grading and entry.pattern_id == config.grading.root_cause_pattern:
                root_cause = " [ROOT CAUSE]"

            console.print(f"- **{entry.pattern_id}**{root_cause} (weight={entry.weight:.2f})")
            if pattern:
                console.print(f"  {pattern.name}")

        if config.grading:
            console.print("\n## Grading\n")
            console.print(f"- **Root Cause:** {config.grading.root_cause_pattern}")
            if config.grading.partial_credit:
                console.print("- **Partial Credit:**")
                for pid, credit in config.grading.partial_credit.items():
                    console.print(f"  - {pid}: {credit*100:.0f}%")

        console.print("\n## Difficulty\n")
        console.print(f"- Multiplier: {config.total_difficulty_multiplier}x")
        if config.estimated_human_time_hours:
            console.print(f"- Estimated Time: {config.estimated_human_time_hours} hours")


@main.command("multi-inject")
@click.argument("config_id")
@click.option("-t", "--target", required=True, help="Target codebase directory")
@click.option("-o", "--output", required=True, help="Output directory")
@click.option("--configs-dir", default="./injection_configs", help="Multi-pattern configs directory")
@click.option("--seed", type=int, help="Random seed for reproducibility")
@click.option("--dry-run", is_flag=True, help="Show what would be changed")
@click.pass_context
def multi_inject(
    ctx: click.Context,
    config_id: str,
    target: str,
    output: str,
    configs_dir: str,
    seed: int | None,
    dry_run: bool,
) -> None:
    """Inject multiple patterns into a target codebase.

    Injects multiple patterns according to a multi-pattern configuration,
    creating complex debugging scenarios with root causes, contributing
    factors, and optional red herrings.

    Examples:
        sdlc-inject multi-inject COMPLEX-001 --target ./zed --output ./injected-zed
        sdlc-inject multi-inject COMPLEX-002 --target ./project --output ./out --seed 42
    """
    catalog: PatternCatalog = ctx.obj["catalog"]
    loader = MultiPatternLoader(configs_dir, catalog)
    config = loader.get(config_id)

    if not config:
        console.print(f"[red]Multi-pattern config not found: {config_id}[/red]")
        console.print(f"[dim]Looked in: {configs_dir}[/dim]")
        raise SystemExit(1)

    # Validate configuration
    is_valid, errors = loader.validate(config)
    if not is_valid:
        console.print(f"[red]Configuration validation failed:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise SystemExit(1)

    target_path = Path(target)
    if not target_path.exists():
        console.print(f"[red]Target directory not found: {target}[/red]")
        raise SystemExit(1)

    # Create injector and run
    injector = MultiPatternInjector(catalog, seed=seed)
    result = injector.inject(
        config=config,
        target_dir=target_path,
        output_dir=Path(output),
        dry_run=dry_run,
    )

    # Save result metadata
    if not dry_run:
        metadata_path = Path(output) / ".multi-pattern-injection.json"
        with open(metadata_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        console.print(f"\n[dim]Metadata saved to: {metadata_path}[/dim]")

    if not result.success and not dry_run:
        console.print(f"\n[yellow]Warning: Injection completed with errors[/yellow]")
        raise SystemExit(1)


# =============================================================================
# Validation Commands
# =============================================================================


@main.command("validate")
@click.argument("pattern_id")
@click.option("-t", "--target", required=True, help="Target directory with injected pattern")
@click.option("--trigger-test", is_flag=True, help="Run trigger test")
@click.option("--golden-path", is_flag=True, help="Verify golden path")
@click.pass_context
def validate(ctx: click.Context, pattern_id: str, target: str, trigger_test: bool, golden_path: bool) -> None:
    """Validate an injected pattern."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    target_path = Path(target)
    if not target_path.exists():
        console.print(f"[red]Target directory not found: {target}[/red]")
        raise SystemExit(1)

    console.print(f"[bold]Validating pattern {pattern.id} in {target}[/bold]\n")

    # Check injected files exist
    console.print("[bold]Checking injected files...[/bold]")
    for file_inj in pattern.injection.files:
        file_path = target_path / file_inj.path
        if file_path.exists():
            console.print(f"  [green]✓[/green] {file_inj.path}")
        else:
            console.print(f"  [red]✗[/red] {file_inj.path} (not found)")

    if trigger_test and pattern.trigger:
        console.print("\n[bold]Trigger conditions:[/bold]")
        for cond in pattern.trigger.conditions:
            console.print(f"  - {cond.description}")

        console.print("\n[bold]Reproduction steps:[/bold]")
        for step in pattern.trigger.reproduction_steps:
            console.print(f"  {step.step}. {step.action}")
            if step.command:
                console.print(f"     [dim]$ {step.command}[/dim]")

    if golden_path and pattern.golden_path:
        console.print("\n[bold]Golden path verification:[/bold]")
        for step in pattern.golden_path.steps:
            console.print(f"  {step.step}. {step.action}")

    console.print("\n[green]Validation complete.[/green]")


@main.command("grade-setup")
@click.argument("pattern_id")
@click.option("-t", "--target", required=True, help="Target directory")
@click.option("-o", "--output", required=True, help="Output directory for grading infrastructure")
@click.pass_context
def grade_setup(ctx: click.Context, pattern_id: str, target: str, output: str) -> None:
    """Generate grading infrastructure for a pattern."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    generate_grading_setup(pattern, Path(target), Path(output))
    console.print(f"[green]Grading infrastructure generated in {output}[/green]")


@main.command("grade")
@click.argument("pattern_id")
@click.option("--trajectory", required=True, help="Agent trajectory file")
@click.option("--environment-state", help="Final environment state directory")
@click.option("-f", "--format", "fmt", default="json", help="Output format (json, yaml, markdown)")
@click.pass_context
def grade(ctx: click.Context, pattern_id: str, trajectory: str, environment_state: str | None, fmt: str) -> None:
    """Grade an agent's trajectory."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    result = evaluate_trajectory(
        pattern=pattern,
        trajectory_path=Path(trajectory),
        environment_state=Path(environment_state) if environment_state else None,
    )

    if fmt == "json":
        console.print(json.dumps(result, indent=2))
    elif fmt == "yaml":
        console.print(yaml.dump(result, default_flow_style=False))
    else:
        console.print(f"# Grading Report: {pattern.id}\n")
        console.print(f"**Total Score:** {result['total_score']*100:.1f}%\n")

        console.print("## Outcome Criteria")
        for r in result["outcome_results"]:
            console.print(f"- {r['criterion']}: {r['score']*100:.0f}%")

        console.print("\n## Process Criteria")
        for r in result["process_results"]:
            console.print(f"- {r['criterion']}: {r['score']*100:.0f}%")


@main.command("env-setup")
@click.argument("pattern_id")
@click.option("-o", "--output", required=True, help="Output directory")
@click.option("--monitoring", is_flag=True, help="Include monitoring stack")
@click.option("--load-generator", is_flag=True, help="Include load generator")
@click.pass_context
def env_setup(ctx: click.Context, pattern_id: str, output: str, monitoring: bool, load_generator: bool) -> None:
    """Generate environment files for a pattern."""
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    generate_environment(
        pattern=pattern,
        output_dir=Path(output),
        include_monitoring=monitoring,
        include_load_generator=load_generator,
    )
    console.print(f"[green]Environment files generated in {output}[/green]")


@main.command("validate-catalog")
@click.option("-p", "--path", help="Specific path to validate")
@click.pass_context
def validate_catalog_cmd(ctx: click.Context, path: str | None) -> None:
    """Validate pattern YAML files."""
    catalog_dir = Path(ctx.obj["catalog_dir"])

    results = validate_catalog(
        catalog_dir,
        specific_path=Path(path) if path else None,
    )

    console.print(f"[bold]Validating patterns in: {catalog_dir}[/bold]\n")

    for valid_path in results["valid"]:
        console.print(f"  [green]✓[/green] {valid_path}")

    for invalid in results["invalid"]:
        console.print(f"  [red]✗[/red] {invalid['path']}")
        console.print(f"      {invalid['error']}")

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Total: {results['total']}")
    console.print(f"  Valid: {len(results['valid'])}")
    console.print(f"  Invalid: {len(results['invalid'])}")

    if results["invalid"]:
        raise SystemExit(1)
    else:
        console.print("\n[green]✓ All patterns valid![/green]")


@main.command("artifacts")
@click.argument("pattern_id")
@click.option("-o", "--output", required=True, help="Output directory for artifacts")
@click.option("--include", "-i", multiple=True, help="Include specific artifact types (sentry, slack, linear, pagerduty, logs, metrics, github, progressive)")
@click.option("--seed", type=int, help="Random seed for reproducibility")
@click.option("--duration", type=int, default=120, help="Incident duration in minutes (for progressive mode)")
@click.pass_context
def artifacts(ctx: click.Context, pattern_id: str, output: str, include: tuple, seed: int | None, duration: int) -> None:
    """Generate mock SDLC artifacts for a pattern.

    Generates realistic artifacts from tools commonly used in incident response:
    - Sentry: Error reports, stack traces, breadcrumbs
    - Slack: Incident channel messages, threads
    - Linear: Bug tickets, comments, activity
    - PagerDuty: Alerts, incidents, timelines
    - Logs: Structured and plaintext application logs
    - Metrics: Prometheus snapshots, Grafana dashboards, alerts
    - GitHub: Issues, PRs, comments, commits
    - Progressive: Real-time incident timeline with rate limits, escalations, webhooks
    """
    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    include_list = list(include) if include else None

    console.print(f"[bold]Generating artifacts for {pattern.id}[/bold]\n")

    results = generate_artifacts_for_pattern(
        pattern=pattern,
        output_dir=Path(output),
        include=include_list,
        seed=seed,
    )

    # Display results
    table = Table(title="Generated Artifacts")
    table.add_column("Type", style="cyan")
    table.add_column("Files", style="green")

    for artifact_type, files in results.items():
        file_names = [f.name for f in files]
        table.add_row(artifact_type, ", ".join(file_names))

    console.print(table)
    console.print(f"\n[green]Artifacts generated in {output}[/green]")

    # Summary of what was generated
    total_files = sum(len(files) for files in results.values())
    console.print(f"\nTotal: {total_files} files across {len(results)} artifact types")


@main.command("analyze")
@click.argument("codebase_path")
@click.option("-o", "--output", help="Output file for analysis report (JSON)")
@click.option("-k", "--top-k", default=10, help="Number of top recommendations")
@click.option("--no-ai", is_flag=True, help="Disable AI-enhanced analysis")
@click.option("--quick", is_flag=True, help="Quick scan without full analysis")
@click.pass_context
def analyze(ctx: click.Context, codebase_path: str, output: str | None, top_k: int, no_ai: bool, quick: bool) -> None:
    """Analyze a codebase and recommend failure patterns.

    Scans the codebase to identify:
    - Concurrency patterns (async, threading, locks)
    - Distributed system patterns (RPC, message queues, databases)
    - State management patterns (caches, sessions, global state)
    - Time-sensitive patterns (timestamps, timeouts, TTLs)

    Then recommends the most suitable failure patterns for injection.

    Examples:
        sdlc-inject analyze ./my-project
        sdlc-inject analyze ./my-project --output report.json --top-k 5
        sdlc-inject analyze ./my-project --quick
    """
    catalog_dir = ctx.obj["catalog_dir"]

    analyzer = CodebaseAnalyzer(
        patterns_dir=catalog_dir,
        use_ai=not no_ai,
    )

    try:
        if quick:
            console.print(f"[bold]Quick scan of {codebase_path}[/bold]\n")
            result = analyzer.quick_scan(codebase_path)

            console.print(f"Languages: {', '.join(result['languages']) or 'Unknown'}")
            console.print(f"Frameworks: {', '.join(result['frameworks']) or 'None detected'}")
            console.print(f"Architecture: {', '.join(result['architecture']) or 'Unknown'}")
            console.print(f"Files: {result['total_files']}")
            console.print(f"Lines: {result['total_lines']}")
            console.print(f"Has tests: {'Yes' if result['has_tests'] else 'No'}")
            console.print(f"Has CI: {'Yes' if result['has_ci'] else 'No'}")
            console.print(f"Has Docker: {'Yes' if result['has_docker'] else 'No'}")

            if result['suitable_for_injection']:
                console.print("\n[green]Codebase is suitable for pattern injection.[/green]")
            else:
                console.print("\n[yellow]Codebase may not be suitable for pattern injection.[/yellow]")

            return

        console.print(f"[bold]Analyzing codebase: {codebase_path}[/bold]\n")
        report = analyzer.analyze(
            codebase_path=codebase_path,
            top_k=top_k,
            output_file=output,
        )

        # Display structure
        console.print("[bold]Codebase Structure:[/bold]")
        console.print(f"  Languages: {', '.join(report.structure.languages) or 'Unknown'}")
        console.print(f"  Frameworks: {', '.join(report.structure.frameworks) or 'None detected'}")
        console.print(f"  Architecture: {', '.join(report.structure.architecture_hints) or 'Unknown'}")
        console.print(f"  Files: {report.structure.total_files}, Lines: {report.structure.total_lines}")

        console.print("\n[bold]Patterns Found:[/bold]")
        console.print(f"  Concurrency: {len(report.concurrency_patterns)}")
        console.print(f"  Distributed: {len(report.distributed_patterns)}")
        console.print(f"  State Management: {len(report.state_patterns)}")
        console.print(f"  Time-Sensitive: {len(report.time_patterns)}")

        # Display recommendations
        console.print("\n[bold]Recommended Patterns:[/bold]\n")
        table = Table()
        table.add_column("Rank", style="dim")
        table.add_column("Pattern", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Rationale", max_width=50)

        for i, rec in enumerate(report.recommendations, 1):
            score_color = "green" if rec.score >= 0.7 else "yellow" if rec.score >= 0.4 else "dim"
            table.add_row(
                str(i),
                f"{rec.pattern_id}\n{rec.pattern_name[:30]}",
                f"[{score_color}]{rec.score:.2f}[/{score_color}]",
                rec.rationale[:50] + "..." if len(rec.rationale) > 50 else rec.rationale,
            )

        console.print(table)

        if output:
            console.print(f"\n[green]Full report written to {output}[/green]")

    finally:
        analyzer.close()


@main.command("enrich")
@click.argument("pattern_id")
@click.option("--dry-run", is_flag=True, help="Show what would be changed without writing")
@click.option("--add-url", help="Add a specific URL to the pattern")
@click.option("--max-incidents", default=3, help="Maximum incidents to add")
@click.pass_context
def enrich(ctx: click.Context, pattern_id: str, dry_run: bool, add_url: str | None, max_incidents: int) -> None:
    """Enrich a pattern with real-world incident references.

    Searches for related incidents (postmortems, engineering blogs) and adds
    them to the pattern with:
    - Source type and company attribution
    - Year of the incident
    - LLM-generated summary of how engineers solved it
    - Relevant tags

    Examples:
        sdlc-inject enrich RACE-001
        sdlc-inject enrich RACE-001 --dry-run
        sdlc-inject enrich RACE-001 --add-url "https://example.com/postmortem"
    """
    catalog_dir = ctx.obj["catalog_dir"]
    updater = PatternUpdater(patterns_dir=catalog_dir)

    try:
        if add_url:
            # Add a specific URL
            console.print(f"[bold]Adding incident URL to {pattern_id}[/bold]\n")
            result = updater.add_incident(
                pattern_id=pattern_id,
                url=add_url,
            )

            if "error" in result:
                console.print(f"[red]Error: {result['error']}[/red]")
                raise SystemExit(1)

            console.print(f"[green]Added incident to {pattern_id}[/green]")
            console.print(f"URL: {add_url}")
            console.print(f"Total incidents: {result['total_incidents']}")

        else:
            # Search and enrich
            console.print(f"[bold]Enriching pattern {pattern_id}[/bold]\n")
            result = updater.enrich_pattern(
                pattern_id=pattern_id,
                dry_run=dry_run,
                max_incidents=max_incidents,
            )

            if "error" in result:
                console.print(f"[red]Error: {result['error']}[/red]")
                raise SystemExit(1)

            console.print(f"Pattern file: {result['pattern_file']}")
            console.print(f"Existing incidents: {result['existing_incidents']}")
            console.print(f"New incidents found: {result['new_incidents']}")
            console.print(f"Total incidents: {result['total_incidents']}")

            if result['incidents_added']:
                console.print("\n[bold]Incidents added:[/bold]")
                for inc in result['incidents_added']:
                    console.print(f"  - {inc.get('title', inc['url'][:50])}")
                    if inc.get('company'):
                        console.print(f"    Company: {inc['company']}")

            if dry_run:
                console.print("\n[yellow]Dry run - no changes written[/yellow]")
            else:
                console.print("\n[green]Pattern file updated![/green]")

    finally:
        updater.close()


@main.command("enrich-all")
@click.option("-c", "--category", help="Filter by category (race, split-brain, clock-skew, coordination)")
@click.option("--dry-run", is_flag=True, help="Show what would be changed without writing")
@click.option("--max-incidents", default=3, help="Maximum incidents per pattern")
@click.pass_context
def enrich_all(ctx: click.Context, category: str | None, dry_run: bool, max_incidents: int) -> None:
    """Enrich all patterns with real-world incident references.

    Searches for related incidents for each pattern and updates the YAML files
    with source attribution and LLM-generated solution summaries.

    Examples:
        sdlc-inject enrich-all
        sdlc-inject enrich-all --category race
        sdlc-inject enrich-all --dry-run
    """
    catalog_dir = ctx.obj["catalog_dir"]
    updater = PatternUpdater(patterns_dir=catalog_dir)

    try:
        console.print(f"[bold]Enriching patterns{' in category: ' + category if category else ''}[/bold]\n")

        results = updater.enrich_all(
            category=category,
            dry_run=dry_run,
            max_incidents_per_pattern=max_incidents,
        )

        # Display results
        table = Table(title="Enrichment Results")
        table.add_column("Pattern", style="cyan")
        table.add_column("Existing", justify="right")
        table.add_column("Added", justify="right", style="green")
        table.add_column("Total", justify="right")
        table.add_column("Status")

        total_added = 0
        for result in results:
            if "error" in result:
                table.add_row(
                    result.get("pattern_id", "Unknown"),
                    "-", "-", "-",
                    f"[red]{result['error']}[/red]"
                )
            else:
                added = result['new_incidents']
                total_added += added
                status = "[green]Updated[/green]" if result.get('written') else "[dim]No changes[/dim]"
                table.add_row(
                    result['pattern_id'],
                    str(result['existing_incidents']),
                    str(added),
                    str(result['total_incidents']),
                    status
                )

        console.print(table)

        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Patterns processed: {len(results)}")
        console.print(f"  Total incidents added: {total_added}")

        if dry_run:
            console.print("\n[yellow]Dry run - no changes written[/yellow]")
        else:
            console.print("\n[green]All patterns updated![/green]")

    finally:
        updater.close()


def _is_github_url(path: str) -> bool:
    """Check if the path is a GitHub URL."""
    return path.startswith(("https://github.com/", "git@github.com:", "github.com/"))


def _clone_github_repo(url: str, ref: str | None = None, shallow: bool = True) -> Path:
    """Clone a GitHub repo to a temporary directory."""
    import subprocess
    import tempfile

    # Normalize URL
    if url.startswith("github.com/"):
        url = f"https://{url}"

    # Remove trailing .git if present
    if url.endswith(".git"):
        url = url[:-4]

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="sdlc-inject-"))

    # Build clone command
    clone_cmd = ["git", "clone"]
    if shallow:
        clone_cmd.extend(["--depth", "1"])
    if ref:
        clone_cmd.extend(["--branch", ref])
    clone_cmd.extend([url, str(temp_dir)])

    try:
        subprocess.run(clone_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        # Clean up on failure
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise click.ClickException(f"Failed to clone repository: {e.stderr}")

    return temp_dir


@main.command("neural-analyze")
@click.argument("codebase_path")
@click.option("-o", "--output", help="Output file for analysis report (JSON)")
@click.option("-m", "--model", default="claude-sonnet-4-20250514", help="Claude model to use")
@click.option("--max-files", default=20, help="Maximum files to analyze")
@click.option("--focus", multiple=True, help="Focus on specific patterns (race, coordination, timing)")
@click.option("--enrich/--no-enrich", default=True, help="Enrich with Exa search for similar vulnerabilities")
@click.option("--ref", help="Git branch, tag, or commit to checkout (for GitHub URLs)")
@click.option("--shallow/--full", default=True, help="Shallow clone for faster downloads (for GitHub URLs)")
@click.option("--keep-clone", is_flag=True, help="Keep cloned repo after analysis (for GitHub URLs)")
@click.option("--max-budget", default=5.0, type=float, help="Maximum cost budget in USD for the analysis")
@click.option("--discover-tools/--no-discover-tools", default=True, help="Discover external tools from incident data for dynamic MCP servers")
@click.pass_context
def neural_analyze(
    ctx: click.Context,
    codebase_path: str,
    output: str | None,
    model: str,
    max_files: int,
    focus: tuple,
    enrich: bool,
    ref: str | None,
    shallow: bool,
    keep_clone: bool,
    max_budget: float,
    discover_tools: bool,
) -> None:
    """Perform deep neural analysis of a codebase using Claude Agent SDK.

    Uses the Claude Agent SDK to give Claude direct access to codebase
    exploration tools (Read, Glob, Grep). Claude can follow imports, trace
    data flows, and identify cross-file vulnerabilities autonomously.

    Supports both local paths and GitHub URLs:
    - Local: ./my-project or /path/to/project
    - GitHub: https://github.com/owner/repo

    This provides:
    - Agentic codebase exploration with Read/Glob/Grep tools
    - Semantic understanding of code flow and data dependencies
    - Cross-file vulnerability detection
    - Suggested injection points with explanations
    - Optional enrichment via Exa API for similar vulnerabilities

    Examples:
        sdlc-inject neural-analyze ./my-project
        sdlc-inject neural-analyze https://github.com/zed-industries/zed
        sdlc-inject neural-analyze https://github.com/owner/repo --ref v1.0.0
        sdlc-inject neural-analyze https://github.com/owner/repo --full --keep-clone
        sdlc-inject neural-analyze ./my-project --focus race --focus coordination
        sdlc-inject neural-analyze ./my-project --max-budget 10.0
    """
    import os
    import shutil

    # Ensure .env is loaded (in case it wasn't loaded at import time)
    try:
        from dotenv import load_dotenv
        # Try package directory first (most reliable)
        package_dir = Path(__file__).parent.parent
        env_file = package_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
        load_dotenv(override=False)
    except ImportError:
        pass

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY environment variable required for neural analysis[/red]")
        console.print("[yellow]Hint: Set ANTHROPIC_API_KEY env var or add it to .env file[/yellow]")
        raise SystemExit(1)

    exa_key = os.environ.get("EXA_API_KEY")
    if enrich and not exa_key:
        console.print("[yellow]Warning: EXA_API_KEY not set, enrichment disabled[/yellow]")
        enrich = False

    # Handle GitHub URLs
    temp_dir: Path | None = None
    analysis_path: str = codebase_path

    if _is_github_url(codebase_path):
        console.print(f"[bold]Cloning GitHub repository: {codebase_path}[/bold]")
        if ref:
            console.print(f"  Branch/tag: {ref}")
        console.print(f"  Shallow clone: {'yes' if shallow else 'no'}\n")

        with console.status("[bold blue]Cloning repository...[/bold blue]"):
            temp_dir = _clone_github_repo(codebase_path, ref=ref, shallow=shallow)
            analysis_path = str(temp_dir)

        console.print(f"[green]Repository cloned to: {temp_dir}[/green]\n")

    console.print(f"[bold]Neural Analysis of {codebase_path}[/bold]\n")
    console.print(f"Model: {model}")
    console.print(f"Max files: {max_files}")
    console.print(f"Max budget: ${max_budget:.2f}")
    if focus:
        console.print(f"Focus patterns: {', '.join(focus)}")
    console.print(f"Exa enrichment: {'enabled' if enrich else 'disabled'}")
    console.print(f"Backend: Claude Agent SDK (agentic exploration)\n")

    analyzer = NeuralCodeAnalyzer(
        model=model,
        exa_api_key=exa_key if enrich else None,
        max_budget_usd=max_budget,
    )

    try:
        with console.status("[bold green]Agent exploring codebase with Claude...[/bold green]"):
            result = analyzer.analyze_codebase(
                codebase_path=analysis_path,
                max_files=max_files,
                focus_patterns=list(focus) if focus else None,
                output_file=output,
            )

        # Optionally enrich with Exa (and discover tools)
        if enrich and exa_key:
            with console.status("[bold blue]Enriching with similar vulnerabilities...[/bold blue]"):
                result = analyzer.enrich_with_similar_code(
                    result,
                    search_similar=True,
                    search_incidents=True,
                    discover_tools=discover_tools,
                )

            # Generate and save service configs for discovered tools
            if discover_tools and result.discovered_tools and output:
                try:
                    from .discovery import SchemaGenerator, ToolProfile, save_service_configs

                    output_dir = Path(output).parent / "service_configs"
                    profiles = [ToolProfile.model_validate(t) for t in result.discovered_tools]
                    if profiles:
                        vuln_types = list(set(
                            v.vulnerability_type for v in result.vulnerability_points[:5]
                        ))
                        vuln_context = ", ".join(vuln_types) if vuln_types else "production debugging"

                        with console.status("[bold blue]Generating service configs for discovered tools...[/bold blue]"):
                            generator = SchemaGenerator(model=model)
                            configs = generator.generate_configs(profiles[:5], vuln_context)

                        if configs:
                            paths = save_service_configs(configs, output_dir)
                            console.print(f"\n[green]Saved {len(paths)} service configs to {output_dir}[/green]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Service config generation failed: {e}[/yellow]")

        # Display results
        console.print("\n[bold]Analysis Results[/bold]\n")
        console.print(f"Files analyzed: {result.files_analyzed}")
        console.print(f"Tokens used: {result.total_tokens_used:,}")
        if result.total_cost_usd > 0:
            console.print(f"Cost: ${result.total_cost_usd:.4f}")
        console.print(f"Vulnerabilities found: {len(result.vulnerability_points)}")

        console.print(f"\n[bold]Architecture Summary:[/bold]")
        console.print(result.architecture_summary or "Not available")

        console.print(f"\n[bold]Concurrency Model:[/bold]")
        console.print(result.concurrency_model or "Not detected")

        # Display vulnerabilities
        if result.vulnerability_points:
            console.print(f"\n[bold]Vulnerability Points ({len(result.vulnerability_points)}):[/bold]\n")

            table = Table()
            table.add_column("File", style="cyan", max_width=30)
            table.add_column("Lines", justify="right")
            table.add_column("Type", style="yellow")
            table.add_column("Confidence", justify="right")
            table.add_column("Explanation", max_width=40)

            for vuln in result.vulnerability_points[:15]:
                conf_color = "green" if vuln.confidence >= 0.7 else "yellow" if vuln.confidence >= 0.4 else "red"
                table.add_row(
                    vuln.file_path[:28] + "..." if len(vuln.file_path) > 30 else vuln.file_path,
                    f"{vuln.start_line}-{vuln.end_line}",
                    vuln.vulnerability_type.replace("_", " "),
                    f"[{conf_color}]{vuln.confidence:.2f}[/{conf_color}]",
                    vuln.explanation[:38] + "..." if len(vuln.explanation) > 40 else vuln.explanation,
                )

            console.print(table)

            if len(result.vulnerability_points) > 15:
                console.print(f"\n[dim]... and {len(result.vulnerability_points) - 15} more[/dim]")

        # Display recommended patterns
        if result.recommended_patterns:
            console.print(f"\n[bold]Recommended Injection Patterns:[/bold]\n")

            for rec in result.recommended_patterns[:5]:
                console.print(f"  • [cyan]{rec.get('pattern_id', 'N/A')}[/cyan]")
                console.print(f"    Confidence: {rec.get('confidence', 0):.2f}")
                console.print(f"    Target: {', '.join(rec.get('target_files', []))[:50]}")
                console.print(f"    Rationale: {rec.get('rationale', '')[:60]}")
                console.print()

        # Display discovered tools
        if result.discovered_tools:
            console.print(f"\n[bold]Discovered External Tools ({len(result.discovered_tools)}):[/bold]\n")

            tools_table = Table()
            tools_table.add_column("Tool", style="cyan")
            tools_table.add_column("Category", style="yellow")
            tools_table.add_column("Relevance", justify="right")
            tools_table.add_column("Description", max_width=40)

            for t in result.discovered_tools[:10]:
                rel = t.get("relevance_score", 0)
                rel_color = "green" if rel >= 0.6 else "yellow" if rel >= 0.3 else "dim"
                tools_table.add_row(
                    t.get("display_name", t.get("name", "?")),
                    t.get("category", "other"),
                    f"[{rel_color}]{rel:.2f}[/{rel_color}]",
                    (t.get("description", "")[:38] + "...")
                    if len(t.get("description", "")) > 40
                    else t.get("description", ""),
                )

            console.print(tools_table)

        if output:
            console.print(f"\n[green]Full report written to {output}[/green]")

        # Summary
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  High confidence vulnerabilities: {sum(1 for v in result.vulnerability_points if v.confidence >= 0.7)}")
        console.print(f"  Medium confidence: {sum(1 for v in result.vulnerability_points if 0.4 <= v.confidence < 0.7)}")
        console.print(f"  Low confidence: {sum(1 for v in result.vulnerability_points if v.confidence < 0.4)}")

    except Exception as e:
        console.print(f"[red]Error during analysis: {e}[/red]")
        raise SystemExit(1)

    finally:
        analyzer.close()

        # Clean up cloned repo if applicable
        if temp_dir and not keep_clone:
            console.print(f"\n[dim]Cleaning up cloned repository...[/dim]")
            shutil.rmtree(temp_dir, ignore_errors=True)
        elif temp_dir and keep_clone:
            console.print(f"\n[green]Cloned repository kept at: {temp_dir}[/green]")


@main.command("evaluate")
@click.argument("pattern_id")
@click.option("-t", "--target", required=True, help="Target codebase with injected pattern")
@click.option("-o", "--output", required=True, help="Output directory for results")
@click.option("-n", "--num-agents", default=10, help="Number of parallel agents")
@click.option("-m", "--model", default="claude-sonnet-4-20250514", help="Claude model to use")
@click.option("--temperatures", default="0.0", help="Comma-separated temperature values")
@click.option("--timeout", default=3600, help="Max time per agent in seconds")
@click.option("--max-budget", default=2.0, type=float, help="Maximum cost budget per agent in USD")
@click.option("--artifacts", help="Path to debugging artifacts")
@click.option("--mcp-mode", is_flag=True, help="Enable MCP servers for observability tools")
@click.option("--mcp-rate-limit", default=30, help="MCP API requests per minute limit")
@click.option("--mcp-seed", type=int, help="Random seed for MCP server data")
@click.option("--service-configs", help="Directory of ServiceConfig YAML files for dynamic MCP servers")
@click.pass_context
def evaluate(
    ctx: click.Context,
    pattern_id: str,
    target: str,
    output: str,
    num_agents: int,
    model: str,
    temperatures: str,
    timeout: int,
    max_budget: float,
    artifacts: str | None,
    mcp_mode: bool,
    mcp_rate_limit: int,
    mcp_seed: int | None,
    service_configs: str | None,
) -> None:
    """Run parallel agent evaluation on an injected codebase using Claude Agent SDK.

    Spins up N agents (powered by the Claude Agent SDK) to debug the same
    injected pattern, collects trajectories, and analyzes success/failure patterns.

    Each agent has access to Read, Edit, Bash, Grep, and Glob tools via the SDK.
    With --mcp-mode, agents also get mock Sentry, Slack, GitHub, PagerDuty,
    and Prometheus tools via in-process SDK MCP servers.

    Examples:
        sdlc-inject evaluate RACE-001 --target ./injected-codebase --output ./results -n 10
        sdlc-inject evaluate RACE-001 --target ./injected --output ./results --mcp-mode
        sdlc-inject evaluate RACE-001 --target ./injected --output ./results --max-budget 5.0
    """
    import asyncio

    from .harness import EvaluationConfig, Orchestrator, MCPConfig

    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    target_path = Path(target)
    if not target_path.exists():
        console.print(f"[red]Target codebase not found: {target}[/red]")
        raise SystemExit(1)

    # Parse temperatures
    temp_list = [float(t.strip()) for t in temperatures.split(",")]

    # Create MCP config if enabled
    mcp_config = None
    if mcp_mode:
        # Load dynamic service configs if provided
        dynamic_configs = []
        if service_configs:
            from .discovery import load_service_configs

            configs_path = Path(service_configs)
            if configs_path.exists():
                dynamic_configs = load_service_configs(configs_path)
                console.print(f"Loaded {len(dynamic_configs)} dynamic service configs from {configs_path}")
            else:
                console.print(f"[yellow]Warning: Service configs directory not found: {service_configs}[/yellow]")

        mcp_config = MCPConfig(
            enabled=True,
            seed=mcp_seed,
            rate_limit_enabled=True,
            requests_per_minute=mcp_rate_limit,
            dynamic_service_configs=dynamic_configs,
        )

    config = EvaluationConfig(
        pattern_id=pattern_id,
        target_codebase=target_path,
        artifacts_dir=Path(artifacts) if artifacts else None,
        num_agents=num_agents,
        max_time_per_agent=timeout,
        max_budget_per_agent=max_budget,
        model=model,
        temperatures=temp_list,
        mcp_config=mcp_config,
        pattern=pattern,
    )

    console.print(f"[bold]Running Evaluation: {pattern_id}[/bold]\n")
    console.print(f"Target: {target}")
    console.print(f"Agents: {num_agents}")
    console.print(f"Model: {model}")
    console.print(f"Temperatures: {temp_list}")
    console.print(f"Timeout: {timeout}s per agent")
    console.print(f"Budget: ${max_budget:.2f} per agent")
    console.print(f"Backend: Claude Agent SDK")
    if mcp_mode:
        console.print(f"MCP Mode: [green]Enabled[/green] (rate limit: {mcp_rate_limit}/min)")
    console.print()

    try:
        orchestrator = Orchestrator()

        with console.status(f"[bold green]Running {num_agents} parallel agents...[/bold green]"):
            run = asyncio.run(orchestrator.run_evaluation(config, Path(output)))

        # Display results
        console.print(f"\n[bold]Evaluation Complete[/bold]\n")
        console.print(f"Run ID: {run.run_id}")
        console.print(f"Duration: {(run.end_time - run.start_time).total_seconds():.1f}s")
        console.print(f"Trajectories collected: {len(run.trajectories)}")
        console.print(f"Errors: {len(run.errors)}")

        if run.analytics:
            console.print(f"\n[bold]Results Summary[/bold]\n")

            table = Table()
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            pr = run.analytics.pass_rate
            pr_color = "green" if pr >= 0.3 else "yellow" if pr >= 0.1 else "red"

            table.add_row("Pass Rate", f"[{pr_color}]{pr*100:.1f}%[/{pr_color}]")
            table.add_row("95% CI", f"{run.analytics.pass_rate_ci_lower*100:.1f}% - {run.analytics.pass_rate_ci_upper*100:.1f}%")
            table.add_row("Root Cause Identified", f"{run.analytics.root_cause_identified_rate*100:.1f}%")
            table.add_row("Median Time (Success)", f"{run.analytics.median_time_success/60:.1f} min")
            table.add_row("Median Time (Failure)", f"{run.analytics.median_time_failure/60:.1f} min")

            console.print(table)

            if run.analytics.failure_modes:
                console.print(f"\n[bold]Failure Modes[/bold]\n")
                for fm in run.analytics.failure_modes[:5]:
                    console.print(f"  • {fm.mode.value}: {fm.count} ({fm.frequency*100:.1f}%)")

        # Display MCP stats if MCP mode was enabled
        if run.mcp_stats:
            console.print(f"\n[bold]MCP API Usage[/bold]\n")
            mcp_table = Table()
            mcp_table.add_column("Metric", style="cyan")
            mcp_table.add_column("Value", justify="right")

            mcp_table.add_row("Total Requests", str(run.mcp_stats.total_requests))
            mcp_table.add_row("Successful", str(run.mcp_stats.successful_requests))
            mcp_table.add_row("Rate Limited", f"[yellow]{run.mcp_stats.rate_limited_requests}[/yellow]")
            mcp_table.add_row("Failed", f"[red]{run.mcp_stats.failed_requests}[/red]")
            mcp_table.add_row("Rate Limit Violations", str(run.mcp_stats.rate_limit_violations))

            console.print(mcp_table)

            if run.mcp_stats.requests_by_service:
                console.print("\n[bold]Requests by Service:[/bold]")
                for service, count in sorted(run.mcp_stats.requests_by_service.items()):
                    console.print(f"  • {service}: {count}")

        console.print(f"\n[green]Results saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error during evaluation: {e}[/red]")
        raise SystemExit(1)


@main.command("generate-services")
@click.argument("report_file")
@click.option("-o", "--output", required=True, help="Output directory for ServiceConfig YAML files")
@click.option("-m", "--model", default="claude-sonnet-4-20250514", help="Claude model for schema generation")
@click.option("--max-tools", default=5, help="Maximum number of tools to generate configs for")
@click.pass_context
def generate_services(
    ctx: click.Context,
    report_file: str,
    output: str,
    model: str,
    max_tools: int,
) -> None:
    """Generate ServiceConfig YAML files from a neural analysis report.

    Takes the JSON report from neural-analyze (which includes discovered_tools)
    and generates ServiceConfig YAML files that can be used with the evaluate
    command's --service-configs option.

    This is useful for:
    - Manually reviewing/editing generated configs before evaluation
    - Re-generating configs without re-running the full analysis
    - Sharing service configs across team members

    Examples:
        sdlc-inject generate-services report.json -o ./service_configs/
        sdlc-inject generate-services report.json -o ./configs/ --max-tools 3
    """
    import json as json_mod
    from .discovery import ToolProfile, SchemaGenerator, save_service_configs

    report_path = Path(report_file)
    if not report_path.exists():
        console.print(f"[red]Report file not found: {report_file}[/red]")
        raise SystemExit(1)

    # Load the report
    with open(report_path) as f:
        report_data = json_mod.load(f)

    discovered_tools = report_data.get("discovered_tools", [])
    if not discovered_tools:
        console.print("[yellow]No discovered tools in this report. Run neural-analyze with --discover-tools first.[/yellow]")
        return

    # Parse ToolProfiles
    profiles = []
    for t in discovered_tools[:max_tools]:
        try:
            profiles.append(ToolProfile.model_validate(t))
        except Exception as e:
            console.print(f"[yellow]Warning: Skipping invalid tool profile: {e}[/yellow]")

    if not profiles:
        console.print("[yellow]No valid tool profiles found.[/yellow]")
        return

    console.print(f"[bold]Generating Service Configs[/bold]\n")
    console.print(f"Tools to process: {len(profiles)}")
    for p in profiles:
        console.print(f"  - {p.display_name} ({p.category})")
    console.print()

    # Build vulnerability context from the report
    vuln_types = list(set(
        v.get("type", "") for v in report_data.get("vulnerability_points", [])[:10]
    ))
    vuln_context = ", ".join(vuln_types) if vuln_types else "production debugging"

    # Generate configs
    generator = SchemaGenerator(model=model)
    try:
        with console.status("[bold green]Generating service configs with Claude...[/bold green]"):
            configs = generator.generate_configs(profiles, vuln_context)

        if configs:
            paths = save_service_configs(configs, Path(output))
            console.print(f"\n[bold]Generated {len(configs)} service configs:[/bold]\n")
            for path in paths:
                console.print(f"  [green]{path}[/green]")
            console.print(f"\nUse with: sdlc-inject evaluate --service-configs {output}")
        else:
            console.print("[yellow]No configs were generated.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error generating configs: {e}[/red]")
        raise SystemExit(1)


@main.command("mcp-server")
@click.argument("pattern_id")
@click.option("--port", default=8080, help="Port to run server on")
@click.option("--seed", type=int, help="Random seed for reproducibility")
@click.option("--rate-limit", default=30, help="Requests per minute limit")
@click.option("-f", "--format", "fmt", default="json", help="Response format (json, yaml)")
@click.pass_context
def mcp_server(
    ctx: click.Context,
    pattern_id: str,
    port: int,
    seed: int | None,
    rate_limit: int,
    fmt: str,
) -> None:
    """Start a standalone MCP server for testing.

    Runs mock Sentry, Slack, GitHub, PagerDuty, and Prometheus servers
    populated with realistic debugging data from the specified pattern.

    Useful for:
    - Testing MCP tool integrations
    - Manual exploration of generated debugging data
    - Developing and debugging agent behavior

    Examples:
        sdlc-inject mcp-server RACE-001
        sdlc-inject mcp-server RACE-001 --port 8080 --seed 42
        curl http://localhost:8080/sentry/issues
        curl http://localhost:8080/slack/channels
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    from .mcp_servers import MCPServerRegistry
    from .mcp_servers.rate_limiter import RateLimitConfig

    catalog: PatternCatalog = ctx.obj["catalog"]
    pattern = catalog.get(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        raise SystemExit(1)

    # Create registry
    rate_config = RateLimitConfig(requests_per_minute=rate_limit)
    registry = MCPServerRegistry(pattern, seed, rate_config)

    class MCPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path_parts = parsed.path.strip("/").split("/")

            if len(path_parts) < 2:
                self.send_error(400, "Invalid path. Use /{service}/{endpoint}")
                return

            service = path_parts[0]
            endpoint = "/" + "/".join(path_parts[1:])

            # Parse query parameters
            params = dict(urllib.parse.parse_qsl(parsed.query))

            # Make request through registry
            response = registry.make_request(service, "GET", endpoint, params)

            # Send response
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Type", f"application/{fmt}")
            self.end_headers()

            if fmt == "yaml":
                import yaml
                body = yaml.dump(response.body, default_flow_style=False)
            else:
                body = json.dumps(response.body, indent=2)

            self.wfile.write(body.encode())

        def log_message(self, format, *args):
            console.print(f"[dim]{self.address_string()} - {format % args}[/dim]")

    console.print(f"[bold]Starting MCP Server for {pattern_id}[/bold]\n")
    console.print(f"Port: {port}")
    console.print(f"Seed: {seed or 'random'}")
    console.print(f"Rate Limit: {rate_limit}/min")
    console.print(f"Format: {fmt}\n")

    console.print("[bold]Available endpoints:[/bold]")
    console.print(f"  Sentry:    http://localhost:{port}/sentry/issues")
    console.print(f"  Slack:     http://localhost:{port}/slack/channels")
    console.print(f"  GitHub:    http://localhost:{port}/github/issues")
    console.print(f"  PagerDuty: http://localhost:{port}/pagerduty/incidents")
    console.print(f"  Prometheus: http://localhost:{port}/prometheus/alerts")
    console.print()

    server = HTTPServer(("localhost", port), MCPHandler)
    console.print(f"[green]Server running at http://localhost:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")


@main.command("analyze-trajectories")
@click.argument("trajectories_path")
@click.option("-p", "--pattern-id", required=True, help="Pattern ID")
@click.option("-o", "--output", help="Output file for analytics (JSON or MD)")
@click.option("-f", "--format", "fmt", default="table", help="Output format (table, json, markdown)")
@click.pass_context
def analyze_trajectories_cmd(
    ctx: click.Context,
    trajectories_path: str,
    pattern_id: str,
    output: str | None,
    fmt: str,
) -> None:
    """Analyze collected agent trajectories.

    Load trajectories from a directory or file and compute analytics
    including pass rate, failure modes, and process metrics.

    Examples:
        sdlc-inject analyze-trajectories ./results/trajectories -p RACE-001
        sdlc-inject analyze-trajectories ./results/trajectories -p RACE-001 --output report.md
    """
    from .harness import load_trajectories, AnalyticsPipeline

    traj_path = Path(trajectories_path)
    if not traj_path.exists():
        console.print(f"[red]Trajectories path not found: {trajectories_path}[/red]")
        raise SystemExit(1)

    console.print(f"[bold]Analyzing Trajectories[/bold]\n")

    trajectories = load_trajectories(traj_path)
    console.print(f"Loaded {len(trajectories)} trajectories")

    pipeline = AnalyticsPipeline()
    result = pipeline.analyze(trajectories, pattern_id, "manual-analysis")

    if fmt == "json":
        console.print(result.to_json())
    elif fmt == "markdown":
        console.print(result.to_markdown())
    else:
        # Table format
        table = Table(title=f"Analytics: {pattern_id}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Trajectories", str(result.num_trajectories))
        table.add_row("Pass Rate", f"{result.pass_rate*100:.1f}%")
        table.add_row("95% CI", f"{result.pass_rate_ci_lower*100:.1f}% - {result.pass_rate_ci_upper*100:.1f}%")
        table.add_row("Partial Rate", f"{result.partial_rate*100:.1f}%")
        table.add_row("Root Cause ID Rate", f"{result.root_cause_identified_rate*100:.1f}%")
        table.add_row("Median Time (Success)", f"{result.median_time_success/60:.1f} min")
        table.add_row("Median Time (Failure)", f"{result.median_time_failure/60:.1f} min")

        console.print(table)

        if result.failure_modes:
            console.print(f"\n[bold]Failure Modes:[/bold]")
            for fm in result.failure_modes:
                console.print(f"  • {fm.mode.value}: {fm.count} ({fm.frequency*100:.1f}%)")

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == ".md":
            with open(output_path, "w") as f:
                f.write(result.to_markdown())
        else:
            with open(output_path, "w") as f:
                f.write(result.to_json())
        console.print(f"\n[green]Analytics saved to {output}[/green]")


if __name__ == "__main__":
    main()
