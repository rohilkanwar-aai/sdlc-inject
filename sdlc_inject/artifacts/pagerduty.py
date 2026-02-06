"""PagerDuty alert artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class PagerDutyArtifactGenerator(ArtifactGenerator):
    """Generates realistic PagerDuty incidents and alerts."""

    def generate(self) -> dict[str, Any]:
        """Generate PagerDuty incident with timeline."""
        return {
            "incident": self._generate_incident(),
            "alerts": self._generate_alerts(),
            "timeline": self._generate_timeline(),
            "responders": self._generate_responders(),
        }

    def _generate_incident(self) -> dict[str, Any]:
        """Generate PagerDuty incident."""
        return {
            "id": self.random_uuid(),
            "incident_number": self.rng.randint(10000, 99999),
            "title": f"[SEV-2] {self.pattern.name}",
            "description": self._build_description(),
            "status": "acknowledged",
            "urgency": "high",
            "priority": {
                "id": "P2",
                "name": "SEV-2",
                "description": "High impact, requires immediate attention",
            },
            "service": {
                "id": self.random_uuid()[:8],
                "name": self.pattern.target_codebase.name,
                "description": "Collaborative editing service",
            },
            "escalation_policy": {
                "id": self.random_uuid()[:8],
                "name": "Platform Engineering",
            },
            "created_at": self.random_timestamp(offset_minutes=-120),
            "updated_at": self.random_timestamp(offset_minutes=-5),
            "last_status_change_at": self.random_timestamp(offset_minutes=-115),
            "acknowledgements": [
                {
                    "at": self.random_timestamp(offset_minutes=-115),
                    "acknowledger": {
                        "id": self.random_uuid()[:8],
                        "type": "user_reference",
                        "name": "On-Call Engineer",
                    },
                }
            ],
            "assignments": [
                {
                    "at": self.random_timestamp(offset_minutes=-120),
                    "assignee": {
                        "id": self.random_uuid()[:8],
                        "type": "user_reference",
                        "name": "On-Call Engineer",
                    },
                }
            ],
            "html_url": f"https://company.pagerduty.com/incidents/{self.rng.randint(10000, 99999)}",
        }

    def _build_description(self) -> str:
        """Build incident description."""
        symptoms = self.pattern.observable_symptoms
        metrics = symptoms.metrics if symptoms else []

        metric_text = ""
        for m in metrics[:3]:
            metric_text += f"- {m.name}: {m.alert_threshold or 'anomaly detected'}\n"

        return f"""Automated alert triggered by monitoring.

**Service:** {self.pattern.target_codebase.name}
**Pattern:** {self.pattern.id}

**Triggering Metrics:**
{metric_text or "- Error rate exceeded threshold"}

**Potential Impact:**
- User-facing service degradation
- Buffer operations failing intermittently
- Estimated {self.rng.randint(50, 500)} users affected

**Runbook:** https://docs.internal/runbooks/{self.pattern.category.lower().replace(' ', '-')}
"""

    def _generate_alerts(self) -> list[dict[str, Any]]:
        """Generate triggered alerts."""
        alerts = []

        alert_templates = [
            ("High Error Rate", "error_rate_high", f"Error rate > 5% on {self.pattern.target_codebase.name}"),
            ("Latency Spike", "latency_p99_high", "P99 latency > 2000ms"),
            ("Connection Pool", "pool_exhaustion", "Connection pool utilization at 100%"),
        ]

        for name, key, summary in alert_templates:
            alerts.append({
                "id": self.random_uuid(),
                "alert_key": key,
                "type": "alert",
                "status": "triggered",
                "severity": "critical",
                "summary": summary,
                "source": "prometheus",
                "created_at": self.random_timestamp(offset_minutes=-120 + len(alerts) * 2),
                "suppressed": False,
                "body": {
                    "type": "alert_body",
                    "contexts": self._generate_alert_contexts(),
                    "details": {
                        "alert_name": name,
                        "firing_value": self.rng.uniform(5, 20),
                        "threshold": 5.0,
                        "environment": "production",
                    },
                },
            })

        return alerts

    def _generate_alert_contexts(self) -> list[dict[str, Any]]:
        """Generate alert context links."""
        return [
            {
                "type": "link",
                "href": f"https://grafana.internal/d/{self.pattern.id.lower()}",
                "text": "View Dashboard",
            },
            {
                "type": "link",
                "href": f"https://sentry.io/issues/?query={self.pattern.id}",
                "text": "View Sentry Errors",
            },
            {
                "type": "link",
                "href": f"https://logs.internal/explore?pattern={self.pattern.id}",
                "text": "View Logs",
            },
        ]

    def _generate_timeline(self) -> list[dict[str, Any]]:
        """Generate incident timeline entries."""
        entries = [
            (-120, "incident.trigger", "Incident triggered by alert: error_rate_high"),
            (-120, "incident.delegate", "Escalated to Platform Engineering on-call"),
            (-119, "incident.notify", "Notification sent via SMS"),
            (-119, "incident.notify", "Notification sent via Slack"),
            (-115, "incident.acknowledge", "Acknowledged by On-Call Engineer"),
            (-115, "annotate", "Starting investigation - checking dashboards"),
            (-90, "annotate", "Identified elevated error rate on buffer endpoint"),
            (-60, "annotate", "Root cause hypothesis: race condition in lock acquisition"),
            (-30, "annotate", "Root cause confirmed - PR in progress"),
            (-10, "annotate", "Fix deployed to production"),
            (-5, "annotate", "Monitoring - error rate returning to baseline"),
        ]

        return [
            {
                "id": self.random_uuid()[:8],
                "type": entry_type,
                "summary": summary,
                "created_at": self.random_timestamp(offset_minutes=offset),
            }
            for offset, entry_type, summary in entries
        ]

    def _generate_responders(self) -> list[dict[str, Any]]:
        """Generate incident responders."""
        return [
            {
                "id": self.random_uuid()[:8],
                "type": "user_reference",
                "name": "On-Call Engineer",
                "email": "oncall@company.com",
                "role": "Incident Commander",
                "joined_at": self.random_timestamp(offset_minutes=-115),
            },
            {
                "id": self.random_uuid()[:8],
                "type": "user_reference",
                "name": "Senior Engineer",
                "email": "senior@company.com",
                "role": "Subject Matter Expert",
                "joined_at": self.random_timestamp(offset_minutes=-100),
            },
        ]

    def save(self, output_dir: Path) -> list[Path]:
        """Save PagerDuty artifacts to files."""
        pd_dir = output_dir / "pagerduty"
        pd_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save incident
        incident_path = pd_dir / "incident.json"
        incident_path.write_text(json.dumps(artifacts["incident"], indent=2))
        files.append(incident_path)

        # Save alerts
        alerts_path = pd_dir / "alerts.json"
        alerts_path.write_text(json.dumps(artifacts["alerts"], indent=2))
        files.append(alerts_path)

        # Save full export
        export_path = pd_dir / "pagerduty_export.json"
        export_path.write_text(json.dumps(artifacts, indent=2))
        files.append(export_path)

        return files
