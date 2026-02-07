"""Generate ServiceConfig schemas from ToolProfiles using Claude.

Takes a discovered ToolProfile and uses Claude to generate a realistic
mock API specification (ServiceConfig) that the GenericMCPServer can
use to simulate the tool during evaluation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from claude_agent_sdk import query, AssistantMessage, ResultMessage

from ..sdk_utils import create_agent_options, extract_json_from_text, collect_text_from_messages
from .service_config import ToolProfile, ServiceConfig, EndpointConfig, ParamConfig


SCHEMA_GENERATION_PROMPT = """You are designing a mock API for the tool "{display_name}" ({category}).

Description: {description}

This mock API will be used in a debugging evaluation environment where an AI agent
is debugging a production issue related to: {vulnerability_context}

Design a realistic mock REST API with 3-5 endpoints that an engineer would use
during incident response with {display_name}. Focus on endpoints that help
with debugging, triaging, and understanding production incidents.

For each endpoint, provide:
1. A tool-friendly name (snake_case, e.g. "list_incidents")
2. HTTP method and path
3. Description of what it does
4. Parameters with types
5. A realistic sample response that includes pattern-relevant data

Return a JSON object with this exact structure:
{{
  "name": "{name}",
  "display_name": "{display_name}",
  "category": "{category}",
  "description": "{description}",
  "endpoints": [
    {{
      "name": "list_incidents",
      "method": "GET",
      "path": "/incidents",
      "description": "List active incidents",
      "parameters": [
        {{"name": "status", "type": "string", "description": "Filter by status", \
"required": false, "enum": ["open", "closed", "investigating"]}}
      ],
      "response_schema": {{
        "type": "object",
        "properties": {{
          "incidents": {{"type": "array", "items": {{"type": "object"}}}}
        }}
      }},
      "sample_response": {{
        "incidents": [
          {{
            "id": "INC-001",
            "title": "{{{{primary_error}}}}",
            "status": "investigating",
            "severity": "high",
            "created_at": "2024-01-15T10:30:00Z"
          }}
        ]
      }}
    }}
  ],
  "mock_data_hints": {{
    "primary_error": "The main error message from the pattern",
    "noise_count": 3,
    "severity_level": "high"
  }}
}}

IMPORTANT for sample_response:
- Use placeholder "{{{{primary_error}}}}" for the main error that will be filled from the pattern
- Include both a "primary" entry (the real incident) and indicate noise entries should be generated
- Make the response structure match what the real {display_name} API would return
"""


class SchemaGenerator:
    """Generates ServiceConfig from ToolProfile using Claude.

    For each discovered tool, Claude designs a realistic mock API
    specification based on what the real tool's API looks like and
    what endpoints would be useful for incident debugging.
    """

    def __init__(self, model: str = "claude-opus-4-6"):
        self.model = model

    async def generate_config_async(
        self,
        tool_profile: ToolProfile,
        vulnerability_context: str = "",
    ) -> ServiceConfig | None:
        """Generate a ServiceConfig for a discovered tool.

        Args:
            tool_profile: The discovered tool to generate a config for
            vulnerability_context: Description of vulnerability types being tested

        Returns:
            ServiceConfig or None if generation fails
        """
        prompt = SCHEMA_GENERATION_PROMPT.format(
            name=tool_profile.name,
            display_name=tool_profile.display_name,
            category=tool_profile.category,
            description=tool_profile.description,
            vulnerability_context=vulnerability_context or "production debugging",
        )

        options = create_agent_options(
            model=self.model,
            max_turns=1,
        )

        all_messages: list = []
        async for message in query(prompt=prompt, options=options):
            all_messages.append(message)

        full_text = collect_text_from_messages(all_messages)
        config_data = extract_json_from_text(full_text)

        if config_data is None:
            return None

        try:
            return ServiceConfig.model_validate(config_data)
        except Exception as e:
            print(f"Warning: Failed to validate config for {tool_profile.name}: {e}")
            return None

    def generate_config(
        self,
        tool_profile: ToolProfile,
        vulnerability_context: str = "",
    ) -> ServiceConfig | None:
        """Synchronous wrapper for generate_config_async."""
        return asyncio.run(
            self.generate_config_async(tool_profile, vulnerability_context)
        )

    async def generate_configs_async(
        self,
        tool_profiles: list[ToolProfile],
        vulnerability_context: str = "",
    ) -> list[ServiceConfig]:
        """Generate ServiceConfigs for multiple tools.

        Args:
            tool_profiles: List of discovered tools
            vulnerability_context: Description of vulnerability types

        Returns:
            List of successfully generated ServiceConfig objects
        """
        configs = []
        for profile in tool_profiles:
            config = await self.generate_config_async(profile, vulnerability_context)
            if config is not None:
                configs.append(config)
        return configs

    def generate_configs(
        self,
        tool_profiles: list[ToolProfile],
        vulnerability_context: str = "",
    ) -> list[ServiceConfig]:
        """Synchronous wrapper for generate_configs_async."""
        return asyncio.run(
            self.generate_configs_async(tool_profiles, vulnerability_context)
        )
