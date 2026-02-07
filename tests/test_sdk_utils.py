"""Tests for SDK utility functions."""

import json
import pytest

from sdlc_inject.sdk_utils import (
    SDKUsageStats,
    create_agent_options,
    extract_json_from_text,
    collect_text_from_messages,
    DEFAULT_MODEL,
)


class TestSDKUsageStats:
    """Tests for SDKUsageStats."""

    def test_initial_state(self):
        stats = SDKUsageStats()
        assert stats.total_cost_usd == 0.0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.total_tokens == 0
        assert stats.total_turns == 0
        assert stats.session_ids == []

    def test_total_tokens_property(self):
        stats = SDKUsageStats(total_input_tokens=100, total_output_tokens=50)
        assert stats.total_tokens == 150

    def test_to_dict(self):
        stats = SDKUsageStats(
            total_cost_usd=0.05,
            total_input_tokens=1000,
            total_output_tokens=500,
            total_turns=3,
        )
        d = stats.to_dict()
        assert d["total_cost_usd"] == 0.05
        assert d["total_tokens"] == 1500
        assert d["total_turns"] == 3


class TestCreateAgentOptions:
    """Tests for create_agent_options factory."""

    def test_default_options(self):
        options = create_agent_options()
        assert options.permission_mode == "bypassPermissions"

    def test_custom_options(self):
        options = create_agent_options(
            system_prompt="Test prompt",
            allowed_tools=["Read", "Grep"],
            model="claude-opus-4-20250514",
            max_turns=10,
            cwd="/tmp/test",
        )
        assert options.system_prompt == "Test prompt"
        assert options.allowed_tools == ["Read", "Grep"]
        assert options.max_turns == 10
        assert options.cwd == "/tmp/test"


class TestExtractJsonFromText:
    """Tests for extract_json_from_text helper."""

    def test_pure_json(self):
        text = '{"key": "value", "number": 42}'
        result = extract_json_from_text(text)
        assert result == {"key": "value", "number": 42}

    def test_json_with_surrounding_text(self):
        text = 'Here is the analysis:\n{"vulnerabilities": [], "summary": "none"}\nEnd.'
        result = extract_json_from_text(text)
        assert result == {"vulnerabilities": [], "summary": "none"}

    def test_no_json(self):
        text = "This text has no JSON content at all."
        result = extract_json_from_text(text)
        assert result is None

    def test_invalid_json(self):
        text = "{not valid json}"
        result = extract_json_from_text(text)
        assert result is None

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = extract_json_from_text(text)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_json_with_whitespace(self):
        text = '   \n  {"key": "value"}  \n  '
        result = extract_json_from_text(text)
        assert result == {"key": "value"}


class TestCollectTextFromMessages:
    """Tests for collect_text_from_messages."""

    def test_empty_messages(self):
        result = collect_text_from_messages([])
        assert result == ""

    def test_non_assistant_messages(self):
        # ResultMessage and other types should be skipped
        result = collect_text_from_messages(["not a message", 42])
        assert result == ""
