# SDLC Inject

CLI tool for injecting realistic SDLC failure patterns into codebases for AI training environments. Built for creating challenging debugging scenarios that test AI agents' ability to diagnose and fix production issues.

## Features

- **20+ Failure Patterns** - Race conditions, split-brain, clock skew, coordination failures
- **Claude Agent SDK** - Agentic codebase analysis with Read/Glob/Grep tools via the Claude Agent SDK
- **Dynamic Tool Discovery** - Automatically discovers observability tools from real-world incidents and generates mock MCP servers for them
- **Multi-Pattern Injection** - Combine patterns for complex cascading failure scenarios
- **Mock MCP Servers** - Interactive Sentry, Slack, GitHub, PagerDuty (plus dynamically discovered tools)
- **Evaluation Harness** - Parallel agent testing with the Claude Agent SDK, in-process MCP servers, and cost tracking
- **Realistic Artifacts** - Generate mock SDLC tool outputs for debugging exercises
- **Progressive Incidents** - Simulate real-time incident evolution with rate limits and escalations
- **Pattern Enrichment** - Enhance patterns with real-world incident references and solutions

## Installation

```bash
# Clone and install
pip install -e .

# For development
pip install -e ".[dev]"
```

### Environment Setup

Create a `.env` file in the `sdlc-inject` directory:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
EXA_API_KEY=your-exa-key-here          # Optional, for enrichment
```

The CLI automatically loads `.env` from both the package directory and the current working directory. Alternatively, export the variables directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
export EXA_API_KEY=...
```

## Quick Start

```bash
# List available patterns
sdlc-inject list

# Analyze a codebase (agentic exploration with Claude)
sdlc-inject neural-analyze ./my-project

# Analyze a GitHub repo directly
sdlc-inject neural-analyze https://github.com/zed-industries/zed

# Inject a pattern into a codebase
sdlc-inject inject RACE-001 --target ./my-project --output ./injected

# Run parallel agent evaluation
sdlc-inject evaluate RACE-001 --target ./injected --output ./results --mcp-mode
```

## Commands

### Pattern Management

```bash
sdlc-inject list                                  # List all patterns
sdlc-inject list --category race --difficulty hard # Filter
sdlc-inject show RACE-001                          # Show details
sdlc-inject show RACE-001 --format markdown
sdlc-inject validate-catalog                       # Validate YAML files
```

### Neural Analysis (Claude Agent SDK)

The neural analyzer uses the Claude Agent SDK to give Claude direct access to codebase exploration tools. Unlike the basic `analyze` command (regex-based), Claude can follow imports, trace data flows across files, and identify cross-file vulnerabilities autonomously.

```bash
# Analyze a local codebase
sdlc-inject neural-analyze ./path/to/codebase

# Analyze a GitHub repository
sdlc-inject neural-analyze https://github.com/zed-industries/zed

# Analyze a specific branch or tag
sdlc-inject neural-analyze https://github.com/owner/repo --ref v1.0.0

# Save report (enables service config generation)
sdlc-inject neural-analyze ./path/to/codebase --output report.json

# Focus on specific vulnerability types
sdlc-inject neural-analyze ./path/to/codebase --focus race --focus coordination

# Disable tool discovery (skip extracting external tools from incidents)
sdlc-inject neural-analyze ./path/to/codebase --no-discover-tools

# Disable Exa enrichment entirely
sdlc-inject neural-analyze ./path/to/codebase --no-enrich

# Full clone and keep repo
sdlc-inject neural-analyze https://github.com/owner/repo --full --keep-clone
```

Neural analysis provides:
- **Agentic codebase exploration** - Claude reads files, greps for patterns, and follows code paths
- **Cross-file vulnerability detection** - Traces interactions between modules
- **Data flow analysis** - Maps how data moves through vulnerable code paths
- **Suggested injections** - Specific code changes that would create realistic bugs
- **Exa enrichment** - Finds similar vulnerabilities and real-world postmortems
- **Dynamic tool discovery** - Identifies which monitoring/observability tools are used in real incidents for this type of codebase, then generates mock API configs for them

### Basic Analysis (Regex-based)

