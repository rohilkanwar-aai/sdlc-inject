"""Shared utilities for Claude Agent SDK integration.

Provides common configuration, cost tracking, and structured output helpers
used by the neural analyzer and evaluation harness.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, AssistantMessage, ResultMessage


# Default model used across the codebase
DEFAULT_MODEL = "claude-sonnet-4-20250514"


@dataclass
class SDKUsageStats:
    """Aggregated usage statistics from SDK interactions."""

    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_turns: int = 0
    session_ids: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def record_result(self, result: ResultMessage) -> None:
        """Record stats from a ResultMessage."""
        if hasattr(result, "total_cost_usd") and result.total_cost_usd is not None:
            self.total_cost_usd += result.total_cost_usd
        if hasattr(result, "usage") and result.usage is not None:
            usage = result.usage
            if hasattr(usage, "input_tokens"):
                self.total_input_tokens += usage.input_tokens or 0
            if hasattr(usage, "output_tokens"):
                self.total_output_tokens += usage.output_tokens or 0
        if hasattr(result, "session_id") and result.session_id:
            self.session_ids.append(result.session_id)
        if hasattr(result, "num_turns") and result.num_turns is not None:
            self.total_turns += result.num_turns

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_turns": self.total_turns,
        }


def create_agent_options(
    *,
    system_prompt: str = "",
    allowed_tools: list[str] | None = None,
    mcp_servers: dict | None = None,
    model: str = DEFAULT_MODEL,
    max_turns: int | None = None,
    cwd: str | None = None,
    permission_mode: str = "bypassPermissions",
) -> ClaudeAgentOptions:
    """Create ClaudeAgentOptions with common defaults.

    Args:
        system_prompt: System prompt for the agent
        allowed_tools: List of tool names to enable
        mcp_servers: MCP server configurations
        model: Claude model to use
        max_turns: Maximum conversation turns
        cwd: Working directory for the agent
        permission_mode: Permission mode (bypassPermissions for automated use)

    Returns:
        Configured ClaudeAgentOptions
    """
    kwargs: dict[str, Any] = {
        "permission_mode": permission_mode,
    }

    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if allowed_tools is not None:
        kwargs["allowed_tools"] = allowed_tools
    if mcp_servers is not None:
        kwargs["mcp_servers"] = mcp_servers
    if model:
        kwargs["model"] = model
    if max_turns is not None:
        kwargs["max_turns"] = max_turns
    if cwd is not None:
        kwargs["cwd"] = cwd

    return ClaudeAgentOptions(**kwargs)


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from text that may contain surrounding prose.

    Tries direct parse first, then finds the outermost { } pair.

    Args:
        text: Text potentially containing a JSON object

    Returns:
        Parsed dict, or None if no valid JSON found
    """
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find outermost braces
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            return json.loads(text[json_start:json_end])
        except json.JSONDecodeError:
            pass

    return None


def collect_text_from_messages(messages: list) -> str:
    """Collect all text content from a list of SDK messages.

    Args:
        messages: List of SDK message objects (AssistantMessage, etc.)

    Returns:
        Concatenated text from all text blocks
    """
    texts = []
    for message in messages:
        if isinstance(message, AssistantMessage) and hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
    return "\n".join(texts)
