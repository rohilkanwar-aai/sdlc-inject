"""Trajectory schema for logging agent debugging sessions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class Outcome(Enum):
    """Outcome of an agent's debugging attempt."""
    SUCCESS = "success"          # Bug fixed correctly
    PARTIAL = "partial"          # Right direction but incomplete
    FAILURE = "failure"          # Wrong fix or no fix
    TIMEOUT = "timeout"          # Ran out of time
    ERROR = "error"              # Agent crashed or errored


class FailureModeType(Enum):
    """Types of failure modes."""
    SYMPTOM_CHASING = "symptom_chasing"      # Increased timeout, added retries
    WRONG_LAYER = "wrong_layer"              # Blamed wrong component
    PARTIAL_FIX = "partial_fix"              # Right idea, incomplete execution
    GAVE_UP = "gave_up"                      # No actionable conclusion
    HALLUCINATED_CAUSE = "hallucinated"      # Invented incorrect explanation
    INTRODUCED_BUG = "introduced_bug"        # Fix created new problem
    UNKNOWN = "unknown"


@dataclass
class ToolCall:
    """A single tool invocation by the agent."""
    timestamp: datetime
    tool_name: str              # "bash", "read_file", "edit_file", "grep"
    input_params: dict[str, Any]
    output: str
    duration_ms: int
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "input_params": self.input_params,
            "output": self.output[:1000] if len(self.output) > 1000 else self.output,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class ReasoningStep:
    """A reasoning/thinking step from the agent."""
    timestamp: datetime
    thought: str
    step_type: str = "reasoning"  # "reasoning", "planning", "reflection"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "thought": self.thought,
            "step_type": self.step_type,
        }


@dataclass
class FileChange:
    """A file modification made by the agent."""
    file_path: str
    change_type: str            # "create", "edit", "delete"
    diff: str | None = None     # Unified diff if available
    timestamp: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "diff": self.diff,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class AgentTrajectory:
    """Complete trajectory of an agent's debugging session."""

    # Identity
    trajectory_id: str
    agent_id: str
    pattern_id: str
    run_id: str

    # Timing
    start_time: datetime
    end_time: datetime | None = None

    # Agent config
    model: str = "claude-opus-4-20250514"
    temperature: float = 0.0

    # Trajectory data
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning_steps: list[ReasoningStep] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)

    # Outcome
    outcome: Outcome = Outcome.FAILURE
    outcome_reason: str = ""

    # Grading
    root_cause_identified: bool = False
    root_cause_explanation: str = ""
    tests_passed_before: bool | None = None
    tests_passed_after: bool | None = None

    # Failure analysis
    failure_mode: FailureModeType | None = None
    failure_explanation: str = ""

    @property
    def duration_seconds(self) -> float:
        """Total duration of the debugging session."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def files_read(self) -> list[str]:
        """List of files read by the agent."""
        return list(set(
            tc.input_params.get("file_path", tc.input_params.get("path", ""))
            for tc in self.tool_calls
            if tc.tool_name in ["read_file", "Read", "cat"]
            and tc.input_params.get("file_path") or tc.input_params.get("path")
        ))

    @property
    def files_modified(self) -> list[str]:
        """List of files modified by the agent."""
        return list(set(fc.file_path for fc in self.file_changes))

    @property
    def commands_run(self) -> list[str]:
        """List of bash commands run by the agent."""
        return [
            tc.input_params.get("command", "")
            for tc in self.tool_calls
            if tc.tool_name in ["bash", "Bash", "terminal"]
        ]

    @property
    def num_tool_calls(self) -> int:
        """Total number of tool calls."""
        return len(self.tool_calls)

    @property
    def num_file_reads(self) -> int:
        """Number of file read operations."""
        return sum(1 for tc in self.tool_calls if tc.tool_name in ["read_file", "Read", "cat"])

    @property
    def num_file_edits(self) -> int:
        """Number of file edit operations."""
        return sum(1 for tc in self.tool_calls if tc.tool_name in ["edit_file", "Edit", "write_file", "Write"])

    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Add a tool call to the trajectory."""
        self.tool_calls.append(tool_call)

    def add_reasoning(self, thought: str, step_type: str = "reasoning") -> None:
        """Add a reasoning step."""
        self.reasoning_steps.append(ReasoningStep(
            timestamp=datetime.now(),
            thought=thought,
            step_type=step_type,
        ))

    def add_file_change(self, file_path: str, change_type: str, diff: str | None = None) -> None:
        """Record a file change."""
        self.file_changes.append(FileChange(
            file_path=file_path,
            change_type=change_type,
            diff=diff,
            timestamp=datetime.now(),
        ))

    def finalize(self, outcome: Outcome, reason: str = "") -> None:
        """Finalize the trajectory with outcome."""
        self.end_time = datetime.now()
        self.outcome = outcome
        self.outcome_reason = reason

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "trajectory_id": self.trajectory_id,
            "agent_id": self.agent_id,
            "pattern_id": self.pattern_id,
            "run_id": self.run_id,
            "model": self.model,
            "temperature": self.temperature,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome.value,
            "outcome_reason": self.outcome_reason,
            "root_cause_identified": self.root_cause_identified,
            "root_cause_explanation": self.root_cause_explanation,
            "tests_passed_before": self.tests_passed_before,
            "tests_passed_after": self.tests_passed_after,
            "failure_mode": self.failure_mode.value if self.failure_mode else None,
            "failure_explanation": self.failure_explanation,
            "metrics": {
                "num_tool_calls": self.num_tool_calls,
                "num_file_reads": self.num_file_reads,
                "num_file_edits": self.num_file_edits,
                "files_read": self.files_read,
                "files_modified": self.files_modified,
            },
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "reasoning_steps": [rs.to_dict() for rs in self.reasoning_steps],
            "file_changes": [fc.to_dict() for fc in self.file_changes],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentTrajectory":
        """Create from dictionary."""
        trajectory = cls(
            trajectory_id=data["trajectory_id"],
            agent_id=data["agent_id"],
            pattern_id=data["pattern_id"],
            run_id=data["run_id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            model=data.get("model", "claude-opus-4-20250514"),
            temperature=data.get("temperature", 0.0),
        )

        if data.get("end_time"):
            trajectory.end_time = datetime.fromisoformat(data["end_time"])

        trajectory.outcome = Outcome(data.get("outcome", "failure"))
        trajectory.outcome_reason = data.get("outcome_reason", "")
        trajectory.root_cause_identified = data.get("root_cause_identified", False)
        trajectory.root_cause_explanation = data.get("root_cause_explanation", "")
        trajectory.tests_passed_before = data.get("tests_passed_before")
        trajectory.tests_passed_after = data.get("tests_passed_after")

        if data.get("failure_mode"):
            trajectory.failure_mode = FailureModeType(data["failure_mode"])
        trajectory.failure_explanation = data.get("failure_explanation", "")

        # Reconstruct tool calls
        for tc_data in data.get("tool_calls", []):
            trajectory.tool_calls.append(ToolCall(
                timestamp=datetime.fromisoformat(tc_data["timestamp"]),
                tool_name=tc_data["tool_name"],
                input_params=tc_data["input_params"],
                output=tc_data["output"],
                duration_ms=tc_data["duration_ms"],
                success=tc_data.get("success", True),
                error=tc_data.get("error"),
            ))

        return trajectory
