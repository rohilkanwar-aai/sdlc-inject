# SDLC Inject

CLI tool for injecting realistic SDLC failure patterns into codebases for AI training environments. Built for creating challenging debugging scenarios that test AI agents' ability to diagnose and fix production issues.

## Features

- **20+ Failure Patterns** - Race conditions, split-brain, clock skew, coordination failures
- **Codebase Analyzer** - AI-powered analysis to recommend optimal patterns for any codebase
- **Realistic Artifacts** - Generate mock Sentry, Slack, PagerDuty, and other SDLC tool outputs
- **Progressive Incidents** - Simulate real-time incident evolution with rate limits and escalations
- **Pattern Enrichment** - Enhance patterns with real-world incident references and solutions

## Installation

```bash
pip install -e .

# For development
pip install -e ".[dev]"
```

## Quick Start

```bash
# List available patterns
sdlc-inject list

# Analyze a codebase for pattern recommendations
sdlc-inject analyze ./my-project

# Show pattern details
sdlc-inject show RACE-001

# Inject a pattern
sdlc-inject inject RACE-001 --target ./my-project --output ./injected

# Generate debugging artifacts
sdlc-inject artifacts RACE-001 --output ./artifacts
```

## Commands

### Pattern Management

```bash
# List all patterns
sdlc-inject list

# Filter by category or difficulty
sdlc-inject list --category race --difficulty hard

# Show pattern details
sdlc-inject show RACE-001
sdlc-inject show RACE-001 --format markdown

# Validate pattern YAML files
sdlc-inject validate-catalog
```

### Codebase Analysis

```bash
# Analyze a codebase and get pattern recommendations
sdlc-inject analyze ./path/to/codebase

# Save analysis report to JSON
sdlc-inject analyze ./path/to/codebase --output report.json --top-k 10

# Quick scan without full analysis
sdlc-inject analyze ./path/to/codebase --quick

# Disable AI-enhanced analysis
sdlc-inject analyze ./path/to/codebase --no-ai
```

The analyzer scans for:
- **Concurrency patterns**: async/await, threads, mutexes, channels
- **Distributed patterns**: RPC, message queues, databases, caches
- **State management**: global state, caches, sessions
- **Time-sensitive code**: timestamps, timeouts, TTLs

### Pattern Injection

```bash
# Inject a pattern into a codebase
sdlc-inject inject RACE-001 --target ./my-project --output ./injected

# With obfuscation (to prevent trivial detection)
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --obfuscation high

# Dry run to see what would change
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --dry-run

# Create git commits for each injection step
sdlc-inject inject RACE-001 --target ./my-project --output ./injected --commit
```

### Artifact Generation

```bash
# Generate all artifact types
sdlc-inject artifacts RACE-001 --output ./artifacts

# Generate specific artifact types
sdlc-inject artifacts RACE-001 --output ./artifacts -i sentry -i slack -i logs

# Generate progressive incident timeline
sdlc-inject artifacts RACE-001 --output ./artifacts -i progressive --duration 120
```

### Pattern Enrichment

```bash
# Enrich a pattern with real-world incidents
sdlc-inject enrich RACE-001

# Preview changes without writing
sdlc-inject enrich RACE-001 --dry-run

# Add a specific incident URL
sdlc-inject enrich RACE-001 --add-url "https://example.com/postmortem"

# Enrich all patterns
sdlc-inject enrich-all
sdlc-inject enrich-all --category race --dry-run
```

### Grading & Validation

```bash
# Validate an injected pattern
sdlc-inject validate RACE-001 --target ./injected --trigger-test

# Generate grading infrastructure
sdlc-inject grade-setup RACE-001 --target ./injected --output ./grading

# Grade an agent's debugging trajectory
sdlc-inject grade RACE-001 --trajectory ./agent-transcript.json

# Generate environment files (Docker, monitoring)
sdlc-inject env-setup RACE-001 --output ./environment --monitoring --load-generator
```

## Pattern Categories

| Category | Prefix | Description | Example Patterns |
|----------|--------|-------------|------------------|
| **Race Conditions** | RACE | Concurrency bugs, check-then-act | Buffer ownership race, ID generation collision |
| **Split-Brain** | SPLIT | Network partitions, data divergence | Dual master, reconnect conflicts |
| **Clock Skew** | CLOCK | Time synchronization issues | Timestamp ordering, cache expiration |
| **Coordination** | COORD | Distributed locks, consensus | Double-grant locks, CRDT merge failures |

## Artifact Types

