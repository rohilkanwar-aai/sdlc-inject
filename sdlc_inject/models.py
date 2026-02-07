"""Pydantic models for pattern definitions."""

from typing import Any
from pydantic import BaseModel, Field


class SdlcPhases(BaseModel):
    primary: str
    secondary: list[str] = []


class TargetCodebase(BaseModel):
    name: str
    min_version: str | None = None
    language: str | None = None


class Patch(BaseModel):
    type: str = Field(alias="type")
    anchor: str | None = None
    old: str | None = None
    new: str | None = None
    content: str | None = None
    location: str | None = None


class FileInjection(BaseModel):
    path: str
    patches: list[Patch]


class ConfigValue(BaseModel):
    key: str
    old_value: str
    new_value: str
    comment: str | None = None


class ConfigChange(BaseModel):
    file: str
    changes: list[ConfigValue]


class FeatureFlag(BaseModel):
    name: str
    description: str


class ObfuscationTechnique(BaseModel):
    type: str = Field(alias="type")
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    content: str | None = None
    location: str | None = None
    description: str | None = None
    commit_messages: list[str] = []


class Obfuscation(BaseModel):
    strategy: str
    techniques: list[ObfuscationTechnique] = []


class Injection(BaseModel):
    files: list[FileInjection] = []
    config_changes: list[ConfigChange] = []
    feature_flags: list[FeatureFlag] = []
    obfuscation: Obfuscation | None = None


class TriggerCondition(BaseModel):
    """Can be a simple string or detailed object."""
    description: str
    required: bool = False
    increases_probability: bool = False

    @classmethod
    def from_yaml(cls, data: str | dict) -> "TriggerCondition":
        if isinstance(data, str):
            return cls(description=data)
        return cls(**data)


class ReproductionStep(BaseModel):
    step: int
    action: str
    command: str | None = None
    automation: str | None = None


class Trigger(BaseModel):
    conditions: list[TriggerCondition] = []
    reproduction_steps: list[ReproductionStep] = []
    expected_frequency: str | None = None


class Symptom(BaseModel):
    symptom: str
    frequency: str | None = None


class LogPattern(BaseModel):
    pattern: str
    level: str
    file: str | None = None


class MetricAnomaly(BaseModel):
    name: str
    type: str | None = Field(default=None, alias="type")
    labels: list[str] = []
    description: str | None = None
    anomaly: str | None = None
    alert_threshold: str | None = None


class DatabaseCheck(BaseModel):
    query: str
    expected_normal: str | None = None
    indicates_bug: str | None = None


class DiagnosticQuery(BaseModel):
    description: str
    query: str


class ObservableSymptoms(BaseModel):
    user_visible: list[Symptom] = []
    log_messages: list[LogPattern] = []
    metrics: list[MetricAnomaly] = []
    database_state: list[DatabaseCheck] = []
    diagnostic_queries: list[DiagnosticQuery] = []


class Difficulty(BaseModel):
    estimated_human_time_hours: float
    frontier_model_pass_rate_percent: int
    complexity_factors: list[str] = []


class FailureMode(BaseModel):
    mode: str
    description: str
    detection: str | None = None


class FailureModes(BaseModel):
    common: list[FailureMode] = []
    subtle: list[FailureMode] = []


class GoldenStep(BaseModel):
    step: int
    action: str
    details: str | None = None
    tools: list[str] = []
    commands: list[str] = []
    search_queries: list[str] = []
    key_insight: str | None = None
    evidence: str | None = None
    time_estimate_minutes: int | None = None
    solutions: dict[str, str] | None = None
    test_code: str | None = None
    test_outline: str | None = None
    resources: list[str] = []
    verification: str | None = None


class GoldenPath(BaseModel):
    overview: str | None = None
    steps: list[GoldenStep]


class Verification(BaseModel):
    type: str = Field(alias="type")
    script: str | None = None
    command: str | None = None
    expected_exit_code: int | None = None
    timeout_seconds: int | None = None
    iterations: int | None = None
    description: str | None = None
    pattern: str | None = None
    baseline_metric: str | None = None
    max_regression_percent: int | None = None


class GradingCriterion(BaseModel):
    criterion: str
    weight: float
    verification: Verification | None = None
    evidence: str | None = None
    evidence_patterns: list[str] = []


class Grading(BaseModel):
    total_weight: float | None = None
    outcome_based: list[GradingCriterion] = []
    process_based: list[GradingCriterion] = []


class ProgressiveHint(BaseModel):
    level: int
    trigger_condition: str | None = None
    trigger: str | None = None
    content: str


class Hints(BaseModel):
    progressive: list[ProgressiveHint] = []


class DockerBuild(BaseModel):
    context: str
    dockerfile: str
    args: dict[str, str] = {}


class DockerService(BaseModel):
    name: str
    image: str | None = None
    build: DockerBuild | None = None
    ports: list[str] = []
    environment: dict[str, str] = {}
    volumes: list[str] = []
    depends_on: list[str] = []


class DockerConfig(BaseModel):
    compose_file: str | None = None
    services: list[DockerService] = []


class KeyMetric(BaseModel):
    name: str
    query: str | None = None
    alert: str | None = None


class MonitoringConfig(BaseModel):
    prometheus_config: str | None = None
    prometheus_metrics: list[str] = []
    grafana_dashboard: str | None = None
    grafana_dashboards: list[str] = []
    key_metrics: list[KeyMetric] = []


class LoadGeneratorConfig(BaseModel):
    tool: str
    script: str
    script_content: str | None = None
    config: dict[str, Any] = {}


class ToxicConfig(BaseModel):
    type: str = Field(alias="type")
    attributes: dict[str, Any] = {}
    upstream: str | None = None


class NetworkScenario(BaseModel):
    name: str
    toxic: ToxicConfig | None = None