```bash
sdlc-inject analyze ./path/to/codebase                  # Quick analysis
sdlc-inject analyze ./path/to/codebase --output report.json
sdlc-inject analyze ./path/to/codebase --no-ai          # Disable LLM enhancement
```

### Dynamic Service Config Generation

When neural analysis discovers external tools (e.g., Datadog, Incident.io, Grafana) from real incident data, it can generate mock API configurations for them. These configs drive the `GenericMCPServer` during evaluation.

```bash
# Generate configs from an existing analysis report
sdlc-inject generate-services report.json -o ./service_configs/

# Limit number of tools
sdlc-inject generate-services report.json -o ./service_configs/ --max-tools 3
```

Generated YAML files can be reviewed and edited before use with the evaluation harness.

### Pattern Injection

```bash
sdlc-inject inject RACE-001 --target ./my-project --output ./injected
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --obfuscation high
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --dry-run
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --commit
```

### Multi-Pattern Injection

```bash
sdlc-inject multi-list --configs-dir ./injection_configs
sdlc-inject multi-inject COMPLEX-001 --target ./my-project --output ./injected
sdlc-inject multi-inject COMPLEX-001 --target ./project --output ./out --seed 42
```

### Artifact Generation

```bash
sdlc-inject artifacts RACE-001 --output ./artifacts
sdlc-inject artifacts RACE-001 --output ./artifacts -i sentry -i slack -i logs
sdlc-inject artifacts RACE-001 --output ./artifacts -i progressive --duration 120
```

### Pattern Enrichment

```bash
sdlc-inject enrich RACE-001
sdlc-inject enrich RACE-001 --dry-run
sdlc-inject enrich RACE-001 --add-url "https://example.com/postmortem"
sdlc-inject enrich-all
```

### Grading & Validation

```bash
sdlc-inject validate RACE-001 --target ./injected --trigger-test
sdlc-inject grade-setup RACE-001 --target ./injected --output ./grading
sdlc-inject grade RACE-001 --trajectory ./agent-transcript.json
sdlc-inject env-setup RACE-001 --output ./environment --monitoring --load-generator
```

### Evaluation Harness (Claude Agent SDK)

Run multiple Claude agents in parallel to calibrate pattern difficulty and analyze success/failure modes. Agents use the Claude Agent SDK with native Read, Edit, Bash, Grep, Glob tools plus MCP servers for observability data.

```bash
# Run 10 parallel agents
sdlc-inject evaluate RACE-001 --target ./injected --output ./results -n 10

# With MCP mode (mock Sentry, Slack, GitHub, PagerDuty, Prometheus)
sdlc-inject evaluate RACE-001 --target ./injected --output ./results --mcp-mode

# With dynamic service configs from neural analysis
sdlc-inject evaluate RACE-001 --target ./injected --output ./results \
    --mcp-mode --service-configs ./service_configs/

# Temperature variations for diversity
sdlc-inject evaluate RACE-001 --target ./injected --output ./results --temperatures 0.0,0.3,0.7

# With rate limiting on MCP APIs
sdlc-inject evaluate RACE-001 --target ./injected --output ./results --mcp-mode --mcp-rate-limit 20

# Analyze collected trajectories
sdlc-inject analyze-trajectories ./results/trajectories -p RACE-001
```

**MCP Mode** provides agents with:
- 5 hardcoded mock services (Sentry, Slack, GitHub, PagerDuty, Prometheus)
- Dynamic mock services loaded from `--service-configs` YAML directory
- All services delivered as in-process SDK MCP servers
- Rate limit enforcement with exponential backoff
- Request logging for grading API efficiency

### Mock MCP Servers (Standalone)

```bash
sdlc-inject mcp-server RACE-001 --port 8080
sdlc-inject mcp-server RACE-001 --port 8080 --seed 42
```

## Architecture

