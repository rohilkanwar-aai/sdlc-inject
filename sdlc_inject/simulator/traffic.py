"""Real-time traffic simulator that writes to a SQLite database.

Generates realistic service traffic including logs, metrics, Sentry events,
and Slack messages. Simulates a cascade failure pattern: large batch ->
gRPC truncation -> duplicate webhooks -> negative inventory -> circuit breaker.
"""

import sqlite3
import threading
import random
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    function TEXT DEFAULT '',
    trace_id TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    labels TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sentry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    project TEXT NOT NULL,
    title TEXT NOT NULL,
    level TEXT DEFAULT 'error',
    count INTEGER DEFAULT 1,
    stacktrace TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS slack_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    channel TEXT NOT NULL,
    user_name TEXT NOT NULL,
    text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_sentry_project ON sentry_events(project);
CREATE INDEX IF NOT EXISTS idx_slack_channel ON slack_messages(channel);
"""


def init_traffic_db(db_path: str) -> None:
    """Initialize the SQLite database with the traffic schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()


class TrafficSimulator:
    """Generates realistic service traffic and writes it to a SQLite database.

    The simulator runs as a daemon thread, producing logs, metrics, Sentry
    events, and Slack messages at a configurable speed. It models a cascade
    failure where large batches get truncated by a gRPC message size limit,
    leading to duplicate webhooks, negative inventory, and eventually a
    storefront circuit breaker trip.

    Args:
        db_path: Path to the SQLite database file.
        speed: Simulation speed multiplier (1.0 = real-time, 10.0 = 10x faster).
        seed: Random seed for reproducible traffic patterns.
    """

    def __init__(self, db_path: str, speed: float = 1.0, seed: int = 42):
        self.db_path = db_path
        self.speed = speed  # 1.0 = real-time, 10.0 = 10x faster
        self.rng = random.Random(seed)
        self.running = False
        self._thread = None

        # Cascade state
        self.negative_sku_count = 0
        self.duplicate_webhook_count = 0
        self.circuit_breaker_tripped = False
        self.tick_count = 0

        # Services in the system
        self.services = [
            "order-processing-service", "batch-builder", "webhook-dispatch",
            "inventory-service", "storefront", "payment-service",
            "notification-service", "user-service", "route-service",
            "seat-service", "preserve-service", "cancel-service",
        ]

    def start(self):
        """Start the simulator daemon thread."""
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the simulator and wait for the thread to finish."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def pre_seed(self, minutes: int = 30):
        """Pre-seed the database with historical traffic.

        Generates realistic historical data going back the specified number
        of minutes. Uses a higher cascade event rate than real-time to build
        up meaningful state quickly.

        Args:
            minutes: Number of minutes of historical data to generate.
        """
        conn = sqlite3.connect(self.db_path)
        now = datetime.now()

        for minute_offset in range(minutes, 0, -1):
            ts = now - timedelta(minutes=minute_offset)

            # Generate 60-100 normal log entries per minute
            for _ in range(self.rng.randint(60, 100)):
                jitter = timedelta(seconds=self.rng.uniform(0, 60))
                entry_ts = ts + jitter
                svc = self.rng.choice(self.services)
                latency = self.rng.randint(5, 200)
                conn.execute(
                    "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
                    (entry_ts.isoformat(), svc, "INFO",
                     f"request completed status=200 latency={latency}ms",
                     self.rng.choice(["handleRequest", "processOrder", "getQuote", "getRoute"]))
                )

            # 15% chance per minute during pre-seed: cascade event (higher rate to build up state)
            if self.rng.random() < 0.15:
                self._generate_cascade_event_to_db(conn, ts)

            # Metrics snapshot every minute
            self._write_metrics_to_db(conn, ts)

            # Occasional alert
            if self.rng.random() < 0.05:
                conn.execute(
                    "INSERT INTO slack_messages (timestamp, channel, user_name, text) VALUES (?,?,?,?)",
                    (ts.isoformat(), "alerts", "bot: grafana-alert",
                     self.rng.choice([
                         "[FIRING] inventory_negative_skus > 50",
                         "[FIRING] webhook_duplicate_sends increasing",
                         "[RESOLVED] order_processing_latency_p99 < 1s",
                         f"[FIRING] storefront circuit breaker: {self.negative_sku_count} negative SKUs",
                     ]))
                )

        conn.commit()
        conn.close()

    def _run(self):
        """Main simulator loop -- runs in a daemon thread."""
        while self.running:
            try:
                conn = sqlite3.connect(self.db_path)
                self._generate_tick(conn)
                conn.commit()
                conn.close()
            except Exception:
                pass  # Don't crash the simulator on errors
            time.sleep(1.0 / self.speed)

    def _generate_tick(self, conn):
        """Generate one tick of traffic (approximately 1 second of activity)."""
        now = datetime.now()
        self.tick_count += 1

        # Normal traffic: 80-120 requests per second
        for _ in range(self.rng.randint(80, 120)):
            svc = self.rng.choice(self.services)
            latency = int(abs(self.rng.gauss(15, 30)))
            status = 200 if self.rng.random() < 0.95 else self.rng.choice([500, 502, 503])
            conn.execute(
                "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
                (now.isoformat(), svc,
                 "ERROR" if status >= 500 else "INFO",
                 f"request completed status={status} latency={latency}ms trace_id={uuid.uuid4().hex[:16]}",
                 self.rng.choice(["handleRequest", "processOrder", "getQuote", "getRoute", "checkSeat"]))
            )

        # Cascade event: ~1% chance per tick
        if self.rng.random() < 0.01:
            self._generate_cascade_event_to_db(conn, now)

        # Metrics every 15 ticks (~15 seconds)
        if self.tick_count % 15 == 0:
            self._write_metrics_to_db(conn, now)

        # Automated alerts every 60 ticks (~1 minute)
        if self.tick_count % 60 == 0:
            self._generate_alert(conn, now)

        # Support escalation every 300 ticks (~5 minutes)
        if self.tick_count % 300 == 0:
            tickets = 50 + self.tick_count // 10
            conn.execute(
                "INSERT INTO slack_messages (timestamp, channel, user_name, text) VALUES (?,?,?,?)",
                (now.isoformat(), "support", "lisa (support)",
                 f"Update: {tickets} tickets now. Customers reporting double shipments and storefront errors.")
            )

    def _generate_cascade_event_to_db(self, conn, ts):
        """Generate a cascade event: large batch -> truncation -> duplicate webhook -> negative inventory."""
        batch_id = f"batch-{uuid.uuid4().hex[:8]}"

        # Step 1: Batch builder assembles large batch
        bytes_sent = self.rng.randint(6000000, 7500000)  # 6-7.5MB
        conn.execute(
            "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
            (ts.isoformat(), "batch-builder", "INFO",
             f"Batch {batch_id} assembled: {self.rng.randint(500, 1200)} orders, bytes_sent={bytes_sent}",
             "assembleBatch"))

        # Step 2: Order processor receives truncated batch (always 4MB)
        conn.execute(
            "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
            (ts.isoformat(), "order-processing-service", "INFO",
             f"Batch {batch_id} received: bytes_received=4194304, gRPC_status=OK, unmarshal_status=OK",
             "processBatch"))

        # Step 3: Orders auto-approved (missing hold_for_review)
        num_orders = self.rng.randint(3, 8)
        for _ in range(num_orders):
            order_id = f"ORD-{self.rng.randint(10000, 99999)}"
            conn.execute(
                "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
                (ts.isoformat(), "order-processing-service", "INFO",
                 f"Order {order_id} state: received -> approved (auto: hold_for_review=false)",
                 "processOrder"))

        # Step 4: Webhook sent
        idem_key_1 = f"{batch_id}-{int(ts.timestamp())}"
        conn.execute(
            "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
            (ts.isoformat(), "webhook-dispatch", "INFO",
             f"Webhook sent: batch={batch_id}, partner=ShipCo, idempotency_key={idem_key_1}, orders={num_orders}",
             "dispatchWebhook"))

        # Step 5: Re-send (different timestamp = different idempotency key)
        later = ts + timedelta(seconds=self.rng.randint(45, 180))
        idem_key_2 = f"{batch_id}-{int(later.timestamp())}"
        conn.execute(
            "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
            (later.isoformat(), "webhook-dispatch", "WARN",
             f"Re-sending webhook: batch={batch_id}, incomplete_state_detected, "
             f"idempotency_key={idem_key_2} (different from original {idem_key_1})",
             "retryWebhook"))
        self.duplicate_webhook_count += 1

        # Step 6: Inventory goes negative
        for _ in range(num_orders):
            sku = f"SKU-{self.rng.randint(1000, 9999)}"
            conn.execute(
                "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
                (later.isoformat(), "inventory-service", "ERROR",
                 f"Stock for {sku} went negative: current=-{self.rng.randint(1, 5)} units after double-fulfillment",
                 "updateStock"))
            self.negative_sku_count += 1

            # Sentry event
            conn.execute(
                "INSERT INTO sentry_events (timestamp, project, title, level) VALUES (?,?,?,?)",
                (later.isoformat(), "inventory-service",
                 f"NegativeStockError: {sku} has negative inventory after fulfillment",
                 "error"))

        # Step 7: Circuit breaker check
        if self.negative_sku_count > 100 and not self.circuit_breaker_tripped:
            self.circuit_breaker_tripped = True
            conn.execute(
                "INSERT INTO logs (timestamp, service, level, message, function) VALUES (?,?,?,?,?)",
                (later.isoformat(), "storefront", "ERROR",
                 f"Circuit breaker TRIPPED: {self.negative_sku_count} SKUs with negative stock. Storefront offline.",
                 "circuitBreaker"))
            conn.execute(
                "INSERT INTO sentry_events (timestamp, project, title, level) VALUES (?,?,?,?)",
                (later.isoformat(), "storefront",
                 "CircuitBreakerOpen: inventory service health check failed",
                 "error"))
            conn.execute(
                "INSERT INTO slack_messages (timestamp, channel, user_name, text) VALUES (?,?,?,?)",
                (later.isoformat(), "alerts", "bot: grafana-alert",
                 f"[FIRING] CRITICAL: Storefront circuit breaker OPEN. {self.negative_sku_count} negative SKUs. Site offline."))

    def _write_metrics_to_db(self, conn, ts):
        """Write a snapshot of system metrics to the database."""
        metrics = {
            "order_processing_success_rate": max(0, min(1, 0.95 + self.rng.gauss(0, 0.02))),
            # NO grpc message size metrics -- agent must find size discrepancy in raw logs
            "grpc_server_handled_total_status_OK": self.rng.randint(9000, 11000),
            "grpc_server_handled_total_status_error": 0,  # SIGNIFICANT SILENCE
            "inventory_negative_skus": self.negative_sku_count,
            "webhook_duplicate_sends_total": self.duplicate_webhook_count,
            "storefront_circuit_breaker_state": 1 if self.circuit_breaker_tripped else 0,
            "tcp_retransmit_rate": self.rng.uniform(0.001, 0.005),  # Normal
            # NO tcp_wmem metric -- agent must discover via kubectl exec or ansible playbook
        }
        for name, value in metrics.items():
            conn.execute(
                "INSERT INTO metrics (timestamp, name, value) VALUES (?,?,?)",
                (ts.isoformat(), name, value))

    def _generate_alert(self, conn, ts):
        """Generate automated Slack alerts based on current cascade state."""
        if self.negative_sku_count > 50:
            conn.execute(
                "INSERT INTO slack_messages (timestamp, channel, user_name, text) VALUES (?,?,?,?)",
                (ts.isoformat(), "alerts", "bot: grafana-alert",
                 f"[FIRING] inventory_negative_skus = {self.negative_sku_count} (threshold: 50)"))
        if self.duplicate_webhook_count > 10:
            conn.execute(
                "INSERT INTO slack_messages (timestamp, channel, user_name, text) VALUES (?,?,?,?)",
                (ts.isoformat(), "alerts", "bot: grafana-alert",
                 f"[FIRING] webhook_duplicate_sends = {self.duplicate_webhook_count} (threshold: 10)"))
