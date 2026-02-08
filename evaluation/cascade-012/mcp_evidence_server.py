#!/usr/bin/env python3
"""MCP server for CASCADE-012 with noise-mixed evidence at 50K+ scale.

Uses the noise generation engine to mix hand-crafted evidence signals
into 50,000+ realistic Slack messages and log entries per source.

Includes noise MCP tools (Jira, Confluence, kubectl, CloudWatch, Datadog,
CI/CD, StatusPage, On-Call, Terraform, Docker Registry) that return
realistic-looking but mostly unhelpful data to test signal-vs-noise filtering.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path so we can import sdlc_inject
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

from sdlc_inject.mcp_servers.evidence import load_evidence_servers_interactive

import random as _random_module
_rate_limit_rng = _random_module.Random(2024)
_request_counter = 0

def _maybe_rate_limit():
    """20% chance of returning a rate limit error."""
    global _request_counter
    _request_counter += 1
    if _rate_limit_rng.random() < 0.20:
        return {
            "error": "rate_limit_exceeded",
            "message": "API rate limit exceeded. Please retry after the specified interval.",
            "retry_after_seconds": 30,
            "request_id": f"req-{_rate_limit_rng.randint(10000, 99999)}",
            "daily_limit": 1000,
            "remaining": _rate_limit_rng.randint(0, 50),
            "reset_at": "2024-12-02T11:00:00Z",
        }
    return None

def _add_verbose_metadata(data: dict) -> dict:
    """Add realistic API metadata that bloats the response."""
    metadata = {
        "_request_id": f"req-{_rate_limit_rng.randint(10000, 99999)}",
        "_response_time_ms": _rate_limit_rng.randint(50, 3000),
        "_api_version": "v2.3.1-beta",
        "_cache_status": _rate_limit_rng.choice(["HIT", "MISS", "STALE", "BYPASS"]),
        "_server": f"api-{_rate_limit_rng.randint(1,8)}.internal",
        "_region": _rate_limit_rng.choice(["us-east-1", "us-west-2", "eu-west-1"]),
    }
    if _rate_limit_rng.random() < 0.3:
        metadata["_deprecation_warning"] = "This endpoint is deprecated and will be removed in API v3.0. Please migrate to the new endpoint format."
    if _rate_limit_rng.random() < 0.2:
        metadata["_data_freshness_warning"] = "Data may be up to 5 minutes stale due to replication lag."
    data["_metadata"] = metadata
    return data

EVIDENCE_FILE = Path(__file__).parent / "CASCADE-012-evidence-map.yaml"

# Load interactive servers: reactive Slack + time-progressing metrics + noise
SERVERS, TIMELINE = load_evidence_servers_interactive(str(EVIDENCE_FILE))

app = Server("cascade-012-evidence")

# ---------------------------------------------------------------------------
# Static noise data for distractor tools
# ---------------------------------------------------------------------------

_NOW = "2026-02-07T14:32:00Z"
_TODAY = "2026-02-07"

JIRA_TICKETS = [
    {"key": "INFRA-2847", "summary": "Performance: tune Kafka consumer latency", "status": "Done", "assignee": "kevin.park", "priority": "Medium", "type": "Task",
     "created": "2026-01-28T09:15:00Z", "updated": "2026-02-05T16:42:00Z", "resolved": "2026-02-05T16:42:00Z",
     "description": "Investigate and tune Kafka consumer configuration for lower end-to-end latency on checkout-events topic. See commit a3f7c2d.",
     "labels": ["kafka", "performance", "checkout"], "sprint": "Platform Sprint 14", "story_points": 3,
     "comments": [{"author": "kevin.park", "body": "Pushed config changes in a3f7c2d. Benchmarked locally, looks good.", "created": "2026-02-05T16:40:00Z"}]},
    {"key": "CHKOUT-1234", "summary": "Checkout timeout under load", "status": "Done", "assignee": "dan.rogers", "priority": "High", "type": "Bug",
     "created": "2026-01-10T11:20:00Z", "updated": "2026-01-15T14:30:00Z", "resolved": "2026-01-15T14:30:00Z",
     "description": "Checkout service returns 504 when order volume exceeds 200 req/s. Root cause was connection pool exhaustion in payment gateway client.",
     "labels": ["checkout", "timeout", "payment"], "sprint": "Checkout Sprint 22", "story_points": 5,
     "comments": [{"author": "dan.rogers", "body": "Fixed by increasing pool size to 50 and adding circuit breaker.", "created": "2026-01-15T14:28:00Z"}]},
    {"key": "CHKOUT-1456", "summary": "Investigate shipping quote latency", "status": "Done", "assignee": "priya.sharma", "priority": "Medium", "type": "Task",
     "created": "2025-12-05T08:45:00Z", "updated": "2025-12-18T17:00:00Z", "resolved": "2025-12-18T17:00:00Z",
     "description": "Shipping quote API p99 latency is 1.2s, should be under 500ms. Investigate caching strategy.",
     "labels": ["shipping", "latency", "cache"], "sprint": "Checkout Sprint 20", "story_points": 3,
     "comments": [{"author": "priya.sharma", "body": "Added Redis cache for carrier rate lookups. p99 now 340ms.", "created": "2025-12-18T16:55:00Z"}]},
    {"key": "PLAT-892", "summary": "Reduce Kafka log retention for cost savings", "status": "Done", "assignee": "kevin.park", "priority": "Low", "type": "Task",
     "created": "2026-01-20T10:00:00Z", "updated": "2026-01-22T11:30:00Z", "resolved": "2026-01-22T11:30:00Z",
     "description": "Kafka broker disk usage is growing. Reduce log.retention.hours from 168 to 4 on non-critical topics to save ~40% disk.",
     "labels": ["kafka", "cost", "infrastructure"], "sprint": "Platform Sprint 13", "story_points": 1,
     "comments": [{"author": "kevin.park", "body": "Applied via Terraform. Monitoring disk usage.", "created": "2026-01-22T11:28:00Z"}]},
    {"key": "PLAT-901", "summary": "Upgrade Redis to 7.2", "status": "In Progress", "assignee": "alicia.chen", "priority": "Medium", "type": "Task",
     "created": "2026-02-01T09:00:00Z", "updated": "2026-02-06T15:00:00Z", "resolved": None,
     "description": "Upgrade Redis cluster from 7.0.11 to 7.2.4 for ACL improvements and memory optimizations.",
     "labels": ["redis", "upgrade", "infrastructure"], "sprint": "Platform Sprint 14", "story_points": 5,
     "comments": [{"author": "alicia.chen", "body": "Staging upgrade complete. Running soak test before prod.", "created": "2026-02-06T14:55:00Z"}]},
    {"key": "CHKOUT-1501", "summary": "Add Apple Pay support", "status": "In Review", "assignee": "dan.rogers", "priority": "High", "type": "Story",
     "created": "2026-01-25T10:30:00Z", "updated": "2026-02-06T11:00:00Z", "resolved": None,
     "description": "Integrate Apple Pay as a payment method in checkout flow. Requires new PSP adapter.",
     "labels": ["checkout", "payments", "feature"], "sprint": "Checkout Sprint 23", "story_points": 8,
     "comments": [{"author": "dan.rogers", "body": "PR #487 ready for review. All unit tests passing.", "created": "2026-02-06T10:58:00Z"}]},
    {"key": "PLAT-910", "summary": "Migrate service mesh to Istio 1.21", "status": "To Do", "assignee": "alicia.chen", "priority": "Medium", "type": "Task",
     "created": "2026-02-03T14:00:00Z", "updated": "2026-02-03T14:00:00Z", "resolved": None,
     "description": "Current Istio 1.19 is approaching EOL. Plan migration to 1.21 with canary rollout.",
     "labels": ["istio", "service-mesh", "upgrade"], "sprint": "Platform Sprint 15", "story_points": 13,
     "comments": []},
    {"key": "CHKOUT-1510", "summary": "Flaky test: test_concurrent_cart_updates", "status": "Open", "assignee": "priya.sharma", "priority": "Low", "type": "Bug",
     "created": "2026-02-04T16:20:00Z", "updated": "2026-02-04T16:20:00Z", "resolved": None,
     "description": "test_concurrent_cart_updates fails ~5% of CI runs due to race condition in mock setup.",
     "labels": ["tests", "flaky", "cart"], "sprint": "Checkout Sprint 23", "story_points": 2,
     "comments": []},
    {"key": "PLAT-915", "summary": "Document disaster recovery procedures", "status": "In Progress", "assignee": "frank.martinez", "priority": "Medium", "type": "Task",
     "created": "2026-02-05T09:30:00Z", "updated": "2026-02-06T10:00:00Z", "resolved": None,
     "description": "Create comprehensive DR runbook covering Kafka, Redis, PostgreSQL, and S3 backup restoration.",
     "labels": ["documentation", "DR", "runbook"], "sprint": "Platform Sprint 14", "story_points": 5,
     "comments": [{"author": "frank.martinez", "body": "Draft for Kafka and Redis sections done. Starting PostgreSQL.", "created": "2026-02-06T09:58:00Z"}]},
    {"key": "INFRA-2860", "summary": "Set up Prometheus remote write to Thanos", "status": "To Do", "assignee": "alicia.chen", "priority": "Low", "type": "Task",
     "created": "2026-02-06T08:00:00Z", "updated": "2026-02-06T08:00:00Z", "resolved": None,
     "description": "Enable long-term metrics storage by configuring Prometheus remote write to Thanos sidecar.",
     "labels": ["prometheus", "thanos", "observability"], "sprint": "Platform Sprint 15", "story_points": 5,
     "comments": []},
    {"key": "CHKOUT-1520", "summary": "Optimize cart page load time", "status": "In Progress", "assignee": "dan.rogers", "priority": "Medium", "type": "Story",
     "created": "2026-02-03T11:00:00Z", "updated": "2026-02-07T09:00:00Z", "resolved": None,
     "description": "Cart page LCP is 2.4s on mobile. Target is under 1.5s. Investigate lazy loading and API response optimization.",
     "labels": ["performance", "frontend", "cart"], "sprint": "Checkout Sprint 23", "story_points": 5,
     "comments": [{"author": "dan.rogers", "body": "Identified 3 blocking API calls that can be parallelized.", "created": "2026-02-07T08:55:00Z"}]},
    {"key": "PLAT-920", "summary": "Evaluate Clickhouse for analytics workloads", "status": "To Do", "assignee": "kevin.park", "priority": "Low", "type": "Spike",
     "created": "2026-02-06T14:00:00Z", "updated": "2026-02-06T14:00:00Z", "resolved": None,
     "description": "Investigate Clickhouse as a replacement for our analytics PostgreSQL read replicas. Run benchmarks.",
     "labels": ["analytics", "database", "spike"], "sprint": "Platform Sprint 15", "story_points": 3,
     "comments": []},
    {"key": "SEC-340", "summary": "Rotate TLS certificates for internal services", "status": "Done", "assignee": "frank.martinez", "priority": "High", "type": "Task",
     "created": "2026-01-30T10:00:00Z", "updated": "2026-02-03T12:00:00Z", "resolved": "2026-02-03T12:00:00Z",
     "description": "Internal mTLS certificates expire Feb 15. Rotate all service certificates.",
     "labels": ["security", "tls", "certificates"], "sprint": "Platform Sprint 14", "story_points": 3,
     "comments": [{"author": "frank.martinez", "body": "All certs rotated. Verified with cert-checker tool.", "created": "2026-02-03T11:58:00Z"}]},
    {"key": "CHKOUT-1490", "summary": "Implement order confirmation email templates", "status": "Done", "assignee": "priya.sharma", "priority": "Medium", "type": "Story",
     "created": "2026-01-18T09:00:00Z", "updated": "2026-01-28T16:00:00Z", "resolved": "2026-01-28T16:00:00Z",
     "description": "Design and implement new responsive email templates for order confirmation.",
     "labels": ["email", "checkout", "frontend"], "sprint": "Checkout Sprint 22", "story_points": 5,
     "comments": []},
    {"key": "PLAT-888", "summary": "Add structured logging to payment service", "status": "Done", "assignee": "dan.rogers", "priority": "Medium", "type": "Task",
     "created": "2026-01-12T13:00:00Z", "updated": "2026-01-20T10:00:00Z", "resolved": "2026-01-20T10:00:00Z",
     "description": "Migrate payment service from text logs to structured JSON logging for better observability.",
     "labels": ["logging", "observability", "payment"], "sprint": "Platform Sprint 13", "story_points": 3,
     "comments": []},
    {"key": "INFRA-2830", "summary": "Resize EBS volumes for Kafka brokers", "status": "Done", "assignee": "kevin.park", "priority": "Medium", "type": "Task",
     "created": "2026-01-08T11:00:00Z", "updated": "2026-01-10T14:00:00Z", "resolved": "2026-01-10T14:00:00Z",
     "description": "Kafka broker EBS volumes at 78% capacity. Resize from 500GB to 1TB gp3.",
     "labels": ["kafka", "aws", "storage"], "sprint": "Platform Sprint 13", "story_points": 2,
     "comments": []},
    {"key": "CHKOUT-1525", "summary": "Add retry logic to inventory reservation API", "status": "Open", "assignee": None, "priority": "Medium", "type": "Task",
     "created": "2026-02-07T10:00:00Z", "updated": "2026-02-07T10:00:00Z", "resolved": None,
     "description": "Inventory reservation calls occasionally fail with 503. Add exponential backoff retry.",
     "labels": ["inventory", "resilience", "checkout"], "sprint": "Checkout Sprint 24", "story_points": 3,
     "comments": []},
]

JIRA_SPRINTS = [
    {"id": 140, "name": "Platform Sprint 14", "state": "active", "start": "2026-01-27", "end": "2026-02-09",
     "goal": "Redis upgrade, DR docs, Kafka tuning", "issues_total": 12, "issues_done": 7},
    {"id": 141, "name": "Platform Sprint 15", "state": "future", "start": "2026-02-10", "end": "2026-02-23",
     "goal": "Istio migration, Thanos setup, Clickhouse eval", "issues_total": 8, "issues_done": 0},
    {"id": 230, "name": "Checkout Sprint 23", "state": "active", "start": "2026-01-27", "end": "2026-02-09",
     "goal": "Apple Pay, cart perf, flaky test fixes", "issues_total": 10, "issues_done": 5},
    {"id": 220, "name": "Checkout Sprint 22", "state": "closed", "start": "2026-01-13", "end": "2026-01-26",
     "goal": "Connection pool fixes, email templates", "issues_total": 11, "issues_done": 11},
    {"id": 130, "name": "Platform Sprint 13", "state": "closed", "start": "2026-01-13", "end": "2026-01-26",
     "goal": "Kafka retention, structured logging, EBS resize", "issues_total": 9, "issues_done": 9},
]

WIKI_PAGES = {
    "WIKI-1042": {
        "id": "WIKI-1042", "title": "Kafka Operations Guide", "space": "Platform",
        "last_updated": "2025-08-14T10:30:00Z", "updated_by": "frank.martinez",
        "body": """# Kafka Operations Guide

