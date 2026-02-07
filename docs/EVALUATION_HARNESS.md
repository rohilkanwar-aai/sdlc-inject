# Parallel Agent Evaluation Harness

## Overview

Infrastructure to calibrate pattern difficulty by running N parallel Claude agents against injected codebases, collecting structured trajectories, and analyzing success/failure patterns.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVALUATION HARNESS ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐     ┌──────────────────────────────────────────┐        │
│   │   Pattern    │     │           Orchestrator                   │        │
│   │   Catalog    │────▶│  - Spin up N isolated environments       │        │
│   │  (YAML)      │     │  - Dispatch agents in parallel           │        │
│   └──────────────┘     │  - Collect trajectories                  │        │
│                        │  - Configure MCP mode (optional)         │        │
│                        └──────────────┬───────────────────────────┘        │
│                                       │                                     │
│                    ┌──────────────────┼──────────────────┐                 │
│                    ▼                  ▼                  ▼                 │
│            ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│            │  Agent 1    │    │  Agent 2    │    │  Agent N    │          │
│            │  ┌───────┐  │    │  ┌───────┐  │    │  ┌───────┐  │          │
│            │  │ Claude│  │    │  │ Claude│  │    │  │ Claude│  │          │
│            │  └───┬───┘  │    │  └───┬───┘  │    │  └───┬───┘  │          │
│            │      │      │    │      │      │    │      │      │          │
│            │  ┌───┴───┐  │    │  ┌───┴───┐  │    │  ┌───┴───┐  │          │
│            │  │  MCP  │  │    │  │  MCP  │  │    │  │  MCP  │  │          │
│            │  │Sandbox│  │    │  │Sandbox│  │    │  │Sandbox│  │          │
│            │  └───┬───┘  │    │  └───┬───┘  │    │  └───┬───┘  │          │
│            │      │      │    │      │      │    │      │      │          │
│            │  ┌───┴───┐  │    │  ┌───┴───┐  │    │  ┌───┴───┐  │          │
│            │  │  MCP  │  │    │  │  MCP  │  │    │  │  MCP  │  │          │
│            │  │Servers│  │    │  │Servers│  │    │  │Servers│  │          │
│            │  └───────┘  │    │  └───────┘  │    │  └───────┘  │          │
│            └──────┬──────┘    └──────┬──────┘    └──────┬──────┘          │
│                   │                  │                  │                  │
│                   ▼                  ▼                  ▼                  │
│            ┌─────────────────────────────────────────────────────┐        │
│            │              Trajectory Collector                    │        │
│            │  - Every tool call logged with timestamp            │        │
│            │  - File reads/writes captured                       │        │
│            │  - MCP API calls tracked with rate limits           │        │
│            │  - Reasoning steps (if available)                   │        │
│            └─────────────────────────┬───────────────────────────┘        │
│                                      │                                     │
│                                      ▼                                     │
│            ┌─────────────────────────────────────────────────────┐        │
│            │              Analytics Pipeline                      │        │
│            │  - Success/failure classification                   │        │
│            │  - Failure mode clustering                          │        │
│            │  - Time-to-resolution distribution                  │        │
│            │  - Tool usage patterns                              │        │
│            │  - MCP API efficiency metrics                       │        │
│            │  - Root cause identification accuracy               │        │
│            └─────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. Orchestrator (`sdlc_inject/harness/orchestrator.py`)

```python
@dataclass
class EvaluationConfig:
    pattern_id: str
    target_codebase: Path
    num_agents: int = 10
    max_time_per_agent: int = 3600  # seconds
    temperature_variations: list[float] = field(default_factory=lambda: [0.0, 0.3, 0.7])

@dataclass
class EvaluationRun:
    run_id: str
    config: EvaluationConfig
    start_time: datetime
    trajectories: list[AgentTrajectory]
    analytics: AnalyticsResult

class Orchestrator:
    async def run_evaluation(self, config: EvaluationConfig) -> EvaluationRun:
        """
        1. Inject pattern into codebase (N copies in isolated dirs)
        2. Generate artifacts for each
        3. Spin up N agents in parallel
        4. Collect all trajectories
        5. Run analytics
        """
        pass
```

### 2. Agent Sandbox (`sdlc_inject/harness/sandbox.py`)

Each agent runs in an isolated environment with:

```python
@dataclass
class SandboxConfig:
    workspace_dir: Path          # Isolated copy of injected codebase
    artifacts_dir: Path          # Sentry, logs, etc.
    allowed_mcps: list[str]      # ["filesystem", "bash", "git"]
    blocked_mcps: list[str]      # ["web_fetch", "web_search"]
    timeout_seconds: int

class AgentSandbox:
    def __init__(self, config: SandboxConfig):
        self.trajectory = AgentTrajectory()

    async def run_agent(self, task_prompt: str) -> AgentTrajectory:
        """Run Claude with MCPs, logging every action."""
        pass
```

### 3. Trajectory Schema (`sdlc_inject/harness/trajectory.py`)

