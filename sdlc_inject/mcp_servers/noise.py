"""Noise generation engine for realistic MCP server data at scale.

Generates 1000x realistic data (50K+ Slack messages, 100K+ log entries,
10K+ metrics data points) with signal entries buried at configured positions.

Key design:
- Lazy generation: entries created on-demand from seed+position (not pre-materialized)
- Deterministic: same seed+position = same entry, regardless of access order
- Cursor-based pagination: efficient access to large datasets
- Pre-built indexes: fast filtering without scanning all entries
- Signal burial: evidence entries injected at specific positions within noise
"""

from __future__ import annotations

import hashlib
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class NoiseConfig:
    """Configuration for noise generation volume and distribution."""
    entries_per_source: int = 5000
    signal_positions: dict[str, list[int]] = field(default_factory=dict)
    distribution: str = "temporal"  # uniform, bursty, temporal
    seed: int = 42
    time_range_hours: int = 168  # 1 week of data
    start_time: datetime | None = None

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now() - timedelta(hours=self.time_range_hours)


@dataclass
class PaginatedResult:
    """Result of a paginated query."""
    entries: list[dict[str, Any]]
    total: int
    next_cursor: int | None
    has_more: bool


# ---------------------------------------------------------------------------
# Base noise generator
# ---------------------------------------------------------------------------

