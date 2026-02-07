"""Orchestrator for running parallel agent evaluations using Claude Agent SDK."""

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from ..sdk_utils import SDKUsageStats, create_agent_options, DEFAULT_MODEL
from .trajectory import AgentTrajectory, Outcome, ToolCall
from .analytics import AnalyticsPipeline, AnalyticsResult
from .mcp_integration import MCPConfig, MCPToolProvider, MCPStats


@dataclass
class EvaluationConfig:
    """Configuration for an evaluation run."""

    pattern_id: str
    target_codebase: Path
    artifacts_dir: Path | None = None
    num_agents: int = 10
    max_time_per_agent: int = 3600      # seconds
    model: str = DEFAULT_MODEL
    temperatures: list[float] = field(default_factory=lambda: [0.0])
    task_prompt: str | None = None      # If None, generated from pattern
    max_budget_per_agent: float = 2.0   # USD per agent
    # MCP mode configuration
    mcp_config: MCPConfig | None = None  # If set, enables MCP server mode
    pattern: "Pattern | None" = None     # Full pattern object for MCP mode


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
    mcp_stats: MCPStats | None = None
    total_cost_usd: float = 0.0

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
            "total_cost_usd": self.total_cost_usd,
            "analytics": self.analytics.to_dict() if self.analytics else None,
            "mcp_stats": self.mcp_stats.to_dict() if self.mcp_stats else None,
        }


class AgentRunner:
    """Runs a single Claude agent using the Agent SDK.

    Replaces the previous hand-rolled loop with regex-based tool parsing.
    The SDK handles the full agentic loop: tool execution, context management,
    and iterative reasoning.
    """

    def __init__(
        self,
        workspace_dir: Path,
        artifacts_dir: Path | None,
        model: str,
        temperature: float,
        timeout: int = 3600,
        max_budget_usd: float = 2.0,
        mcp_provider: MCPToolProvider | None = None,
    ):
        self.workspace_dir = workspace_dir
        self.artifacts_dir = artifacts_dir
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_budget_usd = max_budget_usd
        self.mcp_provider = mcp_provider
        self.usage_stats = SDKUsageStats()

    async def run(
        self,
        task_prompt: str,
        trajectory: AgentTrajectory,
    ) -> AgentTrajectory:
        """
        Run the agent on the debugging task using the Claude Agent SDK.

        The SDK handles the full agentic loop including tool execution.
        We stream messages to record tool calls and reasoning in the trajectory.
        """
        # Build SDK options
        allowed_tools = ["Read", "Edit", "Bash", "Grep", "Glob"]

        mcp_servers = {}
        if self.mcp_provider:
            mcp_servers = self.mcp_provider.get_sdk_mcp_servers()
            allowed_tools.extend(self.mcp_provider.get_sdk_allowed_tools())

        system_prompt = self._build_system_prompt()

        options = create_agent_options(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
            model=self.model,
            max_turns=50,
            max_budget_usd=self.max_budget_usd,
            cwd=str(self.workspace_dir),
        )

        try:
            async for message in query(prompt=task_prompt, options=options):
                if isinstance(message, AssistantMessage) and hasattr(message, "content"):
                    for block in message.content:
                        # Record tool use
                        if hasattr(block, "name") and hasattr(block, "id"):
                            tool_input = (
                                block.input if hasattr(block, "input") else {}
                            )
                            trajectory.add_tool_call(ToolCall(
                                timestamp=datetime.now(),
                                tool_name=block.name,
                                input_params=tool_input if isinstance(tool_input, dict) else {},
                                output="",  # Output comes in ToolResultBlock
                                duration_ms=0,
                                success=True,
                            ))
                        # Record reasoning/thinking
                        elif hasattr(block, "thinking"):
                            trajectory.add_reasoning(
                                block.thinking, step_type="thinking"
                            )
                        # Record text output
                        elif hasattr(block, "text") and block.text:
                            trajectory.add_reasoning(
                                block.text[:500], step_type="reasoning"
                            )

                elif isinstance(message, ResultMessage):
                    self.usage_stats.record_result(message)
                    # Determine outcome
                    outcome = await self._evaluate_outcome(trajectory)
                    trajectory.finalize(outcome, "Agent completed via SDK")

        except Exception as e:
            trajectory.finalize(Outcome.ERROR, str(e))

        # If not finalized yet (e.g., no ResultMessage received)
        if trajectory.end_time is None:
            trajectory.finalize(Outcome.TIMEOUT, "Agent did not produce result")

        return trajectory

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the agent."""
        artifacts_hint = ""
        if self.artifacts_dir:
            artifacts_hint = f"\nDebugging artifacts are at: {self.artifacts_dir}"

        return f"""You are a senior software engineer debugging a production issue.

The codebase is located at: {self.workspace_dir}{artifacts_hint}

Your goal is to:
1. Understand the symptoms from the artifacts
2. Reproduce the issue
3. Find the root cause
4. Implement a fix
5. Verify the fix works

Be methodical. Read relevant files before making changes.
When you believe you've fixed the issue, provide a summary of what you found and fixed."""

    async def _evaluate_outcome(self, trajectory: AgentTrajectory) -> Outcome:
        """Evaluate the outcome of the debugging attempt."""
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
        """Clean up resources (no-op for SDK-based runner)."""
        pass


class Orchestrator:
    """Orchestrates parallel agent evaluation runs.

    Uses the Claude Agent SDK for agent execution. Authentication is handled
    by the SDK via the ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self):
        """Initialize the orchestrator.

        The SDK handles API key management via ANTHROPIC_API_KEY env var.
        """
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable required. "
                "The Claude Agent SDK reads it automatically."
            )

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
        mcp_providers: list[MCPToolProvider] = []

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

            # Create MCP provider if MCP mode is enabled
            mcp_provider = None
            if config.mcp_config and config.mcp_config.enabled and config.pattern:
                mcp_provider = MCPToolProvider(
                    pattern=config.pattern,
                    config=config.mcp_config,
                )
                mcp_providers.append(mcp_provider)

            runner = AgentRunner(
                workspace_dir=workspace,
                artifacts_dir=config.artifacts_dir,
                model=config.model,
                temperature=temp,
                timeout=config.max_time_per_agent,
                max_budget_usd=config.max_budget_per_agent,
                mcp_provider=mcp_provider,
            )

            tasks.append(self._run_agent(runner, task_prompt, trajectory))

        # Wait for all agents
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results and costs
        for result in results:
            if isinstance(result, Exception):
                run.errors.append(str(result))
            elif isinstance(result, AgentTrajectory):
                run.trajectories.append(result)

        # Aggregate costs from all runners
        # (Cost tracking is embedded in each runner's usage_stats)

        run.end_time = datetime.now()

        # Aggregate MCP stats if MCP mode was enabled
        if mcp_providers:
            run.mcp_stats = MCPStats()
            for provider in mcp_providers:
                stats = provider.stats
                run.mcp_stats.total_requests += stats.total_requests
                run.mcp_stats.successful_requests += stats.successful_requests
                run.mcp_stats.rate_limited_requests += stats.rate_limited_requests
                run.mcp_stats.failed_requests += stats.failed_requests
                run.mcp_stats.rate_limit_violations += stats.rate_limit_violations
                run.mcp_stats.total_response_time_ms += stats.total_response_time_ms
                for service, count in stats.requests_by_service.items():
                    run.mcp_stats.requests_by_service[service] = (
                        run.mcp_stats.requests_by_service.get(service, 0) + count
                    )

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

When you have fixed the issue, provide a summary of what you found and fixed."""

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
