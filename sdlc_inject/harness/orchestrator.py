"""Orchestrator for running parallel agent evaluations."""

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .trajectory import AgentTrajectory, Outcome, ToolCall
from .analytics import AnalyticsPipeline, AnalyticsResult


@dataclass
class EvaluationConfig:
    """Configuration for an evaluation run."""
    pattern_id: str
    target_codebase: Path
    artifacts_dir: Path | None = None
    num_agents: int = 10
    max_time_per_agent: int = 3600      # seconds
    model: str = "claude-sonnet-4-20250514"
    temperatures: list[float] = field(default_factory=lambda: [0.0])
    task_prompt: str | None = None      # If None, generated from pattern


@dataclass
class EvaluationRun:
    """Result of an evaluation run."""
    run_id: str
    config: EvaluationConfig
    start_time: datetime
    end_time: datetime | None = None
    trajectories: list[AgentTrajectory] = field(default_factory=list)
    analytics: AnalyticsResult | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pattern_id": self.config.pattern_id,
            "num_agents": self.config.num_agents,
            "model": self.config.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "num_trajectories": len(self.trajectories),
            "num_errors": len(self.errors),
            "analytics": self.analytics.to_dict() if self.analytics else None,
        }


class AgentRunner:
    """Runs a single Claude agent with tool access."""

    def __init__(
        self,
        workspace_dir: Path,
        artifacts_dir: Path | None,
        model: str,
        temperature: float,
        api_key: str,
        timeout: int = 3600,
    ):
        self.workspace_dir = workspace_dir
        self.artifacts_dir = artifacts_dir
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=120.0)

    async def run(
        self,
        task_prompt: str,
        trajectory: AgentTrajectory,
    ) -> AgentTrajectory:
        """
        Run the agent on the debugging task.

        This is a simplified implementation that makes API calls directly.
        For production, this should use the Claude Agent SDK with proper
        tool execution.
        """
        system_prompt = self._build_system_prompt()
        messages = [{"role": "user", "content": task_prompt}]

        start_time = datetime.now()
        max_iterations = 50  # Prevent infinite loops

        try:
            for iteration in range(max_iterations):
                # Check timeout
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.timeout:
                    trajectory.finalize(Outcome.TIMEOUT, "Exceeded time limit")
                    break

                # Call Claude
                response = await self._call_claude(system_prompt, messages)

                # Check if agent is done
                if self._is_task_complete(response):
                    # Evaluate outcome
                    outcome = await self._evaluate_outcome(trajectory)
                    trajectory.finalize(outcome, "Task completed")
                    break

                # Extract and execute tool calls
                tool_calls = self._extract_tool_calls(response)
                if not tool_calls:
                    # No tool calls, agent might be stuck or done
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": "Please continue debugging or indicate if you've fixed the issue."
                    })
                    continue

                # Execute tools and record in trajectory
                tool_results = []
                for tool_call in tool_calls:
                    result = await self._execute_tool(tool_call, trajectory)
                    tool_results.append(result)

                # Add to conversation
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": f"Tool results:\n{json.dumps(tool_results, indent=2)}"
                })

            else:
                # Exceeded max iterations
                trajectory.finalize(Outcome.TIMEOUT, "Exceeded iteration limit")

        except Exception as e:
            trajectory.finalize(Outcome.ERROR, str(e))

        return trajectory

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the agent."""
        return f"""You are a senior software engineer debugging a production issue.

You have access to the following tools:
- read_file(path): Read contents of a file
- edit_file(path, old_content, new_content): Edit a file
- bash(command): Run a shell command
- grep(pattern, path): Search for pattern in files

The codebase is located at: {self.workspace_dir}
{"Debugging artifacts are at: " + str(self.artifacts_dir) if self.artifacts_dir else ""}

Your goal is to:
1. Understand the symptoms from the artifacts
2. Reproduce the issue
3. Find the root cause
4. Implement a fix
5. Verify the fix works

