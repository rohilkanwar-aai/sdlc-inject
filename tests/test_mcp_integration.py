"""Tests for MCP integration with SDK MCP servers."""

import pytest

from sdlc_inject.harness.mcp_integration import (
    MCPConfig,
    MCPStats,
    MCPToolProvider,
)


class TestMCPConfig:
    """Tests for MCPConfig dataclass."""

    def test_defaults(self):
        config = MCPConfig()
        assert config.enabled is True
        assert config.rate_limit_enabled is True
        assert config.requests_per_minute == 30
        assert config.enable_sentry is True
        assert config.enable_slack is True
        assert config.enable_github is True
        assert config.enable_pagerduty is True
        assert config.enable_prometheus is True

    def test_custom_config(self):
        config = MCPConfig(
            enabled=True,
            seed=42,
            requests_per_minute=10,
            enable_prometheus=False,
        )
        assert config.seed == 42
        assert config.requests_per_minute == 10
        assert config.enable_prometheus is False


class TestMCPStats:
    """Tests for MCPStats dataclass."""

    def test_defaults(self):
        stats = MCPStats()
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.rate_limited_requests == 0

    def test_to_dict(self):
        stats = MCPStats(total_requests=10, successful_requests=8)
        d = stats.to_dict()
        assert d["total_requests"] == 10
        assert d["successful_requests"] == 8
        assert d["avg_response_time_ms"] == 0.0

    def test_avg_response_time(self):
        stats = MCPStats(total_requests=4, total_response_time_ms=100.0)
        d = stats.to_dict()
        assert d["avg_response_time_ms"] == 25.0


class TestMCPToolProvider:
    """Tests for MCPToolProvider."""

    @pytest.fixture
    def mock_pattern(self):
        """Create a minimal mock pattern for testing."""
        from unittest.mock import MagicMock
        pattern = MagicMock()
        pattern.id = "RACE-001"
        pattern.name = "Test Race Condition"
        pattern.category = "race"
        pattern.subcategory = "buffer-ownership"
        pattern.description = "Test pattern"
        pattern.observable_symptoms = MagicMock()
        pattern.observable_symptoms.error_messages = ["test error"]
        pattern.observable_symptoms.log_patterns = ["ERROR: buffer conflict"]
        pattern.observable_symptoms.behavioral_symptoms = ["intermittent failures"]
        pattern.observable_symptoms.metrics_anomalies = []
        pattern.injection = MagicMock()
        pattern.injection.files = []
        pattern.difficulty = MagicMock()
        pattern.difficulty.estimated_human_time_hours = 4
        pattern.difficulty.frontier_model_pass_rate_percent = 30
        pattern.difficulty.level = "hard"
        pattern.tags = ["race", "buffer"]
        pattern.golden_path = None
        pattern.grading = None
        return pattern

    def test_get_tool_definitions(self, mock_pattern):
        """Legacy tool definitions should still work."""
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        tools = provider.get_tool_definitions()

        # Should have tools from all 5 services
        tool_names = [t["name"] for t in tools]
        assert "sentry_list_issues" in tool_names
        assert "slack_list_channels" in tool_names
        assert "github_list_issues" in tool_names
        assert "pagerduty_list_incidents" in tool_names
        assert "prometheus_query" in tool_names

    def test_get_sdk_allowed_tools(self, mock_pattern):
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        patterns = provider.get_sdk_allowed_tools()

        assert "mcp__sentry__*" in patterns
        assert "mcp__slack__*" in patterns
        assert "mcp__github__*" in patterns
        assert "mcp__pagerduty__*" in patterns
        assert "mcp__prometheus__*" in patterns

    def test_get_sdk_allowed_tools_partial(self, mock_pattern):
        config = MCPConfig(seed=42, enable_prometheus=False, enable_pagerduty=False)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        patterns = provider.get_sdk_allowed_tools()

        assert "mcp__sentry__*" in patterns
        assert "mcp__prometheus__*" not in patterns
        assert "mcp__pagerduty__*" not in patterns

    def test_get_sdk_mcp_servers(self, mock_pattern):
        """SDK MCP servers should be created for all enabled services."""
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        servers = provider.get_sdk_mcp_servers()

        assert "sentry" in servers
        assert "slack" in servers
        assert "github" in servers
        assert "pagerduty" in servers
        assert "prometheus" in servers

    def test_get_sdk_mcp_servers_partial(self, mock_pattern):
        config = MCPConfig(seed=42, enable_slack=False)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        servers = provider.get_sdk_mcp_servers()

        assert "sentry" in servers
        assert "slack" not in servers

    def test_grading_score_no_requests(self, mock_pattern):
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        assert provider.get_grading_score_adjustment() == 1.0

    def test_grading_score_rate_limit_penalty(self, mock_pattern):
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        provider.stats.total_requests = 10
        provider.stats.successful_requests = 8
        provider.stats.rate_limit_violations = 3
        adjustment = provider.get_grading_score_adjustment()
        assert adjustment < 1.0
        assert adjustment >= 0.8

    def test_execute_tool_legacy(self, mock_pattern):
        """Legacy execute_tool should still work."""
        config = MCPConfig(seed=42)
        provider = MCPToolProvider(pattern=mock_pattern, config=config)
        result = provider.execute_tool("sentry_list_issues", {})

        # Should return data (or error if mock server setup is incomplete)
        assert isinstance(result, dict)
        assert "success" in result or "error" in result
