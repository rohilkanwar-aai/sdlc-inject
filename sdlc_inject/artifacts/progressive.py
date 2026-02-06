"""Progressive incident simulation with real-time updates."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class IncidentPhase(Enum):
    """Incident lifecycle phases."""
    NORMAL = "normal"
    DEGRADED = "degraded"
    ALERT_FIRED = "alert_fired"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MITIGATING = "mitigating"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


@dataclass
class TimelineEvent:
    """A single event in the incident timeline."""
    timestamp: datetime
    phase: IncidentPhase
    event_type: str
    source: str
    data: dict


class ProgressiveIncidentGenerator(ArtifactGenerator):
    """Generates progressive incident artifacts that show evolution over time."""

    def __init__(self, pattern: Pattern, seed: int | None = None, duration_minutes: int = 120):
        super().__init__(pattern, seed)
        self.duration_minutes = duration_minutes
        self.incident_start = self.base_time - timedelta(minutes=duration_minutes)
        self.timeline: list[TimelineEvent] = []

    def generate(self) -> dict[str, Any]:
        """Generate all progressive artifacts."""
        # Build the incident timeline first
        self._build_timeline()

        return {
            "timeline": self._format_timeline(),
            "status_page": self._generate_status_page_updates(),
            "metrics_stream": self._generate_metrics_stream(),
            "log_stream": self._generate_log_stream(),
            "webhook_events": self._generate_webhook_events(),
            "rate_limit_events": self._generate_rate_limit_events(),
            "escalation_chain": self._generate_escalation_chain(),
            "runbook_execution": self._generate_runbook_execution(),
        }

    def _build_timeline(self) -> None:
        """Build the incident timeline with realistic phases."""
        self.timeline = []

        # Phase timings (minutes from incident start)
        phases = [
            (0, IncidentPhase.NORMAL, "baseline"),
            (15, IncidentPhase.DEGRADED, "degradation_starts"),
            (20, IncidentPhase.ALERT_FIRED, "alert_triggered"),
            (25, IncidentPhase.ACKNOWLEDGED, "on_call_ack"),
            (30, IncidentPhase.INVESTIGATING, "investigation_starts"),
            (60, IncidentPhase.IDENTIFIED, "root_cause_found"),
            (75, IncidentPhase.MITIGATING, "fix_deployed"),
            (90, IncidentPhase.MONITORING, "monitoring_recovery"),
            (120, IncidentPhase.RESOLVED, "incident_closed"),
        ]

        for offset, phase, event_type in phases:
            ts = self.incident_start + timedelta(minutes=offset)
            self.timeline.append(TimelineEvent(
                timestamp=ts,
                phase=phase,
                event_type=event_type,
                source="incident_controller",
                data=self._generate_phase_data(phase),
            ))

    def _generate_phase_data(self, phase: IncidentPhase) -> dict:
        """Generate data for each phase."""
        phase_data = {
            IncidentPhase.NORMAL: {
                "error_rate": 0.001,
                "latency_p99_ms": 50,
                "active_connections": 15,
                "status": "operational",
            },
            IncidentPhase.DEGRADED: {
                "error_rate": 0.03,
                "latency_p99_ms": 500,
                "active_connections": 35,
                "status": "degraded_performance",
            },
            IncidentPhase.ALERT_FIRED: {
                "error_rate": 0.08,
                "latency_p99_ms": 2000,
                "active_connections": 48,
                "status": "major_outage",
                "alert_name": f"HighErrorRate_{self.pattern.target_codebase.name}",
            },
            IncidentPhase.ACKNOWLEDGED: {
                "error_rate": 0.10,
                "latency_p99_ms": 2500,
                "responder": "on-call-engineer",
                "ack_method": "pagerduty_app",
            },
            IncidentPhase.INVESTIGATING: {
                "error_rate": 0.12,
                "latency_p99_ms": 3000,
                "hypothesis": "Resource contention under load",
                "tools_used": ["grafana", "sentry", "logs"],
            },
            IncidentPhase.IDENTIFIED: {
                "error_rate": 0.10,
                "latency_p99_ms": 2800,
                "root_cause": self.pattern.name,
                "affected_component": self._get_primary_file(),
            },
            IncidentPhase.MITIGATING: {
                "error_rate": 0.05,
                "latency_p99_ms": 1000,
                "fix_type": "code_change",
                "pr_number": self.rng.randint(1000, 9999),
            },
            IncidentPhase.MONITORING: {
                "error_rate": 0.008,
                "latency_p99_ms": 80,
                "active_connections": 20,
                "status": "monitoring",
            },
            IncidentPhase.RESOLVED: {
                "error_rate": 0.001,
                "latency_p99_ms": 45,
                "active_connections": 18,
                "status": "operational",
                "duration_minutes": self.duration_minutes,
            },
        }
        return phase_data.get(phase, {})

    def _format_timeline(self) -> list[dict]:
        """Format timeline for output."""
        return [
            {
                "timestamp": e.timestamp.isoformat() + "Z",
                "phase": e.phase.value,
                "event_type": e.event_type,
                "source": e.source,
                "data": e.data,
            }
            for e in self.timeline
        ]

    def _generate_status_page_updates(self) -> list[dict[str, Any]]:
        """Generate Statuspage.io style updates."""
        updates = []

        status_map = {
            IncidentPhase.DEGRADED: ("investigating", "We are investigating increased error rates."),
            IncidentPhase.ALERT_FIRED: ("investigating", "We are aware of issues affecting the collaboration service."),
            IncidentPhase.INVESTIGATING: ("identified", "The issue has been identified and we are working on a fix."),
            IncidentPhase.IDENTIFIED: ("identified", f"Root cause identified: {self.pattern.name}. Fix in progress."),
            IncidentPhase.MITIGATING: ("monitoring", "A fix has been deployed. We are monitoring the results."),
            IncidentPhase.RESOLVED: ("resolved", "This incident has been resolved."),
        }

        for event in self.timeline:
            if event.phase in status_map:
                status, body = status_map[event.phase]
                updates.append({
                    "id": self.random_uuid()[:8],
                    "incident_id": f"inc_{self.random_uuid()[:8]}",
                    "status": status,
                    "body": body,
                    "created_at": event.timestamp.isoformat() + "Z",
                    "updated_at": event.timestamp.isoformat() + "Z",
                    "affected_components": [
                        {
                            "id": "comp_1",
                            "name": self.pattern.target_codebase.name,
                            "status": self._component_status(event.phase),
                        }
                    ],
                    "twitter_updated": event.phase in (IncidentPhase.ALERT_FIRED, IncidentPhase.RESOLVED),
                })

        return updates

    def _component_status(self, phase: IncidentPhase) -> str:
        """Map phase to component status."""
        return {
            IncidentPhase.NORMAL: "operational",
            IncidentPhase.DEGRADED: "degraded_performance",
            IncidentPhase.ALERT_FIRED: "major_outage",
            IncidentPhase.ACKNOWLEDGED: "major_outage",
            IncidentPhase.INVESTIGATING: "major_outage",
            IncidentPhase.IDENTIFIED: "partial_outage",
            IncidentPhase.MITIGATING: "degraded_performance",
            IncidentPhase.MONITORING: "degraded_performance",
            IncidentPhase.RESOLVED: "operational",
        }.get(phase, "operational")

    def _generate_metrics_stream(self) -> list[dict[str, Any]]:
        """Generate streaming metrics data points."""
        metrics = []

        # Generate data points every minute
        for minute in range(self.duration_minutes + 1):
            ts = self.incident_start + timedelta(minutes=minute)
            phase = self._get_phase_at(ts)
            phase_data = self._generate_phase_data(phase)

            # Add jitter to make it realistic
            error_rate = phase_data.get("error_rate", 0.001) * (1 + self.rng.uniform(-0.2, 0.2))
            latency = phase_data.get("latency_p99_ms", 50) * (1 + self.rng.uniform(-0.15, 0.15))
            connections = phase_data.get("active_connections", 15) + self.rng.randint(-3, 3)

            metrics.append({
                "timestamp": ts.isoformat() + "Z",
                "metrics": {
                    "http_error_rate": round(error_rate, 4),
                    "http_latency_p99_ms": round(latency, 1),
                    "db_pool_active_connections": max(0, connections),
                    "db_pool_max_connections": 50,
                    "buffer_conflicts_total": self._cumulative_conflicts(minute),
                    "request_rate_per_second": self.rng.randint(100, 500),
                },
                "phase": phase.value,
            })

        return metrics

    def _cumulative_conflicts(self, minute: int) -> int:
        """Calculate cumulative buffer conflicts."""
        # Conflicts accumulate during the incident
        if minute < 15:
            return self.rng.randint(0, 2)
        elif minute < 75:
            # During incident, conflicts accumulate
            base = (minute - 15) * self.rng.randint(5, 15)
            return base + self.rng.randint(0, 50)
        else:
            # After fix, no new conflicts
            return 600 + self.rng.randint(0, 10)

    def _get_phase_at(self, ts: datetime) -> IncidentPhase:
        """Get the incident phase at a given timestamp."""
        current_phase = IncidentPhase.NORMAL
        for event in self.timeline:
            if event.timestamp <= ts:
                current_phase = event.phase
            else:
                break
        return current_phase

    def _generate_log_stream(self) -> list[dict[str, Any]]:
        """Generate streaming log entries."""
        logs = []

        for minute in range(self.duration_minutes + 1):
            ts = self.incident_start + timedelta(minutes=minute)
            phase = self._get_phase_at(ts)

            # Number of logs per minute varies by phase
            num_logs = {
                IncidentPhase.NORMAL: self.rng.randint(5, 10),
                IncidentPhase.DEGRADED: self.rng.randint(15, 25),
                IncidentPhase.ALERT_FIRED: self.rng.randint(30, 50),
                IncidentPhase.ACKNOWLEDGED: self.rng.randint(25, 40),
                IncidentPhase.INVESTIGATING: self.rng.randint(20, 35),
                IncidentPhase.IDENTIFIED: self.rng.randint(15, 25),
                IncidentPhase.MITIGATING: self.rng.randint(10, 20),
                IncidentPhase.MONITORING: self.rng.randint(8, 15),
                IncidentPhase.RESOLVED: self.rng.randint(5, 10),
            }.get(phase, 10)

            for i in range(num_logs):
                log_ts = ts + timedelta(seconds=self.rng.randint(0, 59))
                logs.append(self._generate_log_entry(log_ts, phase))

        # Sort by timestamp
        logs.sort(key=lambda x: x["timestamp"])
        return logs

    def _generate_log_entry(self, ts: datetime, phase: IncidentPhase) -> dict:
        """Generate a single log entry based on phase."""
        # Error probability varies by phase
        error_prob = {
            IncidentPhase.NORMAL: 0.01,
            IncidentPhase.DEGRADED: 0.15,
            IncidentPhase.ALERT_FIRED: 0.30,
            IncidentPhase.ACKNOWLEDGED: 0.25,
            IncidentPhase.INVESTIGATING: 0.20,
            IncidentPhase.IDENTIFIED: 0.15,
            IncidentPhase.MITIGATING: 0.08,
            IncidentPhase.MONITORING: 0.03,
            IncidentPhase.RESOLVED: 0.01,
        }.get(phase, 0.01)

        if self.rng.random() < error_prob:
            return self._error_log(ts)
        else:
            return self._info_log(ts)

    def _error_log(self, ts: datetime) -> dict:
        """Generate an error log entry."""
        symptoms = self.pattern.observable_symptoms
        log_patterns = symptoms.log_messages if symptoms else []

        if log_patterns:
            pattern = self.random_choice(log_patterns)
            message = pattern.pattern.replace(".*", " ").replace("\\d+", str(self.rng.randint(1000, 9999)))
            level = pattern.level.upper()
        else:
            message = "Buffer lock acquisition failed"
            level = "ERROR"

        return {
            "timestamp": ts.isoformat() + "Z",
            "level": level,
            "message": message,
            "service": self.pattern.target_codebase.name,
            "request_id": self.random_uuid()[:16],
            "buffer_id": f"buf_{self.rng.randint(1000, 9999)}",
            "user_id": self.random_uuid()[:8],
        }

    def _info_log(self, ts: datetime) -> dict:
        """Generate an info log entry."""
        messages = [
            "Request completed successfully",
            "Buffer acquired",
            "Lock released",
            "Connection established",
            "Query executed",
        ]
        return {
            "timestamp": ts.isoformat() + "Z",
            "level": "INFO",
            "message": self.random_choice(messages),
            "service": self.pattern.target_codebase.name,
            "request_id": self.random_uuid()[:16],
            "duration_ms": self.rng.randint(5, 100),
        }

    def _generate_webhook_events(self) -> list[dict[str, Any]]:
        """Generate webhook/event stream payloads."""
        events = []

        # Generate events for key moments
        event_templates = [
            (20, "alert.triggered", "prometheus", {
                "alert_name": "HighErrorRate",
                "severity": "critical",
                "value": 0.08,
                "threshold": 0.05,
            }),
            (20, "incident.created", "pagerduty", {
                "incident_key": f"inc_{self.random_uuid()[:8]}",
                "urgency": "high",
            }),
            (25, "incident.acknowledged", "pagerduty", {
                "acknowledger": "on-call-engineer",
                "method": "mobile_app",
            }),
            (30, "channel.created", "slack", {
                "channel_name": f"incident-{self.pattern.id.lower()}-{self.rng.randint(100,999)}",
                "creator": "incident-bot",
            }),
            (60, "annotation.created", "grafana", {
                "dashboard_id": self.rng.randint(1, 100),
                "text": "Root cause identified",
                "tags": ["incident", "root-cause"],
            }),
            (75, "deployment.completed", "github", {
                "sha": self.random_uuid().replace("-", "")[:40],
                "environment": "production",
                "status": "success",
            }),
            (120, "incident.resolved", "pagerduty", {
                "resolver": "on-call-engineer",
                "duration_minutes": 100,
            }),
        ]

        for offset, event_type, source, data in event_templates:
            ts = self.incident_start + timedelta(minutes=offset)
            events.append({
                "id": self.random_uuid(),
                "type": event_type,
                "source": source,
                "timestamp": ts.isoformat() + "Z",
                "data": data,
                "webhook_delivery": {
                    "status": "delivered",
                    "attempts": 1,
                    "response_code": 200,
                },
            })

        return events

    def _generate_rate_limit_events(self) -> list[dict[str, Any]]:
        """Generate rate limiting events."""
        events = []

        # Rate limits kick in during peak incident (minutes 20-75)
        for minute in range(20, 76):
            # Probability of rate limit increases with load
            if self.rng.random() < 0.3:  # 30% chance each minute
                ts = self.incident_start + timedelta(minutes=minute, seconds=self.rng.randint(0, 59))
                events.append(self._rate_limit_event(ts))

        return events

    def _rate_limit_event(self, ts: datetime) -> dict:
        """Generate a single rate limit event."""
        limit_type = self.random_choice(["api", "db_pool", "redis"])

        configs = {
            "api": {
                "endpoint": "/api/buffers/acquire",
                "limit": 1000,
                "window_seconds": 60,
                "current_count": self.rng.randint(1000, 1500),
                "retry_after_seconds": self.rng.randint(5, 30),
            },
            "db_pool": {
                "pool_name": "main",
                "max_connections": 50,
                "waiting_requests": self.rng.randint(10, 50),
                "wait_timeout_ms": self.rng.randint(1000, 5000),
            },
            "redis": {
                "operation": "LOCK",
                "max_ops_per_second": 10000,
                "current_ops": self.rng.randint(10000, 15000),
                "backoff_ms": self.rng.randint(100, 1000),
            },
        }

        return {
            "timestamp": ts.isoformat() + "Z",
            "type": f"rate_limit.{limit_type}",
            "level": "WARNING",
            "message": f"Rate limit exceeded for {limit_type}",
            "details": configs[limit_type],
            "request_id": self.random_uuid()[:16],
            "client_id": self.random_uuid()[:8],
            "response": {
                "status_code": 429,
                "headers": {
                    "Retry-After": str(configs[limit_type].get("retry_after_seconds", 30)),
                    "X-RateLimit-Limit": str(configs[limit_type].get("limit", 1000)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(ts.timestamp()) + 60),
                },
            },
        }

    def _generate_escalation_chain(self) -> list[dict[str, Any]]:
        """Generate PagerDuty escalation chain."""
        escalations = [
            {
                "level": 1,
                "target": {
                    "type": "user",
                    "name": "On-Call Engineer",
                    "email": "oncall@company.com",
                },
                "notified_at": (self.incident_start + timedelta(minutes=20)).isoformat() + "Z",
                "acknowledged_at": (self.incident_start + timedelta(minutes=25)).isoformat() + "Z",
                "notification_channels": ["push", "sms", "phone"],
                "status": "acknowledged",
            },
        ]

        # Add escalation if not acknowledged quickly (simulated scenario)
        if self.rng.random() < 0.3:  # 30% chance of escalation
            escalations.append({
                "level": 2,
                "target": {
                    "type": "user",
                    "name": "Senior Engineer",
                    "email": "senior@company.com",
                },
                "notified_at": (self.incident_start + timedelta(minutes=35)).isoformat() + "Z",
                "acknowledged_at": (self.incident_start + timedelta(minutes=37)).isoformat() + "Z",
                "notification_channels": ["push", "sms"],
                "status": "acknowledged",
                "reason": "Escalated for additional expertise",
            })

        # Add management escalation for long incidents
        if self.duration_minutes > 90:
            escalations.append({
                "level": 3,
                "target": {
                    "type": "schedule",
                    "name": "Engineering Management",
                },
                "notified_at": (self.incident_start + timedelta(minutes=60)).isoformat() + "Z",
                "notification_channels": ["email", "slack"],
                "status": "notified",
                "reason": "Incident duration exceeded 1 hour",
            })

        return escalations

    def _generate_runbook_execution(self) -> list[dict[str, Any]]:
        """Generate runbook execution steps."""
        steps = [
            {
                "step": 1,
                "name": "Verify alert is valid",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=25)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=27)).isoformat() + "Z",
                "output": "Alert confirmed - error rate at 8%",
                "executor": "on-call-engineer",
            },
            {
                "step": 2,
                "name": "Check service health dashboards",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=27)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=30)).isoformat() + "Z",
                "output": "Latency elevated, connection pool near capacity",
                "links": [
                    f"https://grafana.internal/d/{self.pattern.id.lower()}",
                ],
            },
            {
                "step": 3,
                "name": "Check for recent deployments",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=30)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=32)).isoformat() + "Z",
                "output": "No recent deployments in last 24h",
            },
            {
                "step": 4,
                "name": "Review error logs",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=32)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=45)).isoformat() + "Z",
                "output": f"Found pattern: {self._get_log_pattern()}",
                "findings": ["Lock acquisition failures", "Concurrent request conflicts"],
            },
            {
                "step": 5,
                "name": "Identify affected component",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=45)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=60)).isoformat() + "Z",
                "output": f"Root cause in {self._get_primary_file()}",
                "root_cause": self.pattern.name,
            },
            {
                "step": 6,
                "name": "Implement and deploy fix",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=60)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=75)).isoformat() + "Z",
                "output": f"PR #{self.rng.randint(1000, 9999)} merged and deployed",
                "pr_url": f"https://github.com/org/{self.pattern.target_codebase.name}/pull/{self.rng.randint(1000, 9999)}",
            },
            {
                "step": 7,
                "name": "Verify fix and monitor",
                "status": "completed",
                "started_at": (self.incident_start + timedelta(minutes=75)).isoformat() + "Z",
                "completed_at": (self.incident_start + timedelta(minutes=120)).isoformat() + "Z",
                "output": "Error rate returned to baseline, no new conflicts",
            },
        ]

        return steps

    def _get_primary_file(self) -> str:
        """Get primary injection file."""
        if self.pattern.injection and self.pattern.injection.files:
            return self.pattern.injection.files[0].path
        return "unknown.rs"

    def _get_log_pattern(self) -> str:
        """Get a log pattern from the pattern."""
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.log_messages:
            return symptoms.log_messages[0].pattern
        return "lock acquisition failed"

    def save(self, output_dir: Path) -> list[Path]:
        """Save progressive incident artifacts."""
        progressive_dir = output_dir / "progressive"
        progressive_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save timeline
        timeline_path = progressive_dir / "incident_timeline.json"
        timeline_path.write_text(json.dumps(artifacts["timeline"], indent=2))
        files.append(timeline_path)

        # Save status page updates
        status_path = progressive_dir / "status_page_updates.json"
        status_path.write_text(json.dumps(artifacts["status_page"], indent=2))
        files.append(status_path)

        # Save metrics stream (JSONL for streaming)
        metrics_path = progressive_dir / "metrics_stream.jsonl"
        with metrics_path.open("w") as f:
            for point in artifacts["metrics_stream"]:
                f.write(json.dumps(point) + "\n")
        files.append(metrics_path)

        # Save log stream (JSONL)
        logs_path = progressive_dir / "log_stream.jsonl"
        with logs_path.open("w") as f:
            for log in artifacts["log_stream"]:
                f.write(json.dumps(log) + "\n")
        files.append(logs_path)

        # Save webhook events
        webhooks_path = progressive_dir / "webhook_events.json"
        webhooks_path.write_text(json.dumps(artifacts["webhook_events"], indent=2))
        files.append(webhooks_path)

        # Save rate limit events
        rate_limits_path = progressive_dir / "rate_limit_events.json"
        rate_limits_path.write_text(json.dumps(artifacts["rate_limit_events"], indent=2))
        files.append(rate_limits_path)

        # Save escalation chain
        escalation_path = progressive_dir / "escalation_chain.json"
        escalation_path.write_text(json.dumps(artifacts["escalation_chain"], indent=2))
        files.append(escalation_path)

        # Save runbook execution
        runbook_path = progressive_dir / "runbook_execution.json"
        runbook_path.write_text(json.dumps(artifacts["runbook_execution"], indent=2))
        files.append(runbook_path)

        # Generate human-readable incident report
        report_path = progressive_dir / "incident_report.md"
        report_path.write_text(self._generate_incident_report(artifacts))
        files.append(report_path)

        return files

    def _generate_incident_report(self, artifacts: dict) -> str:
        """Generate markdown incident report."""
        timeline = artifacts["timeline"]
        escalation = artifacts["escalation_chain"]
        runbook = artifacts["runbook_execution"]

        report = f"""# Incident Report: {self.pattern.id}