## Cluster Overview
- **Brokers**: 3-node cluster (kafka-0, kafka-1, kafka-2)
- **Version**: 3.6.1
- **Storage**: gp3 EBS, 1TB per broker

## Consumer Configuration Best Practices
- `session.timeout.ms`: 30000 (30s) -- allows for GC pauses
- `heartbeat.interval.ms`: 10000 (10s)
- `max.poll.interval.ms`: 300000 (5min) -- for batch consumers
- `auto.offset.reset`: earliest

## Topic Naming Convention
- `{domain}.{entity}.{version}` e.g. `checkout.orders.v2`

## Monitoring
- Consumer lag: check `kafka_consumer_lag` in Prometheus
- Under-replicated partitions: should always be 0
- ISR shrink rate: alert if > 0 for 5 minutes

## Runbook: High Consumer Lag
1. Check consumer group status: `kafka-consumer-groups.sh --describe`
2. Check for rebalancing: look for "Preparing to rebalance" in broker logs
3. If rebalancing is stuck, check `session.timeout.ms` and `max.poll.interval.ms`
4. Consider increasing partition count if throughput is the bottleneck

## Runbook: Broker Down
1. Check pod status in Kubernetes
2. Check broker logs for errors
3. If OOM, increase memory limits in StatefulSet
4. Restart pod if needed: `kubectl delete pod kafka-N`

_Last reviewed: 2025-08-14 by Frank Martinez_
""",
    },
    "WIKI-1105": {
        "id": "WIKI-1105", "title": "Incident Response Runbook", "space": "SRE",
        "last_updated": "2025-06-20T14:00:00Z", "updated_by": "alicia.chen",
        "body": """# Incident Response Runbook

## Severity Levels
- **SEV1**: Complete service outage, revenue impact > $10K/hr
- **SEV2**: Partial degradation, user-facing impact
- **SEV3**: Internal tooling issues, no direct user impact

## First Responder Checklist
1. Acknowledge PagerDuty alert
2. Join #incidents Slack channel
3. Check Grafana dashboards: https://grafana.internal/d/svc-overview (NOTE: link may be outdated)
4. Check Prometheus for key metrics
5. Check recent deploys in CI/CD
6. Escalate if not resolved in 15 minutes

## Communication Template
- Post in #incidents: "Investigating [DESCRIPTION]. Impact: [SCOPE]. ETA: [TIME]"
- Update every 15 minutes
- Post resolution summary when done

## Common Issues
- **High error rate**: Check Sentry for new exceptions
- **High latency**: Check Prometheus for resource saturation
- **Pod crashes**: Check kubectl events and logs

## Escalation Contacts
- Platform: Alicia Chen (@alicia)
- Backend: Dan Rogers (@dan)
- Infrastructure: Kevin Park (@kevin)
- SRE: Frank Martinez (@frank)

_Last reviewed: 2025-06-20 by Alicia Chen_
""",
    },
    "WIKI-1200": {
        "id": "WIKI-1200", "title": "Checkout Service Architecture", "space": "Engineering",
        "last_updated": "2026-01-05T11:00:00Z", "updated_by": "dan.rogers",
        "body": """# Checkout Service Architecture

## Overview
The checkout service handles the complete order flow from cart to payment confirmation.

## Components
- **checkout-service**: Go service, handles order orchestration
- **payment-service**: Java service, PSP integration (Stripe, PayPal)
- **inventory-service**: Go service, stock reservation
- **cart-service**: Python service, shopping cart management

## Data Flow
1. User clicks "Place Order"
2. checkout-service validates cart contents via cart-service
3. checkout-service reserves inventory via inventory-service
4. checkout-service initiates payment via payment-service
5. On success, checkout-service publishes `order.completed` event to Kafka
6. Confirmation page rendered

## Kafka Topics
- `checkout.orders.v2` - Order events (created, completed, cancelled)
- `checkout.payments.v1` - Payment status events
- `inventory.reservations.v1` - Reservation events

## Database
- PostgreSQL 15 (RDS) - orders, order_items, payments
- Redis 7.0 - cart data, session cache

## Scaling
- checkout-service: HPA, min 3 / max 10 replicas
- payment-service: HPA, min 2 / max 8 replicas
- Database: Multi-AZ RDS with read replicas

## Health Checks
- `/healthz` - basic liveness
- `/readyz` - readiness (includes DB connectivity)

_Last updated: 2026-01-05 by Dan Rogers_
""",
    },
    "WIKI-1089": {
        "id": "WIKI-1089", "title": "On-Call Handbook", "space": "SRE",
        "last_updated": "2025-11-10T09:00:00Z", "updated_by": "frank.martinez",
        "body": """# On-Call Handbook

## Rotation Schedule
- Platform team: weekly rotation (Mon 9am to Mon 9am)
- Backend team: weekly rotation (Mon 9am to Mon 9am)
- SRE: always secondary on-call

## Expectations
- Acknowledge pages within 5 minutes
- Begin investigation within 10 minutes
- Escalate if not resolved within 30 minutes
- Write post-incident review within 48 hours

## Tools Access
- PagerDuty: all on-call engineers have admin
- Grafana: SSO, dashboards in "On-Call" folder
- kubectl: via bastion host or VPN
- AWS Console: read-only for on-call role

## Handoff Procedure
1. Review open incidents and ongoing issues
2. Check #oncall-handoff channel for notes
3. Verify PagerDuty schedule shows you as primary
4. Test notification path (phone + Slack)