```
sdlc-inject/
├── patterns/                        # Pattern YAML definitions
│   ├── race/                        # Race condition patterns
│   ├── split-brain/                 # Split-brain patterns
│   ├── clock-skew/                  # Clock skew patterns
│   └── coordination/                # Coordination patterns
├── sdlc_inject/
│   ├── cli.py                       # CLI commands
│   ├── models.py                    # Pydantic models for patterns
│   ├── catalog.py                   # Pattern catalog management
│   ├── injection.py                 # Pattern injection logic
│   ├── grading.py                   # Grading infrastructure
│   ├── environment.py               # Environment generation
│   ├── sdk_utils.py                 # Claude Agent SDK shared utilities
│   ├── analyzer/                    # Codebase analysis
│   │   ├── agent.py                 # AI-powered analyzer (regex + LLM)
│   │   ├── neural.py                # Neural analyzer (Agent SDK, agentic exploration)
│   │   ├── tools.py                 # Analysis tools
│   │   └── recommendations.py       # Pattern recommendations
│   ├── discovery/                   # Dynamic tool discovery pipeline
│   │   ├── service_config.py        # ToolProfile, ServiceConfig, YAML I/O
│   │   ├── tool_extractor.py        # Extract tools from Exa incident data
│   │   └── schema_generator.py      # Generate ServiceConfig via Claude
│   ├── enricher/                    # Pattern enrichment
│   │   ├── searcher.py              # Incident search
│   │   ├── summarizer.py            # LLM summarization
│   │   └── updater.py               # YAML file updates
│   ├── harness/                     # Evaluation harness
│   │   ├── orchestrator.py          # Parallel agent execution (Agent SDK)
│   │   ├── mcp_integration.py       # MCP server integration (static + dynamic)
│   │   ├── trajectory.py            # Agent trajectory logging
│   │   └── analytics.py             # Pass rate, failure mode analysis
│   ├── mcp_servers/                 # Mock MCP server implementations
│   │   ├── base.py                  # BaseMCPServer abstract class
│   │   ├── registry.py              # Server registry + dynamic registration
│   │   ├── generic.py               # GenericMCPServer (template-based, from ServiceConfig)
│   │   ├── sentry.py                # Mock Sentry
│   │   ├── slack.py                 # Mock Slack
│   │   ├── github.py                # Mock GitHub
│   │   ├── pagerduty.py             # Mock PagerDuty
│   │   ├── prometheus.py            # Mock Prometheus
│   │   └── rate_limiter.py          # Token bucket rate limiter
│   └── artifacts/                   # Artifact generators
└── tests/                           # Test suite
```

## Pattern Categories

| Category | Prefix | Description | Example Patterns |
|----------|--------|-------------|------------------|
| **Race Conditions** | RACE | Concurrency bugs, check-then-act | Buffer ownership race, ID generation collision |
| **Split-Brain** | SPLIT | Network partitions, data divergence | Dual master, reconnect conflicts |
| **Clock Skew** | CLOCK | Time synchronization issues | Timestamp ordering, cache expiration |
| **Coordination** | COORD | Distributed locks, consensus | Double-grant locks, CRDT merge failures |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | API key for Claude Agent SDK (neural analysis, evaluation harness, tool discovery) |
| `EXA_API_KEY` | No | API key for Exa semantic search (enrichment, tool discovery) |

## Development

```bash
pip install -e ".[dev]"
pytest                              # Run tests (59 tests)
sdlc-inject validate-catalog        # Validate all patterns
```

## End-to-End Workflow

```bash
# 1. Analyze a codebase and discover relevant tools
sdlc-inject neural-analyze https://github.com/org/repo -o report.json

# 2. (Optional) Review/edit generated service configs
ls service_configs/
# Edit YAML files if needed

# 3. Inject a recommended pattern
sdlc-inject inject RACE-001 --target ./cloned-repo --output ./injected

# 4. Run evaluation with all discovered tools available
sdlc-inject evaluate RACE-001 --target ./injected --output ./results \
    --mcp-mode --service-configs ./service_configs/ -n 10

# 5. Analyze results
sdlc-inject analyze-trajectories ./results/trajectories -p RACE-001 --output report.md
```

## Related Work

- [Dan Luu's Post-Mortems Collection](https://github.com/danluu/post-mortems)
- [Google SRE Book](https://sre.google/sre-book/)
- [AWS Post-Event Summaries](https://aws.amazon.com/premiumsupport/technology/pes/)
- Engineering blogs from Netflix, Cloudflare, GitHub, and others
- [docs/RESEARCH.md](docs/RESEARCH.md) - Full pattern taxonomy with 1000+ failure patterns
- [docs/EVALUATION_HARNESS.md](docs/EVALUATION_HARNESS.md) - Evaluation harness architecture