Be methodical. Read relevant files before making changes.
When you believe you've fixed the issue, state "TASK COMPLETE" with a summary."""

    async def _call_claude(self, system: str, messages: list[dict]) -> str:
        """Call Claude API."""
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
            "temperature": self.temperature,
        }

        response = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        return data["content"][0]["text"]

    def _extract_tool_calls(self, response: str) -> list[dict]:
        """Extract tool calls from response (simplified parsing)."""
        # This is a simplified implementation
        # In production, use proper tool_use blocks from Claude
        tool_calls = []

        # Look for patterns like: read_file("path") or bash("command")
        import re

        # Pattern for read_file
        for match in re.finditer(r'read_file\(["\']([^"\']+)["\']\)', response):
            tool_calls.append({"tool": "read_file", "path": match.group(1)})

        # Pattern for bash
        for match in re.finditer(r'bash\(["\']([^"\']+)["\']\)', response):
            tool_calls.append({"tool": "bash", "command": match.group(1)})

        # Pattern for grep
        for match in re.finditer(r'grep\(["\']([^"\']+)["\'],\s*["\']([^"\']+)["\']\)', response):
            tool_calls.append({"tool": "grep", "pattern": match.group(1), "path": match.group(2)})

        return tool_calls

    async def _execute_tool(self, tool_call: dict, trajectory: AgentTrajectory) -> dict:
        """Execute a tool call and record it."""
        start = datetime.now()
        result = {"success": False, "output": ""}

        try:
            if tool_call["tool"] == "read_file":
                path = self.workspace_dir / tool_call["path"]
                if path.exists():
                    result["output"] = path.read_text()[:10000]
                    result["success"] = True
                else:
                    result["output"] = f"File not found: {tool_call['path']}"

            elif tool_call["tool"] == "bash":
                import subprocess
                proc = subprocess.run(
                    tool_call["command"],
                    shell=True,
                    cwd=self.workspace_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result["output"] = proc.stdout + proc.stderr
                result["success"] = proc.returncode == 0

            elif tool_call["tool"] == "grep":
                import subprocess
                proc = subprocess.run(
                    ["grep", "-r", tool_call["pattern"], tool_call["path"]],
                    cwd=self.workspace_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result["output"] = proc.stdout
                result["success"] = True

        except Exception as e:
            result["output"] = str(e)

        # Record in trajectory
        duration = int((datetime.now() - start).total_seconds() * 1000)
        trajectory.add_tool_call(ToolCall(
            timestamp=start,
            tool_name=tool_call["tool"],
            input_params=tool_call,
            output=result["output"][:1000],
            duration_ms=duration,
            success=result["success"],
        ))

        return result

    def _is_task_complete(self, response: str) -> bool:
        """Check if agent indicates task is complete."""
        return "TASK COMPLETE" in response.upper()

    async def _evaluate_outcome(self, trajectory: AgentTrajectory) -> Outcome:
        """Evaluate the outcome of the debugging attempt."""
        # Run tests if available
        import subprocess

        test_commands = [
            "cargo test",
            "pytest",
            "npm test",
            "go test ./...",
        ]

        for cmd in test_commands:
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=self.workspace_dir,
                    capture_output=True,
                    timeout=60,
                )
                if proc.returncode == 0:
                    trajectory.tests_passed_after = True
                    return Outcome.SUCCESS
                else:
                    trajectory.tests_passed_after = False
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        # If no tests ran successfully, check if files were modified
        if trajectory.file_changes:
            return Outcome.PARTIAL

        return Outcome.FAILURE

    async def close(self):
        await self.client.aclose()


class Orchestrator:
    """Orchestrates parallel agent evaluation runs."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

    async def run_evaluation(
        self,
        config: EvaluationConfig,
        output_dir: Path | None = None,
    ) -> EvaluationRun:
        """
        Run a full evaluation with multiple agents.

        Args:
            config: Evaluation configuration
            output_dir: Optional directory to save results

        Returns:
            EvaluationRun with all trajectories and analytics
        """
        run_id = f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        run = EvaluationRun(
            run_id=run_id,
            config=config,
            start_time=datetime.now(),
        )

        # Create isolated workspaces for each agent
        workspaces = await self._create_workspaces(config, run_id)

        # Build task prompt
        task_prompt = config.task_prompt or self._build_task_prompt(config)

        # Distribute temperatures across agents
        agent_temps = []
        for i in range(config.num_agents):
            temp = config.temperatures[i % len(config.temperatures)]
            agent_temps.append(temp)

        # Run agents in parallel
        tasks = []
        for i, (workspace, temp) in enumerate(zip(workspaces, agent_temps)):
            agent_id = f"agent-{i:03d}"
            trajectory = AgentTrajectory(
                trajectory_id=f"{run_id}-{agent_id}",
                agent_id=agent_id,
                pattern_id=config.pattern_id,
                run_id=run_id,
                start_time=datetime.now(),
                model=config.model,
                temperature=temp,
            )

            runner = AgentRunner(
                workspace_dir=workspace,
                artifacts_dir=config.artifacts_dir,
                model=config.model,
                temperature=temp,
                api_key=self.api_key,
                timeout=config.max_time_per_agent,
            )

            tasks.append(self._run_agent(runner, task_prompt, trajectory))

        # Wait for all agents
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for result in results:
            if isinstance(result, Exception):
                run.errors.append(str(result))
            elif isinstance(result, AgentTrajectory):
                run.trajectories.append(result)

        run.end_time = datetime.now()

        # Run analytics
        pipeline = AnalyticsPipeline()
        run.analytics = pipeline.analyze(
            run.trajectories,
            config.pattern_id,
            run_id,
        )

        # Save results
        if output_dir:
            await self._save_results(run, output_dir)

        # Cleanup workspaces
        await self._cleanup_workspaces(workspaces)

        return run

    async def _run_agent(
        self,
        runner: AgentRunner,
        task_prompt: str,
        trajectory: AgentTrajectory,
    ) -> AgentTrajectory:
        """Run a single agent (wrapper for error handling)."""
        try:
            result = await runner.run(task_prompt, trajectory)
            return result
        finally:
            await runner.close()

    async def _create_workspaces(
        self,
        config: EvaluationConfig,
        run_id: str,
    ) -> list[Path]:
        """Create isolated workspace copies for each agent."""
        import tempfile

        base_temp = Path(tempfile.mkdtemp(prefix=f"sdlc-eval-{run_id}-"))
        workspaces = []

        for i in range(config.num_agents):
            workspace = base_temp / f"agent-{i:03d}"
            shutil.copytree(config.target_codebase, workspace)
            workspaces.append(workspace)

        return workspaces

    async def _cleanup_workspaces(self, workspaces: list[Path]) -> None:
        """Clean up workspace directories."""
        for workspace in workspaces:
            # Get parent (base temp dir)
            parent = workspace.parent
            if parent.name.startswith("sdlc-eval-"):
                shutil.rmtree(parent, ignore_errors=True)
                break  # Only need to delete parent once

    def _build_task_prompt(self, config: EvaluationConfig) -> str:
        """Build task prompt from pattern configuration."""
        return f"""Debug the following issue in this codebase.

Pattern: {config.pattern_id}

The codebase has a bug that causes intermittent failures. Your task is to:
1. Review the debugging artifacts (logs, error reports) if available
2. Identify the root cause of the issue
3. Implement a fix
4. Verify your fix resolves the issue

When you have fixed the issue, respond with "TASK COMPLETE" and explain what you found and fixed."""

    async def _save_results(self, run: EvaluationRun, output_dir: Path) -> None:
        """Save evaluation results to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save run summary
        with open(output_dir / "run_summary.json", "w") as f:
            json.dump(run.to_dict(), f, indent=2)

        # Save individual trajectories
        trajectories_dir = output_dir / "trajectories"
        trajectories_dir.mkdir(exist_ok=True)
        for t in run.trajectories:
            with open(trajectories_dir / f"{t.trajectory_id}.json", "w") as f:
                f.write(t.to_json())

        # Save analytics
        if run.analytics:
            with open(output_dir / "analytics.json", "w") as f:
                f.write(run.analytics.to_json())

            with open(output_dir / "analytics_report.md", "w") as f:
                f.write(run.analytics.to_markdown())


async def run_evaluation(
    pattern_id: str,
    target_codebase: Path,
    num_agents: int = 10,
    output_dir: Path | None = None,
    **kwargs,
) -> EvaluationRun:
    """
    Convenience function to run an evaluation.

    Args:
        pattern_id: ID of the pattern being evaluated
        target_codebase: Path to the injected codebase
        num_agents: Number of parallel agents
        output_dir: Optional output directory
        **kwargs: Additional config options

    Returns:
        EvaluationRun with results
    """
    config = EvaluationConfig(
        pattern_id=pattern_id,
        target_codebase=target_codebase,
        num_agents=num_agents,
        **kwargs,
    )

    orchestrator = Orchestrator()
    return await orchestrator.run_evaluation(config, output_dir)