_Last reviewed: 2025-11-10 by Frank Martinez_
""",
    },
}

KUBECTL_PODS = {
    "default": [
        {"name": "checkout-service-7b8f9c4d5-x2k4m", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "ip-10-0-1-42", "cpu": "245m", "memory": "412Mi"},
        {"name": "checkout-service-7b8f9c4d5-j9n2p", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "ip-10-0-2-18", "cpu": "238m", "memory": "398Mi"},
        {"name": "checkout-service-7b8f9c4d5-a1b3c", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "ip-10-0-1-55", "cpu": "251m", "memory": "425Mi"},
        {"name": "payment-service-5c6d7e8f9-m4k2j", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "ip-10-0-2-18", "cpu": "180m", "memory": "310Mi"},
        {"name": "payment-service-5c6d7e8f9-p7n3q", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "ip-10-0-1-42", "cpu": "175m", "memory": "305Mi"},
        {"name": "cart-service-3a4b5c6d7-r8s2t", "ready": "1/1", "status": "Running", "restarts": 1, "age": "2d", "node": "ip-10-0-1-55", "cpu": "120m", "memory": "256Mi"},
        {"name": "cart-service-3a4b5c6d7-u5v1w", "ready": "1/1", "status": "Running", "restarts": 0, "age": "2d", "node": "ip-10-0-2-33", "cpu": "115m", "memory": "248Mi"},
        {"name": "inventory-service-9e8f7g6h5-y3z4a", "ready": "1/1", "status": "Running", "restarts": 0, "age": "4d", "node": "ip-10-0-2-33", "cpu": "95m", "memory": "198Mi"},
        {"name": "inventory-service-9e8f7g6h5-b6c7d", "ready": "1/1", "status": "Running", "restarts": 0, "age": "4d", "node": "ip-10-0-1-42", "cpu": "92m", "memory": "195Mi"},
        {"name": "frontend-8h9i0j1k2-e3f4g", "ready": "1/1", "status": "Running", "restarts": 0, "age": "1d", "node": "ip-10-0-1-55", "cpu": "55m", "memory": "128Mi"},
        {"name": "frontend-8h9i0j1k2-h5i6j", "ready": "1/1", "status": "Running", "restarts": 0, "age": "1d", "node": "ip-10-0-2-18", "cpu": "52m", "memory": "125Mi"},
    ],
    "kafka": [
        {"name": "kafka-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "14d", "node": "ip-10-0-1-42", "cpu": "890m", "memory": "3.2Gi"},
        {"name": "kafka-1", "ready": "1/1", "status": "Running", "restarts": 0, "age": "14d", "node": "ip-10-0-2-18", "cpu": "875m", "memory": "3.1Gi"},
        {"name": "kafka-2", "ready": "1/1", "status": "Running", "restarts": 0, "age": "14d", "node": "ip-10-0-2-33", "cpu": "860m", "memory": "3.0Gi"},
        {"name": "zookeeper-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "14d", "node": "ip-10-0-1-55", "cpu": "120m", "memory": "512Mi"},
    ],
    "monitoring": [
        {"name": "prometheus-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "ip-10-0-1-42", "cpu": "450m", "memory": "2.1Gi"},
        {"name": "grafana-6f7g8h9i0-k1l2m", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "ip-10-0-2-18", "cpu": "85m", "memory": "256Mi"},
        {"name": "alertmanager-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "ip-10-0-2-33", "cpu": "30m", "memory": "64Mi"},
        {"name": "otel-collector-4d5e6f7g8-n3o4p", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "ip-10-0-1-55", "cpu": "320m", "memory": "512Mi"},
    ],
}

KUBECTL_POD_DETAILS = {
    "checkout-service-7b8f9c4d5-x2k4m": {
        "name": "checkout-service-7b8f9c4d5-x2k4m", "namespace": "default",
        "labels": {"app": "checkout-service", "version": "v2.14.3", "pod-template-hash": "7b8f9c4d5"},
        "status": {"phase": "Running", "startTime": "2026-02-04T11:20:00Z",
                   "conditions": [{"type": "Ready", "status": "True"}, {"type": "ContainersReady", "status": "True"}]},
        "containers": [{"name": "checkout", "image": "registry.internal/checkout-service:v2.14.3",
                        "state": "Running", "started": "2026-02-04T11:20:15Z", "ready": True,
                        "resources": {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "480Mi"}},
                        "usage": {"cpu": "245m", "memory": "425Mi"},
                        "liveness_probe": "/healthz", "readiness_probe": "/readyz"}],
        "events": [{"type": "Normal", "reason": "Scheduled", "message": "Successfully assigned default/checkout-service-7b8f9c4d5-x2k4m to ip-10-0-1-42", "age": "3d"},
                   {"type": "Normal", "reason": "Pulled", "message": "Container image already present on machine", "age": "3d"},
                   {"type": "Normal", "reason": "Started", "message": "Started container checkout", "age": "3d"}],
        "note": "Memory usage at 89% of limit (425Mi / 480Mi)",
    },
    "cart-service-3a4b5c6d7-r8s2t": {
        "name": "cart-service-3a4b5c6d7-r8s2t", "namespace": "default",
        "labels": {"app": "cart-service", "version": "v1.8.2", "pod-template-hash": "3a4b5c6d7"},
        "status": {"phase": "Running", "startTime": "2026-02-05T09:00:00Z",
                   "conditions": [{"type": "Ready", "status": "True"}, {"type": "ContainersReady", "status": "True"}]},
        "containers": [{"name": "cart", "image": "registry.internal/cart-service:v1.8.2",
                        "state": "Running", "started": "2026-02-07T14:17:00Z", "ready": True,
                        "restartCount": 1, "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137, "finishedAt": "2026-02-07T14:16:45Z"}},
                        "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "300m", "memory": "300Mi"}},
                        "usage": {"cpu": "120m", "memory": "256Mi"}}],
        "events": [{"type": "Warning", "reason": "OOMKilled", "message": "Container cart OOMKilled", "age": "15m"},
                   {"type": "Normal", "reason": "Pulled", "message": "Container image already present on machine", "age": "15m"},
                   {"type": "Normal", "reason": "Started", "message": "Started container cart", "age": "15m"}],
    },
    "kafka-0": {
        "name": "kafka-0", "namespace": "kafka",
        "labels": {"app": "kafka", "statefulset.kubernetes.io/pod-name": "kafka-0"},
        "status": {"phase": "Running", "startTime": "2026-01-24T06:00:00Z",
                   "conditions": [{"type": "Ready", "status": "True"}]},
        "containers": [{"name": "kafka", "image": "confluentinc/cp-kafka:7.5.3",
                        "state": "Running", "started": "2026-01-24T06:00:30Z", "ready": True,
                        "resources": {"requests": {"cpu": "500m", "memory": "2Gi"}, "limits": {"cpu": "2000m", "memory": "4Gi"}},
                        "usage": {"cpu": "890m", "memory": "3.2Gi"}}],
        "events": [],
    },
}

KUBECTL_EVENTS = {
    "default": [
        {"type": "Normal", "reason": "Scheduled", "object": "pod/checkout-service-7b8f9c4d5-x2k4m", "message": "Successfully assigned default/checkout-service-7b8f9c4d5-x2k4m to ip-10-0-1-42", "age": "3d"},
        {"type": "Normal", "reason": "Pulled", "object": "pod/checkout-service-7b8f9c4d5-x2k4m", "message": "Container image already present on machine", "age": "3d"},
        {"type": "Normal", "reason": "Started", "object": "pod/checkout-service-7b8f9c4d5-x2k4m", "message": "Started container checkout", "age": "3d"},
        {"type": "Normal", "reason": "Scheduled", "object": "pod/cart-service-3a4b5c6d7-r8s2t", "message": "Successfully assigned default/cart-service-3a4b5c6d7-r8s2t to ip-10-0-1-55", "age": "2d"},
        {"type": "Warning", "reason": "OOMKilled", "object": "pod/cart-service-3a4b5c6d7-r8s2t", "message": "Container cart OOMKilled", "age": "15m"},
        {"type": "Normal", "reason": "Pulled", "object": "pod/cart-service-3a4b5c6d7-r8s2t", "message": "Container image already present on machine", "age": "15m"},
        {"type": "Normal", "reason": "Started", "object": "pod/cart-service-3a4b5c6d7-r8s2t", "message": "Started container cart", "age": "15m"},
        {"type": "Normal", "reason": "ScalingReplicaSet", "object": "deployment/frontend", "message": "Scaled up replica set frontend-8h9i0j1k2 to 2", "age": "1d"},
        {"type": "Normal", "reason": "SuccessfulCreate", "object": "replicaset/frontend-8h9i0j1k2", "message": "Created pod: frontend-8h9i0j1k2-e3f4g", "age": "1d"},
    ],
    "kafka": [
        {"type": "Normal", "reason": "Scheduled", "object": "pod/kafka-0", "message": "Successfully assigned kafka/kafka-0 to ip-10-0-1-42", "age": "14d"},
        {"type": "Normal", "reason": "Started", "object": "pod/kafka-0", "message": "Started container kafka", "age": "14d"},
    ],
    "monitoring": [
        {"type": "Normal", "reason": "Scheduled", "object": "pod/prometheus-0", "message": "Successfully assigned monitoring/prometheus-0 to ip-10-0-1-42", "age": "7d"},
        {"type": "Normal", "reason": "Started", "object": "pod/prometheus-0", "message": "Started container prometheus", "age": "7d"},
    ],
}

# kubectl logs -- kafka-0 intentionally shows the rebalance storm (helpful signal)
KUBECTL_LOGS = {
    "kafka-0": {
        "kafka": [
            "[2026-02-07 14:25:01,234] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4012 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:01,235] INFO [GroupCoordinator 0]: Group checkout-consumer-group with generation 4013 is now empty (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:03,891] INFO [GroupCoordinator 0]: Dynamic member with unknown member id joins group checkout-consumer-group in Stable state. Created a new member id checkout-service-7b8f9c4d5-x2k4m-uuid1 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:03,892] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4013 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:07,445] INFO [GroupCoordinator 0]: Stabilized group checkout-consumer-group generation 4014 with 3 members (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:07,501] INFO [GroupCoordinator 0]: Assignment received from leader for group checkout-consumer-group for generation 4014 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:13,678] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4014 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:13,679] INFO [GroupCoordinator 0]: Group checkout-consumer-group with generation 4015 is now empty (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:16,123] INFO [GroupCoordinator 0]: Dynamic member with unknown member id joins group checkout-consumer-group in Stable state. Created a new member id checkout-service-7b8f9c4d5-j9n2p-uuid2 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:16,124] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4015 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:19,890] INFO [GroupCoordinator 0]: Stabilized group checkout-consumer-group generation 4016 with 3 members (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:21,002] INFO [GroupCoordinator 0]: Member checkout-service-7b8f9c4d5-a1b3c-uuid3 in group checkout-consumer-group has failed, removing it from the group (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:21,003] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4016 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:27,567] INFO [GroupCoordinator 0]: Stabilized group checkout-consumer-group generation 4017 with 2 members (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:28,100] INFO [GroupCoordinator 0]: Dynamic member with unknown member id joins group checkout-consumer-group. Created a new member id checkout-service-7b8f9c4d5-a1b3c-uuid4 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:28,101] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4017 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:34,789] INFO [GroupCoordinator 0]: Stabilized group checkout-consumer-group generation 4018 with 3 members (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:34,800] INFO [GroupCoordinator 0]: Assignment received from leader for group checkout-consumer-group for generation 4018 (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:41,234] INFO [GroupCoordinator 0]: Member checkout-service-7b8f9c4d5-x2k4m-uuid1 in group checkout-consumer-group has failed, removing it from the group (kafka.coordinator.group.GroupCoordinator)",
            "[2026-02-07 14:25:41,235] INFO [GroupCoordinator 0]: Preparing to rebalance group checkout-consumer-group in state PreparingRebalance with old generation 4018 (kafka.coordinator.group.GroupCoordinator)",
        ],
    },
    "checkout-service-7b8f9c4d5-x2k4m": {
        "checkout": [
            "2026-02-07T14:25:02.100Z ERROR [kafka-consumer] Failed to process message: context deadline exceeded (timeout=5s)",
            "2026-02-07T14:25:02.101Z WARN  [kafka-consumer] Consumer group rebalancing, pausing processing",
            "2026-02-07T14:25:07.600Z INFO  [kafka-consumer] Partitions assigned: [checkout.orders.v2-0, checkout.orders.v2-1]",
            "2026-02-07T14:25:08.200Z INFO  [kafka-consumer] Resuming message processing",
            "2026-02-07T14:25:13.500Z ERROR [kafka-consumer] Failed to commit offsets: rebalance in progress",
            "2026-02-07T14:25:13.501Z WARN  [kafka-consumer] Consumer group rebalancing, pausing processing",
            "2026-02-07T14:25:19.900Z INFO  [kafka-consumer] Partitions assigned: [checkout.orders.v2-0]",
            "2026-02-07T14:25:25.300Z ERROR [http-handler] POST /api/v1/orders - 504 Gateway Timeout (12.1s)",
            "2026-02-07T14:25:25.301Z ERROR [http-handler] Order creation failed: kafka producer: request timeout",
            "2026-02-07T14:25:28.200Z WARN  [kafka-consumer] Consumer group rebalancing, pausing processing",
            "2026-02-07T14:25:34.850Z INFO  [kafka-consumer] Partitions assigned: [checkout.orders.v2-0, checkout.orders.v2-2]",
            "2026-02-07T14:25:41.100Z ERROR [kafka-consumer] Failed to commit offsets: rebalance in progress",
        ],
    },
    "payment-service-5c6d7e8f9-m4k2j": {
        "payment": [
            "2026-02-07T14:25:00.000Z INFO  [main] Payment service v3.2.1 healthy",
            "2026-02-07T14:25:10.000Z INFO  [stripe] Processing payment pay_abc123 amount=49.99 currency=USD",
            "2026-02-07T14:25:10.450Z INFO  [stripe] Payment pay_abc123 succeeded",
            "2026-02-07T14:25:20.000Z INFO  [stripe] Processing payment pay_def456 amount=129.50 currency=USD",
            "2026-02-07T14:25:20.380Z INFO  [stripe] Payment pay_def456 succeeded",
            "2026-02-07T14:25:30.000Z INFO  [health] Health check OK: db=connected stripe=connected",
        ],
    },
    "cart-service-3a4b5c6d7-r8s2t": {
        "cart": [
            "2026-02-07T14:17:00.000Z INFO  [main] Cart service v1.8.2 starting",
            "2026-02-07T14:17:01.200Z INFO  [redis] Connected to Redis cluster",
            "2026-02-07T14:17:01.500Z INFO  [main] Cart service ready, listening on :8080",
            "2026-02-07T14:25:00.000Z INFO  [handler] GET /api/v1/cart/user-123 - 200 (12ms)",
            "2026-02-07T14:25:05.000Z INFO  [handler] POST /api/v1/cart/user-456/items - 200 (8ms)",
            "2026-02-07T14:25:15.000Z INFO  [handler] GET /api/v1/cart/user-789 - 200 (10ms)",
        ],
    },
    "prometheus-0": {
        "prometheus": [
            "ts=2026-02-07T14:25:00.000Z caller=main.go:1234 level=info msg=\"TSDB compaction complete\" duration=2.3s",
            "ts=2026-02-07T14:25:10.000Z caller=scrape.go:567 level=info msg=\"Scrape targets healthy\" active=42 failed=0",
            "ts=2026-02-07T14:25:30.000Z caller=rules.go:890 level=info msg=\"Rule evaluation complete\" groups=12 duration=0.4s",
        ],
    },
}

CLOUDWATCH_METRICS = {
    "AWS/ECS": {
        "CPUUtilization": {
            "label": "CPUUtilization",
            "datapoints": [
                {"timestamp": "2026-02-07T14:00:00Z", "average": 42.3, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:05:00Z", "average": 44.1, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:10:00Z", "average": 43.8, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:15:00Z", "average": 48.2, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:20:00Z", "average": 51.7, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:25:00Z", "average": 55.3, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:30:00Z", "average": 53.9, "unit": "Percent"},
            ],
        },
        "MemoryUtilization": {
            "label": "MemoryUtilization",
            "datapoints": [
                {"timestamp": "2026-02-07T14:00:00Z", "average": 67.2, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:05:00Z", "average": 67.5, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:10:00Z", "average": 68.1, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:15:00Z", "average": 69.8, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:20:00Z", "average": 72.4, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:25:00Z", "average": 74.1, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:30:00Z", "average": 73.8, "unit": "Percent"},
            ],
        },
    },
    "Custom/Checkout": {
        "SuccessRate": {
            "label": "CheckoutSuccessRate",
            "datapoints": [
                {"timestamp": "2026-02-07T14:00:00Z", "average": 99.1, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:05:00Z", "average": 98.7, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:10:00Z", "average": 95.2, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:15:00Z", "average": 78.4, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:20:00Z", "average": 52.1, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:25:00Z", "average": 45.3, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:30:00Z", "average": 44.8, "unit": "Percent"},
            ],
            "note": "CloudWatch aggregates over 5-minute windows. Prometheus uses 1-minute windows which may show different values.",
        },
        "OrdersPerMinute": {
            "label": "OrdersPerMinute",
            "datapoints": [
                {"timestamp": "2026-02-07T14:00:00Z", "average": 145.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:05:00Z", "average": 142.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:10:00Z", "average": 138.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:15:00Z", "average": 98.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:20:00Z", "average": 67.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:25:00Z", "average": 55.0, "unit": "Count"},
                {"timestamp": "2026-02-07T14:30:00Z", "average": 52.0, "unit": "Count"},
            ],
        },
    },
}

CLOUDWATCH_ALARMS = [
    {"name": "checkout-error-rate-high", "state": "OK", "metric": "Custom/Checkout/ErrorRate", "threshold": "> 20%", "period": "10 minutes",
     "description": "Checkout error rate exceeds 20% for 10 minutes", "last_updated": "2026-02-07T14:00:00Z",
     "note": "Alarm uses 10-minute evaluation period. Current incident started ~8 minutes ago."},
    {"name": "checkout-latency-p99", "state": "OK", "metric": "Custom/Checkout/Latency-p99", "threshold": "> 5000ms", "period": "15 minutes",
     "description": "Checkout p99 latency exceeds 5s for 15 minutes", "last_updated": "2026-02-07T14:00:00Z"},
    {"name": "kafka-broker-disk-usage", "state": "OK", "metric": "Custom/Kafka/DiskUsage", "threshold": "> 85%", "period": "5 minutes",
     "description": "Kafka broker disk usage exceeds 85%", "last_updated": "2026-02-07T14:25:00Z"},
    {"name": "rds-cpu-high", "state": "OK", "metric": "AWS/RDS/CPUUtilization", "threshold": "> 80%", "period": "5 minutes",
     "description": "RDS CPU utilization exceeds 80%", "last_updated": "2026-02-07T14:25:00Z"},
    {"name": "redis-memory-high", "state": "OK", "metric": "Custom/Redis/MemoryUsage", "threshold": "> 80%", "period": "5 minutes",
     "description": "Redis memory usage exceeds 80%", "last_updated": "2026-02-07T14:25:00Z"},
    {"name": "elb-5xx-count", "state": "OK", "metric": "AWS/ELB/HTTPCode_ELB_5XX_Count", "threshold": "> 100", "period": "5 minutes",
     "description": "ELB 5xx error count exceeds 100 in 5 minutes", "last_updated": "2026-02-07T14:25:00Z"},
]

DATADOG_TRACES = {
    "checkout-service": {
        "traces": [
            {"trace_id": "abc123def456", "service": "checkout-service", "resource": "POST /api/v1/orders",
             "status": "error", "duration_ms": 12134, "start": "2026-02-07T14:25:25.000Z",
             "spans_collected": 3, "spans_expected": 7, "error_message": "kafka producer: request timeout",
             "spans": [
                 {"span_id": "s1", "service": "checkout-service", "operation": "http.request", "duration_ms": 12134, "status": "error"},
                 {"span_id": "s2", "service": "checkout-service", "operation": "kafka.produce", "duration_ms": 10023, "status": "error", "error": "request timeout"},
                 {"span_id": "s3", "service": "checkout-service", "operation": "db.query", "duration_ms": 45, "status": "ok"},
             ],
             "warning": "Incomplete trace: 4 of 7 expected spans missing. OTel collector may be dropping spans under load."},
            {"trace_id": "ghi789jkl012", "service": "checkout-service", "resource": "POST /api/v1/orders",
             "status": "error", "duration_ms": 15201, "start": "2026-02-07T14:26:01.000Z",
             "spans_collected": 2, "spans_expected": 7, "error_message": "context deadline exceeded",
             "spans": [
                 {"span_id": "s4", "service": "checkout-service", "operation": "http.request", "duration_ms": 15201, "status": "error"},
                 {"span_id": "s5", "service": "checkout-service", "operation": "db.query", "duration_ms": 38, "status": "ok"},
             ],
             "warning": "Incomplete trace: 5 of 7 expected spans missing."},
            {"trace_id": "mno345pqr678", "service": "checkout-service", "resource": "GET /api/v1/orders/{id}",
             "status": "ok", "duration_ms": 89, "start": "2026-02-07T14:24:50.000Z",
             "spans_collected": 4, "spans_expected": 4,
             "spans": [
                 {"span_id": "s6", "service": "checkout-service", "operation": "http.request", "duration_ms": 89, "status": "ok"},
                 {"span_id": "s7", "service": "checkout-service", "operation": "db.query", "duration_ms": 12, "status": "ok"},
                 {"span_id": "s8", "service": "checkout-service", "operation": "cache.get", "duration_ms": 3, "status": "ok"},
                 {"span_id": "s9", "service": "checkout-service", "operation": "serialize", "duration_ms": 1, "status": "ok"},
             ]},
        ],
    },
    "payment-service": {
        "traces": [
            {"trace_id": "stu901vwx234", "service": "payment-service", "resource": "POST /api/v1/payments",
             "status": "ok", "duration_ms": 450, "start": "2026-02-07T14:25:10.000Z",
             "spans_collected": 5, "spans_expected": 5,
             "spans": [
                 {"span_id": "s10", "service": "payment-service", "operation": "http.request", "duration_ms": 450, "status": "ok"},
                 {"span_id": "s11", "service": "payment-service", "operation": "stripe.charge", "duration_ms": 380, "status": "ok"},
                 {"span_id": "s12", "service": "payment-service", "operation": "db.query", "duration_ms": 15, "status": "ok"},
                 {"span_id": "s13", "service": "payment-service", "operation": "db.query", "duration_ms": 8, "status": "ok"},
                 {"span_id": "s14", "service": "payment-service", "operation": "kafka.produce", "duration_ms": 12, "status": "ok"},
             ]},
        ],
    },
}

DATADOG_TRACE_DETAILS = {
    "abc123def456": DATADOG_TRACES["checkout-service"]["traces"][0],
    "ghi789jkl012": DATADOG_TRACES["checkout-service"]["traces"][1],
    "mno345pqr678": DATADOG_TRACES["checkout-service"]["traces"][2],
    "stu901vwx234": DATADOG_TRACES["payment-service"]["traces"][0],
}

DATADOG_METRICS = {
    "avg:checkout.request.duration{service:checkout-service}": {
        "status": "ok",
        "series": [
            {"pointlist": [[1738936800000, 0.12], [1738937100000, 0.15], [1738937400000, 0.89], [1738937700000, 4.52], [1738938000000, 8.91], [1738938300000, 11.23]],
             "metric": "checkout.request.duration", "tag_set": ["service:checkout-service"], "unit": "seconds"},
        ],
        "warning": "Data may be incomplete. OTel collector reported 12% span drop rate in the last 15 minutes.",
    },
    "sum:checkout.requests{service:checkout-service}.as_rate()": {
        "status": "ok",
        "series": [
            {"pointlist": [[1738936800000, 145], [1738937100000, 142], [1738937400000, 120], [1738937700000, 85], [1738938000000, 62], [1738938300000, 55]],
             "metric": "checkout.requests", "tag_set": ["service:checkout-service"], "unit": "requests/min"},
        ],
        "warning": "Data may be incomplete. OTel collector reported 12% span drop rate in the last 15 minutes.",
    },
}

CI_RUNS = [
    {"id": 98712, "repo": "platform/kafka-config", "workflow": "deploy-kafka-config", "branch": "main", "commit": "a3f7c2d",
     "author": "kevin.park", "status": "success", "conclusion": "success", "started": "2026-02-05T16:30:00Z", "completed": "2026-02-05T16:38:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "45s"},
        {"name": "unit-tests", "status": "completed", "conclusion": "success", "duration": "1m20s"},
        {"name": "deploy-staging", "status": "completed", "conclusion": "success", "duration": "2m10s"},
        {"name": "deploy-prod", "status": "completed", "conclusion": "success", "duration": "2m05s"},
     ],
     "note": "No integration tests or load tests in this workflow."},
    {"id": 98745, "repo": "checkout/checkout-service", "workflow": "ci", "branch": "main", "commit": "f8e2a1b",
     "author": "dan.rogers", "status": "success", "conclusion": "success", "started": "2026-02-06T10:15:00Z", "completed": "2026-02-06T10:32:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "30s"},
        {"name": "unit-tests", "status": "completed", "conclusion": "success", "duration": "3m45s"},
        {"name": "integration-tests", "status": "completed", "conclusion": "success", "duration": "5m20s"},
        {"name": "build-image", "status": "completed", "conclusion": "success", "duration": "2m15s"},
     ]},
    {"id": 98750, "repo": "checkout/cart-service", "workflow": "ci", "branch": "feature/cart-perf", "commit": "c4d5e6f",
     "author": "dan.rogers", "status": "success", "conclusion": "success", "started": "2026-02-07T09:00:00Z", "completed": "2026-02-07T09:18:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "20s"},
        {"name": "unit-tests", "status": "completed", "conclusion": "success", "duration": "2m10s"},
        {"name": "integration-tests", "status": "completed", "conclusion": "success", "duration": "4m30s"},
        {"name": "build-image", "status": "completed", "conclusion": "success", "duration": "1m50s"},
     ]},
    {"id": 98700, "repo": "platform/infrastructure", "workflow": "terraform-apply", "branch": "main", "commit": "b1c2d3e",
     "author": "kevin.park", "status": "success", "conclusion": "success", "started": "2026-01-22T11:00:00Z", "completed": "2026-01-22T11:15:00Z",
     "jobs": [
        {"name": "terraform-plan", "status": "completed", "conclusion": "success", "duration": "3m10s"},
        {"name": "terraform-apply", "status": "completed", "conclusion": "success", "duration": "8m45s"},
     ]},
]

CI_RUN_LOGS = {
    98712: """=== deploy-kafka-config / lint ===
