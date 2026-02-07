"""Mock Prometheus MCP server for metrics simulation.

Generates realistic metrics data, PromQL query results, and alert states
based on the failure pattern being debugged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern


class PrometheusMCPServer(BaseMCPServer):
    """Mock Prometheus API server.

    Simulates Prometheus's API with endpoints for:
    - Instant queries
    - Range queries
    - Alert rules and states
    - Targets and service discovery

    Data is deterministically generated from the pattern's
    metrics definitions and observable symptoms.
    """

    service_name = "prometheus"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /api/v1/query",
            "GET /api/v1/query_range",
            "GET /api/v1/alerts",
            "GET /api/v1/rules",
            "GET /api/v1/targets",
            "GET /api/v1/metadata",
            "GET /api/v1/labels",
            "GET /api/v1/label/{name}/values",
        ]

    def _initialize_data(self) -> None:
        """Generate Prometheus data from pattern context."""
        self.metrics: dict[str, dict[str, Any]] = {}
        self.alerts: list[dict[str, Any]] = []
        self.rules: list[dict[str, Any]] = []
        self.targets: list[dict[str, Any]] = []

        # Generate metrics definitions
        self._generate_metrics()

        # Generate alert rules
        self._generate_rules()

        # Generate alert states
        self._generate_alerts()

        # Generate targets
        self._generate_targets()

    def _generate_metrics(self) -> None:
        """Generate metrics based on pattern category."""
        # Common metrics
        common_metrics = {
            "http_requests_total": {
                "type": "counter",
                "help": "Total HTTP requests",
                "labels": ["method", "status", "handler"],
            },
            "http_request_duration_seconds": {
                "type": "histogram",
                "help": "HTTP request latency in seconds",
                "labels": ["method", "handler"],
            },
            "process_cpu_seconds_total": {
                "type": "counter",
                "help": "Total CPU time spent",
                "labels": ["instance"],
            },
            "process_resident_memory_bytes": {
                "type": "gauge",
                "help": "Resident memory size in bytes",
                "labels": ["instance"],
            },
        }

        self.metrics.update(common_metrics)

        # Pattern-specific metrics
        category = (self.pattern.subcategory or self.pattern.category).lower()

        if "race" in category:
            self.metrics.update({
                "lock_acquisitions_total": {
                    "type": "counter",
                    "help": "Total lock acquisition attempts",
                    "labels": ["lock_name", "result"],
                },
                "lock_contention_seconds": {
                    "type": "histogram",
                    "help": "Lock contention wait time",
                    "labels": ["lock_name"],
                },
                "concurrent_operations_total": {
                    "type": "counter",
                    "help": "Total concurrent operations",
                    "labels": ["operation"],
                },
                "data_races_detected_total": {
                    "type": "counter",
                    "help": "Detected data race conditions",
                    "labels": ["resource"],
                },
            })
        elif "split" in category or "partition" in category:
            self.metrics.update({
                "cluster_nodes_total": {
                    "type": "gauge",
                    "help": "Total nodes in cluster",
                    "labels": ["state"],
                },
                "replication_lag_seconds": {
                    "type": "gauge",
                    "help": "Replication lag in seconds",
                    "labels": ["node"],
                },
                "consensus_rounds_total": {
                    "type": "counter",
                    "help": "Total consensus rounds",
                    "labels": ["result"],
                },
                "partition_events_total": {
                    "type": "counter",
                    "help": "Network partition events",
                    "labels": ["type"],
                },
            })
        elif "clock" in category or "time" in category:
            self.metrics.update({
                "clock_drift_seconds": {
                    "type": "gauge",
                    "help": "Clock drift from reference",
                    "labels": ["node"],
                },
                "ntp_sync_status": {
                    "type": "gauge",
                    "help": "NTP synchronization status",
                    "labels": ["node"],
                },
                "timestamp_ordering_errors_total": {
                    "type": "counter",
                    "help": "Timestamp ordering violations",
                    "labels": ["operation"],
                },
            })

        # Add any metrics from pattern definition
        if self.pattern.observable_symptoms and self.pattern.observable_symptoms.metrics:
            for metric in self.pattern.observable_symptoms.metrics:
                metric_name = metric.name.replace(".", "_").replace("-", "_")
                self.metrics[metric_name] = {
                    "type": "gauge",
                    "help": f"Pattern metric: {metric.name}",
                    "labels": ["instance"],
                }

    def _generate_rules(self) -> None:
        """Generate alert rules."""
        rules_group = {
            "name": "sdlc_alerts",
            "rules": [],
        }

        # Add rules based on pattern
        category = (self.pattern.subcategory or self.pattern.category).lower()

        if "race" in category:
            rules_group["rules"].extend([
                {
                    "name": "HighLockContention",
                    "query": "rate(lock_acquisitions_total{result='contention'}[5m]) > 10",
                    "duration": "5m",
                    "labels": {"severity": "warning"},
                    "annotations": {"summary": "High lock contention detected"},
                },
                {
                    "name": "DataRaceDetected",
                    "query": "increase(data_races_detected_total[5m]) > 0",
                    "duration": "1m",
                    "labels": {"severity": "critical"},
                    "annotations": {"summary": "Data race condition detected"},
                },
            ])
        elif "split" in category:
            rules_group["rules"].extend([
                {
                    "name": "ClusterSplitBrain",
                    "query": "count(cluster_nodes_total{state='active'}) > 1",
                    "duration": "1m",
                    "labels": {"severity": "critical"},
                    "annotations": {"summary": "Split-brain condition detected"},
                },
                {
                    "name": "HighReplicationLag",
                    "query": "replication_lag_seconds > 30",
                    "duration": "5m",
                    "labels": {"severity": "warning"},
                    "annotations": {"summary": "Replication lag exceeds threshold"},
                },
            ])
        elif "clock" in category:
            rules_group["rules"].extend([
                {
                    "name": "ClockDriftHigh",
                    "query": "abs(clock_drift_seconds) > 1",
                    "duration": "2m",
                    "labels": {"severity": "warning"},
                    "annotations": {"summary": "Significant clock drift detected"},
                },
                {
                    "name": "TimestampOrderingError",
                    "query": "increase(timestamp_ordering_errors_total[5m]) > 0",
                    "duration": "1m",
                    "labels": {"severity": "critical"},
                    "annotations": {"summary": "Timestamp ordering violation"},
                },
            ])

        # Common rules
        rules_group["rules"].extend([
            {
                "name": "HighErrorRate",
                "query": "rate(http_requests_total{status=~'5..'}[5m]) / rate(http_requests_total[5m]) > 0.05",
                "duration": "5m",
                "labels": {"severity": "critical"},
                "annotations": {"summary": "Error rate exceeds 5%"},
            },
            {
                "name": "HighLatency",
                "query": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1",
                "duration": "5m",
                "labels": {"severity": "warning"},
                "annotations": {"summary": "P99 latency exceeds 1 second"},
            },
        ])

        self.rules = [rules_group]

    def _generate_alerts(self) -> None:
        """Generate active alerts."""
        category = (self.pattern.subcategory or self.pattern.category).lower()

        # Primary alert (firing)
        if "race" in category:
            primary_alert = {
                "labels": {
                    "alertname": "DataRaceDetected",
                    "severity": "critical",
                    "instance": "server-1:9090",
                },
                "annotations": {
                    "summary": "Data race condition detected",
                    "description": "Concurrent modification of shared resource detected",
                },
                "state": "firing",
                "activeAt": self._random_timestamp(2, 1).isoformat() + "Z",
                "value": "1",
            }
        elif "split" in category:
            primary_alert = {
                "labels": {
                    "alertname": "ClusterSplitBrain",
                    "severity": "critical",
                    "cluster": "primary",
                },
                "annotations": {
                    "summary": "Split-brain condition detected",
                    "description": "Multiple nodes claiming leadership",
                },
                "state": "firing",
                "activeAt": self._random_timestamp(2, 1).isoformat() + "Z",
                "value": "2",
            }
        elif "clock" in category:
            primary_alert = {
                "labels": {
                    "alertname": "TimestampOrderingError",
                    "severity": "critical",
                    "node": "server-3",
                },
                "annotations": {
                    "summary": "Timestamp ordering violation",
                    "description": "Events received out of causal order",
                },
                "state": "firing",
                "activeAt": self._random_timestamp(2, 1).isoformat() + "Z",
                "value": "5",
            }
        else:
            primary_alert = {
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "service": "main",
                },
                "annotations": {
                    "summary": "Error rate exceeds threshold",
                },
                "state": "firing",
                "activeAt": self._random_timestamp(2, 1).isoformat() + "Z",
                "value": "0.08",
            }

        self.alerts.append(primary_alert)

        # Supporting alerts
        self.alerts.append({
            "labels": {
                "alertname": "HighLatency",
                "severity": "warning",
                "handler": "/api/critical",
            },
            "annotations": {
                "summary": "P99 latency exceeds threshold",
            },
            "state": "firing",
            "activeAt": self._random_timestamp(1, 0).isoformat() + "Z",
            "value": "2.3",
        })

    def _generate_targets(self) -> None:
        """Generate scrape targets."""
        self.targets = [
            {
                "discoveredLabels": {"__address__": f"server-{i}:9090", "job": "main-service"},
                "labels": {"instance": f"server-{i}:9090", "job": "main-service"},
                "scrapePool": "main-service",
                "scrapeUrl": f"http://server-{i}:9090/metrics",
                "lastScrape": datetime.now().isoformat() + "Z",
                "lastScrapeDuration": self.rng.uniform(0.01, 0.1),
                "health": "up",
            }
            for i in range(1, 6)
        ]

    def _query_metric(self, query: str, time_point: datetime | None = None) -> list[dict[str, Any]]:
        """Simulate a PromQL query result."""
        results = []
        time_point = time_point or datetime.now()

        # Parse simple metric name from query
        metric_match = re.match(r"^(\w+)", query)
        if not metric_match:
            return results

        metric_name = metric_match.group(1)

        # Generate some sample values
        for i in range(1, 4):
            instance = f"server-{i}:9090"

            # Generate value based on metric type and query
            if "rate" in query or "increase" in query:
                value = self.rng.uniform(0, 100)
            elif "histogram_quantile" in query:
                value = self.rng.uniform(0.1, 5)
            elif "error" in metric_name.lower() or "race" in metric_name.lower():
                value = self.rng.uniform(0.01, 0.2)
            else:
                value = self.rng.uniform(0, 1000)

            results.append({
                "metric": {
                    "__name__": metric_name,
                    "instance": instance,
                    "job": "main-service",
                },
                "value": [time_point.timestamp(), str(value)],
            })

        return results

    def _query_range(
        self, query: str, start: datetime, end: datetime, step: int
    ) -> list[dict[str, Any]]:
        """Simulate a range query result."""
        results = []

        # Generate time series
        for i in range(1, 3):
            instance = f"server-{i}:9090"
            values = []

            current = start
            while current <= end:
                # Generate realistic-looking values with some pattern
                base_value = self.rng.uniform(10, 100)
                # Add spike near the incident
                incident_time = datetime.now() - timedelta(hours=1)
                if abs((current - incident_time).total_seconds()) < 1800:  # Within 30 min
                    base_value *= self.rng.uniform(2, 5)  # Spike

                values.append([current.timestamp(), str(base_value)])
                current += timedelta(seconds=step)

            results.append({
                "metric": {"instance": instance, "job": "main-service"},
                "values": values,
            })

        return results

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Handle Prometheus API requests."""
        endpoint = endpoint.rstrip("/")

        # GET /api/v1/query
        if method == "GET" and endpoint == "/api/v1/query":
            return self._handle_instant_query(params)

        # GET /api/v1/query_range
        if method == "GET" and endpoint == "/api/v1/query_range":
            return self._handle_range_query(params)

        # GET /api/v1/alerts
        if method == "GET" and endpoint == "/api/v1/alerts":
            return Response(200, {
                "status": "success",
                "data": {"alerts": self.alerts},
            })

        # GET /api/v1/rules
        if method == "GET" and endpoint == "/api/v1/rules":
            return Response(200, {
                "status": "success",
                "data": {"groups": self.rules},
            })

        # GET /api/v1/targets
        if method == "GET" and endpoint == "/api/v1/targets":
            return Response(200, {
                "status": "success",
                "data": {"activeTargets": self.targets},
            })

        # GET /api/v1/metadata
        if method == "GET" and endpoint == "/api/v1/metadata":
            return Response(200, {
                "status": "success",
                "data": self.metrics,
            })

        # GET /api/v1/labels
        if method == "GET" and endpoint == "/api/v1/labels":
            labels = set()
            for metric_info in self.metrics.values():
                labels.update(metric_info.get("labels", []))
            labels.add("__name__")
            labels.add("instance")
            labels.add("job")
            return Response(200, {
                "status": "success",
                "data": sorted(labels),
            })

        # GET /api/v1/label/{name}/values
        match = re.match(r"^/api/v1/label/([^/]+)/values$", endpoint)
        if match and method == "GET":
            return self._handle_label_values(match.group(1))

        return Response(404, {"error": f"Endpoint not found: {method} {endpoint}"})

    def _handle_instant_query(self, params: dict[str, Any]) -> Response:
        """Handle instant query."""
        query = params.get("query", "")
        if not query:
            return Response(400, {"status": "error", "error": "query parameter required"})

        time_param = params.get("time")
        time_point = datetime.fromtimestamp(float(time_param)) if time_param else None

        results = self._query_metric(query, time_point)

        return Response(200, {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": results,
            },
        })

    def _handle_range_query(self, params: dict[str, Any]) -> Response:
        """Handle range query."""
        query = params.get("query", "")
        if not query:
            return Response(400, {"status": "error", "error": "query parameter required"})

        start = params.get("start", (datetime.now() - timedelta(hours=1)).timestamp())
        end = params.get("end", datetime.now().timestamp())
        step = params.get("step", 60)

        start_dt = datetime.fromtimestamp(float(start))
        end_dt = datetime.fromtimestamp(float(end))

        results = self._query_range(query, start_dt, end_dt, int(step))

        return Response(200, {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": results,
            },
        })

    def _handle_label_values(self, label_name: str) -> Response:
        """Handle label values query."""
        if label_name == "__name__":
            return Response(200, {
                "status": "success",
                "data": list(self.metrics.keys()),
            })
        elif label_name == "instance":
            return Response(200, {
                "status": "success",
                "data": [f"server-{i}:9090" for i in range(1, 6)],
            })
        elif label_name == "job":
            return Response(200, {
                "status": "success",
                "data": ["main-service", "prometheus"],
            })
        else:
            return Response(200, {
                "status": "success",
                "data": [],
            })
