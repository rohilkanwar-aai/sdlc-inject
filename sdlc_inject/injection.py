"""Pattern injection into target codebases."""

import re
import shutil
from pathlib import Path

from rich.console import Console

from .models import Pattern, Patch, ConfigValue

console = Console()


def inject_pattern(
    pattern: Pattern,
    target_dir: Path,
    output_dir: Path,
    obfuscation_level: str = "medium",
    create_commits: bool = False,
    dry_run: bool = False,
) -> None:
    """Inject a pattern into a target codebase."""
    console.print(f"[bold]Injecting pattern {pattern.id} into {target_dir}[/bold]\n")

    if not target_dir.exists():
        raise FileNotFoundError(f"Target directory not found: {target_dir}")

    # Copy target to output (unless dry run)
    if not dry_run:
        if output_dir.exists():
            console.print(f"[yellow]Warning: Output directory exists, will overwrite[/yellow]")
            shutil.rmtree(output_dir)
        shutil.copytree(target_dir, output_dir)
        console.print(f"[dim]Copied {target_dir} to {output_dir}[/dim]\n")

    # Apply file patches
    for file_inj in pattern.injection.files:
        target_path = output_dir / file_inj.path

        if dry_run:
            console.print(f"[cyan]Would modify:[/cyan] {file_inj.path}")
            for i, patch in enumerate(file_inj.patches, 1):
                console.print(f"  Patch {i}: {patch.type}")
                if patch.old:
                    preview = patch.old[:50].replace("\n", " ")
                    console.print(f"    Looking for: {preview}...")
            continue

        if not target_path.exists():
            console.print(f"[yellow]Warning: File not found, skipping: {file_inj.path}[/yellow]")
            continue

        console.print(f"[green]Patching:[/green] {file_inj.path}")

        content = target_path.read_text()
        for patch in file_inj.patches:
            content = apply_patch(content, patch)
        target_path.write_text(content)

    # Apply config changes
    for config_change in pattern.injection.config_changes:
        config_path = output_dir / config_change.file

        if dry_run:
            console.print(f"[cyan]Would modify config:[/cyan] {config_change.file}")
            continue

        if not config_path.exists():
            console.print(f"[yellow]Warning: Config not found, skipping: {config_change.file}[/yellow]")
            continue

        console.print(f"[green]Modifying config:[/green] {config_change.file}")

        content = config_path.read_text()
        for change in config_change.changes:
            content = apply_config_change(content, change)
        config_path.write_text(content)

    # Apply obfuscation
    if obfuscation_level != "none" and pattern.injection.obfuscation:
        if dry_run:
            console.print(f"[cyan]Would apply obfuscation:[/cyan] {obfuscation_level}")
        else:
            apply_obfuscation(output_dir, pattern, obfuscation_level)

    # Create git commits
    if create_commits and not dry_run:
        create_injection_commits(output_dir, pattern)

    if dry_run:
        console.print("\n[yellow]Dry run complete. No changes were made.[/yellow]")
    else:
        console.print(f"\n[green]Injection complete. Output: {output_dir}[/green]")