[14:30:05] Checking YAML syntax... OK
[14:30:10] Validating Kafka config schema... OK
[14:30:45] Lint passed.

=== deploy-kafka-config / unit-tests ===
[14:31:00] Running config validation tests...
[14:31:15] test_valid_consumer_config ... PASSED
[14:31:20] test_valid_producer_config ... PASSED
[14:31:25] test_topic_naming ... PASSED
[14:31:30] test_retention_policy ... PASSED
[14:32:20] All 12 tests passed.

=== deploy-kafka-config / deploy-staging ===
[14:32:30] Applying config to staging Kafka cluster...
[14:33:00] Config applied. Verifying...
[14:33:30] Consumer group stable. Staging OK.
[14:34:40] Staging deploy complete.

=== deploy-kafka-config / deploy-prod ===
[14:34:45] Applying config to production Kafka cluster...
[14:35:15] Config applied. Verifying...
[14:35:45] Consumer group stable. Production OK.
[14:36:50] Production deploy complete.

NOTE: No integration tests with actual message flow. No load tests.
""",
    98745: """=== ci / lint ===
[10:15:05] golangci-lint run... OK
[10:15:35] Lint passed.

=== ci / unit-tests ===
[10:15:40] go test ./...
[10:17:00] ok  checkout-service/handlers     1.2s
[10:18:00] ok  checkout-service/kafka        2.1s
[10:19:25] ok  checkout-service/models       0.8s
[10:19:25] All tests passed. Coverage: 78.3%

