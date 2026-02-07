"""Tests for the dynamic tool discovery and service generation pipeline."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from sdlc_inject.discovery.service_config import (
    ToolProfile,
    ServiceConfig,
    EndpointConfig,
    ParamConfig,
    load_service_configs,
    save_service_configs,
)


# ---------------------------------------------------------------------------
# ToolProfile tests
# ---------------------------------------------------------------------------


class TestToolProfile:
    def test_creation(self):
        profile = ToolProfile(
            name="datadog",
            display_name="Datadog",
            category="monitoring",
            description="Infrastructure monitoring and APM",
        )
        assert profile.name == "datadog"
        assert profile.relevance_score == 0.5  # default

    def test_to_dict(self):
        profile = ToolProfile(
            name="incident_io",
            display_name="Incident.io",
            category="incident_management",
            description="Incident management platform",
            relevance_score=0.8,
            source_urls=["https://example.com/postmortem"],
            mentioned_in_patterns=["RACE-001"],
        )
        d = profile.to_dict()
        assert d["name"] == "incident_io"
        assert d["relevance_score"] == 0.8
        assert len(d["source_urls"]) == 1
        assert d["mentioned_in_patterns"] == ["RACE-001"]

    def test_validation(self):
        """Relevance score must be 0-1."""
        with pytest.raises(Exception):
            ToolProfile(
                name="test",
                display_name="Test",
                category="other",
                description="Test",
                relevance_score=1.5,
            )


# ---------------------------------------------------------------------------
# ServiceConfig tests
# ---------------------------------------------------------------------------


class TestServiceConfig:
    def test_creation(self):
        config = ServiceConfig(
            name="datadog",
            display_name="Datadog",
            category="monitoring",
            endpoints=[
                EndpointConfig(
                    name="list_monitors",
                    path="/monitors",
                    description="List monitors",
                    parameters=[
                        ParamConfig(name="status", type="string", description="Filter by status"),
                    ],
                    sample_response={"monitors": [{"id": "1", "name": "CPU Alert"}]},
                )
            ],
        )
        assert config.name == "datadog"
        assert len(config.endpoints) == 1
        assert config.endpoints[0].parameters[0].name == "status"

    def test_yaml_roundtrip(self):
        config = ServiceConfig(
            name="grafana",
            display_name="Grafana",
            category="monitoring",
            description="Dashboard and alerting",
            endpoints=[
                EndpointConfig(
                    name="list_dashboards",
                    path="/dashboards",
                    description="List dashboards",
                    sample_response={"dashboards": []},
                )
            ],
            mock_data_hints={"primary_error": "CPU spike", "noise_count": 2},
        )
        yaml_str = config.to_yaml()
        assert "grafana" in yaml_str
        assert "list_dashboards" in yaml_str

        # Roundtrip
        restored = ServiceConfig.from_yaml(yaml_str)
        assert restored.name == "grafana"
        assert restored.display_name == "Grafana"
        assert len(restored.endpoints) == 1
        assert restored.mock_data_hints["primary_error"] == "CPU spike"

    def test_yaml_file_roundtrip(self, tmp_path):
        config = ServiceConfig(
            name="opsgenie",
            display_name="Opsgenie",
            category="alerting",
            endpoints=[],
        )
        file_path = tmp_path / "opsgenie.yaml"
        config.to_yaml_file(file_path)
        assert file_path.exists()

        restored = ServiceConfig.from_yaml_file(file_path)
        assert restored.name == "opsgenie"


# ---------------------------------------------------------------------------
# Batch I/O tests
# ---------------------------------------------------------------------------


class TestBatchIO:
    def test_save_and_load(self, tmp_path):
        configs = [
            ServiceConfig(
                name="datadog",
                display_name="Datadog",
                category="monitoring",
                endpoints=[],
            ),
            ServiceConfig(
                name="incident_io",
                display_name="Incident.io",
                category="incident_management",
                endpoints=[],
            ),
        ]

        paths = save_service_configs(configs, tmp_path)
        assert len(paths) == 2
        assert (tmp_path / "datadog.yaml").exists()
        assert (tmp_path / "incident_io.yaml").exists()

        loaded = load_service_configs(tmp_path)
        assert len(loaded) == 2
        names = {c.name for c in loaded}
        assert "datadog" in names
        assert "incident_io" in names

    def test_load_empty_dir(self, tmp_path):
        loaded = load_service_configs(tmp_path)
        assert loaded == []

    def test_load_nonexistent_dir(self):
        loaded = load_service_configs("/nonexistent/path")
        assert loaded == []


# ---------------------------------------------------------------------------
# GenericMCPServer tests
# ---------------------------------------------------------------------------


class TestGenericMCPServer:
    @pytest.fixture
    def mock_pattern(self):
        pattern = MagicMock()
        pattern.id = "RACE-001"
        pattern.name = "Test Race Condition"
        pattern.category = "race"
        pattern.subcategory = "buffer-ownership"
        pattern.description = "Test pattern"
        pattern.observable_symptoms = MagicMock()
        pattern.observable_symptoms.error_messages = ["Buffer conflict detected"]
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

    @pytest.fixture
    def sample_service_config(self):
        return ServiceConfig(
            name="datadog",
            display_name="Datadog",
            category="monitoring",
            description="Infrastructure monitoring",
            endpoints=[
                EndpointConfig(
                    name="list_monitors",
                    method="GET",
                    path="/monitors",
                    description="List active monitors",
                    parameters=[
                        ParamConfig(name="status", type="string", description="Status filter"),
                        ParamConfig(name="limit", type="integer", description="Max results"),
                    ],
                    sample_response={
                        "monitors": [
                            {
                                "id": "{{random_id}}",
                                "name": "{{primary_error}}",
                                "status": "alert",
                                "created_at": "{{timestamp}}",
                            }
                        ]
                    },
                ),
                EndpointConfig(
                    name="get_monitor",
                    method="GET",
                    path="/monitors/{monitor_id}",
                    description="Get monitor details",
                    parameters=[
                        ParamConfig(name="monitor_id", type="string", required=True),
                    ],
                    sample_response={
                        "id": "{{random_id}}",
                        "name": "{{primary_error}}",
                        "status": "alert",
                    },
                ),
            ],
            mock_data_hints={"noise_count": 2},
        )

    def test_init(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        assert server.service_name == "datadog"

    def test_get_endpoints(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        endpoints = server.get_endpoints()
        assert "GET /monitors" in endpoints
        assert "GET /monitors/{monitor_id}" in endpoints

    def test_handle_request_by_name(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        response = server.handle_request("GET", "list_monitors", {})
        assert response.status == 200
        assert "monitors" in response.body

    def test_handle_request_unknown_endpoint(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        response = server.handle_request("GET", "/nonexistent", {})
        assert response.status == 404

    def test_substitutions_applied(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        response = server.handle_request("GET", "list_monitors", {})
        monitors = response.body.get("monitors", [])
        assert len(monitors) >= 1
        # Primary entry should have the error message, not the placeholder
        primary = monitors[0]
        assert "{{primary_error}}" not in primary.get("name", "")

    def test_noise_injection(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        response = server.handle_request("GET", "list_monitors", {})
        monitors = response.body.get("monitors", [])
        # noise_count=2 + 1 primary = 3 total
        assert len(monitors) == 3

    def test_limit_filter(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        response = server.handle_request("GET", "list_monitors", {"limit": 1})
        monitors = response.body.get("monitors", [])
        assert len(monitors) == 1

    def test_deterministic_with_seed(self, sample_service_config, mock_pattern):
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        server1 = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        server2 = GenericMCPServer(
            service_config=sample_service_config,
            pattern=mock_pattern,
            seed=42,
        )
        r1 = server1.handle_request("GET", "list_monitors", {})
        r2 = server2.handle_request("GET", "list_monitors", {})
        # IDs should match since seed is the same
        assert r1.body["monitors"][0]["id"] == r2.body["monitors"][0]["id"]


# ---------------------------------------------------------------------------
# Dynamic registration tests
# ---------------------------------------------------------------------------


class TestDynamicRegistration:
    @pytest.fixture
    def mock_pattern(self):
        pattern = MagicMock()
        pattern.id = "RACE-001"
        pattern.name = "Test Race Condition"
        pattern.category = "race"
        pattern.subcategory = "buffer-ownership"
        pattern.description = "Test pattern"
        pattern.observable_symptoms = MagicMock()
        pattern.observable_symptoms.error_messages = ["Buffer conflict"]
        pattern.observable_symptoms.log_patterns = ["ERROR: conflict"]
        pattern.observable_symptoms.behavioral_symptoms = []
        pattern.observable_symptoms.metrics_anomalies = []
        pattern.injection = MagicMock()
        pattern.injection.files = []
        pattern.difficulty = MagicMock()
        pattern.difficulty.estimated_human_time_hours = 4
        pattern.difficulty.frontier_model_pass_rate_percent = 30
        pattern.difficulty.level = "hard"
        pattern.tags = []
        pattern.golden_path = None
        pattern.grading = None
        return pattern

    def test_register_dynamic_server(self, mock_pattern):
        from sdlc_inject.mcp_servers.registry import MCPServerRegistry
        from sdlc_inject.mcp_servers.generic import GenericMCPServer

        registry = MCPServerRegistry(mock_pattern, seed=42)
        initial_count = len(registry.get_available_services())

        config = ServiceConfig(
            name="datadog",
            display_name="Datadog",
            category="monitoring",
            endpoints=[
                EndpointConfig(
                    name="list_monitors",
                    path="/monitors",
                    description="List monitors",
                    sample_response={"monitors": []},
                ),
            ],
        )
        server = GenericMCPServer(
            service_config=config,
            pattern=mock_pattern,
            seed=42,
        )
        registry.register_dynamic_server("datadog", server)

        assert "datadog" in registry.get_available_services()
        assert len(registry.get_available_services()) == initial_count + 1

        # Can make requests to it
        response = registry.make_request("datadog", "GET", "list_monitors")
        assert response.status == 200

    def test_mcp_config_with_dynamic_configs(self, mock_pattern):
        from sdlc_inject.harness.mcp_integration import MCPConfig, MCPToolProvider

        svc_config = ServiceConfig(
            name="linear",
            display_name="Linear",
            category="other",
            endpoints=[
                EndpointConfig(
                    name="list_issues",
                    path="/issues",
                    description="List issues",
                    sample_response={"issues": [{"id": "LIN-1", "title": "{{primary_error}}"}]},
                ),
            ],
        )

        config = MCPConfig(seed=42, dynamic_service_configs=[svc_config])
        provider = MCPToolProvider(pattern=mock_pattern, config=config)

        # Dynamic server should be registered
        assert "linear" in provider.registry.get_available_services()

        # SDK tools should include the dynamic server
        allowed = provider.get_sdk_allowed_tools()
        assert "mcp__linear__*" in allowed

        # SDK servers should include it
        servers = provider.get_sdk_mcp_servers()
        assert "linear" in servers