```python
@dataclass
class ToolCall:
    timestamp: datetime
    tool_name: str              # "bash", "read_file", "edit_file"
    input_params: dict
    output: str
    duration_ms: int

@dataclass
class ReasoningStep:
    timestamp: datetime
    thought: str                # If using extended thinking

@dataclass
class AgentTrajectory:
    agent_id: str
    pattern_id: str
    start_time: datetime
    end_time: datetime
    tool_calls: list[ToolCall]
    reasoning_steps: list[ReasoningStep]
    final_state: dict           # Files modified, tests run, etc.
    outcome: Outcome            # SUCCESS, FAILURE, TIMEOUT, ERROR

    # Derived metrics
    @property
    def total_duration_seconds(self) -> float: ...

    @property
    def files_read(self) -> list[str]: ...

    @property
    def files_modified(self) -> list[str]: ...

    @property
    def commands_run(self) -> list[str]: ...
```

### 4. Analytics Pipeline (`sdlc_inject/harness/analytics.py`)

```python
@dataclass
class AnalyticsResult:
    # Core metrics
    pass_rate: float                    # 0.0 to 1.0
    pass_rate_ci_95: tuple[float, float]  # Confidence interval

    # Time analysis
    median_time_to_success: float       # seconds
    time_distribution: dict             # histogram buckets

    # Failure analysis
    failure_modes: list[FailureMode]    # Clustered failure types
    most_common_failure: str

    # Process analysis
    avg_files_read_success: float
    avg_files_read_failure: float
    root_cause_identified_rate: float

    # Tool usage
    tool_usage_frequency: dict[str, int]
    successful_tool_sequences: list[list[str]]  # Common patterns in wins

@dataclass
class FailureMode:
    name: str                           # "symptom_chasing", "wrong_layer", etc.
    frequency: float                    # 0.0 to 1.0 of failures
    example_trajectory_ids: list[str]
    common_characteristics: dict

class AnalyticsPipeline:
    def analyze(self, trajectories: list[AgentTrajectory]) -> AnalyticsResult:
        """
        1. Classify each trajectory as success/failure
        2. Cluster failures into modes
        3. Compute statistics
        4. Identify successful patterns
        """
        pass

    def _classify_outcome(self, trajectory: AgentTrajectory, pattern: Pattern) -> Outcome:
        """
        Check:
        - Did tests pass after changes?
        - Was root cause mentioned in reasoning?
        - Were correct files modified?
        """
        pass

    def _cluster_failures(self, failed: list[AgentTrajectory]) -> list[FailureMode]:
        """
        Use embeddings or heuristics to group similar failures:
        - Symptom chasing (timeout/retry changes without root cause)
        - Wrong layer (blames network when it's code)
        - Partial fix (correct direction but incomplete)
        - Gave up (no actionable conclusion)
        """
        pass
```

---

## MCP Mode (Mock Observability Tools)

MCP Mode provides agents with interactive access to mock observability tools (Sentry, Slack, GitHub, PagerDuty, Prometheus) populated with pattern-specific debugging data. This simulates real-world incident response workflows.

### MCP Tool Provider (`sdlc_inject/harness/mcp_integration.py`)

```python
@dataclass
class MCPConfig:
    enabled: bool = True
    seed: int | None = None          # For reproducible data

    # Rate limiting
    rate_limit_enabled: bool = True
    requests_per_minute: int = 30
    burst_limit: int = 5
    penalty_multiplier: float = 2.0   # Exponential backoff factor

    # Service toggles
    enable_sentry: bool = True
    enable_slack: bool = True
    enable_github: bool = True
    enable_pagerduty: bool = True
    enable_prometheus: bool = True

@dataclass
class MCPStats:
    total_requests: int = 0
    successful_requests: int = 0
    rate_limited_requests: int = 0
    requests_by_service: dict[str, int]
    rate_limit_violations: int = 0
    avg_response_time_ms: float = 0.0
```

### Available MCP Tools

| Service | Tools | Description |
|---------|-------|-------------|
| **Sentry** | `sentry_list_issues`, `sentry_get_issue`, `sentry_get_events` | Error tracking with stack traces |
| **Slack** | `slack_list_channels`, `slack_get_messages`, `slack_get_thread` | Incident channel communications |
| **GitHub** | `github_list_issues`, `github_get_issue`, `github_list_commits`, `github_get_pull_request` | Code history and discussions |
| **PagerDuty** | `pagerduty_list_incidents`, `pagerduty_get_incident`, `pagerduty_get_timeline` | Alert and escalation data |
| **Prometheus** | `prometheus_query`, `prometheus_query_range`, `prometheus_list_alerts` | Metrics and alert state |

### Rate Limiting as Reward Signal

MCP mode enforces rate limits to train efficient API usage:

```python
class MCPToolProvider:
    def get_grading_score_adjustment(self) -> float:
        """
        Returns a multiplier (0.8-1.0) that penalizes:
        - Rate limit violations: -2% per violation (max -10%)
        - Excessive API calls (>50): -0.2% per excess call (max -10%)
        - Low success rate (<80%): proportional penalty
        """
```

