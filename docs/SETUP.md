# Setup and Troubleshooting Guide

This guide covers installation, configuration, and common issues when running sdlc-inject.

## Prerequisites

- Python 3.10+
- An Anthropic API key (`ANTHROPIC_API_KEY`)
- (Optional) An Exa API key (`EXA_API_KEY`) for enrichment and tool discovery

## Installation

```bash
cd sdlc-inject

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install the package (editable mode for development)
pip install -e .

# For development (adds pytest, ruff, etc.)
pip install -e ".[dev]"

# Verify installation
sdlc-inject --help
```

## Configuring API Keys

sdlc-inject needs the `ANTHROPIC_API_KEY` environment variable for any command that uses Claude (neural analysis, evaluation harness, tool discovery, enrichment).

### Option 1: `.env` file (recommended)

Create a `.env` file in the `sdlc-inject` directory:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
EXA_API_KEY=your-exa-key-here
```

The CLI loads this file automatically at startup via `python-dotenv`. It searches two locations:
1. The package directory (where `sdlc_inject/` lives) -- highest priority
2. The current working directory

### Option 2: Export in shell

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
export EXA_API_KEY=your-exa-key-here
```

Add these to your `~/.zshrc` or `~/.bashrc` to persist across sessions.

### Option 3: Inline per-command

```bash
ANTHROPIC_API_KEY=sk-ant-... sdlc-inject neural-analyze ./my-project
```

## Verifying Your Setup

```bash
# Check the CLI is installed
sdlc-inject --help

# Check patterns are loadable
sdlc-inject list

# Quick test of API connectivity (uses the Anthropic API)
sdlc-inject neural-analyze ./sdlc_inject --max-files 2 --no-enrich --max-budget 0.50
```

If the neural-analyze command works without errors, your API key and SDK are configured correctly.

## Troubleshooting

### 401 Unauthorized errors

```
Error during analysis: Client error '401 Unauthorized' for url
'https://api.anthropic.com/v1/messages'
```

**Cause:** The `ANTHROPIC_API_KEY` environment variable is not set or the API key is invalid.

**Fix:**
1. Check if the key is set:
   ```bash
   echo $ANTHROPIC_API_KEY
   ```
   If empty, the `.env` file isn't being loaded.

2. Verify the `.env` file exists and has the correct key:
   ```bash
   cat .env
   # Should show: ANTHROPIC_API_KEY=sk-ant-api03-...
   ```

3. Make sure you're running the command from the `sdlc-inject` directory (or that the `.env` file is in the package directory):
   ```bash
   cd /path/to/sdlc-inject
   sdlc-inject neural-analyze ./my-project
   ```

4. Test the key directly:
   ```bash
   python -c "
   from dotenv import load_dotenv
   import os
   load_dotenv()
   key = os.environ.get('ANTHROPIC_API_KEY', '')
   print(f'Key loaded: {bool(key)}')
   print(f'Key starts with sk-ant: {key.startswith(\"sk-ant\")}')
   "
   ```

5. If the key still doesn't load, export it directly:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
   sdlc-inject neural-analyze ./my-project
   ```

### EXA_API_KEY not set

```
Warning: EXA_API_KEY not set, enrichment disabled
```

**This is not an error** -- enrichment is optional. Without it, neural analysis still works but won't search for similar vulnerabilities or discover external tools.

To enable enrichment, add your Exa key to `.env`:
```bash
EXA_API_KEY=your-exa-key-here
```

Get an Exa API key at [exa.ai](https://exa.ai).

### ModuleNotFoundError: claude_agent_sdk

```
ModuleNotFoundError: No module named 'claude_agent_sdk'
```

**Fix:** Install the Claude Agent SDK:
```bash
pip install "claude-agent-sdk>=0.1.29"
```

Or reinstall the package which includes it as a dependency:
```bash
pip install -e .
```

### Command not found: sdlc-inject

**Fix:** Make sure your virtual environment is activated:
```bash
source .venv/bin/activate
```

Or reinstall the package:
```bash
pip install -e .
```

### Rate limit errors during neural analysis

If analysis is slow or produces warnings about rate limits, the Claude API may be throttling requests. You can:

- Use `--max-files` to reduce the number of files analyzed
- Use `--max-budget` to cap the total cost
- Use `--no-enrich` to skip Exa enrichment (fewer API calls overall)

### Tests failing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_sdk_utils.py -v
pytest tests/test_discovery.py -v
pytest tests/test_mcp_integration.py -v
pytest tests/test_neural_analyzer.py -v
```