## Summary

- **Service:** {self.pattern.target_codebase.name}
- **Duration:** {self.duration_minutes} minutes
- **Severity:** SEV-2
- **Root Cause:** {self.pattern.name}

## Timeline

| Time | Phase | Event |
|------|-------|-------|
"""
        for event in timeline:
            report += f"| {event['timestamp'][:19]} | {event['phase']} | {event['event_type']} |\n"

        report += """
## Escalation Chain

"""
        for esc in escalation:
            report += f"- **Level {esc['level']}:** {esc['target']['name']} ({esc['status']})\n"

        report += """
## Runbook Execution

"""
        for step in runbook:
            status_icon = "✅" if step["status"] == "completed" else "⏳"
            report += f"{status_icon} **Step {step['step']}:** {step['name']}\n"
            report += f"   - Output: {step['output']}\n\n"

        report += f"""
## Impact

- **Affected Users:** ~{self.rng.randint(100, 1000)}
- **Error Rate Peak:** {max(e['data'].get('error_rate', 0) for e in timeline if 'error_rate' in e.get('data', {})):.1%}
- **Rate Limit Events:** {len(artifacts['rate_limit_events'])}

## Action Items

- [ ] Schedule post-mortem
- [ ] Update runbook with learnings
- [ ] Add alerting for {self.pattern.observable_symptoms.metrics[0].name if self.pattern.observable_symptoms and self.pattern.observable_symptoms.metrics else 'related metrics'}
- [ ] Review similar code paths for same issue
"""
        return report
