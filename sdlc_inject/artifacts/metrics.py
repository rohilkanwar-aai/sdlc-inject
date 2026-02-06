"""Prometheus/Grafana metrics artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class MetricsArtifactGenerator(ArtifactGenerator):
    """Generates realistic Prometheus metrics and Grafana dashboard data."""

    def generate(self) -> dict[str, Any]:
        """Generate metrics data."""
        return {
            "prometheus_snapshot": self._generate_prometheus_snapshot(),
            "grafana_dashboard": self._generate_grafana_dashboard(),
            "alert_rules": self._generate_alert_rules(),
            "timeseries": self._generate_timeseries_data(),
        }

    def _generate_prometheus_snapshot(self) -> dict[str, Any]:
        """Generate Prometheus metrics snapshot."""
        metrics = []

        # Standard HTTP metrics
        metrics.extend(self._http_metrics())

        # Pattern-specific metrics
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.metrics:
            for m in symptoms.metrics:
                metrics.append(self._pattern_metric(m))

        # Resource metrics
        metrics.extend(self._resource_metrics())

        return {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": metrics,
            },
        }

    def _http_metrics(self) -> list[dict[str, Any]]:
        """Generate HTTP-related metrics."""
        return [
            {
                "metric": {
                    "__name__": "http_requests_total",
                    "method": "POST",
                    "path": "/api/buffers/acquire",
                    "status": "200",
                    "service": self.pattern.target_codebase.name,
                },
                "value": [self.base_time.timestamp(), str(self.rng.randint(10000, 50000))],
            },
            {
                "metric": {
                    "__name__": "http_requests_total",
                    "method": "POST",
                    "path": "/api/buffers/acquire",
                    "status": "500",
                    "service": self.pattern.target_codebase.name,
                },
                "value": [self.base_time.timestamp(), str(self.rng.randint(500, 2000))],
            },
            {
                "metric": {
                    "__name__": "http_request_duration_seconds",
                    "quantile": "0.99",
                    "path": "/api/buffers/acquire",
                },
                "value": [self.base_time.timestamp(), str(self.rng.uniform(1.5, 3.0))],
            },
            {
                "metric": {
                    "__name__": "http_request_duration_seconds",
                    "quantile": "0.50",
                    "path": "/api/buffers/acquire",
                },
                "value": [self.base_time.timestamp(), str(self.rng.uniform(0.05, 0.2))],
            },
        ]

    def _pattern_metric(self, metric) -> dict[str, Any]:
        """Generate a metric from pattern definition."""
        value = "0"
        if metric.type == "counter":
            value = str(self.rng.randint(100, 1000))
        elif metric.type == "gauge":
            value = str(self.rng.uniform(0, 100))
        elif metric.type == "histogram":
            value = str(self.rng.uniform(0.01, 2.0))

        return {
            "metric": {
                "__name__": metric.name,
                "service": self.pattern.target_codebase.name,
            },
            "value": [self.base_time.timestamp(), value],
        }

    def _resource_metrics(self) -> list[dict[str, Any]]:
        """Generate resource utilization metrics."""
        return [
            {
                "metric": {
                    "__name__": "db_pool_connections_active",
                    "pool": "main",
                },
                "value": [self.base_time.timestamp(), str(self.rng.randint(45, 50))],  # Near limit
            },
            {
                "metric": {
                    "__name__": "db_pool_connections_max",
                    "pool": "main",
                },
                "value": [self.base_time.timestamp(), "50"],
            },
            {
                "metric": {
                    "__name__": "process_cpu_seconds_total",
                    "instance": "collab-1",
                },
                "value": [self.base_time.timestamp(), str(self.rng.randint(10000, 50000))],
            },
            {
                "metric": {
                    "__name__": "process_resident_memory_bytes",
                    "instance": "collab-1",
                },
                "value": [self.base_time.timestamp(), str(self.rng.randint(500000000, 2000000000))],
            },
        ]

    def _generate_grafana_dashboard(self) -> dict[str, Any]:
        """Generate Grafana dashboard definition."""
        panels = [
            self._panel("Error Rate", "rate(http_requests_total{status=~\"5..\"}[5m])", "timeseries"),
            self._panel("Request Latency P99", "histogram_quantile(0.99, http_request_duration_seconds)", "timeseries"),
            self._panel("Active Connections", "db_pool_connections_active", "gauge"),
            self._panel("Request Rate", "rate(http_requests_total[5m])", "timeseries"),
        ]

        # Add pattern-specific panels
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.metrics:
            for m in symptoms.metrics:
                panels.append(self._panel(
                    m.name.replace("_", " ").title(),
                    m.name,
                    "timeseries" if m.type != "gauge" else "gauge"
                ))

        return {
            "id": self.rng.randint(1, 1000),
            "uid": self.random_uuid()[:8],
            "title": f"{self.pattern.target_codebase.name} - {self.pattern.id}",
            "tags": ["incident", self.pattern.category.lower()],
            "timezone": "browser",
            "refresh": "5s",
            "time": {
                "from": "now-2h",
                "to": "now",
            },
            "panels": panels,
            "annotations": {
                "list": [
                    {
                        "name": "Incident Start",
                        "datasource": "-- Grafana --",
                        "enable": True,
                        "iconColor": "red",
                    },
                ],
            },
        }

    def _panel(self, title: str, query: str, panel_type: str) -> dict[str, Any]:
        """Generate a Grafana panel."""
        panel_id = self.rng.randint(1, 100)
        return {
            "id": panel_id,
            "title": title,
            "type": panel_type,
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
            "targets": [
                {
                    "expr": query,
                    "legendFormat": "{{instance}}",
                    "refId": "A",
                }
            ],
            "options": {},
            "fieldConfig": {
                "defaults": {
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 50},
                            {"color": "red", "value": 80},
                        ],
                    },
                },
            },
        }

    def _generate_alert_rules(self) -> list[dict[str, Any]]:
        """Generate Prometheus alerting rules."""
        rules = [
            {
                "alert": "HighErrorRate",
                "expr": 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05',
                "for": "5m",
                "labels": {
                    "severity": "critical",
                    "service": self.pattern.target_codebase.name,
                },
                "annotations": {
                    "summary": "High error rate on {{ $labels.service }}",
                    "description": "Error rate is {{ $value | humanizePercentage }}",
                },
                "state": "firing",
                "activeAt": self.random_timestamp(offset_minutes=-120),
            },
            {
                "alert": "HighLatency",
                "expr": "histogram_quantile(0.99, http_request_duration_seconds_bucket) > 2",
                "for": "5m",
                "labels": {
                    "severity": "warning",
                    "service": self.pattern.target_codebase.name,
                },
                "annotations": {
                    "summary": "High P99 latency on {{ $labels.service }}",
                    "description": "P99 latency is {{ $value }}s",
                },
                "state": "firing",
                "activeAt": self.random_timestamp(offset_minutes=-118),
            },
        ]

        # Add pattern-specific alerts
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.metrics:
            for m in symptoms.metrics:
                if m.alert_threshold:
                    rules.append({
                        "alert": f"{m.name.title().replace('_', '')}Alert",
                        "expr": f"{m.name} {m.alert_threshold}",
                        "for": "5m",
                        "labels": {"severity": "critical"},
                        "annotations": {"summary": f"{m.name} alert triggered"},
                        "state": "firing",
                        "activeAt": self.random_timestamp(offset_minutes=-110),
                    })

        return rules

    def _generate_timeseries_data(self) -> dict[str, list]:
        """Generate time series data for visualization."""
        # Generate 2 hours of data at 1-minute intervals
        timestamps = []
        error_rate = []
        latency_p99 = []
        connections = []

        for i in range(120):
            ts = (self.base_time - timedelta(minutes=120) + timedelta(minutes=i)).isoformat()
            timestamps.append(ts)

            # Simulate incident pattern: normal -> spike -> recovery
            if i < 30:  # Before incident
                error_rate.append(self.rng.uniform(0.001, 0.005))
                latency_p99.append(self.rng.uniform(0.04, 0.06))
                connections.append(self.rng.randint(10, 20))
            elif i < 90:  # During incident
                error_rate.append(self.rng.uniform(0.05, 0.15))
                latency_p99.append(self.rng.uniform(1.5, 3.0))
                connections.append(self.rng.randint(45, 50))
            else:  # Recovery
                recovery_factor = (i - 90) / 30
                error_rate.append(self.rng.uniform(0.001, 0.05) * (1 - recovery_factor))
                latency_p99.append(self.rng.uniform(0.04, 1.5) * (1 - recovery_factor) + 0.05)
                connections.append(self.rng.randint(10, 30))

        return {
            "timestamps": timestamps,
            "error_rate": error_rate,
            "latency_p99": latency_p99,
            "active_connections": connections,
        }

    def save(self, output_dir: Path) -> list[Path]:
        """Save metrics artifacts to files."""
        metrics_dir = output_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save Prometheus snapshot
        prom_path = metrics_dir / "prometheus_snapshot.json"
        prom_path.write_text(json.dumps(artifacts["prometheus_snapshot"], indent=2))
        files.append(prom_path)

        # Save Grafana dashboard
        grafana_path = metrics_dir / "grafana_dashboard.json"
        grafana_path.write_text(json.dumps(artifacts["grafana_dashboard"], indent=2))
        files.append(grafana_path)

        # Save alert rules
        rules_path = metrics_dir / "alert_rules.yaml"
        rules_content = "groups:\n  - name: incident_alerts\n    rules:\n"
        for rule in artifacts["alert_rules"]:
            rules_content += f"      - alert: {rule['alert']}\n"
            rules_content += f"        expr: {rule['expr']}\n"
            rules_content += f"        for: {rule['for']}\n"
        rules_path.write_text(rules_content)
        files.append(rules_path)

        # Save timeseries data (for visualization tools)
        ts_path = metrics_dir / "timeseries.json"
        ts_path.write_text(json.dumps(artifacts["timeseries"], indent=2))
        files.append(ts_path)

        return files