If tests fail with import errors, reinstall:
```bash
pip install -e ".[dev]"
```

## How the Key Components Work

### Neural Analysis Pipeline

```
sdlc-inject neural-analyze <path-or-url>
```

1. **Clone** (if GitHub URL): shallow git clone to a temp directory
2. **Heuristic seed**: scans filenames for concurrency/distributed keywords to suggest starting files
3. **Agent exploration**: Claude Agent SDK with Read/Glob/Grep tools autonomously explores the codebase
4. **Structured output**: agent produces JSON with vulnerabilities, architecture summary, pattern recommendations
5. **Exa enrichment** (if enabled): searches for similar vulnerabilities and real-world postmortems
6. **Tool discovery** (if enabled): extracts which monitoring tools were used in real incidents
7. **Service config generation** (if tools discovered + output specified): Claude generates mock API specs as YAML

### Dynamic Tool Discovery Pipeline

When `--discover-tools` is enabled (default when enrichment is on):

```
Exa finds incidents
  -> Claude extracts tool names from incident text (Datadog, Incident.io, etc.)
  -> Claude generates ServiceConfig YAML for each tool
  -> YAMLs saved to service_configs/ alongside the report
```

These configs can be reviewed, edited, and passed to the evaluation harness:

```bash
sdlc-inject evaluate RACE-001 --target ./injected --output ./results \
    --mcp-mode --service-configs ./service_configs/
```

### Evaluation Harness

```
sdlc-inject evaluate <pattern> --target <codebase> --output <dir>
```

1. Creates N isolated workspace copies of the target codebase
2. Spins up N parallel Claude agents (via Agent SDK) with:
   - Read, Edit, Bash, Grep, Glob tools
   - MCP servers (hardcoded: Sentry, Slack, GitHub, PagerDuty, Prometheus)
   - Dynamic MCP servers (from --service-configs YAML directory)
3. Each agent debugs the injected bug independently
4. Records full trajectories (tool calls, reasoning, file changes)
5. Computes analytics (pass rate, failure modes, time distribution)

### ServiceConfig YAML Format

Each discovered tool gets a YAML file that looks like this:

```yaml
name: datadog
display_name: Datadog
category: monitoring
description: Infrastructure monitoring and APM
endpoints:
  - name: list_monitors
    method: GET
    path: /monitors
    description: List active monitors and alerts
    parameters:
      - name: status
        type: string
        description: Filter by monitor status
        enum: [alert, warn, ok, no_data]
      - name: limit
        type: integer
        description: Maximum results to return
    response_schema:
      type: object
      properties:
        monitors:
          type: array
    sample_response:
      monitors:
        - id: "{{random_id}}"
          name: "{{primary_error}}"
          status: alert
          created_at: "{{timestamp}}"
mock_data_hints:
  primary_error: "The main error from the pattern"
  noise_count: 3
  severity_level: high
```

Placeholders like `{{primary_error}}`, `{{random_id}}`, `{{timestamp}}` are automatically replaced with pattern-specific data at runtime.

## Common Workflows

### Analyzing a new codebase

```bash
# Full analysis with enrichment and tool discovery
sdlc-inject neural-analyze https://github.com/org/repo -o analysis.json

# Review results
cat analysis.json | python -m json.tool | head -50

# Review discovered service configs
ls service_configs/
cat service_configs/datadog.yaml
```

### Running a full evaluation

```bash
# 1. Inject a pattern
sdlc-inject inject RACE-001 --target ./cloned-repo --output ./injected

# 2. Run evaluation with all available tools
sdlc-inject evaluate RACE-001 \
    --target ./injected \
    --output ./eval-results \
    --mcp-mode \
    --service-configs ./service_configs/ \
    -n 10 \
    --max-budget 3.0

# 3. Review results
cat eval-results/run_summary.json | python -m json.tool
cat eval-results/analytics_report.md
```

### Regenerating service configs

If you want to regenerate configs with different parameters or after editing the analysis:

```bash
sdlc-inject generate-services analysis.json -o ./service_configs/ --max-tools 5
```