This encourages agents to:
- Query efficiently rather than brute-force searching
- Respect rate limits and implement backoff
- Use targeted queries with filters

### Standalone MCP Server

Test MCP endpoints manually before running evaluations:

```bash
# Start standalone server
sdlc-inject mcp-server RACE-001 --port 8080 --seed 42

# Test endpoints
curl http://localhost:8080/sentry/issues
curl http://localhost:8080/slack/channels
curl http://localhost:8080/prometheus/alerts
```

---

## CLI Commands

```bash
# Run evaluation with 10 parallel agents
sdlc-inject evaluate RACE-001 \
  --target ./my-codebase \
  --num-agents 10 \
  --output ./evaluation-results

# Run with temperature variations (diversity)
sdlc-inject evaluate RACE-001 \
  --target ./my-codebase \
  --num-agents 30 \
  --temperatures 0.0,0.3,0.7 \
  --output ./evaluation-results

# With MCP mode (agents get access to mock observability tools)
sdlc-inject evaluate RACE-001 \
  --target ./my-codebase \
  --mcp-mode \
  --mcp-rate-limit 30 \
  --mcp-seed 42 \
  --output ./evaluation-results

# Analyze existing trajectories
sdlc-inject analyze-trajectories ./evaluation-results \
  --output analytics-report.json

# Compare two patterns
sdlc-inject compare-patterns RACE-001 RACE-002 \
  --trajectories ./results \
  --output comparison.md
```

---

## Output: Analytics Report

```json
{
  "pattern_id": "RACE-001",
  "evaluation_run_id": "eval-2026-02-06-001",
  "num_agents": 30,

  "summary": {
    "pass_rate": 0.267,
    "pass_rate_ci_95": [0.12, 0.41],
    "median_time_success": 2340,
    "median_time_failure": 1890
  },

  "failure_modes": [
    {
      "name": "symptom_chasing",
      "frequency": 0.45,
      "description": "Increased timeout or added retries without addressing race",
      "example_actions": ["edit: BUFFER_TIMEOUT = 5000", "add: retry(3)"]
    },
    {
      "name": "wrong_layer",
      "frequency": 0.27,
      "description": "Blamed network latency, added connection pooling",
      "example_actions": ["edit: connection_pool_size = 100"]
    },
    {
      "name": "partial_fix",
      "frequency": 0.18,
      "description": "Identified race but fix was incomplete or introduced deadlock",
      "example_actions": ["add: mutex.lock()", "missing: mutex.unlock()"]
    }
  ],

  "successful_patterns": {
    "common_tool_sequence": [
      "sentry_list_issues()",
      "sentry_get_issue(issue_123)",
      "read_file(src/db/buffers.rs)",
      "slack_get_messages(incident-channel)",
      "prometheus_query(buffer_conflicts)",
      "edit_file(src/db/buffers.rs)",
      "bash(cargo test)"
    ],
    "avg_files_read": 4.2,
    "root_cause_mentioned": true
  },

  "mcp_stats": {
    "total_requests": 847,
    "successful_requests": 812,
    "rate_limited_requests": 35,
    "requests_by_service": {
      "sentry": 156,
      "slack": 234,
      "github": 189,
      "pagerduty": 98,
      "prometheus": 170
    },
    "rate_limit_violations": 12,
    "avg_response_time_ms": 45.2,
    "grading_adjustment_avg": 0.94
  },

  "recommendations": {
    "difficulty_assessment": "appropriate",
    "suggested_hints": [],
    "flag_for_review": false
  }
}
```

---

## Implementation Priority

| Component | Effort | Value | Priority |
|-----------|--------|-------|----------|
| Trajectory logging | Low | High | P0 - Need this first |
| Single agent runner | Medium | High | P0 - Core functionality |
| Parallel orchestration | Medium | High | P1 - Scale up |
| Basic analytics (pass rate) | Low | High | P0 - Minimum viable |
| Failure clustering | High | Medium | P2 - Nice to have |
| CLI commands | Low | Medium | P1 - Usability |

---

## For the RFP (Feb 9)

**Minimum viable demo:**
1. Run 5-10 agents against RACE-001
2. Collect trajectories
3. Report: pass rate, common failure modes, time distribution

**This gives us:**
- Concrete numbers for the proposal ("25% pass rate on RACE-001")
- Evidence-based difficulty claims
- Failure mode taxonomy from real data

---

## Cost Estimate

| Item | Per Agent | 10 Agents | 30 Agents |
|------|-----------|-----------|-----------|
| Claude API (Sonnet, ~50K tokens) | $0.15 | $1.50 | $4.50 |
| Claude API (Opus, ~50K tokens) | $0.75 | $7.50 | $22.50 |
| Compute (container) | ~$0.02 | $0.20 | $0.60 |
| **Total (Sonnet)** | | **~$2** | **~$5** |
| **Total (Opus)** | | **~$8** | **~$23** |

Running calibration for all 20 patterns with 10 agents each: **~$40-160**

This is very affordable for pre-RFP validation.
