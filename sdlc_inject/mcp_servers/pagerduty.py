"""Mock PagerDuty MCP server for incident management simulation.

Generates realistic incidents, alerts, and escalation chains
based on the failure pattern being debugged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern


class PagerDutyMCPServer(BaseMCPServer):
    """Mock PagerDuty API server.

    Simulates PagerDuty's API with endpoints for:
    - Incidents and incident details
    - Alerts and alert grouping
    - Escalation policies
    - On-call schedules

    Data is deterministically generated from the pattern's
    trigger conditions and severity.
    """

    service_name = "pagerduty"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /incidents",
            "GET /incidents/{id}",
            "GET /incidents/{id}/alerts",
            "GET /incidents/{id}/log_entries",
            "PUT /incidents/{id}/resolve",
            "PUT /incidents/{id}/acknowledge",
            "GET /services",
            "GET /escalation_policies",
            "GET /oncalls",
        ]

    def _initialize_data(self) -> None:
        """Generate PagerDuty data from pattern context."""
        self.incidents: list[dict[str, Any]] = []
        self.alerts: dict[str, list[dict[str, Any]]] = {}
        self.log_entries: dict[str, list[dict[str, Any]]] = {}
        self.services: list[dict[str, Any]] = []
        self.escalation_policies: list[dict[str, Any]] = []
        self.oncalls: list[dict[str, Any]] = []

        # Generate services
        self._generate_services()

        # Generate escalation policies
        self._generate_escalation_policies()

        # Generate on-call schedule
        self._generate_oncalls()

        # Generate main incident
        self._generate_primary_incident()

        # Generate historical incidents
        self._generate_historical_incidents()

    def _generate_services(self) -> None:
        """Generate monitored services."""
        service_name = self.pattern.target_codebase.name if self.pattern.target_codebase else "main-service"

        self.services = [
            {
                "id": f"P{self._random_id(length=7).upper()}",
                "name": service_name,
                "description": "Primary production service",
                "status": "active",
                "escalation_policy": {"id": "POLICYABC"},
                "created_at": (datetime.now() - timedelta(days=365)).isoformat() + "Z",
                "alert_creation": "create_alerts_and_incidents",
                "integrations": [
                    {"type": "prometheus_integration"},
                    {"type": "datadog_integration"},
                ],
            },
            {
                "id": f"P{self._random_id(length=7).upper()}",
                "name": "database-cluster",
                "description": "Database cluster monitoring",
                "status": "active",
                "escalation_policy": {"id": "POLICYDEF"},
            },
            {
                "id": f"P{self._random_id(length=7).upper()}",
                "name": "api-gateway",
                "description": "API Gateway service",
                "status": "active",
                "escalation_policy": {"id": "POLICYABC"},
            },
        ]

    def _generate_escalation_policies(self) -> None:
        """Generate escalation policies."""
        self.escalation_policies = [
            {
                "id": "POLICYABC",
                "name": "Engineering On-Call",
                "escalation_rules": [
                    {
                        "escalation_delay_in_minutes": 15,
                        "targets": [
                            {"type": "schedule_reference", "id": "SCHEDULE1"},
                        ],
                    },
                    {
                        "escalation_delay_in_minutes": 30,
                        "targets": [
                            {"type": "user_reference", "id": "USER1", "name": "Tech Lead"},
                        ],
                    },
                    {
                        "escalation_delay_in_minutes": 60,
                        "targets": [
                            {"type": "user_reference", "id": "USER2", "name": "Engineering Manager"},
                        ],
                    },
                ],
            },
        ]

    def _generate_oncalls(self) -> None:
        """Generate on-call schedule."""
        self.oncalls = [
            {
                "user": {
                    "id": "USER_ONCALL",
                    "name": "Sarah Chen",
                    "email": "sarah.chen@company.com",
                },
                "schedule": {"id": "SCHEDULE1", "name": "Primary On-Call"},
                "escalation_policy": {"id": "POLICYABC"},
                "escalation_level": 1,
                "start": (datetime.now() - timedelta(hours=8)).isoformat() + "Z",
                "end": (datetime.now() + timedelta(hours=16)).isoformat() + "Z",
            },
            {
                "user": {
                    "id": "USER_BACKUP",
                    "name": "Mike Johnson",
                    "email": "mike.johnson@company.com",
                },
                "schedule": {"id": "SCHEDULE2", "name": "Backup On-Call"},
                "escalation_policy": {"id": "POLICYABC"},
                "escalation_level": 2,
            },
        ]

    def _generate_primary_incident(self) -> None:
        """Generate the main active incident."""
        incident_id = f"P{self._random_id(length=7).upper()}"

        # Determine severity based on pattern difficulty
        if self.pattern.difficulty:
            pass_rate = self.pattern.difficulty.frontier_model_pass_rate_percent or 50
            if pass_rate < 20:
                urgency = "high"
            elif pass_rate < 40:
                urgency = "high"
            else:
                urgency = "low"
        else:
            urgency = "high"

        # Build incident title from pattern
        category = (self.pattern.subcategory or self.pattern.category).lower()
        if "race" in category:
            title = "Data inconsistency detected - possible race condition"
        elif "split" in category:
            title = "Cluster split-brain detected"
        elif "clock" in category:
            title = "Timestamp ordering failures detected"
        else:
            title = f"Alert: {self.pattern.name}"

        incident = {
            "id": incident_id,
            "incident_number": self.rng.randint(1000, 9999),
            "title": title,
            "description": self.pattern.description[:500] if self.pattern.description else title,
            "created_at": self._random_timestamp(2, 1).isoformat() + "Z",
            "status": "acknowledged",
            "urgency": urgency,
            "priority": {"id": "P1", "name": "P1", "color": "FF0000"} if urgency == "high" else None,
            "service": {
                "id": self.services[0]["id"],
                "name": self.services[0]["name"],
            },
            "escalation_policy": {"id": "POLICYABC"},
            "assignments": [
                {
                    "at": self._random_timestamp(1, 0).isoformat() + "Z",
                    "assignee": {"id": "USER_ONCALL", "name": "Sarah Chen"},
                }
            ],
            "acknowledgements": [
                {
                    "at": self._random_timestamp(1, 0).isoformat() + "Z",
                    "acknowledger": {"id": "USER_ONCALL", "name": "Sarah Chen"},
                }
            ],
            "last_status_change_at": self._random_timestamp(1, 0).isoformat() + "Z",
            "alert_counts": {"all": 5, "triggered": 0, "resolved": 2},
        }

        self.incidents.append(incident)
        self._generate_alerts_for_incident(incident_id, is_primary=True)
        self._generate_log_entries(incident_id, is_primary=True)

    def _generate_historical_incidents(self) -> None:
        """Generate historical resolved incidents."""
        historical = [
            ("Memory usage warning", "resolved", 72),
            ("API latency spike", "resolved", 168),
            ("Database connection errors", "resolved", 336),
        ]

        for title, status, hours_ago in historical:
            incident_id = f"P{self._random_id(length=7).upper()}"
            created = self._random_timestamp(hours_ago + 1, hours_ago)
            resolved = created + timedelta(hours=self.rng.randint(1, 4))

            incident = {
                "id": incident_id,
                "incident_number": self.rng.randint(1000, 9999),
                "title": title,
                "created_at": created.isoformat() + "Z",
                "status": status,
                "urgency": "low",
                "service": {
                    "id": self._random_choice(self.services)["id"],
                    "name": self._random_choice(self.services)["name"],
                },
                "resolved_at": resolved.isoformat() + "Z" if status == "resolved" else None,
            }
            self.incidents.append(incident)
            self._generate_alerts_for_incident(incident_id, is_primary=False)

    def _generate_alerts_for_incident(self, incident_id: str, is_primary: bool) -> None:
        """Generate alerts for an incident."""
        alerts = []

        if is_primary:
            alert_summaries = self._get_primary_alert_summaries()
            num_alerts = len(alert_summaries)
        else:
            alert_summaries = [
                ("Warning threshold exceeded", "warning"),
                ("Metric anomaly detected", "info"),
            ]
            num_alerts = self.rng.randint(1, 3)

        base_time = datetime.now() - timedelta(hours=2 if is_primary else 72)

        for i in range(min(num_alerts, len(alert_summaries))):
            summary, severity = alert_summaries[i] if i < len(alert_summaries) else ("Alert", "warning")
            ts = base_time + timedelta(minutes=i * 5)

            alerts.append({
                "id": f"A{self._random_id(length=7).upper()}",
                "alert_key": f"alert-{self.rng.randint(10000, 99999)}",
                "summary": summary,
                "severity": severity,
                "status": "resolved" if i < 2 else "triggered",
                "created_at": ts.isoformat() + "Z",
                "incident": {"id": incident_id},
                "body": {
                    "type": "alert_body",
                    "details": {
                        "source": "prometheus",
                        "metric": "error_rate",
                        "threshold": "0.05",
                        "current_value": str(self.rng.uniform(0.05, 0.15)),
                    },
                },
            })

        self.alerts[incident_id] = alerts

    def _get_primary_alert_summaries(self) -> list[tuple[str, str]]:
        """Get alert summaries based on pattern category."""
        category = (self.pattern.subcategory or self.pattern.category).lower()

        if "race" in category:
            return [
                ("Data integrity check failed", "critical"),
                ("Concurrent modification detected", "critical"),
                ("Lock contention spike", "warning"),
                ("Transaction rollback rate increased", "warning"),
                ("Inconsistent read detected", "critical"),
            ]
        elif "split" in category:
            return [
                ("Cluster quorum lost", "critical"),
                ("Node sync failed", "critical"),
                ("Replication lag exceeded threshold", "warning"),
                ("Split-brain condition detected", "critical"),
                ("Consensus failure", "critical"),
            ]
        elif "clock" in category:
            return [
                ("Clock drift detected", "warning"),
                ("Timestamp ordering violation", "critical"),
                ("NTP sync failed", "warning"),
                ("Event ordering anomaly", "critical"),
            ]
        else:
            return [
                ("Error rate exceeded threshold", "critical"),
                ("Service degradation detected", "warning"),
                ("Anomaly detected in metrics", "warning"),
            ]

    def _generate_log_entries(self, incident_id: str, is_primary: bool) -> None:
        """Generate incident log entries (timeline)."""
        entries = []
        base_time = datetime.now() - timedelta(hours=2 if is_primary else 72)

        if is_primary:
            timeline = [
                (0, "trigger", "Incident triggered", "prometheus"),
                (2, "notify", "Notified Sarah Chen", None),
                (5, "acknowledge", "Acknowledged by Sarah Chen", "Sarah Chen"),
                (10, "annotate", "Investigating error patterns in logs", "Sarah Chen"),
                (20, "annotate", "Found suspicious concurrent access pattern", "Sarah Chen"),
                (30, "escalate", "Escalated to level 2", None),
                (35, "notify", "Notified Tech Lead", None),
            ]
        else:
            timeline = [
                (0, "trigger", "Incident triggered", "monitoring"),
                (5, "acknowledge", "Acknowledged", "oncall"),
                (60, "resolve", "Resolved - false alarm", "oncall"),
            ]

        for minutes, entry_type, message, agent in timeline:
            ts = base_time + timedelta(minutes=minutes)
            entries.append({
                "id": f"LOG{self._random_id(length=10).upper()}",
                "type": f"incident_log_entry_type_{entry_type}",
                "created_at": ts.isoformat() + "Z",
                "incident": {"id": incident_id},
                "agent": {
                    "type": "user_reference" if agent and not agent.startswith("prom") else "service_reference",
                    "name": agent,
                } if agent else None,
                "channel": {"type": "email"},
                "summary": message,
            })

        self.log_entries[incident_id] = entries

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Handle PagerDuty API requests."""
        endpoint = endpoint.rstrip("/")

        # GET /incidents
        if method == "GET" and endpoint == "/incidents":
            return self._handle_list_incidents(params)

        # GET /incidents/{id}
        match = re.match(r"^/incidents/([^/]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_incident(match.group(1))

        # GET /incidents/{id}/alerts
        match = re.match(r"^/incidents/([^/]+)/alerts$", endpoint)
        if match and method == "GET":
            return self._handle_get_alerts(match.group(1))

        # GET /incidents/{id}/log_entries
        match = re.match(r"^/incidents/([^/]+)/log_entries$", endpoint)
        if match and method == "GET":
            return self._handle_get_log_entries(match.group(1))

        # PUT /incidents/{id}/resolve
        match = re.match(r"^/incidents/([^/]+)/resolve$", endpoint)
        if match and method == "PUT":
            return self._handle_resolve_incident(match.group(1))

        # PUT /incidents/{id}/acknowledge
        match = re.match(r"^/incidents/([^/]+)/acknowledge$", endpoint)
        if match and method == "PUT":
            return self._handle_acknowledge_incident(match.group(1))

        # GET /services
        if method == "GET" and endpoint == "/services":
            return Response(200, {"services": self.services})

        # GET /escalation_policies
        if method == "GET" and endpoint == "/escalation_policies":
            return Response(200, {"escalation_policies": self.escalation_policies})

        # GET /oncalls
        if method == "GET" and endpoint == "/oncalls":
            return Response(200, {"oncalls": self.oncalls})

        return Response(404, {"error": f"Endpoint not found: {method} {endpoint}"})

    def _handle_list_incidents(self, params: dict[str, Any]) -> Response:
        """List incidents."""
        incidents = self.incidents.copy()

        statuses = params.get("statuses", [])
        if statuses:
            if isinstance(statuses, str):
                statuses = [statuses]
            incidents = [i for i in incidents if i["status"] in statuses]

        return Response(200, {"incidents": incidents})

    def _handle_get_incident(self, incident_id: str) -> Response:
        """Get a specific incident."""
        for incident in self.incidents:
            if incident["id"] == incident_id:
                return Response(200, {"incident": incident})
        return Response(404, {"error": f"Incident not found: {incident_id}"})

    def _handle_get_alerts(self, incident_id: str) -> Response:
        """Get alerts for an incident."""
        if incident_id not in self.alerts:
            return Response(200, {"alerts": []})
        return Response(200, {"alerts": self.alerts[incident_id]})

    def _handle_get_log_entries(self, incident_id: str) -> Response:
        """Get log entries for an incident."""
        if incident_id not in self.log_entries:
            return Response(200, {"log_entries": []})
        return Response(200, {"log_entries": self.log_entries[incident_id]})

    def _handle_resolve_incident(self, incident_id: str) -> Response:
        """Resolve an incident."""
        for incident in self.incidents:
            if incident["id"] == incident_id:
                incident["status"] = "resolved"
                incident["resolved_at"] = datetime.now().isoformat() + "Z"
                return Response(200, {"incident": incident})
        return Response(404, {"error": f"Incident not found: {incident_id}"})

    def _handle_acknowledge_incident(self, incident_id: str) -> Response:
        """Acknowledge an incident."""
        for incident in self.incidents:
            if incident["id"] == incident_id:
                incident["status"] = "acknowledged"
                return Response(200, {"incident": incident})
        return Response(404, {"error": f"Incident not found: {incident_id}"})
