"""Data models for dynamic tool discovery and service configuration.

ToolProfile: lightweight descriptor of a discovered tool (output of Exa extraction)
ServiceConfig: full mock API specification (output of schema generation, input to GenericMCPServer)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ToolProfile -- output of discovery phase
# ---------------------------------------------------------------------------


class ToolProfile(BaseModel):
    """A tool/service discovered from Exa enrichment results.

    Represents an observability, incident management, monitoring, or
    communication tool mentioned in real-world incident reports.
    """

    name: str = Field(description="Snake_case identifier, e.g. 'incident_io', 'datadog'")
    display_name: str = Field(description="Human-readable name, e.g. 'Incident.io'")
    category: str = Field(
        description="Tool category: monitoring, incident_management, "
        "communication, logging, apm, alerting, ci_cd, other"
    )
    description: str = Field(description="1-2 sentence description of the tool")
    relevance_score: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="How relevant this tool is to the analyzed codebase (0-1)",
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="Exa URLs where this tool was mentioned",
    )
    mentioned_in_patterns: list[str] = Field(
        default_factory=list,
        description="Pattern IDs where this tool appeared in related incidents",
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# ServiceConfig -- output of schema generation phase
# ---------------------------------------------------------------------------


class ParamConfig(BaseModel):
    """Parameter definition for an endpoint."""

    name: str
    type: str = Field(default="string", description="JSON Schema type")
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[str] | None = None


class EndpointConfig(BaseModel):
    """Definition of a single API endpoint in a service."""

    name: str = Field(description="Tool-friendly name, e.g. 'list_incidents'")
    method: str = Field(default="GET", description="HTTP method")
    path: str = Field(description="API path, e.g. '/incidents'")
    description: str = Field(description="What this endpoint does")
    parameters: list[ParamConfig] = Field(default_factory=list)
    response_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema describing the response shape",
    )
    sample_response: dict[str, Any] = Field(
        default_factory=dict,
        description="Example response used as template for mock data generation",
    )


class ServiceConfig(BaseModel):
    """Full specification for a dynamically-generated mock MCP server.

    Created by the SchemaGenerator from a ToolProfile, then used by
    GenericMCPServer to instantiate a template-based mock service.

    Serializable to/from YAML for persistence and manual editing.
    """

    name: str = Field(description="Snake_case service identifier")
    display_name: str = Field(description="Human-readable name")
    category: str = Field(description="Tool category")
    description: str = Field(default="", description="Service description")
    endpoints: list[EndpointConfig] = Field(default_factory=list)
    mock_data_hints: dict[str, Any] = Field(
        default_factory=dict,
        description="Pattern-specific hints for mock data generation. "
        "Keys: primary_error, noise_count, severity_level, etc.",
    )

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.dump(
            self.model_dump(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ServiceConfig:
        """Deserialize from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> ServiceConfig:
        """Load from a YAML file."""
        path = Path(path)
        return cls.from_yaml(path.read_text())

    def to_yaml_file(self, path: str | Path) -> None:
        """Save to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml())


# ---------------------------------------------------------------------------
# Batch I/O helpers
# ---------------------------------------------------------------------------


def load_service_configs(directory: str | Path) -> list[ServiceConfig]:
    """Load all ServiceConfig YAML files from a directory.

    Args:
        directory: Path to directory containing .yaml/.yml files

    Returns:
        List of ServiceConfig objects
    """
    directory = Path(directory)
    configs = []
    if not directory.exists():
        return configs

    for path in sorted(directory.iterdir()):
        if path.suffix in (".yaml", ".yml") and path.is_file():
            try:
                configs.append(ServiceConfig.from_yaml_file(path))
            except Exception as e:
                print(f"Warning: Failed to load {path}: {e}")

    return configs


def save_service_configs(
    configs: list[ServiceConfig], directory: str | Path
) -> list[Path]:
    """Save ServiceConfig objects as YAML files in a directory.

    Args:
        configs: List of ServiceConfig objects
        directory: Output directory

    Returns:
        List of file paths written
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    paths = []
    for config in configs:
        path = directory / f"{config.name}.yaml"
        config.to_yaml_file(path)
        paths.append(path)

    return paths