=== ci / integration-tests ===
[10:19:30] Starting test containers (postgres, redis, kafka)...
[10:20:00] Containers ready.
[10:20:05] Running integration suite...
[10:24:50] 24/24 integration tests passed.

=== ci / build-image ===
[10:24:55] Building Docker image...
[10:27:10] Image built: registry.internal/checkout-service:f8e2a1b
""",
    98750: """=== ci / lint ===
[09:00:05] flake8 check... OK
[09:00:25] Lint passed.

=== ci / unit-tests ===
[09:00:30] pytest tests/
[09:02:40] 45 passed, 0 failed. Coverage: 82.1%

=== ci / integration-tests ===
[09:02:45] Starting test containers...
[09:03:15] Containers ready.
[09:07:15] 18/18 integration tests passed.

=== ci / build-image ===
[09:07:20] Building Docker image...
[09:09:10] Image built: registry.internal/cart-service:c4d5e6f
""",
    98700: """=== terraform-apply / terraform-plan ===
[11:00:05] Initializing Terraform...
[11:00:30] Planning...
[11:02:00] Plan: 2 to change, 0 to add, 0 to destroy.
[11:02:05] Changes:
  ~ aws_msk_configuration.kafka_config
    ~ server_properties: log.retention.hours 168 -> 4
  ~ aws_msk_cluster.main
    ~ configuration_info.revision: 3 -> 4