| Type | Description | Files Generated |
|------|-------------|-----------------|
| **sentry** | Error reports, stack traces, breadcrumbs | `issue.json`, `events.json`, `breadcrumbs.json` |
| **slack** | Incident channel messages, threads | `channel_export.json`, `incident_transcript.md` |
| **linear** | Bug tickets, comments, activity | `issue.json`, `comments.json`, `issue.md` |
| **pagerduty** | Alerts, incidents, timelines | `incident.json`, `alerts.json` |
| **logs** | Structured and plaintext app logs | `app.jsonl`, `app.log`, `errors.jsonl` |
| **metrics** | Prometheus snapshots, Grafana dashboards | `prometheus_snapshot.json`, `grafana_dashboard.json` |
| **github** | Issues, PRs, comments, commits | `issue.json`, `pull_request.json`, `issue_thread.md` |
| **progressive** | Real-time incident evolution | See below |

### Progressive Incident Simulation

Generates a complete incident timeline with real-time updates:

```bash
sdlc-inject artifacts RACE-001 --output ./artifacts -i progressive --duration 120
```

**Generated files:**

| File | Description |
|------|-------------|
| `incident_timeline.json` | Phase-by-phase incident progression |
| `metrics_stream.jsonl` | Minute-by-minute metrics degradation |
| `log_stream.jsonl` | Time-ordered log entries |
| `rate_limit_events.json` | 429 errors with Retry-After headers |
| `webhook_events.json` | Events from Prometheus, PagerDuty, Slack |
| `escalation_chain.json` | PagerDuty escalation levels |
| `status_page_updates.json` | Statuspage.io style updates |
| `runbook_execution.json` | Step-by-step runbook execution |
| `incident_report.md` | Post-incident report |

## Project Structure

```
sdlc-inject/
├── patterns/                    # Pattern YAML definitions
│   ├── race/                    # Race condition patterns
│   ├── split-brain/             # Split-brain patterns
│   ├── clock-skew/              # Clock skew patterns
│   └── coordination/            # Coordination patterns
├── sdlc_inject/
│   ├── cli.py                   # CLI commands
│   ├── models.py                # Pydantic models for patterns
│   ├── catalog.py               # Pattern catalog management
│   ├── injection.py             # Pattern injection logic
│   ├── grading.py               # Grading infrastructure
│   ├── environment.py           # Environment generation
│   ├── analyzer/                # Codebase analysis
│   │   ├── agent.py             # AI-powered analyzer
│   │   ├── tools.py             # Analysis tools
│   │   └── recommendations.py   # Pattern recommendations
│   ├── enricher/                # Pattern enrichment
│   │   ├── searcher.py          # Incident search
│   │   ├── summarizer.py        # LLM summarization
│   │   └── updater.py           # YAML file updates
│   └── artifacts/               # Artifact generators
│       ├── sentry.py
│       ├── slack.py
│       ├── pagerduty.py
│       ├── logs.py
│       ├── metrics.py
│       ├── github.py
│       └── progressive.py
└── demo/                        # Demo outputs
```

## Pattern YAML Schema

Each pattern is defined in YAML with:

```yaml
id: RACE-001
version: "1.0"
name: "Check-then-act buffer ownership race"
category: "Distributed System Failures"
subcategory: "Race Conditions"

sdlc_phases:
  primary: "Debugging"
  secondary: ["Verification"]

description: |
  A race condition in buffer ownership checking...

target_codebase:
  name: "zed"
  language: "rust"

injection:
  files:
    - path: "crates/collab/src/db/buffers.rs"
      patches:
        - type: "insert_after"
          anchor: "fn acquire_buffer_lock"
          content: |
            // Injected delay...

trigger:
  conditions:
    - description: "Two users connected to same project"
      required: true

observable_symptoms:
  user_visible:
    - symptom: "Edits appear then disappear"
  log_messages:
    - pattern: "buffer ownership conflict"
      level: "WARNING"
  metrics:
    - name: "buffer_conflicts_total"

difficulty:
  estimated_human_time_hours: 3
  frontier_model_pass_rate_percent: 25

golden_path:
  steps:
    - step: 1
      action: "Reproduce the issue"
      tools: ["terminal"]

grading:
  outcome_based:
    - criterion: "Race condition eliminated"
      weight: 0.35
  process_based:
    - criterion: "Identified check-then-act anti-pattern"
      weight: 0.10

related_incidents:
  - url: "https://example.com/postmortem"
    title: "Production Race Condition"
    source_type: "postmortem"
    company: "Example Corp"
    year: 2023
    engineer_solution_summary: |
      Engineers identified the root cause...
    tags: ["race-condition", "distributed"]
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for AI-enhanced analysis and enrichment |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Validate all patterns
sdlc-inject validate-catalog

# Generate demo artifacts
sdlc-inject artifacts RACE-001 --output ./demo/artifacts
```

## Related Work

This tool is designed to create training environments for AI agents based on real-world incident patterns. Sources include:

- [Dan Luu's Post-Mortems Collection](https://github.com/danluu/post-mortems)
- [Google SRE Book](https://sre.google/sre-book/)
- [AWS Post-Event Summaries](https://aws.amazon.com/premiumsupport/technology/pes/)
- Engineering blogs from Netflix, Cloudflare, GitHub, and others
