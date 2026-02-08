"""Cascade pattern matcher -- finds which cascade patterns fit a given codebase.

Two-phase approach:
  Phase 1 (Static): Fast fingerprint of codebase architecture (languages, infra,
  code patterns, service boundaries). Scores each cascade pattern's `requirements`
  against the fingerprint.

  Phase 2 (Neural): For top-scoring patterns, uses Claude Agent SDK to map
  specific files/functions to each hop in the causal chain.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------------
# Phase 1: Static codebase fingerprinting
# ---------------------------------------------------------------------------

# Maps file extensions to language names
_EXT_LANG = {
    ".py": "python", ".rs": "rust", ".go": "go", ".ts": "typescript",
    ".tsx": "typescript", ".js": "javascript", ".java": "java",
    ".kt": "kotlin", ".scala": "scala", ".rb": "ruby", ".cs": "csharp",
    ".cpp": "cpp", ".c": "c", ".php": "php",
}

# Infrastructure signals: pattern -> infrastructure component
_INFRA_SIGNALS: dict[str, list[str]] = {
    "redis": [
        r"redis", r"ioredis", r"redis-py", r"redis\.get", r"redis\.set",
        r"REDIS_URL", r"redis://", r"RedisClient",
    ],
    "postgres": [
        r"postgres", r"psycopg", r"pg_connect", r"DATABASE_URL.*postgres",
        r"sqlalchemy.*postgres", r"PG_HOST", r"postgresql://", r"pgx\.",
    ],
    "kafka": [
        r"kafka", r"confluent.kafka", r"KafkaProducer", r"KafkaConsumer",
        r"KAFKA_BOOTSTRAP", r"kafka://",
    ],
    "rabbitmq": [
        r"rabbitmq", r"amqp", r"pika\.", r"AMQP_URL", r"amqp://",
        r"RabbitMQ", r"amqplib",
    ],
    "grpc": [
        r"grpc", r"\.proto\b", r"protobuf", r"grpc\.", r"\.pb\.go",
        r"_grpc\.py", r"_pb2\.py", r"tonic::", r"grpcio",
    ],
    "kubernetes": [
        r"kubernetes", r"kubectl", r"k8s", r"Deployment", r"liveness",
        r"readiness", r"\.kube", r"helm", r"kustomize",
    ],
    "docker": [
        r"Dockerfile", r"docker-compose", r"FROM\s+\w+:", r"ENTRYPOINT",
    ],
    "terraform": [
        r"terraform", r"\.tf$", r"tfstate", r"provider\s+\"aws\"",
    ],
    "message_queue": [
        r"message.queue", r"celery", r"rq\.", r"bull", r"bee-queue",
        r"SQS", r"pubsub",
    ],
    "elasticsearch": [
        r"elasticsearch", r"opensearch", r"elastic\.", r"ES_HOST",
    ],
}

# Code pattern signals: pattern_name -> regex patterns to search for
_CODE_SIGNALS: dict[str, list[str]] = {
    "connection_pool": [
        r"pool\.get", r"connection_pool", r"ConnectionPool", r"pool\.acquire",
        r"create_pool", r"Pool\(", r"getConnection",
    ],
    "retry_logic": [
        r"retry", r"@Retryable", r"backoff", r"max_retries", r"retry_count",
        r"tenacity", r"retrying",
    ],
    "error_handler": [
        r"except\s+\w+Error", r"catch\s*\(", r"\.catch\(", r"on_error",
        r"error_handler", r"rescue\b",
    ],
    "redis_cache": [
        r"cache\.get", r"cache\.set", r"@cached", r"cache_key",
        r"ttl", r"expire", r"redis.*cache",
    ],
    "idempotency": [
        r"idempoten", r"idempotency.key", r"dedup", r"exactly.once",
    ],
    "feature_flags": [
        r"feature.flag", r"feature.toggle", r"LaunchDarkly", r"flagd",
        r"unleash", r"split\.io", r"isEnabled",
    ],
    "http_client": [
        r"HttpClient", r"requests\.", r"axios", r"fetch\(",
        r"http\.Client", r"RestTemplate", r"OkHttp",
    ],
    "thread_pool": [
        r"ThreadPool", r"ExecutorService", r"thread_pool", r"worker_threads",
        r"asyncio\.Semaphore", r"goroutine",
    ],
    "session_management": [
        r"session", r"session_id", r"session.store", r"express-session",
        r"SessionMiddleware",
    ],
    "database_migration": [
        r"migration", r"alembic", r"flyway", r"knex.*migrate", r"ALTER TABLE",
        r"django.*migrate",
    ],
    "batch_job": [
        r"batch", r"cron", r"scheduler", r"celery.beat", r"@Scheduled",
        r"crontab",
    ],
    "data_export": [
        r"export", r"etl", r"pipeline", r"data.warehouse", r"extract",
    ],
    "invoicing": [
        r"invoice", r"billing", r"charge", r"payment", r"stripe",
    ],
    "load_balancer": [
        r"load.balance", r"nginx", r"haproxy", r"upstream", r"backend",
        r"health.check",
    ],
    "tls_certificates": [
        r"certificate", r"cert", r"tls", r"ssl", r"x509", r"letsencrypt",
    ],
    "service_discovery": [
        r"service.discovery", r"consul", r"eureka", r"dns\.resolve",
        r"\.internal\b",
    ],
    "protobuf": [
        r"protobuf", r"\.proto\b", r"proto3", r"pb2", r"prost",
    ],
    "dead_letter_queue": [
        r"dead.letter", r"dlq", r"DLQ", r"x-dead-letter",
    ],
    "circuit_breaker": [
        r"circuit.breaker", r"CircuitBreaker", r"hystrix", r"resilience4j",
        r"polly",
    ],
    "webhook": [
        r"webhook", r"callback_url", r"notify_url", r"hook_url",
    ],
    "state_machine": [
        r"state.machine", r"StateMachine", r"transition", r"fsm",
    ],
    "grpc_streaming": [
        r"stream", r"ServerStream", r"ClientStream", r"BidiStream",
        r"streaming_rpc",
    ],
    "jvm_gc": [
        r"gc\.log", r"GarbageCollect", r"-XX:.*GC", r"heap.dump",
        r"jmap", r"jstat",
    ],
    "kubernetes_liveness": [
        r"liveness", r"livenessProbe", r"readinessProbe", r"healthz",
    ],
    "concurrent_access": [
        r"mutex", r"lock", r"synchronized", r"atomic", r"RwLock",
        r"Semaphore", r"threading\.Lock",
    ],
    "check_then_act": [
        r"if.*exists.*then", r"if.*available.*acquire", r"if.*free.*take",
        r"check.*then.*do",
    ],
    "dns_resolution": [
        r"dns", r"resolve", r"nslookup", r"dig\b", r"getaddrinfo",
        r"\.internal\b",
    ],
    "database_replication": [
        r"replica", r"replication", r"read.replica", r"primary.*standby",
        r"master.*slave",
    ],
    "eventual_consistency": [
        r"eventual.consistency", r"CRDT", r"conflict.resolution",
        r"last.write.wins", r"vector.clock",
    ],
    "materialized_view": [
        r"materialized.view", r"REFRESH\s+MATERIALIZED", r"matview",
    ],
    "cron_scheduling": [
        r"cron", r"crontab", r"schedule", r"APScheduler", r"node-cron",
    ],
    "timezone_handling": [
        r"timezone", r"tz", r"UTC", r"datetime.*tz", r"pytz", r"zoneinfo",
        r"America/", r"Europe/",
    ],
}

_EXCLUDE_DIRS = {
    "node_modules", "vendor", "target", ".git", "venv", "__pycache__",
    "dist", "build", ".next", ".cache", "coverage",
}


@dataclass
class CodebaseFingerprint:
    """Static architectural fingerprint of a codebase."""
    path: str
    languages: dict[str, int]  # language -> file count
    infrastructure: dict[str, int]  # infra component -> signal count
    code_patterns: dict[str, int]  # pattern name -> signal count
    service_dirs: list[str]  # detected service/module directories
    total_files: int = 0
    total_lines: int = 0

    def has_language(self, lang: str) -> bool:
        return self.languages.get(lang, 0) > 0

    def has_infra(self, component: str) -> bool:
        return self.infrastructure.get(component, 0) > 0

    def has_pattern(self, pattern: str) -> bool:
        return self.code_patterns.get(pattern, 0) > 0

    @property
    def service_count(self) -> int:
        return max(len(self.service_dirs), 1)


@dataclass
class CascadeMatch:
    """A scored match between a cascade pattern and a codebase."""
    pattern_id: str
    pattern_name: str
    score: float  # 0.0 to 1.0
    hop_count: int
    estimated_pass_rate: int
    language_match: list[str]
    infra_match: list[str]
    infra_missing: list[str]
    pattern_match: list[str]
    pattern_missing: list[str]
    service_fit: bool  # Does the codebase have enough services?
    rationale: str
    # Populated by Phase 2 (neural)
    hop_mappings: list[dict[str, Any]] = field(default_factory=list)


def fingerprint_codebase(codebase_path: str | Path) -> CodebaseFingerprint:
    """Phase 1: Build a static fingerprint of a codebase.

    Scans files for language distribution, infrastructure signals,
    and code pattern signals. Fast -- no LLM calls.
    """
    root = Path(codebase_path)
    languages: dict[str, int] = {}
    infra_counts: dict[str, int] = {}
    pattern_counts: dict[str, int] = {}
    service_dirs: list[str] = []
    total_files = 0
    total_lines = 0

    # Walk files
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(excl in file_path.parts for excl in _EXCLUDE_DIRS):
            continue

        ext = file_path.suffix.lower()

        # Count languages
        if ext in _EXT_LANG:
            lang = _EXT_LANG[ext]
            languages[lang] = languages.get(lang, 0) + 1
            total_files += 1

        # Read content for signal matching (skip very large files)
        content = ""
        try:
            if file_path.stat().st_size < 500_000:  # 500KB max
                content = file_path.read_text(errors="ignore")
                total_lines += content.count("\n")
        except (OSError, UnicodeDecodeError):
            continue

        if not content:
            continue

        # Detect infrastructure signals
        for infra_name, patterns in _INFRA_SIGNALS.items():
            for pat in patterns:
                if re.search(pat, content, re.IGNORECASE):
                    infra_counts[infra_name] = infra_counts.get(infra_name, 0) + 1
                    break  # One match per file per infra type

        # Detect code pattern signals
        for pat_name, patterns in _CODE_SIGNALS.items():
            for pat in patterns:
                if re.search(pat, content, re.IGNORECASE):
                    pattern_counts[pat_name] = pattern_counts.get(pat_name, 0) + 1
                    break

    # Detect service directories (common patterns)
    service_patterns = [
        "services/*/", "apps/*/", "packages/*/", "src/*/",
        "microservices/*/", "modules/*/",
    ]
    for sp in service_patterns:
        base_dir = sp.split("/")[0]
        svc_root = root / base_dir
        if svc_root.is_dir():
            for child in svc_root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    service_dirs.append(str(child.relative_to(root)))

    # Also check for docker-compose service definitions
    for compose_file in root.glob("docker-compose*.y*ml"):
        try:
            with open(compose_file) as f:
                compose = yaml.safe_load(f)
            if compose and "services" in compose:
                for svc_name in compose["services"]:
                    if svc_name not in service_dirs:
                        service_dirs.append(f"compose:{svc_name}")
        except Exception:
            pass

    return CodebaseFingerprint(
        path=str(root),
        languages=languages,
        infrastructure=infra_counts,
        code_patterns=pattern_counts,
        service_dirs=service_dirs,
        total_files=total_files,
        total_lines=total_lines,
    )


# ---------------------------------------------------------------------------
# Pattern loading and scoring
# ---------------------------------------------------------------------------

def _load_cascade_patterns(patterns_dir: str | Path) -> list[dict]:
    """Load all cascade pattern YAMLs from a directory."""
    patterns_path = Path(patterns_dir)
    patterns = []

    for yaml_file in sorted(patterns_path.glob("CASCADE-*.yaml")):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if data and data.get("id", "").startswith("CASCADE-"):
                data["_file"] = str(yaml_file)
                patterns.append(data)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load {yaml_file}: {e}[/yellow]")

    return patterns


def score_pattern(fingerprint: CodebaseFingerprint, pattern: dict) -> CascadeMatch:
    """Score how well a cascade pattern fits a codebase fingerprint.

    Scoring:
      - Language overlap:      20% (at least one required language present)
      - Infrastructure match:  30% (fraction of required infra present)
      - Code pattern match:    30% (fraction of required patterns present)
      - Service count fit:     10% (enough services for the causal chain)
      - Bonus signals:         10% (extra signals that increase confidence)
    """
    reqs = pattern.get("requirements", {})
    req_languages = reqs.get("languages", [])
    req_patterns = reqs.get("patterns", [])
    req_infra = reqs.get("infrastructure", [])
    min_services = reqs.get("min_services", 1)

    # --- Language match (20%) ---
    lang_matches = [l for l in req_languages if fingerprint.has_language(l)]
    lang_score = 1.0 if lang_matches else 0.0

    # --- Infrastructure match (30%) ---
    infra_matches = [i for i in req_infra if fingerprint.has_infra(i)]
    infra_missing = [i for i in req_infra if not fingerprint.has_infra(i)]
    infra_score = len(infra_matches) / max(len(req_infra), 1)

    # --- Code pattern match (30%) ---
    pattern_matches = [p for p in req_patterns if fingerprint.has_pattern(p)]
    pattern_missing = [p for p in req_patterns if not fingerprint.has_pattern(p)]
    pattern_score = len(pattern_matches) / max(len(req_patterns), 1)

    # --- Service count fit (10%) ---
    service_fit = fingerprint.service_count >= min_services
    service_score = 1.0 if service_fit else min(fingerprint.service_count / max(min_services, 1), 0.8)

    # --- Bonus signals (10%) ---
    # Extra infra or patterns beyond requirements boost confidence
    bonus = 0.0
    all_infra = set(fingerprint.infrastructure.keys())
    all_patterns = set(fingerprint.code_patterns.keys())
    # Having more infra/patterns than required is a good sign
    if len(all_infra) > len(req_infra):
        bonus += 0.3
    if len(all_patterns) > len(req_patterns):
        bonus += 0.3
    # Having docker is a sign of a production-like codebase
    if fingerprint.has_infra("docker"):
        bonus += 0.2
    # Having kubernetes is a strong signal for infra-heavy patterns
    if fingerprint.has_infra("kubernetes"):
        bonus += 0.2
    bonus = min(bonus, 1.0)

    # Weighted total
    total = (
        lang_score * 0.20
        + infra_score * 0.30
        + pattern_score * 0.30
        + service_score * 0.10
        + bonus * 0.10
    )

    # Build rationale
    rationale_parts = []
    if lang_matches:
        rationale_parts.append(f"Languages: {', '.join(lang_matches)}")
    if infra_matches:
        rationale_parts.append(f"Infra: {', '.join(infra_matches)}")
    if infra_missing:
        rationale_parts.append(f"Missing infra: {', '.join(infra_missing)}")
    if pattern_matches:
        rationale_parts.append(f"Patterns: {', '.join(pattern_matches)}")
    if pattern_missing:
        rationale_parts.append(f"Missing patterns: {', '.join(pattern_missing)}")

    difficulty = pattern.get("difficulty", {})

    return CascadeMatch(
        pattern_id=pattern["id"],
        pattern_name=pattern.get("name", ""),
        score=round(total, 3),
        hop_count=difficulty.get("hop_count", 0),
        estimated_pass_rate=difficulty.get("frontier_model_pass_rate_percent", 0),
        language_match=lang_matches,
        infra_match=infra_matches,
        infra_missing=infra_missing,
        pattern_match=pattern_matches,
        pattern_missing=pattern_missing,
        service_fit=service_fit,
        rationale="; ".join(rationale_parts),
    )


def match_cascade_patterns(
    codebase_path: str | Path,
    patterns_dir: str | Path,
    top_k: int = 5,
    min_score: float = 0.3,
) -> tuple[CodebaseFingerprint, list[CascadeMatch]]:
    """Match a codebase against all cascade patterns.

    Returns the fingerprint and a ranked list of matches.
    """
    console.print(f"[bold]Fingerprinting codebase: {codebase_path}[/bold]\n")
    fingerprint = fingerprint_codebase(codebase_path)

    console.print(f"  Languages: {dict(sorted(fingerprint.languages.items(), key=lambda x: -x[1]))}")
    console.print(f"  Infrastructure: {list(fingerprint.infrastructure.keys())}")
    console.print(f"  Code patterns: {list(fingerprint.code_patterns.keys())}")
    console.print(f"  Services: {fingerprint.service_count} ({', '.join(fingerprint.service_dirs[:5])})")
    console.print(f"  Files: {fingerprint.total_files}, Lines: {fingerprint.total_lines}\n")

    # Load and score patterns
    patterns = _load_cascade_patterns(patterns_dir)
    console.print(f"[bold]Scoring {len(patterns)} cascade patterns...[/bold]\n")

    matches = []
    for pattern in patterns:
        match = score_pattern(fingerprint, pattern)
        if match.score >= min_score:
            matches.append(match)

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)

    return fingerprint, matches[:top_k]


# ---------------------------------------------------------------------------
# Phase 2: Neural hop mapping (uses Claude Agent SDK)
# ---------------------------------------------------------------------------

_HOP_MAPPING_PROMPT = """You are analyzing a codebase to determine how a specific cascading
failure pattern could be injected.