=== terraform-apply / terraform-apply ===
[11:03:15] Applying...
[11:10:00] Apply complete. Resources: 2 changed.
[11:11:00] MSK cluster configuration updated.
[11:15:00] Done.
""",
}

STATUSPAGE_STATUS = {
    "page": {"name": "Acme Commerce Platform", "url": "https://status.acme-commerce.com"},
    "status": {"indicator": "none", "description": "All Systems Operational"},
    "components": [
        {"name": "Checkout API", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "Payment Processing", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "Cart Service", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "Product Catalog", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "Search", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "CDN", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
    ],
    "note": "Status page checks use synthetic health checks that hit /healthz endpoints. These pass even when the service has functional issues.",
}

STATUSPAGE_INCIDENTS = [
    {"id": "inc-2026-0118", "name": "DNS Resolution Delays", "status": "resolved",
     "created_at": "2026-01-24T08:30:00Z", "resolved_at": "2026-01-24T10:15:00Z",
     "impact": "minor", "components": ["CDN", "Product Catalog"],
     "updates": [
         {"status": "investigating", "body": "We are investigating reports of slow page loads.", "created_at": "2026-01-24T08:30:00Z"},
         {"status": "identified", "body": "Root cause identified as Route53 health check misconfiguration.", "created_at": "2026-01-24T09:00:00Z"},
         {"status": "resolved", "body": "DNS configuration corrected. All services restored.", "created_at": "2026-01-24T10:15:00Z"},
     ]},
    {"id": "inc-2026-0105", "name": "Elevated Payment Processing Errors", "status": "resolved",
     "created_at": "2026-01-10T15:20:00Z", "resolved_at": "2026-01-10T16:45:00Z",
     "impact": "major", "components": ["Payment Processing", "Checkout API"],
     "updates": [
         {"status": "investigating", "body": "Investigating elevated 5xx errors on payment endpoints.", "created_at": "2026-01-10T15:20:00Z"},
         {"status": "identified", "body": "Stripe API rate limit reached due to retry storm.", "created_at": "2026-01-10T15:45:00Z"},
         {"status": "resolved", "body": "Implemented circuit breaker. Error rate returned to normal.", "created_at": "2026-01-10T16:45:00Z"},
     ]},
]

ONCALL_SCHEDULE = {
    "current": {
        "platform": {"primary": {"name": "Alicia Chen", "username": "alicia.chen", "phone": "+1-555-0101", "start": "2026-02-03T09:00:00Z", "end": "2026-02-10T09:00:00Z"},
                     "secondary": {"name": "Frank Martinez", "username": "frank.martinez", "phone": "+1-555-0104"}},
        "backend": {"primary": {"name": "Dan Rogers", "username": "dan.rogers", "phone": "+1-555-0102", "start": "2026-02-03T09:00:00Z", "end": "2026-02-10T09:00:00Z"},
                    "secondary": {"name": "Priya Sharma", "username": "priya.sharma", "phone": "+1-555-0103"}},
    },
    "rotation": [
        {"team": "platform", "week_of": "2026-01-27", "primary": "kevin.park", "secondary": "alicia.chen"},
        {"team": "platform", "week_of": "2026-02-03", "primary": "alicia.chen", "secondary": "frank.martinez"},
        {"team": "platform", "week_of": "2026-02-10", "primary": "frank.martinez", "secondary": "kevin.park"},
        {"team": "platform", "week_of": "2026-02-17", "primary": "kevin.park", "secondary": "alicia.chen"},
        {"team": "backend", "week_of": "2026-01-27", "primary": "priya.sharma", "secondary": "dan.rogers"},
        {"team": "backend", "week_of": "2026-02-03", "primary": "dan.rogers", "secondary": "priya.sharma"},
        {"team": "backend", "week_of": "2026-02-10", "primary": "priya.sharma", "secondary": "dan.rogers"},
        {"team": "backend", "week_of": "2026-02-17", "primary": "dan.rogers", "secondary": "priya.sharma"},
    ],
}

TERRAFORM_RESOURCES = [
    {"type": "aws_msk_cluster", "name": "main", "module": "kafka", "provider": "aws", "status": "applied"},
    {"type": "aws_msk_configuration", "name": "kafka_config", "module": "kafka", "provider": "aws", "status": "applied"},
    {"type": "aws_rds_cluster", "name": "checkout_db", "module": "rds", "provider": "aws", "status": "applied"},
    {"type": "aws_rds_cluster_instance", "name": "checkout_db_writer", "module": "rds", "provider": "aws", "status": "applied"},
    {"type": "aws_rds_cluster_instance", "name": "checkout_db_reader", "module": "rds", "provider": "aws", "status": "applied"},
    {"type": "aws_elasticache_replication_group", "name": "redis", "module": "redis", "provider": "aws", "status": "applied"},
    {"type": "aws_eks_cluster", "name": "main", "module": "eks", "provider": "aws", "status": "applied"},
    {"type": "aws_eks_node_group", "name": "default", "module": "eks", "provider": "aws", "status": "applied"},
    {"type": "aws_s3_bucket", "name": "assets", "module": "storage", "provider": "aws", "status": "applied"},
    {"type": "aws_s3_bucket", "name": "backups", "module": "storage", "provider": "aws", "status": "applied"},
    {"type": "aws_cloudfront_distribution", "name": "cdn", "module": "cdn", "provider": "aws", "status": "applied"},
    {"type": "aws_route53_zone", "name": "main", "module": "dns", "provider": "aws", "status": "applied"},
    {"type": "aws_acm_certificate", "name": "main", "module": "tls", "provider": "aws", "status": "applied"},
    {"type": "aws_lb", "name": "public", "module": "networking", "provider": "aws", "status": "applied"},
    {"type": "aws_lb_target_group", "name": "checkout", "module": "networking", "provider": "aws", "status": "applied"},
]

TERRAFORM_STATE = {
    "aws_msk_cluster.main": {
        "type": "aws_msk_cluster", "name": "main",
        "attributes": {
            "cluster_name": "prod-kafka", "kafka_version": "3.6.1",
            "number_of_broker_nodes": 3,
            "broker_node_group_info": {"instance_type": "kafka.m5.large", "ebs_volume_size": 1000},
            "configuration_info": {"arn": "arn:aws:kafka:us-east-1:123456789:configuration/kafka_config/4", "revision": 4},
            "current_version": "K3V2HH1JNQD1M7",
        },
    },
    "aws_msk_configuration.kafka_config": {
        "type": "aws_msk_configuration", "name": "kafka_config",
        "attributes": {
            "name": "prod-kafka-config", "kafka_versions": ["3.6.1"],
            "server_properties": "auto.create.topics.enable=false\nlog.retention.hours=4\ndefault.replication.factor=3\nmin.insync.replicas=2\nnum.partitions=6\nlog.segment.bytes=1073741824\ncompression.type=producer\n",
            "latest_revision": 4,
            "description": "Production Kafka broker configuration",
        },
        "note": "This is BROKER config only. Consumer config (session.timeout.ms, heartbeat.interval.ms) is in the application-level config, not managed by Terraform.",
    },
    "aws_rds_cluster.checkout_db": {
        "type": "aws_rds_cluster", "name": "checkout_db",
        "attributes": {
            "cluster_identifier": "prod-checkout-db", "engine": "aurora-postgresql", "engine_version": "15.4",
            "master_username": "checkout_admin", "database_name": "checkout",
            "backup_retention_period": 7, "preferred_backup_window": "03:00-04:00",
            "storage_encrypted": True, "multi_az": True,
        },
    },
    "aws_elasticache_replication_group.redis": {
        "type": "aws_elasticache_replication_group", "name": "redis",
        "attributes": {
            "replication_group_id": "prod-redis", "engine": "redis", "engine_version": "7.0",
            "node_type": "cache.r6g.large", "num_cache_clusters": 3,
            "automatic_failover_enabled": True, "at_rest_encryption_enabled": True,
        },
    },
}

DOCKER_REGISTRY_TAGS = {
    "checkout-service": [
        {"tag": "v2.14.3", "digest": "sha256:a1b2c3d4e5f6", "pushed": "2026-02-04T10:00:00Z", "size": "45.2 MB"},
        {"tag": "v2.14.2", "digest": "sha256:f6e5d4c3b2a1", "pushed": "2026-01-30T14:00:00Z", "size": "45.1 MB"},
        {"tag": "v2.14.1", "digest": "sha256:1a2b3c4d5e6f", "pushed": "2026-01-25T11:00:00Z", "size": "44.9 MB"},
        {"tag": "v2.14.0", "digest": "sha256:6f5e4d3c2b1a", "pushed": "2026-01-20T09:00:00Z", "size": "44.8 MB"},
    ],
    "cart-service": [
        {"tag": "v1.8.2", "digest": "sha256:b2c3d4e5f6a1", "pushed": "2026-02-05T08:30:00Z", "size": "32.1 MB"},
        {"tag": "v1.8.1", "digest": "sha256:a1f6e5d4c3b2", "pushed": "2026-01-28T15:00:00Z", "size": "32.0 MB"},
    ],
    "payment-service": [
        {"tag": "v3.2.1", "digest": "sha256:c3d4e5f6a1b2", "pushed": "2026-02-01T12:00:00Z", "size": "58.7 MB"},
        {"tag": "v3.2.0", "digest": "sha256:b2a1f6e5d4c3", "pushed": "2026-01-22T10:00:00Z", "size": "58.5 MB"},
    ],
    "inventory-service": [
        {"tag": "v2.1.0", "digest": "sha256:d4e5f6a1b2c3", "pushed": "2026-01-29T16:00:00Z", "size": "38.4 MB"},
    ],
    "frontend": [
        {"tag": "v4.5.0", "digest": "sha256:e5f6a1b2c3d4", "pushed": "2026-02-06T09:00:00Z", "size": "22.3 MB"},
        {"tag": "v4.4.9", "digest": "sha256:d4c3b2a1f6e5", "pushed": "2026-02-03T14:00:00Z", "size": "22.1 MB"},
    ],
}

DOCKER_REGISTRY_MANIFESTS = {
    ("checkout-service", "v2.14.3"): {
        "schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:a1b2c3d4e5f6", "size": 7023},
        "layers": [
            {"digest": "sha256:layer1abc", "size": 28311552, "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip"},
            {"digest": "sha256:layer2def", "size": 18874368, "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip"},
        ],
        "annotations": {"org.opencontainers.image.created": "2026-02-04T10:00:00Z", "org.opencontainers.image.revision": "f8e2a1b",
                        "org.opencontainers.image.source": "https://github.com/acme/checkout-service"},
    },
}

# ---------------------------------------------------------------------------


@app.list_tools()
async def list_tools():
    return [
        # Slack
        Tool(name="slack_list_channels", description="List available Slack channels",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="slack_read_channel",
             description="Read messages from a Slack channel. Supports cursor-based pagination for large channels.",
             inputSchema={"type": "object", "properties": {
                 "channel": {"type": "string", "description": "Channel name (e.g. '#incidents')"},
                 "limit": {"type": "integer", "description": "Max messages to return (default 50)", "default": 50},
                 "cursor": {"type": "integer", "description": "Pagination cursor (start from 0)", "default": 0},
             }, "required": ["channel"]}),
        Tool(name="slack_search", description="Search Slack messages across all channels.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"}, "limit": {"type": "integer", "default": 20},
             }, "required": ["query"]}),
        Tool(name="slack_post_message",
             description="Post a message to a Slack channel. Team members may respond. Use @name to direct at someone (e.g. @kevin, @alicia, @dan, @priya, @frank).",
             inputSchema={"type": "object", "properties": {
                 "channel": {"type": "string", "description": "Channel name (e.g. '#incidents')"},
                 "text": {"type": "string", "description": "Your message. Mention @name to direct at someone."},
             }, "required": ["channel", "text"]}),

        # Sentry
        Tool(name="sentry_list_projects", description="List Sentry projects and issue counts.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="sentry_list_issues", description="List Sentry issues, optionally by project.",
             inputSchema={"type": "object", "properties": {
                 "project": {"type": "string", "description": "Project name filter"},
             }}),
        Tool(name="sentry_get_issue", description="Get detailed Sentry issue with stacktrace.",
             inputSchema={"type": "object", "properties": {
                 "issue_id": {"type": "string"},
             }, "required": ["issue_id"]}),

        # PagerDuty
        Tool(name="pagerduty_list_incidents", description="List PagerDuty incidents.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="pagerduty_get_timeline", description="Get incident timeline.",
             inputSchema={"type": "object", "properties": {
                 "incident_id": {"type": "string"},
             }, "required": ["incident_id"]}),

        # Prometheus
        Tool(name="prometheus_query",
             description="Query a Prometheus metric. Use to check service health, error rates, resource usage, consumer lag, goroutine counts, connection pools, etc.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Metric name or PromQL"},
             }, "required": ["query"]}),
        Tool(name="prometheus_list_metrics", description="List all available Prometheus metrics.",
             inputSchema={"type": "object", "properties": {}}),

        # Logs
        Tool(name="logs_list_services", description="List services with available logs.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="logs_get_service_logs",
             description="Get logs for a service. Supports filtering by level, time, keyword. Use cursor for pagination.",
             inputSchema={"type": "object", "properties": {
                 "service": {"type": "string"},
                 "level": {"type": "string", "description": "ERROR, WARN, INFO"},
                 "since": {"type": "string", "description": "ISO timestamp"},
                 "grep": {"type": "string", "description": "Keyword search"},
                 "limit": {"type": "integer", "default": 50},
                 "cursor": {"type": "integer", "default": 0},
             }, "required": ["service"]}),
        Tool(name="logs_search", description="Search logs across all services.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"},
                 "limit": {"type": "integer", "default": 20},
             }, "required": ["query"]}),

        # Feature Flags
        Tool(name="featureflags_list", description="List all feature flags.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="featureflags_get", description="Get a specific flag's value.",
             inputSchema={"type": "object", "properties": {
                 "flag": {"type": "string"},
             }, "required": ["flag"]}),

        # Git
        Tool(name="git_recent_commits", description="Show recent commits, filter by file.",
             inputSchema={"type": "object", "properties": {
                 "file": {"type": "string"}, "since": {"type": "string"},
             }}),
        Tool(name="git_blame", description="Show which commits touched a file.",
             inputSchema={"type": "object", "properties": {
                 "file": {"type": "string"},
             }, "required": ["file"]}),

        # --- Jira ---
        Tool(name="jira_search", description="Search Jira tickets by query string. Returns matching issues across all projects.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "JQL or text search query"},
                 "max_results": {"type": "integer", "description": "Max results to return (default 20)", "default": 20},
             }, "required": ["query"]}),
        Tool(name="jira_get_issue", description="Get full details for a Jira issue including description, comments, and linked issues.",
             inputSchema={"type": "object", "properties": {
                 "issue_id": {"type": "string", "description": "Jira issue key (e.g. INFRA-2847)"},
             }, "required": ["issue_id"]}),
        Tool(name="jira_list_sprints", description="List current and recent sprints across all boards.",
             inputSchema={"type": "object", "properties": {
                 "state": {"type": "string", "description": "Filter by state: active, closed, future", "enum": ["active", "closed", "future"]},
             }}),

        # --- Confluence / Wiki ---
        Tool(name="wiki_search", description="Search Confluence/wiki pages by query string.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Search query"},
                 "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
             }, "required": ["query"]}),
        Tool(name="wiki_get_page", description="Get full content of a wiki page by ID.",
             inputSchema={"type": "object", "properties": {
                 "page_id": {"type": "string", "description": "Wiki page ID (e.g. WIKI-1042)"},
             }, "required": ["page_id"]}),

        # --- kubectl ---
        Tool(name="kubectl_get_pods", description="List pods in a Kubernetes namespace. Shows status, restarts, and age.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "description": "Kubernetes namespace (default, kafka, monitoring)", "default": "default"},
             }, "required": ["namespace"]}),
        Tool(name="kubectl_describe_pod", description="Get detailed information about a specific pod including events, resource usage, and container status.",
             inputSchema={"type": "object", "properties": {
                 "pod_name": {"type": "string", "description": "Full pod name"},
             }, "required": ["pod_name"]}),
        Tool(name="kubectl_get_events", description="List Kubernetes events in a namespace. Shows scheduling, scaling, and error events.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "description": "Kubernetes namespace", "default": "default"},
             }, "required": ["namespace"]}),
        Tool(name="kubectl_logs", description="Get logs from a pod/container. Returns recent log output.",
             inputSchema={"type": "object", "properties": {
                 "pod_name": {"type": "string", "description": "Full pod name"},
                 "container": {"type": "string", "description": "Container name (optional if pod has one container)"},
                 "tail": {"type": "integer", "description": "Number of lines from the end (default 100)", "default": 100},
             }, "required": ["pod_name"]}),

        # --- AWS CloudWatch ---
        Tool(name="cloudwatch_get_metrics", description="Get CloudWatch metric data. Returns 5-minute aggregated datapoints.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "description": "CloudWatch namespace (e.g. AWS/ECS, Custom/Checkout)"},
                 "metric": {"type": "string", "description": "Metric name (e.g. CPUUtilization, SuccessRate)"},
             }, "required": ["namespace", "metric"]}),
        Tool(name="cloudwatch_list_alarms", description="List all CloudWatch alarms and their current state.",
             inputSchema={"type": "object", "properties": {}}),

        # --- Datadog APM ---
        Tool(name="datadog_list_traces", description="List recent traces for a service. May have incomplete data due to OTel collector span dropping.",
             inputSchema={"type": "object", "properties": {
                 "service": {"type": "string", "description": "Service name (e.g. checkout-service)"},
                 "status": {"type": "string", "description": "Filter by status: error, ok", "enum": ["error", "ok"]},
             }, "required": ["service"]}),
        Tool(name="datadog_get_trace", description="Get detailed trace information including all collected spans.",
             inputSchema={"type": "object", "properties": {
                 "trace_id": {"type": "string", "description": "Trace ID"},
             }, "required": ["trace_id"]}),
        Tool(name="datadog_query_metrics", description="Query Datadog metrics using Datadog query syntax.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Datadog metric query (e.g. avg:checkout.request.duration{service:checkout-service})"},
             }, "required": ["query"]}),

        # --- CI/CD ---
        Tool(name="ci_list_runs", description="List recent CI/CD workflow runs for a repository.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string", "description": "Repository name (e.g. checkout/checkout-service)"},
             }}),
        Tool(name="ci_get_run_logs", description="Get detailed logs for a CI/CD workflow run.",
             inputSchema={"type": "object", "properties": {
                 "run_id": {"type": "integer", "description": "Workflow run ID"},
             }, "required": ["run_id"]}),

        # --- Status Page ---
        Tool(name="statuspage_get_status", description="Get current system status from the public status page.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="statuspage_list_incidents", description="List recent status page incidents.",
             inputSchema={"type": "object", "properties": {}}),

        # --- On-Call ---
        Tool(name="oncall_who_is_on_call", description="Show who is currently on-call for each team.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="oncall_get_schedule", description="Get the full on-call rotation schedule.",
             inputSchema={"type": "object", "properties": {
                 "team": {"type": "string", "description": "Filter by team (platform, backend)"},
             }}),

        # --- Terraform ---
        Tool(name="terraform_show_state", description="Show Terraform state for a specific resource. Shows current infrastructure configuration.",
             inputSchema={"type": "object", "properties": {
                 "resource": {"type": "string", "description": "Resource address (e.g. aws_msk_cluster.main)"},
             }, "required": ["resource"]}),
        Tool(name="terraform_list_resources", description="List all Terraform-managed infrastructure resources.",
             inputSchema={"type": "object", "properties": {}}),

        # --- Docker Registry ---
        Tool(name="registry_list_tags", description="List image tags for a repository in the Docker registry.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string", "description": "Image repository name (e.g. checkout-service)"},
             }, "required": ["repo"]}),
        Tool(name="registry_get_manifest", description="Get the manifest for a specific image tag.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string", "description": "Image repository name"},
                 "tag": {"type": "string", "description": "Image tag (e.g. v2.14.3)"},
             }, "required": ["repo", "tag"]}),
    ]


def _text(data) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _call_server(service: str, method: str, endpoint: str, params: dict) -> dict:
    """Route a call to the appropriate evidence server."""
    srv = SERVERS.get(service)
    if not srv:
        return _add_verbose_metadata({"error": f"Service not found: {service}"})
    resp = srv.make_request(method, endpoint, params)
    return _add_verbose_metadata(resp.body if isinstance(resp.body, dict) else {"data": resp.body})


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    # Rate limiting: 20% chance of rejection
    rl = _maybe_rate_limit()
    if rl:
        return _text(rl)

    # --- Slack ---
    if name == "slack_list_channels":
        return _text(_call_server("slack", "GET", "/channels", {}))
    if name == "slack_read_channel":
        ch = arguments.get("channel", "").lstrip("#")
        return _text(_call_server("slack", "GET", f"/channels/{ch}/messages", {
            "limit": str(arguments.get("limit", 50)),
            "cursor": str(arguments.get("cursor", 0)),
        }))
    if name == "slack_search":
        return _text(_call_server("slack", "GET", "/search", {
            "query": arguments.get("query", ""),
            "limit": str(arguments.get("limit", 20)),
        }))
    if name == "slack_post_message":
        ch = arguments.get("channel", "#incidents").lstrip("#")
        return _text(_call_server("slack", "POST", f"/channels/{ch}/messages", {
            "text": arguments.get("text", ""),
        }))

    # --- Sentry ---
    if name == "sentry_list_projects":
        return _text(_call_server("sentry", "GET", "/projects", {}))
    if name == "sentry_list_issues":
        return _text(_call_server("sentry", "GET", "/issues", {
            "project": arguments.get("project", ""),
        }))
    if name == "sentry_get_issue":
        return _text(_call_server("sentry", "GET", f"/issues/{arguments['issue_id']}", {}))

    # --- PagerDuty ---
    if name == "pagerduty_list_incidents":
        return _text(_call_server("pagerduty", "GET", "/incidents", {}))
    if name == "pagerduty_get_timeline":
        return _text(_call_server("pagerduty", "GET", f"/incidents/{arguments['incident_id']}/timeline", {}))

    # --- Prometheus ---
    if name == "prometheus_query":
        return _text(_call_server("prometheus", "GET", "/query", {"q": arguments.get("query", "")}))
    if name == "prometheus_list_metrics":
        return _text(_call_server("prometheus", "GET", "/metrics", {}))

    # --- Logs ---
    if name == "logs_list_services":
        return _text(_call_server("logs", "GET", "/services", {}))
    if name == "logs_get_service_logs":
        params = {"limit": str(arguments.get("limit", 50)), "cursor": str(arguments.get("cursor", 0))}
        if arguments.get("level"): params["level"] = arguments["level"]
        if arguments.get("since"): params["since"] = arguments["since"]
        if arguments.get("grep"): params["grep"] = arguments["grep"]
        return _text(_call_server("logs", "GET", f"/services/{arguments['service']}/logs", params))
    if name == "logs_search":
        return _text(_call_server("logs", "GET", "/search", {
            "query": arguments.get("query", ""),
            "limit": str(arguments.get("limit", 20)),
        }))

    # --- Feature Flags ---
    if name == "featureflags_list":
        return _text(_call_server("featureflags", "GET", "/flags", {}))
    if name == "featureflags_get":
        return _text(_call_server("featureflags", "GET", f"/flags/{arguments['flag']}", {}))

    # --- Git ---
    if name == "git_recent_commits":
        params = {}
        if arguments.get("file"): params["file"] = arguments["file"]
        if arguments.get("since"): params["since"] = arguments["since"]
        return _text(_call_server("git", "GET", "/log", params))
    if name == "git_blame":
        return _text(_call_server("git", "GET", f"/blame/{arguments['file']}", {}))

    # -----------------------------------------------------------------------
    # Noise tool handlers (static pre-seeded data)
    # -----------------------------------------------------------------------

    # --- Jira ---
    if name == "jira_search":
        query = arguments.get("query", "").lower()
        results = []
        for ticket in JIRA_TICKETS:
            if (query in ticket["summary"].lower()
                    or query in ticket.get("description", "").lower()
                    or query in ticket["key"].lower()
                    or any(query in lbl for lbl in ticket.get("labels", []))):
                results.append({
                    "key": ticket["key"], "summary": ticket["summary"],
                    "status": ticket["status"], "assignee": ticket["assignee"],
                    "priority": ticket["priority"], "type": ticket["type"],
                    "updated": ticket["updated"],
                })
        if not results:
            # Return all tickets if no specific match
            results = [{"key": t["key"], "summary": t["summary"], "status": t["status"],
                        "assignee": t["assignee"], "priority": t["priority"], "type": t["type"],
                        "updated": t["updated"]} for t in JIRA_TICKETS]
        max_results = arguments.get("max_results", 20)
        return _text(_add_verbose_metadata({"total": len(results), "issues": results[:max_results]}))

    if name == "jira_get_issue":
        issue_id = arguments.get("issue_id", "").upper()
        for ticket in JIRA_TICKETS:
            if ticket["key"] == issue_id:
                return _text(_add_verbose_metadata(dict(ticket)))
        return _text(_add_verbose_metadata({"error": f"Issue not found: {issue_id}"}))

    if name == "jira_list_sprints":
        state_filter = arguments.get("state")
        sprints = JIRA_SPRINTS
        if state_filter:
            sprints = [s for s in sprints if s["state"] == state_filter]
        return _text(_add_verbose_metadata({"sprints": sprints}))

    # --- Confluence / Wiki ---
    if name == "wiki_search":
        query = arguments.get("query", "").lower()
        results = []
        for page_id, page in WIKI_PAGES.items():
            if query in page["title"].lower() or query in page["body"].lower():
                results.append({
                    "id": page["id"], "title": page["title"], "space": page["space"],
                    "last_updated": page["last_updated"], "updated_by": page["updated_by"],
                    "excerpt": page["body"][:200] + "...",
                })
        if not results:
            results = [{"id": p["id"], "title": p["title"], "space": p["space"],
                        "last_updated": p["last_updated"], "updated_by": p["updated_by"],
                        "excerpt": p["body"][:200] + "..."}
                       for p in WIKI_PAGES.values()]
        limit = arguments.get("limit", 10)
        return _text(_add_verbose_metadata({"total": len(results), "results": results[:limit]}))

    if name == "wiki_get_page":
        page_id = arguments.get("page_id", "")
        page = WIKI_PAGES.get(page_id)
        if page:
            return _text(_add_verbose_metadata(dict(page)))
        return _text(_add_verbose_metadata({"error": f"Page not found: {page_id}"}))

    # --- kubectl ---
    if name == "kubectl_get_pods":
        ns = arguments.get("namespace", "default")
        pods = KUBECTL_PODS.get(ns, [])
        if not pods:
            return _text(_add_verbose_metadata({"error": f"No pods found in namespace: {ns}"}))
        return _text(_add_verbose_metadata({"namespace": ns, "pods": pods}))

    if name == "kubectl_describe_pod":
        pod_name = arguments.get("pod_name", "")
        detail = KUBECTL_POD_DETAILS.get(pod_name)
        if detail:
            return _text(_add_verbose_metadata(dict(detail)))
        # Generic response for pods we don't have specific detail for
        for ns_pods in KUBECTL_PODS.values():
            for pod in ns_pods:
                if pod["name"] == pod_name:
                    return _text(_add_verbose_metadata({
                        "name": pod["name"], "status": {"phase": pod["status"]},
                        "containers": [{"name": pod["name"].split("-")[0], "ready": True,
                                        "restarts": pod["restarts"]}],
                        "events": [],
                    }))
        return _text(_add_verbose_metadata({"error": f"Pod not found: {pod_name}"}))

    if name == "kubectl_get_events":
        ns = arguments.get("namespace", "default")
        events = KUBECTL_EVENTS.get(ns, [])
        return _text(_add_verbose_metadata({"namespace": ns, "events": events}))

    if name == "kubectl_logs":
        pod_name = arguments.get("pod_name", "")
        container = arguments.get("container")
        tail = arguments.get("tail", 100)
        pod_logs = KUBECTL_LOGS.get(pod_name)
        if pod_logs:
            if container and container in pod_logs:
                lines = pod_logs[container]
            else:
                # Return logs from first container
                first_container = next(iter(pod_logs))
                lines = pod_logs[first_container]
            return _text(_add_verbose_metadata({"pod": pod_name, "container": container or "default", "lines": lines[-tail:]}))
        return _text(_add_verbose_metadata({"error": f"No logs available for pod: {pod_name}"}))

    # --- AWS CloudWatch ---
    if name == "cloudwatch_get_metrics":
        ns = arguments.get("namespace", "")
        metric = arguments.get("metric", "")
        ns_data = CLOUDWATCH_METRICS.get(ns, {})
        metric_data = ns_data.get(metric)
        if metric_data:
            return _text(_add_verbose_metadata(dict(metric_data)))
        # Return empty if not found
        return _text(_add_verbose_metadata({"label": metric, "datapoints": [], "message": f"No data found for {ns}/{metric}. Check namespace and metric name."}))

    if name == "cloudwatch_list_alarms":
        return _text(_add_verbose_metadata({"alarms": CLOUDWATCH_ALARMS}))

    # --- Datadog APM ---
    if name == "datadog_list_traces":
        service = arguments.get("service", "")
        status_filter = arguments.get("status")
        svc_data = DATADOG_TRACES.get(service, {"traces": []})
        traces = svc_data["traces"]
        if status_filter:
            traces = [t for t in traces if t["status"] == status_filter]
        summary = [{"trace_id": t["trace_id"], "resource": t["resource"], "status": t["status"],
                    "duration_ms": t["duration_ms"], "start": t["start"],
                    "spans_collected": t.get("spans_collected"), "spans_expected": t.get("spans_expected"),
                    "warning": t.get("warning")} for t in traces]
        return _text(_add_verbose_metadata({"service": service, "traces": summary,
                      "note": "Traces may be incomplete. OTel collector has been dropping spans intermittently."}))

    if name == "datadog_get_trace":
        trace_id = arguments.get("trace_id", "")
        trace = DATADOG_TRACE_DETAILS.get(trace_id)
        if trace:
            return _text(_add_verbose_metadata(dict(trace)))
        return _text(_add_verbose_metadata({"error": f"Trace not found: {trace_id}"}))

    if name == "datadog_query_metrics":
        query = arguments.get("query", "")
        metric_data = DATADOG_METRICS.get(query)
        if metric_data:
            return _text(_add_verbose_metadata(dict(metric_data)))
        return _text(_add_verbose_metadata({"status": "ok", "series": [],
                      "warning": "Data may be incomplete. OTel collector reported span drop rate in the last 15 minutes.",
                      "message": f"No data found for query: {query}"}))

    # --- CI/CD ---
    if name == "ci_list_runs":
        repo_filter = arguments.get("repo", "")
        runs = CI_RUNS
        if repo_filter:
            runs = [r for r in runs if repo_filter.lower() in r["repo"].lower()]
        summary = [{"id": r["id"], "repo": r["repo"], "workflow": r["workflow"], "branch": r["branch"],
                    "author": r["author"], "status": r["status"], "conclusion": r["conclusion"],
                    "started": r["started"], "completed": r["completed"],
                    "note": r.get("note")} for r in runs]
        return _text(_add_verbose_metadata({"total": len(summary), "runs": summary}))

    if name == "ci_get_run_logs":
        run_id = arguments.get("run_id", 0)
        logs = CI_RUN_LOGS.get(run_id)
        if logs:
            return _text(_add_verbose_metadata({"run_id": run_id, "logs": logs}))
        return _text(_add_verbose_metadata({"error": f"Run not found: {run_id}"}))

    # --- Status Page ---
    if name == "statuspage_get_status":
        return _text(_add_verbose_metadata(dict(STATUSPAGE_STATUS)))

    if name == "statuspage_list_incidents":
        return _text(_add_verbose_metadata({"incidents": STATUSPAGE_INCIDENTS}))

    # --- On-Call ---
    if name == "oncall_who_is_on_call":
        return _text(_add_verbose_metadata(dict(ONCALL_SCHEDULE["current"])))

    if name == "oncall_get_schedule":
        team_filter = arguments.get("team")
        rotation = ONCALL_SCHEDULE["rotation"]
        if team_filter:
            rotation = [r for r in rotation if r["team"] == team_filter]
        return _text(_add_verbose_metadata({"current": ONCALL_SCHEDULE["current"], "rotation": rotation}))

    # --- Terraform ---
    if name == "terraform_show_state":
        resource = arguments.get("resource", "")
        state = TERRAFORM_STATE.get(resource)
        if state:
            return _text(_add_verbose_metadata(dict(state)))
        return _text(_add_verbose_metadata({"error": f"Resource not found in state: {resource}. Use terraform_list_resources to see available resources."}))

    if name == "terraform_list_resources":
        return _text(_add_verbose_metadata({"resources": TERRAFORM_RESOURCES}))

    # --- Docker Registry ---
    if name == "registry_list_tags":
        repo = arguments.get("repo", "")
        tags = DOCKER_REGISTRY_TAGS.get(repo)
        if tags:
            return _text(_add_verbose_metadata({"repository": f"registry.internal/{repo}", "tags": tags}))
        return _text(_add_verbose_metadata({"error": f"Repository not found: {repo}. Known repos: {list(DOCKER_REGISTRY_TAGS.keys())}"}))

    if name == "registry_get_manifest":
        repo = arguments.get("repo", "")
        tag = arguments.get("tag", "")
        manifest = DOCKER_REGISTRY_MANIFESTS.get((repo, tag))
        if manifest:
            return _text(_add_verbose_metadata(dict(manifest)))
        # Generic manifest for known repo/tag combos
        tags = DOCKER_REGISTRY_TAGS.get(repo, [])
        for t in tags:
            if t["tag"] == tag:
                return _text(_add_verbose_metadata({
                    "schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "config": {"digest": t["digest"], "size": 7023},
                    "layers": [{"digest": "sha256:generic_layer", "size": 25165824}],
                    "annotations": {"org.opencontainers.image.created": t["pushed"]},
                }))
        return _text(_add_verbose_metadata({"error": f"Manifest not found: {repo}:{tag}"}))

    return _text(_add_verbose_metadata({"error": f"Unknown tool: {name}"}))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