class NoiseGenerator(ABC):
    """Base class for generating realistic noise data at scale.

    Each position in [0, total) maps to either a noise entry (generated
    deterministically from seed+position) or a signal entry (from the
    hand-crafted evidence). Signal positions are configured in NoiseConfig.

    Subclasses implement generate_entry() to produce noise entries
    appropriate for their data type (Slack, logs, metrics, etc.).
    """

    def __init__(
        self,
        config: NoiseConfig,
        signals: list[dict[str, Any]],
    ):
        self.config = config
        self.total = config.entries_per_source
        self.rng = random.Random(config.seed)

        # Map position -> signal entry
        source_key = self.__class__.__name__.replace("NoiseGenerator", "").lower()
        positions = config.signal_positions.get(source_key, [])
        self._signal_map: dict[int, dict] = {}
        for i, pos in enumerate(positions):
            if i < len(signals):
                self._signal_map[pos] = signals[i]

    def _rng_for_position(self, position: int) -> random.Random:
        """Create a deterministic RNG for a specific position.

        This ensures the same entry is generated regardless of access order.
        """
        seed = self.config.seed + position * 31 + hash(self.__class__.__name__) % 10000
        return random.Random(seed)

    @abstractmethod
    def generate_entry(self, position: int, rng: random.Random) -> dict[str, Any]:
        """Generate a single noise entry at the given position."""
        pass

    def get_entry(self, position: int) -> dict[str, Any]:
        """Get entry at position -- signal if it's a signal position, else noise."""
        if position in self._signal_map:
            return self._signal_map[position]
        return self.generate_entry(position, self._rng_for_position(position))

    def get_page(
        self,
        cursor: int = 0,
        limit: int = 50,
        **filters: Any,
    ) -> PaginatedResult:
        """Cursor-based pagination with optional filtering.

        For unfiltered queries, returns entries [cursor, cursor+limit).
        For filtered queries, scans from cursor until limit matches found.
        """
        if not filters or all(v is None or v == "" for v in filters.values()):
            # Fast path: no filtering
            entries = [self.get_entry(i) for i in range(cursor, min(cursor + limit, self.total))]
            next_pos = cursor + limit
            return PaginatedResult(
                entries=entries,
                total=self.total,
                next_cursor=next_pos if next_pos < self.total else None,
                has_more=next_pos < self.total,
            )

        # Filtered: scan and collect matches
        entries = []
        pos = cursor
        scanned = 0
        max_scan = min(self.total - cursor, limit * 100)  # Don't scan forever

        while len(entries) < limit and pos < self.total and scanned < max_scan:
            entry = self.get_entry(pos)
            if self._matches_filters(entry, filters):
                entries.append(entry)
            pos += 1
            scanned += 1

        return PaginatedResult(
            entries=entries,
            total=self.total,
            next_cursor=pos if pos < self.total else None,
            has_more=pos < self.total,
        )

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search across all entries for a text query.

        Scans signal entries first (fast), then noise entries (lazy).
        """
        query_lower = query.lower()
        results = []

        # Search signals first (fast, high priority)
        for pos, entry in sorted(self._signal_map.items()):
            if self._entry_matches_text(entry, query_lower):
                results.append(entry)
                if len(results) >= limit:
                    return results

        # Search noise (scan up to 10x limit positions)
        max_scan = min(self.total, limit * 200)
        for pos in range(max_scan):
            if pos in self._signal_map:
                continue  # Already checked
            entry = self.get_entry(pos)
            if self._entry_matches_text(entry, query_lower):
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    def _matches_filters(self, entry: dict, filters: dict) -> bool:
        """Check if an entry matches all active filters."""
        for key, value in filters.items():
            if value is None or value == "":
                continue
            entry_value = str(entry.get(key, "")).lower()
            if isinstance(value, str) and value.lower() not in entry_value:
                return False
        return True

    def _entry_matches_text(self, entry: dict, query: str) -> bool:
        """Check if any string field in entry contains the query."""
        for v in entry.values():
            if isinstance(v, str) and query in v.lower():
                return True
        return False


# ---------------------------------------------------------------------------
# Slack noise generator
# ---------------------------------------------------------------------------

_SLACK_PERSONAS = [
    {"name": "alice-eng", "real_name": "Alice Chen", "style": "technical", "avg_words": 15},
    {"name": "bob-sre", "real_name": "Bob Martinez", "style": "concise", "avg_words": 8},
    {"name": "carol-pm", "real_name": "Carol Wang", "style": "verbose", "avg_words": 25},
    {"name": "dave-fe", "real_name": "Dave Kim", "style": "casual", "avg_words": 10},
    {"name": "eve-data", "real_name": "Eve Johnson", "style": "analytical", "avg_words": 18},
    {"name": "frank-devops", "real_name": "Frank Osei", "style": "ops", "avg_words": 12},
    {"name": "grace-qa", "real_name": "Grace Liu", "style": "detail", "avg_words": 14},
    {"name": "hank-ml", "real_name": "Hank Patel", "style": "academic", "avg_words": 20},
    {"name": "iris-security", "real_name": "Iris Nakamura", "style": "serious", "avg_words": 16},
    {"name": "jack-mobile", "real_name": "Jack Thompson", "style": "brief", "avg_words": 6},
]

_SLACK_TEMPLATES = {
    "standup": [
        "Yesterday: {task}. Today: {task2}. No blockers.",
        "Wrapping up {feature}. Should be ready for review by EOD.",
        "Still working on {ticket}. Hit a snag with {tech}, investigating.",
        "PR #{pr_num} is up for {feature}. Would appreciate eyes on the {component} changes.",
        "Blocked on {ticket} waiting for {team} to deploy their changes.",
        "Quick update: {feature} is in staging, running soak test overnight.",
        "Pairing with {person} on {ticket} today.",
        "OOO this afternoon, dentist appointment. Back tomorrow.",
    ],
    "pr_review": [
        "LGTM, approving.",
        "Left a few comments on the {component} changes, nothing blocking.",
        "nit: can we rename `{var}` to something more descriptive?",
        "This looks good but I'd add a test for the edge case where {condition}.",
        "Approved with suggestion: consider using {pattern} instead of {pattern2} here.",
        "Question: why did we choose {approach} over {approach2}?",
        "Looks clean. Ship it.",
        "+1, nice refactor of the {component} module.",
    ],
    "general": [
        "Anyone know the status of the {service} migration?",
        "FYI {link} is a good read on {topic}.",
        "Is {meeting} still happening today?",
        "Can someone review PR #{pr_num}? It's been open for 3 days.",
        "The {env} environment is acting up again, seeing intermittent {issue}.",
        "Heads up: upgrading {dep} to {version} next week.",
        "Does anyone have experience with {tech}? Trying to decide between that and {tech2}.",
        "Reminder: {event} is tomorrow. Don't forget to sign up.",
    ],
    "bot_ci": [
        "Build passed: {service} #{build_num} ({branch})",
        "Build failed: {service} #{build_num} ({branch}) - {test_count} test(s) failed",
        "Build passed: {service} #{build_num} ({branch}) [flaky test retry succeeded]",
    ],
    "bot_deploy": [
        "Deploy complete: {service} {version_old} -> {version_new}",
        "Deploy started: {service} {version_new} to {env}",
        "Rollback complete: {service} reverted to {version_old}",
    ],
    "bot_alert": [
        "[FIRING] {alert_name}: {metric} {condition} for {duration}",
        "[RESOLVED] {alert_name}: {metric} returned to normal",
        "[FIRING] {alert_name}: {service} health check failed",
        "[RESOLVED] {alert_name}: {service} health check recovered",
    ],
    "bot_dependabot": [
        "PR #{pr_num}: Bump {pkg} from {ver_old} to {ver_new} in {path}",
    ],
}

_SERVICES = [
    "checkout", "shipping", "recommendation", "product-catalog", "ad",
    "cart", "payment", "email", "frontend", "accounting", "product-reviews",
    "load-generator", "fraud-detection", "currency",
]

_FEATURES = [
    "user authentication", "cart persistence", "search indexing",
    "recommendation model v2", "payment retry logic", "shipping cost calculator",
    "product image CDN", "A/B testing framework", "metrics pipeline",
    "admin dashboard", "mobile API", "webhook delivery", "rate limiting",
    "order tracking", "inventory sync", "email templates",
]

_TECHS = [
    "gRPC", "Kafka", "Redis", "Valkey", "PostgreSQL", "Next.js", "Go",
    "Rust", "Python", "Java", "protobuf", "Kubernetes", "Docker",
    "OpenTelemetry", "Prometheus", "Grafana", "Flagd", "Terraform",
]


class SlackNoiseGenerator(NoiseGenerator):
    """Generates realistic Slack messages at scale."""

    def generate_entry(self, position: int, rng: random.Random) -> dict[str, Any]:
        # Time distribution: work hours weighted
        hours_offset = (position / max(self.total, 1)) * self.config.time_range_hours
        base_time = self.config.start_time + timedelta(hours=hours_offset)
        # Add jitter
        jitter_minutes = rng.randint(-30, 30)
        timestamp = base_time + timedelta(minutes=jitter_minutes)

        # 40% bot messages, 60% human
        is_bot = rng.random() < 0.4
        if is_bot:
            return self._generate_bot_message(rng, timestamp)
        return self._generate_human_message(rng, timestamp)

    def _generate_human_message(self, rng: random.Random, timestamp: datetime) -> dict:
        persona = rng.choice(_SLACK_PERSONAS)
        category = rng.choice(["standup", "pr_review", "general", "general", "general"])
        templates = _SLACK_TEMPLATES[category]
        template = rng.choice(templates)

        text = template.format(
            task=rng.choice(_FEATURES),
            task2=rng.choice(_FEATURES),
            feature=rng.choice(_FEATURES),
            ticket=f"ENG-{rng.randint(1000, 9999)}",
            tech=rng.choice(_TECHS),
            team=rng.choice(["backend", "platform", "frontend", "data", "infra"]),
            person=rng.choice(_SLACK_PERSONAS)["real_name"].split()[0],
            pr_num=rng.randint(1000, 2000),
            component=rng.choice(["checkout", "cart", "auth", "shipping", "payment"]),
            var=rng.choice(["ctx", "svc", "cfg", "req", "resp"]),
            condition=rng.choice(["empty cart", "nil user", "timeout", "invalid currency"]),
            pattern=rng.choice(["context.WithTimeout", "sync.Pool", "errgroup"]),
            pattern2=rng.choice(["manual goroutines", "channels", "mutex"]),
            approach=rng.choice(["gRPC streaming", "HTTP/2", "WebSocket"]),
            approach2=rng.choice(["polling", "long-polling", "SSE"]),
            service=rng.choice(_SERVICES),
            link="<link>",
            topic=rng.choice(["distributed systems", "Go performance", "Kafka tuning", "observability"]),
            meeting=rng.choice(["sprint planning", "retro", "architecture review", "standup"]),
            env=rng.choice(["staging", "dev", "production"]),
            issue=rng.choice(["timeouts", "connection resets", "high latency", "OOM kills"]),
            dep=rng.choice(_TECHS),
            version=f"v{rng.randint(1,5)}.{rng.randint(0,20)}.{rng.randint(0,10)}",
            tech2=rng.choice(_TECHS),
            event=rng.choice(["tech talk", "team lunch", "demo day", "all-hands"]),
        )

        return {
            "user": f"{persona['real_name']} ({persona['name']})",
            "timestamp": timestamp.isoformat() + "Z",
            "text": text,
        }

    def _generate_bot_message(self, rng: random.Random, timestamp: datetime) -> dict:
        bot_type = rng.choice(["bot_ci", "bot_ci", "bot_ci", "bot_deploy", "bot_alert", "bot_dependabot"])
        templates = _SLACK_TEMPLATES[bot_type]
        template = rng.choice(templates)

        bot_names = {
            "bot_ci": "bot: ci-notify",
            "bot_deploy": "bot: deploy-notify",
            "bot_alert": "bot: grafana-alert",
            "bot_dependabot": "bot: dependabot",
        }

        text = template.format(
            service=rng.choice(_SERVICES),
            build_num=rng.randint(100, 2000),
            branch=rng.choice(["main", "develop", f"feature/ENG-{rng.randint(1000,9999)}"]),
            test_count=rng.randint(1, 5),
            version_old=f"v{rng.randint(1,3)}.{rng.randint(0,20)}.{rng.randint(0,10)}",
            version_new=f"v{rng.randint(1,3)}.{rng.randint(0,20)}.{rng.randint(1,15)}",
            env=rng.choice(["production", "staging"]),
            alert_name=rng.choice(["HighLatency", "ErrorRate", "CPUUsage", "MemoryUsage", "DiskSpace", "PodRestart"]),
            metric=rng.choice(["http_request_duration_p99", "error_rate", "cpu_percent", "memory_used_bytes"]),
            condition=rng.choice(["> 1s for 5m", "> 5% for 10m", "> 80% for 15m", "> 90% for 5m"]),
            duration=rng.choice(["5 minutes", "10 minutes", "15 minutes"]),
            pkg=rng.choice(["golang.org/x/net", "google.golang.org/grpc", "github.com/IBM/sarama", "protobuf"]),
            ver_old=f"{rng.randint(1,5)}.{rng.randint(0,40)}.{rng.randint(0,10)}",
            ver_new=f"{rng.randint(1,5)}.{rng.randint(0,40)}.{rng.randint(1,15)}",
            path=f"/src/{rng.choice(_SERVICES)}",
            pr_num=rng.randint(1200, 1500),
        )

        return {
            "user": bot_names[bot_type],
            "timestamp": timestamp.isoformat() + "Z",
            "text": text,
        }


# ---------------------------------------------------------------------------
# Log noise generator
# ---------------------------------------------------------------------------

_LOG_TEMPLATES = {
    "go": {
        "INFO": [
            "[PlaceOrder] user_id={user_id} user_currency={currency}",
            "payment went through transaction_id={tx_id}",
            "order placed app.order.id={order_id}",
            "order confirmation email sent to {email}",
            "sending to postProcessor",
            "Successful to write message. offset: {offset}, duration: {duration}ms",
            "service config: &{{productCatalogSvcAddr:{host}:8080 cartSvcAddr:{host2}:8080}}",
            "connection established to {host}:{port}",
            "gRPC health check: SERVING",
            "starting to listen on tcp: \":{port}\"",
        ],
        "WARN": [
            "retrying request attempt {attempt}/{max}, backoff {backoff}s",
            "slow query detected: duration={duration}ms threshold=500ms",
            "context deadline approaching: remaining={remaining}ms",
            "deprecated API called: {endpoint}",
            "connection pool utilization high: {util}%",
        ],
        "ERROR": [
            "failed POST to {service}: context deadline exceeded (Client.Timeout exceeded while awaiting headers)",
            "could not charge the card: rpc error: code = DeadlineExceeded",
            "shipping quote failure: failed POST to {service}: context deadline exceeded",
            "failed to get user cart during checkout: rpc error: code = Unavailable",
        ],
    },
    "python": {
        "INFO": [
            "Received request: ListRecommendations for user {user_id}",
            "Product catalog cache refreshed: {count} products",
            "Recommendation model loaded: version={version}",
            "gRPC server started on port {port}",
            "Health check: OK",
            "Processing request with {count} product IDs",
        ],
        "WARN": [
            "Cache miss for product {product_id}, fetching from catalog",
            "Recommendation model stale: last refresh {minutes} minutes ago",
            "ThreadPoolExecutor at capacity: {active}/10 workers busy",
        ],
        "ERROR": [
            "gRPC error calling ProductCatalogService: StatusCode.DEADLINE_EXCEEDED",
            "Failed to refresh product catalog: connection refused",
            "Unhandled exception in recommendation handler",
        ],
    },
    "rust": {
        "INFO": [
            "Actix-web server started on 0.0.0.0:{port}",
            "GET /get-quote completed status=200 latency={latency}ms",
            "POST /ship-order completed status=200 latency={latency}ms",
            "Shipping cost calculated: ${amount} for {items} items",
            "Health check: OK",
        ],
        "WARN": [
            "Slow request: GET /get-quote latency={latency}ms",
            "Connection pool running low: {available} of {max} available",
        ],
        "ERROR": [
            "Internal server error: {error}",
            "Failed to connect to quote service: {error}",
        ],
    },
    "java": {
        "INFO": [
            "AdService started on port {port}",
            "Feature flag adHighCpu evaluated: {value}",
            "Ad request processed: {count} ads returned in {latency}ms",
            "gRPC health check: SERVING",
        ],
        "WARN": [
            "High CPU load detected: {percent}%",
            "Ad rendering slow: {latency}ms for {count} ads",
        ],
        "ERROR": [
            "java.lang.NullPointerException at AdService.getAds(AdService.java:{line})",
            "io.grpc.StatusRuntimeException: UNAVAILABLE: {message}",
        ],
    },
}

_LOG_FUNCTIONS = {
    "go": ["PlaceOrder", "quoteShipping", "shipOrder", "sendOrderConfirmation",
           "getUserCart", "chargeCard", "prepOrderItems", "convertCurrency",
           "sendToPostProcessor", "emptyUserCart", "validateAddress"],
    "python": ["ListRecommendations", "get_product", "refresh_catalog",
               "predict", "serve", "health_check"],
    "rust": ["get_quote", "ship_order", "calculate_cost", "health_check"],
    "java": ["getAds", "evaluateFlag", "renderAd", "healthCheck"],
}


class LogNoiseGenerator(NoiseGenerator):
    """Generates realistic application log entries."""

    def __init__(
        self,
        config: NoiseConfig,
        signals: list[dict[str, Any]],
        service_name: str = "checkout-service",
        language: str = "go",
    ):
        self.service_name = service_name
        self.language = language
        super().__init__(config, signals)

    def generate_entry(self, position: int, rng: random.Random) -> dict[str, Any]:
        # Time distribution
        hours_offset = (position / max(self.total, 1)) * self.config.time_range_hours
        base_time = self.config.start_time + timedelta(hours=hours_offset)
        jitter_seconds = rng.randint(-30, 30)
        timestamp = base_time + timedelta(seconds=jitter_seconds)

        # Level distribution: 99% INFO, 0.8% WARN, 0.2% ERROR
        roll = rng.random()
        if roll < 0.002:
            level = "ERROR"
        elif roll < 0.01:
            level = "WARN"
        else:
            level = "INFO"

        lang = self.language
        templates = _LOG_TEMPLATES.get(lang, _LOG_TEMPLATES["go"])
        level_templates = templates.get(level, templates["INFO"])
        template = rng.choice(level_templates)

        functions = _LOG_FUNCTIONS.get(lang, _LOG_FUNCTIONS["go"])

        message = template.format(
            user_id=f"usr-{rng.randint(10000, 99999):05x}",
            currency=rng.choice(["USD", "EUR", "GBP", "JPY", "CAD"]),
            tx_id=f"tx-{rng.randint(100000, 999999):06x}",
            order_id=f"ord-{rng.randint(100000, 999999):06x}",
            email=f"user{rng.randint(1, 9999)}@example.com",
            offset=rng.randint(1000, 50000),
            duration=rng.randint(1, 50),
            host=rng.choice(["product-catalog", "cart", "payment", "shipping-service", "email-service"]),
            host2=rng.choice(["currency", "recommendation", "ad"]),
            port=rng.choice([8080, 9090, 50051, 3000]),
            service=rng.choice(["shipping service", "email service", "cart service"]),
            attempt=rng.randint(1, 5),
            max=5,
            backoff=rng.choice([2, 4, 8, 16, 32]),
            remaining=rng.randint(100, 5000),
            endpoint=rng.choice(["/v1/validate", "/legacy/quote", "/api/v1/check"]),
            util=rng.randint(60, 99),
            product_id=f"OLJCESPC7Z",
            count=rng.randint(1, 100),
            version=f"v{rng.randint(1,3)}.{rng.randint(0,10)}",
            minutes=rng.randint(1, 60),
            active=rng.randint(5, 10),
            latency=rng.randint(1, 500),
            amount=f"{rng.uniform(5, 50):.2f}",
            items=rng.randint(1, 10),
            available=rng.randint(0, 5),
            error=rng.choice(["connection refused", "timeout", "broken pipe"]),
            value=rng.choice(["true", "false"]),
            percent=rng.randint(40, 95),
            line=rng.randint(100, 400),
            message=rng.choice(["io exception", "connection reset", "peer not available"]),
        )

        return {
            "timestamp": timestamp.isoformat() + "Z",
            "level": level,
            "message": message,
            "function": rng.choice(functions),
            "service": self.service_name,
        }


# ---------------------------------------------------------------------------
# Prometheus noise generator
# ---------------------------------------------------------------------------

# Realistic daily traffic curve (24 hours, normalized 0-1)
_DAILY_CURVE = [
    0.20, 0.15, 0.10, 0.10, 0.15, 0.30,  # 00-05 (night)
    0.50, 0.70, 0.85, 0.95, 1.00, 0.95,  # 06-11 (morning peak)
    0.85, 0.90, 1.00, 0.95, 0.85, 0.80,  # 12-17 (afternoon peak)
    0.70, 0.75, 0.80, 0.60, 0.40, 0.30,  # 18-23 (evening)
]


class PrometheusNoiseGenerator(NoiseGenerator):
    """Generates realistic time-series data points."""

    def __init__(
        self,
        config: NoiseConfig,
        signals: list[dict[str, Any]],
        metric_name: str = "http_requests_total",
        base_value: float = 100.0,
        noise_pct: float = 0.1,
    ):
        self.metric_name = metric_name
        self.base_value = base_value
        self.noise_pct = noise_pct
        super().__init__(config, signals)

    def generate_entry(self, position: int, rng: random.Random) -> dict[str, Any]:
        # Map position to timestamp
        hours_offset = (position / max(self.total, 1)) * self.config.time_range_hours
        timestamp = self.config.start_time + timedelta(hours=hours_offset)

        # Apply daily traffic curve
        hour_of_day = timestamp.hour
        daily_factor = _DAILY_CURVE[hour_of_day]

        # Random walk noise
        noise = rng.gauss(0, self.base_value * self.noise_pct)

        value = self.base_value * daily_factor + noise
        value = max(0, value)  # No negative values

        return {
            "metric": self.metric_name,
            "timestamp": timestamp.isoformat() + "Z",
            "value": round(value, 3),
            "labels": {
                "service": rng.choice(_SERVICES),
                "instance": f"pod-{rng.randint(1,5)}",
            },
        }


# ---------------------------------------------------------------------------
# Sentry noise generator
# ---------------------------------------------------------------------------

_ERROR_TYPES = {
    "go": [
        ("context deadline exceeded", 0.25),
        ("runtime error: invalid memory address or nil pointer dereference", 0.15),
        ("connection refused", 0.12),
        ("EOF", 0.10),
        ("broken pipe", 0.08),
        ("i/o timeout", 0.08),
        ("transport is closing", 0.07),
        ("TLS handshake timeout", 0.05),
        ("no route to host", 0.05),
        ("connection reset by peer", 0.05),
    ],
    "python": [
        ("TimeoutError: [Errno 110] Connection timed out", 0.20),
        ("AttributeError: 'NoneType' object has no attribute", 0.18),
        ("grpc.StatusCode.UNAVAILABLE", 0.15),
        ("ConnectionRefusedError", 0.12),
        ("KeyError:", 0.10),
        ("ValueError: invalid literal", 0.08),
        ("MemoryError", 0.05),
        ("RecursionError", 0.02),
    ],
    "java": [
        ("java.lang.NullPointerException", 0.30),
        ("java.net.SocketTimeoutException", 0.15),
        ("io.grpc.StatusRuntimeException: UNAVAILABLE", 0.12),
        ("java.lang.OutOfMemoryError: Java heap space", 0.08),
        ("java.util.ConcurrentModificationException", 0.05),
    ],
}


class SentryNoiseGenerator(NoiseGenerator):
    """Generates realistic Sentry error issues."""

    def __init__(
        self,
        config: NoiseConfig,
        signals: list[dict[str, Any]],
        project_name: str = "checkout-service",
        language: str = "go",
    ):
        self.project_name = project_name
        self.language = language
        super().__init__(config, signals)

    def generate_entry(self, position: int, rng: random.Random) -> dict[str, Any]:
        lang = self.language
        error_types = _ERROR_TYPES.get(lang, _ERROR_TYPES["go"])

        # Weighted selection
        roll = rng.random()
        cumulative = 0.0
        selected_error = error_types[0][0]
        for error_type, weight in error_types:
            cumulative += weight
            if roll <= cumulative:
                selected_error = error_type
                break

        hours_offset = (position / max(self.total, 1)) * self.config.time_range_hours
        timestamp = self.config.start_time + timedelta(hours=hours_offset)

        # Pareto distribution for event counts (few issues with many events)
        event_count = int(rng.paretovariate(1.5) * 5)
        event_count = max(1, min(event_count, 5000))

        issue_id = f"{self.project_name.upper().replace('-', '')}-{position + 100}"

        return {
            "id": issue_id,
            "title": selected_error,
            "count": event_count,
            "first_seen": (timestamp - timedelta(hours=rng.randint(1, 72))).isoformat() + "Z",
            "last_seen": timestamp.isoformat() + "Z",
            "level": rng.choice(["error", "error", "error", "warning"]),
            "project": self.project_name,
            "tags": {
                "environment": "production",
                "runtime": f"{lang}",
            },
        }