## Cascade Pattern: {pattern_id}
{pattern_description}

## Causal Chain (each hop must map to real code/config in this codebase):
{causal_chain}

## Codebase Fingerprint:
- Languages: {languages}
- Infrastructure: {infrastructure}
- Code patterns: {code_patterns}
- Services: {services}

## Your Task:
For each hop in the causal chain, find the SPECIFIC file(s) and code location(s)
in this codebase where:
1. The failure condition could be injected (for hop 1 - the root cause)
2. The evidence would naturally appear (for intermediate hops)
3. The symptom would be visible (for the final hop)

Use the exploration tools (Glob, Grep, Read) to find concrete matches.

Output as JSON:
{{
  "feasibility": "high" | "medium" | "low",
  "feasibility_rationale": "...",
  "hop_mappings": [
    {{
      "hop": 1,
      "component": "payment-service",
      "mapped_to": {{
        "files": ["path/to/file.py"],
        "functions": ["handle_checkout"],
        "line_range": "45-62",
        "injection_description": "Remove conn.close() from except block"
      }},
      "confidence": 0.85
    }}
  ],
  "modifications_needed": [
    "Need to add Redis caching layer to order-service"
  ]
}}
"""


async def neural_map_hops(
    codebase_path: str | Path,
    pattern: dict,
    model: str = "claude-sonnet-4-5-20250929",
) -> dict:
    """Phase 2: Use Claude to map cascade hops to specific codebase locations.

    This is the expensive step -- only run on top-scoring pattern matches.
    """
    from claude_agent_sdk import query, ResultMessage
    from .sdk_utils import create_agent_options, extract_json_from_text, collect_text_from_messages

    # Build causal chain description
    chain_lines = []
    for hop in pattern.get("causal_chain", []):
        chain_lines.append(
            f"  Hop {hop['hop']}: [{hop['component']}] {hop['failure']} "
            f"(boundary: {hop['boundary_type']}, evidence: {hop['evidence_location']})"
        )
    causal_chain_str = "\n".join(chain_lines)

    prompt = _HOP_MAPPING_PROMPT.format(
        pattern_id=pattern["id"],
        pattern_description=pattern.get("description", ""),
        causal_chain=causal_chain_str,
        languages="scanning...",
        infrastructure="scanning...",
        code_patterns="scanning...",
        services="scanning...",
    )

    options = create_agent_options(
        system_prompt="You are a systems engineer mapping failure injection points in a real codebase.",
        allowed_tools=["Read", "Glob", "Grep"],
        model=model,
        max_turns=30,
        cwd=str(codebase_path),
    )

    all_messages = []
    async for message in query(prompt=prompt, options=options):
        all_messages.append(message)

    full_text = collect_text_from_messages(all_messages)
    result = extract_json_from_text(full_text)

    return result or {"feasibility": "unknown", "hop_mappings": [], "modifications_needed": []}