def apply_patch(content: str, patch: Patch) -> str:
    """Apply a single patch to content."""
    patch_type = patch.type

    if patch_type == "replace":
        if not patch.old or not patch.new:
            raise ValueError("Replace patch requires 'old' and 'new' fields")

        # Try exact match first
        if patch.old in content:
            return content.replace(patch.old, patch.new, 1)

        # Try fuzzy match (ignoring whitespace differences)
        pattern = re.escape(patch.old)
        pattern = re.sub(r'\\ +', r'\\s+', pattern)  # Allow flexible whitespace
        match = re.search(pattern, content)
        if match:
            return content[:match.start()] + patch.new + content[match.end():]

        raise ValueError(f"Could not find pattern to replace: {patch.old[:50]}...")

    elif patch_type in ("insert", "insert_after"):
        insert_content = patch.content or patch.new
        if not insert_content:
            raise ValueError("Insert patch requires 'content' or 'new' field")

        if patch.location and patch.location.startswith("line:"):
            line_num = int(patch.location[5:])
            lines = content.split("\n")
            lines.insert(line_num - 1, insert_content.rstrip("\n"))
            return "\n".join(lines)

        if patch.anchor:
            pos = content.find(patch.anchor)
            if pos == -1:
                raise ValueError(f"Anchor not found: {patch.anchor}")

            # Find end of line
            end_of_line = content.find("\n", pos + len(patch.anchor))
            if end_of_line == -1:
                end_of_line = len(content)

            return content[:end_of_line + 1] + insert_content + content[end_of_line + 1:]

        # Default: append
        if not content.endswith("\n"):
            content += "\n"
        return content + insert_content

    elif patch_type == "insert_before":
        insert_content = patch.content or patch.new
        if not insert_content or not patch.anchor:
            raise ValueError("insert_before requires 'content'/'new' and 'anchor'")

        pos = content.find(patch.anchor)
        if pos == -1:
            raise ValueError(f"Anchor not found: {patch.anchor}")

        return content[:pos] + insert_content + "\n" + content[pos:]

    elif patch_type == "delete":
        if patch.old:
            if patch.old not in content:
                raise ValueError(f"Content to delete not found: {patch.old[:50]}...")
            return content.replace(patch.old, "", 1)

        if patch.anchor:
            lines = content.split("\n")
            lines = [l for l in lines if patch.anchor not in l]
            return "\n".join(lines)

        raise ValueError("Delete patch requires 'old' or 'anchor' field")

    else:
        raise ValueError(f"Unknown patch type: {patch_type}")


def apply_config_change(content: str, change: ConfigValue) -> str:
    """Apply a config value change."""
    # Try various formats

    # Rust const: const KEY: Type = value;
    pattern = rf'(const\s+{re.escape(change.key)}\s*:\s*\w+\s*=\s*){re.escape(change.old_value)}'
    if re.search(pattern, content):
        return re.sub(pattern, rf'\g<1>{change.new_value}', content, count=1)

    # Key = value
    pattern = rf'({re.escape(change.key)}\s*=\s*){re.escape(change.old_value)}'
    if re.search(pattern, content):
        return re.sub(pattern, rf'\g<1>{change.new_value}', content, count=1)

    # YAML: key: value
    pattern = rf'({re.escape(change.key)}\s*:\s*){re.escape(change.old_value)}'
    if re.search(pattern, content):
        return re.sub(pattern, rf'\g<1>{change.new_value}', content, count=1)

    # JSON: "key": value
    pattern = rf'("{re.escape(change.key)}"\s*:\s*){re.escape(change.old_value)}'
    if re.search(pattern, content):
        return re.sub(pattern, rf'\g<1>{change.new_value}', content, count=1)

    raise ValueError(f"Could not find config key '{change.key}' with value '{change.old_value}'")


def apply_obfuscation(output_dir: Path, pattern: Pattern, level: str) -> None:
    """Apply obfuscation to injected code."""
    if not pattern.injection.obfuscation:
        return

    console.print(f"[dim]Applying {level} obfuscation...[/dim]")

    obfuscation = pattern.injection.obfuscation

    for technique in obfuscation.techniques:
        if technique.type == "comment_misdirection" and technique.content:
            console.print(f"  [dim]Would add misdirection comment[/dim]")

        elif technique.type == "rename_variable" and technique.from_ and technique.to:
            console.print(f"  [dim]Would rename {technique.from_} -> {technique.to}[/dim]")


def create_injection_commits(output_dir: Path, pattern: Pattern) -> None:
    """Create git commits for the injection."""
    try:
        import git
    except ImportError:
        console.print("[yellow]GitPython not installed, skipping commit creation[/yellow]")
        return

    try:
        repo = git.Repo(output_dir)
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(output_dir)

    # Stage all changes
    repo.git.add(A=True)

    # Create commit
    message = f"""feat: Add {pattern.name} pattern injection

Pattern: {pattern.id}
Category: {pattern.category}
Difficulty: {pattern.difficulty.estimated_human_time_hours} hours, {pattern.difficulty.frontier_model_pass_rate_percent}% pass rate
"""

    repo.index.commit(message)
    console.print("[green]Created git commit for injection[/green]")
