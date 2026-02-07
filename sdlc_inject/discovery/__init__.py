"""Dynamic tool discovery and MCP server generation.

This package provides:
- Tool discovery from Exa enrichment results (extracting which observability,
  incident management, and communication tools are mentioned in postmortems)
- Schema generation (using Claude to create ServiceConfig for discovered tools)
- YAML-serializable config models for persisting and reusing service definitions
"""

from .service_config import (
    ToolProfile,
    ServiceConfig,
    EndpointConfig,
    ParamConfig,
    load_service_configs,
    save_service_configs,
)
from .tool_extractor import ToolExtractor
from .schema_generator import SchemaGenerator

__all__ = [
    "ToolProfile",
    "ServiceConfig",
    "EndpointConfig",
    "ParamConfig",
    "ToolExtractor",
    "SchemaGenerator",
    "load_service_configs",
    "save_service_configs",
]