class NetworkSimulation(BaseModel):
    tool: str
    setup: str | None = None
    scenarios: list[NetworkScenario] = []


class ClockManipulation(BaseModel):
    tool: str
    setup: str | None = None


class ProcessControl(BaseModel):
    technique: str
    scripts: dict[str, str] = {}


class Environment(BaseModel):
    docker: DockerConfig | None = None
    monitoring: MonitoringConfig | None = None
    load_generator: LoadGeneratorConfig | None = None
    network_simulation: NetworkSimulation | None = None
    clock_manipulation: ClockManipulation | None = None
    process_control: ProcessControl | None = None


class RelatedPattern(BaseModel):
    id: str
    relationship: str
    description: str | None = None


class RelatedIncident(BaseModel):
    """Reference to a real-world incident related to this pattern."""

    url: str
    title: str | None = None
    relevance: str | None = None
    # Enhanced fields for incident enrichment
    source_type: str | None = None  # "postmortem", "blog", "paper", "news", "github"
    company: str | None = None  # Company that experienced the incident
    year: int | None = None  # Year the incident occurred
    engineer_solution_summary: str | None = None  # LLM-generated summary of how engineers solved it
    tags: list[str] = []  # Tags like ["race-condition", "distributed", "database"]


# ============================================================================
# Codebase-Independent Pattern Schema (v2.0)
# ============================================================================


class PatternRequirements(BaseModel):
    """Requirements for a pattern to be applicable to a codebase.

    Instead of specifying a specific target codebase, patterns can define
    generic requirements that the analyzer matches against any codebase.
    """

    languages: list[str] = []  # ["rust", "python", "go", "typescript"]
    patterns: list[str] = []  # ["concurrent_access", "check_then_act", "async_operations"]
    frameworks: list[str] = []  # ["tokio", "asyncio", "goroutines"]
    min_complexity: int | None = None  # Minimum cyclomatic complexity
    has_tests: bool | None = None  # Whether target should have existing tests


class LanguageInjection(BaseModel):
    """Language-specific injection code."""

    target_pattern: str  # Regex pattern to match (with named groups)
    injection_code: str  # Code to inject (can reference named groups with {name})
    file_patterns: list[str] = []  # Glob patterns for files to search ["**/*.py"]


class InjectionTemplate(BaseModel):
    """Template-based injection for codebase-independent patterns.

    Instead of specifying exact file paths, patterns define templates that
    the injection engine matches against the target codebase.
    """

    description: str  # Human-readable description of what this injects
    detection_query: str | None = None  # Query for finding injection points

    # Language-specific injection configurations
    rust: LanguageInjection | None = None
    python: LanguageInjection | None = None
    go: LanguageInjection | None = None
    typescript: LanguageInjection | None = None
    javascript: LanguageInjection | None = None
    java: LanguageInjection | None = None

    # Obfuscation settings for the injection
    obfuscation_level: str = "medium"  # "none", "low", "medium", "high"
    disguise_as: str | None = None  # "metrics", "logging", "tracing", etc.


class MultiPatternEntry(BaseModel):
    """A single pattern in a multi-pattern configuration."""

    pattern_id: str
    weight: float = 1.0  # Importance weight for grading (1.0 = root cause)
    hints_enabled: bool = True
    injection_probability: float = 1.0  # Probability of injecting this pattern


class MultiPatternGrading(BaseModel):
    """Grading configuration for multi-pattern scenarios."""

    root_cause_pattern: str  # Pattern ID that is the actual root cause
    partial_credit: dict[str, float] = {}  # Pattern ID -> credit for identifying


class MultiPatternConfig(BaseModel):
    """Configuration for injecting multiple patterns into a single codebase.

    Allows creating complex, realistic debugging scenarios with
    cascading failures, red herrings, and contributing factors.
    """

    id: str
    name: str
    description: str | None = None

    patterns: list[MultiPatternEntry]
    grading: MultiPatternGrading | None = None

    # Metadata
    total_difficulty_multiplier: float = 1.5  # How much harder than single pattern
    estimated_human_time_hours: float | None = None


class Pattern(BaseModel):
    """A single injectable failure pattern.

    Supports two modes:
    1. Codebase-specific (v1.0): Uses `target_codebase` and `injection` with explicit file paths
    2. Codebase-independent (v2.0): Uses `requirements` and `injection_template` with pattern matching

    Both modes can coexist - a pattern may have both for different use cases.
    """

    id: str
    version: str
    name: str
    category: str
    subcategory: str
    sdlc_phases: SdlcPhases
    description: str

    # V1.0 - Codebase-specific injection (optional)
    target_codebase: TargetCodebase | None = None
    injection: Injection | None = None

    # V2.0 - Codebase-independent injection (optional)
    requirements: PatternRequirements | None = None
    injection_template: InjectionTemplate | None = None

    # Common fields
    trigger: Trigger | None = None
    observable_symptoms: ObservableSymptoms | None = None
    difficulty: Difficulty | None = None
    failure_modes: FailureModes | None = None
    golden_path: GoldenPath | None = None
    grading: Grading | None = None
    hints: Hints | None = None
    environment: Environment | None = None
    related_patterns: list[RelatedPattern] = []
    related_incidents: list[RelatedIncident] = []
    tags: list[str] = []

    model_config = {"populate_by_name": True}

    @property
    def is_codebase_independent(self) -> bool:
        """Check if pattern uses codebase-independent injection."""
        return self.requirements is not None and self.injection_template is not None

    @property
    def supported_languages(self) -> list[str]:
        """Get list of languages this pattern supports."""
        if self.requirements:
            return self.requirements.languages
        if self.target_codebase and self.target_codebase.language:
            return [self.target_codebase.language]
        return []
