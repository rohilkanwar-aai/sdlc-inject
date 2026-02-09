#!/usr/bin/env python3
"""MCP server for CASCADE-011 with LLM-powered coworkers.

Kernel tcp_wmem -> gRPC truncation -> protobuf silent drop -> double-fulfillment
-> storefront blackout cascade (8 hops, triple significant silence).

Key difference from CASCADE-012: slack_post_message uses the LLM coworker
engine (Sonnet 4.5) instead of static Q&A matching. Other tools use the
existing evidence-seeded servers plus 42 noise tools.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

# Add project root to path so we can import sdlc_inject
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

from sdlc_inject.mcp_servers.evidence import load_evidence_servers_interactive
from sdlc_inject.mcp_servers.llm_coworkers import (
    Persona,
    LLMCoworkerEngine,
    LLMReactiveSlackServer,
)

import random as _random_module
_rate_limit_rng = _random_module.Random(2026)
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
            "reset_at": "2026-02-07T15:00:00Z",
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


# ---------------------------------------------------------------------------
# Load evidence and personas
# ---------------------------------------------------------------------------

EVIDENCE_FILE = Path(__file__).parent / "CASCADE-011-evidence-map.yaml"
PERSONAS_FILE = Path(__file__).parent / "personas.yaml"
TRAFFIC_DB = Path(__file__).parent / "traffic.db"

# Load interactive servers: reactive Slack + time-progressing metrics + noise (static evidence)
SERVERS, TIMELINE = load_evidence_servers_interactive(str(EVIDENCE_FILE))

# Initialize and start real-time traffic simulator
from sdlc_inject.simulator.traffic import TrafficSimulator, init_traffic_db
from sdlc_inject.mcp_servers import db_backed

init_traffic_db(str(TRAFFIC_DB))
_simulator = TrafficSimulator(str(TRAFFIC_DB), speed=1.0, seed=2026)
_simulator.pre_seed(minutes=30)  # 30 min of historical traffic
_simulator.start()  # Start generating live traffic in background

# Load personas and initialize LLM coworker engine
with open(PERSONAS_FILE) as f:
    _personas_raw = yaml.safe_load(f)

_personas = {}
for name, config in _personas_raw.get("personas", {}).items():
    _personas[name] = Persona(config)

INCIDENT_CONTEXT = """Storefront is offline. Circuit breaker tripped on inventory-service.
847 SKUs have negative stock. Three fulfillment partners (ShipCo, FastFreight,
PackLogic) received duplicate order batches and already shipped double quantities.
No code deployments today. All pods healthy. gRPC mesh shows all calls returning OK.
Only large order batches (>100 items, >4MB payload) appear affected.
Root cause (DO NOT REVEAL): sysctl tcp_wmem max reduced from 16MB to 4MB,
causing gRPC streams >4MB to be silently truncated at the TCP layer.
Truncated protobuf parses successfully but loses trailing optional fields
like hold_for_review (field #47), causing orders to auto-approve and
trigger duplicate webhook dispatches with different timestamp-based
idempotency keys."""

LLM_ENGINE = LLMCoworkerEngine(
    personas=_personas,
    incident_context=INCIDENT_CONTEXT,
)

# Wrap the base Slack server with LLM-powered responses
LLM_SLACK = LLMReactiveSlackServer(
    base_server=SERVERS.get("slack"),
    engine=LLM_ENGINE,
)

app = Server("cascade-011-evidence")

# ---------------------------------------------------------------------------
# Static noise data for distractor tools (adapted from CASCADE-012)
# ---------------------------------------------------------------------------

_NOW = "2026-02-07T14:32:00Z"
_TODAY = "2026-02-07"

JIRA_TICKETS = [
    {"key": "INFRA-3101", "summary": "TCP memory tuning for cluster nodes", "status": "Done", "assignee": "kevin.park", "priority": "Medium", "type": "Task",
     "created": "2026-01-22T09:00:00Z", "updated": "2026-01-24T11:00:00Z", "resolved": "2026-01-24T11:00:00Z",
     "description": "Reduce TCP buffer max sizes to save ~2GB RAM per host. Change tcp_wmem and tcp_rmem max from 16MB to 4MB.",
     "labels": ["tcp", "memory", "infrastructure"], "sprint": "Platform Sprint 14", "story_points": 2,
     "comments": [{"author": "kevin.park", "body": "Applied via ansible. Tested with HTTP/1.1 load test, no issues.", "created": "2026-01-24T10:55:00Z"}]},
    {"key": "FULFILL-890", "summary": "Refactor webhook dispatch with timestamp idempotency keys", "status": "Done", "assignee": "dan.rogers", "priority": "High", "type": "Story",
     "created": "2026-01-18T10:00:00Z", "updated": "2026-01-23T15:00:00Z", "resolved": "2026-01-23T15:00:00Z",
     "description": "Change idempotency key format from UUID to timestamp for better traceability. Update webhook dispatch to async.",
     "labels": ["fulfillment", "webhook", "idempotency"], "sprint": "Fulfillment Sprint 8", "story_points": 5,
     "comments": [{"author": "dan.rogers", "body": "Refactor complete. Partner integration tests passing.", "created": "2026-01-23T14:55:00Z"},
                   {"author": "priya.sharma", "body": "Verified ShipCo, FastFreight, PackLogic all accept new key format.", "created": "2026-01-23T15:00:00Z"}]},
    {"key": "FULFILL-895", "summary": "Improve fulfillment retry logic with exponential backoff", "status": "Done", "assignee": "priya.sharma", "priority": "Medium", "type": "Task",
     "created": "2026-01-20T11:00:00Z", "updated": "2026-01-22T14:30:00Z", "resolved": "2026-01-22T14:30:00Z",
     "description": "Add exponential backoff to fulfillment webhook retry. Current retry is immediate which can cause duplicate sends.",
     "labels": ["fulfillment", "retry", "resilience"], "sprint": "Fulfillment Sprint 8", "story_points": 3,
     "comments": [{"author": "priya.sharma", "body": "Added backoff with jitter. Max 3 retries, 1s/2s/4s delays.", "created": "2026-01-22T14:28:00Z"}]},
    {"key": "PLAT-925", "summary": "Adjust circuit breaker threshold for inventory service", "status": "Done", "assignee": "frank.martinez", "priority": "Medium", "type": "Task",
     "created": "2026-01-26T09:00:00Z", "updated": "2026-01-28T11:30:00Z", "resolved": "2026-01-28T11:30:00Z",
     "description": "Current threshold of 100 negative SKUs is too high. Reduce to 50 to trip faster when inventory data is inconsistent.",
     "labels": ["circuit-breaker", "inventory", "storefront"], "sprint": "Platform Sprint 14", "story_points": 2,
     "comments": [{"author": "frank.martinez", "body": "Threshold updated. Tested with chaos engineering -- trips in <10s.", "created": "2026-01-28T11:28:00Z"}]},
    {"key": "PLAT-901", "summary": "Upgrade Redis to 7.2", "status": "In Progress", "assignee": "alicia.chen", "priority": "Medium", "type": "Task",
     "created": "2026-02-01T09:00:00Z", "updated": "2026-02-06T15:00:00Z", "resolved": None,
     "description": "Upgrade Redis cluster from 7.0.11 to 7.2.4 for ACL improvements and memory optimizations.",
     "labels": ["redis", "upgrade", "infrastructure"], "sprint": "Platform Sprint 14", "story_points": 5,
     "comments": [{"author": "alicia.chen", "body": "Staging upgrade complete. Running soak test before prod.", "created": "2026-02-06T14:55:00Z"}]},
    {"key": "CHKOUT-1501", "summary": "Add Apple Pay support", "status": "In Review", "assignee": "dan.rogers", "priority": "High", "type": "Story",
     "created": "2026-01-25T10:30:00Z", "updated": "2026-02-06T11:00:00Z", "resolved": None,
     "description": "Integrate Apple Pay as a payment method in checkout flow.",
     "labels": ["checkout", "payments", "feature"], "sprint": "Checkout Sprint 23", "story_points": 8,
     "comments": [{"author": "dan.rogers", "body": "PR #487 ready for review.", "created": "2026-02-06T10:58:00Z"}]},
    {"key": "PLAT-910", "summary": "Migrate service mesh to Istio 1.21", "status": "To Do", "assignee": "alicia.chen", "priority": "Medium", "type": "Task",
     "created": "2026-02-03T14:00:00Z", "updated": "2026-02-03T14:00:00Z", "resolved": None,
     "description": "Current Istio 1.19 is approaching EOL. Plan migration to 1.21.",
     "labels": ["istio", "service-mesh", "upgrade"], "sprint": "Platform Sprint 15", "story_points": 13,
     "comments": []},
    {"key": "CHKOUT-1510", "summary": "Flaky test: test_concurrent_cart_updates", "status": "Open", "assignee": "priya.sharma", "priority": "Low", "type": "Bug",
     "created": "2026-02-04T16:20:00Z", "updated": "2026-02-04T16:20:00Z", "resolved": None,
     "description": "test_concurrent_cart_updates fails ~5% of CI runs.",
     "labels": ["tests", "flaky", "cart"], "sprint": "Checkout Sprint 23", "story_points": 2,
     "comments": []},
    {"key": "PLAT-915", "summary": "Document disaster recovery procedures", "status": "In Progress", "assignee": "frank.martinez", "priority": "Medium", "type": "Task",
     "created": "2026-02-05T09:30:00Z", "updated": "2026-02-06T10:00:00Z", "resolved": None,
     "description": "Create comprehensive DR runbook.",
     "labels": ["documentation", "DR", "runbook"], "sprint": "Platform Sprint 14", "story_points": 5,
     "comments": [{"author": "frank.martinez", "body": "Draft for Redis and Postgres sections done.", "created": "2026-02-06T09:58:00Z"}]},
    {"key": "INFRA-3110", "summary": "Set up Prometheus remote write to Thanos", "status": "To Do", "assignee": "alicia.chen", "priority": "Low", "type": "Task",
     "created": "2026-02-06T08:00:00Z", "updated": "2026-02-06T08:00:00Z", "resolved": None,
     "description": "Enable long-term metrics storage.",
     "labels": ["prometheus", "thanos", "observability"], "sprint": "Platform Sprint 15", "story_points": 5,
     "comments": []},
    {"key": "SEC-340", "summary": "Rotate TLS certificates for internal services", "status": "Done", "assignee": "frank.martinez", "priority": "High", "type": "Task",
     "created": "2026-01-30T10:00:00Z", "updated": "2026-02-03T12:00:00Z", "resolved": "2026-02-03T12:00:00Z",
     "description": "Internal mTLS certificates expire Feb 15. Rotate all.",
     "labels": ["security", "tls", "certificates"], "sprint": "Platform Sprint 14", "story_points": 3,
     "comments": [{"author": "frank.martinez", "body": "All certs rotated.", "created": "2026-02-03T11:58:00Z"}]},
    {"key": "FULFILL-910", "summary": "Partner API schema v3 migration", "status": "To Do", "assignee": "priya.sharma", "priority": "Medium", "type": "Story",
     "created": "2026-02-06T14:00:00Z", "updated": "2026-02-06T14:00:00Z", "resolved": None,
     "description": "ShipCo is migrating to API v3. Update our integration before March deadline.",
     "labels": ["fulfillment", "partner", "migration"], "sprint": "Fulfillment Sprint 9", "story_points": 8,
     "comments": []},
    {"key": "OPS-847", "summary": "Investigate missing hold_for_review flags", "status": "Open", "assignee": "dan.rogers", "priority": "Medium", "type": "Bug",
     "created": "2026-02-05T10:30:00Z", "updated": "2026-02-07T09:00:00Z", "resolved": None,
     "description": "Some order batches are missing the hold_for_review protobuf field. Only seen on large batches (>100 orders). Protobuf.Unmarshal returns no error.",
     "labels": ["order-processing", "protobuf", "bug"], "sprint": "Fulfillment Sprint 8", "story_points": 5,
     "comments": [{"author": "dan.rogers", "body": "Can't reproduce locally. gRPC call returns OK. Maybe data issue?", "created": "2026-02-05T16:00:00Z"}]},
    {"key": "PLAT-888", "summary": "Add structured logging to payment service", "status": "Done", "assignee": "dan.rogers", "priority": "Medium", "type": "Task",
     "created": "2026-01-12T13:00:00Z", "updated": "2026-01-20T10:00:00Z", "resolved": "2026-01-20T10:00:00Z",
     "description": "Migrate payment service to structured JSON logging.",
     "labels": ["logging", "observability", "payment"], "sprint": "Platform Sprint 13", "story_points": 3,
     "comments": []},
    {"key": "CHKOUT-1525", "summary": "Add retry logic to inventory reservation API", "status": "Open", "assignee": None, "priority": "Medium", "type": "Task",
     "created": "2026-02-07T10:00:00Z", "updated": "2026-02-07T10:00:00Z", "resolved": None,
     "description": "Inventory reservation calls occasionally fail with 503.",
     "labels": ["inventory", "resilience"], "sprint": "Checkout Sprint 24", "story_points": 3,
     "comments": []},
]

JIRA_SPRINTS = [
    {"id": 140, "name": "Platform Sprint 14", "state": "active", "start": "2026-01-27", "end": "2026-02-09",
     "goal": "Redis upgrade, DR docs, TCP tuning", "issues_total": 12, "issues_done": 8},
    {"id": 141, "name": "Platform Sprint 15", "state": "future", "start": "2026-02-10", "end": "2026-02-23",
     "goal": "Istio migration, Thanos setup", "issues_total": 6, "issues_done": 0},
    {"id": 80, "name": "Fulfillment Sprint 8", "state": "active", "start": "2026-01-27", "end": "2026-02-09",
     "goal": "Webhook refactor, retry improvements", "issues_total": 10, "issues_done": 7},
    {"id": 81, "name": "Fulfillment Sprint 9", "state": "future", "start": "2026-02-10", "end": "2026-02-23",
     "goal": "Partner API v3 migration", "issues_total": 4, "issues_done": 0},
    {"id": 230, "name": "Checkout Sprint 23", "state": "active", "start": "2026-01-27", "end": "2026-02-09",
     "goal": "Apple Pay, cart perf", "issues_total": 8, "issues_done": 4},
]

WIKI_PAGES = {
    "WIKI-2001": {
        "id": "WIKI-2001", "title": "Order Processing Pipeline Architecture", "space": "Engineering",
        "last_updated": "2026-01-15T10:00:00Z", "updated_by": "dan.rogers",
        "body": """# Order Processing Pipeline Architecture

## Overview
The order processing pipeline handles batch order fulfillment via gRPC streaming.

## Data Flow
1. batch-builder service creates order batches (protobuf serialized)
2. Sends batch via gRPC stream to order-processing-service
3. order-processing-service deserializes protobuf and applies business rules
4. Orders with hold_for_review=true go to manual review queue
5. Auto-approved orders trigger fulfillment webhook dispatch
6. fulfillment-gateway sends webhooks to partners (ShipCo, FastFreight, PackLogic)

## Protobuf Schema
- OrderBatch message contains repeated Order messages
- Each Order has ~50 fields including hold_for_review (field #47, optional bool)
- Batch sizes range from 500KB (small) to 8MB+ (large seasonal batches)

## Idempotency
- Webhook dispatch uses idempotency keys to prevent duplicate fulfillment
- Format: timestamp-based (changed from UUID in v3.8.2)

## Circuit Breaker
- Storefront has circuit breaker on inventory-service
- Trips when >50 SKUs have negative stock
- Auto-resets after 5 minutes if inventory recovers

_Last updated: 2026-01-15 by Dan Rogers_
""",
    },
    "WIKI-2002": {
        "id": "WIKI-2002", "title": "Incident Response Runbook", "space": "SRE",
        "last_updated": "2025-11-20T14:00:00Z", "updated_by": "alicia.chen",
        "body": """# Incident Response Runbook

## Severity Levels
- **SEV1**: Complete service outage, revenue impact > $10K/hr
- **SEV2**: Partial degradation, user-facing impact
- **SEV3**: Internal tooling issues

## First Responder Checklist
1. Acknowledge PagerDuty alert
2. Join #incidents Slack channel
3. Check pod health: kubectl get pods
4. Check recent deploys in #deploys
5. Check Prometheus metrics
6. Escalate if not resolved in 15 minutes

## Escalation Contacts
- SRE: Alicia Chen (@alicia), Kevin Park (@kevin)
- Backend: Dan Rogers (@dan), Priya Sharma (@priya)
- DevOps: Frank Martinez (@frank)

_Last reviewed: 2025-11-20 by Alicia Chen_
""",
    },
    "WIKI-2003": {
        "id": "WIKI-2003", "title": "TCP/Network Tuning Guide", "space": "Platform",
        "last_updated": "2026-01-24T11:00:00Z", "updated_by": "kevin.park",
        "body": """# TCP/Network Tuning Guide

## Current Configuration
Applied via ansible role `tcp_tuning`:
- `net.ipv4.tcp_wmem = 4096 87380 4194304` (min/default/max write buffer)
- `net.ipv4.tcp_rmem = 4096 87380 4194304` (min/default/max read buffer)
- `net.core.somaxconn = 65535`

## History
- 2026-01-24: Reduced tcp_wmem/tcp_rmem max from 16MB to 4MB (kevin.park)
  - Saves ~2GB RAM per host
  - Tested with HTTP/1.1 load test (1000 concurrent) -- no issues
  - Note: gRPC uses HTTP/2 over TCP, same buffer semantics

## Impact
- Per-socket maximum send/receive buffer is now 4MB
- Most API requests are well under 4MB
- If any single TCP stream needs to send >4MB in one write, it will be bounded

_Last updated: 2026-01-24 by Kevin Park_
""",
    },
    "WIKI-2004": {
        "id": "WIKI-2004", "title": "Fulfillment Partner Integration", "space": "Engineering",
        "last_updated": "2026-01-23T15:00:00Z", "updated_by": "priya.sharma",
        "body": """# Fulfillment Partner Integration

## Partners
- **ShipCo**: Primary fulfillment, handles 60% of volume
- **FastFreight**: Secondary, handles 30%
- **PackLogic**: Tertiary, handles 10%

## Webhook Format
- POST to partner endpoint with JSON payload
- Idempotency key in X-Idempotency-Key header (timestamp format since v3.8.2)
- Partners are expected to dedup on idempotency key

## Batch Sizes
- Small batches: 10-50 orders (~500KB-2MB)
- Medium batches: 50-150 orders (~2MB-5MB)
- Large batches: 150-500 orders (~5MB-10MB)

_Last updated: 2026-01-23 by Priya Sharma_
""",
    },
    "WIKI-2005": {
        "id": "WIKI-2005", "title": "On-Call Handbook", "space": "SRE",
        "last_updated": "2025-11-10T09:00:00Z", "updated_by": "frank.martinez",
        "body": """# On-Call Handbook

## Rotation Schedule
- Platform team: weekly rotation (Mon 9am to Mon 9am)
- Backend team: weekly rotation
- SRE: always secondary on-call

## Tools Access
- PagerDuty: all on-call engineers have admin
- Grafana: SSO
- kubectl: via bastion host or VPN
- ansible: via jump box for infra changes

_Last reviewed: 2025-11-10 by Frank Martinez_
""",
    },
}

KUBECTL_PODS = {
    "default": [
        {"name": "order-processing-service-6a7b8c9d0-x1y2z", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "prod-node-03", "cpu": "150m", "memory": "312Mi"},
        {"name": "order-processing-service-6a7b8c9d0-a3b4c", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "prod-node-07", "cpu": "145m", "memory": "305Mi"},
        {"name": "batch-builder-4d5e6f7g8-h9i0j", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "prod-node-03", "cpu": "200m", "memory": "256Mi"},
        {"name": "fulfillment-gateway-2k3l4m5n6-o7p8q", "ready": "1/1", "status": "Running", "restarts": 0, "age": "4d", "node": "prod-node-07", "cpu": "120m", "memory": "198Mi"},
        {"name": "inventory-service-9r0s1t2u3-v4w5x", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "prod-node-05", "cpu": "95m", "memory": "195Mi"},
        {"name": "inventory-service-9r0s1t2u3-y6z7a", "ready": "1/1", "status": "Running", "restarts": 0, "age": "5d", "node": "prod-node-09", "cpu": "92m", "memory": "190Mi"},
        {"name": "storefront-api-8b9c0d1e2-f3g4h", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "prod-node-05", "cpu": "10m", "memory": "128Mi"},
        {"name": "storefront-api-8b9c0d1e2-i5j6k", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "prod-node-03", "cpu": "8m", "memory": "125Mi"},
        {"name": "payment-service-5l6m7n8o9-p0q1r", "ready": "1/1", "status": "Running", "restarts": 0, "age": "6d", "node": "prod-node-09", "cpu": "180m", "memory": "310Mi"},
        {"name": "cart-service-3s4t5u6v7-w8x9y", "ready": "1/1", "status": "Running", "restarts": 0, "age": "2d", "node": "prod-node-05", "cpu": "115m", "memory": "248Mi"},
        {"name": "recommendation-service-1z2a3b4c5-d6e7f", "ready": "1/1", "status": "Running", "restarts": 0, "age": "4d", "node": "prod-node-07", "cpu": "200m", "memory": "512Mi"},
        {"name": "frontend-8g9h0i1j2-k3l4m", "ready": "1/1", "status": "Running", "restarts": 0, "age": "3d", "node": "prod-node-03", "cpu": "55m", "memory": "128Mi"},
    ],
    "monitoring": [
        {"name": "prometheus-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "prod-node-05", "cpu": "450m", "memory": "2.1Gi"},
        {"name": "grafana-5n6o7p8q9-r0s1t", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "prod-node-09", "cpu": "85m", "memory": "256Mi"},
        {"name": "alertmanager-0", "ready": "1/1", "status": "Running", "restarts": 0, "age": "7d", "node": "prod-node-07", "cpu": "30m", "memory": "64Mi"},
    ],
}

KUBECTL_POD_DETAILS = {
    "order-processing-service-6a7b8c9d0-x1y2z": {
        "name": "order-processing-service-6a7b8c9d0-x1y2z", "namespace": "default",
        "labels": {"app": "order-processing-service", "version": "v3.8.3"},
        "status": {"phase": "Running", "startTime": "2026-02-02T10:00:00Z",
                   "conditions": [{"type": "Ready", "status": "True"}, {"type": "ContainersReady", "status": "True"}]},
        "containers": [{"name": "order-processing", "image": "registry.internal/order-processing-service:v3.8.3",
                        "state": "Running", "ready": True,
                        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
                        "usage": {"cpu": "150m", "memory": "312Mi"}}],
        "events": [{"type": "Normal", "reason": "Scheduled", "message": "Successfully assigned", "age": "5d"},
                   {"type": "Normal", "reason": "Started", "message": "Started container order-processing", "age": "5d"}],
    },
}

KUBECTL_EVENTS = {
    "default": [
        {"type": "Normal", "reason": "Scheduled", "object": "pod/order-processing-service-6a7b8c9d0-x1y2z", "message": "Successfully assigned", "age": "5d"},
        {"type": "Normal", "reason": "Started", "object": "pod/order-processing-service-6a7b8c9d0-x1y2z", "message": "Started container", "age": "5d"},
        {"type": "Normal", "reason": "Scheduled", "object": "pod/storefront-api-8b9c0d1e2-f3g4h", "message": "Successfully assigned", "age": "3d"},
        {"type": "Normal", "reason": "Started", "object": "pod/storefront-api-8b9c0d1e2-f3g4h", "message": "Started container", "age": "3d"},
    ],
    "monitoring": [
        {"type": "Normal", "reason": "Started", "object": "pod/prometheus-0", "message": "Started container prometheus", "age": "7d"},
    ],
}

KUBECTL_LOGS = {
    "order-processing-service-6a7b8c9d0-x1y2z": {
        "order-processing": [
            "2026-02-07T13:40:00Z INFO  Processing batch batch-20260207-1340 with 234 orders (payload: 6.8MB)",
            "2026-02-07T13:40:01Z INFO  gRPC stream received: batch-20260207-1340, bytes_received=4194304, status=OK",
            "2026-02-07T13:40:01Z DEBUG protobuf.Unmarshal: success, orders_parsed=234, fields_absent=[47]",
            "2026-02-07T13:40:02Z INFO  Batch batch-20260207-1340: 0/234 orders have hold_for_review=true. Auto-approving.",
            "2026-02-07T13:40:02Z INFO  Dispatching webhook to ShipCo: batch=batch-20260207-1340",
            "2026-02-07T13:42:01Z INFO  gRPC stream received: batch-20260207-1342, bytes_received=4194304, status=OK",
            "2026-02-07T13:42:02Z INFO  Batch batch-20260207-1342: 0/613 orders have hold_for_review=true. Auto-approving.",
            "2026-02-07T13:43:01Z INFO  gRPC stream received: batch-20260207-1343-small, bytes_received=348160, status=OK",
            "2026-02-07T13:43:01Z INFO  Batch batch-20260207-1343-small: 4/12 orders have hold_for_review=true. Routing 4 to review.",
            "2026-02-07T13:45:00Z WARN  Batch batch-20260207-1340 re-entered pipeline via retry.",
            "2026-02-07T13:45:01Z INFO  Dispatching webhook to ShipCo: batch=batch-20260207-1340 (retry)",
        ],
    },
    "inventory-service-9r0s1t2u3-v4w5x": {
        "inventory": [
            "2026-02-07T13:40:03Z INFO  Stock reservation: batch-20260207-1340, 234 items reserved",
            "2026-02-07T13:45:02Z WARN  Stock reservation: batch-20260207-1340 (duplicate), stock going NEGATIVE for 89 SKUs",
            "2026-02-07T13:47:02Z ERROR Stock NEGATIVE for 847 SKUs. Max negative: -234 (ELEC-TV-55-SAM)",
            "2026-02-07T13:47:03Z CRIT  Circuit breaker threshold exceeded: 847 > 50. Reporting UNHEALTHY.",
        ],
    },
    "storefront-api-8b9c0d1e2-f3g4h": {
        "storefront": [
            "2026-02-07T13:47:03Z ERROR Circuit breaker OPEN for inventory-service. Returning 503.",
            "2026-02-07T13:47:04Z INFO  Draining in-flight requests. 34 requests returned 503.",
        ],
    },
    "batch-builder-4d5e6f7g8-h9i0j": {
        "batch-builder": [
            "2026-02-07T13:39:59Z INFO  Building batch batch-20260207-1340: 234 orders, serialized size=6841344 bytes (6.52MB)",
            "2026-02-07T13:40:00Z DEBUG gRPC stream send: batch-20260207-1340, bytes_sent=6841344, status=OK",
            "2026-02-07T13:41:59Z INFO  Building batch batch-20260207-1342: 613 orders, serialized size=5242880 bytes (5.0MB)",
            "2026-02-07T13:43:00Z INFO  Building batch batch-20260207-1343-small: 12 orders, serialized size=348160 bytes (340KB)",
            "2026-02-07T13:43:00Z DEBUG gRPC stream send: batch-20260207-1343-small, bytes_sent=348160, status=OK",
        ],
    },
}

CLOUDWATCH_METRICS = {
    "Custom/Fulfillment": {
        "WebhookDispatchRate": {
            "label": "WebhookDispatchRate",
            "datapoints": [
                {"timestamp": "2026-02-07T13:00:00Z", "average": 8.0, "unit": "Count/min"},
                {"timestamp": "2026-02-07T13:15:00Z", "average": 12.0, "unit": "Count/min"},
                {"timestamp": "2026-02-07T13:30:00Z", "average": 15.0, "unit": "Count/min"},
                {"timestamp": "2026-02-07T13:45:00Z", "average": 28.0, "unit": "Count/min"},
                {"timestamp": "2026-02-07T14:00:00Z", "average": 0.0, "unit": "Count/min"},
            ],
            "note": "Spike at 13:45 from duplicate dispatches, then 0 after webhook kill switch.",
        },
    },
    "Custom/Inventory": {
        "NegativeStockSKUs": {
            "label": "NegativeStockSKUs",
            "datapoints": [
                {"timestamp": "2026-02-07T13:00:00Z", "average": 0, "unit": "Count"},
                {"timestamp": "2026-02-07T13:15:00Z", "average": 0, "unit": "Count"},
                {"timestamp": "2026-02-07T13:30:00Z", "average": 0, "unit": "Count"},
                {"timestamp": "2026-02-07T13:45:00Z", "average": 89, "unit": "Count"},
                {"timestamp": "2026-02-07T14:00:00Z", "average": 847, "unit": "Count"},
            ],
        },
    },
    "AWS/ECS": {
        "CPUUtilization": {
            "label": "CPUUtilization",
            "datapoints": [
                {"timestamp": "2026-02-07T13:00:00Z", "average": 38.2, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:15:00Z", "average": 39.5, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:30:00Z", "average": 41.0, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:45:00Z", "average": 42.3, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:00:00Z", "average": 35.1, "unit": "Percent"},
            ],
        },
        "MemoryUtilization": {
            "label": "MemoryUtilization",
            "datapoints": [
                {"timestamp": "2026-02-07T13:00:00Z", "average": 58.2, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:15:00Z", "average": 58.5, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:30:00Z", "average": 59.0, "unit": "Percent"},
                {"timestamp": "2026-02-07T13:45:00Z", "average": 59.3, "unit": "Percent"},
                {"timestamp": "2026-02-07T14:00:00Z", "average": 56.1, "unit": "Percent"},
            ],
            "note": "Memory usage DROPPED 2-3% after tcp_wmem reduction 2 weeks ago.",
        },
    },
}

CLOUDWATCH_ALARMS = [
    {"name": "storefront-circuit-breaker", "state": "ALARM", "metric": "Custom/Inventory/NegativeStockSKUs", "threshold": "> 50", "period": "1 minute",
     "description": "Inventory negative stock SKUs exceeds threshold", "last_updated": "2026-02-07T13:47:00Z"},
    {"name": "fulfillment-duplicate-batch", "state": "ALARM", "metric": "Custom/Fulfillment/DuplicateBatchCount", "threshold": "> 0", "period": "1 minute",
     "description": "Duplicate batch IDs detected in webhook log", "last_updated": "2026-02-07T13:49:00Z"},
    {"name": "inventory-latency-p99", "state": "OK", "metric": "Custom/Inventory/Latency-p99", "threshold": "> 1000ms", "period": "5 minutes",
     "description": "Inventory service P99 latency", "last_updated": "2026-02-07T14:00:00Z"},
    {"name": "grpc-error-rate", "state": "OK", "metric": "Custom/gRPC/ErrorRate", "threshold": "> 1%", "period": "5 minutes",
     "description": "gRPC error rate across service mesh", "last_updated": "2026-02-07T14:00:00Z",
     "note": "This alarm is OK because gRPC returns status OK even when TCP truncation occurs."},
    {"name": "payment-error-rate", "state": "OK", "metric": "Custom/Payment/ErrorRate", "threshold": "> 5%", "period": "5 minutes"},
    {"name": "rds-cpu-high", "state": "OK", "metric": "AWS/RDS/CPUUtilization", "threshold": "> 80%", "period": "5 minutes"},
]

DATADOG_TRACES = {
    "order-processing-service": {
        "traces": [
            {"trace_id": "opr-trace-001", "service": "order-processing-service", "resource": "ProcessBatch",
             "status": "ok", "duration_ms": 1230, "start": "2026-02-07T13:40:00.000Z",
             "spans_collected": 5, "spans_expected": 5,
             "spans": [
                 {"span_id": "s1", "service": "order-processing-service", "operation": "grpc.recv", "duration_ms": 890, "status": "ok"},
                 {"span_id": "s2", "service": "order-processing-service", "operation": "protobuf.unmarshal", "duration_ms": 45, "status": "ok"},
                 {"span_id": "s3", "service": "order-processing-service", "operation": "business_rules", "duration_ms": 120, "status": "ok"},
                 {"span_id": "s4", "service": "order-processing-service", "operation": "webhook.dispatch", "duration_ms": 340, "status": "ok"},
                 {"span_id": "s5", "service": "order-processing-service", "operation": "inventory.reserve", "duration_ms": 89, "status": "ok"},
             ],
             "note": "All spans show OK. Protobuf unmarshal succeeded (but silently lost trailing fields)."},
        ],
    },
    "fulfillment-gateway": {
        "traces": [
            {"trace_id": "fg-trace-001", "service": "fulfillment-gateway", "resource": "POST /webhook/shipco",
             "status": "ok", "duration_ms": 340, "start": "2026-02-07T13:40:02.000Z",
             "spans_collected": 3, "spans_expected": 3,
             "spans": [
                 {"span_id": "s6", "service": "fulfillment-gateway", "operation": "http.request", "duration_ms": 340, "status": "ok"},
                 {"span_id": "s7", "service": "fulfillment-gateway", "operation": "serialize", "duration_ms": 12, "status": "ok"},
                 {"span_id": "s8", "service": "fulfillment-gateway", "operation": "partner.post", "duration_ms": 310, "status": "ok"},
             ]},
        ],
    },
}

DATADOG_TRACE_DETAILS = {
    "opr-trace-001": DATADOG_TRACES["order-processing-service"]["traces"][0],
    "fg-trace-001": DATADOG_TRACES["fulfillment-gateway"]["traces"][0],
}

DATADOG_METRICS = {
    "avg:grpc.server.msg.received_size{service:order-processing-service}": {
        "status": "ok",
        "series": [
            {"pointlist": [[1738929600000, 2100000], [1738929900000, 2300000], [1738930200000, 4194304], [1738930500000, 4194304], [1738930800000, 4194304]],
             "metric": "grpc.server.msg.received_size", "tag_set": ["service:order-processing-service"], "unit": "bytes"},
        ],
        "note": "Received message size capped at exactly 4194304 (4MB) for large batches. Client sends 6.8MB.",
    },
}

CI_RUNS = [
    {"id": 10100, "repo": "infra/ansible-playbooks", "workflow": "apply-tcp-tuning", "branch": "main", "commit": "a1b2c3d",
     "author": "kevin.park", "status": "success", "conclusion": "success", "started": "2026-01-24T10:30:00Z", "completed": "2026-01-24T10:47:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "30s"},
        {"name": "dry-run", "status": "completed", "conclusion": "success", "duration": "2m10s"},
        {"name": "apply", "status": "completed", "conclusion": "success", "duration": "8m05s"},
     ],
     "note": "No integration tests with gRPC streaming payloads."},
    {"id": 10200, "repo": "services/order-processing-service", "workflow": "ci", "branch": "main", "commit": "p3q4r5s",
     "author": "dan.rogers", "status": "success", "conclusion": "success", "started": "2026-02-01T09:30:00Z", "completed": "2026-02-01T09:48:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "25s"},
        {"name": "unit-tests", "status": "completed", "conclusion": "success", "duration": "3m20s"},
        {"name": "integration-tests", "status": "completed", "conclusion": "success", "duration": "5m45s"},
        {"name": "build-image", "status": "completed", "conclusion": "success", "duration": "2m00s"},
     ]},
    {"id": 10300, "repo": "services/fulfillment-gateway", "workflow": "ci", "branch": "main", "commit": "h7i8j9k",
     "author": "priya.sharma", "status": "success", "conclusion": "success", "started": "2026-01-22T14:00:00Z", "completed": "2026-01-22T14:18:00Z",
     "jobs": [
        {"name": "lint", "status": "completed", "conclusion": "success", "duration": "20s"},
        {"name": "unit-tests", "status": "completed", "conclusion": "success", "duration": "2m30s"},
        {"name": "integration-tests", "status": "completed", "conclusion": "success", "duration": "4m10s"},
        {"name": "build-image", "status": "completed", "conclusion": "success", "duration": "1m50s"},
     ]},
]

CI_RUN_LOGS = {
    10100: """=== apply-tcp-tuning / lint ===
[10:30:05] Checking YAML syntax... OK
[10:30:30] Lint passed.

=== apply-tcp-tuning / dry-run ===
[10:31:00] Running ansible-playbook --check tcp_tuning.yml...
[10:32:00] TASK [Apply sysctl settings] changed
[10:32:05] net.ipv4.tcp_wmem: 4096 87380 16777216 -> 4096 87380 4194304
[10:32:05] net.ipv4.tcp_rmem: 4096 87380 16777216 -> 4096 87380 4194304
[10:33:10] Dry run complete. 12 hosts, 2 changes per host.

=== apply-tcp-tuning / apply ===
[10:34:00] Running ansible-playbook tcp_tuning.yml...
[10:35:00] TASK [Apply sysctl settings] changed on prod-node-01
[10:35:30] TASK [Apply sysctl settings] changed on prod-node-02
[10:36:00] TASK [Apply sysctl settings] changed on prod-node-03
[10:36:30] ... (9 more nodes)
[10:38:00] TASK [Verify settings] ok on all hosts
[10:38:05] All hosts verified: tcp_wmem max = 4194304, tcp_rmem max = 4194304
[10:38:30] Apply complete. 12 hosts changed.

NOTE: No integration tests with actual gRPC streaming traffic.
""",
    10200: """=== ci / lint ===
[09:30:05] golangci-lint run... OK

=== ci / unit-tests ===
[09:30:40] go test ./...
[09:33:00] ok  order-processing/handlers    1.4s
[09:34:00] ok  order-processing/batch       2.3s
[09:34:00] All tests passed. Coverage: 76.2%

=== ci / integration-tests ===
[09:34:10] Starting test containers...
[09:34:40] Containers ready.
[09:40:25] 28/28 integration tests passed.

=== ci / build-image ===
[09:40:30] Building Docker image...
[09:42:30] Image built: registry.internal/order-processing-service:p3q4r5s
""",
}

STATUSPAGE_STATUS = {
    "page": {"name": "Acme Commerce Platform", "url": "https://status.acme-commerce.com"},
    "status": {"indicator": "major", "description": "Major System Outage"},
    "components": [
        {"name": "Storefront", "status": "major_outage", "updated_at": "2026-02-07T13:48:00Z"},
        {"name": "Order Processing", "status": "degraded_performance", "updated_at": "2026-02-07T13:50:00Z"},
        {"name": "Payment Processing", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "Cart Service", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
        {"name": "API", "status": "operational", "updated_at": "2026-02-07T14:00:00Z"},
    ],
}

STATUSPAGE_INCIDENTS = [
    {"id": "inc-2026-0207", "name": "Storefront Outage - Circuit Breaker Tripped", "status": "investigating",
     "created_at": "2026-02-07T13:48:00Z",
     "impact": "major", "components": ["Storefront", "Order Processing"],
     "updates": [
         {"status": "investigating", "body": "Storefront is offline. Circuit breaker tripped on inventory service. Investigating.", "created_at": "2026-02-07T13:48:00Z"},
     ]},
]

ONCALL_SCHEDULE = {
    "current": {
        "platform": {"primary": {"name": "Alicia Chen", "username": "alicia.chen", "start": "2026-02-03T09:00:00Z", "end": "2026-02-10T09:00:00Z"},
                     "secondary": {"name": "Frank Martinez", "username": "frank.martinez"}},
        "backend": {"primary": {"name": "Dan Rogers", "username": "dan.rogers", "start": "2026-02-03T09:00:00Z", "end": "2026-02-10T09:00:00Z"},
                    "secondary": {"name": "Priya Sharma", "username": "priya.sharma"}},
    },
    "rotation": [
        {"team": "platform", "week_of": "2026-01-27", "primary": "kevin.park", "secondary": "alicia.chen"},
        {"team": "platform", "week_of": "2026-02-03", "primary": "alicia.chen", "secondary": "frank.martinez"},
        {"team": "platform", "week_of": "2026-02-10", "primary": "frank.martinez", "secondary": "kevin.park"},
        {"team": "backend", "week_of": "2026-01-27", "primary": "priya.sharma", "secondary": "dan.rogers"},
        {"team": "backend", "week_of": "2026-02-03", "primary": "dan.rogers", "secondary": "priya.sharma"},
    ],
}

TERRAFORM_RESOURCES = [
    {"type": "aws_instance", "name": "prod_nodes", "module": "compute", "provider": "aws", "status": "applied"},
    {"type": "aws_rds_cluster", "name": "orders_db", "module": "rds", "provider": "aws", "status": "applied"},
    {"type": "aws_elasticache_replication_group", "name": "redis", "module": "redis", "provider": "aws", "status": "applied"},
    {"type": "aws_eks_cluster", "name": "main", "module": "eks", "provider": "aws", "status": "applied"},
    {"type": "aws_s3_bucket", "name": "assets", "module": "storage", "provider": "aws", "status": "applied"},
    {"type": "aws_cloudfront_distribution", "name": "cdn", "module": "cdn", "provider": "aws", "status": "applied"},
    {"type": "aws_lb", "name": "public", "module": "networking", "provider": "aws", "status": "applied"},
]

TERRAFORM_STATE = {
    "aws_instance.prod_nodes": {
        "type": "aws_instance", "name": "prod_nodes",
        "attributes": {
            "instance_type": "c5.2xlarge", "count": 12,
            "ami": "ami-0abcdef1234567890",
            "user_data_note": "Includes sysctl tuning via ansible post-provisioning. See ansible/roles/tcp_tuning/.",
        },
    },
    "aws_rds_cluster.orders_db": {
        "type": "aws_rds_cluster", "name": "orders_db",
        "attributes": {
            "engine": "aurora-postgresql", "engine_version": "15.4",
            "cluster_identifier": "prod-orders-db",
        },
    },
}

DOCKER_REGISTRY_TAGS = {
    "order-processing-service": [
        {"tag": "v3.8.3", "digest": "sha256:ops383abc", "pushed": "2026-02-01T10:00:00Z", "size": "48.1 MB"},
        {"tag": "v3.8.2", "digest": "sha256:ops382def", "pushed": "2026-01-23T14:30:00Z", "size": "48.0 MB"},
    ],
    "fulfillment-gateway": [
        {"tag": "v1.9.4", "digest": "sha256:fg194abc", "pushed": "2026-01-22T14:00:00Z", "size": "35.2 MB"},
    ],
    "inventory-service": [
        {"tag": "v2.4.1", "digest": "sha256:inv241abc", "pushed": "2026-01-20T09:00:00Z", "size": "38.4 MB"},
    ],
    "storefront-api": [
        {"tag": "v2.1.1", "digest": "sha256:sf211abc", "pushed": "2026-01-28T11:00:00Z", "size": "28.3 MB"},
    ],
}

DOCKER_REGISTRY_MANIFESTS = {}

# ---------------------------------------------------------------------------
# Tool definitions
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
        Tool(name="jira_search", description="Search Jira tickets by query string.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "JQL or text search query"},
                 "max_results": {"type": "integer", "default": 20},
             }, "required": ["query"]}),
        Tool(name="jira_get_issue", description="Get full details for a Jira issue.",
             inputSchema={"type": "object", "properties": {
                 "issue_id": {"type": "string", "description": "Jira issue key"},
             }, "required": ["issue_id"]}),
        Tool(name="jira_list_sprints", description="List current and recent sprints.",
             inputSchema={"type": "object", "properties": {
                 "state": {"type": "string", "enum": ["active", "closed", "future"]},
             }}),

        # --- Confluence / Wiki ---
        Tool(name="wiki_search", description="Search Confluence/wiki pages by query.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"}, "limit": {"type": "integer", "default": 10},
             }, "required": ["query"]}),
        Tool(name="wiki_get_page", description="Get full content of a wiki page by ID.",
             inputSchema={"type": "object", "properties": {
                 "page_id": {"type": "string"},
             }, "required": ["page_id"]}),

        # --- kubectl ---
        Tool(name="kubectl_get_pods", description="List pods in a Kubernetes namespace.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "default": "default"},
             }, "required": ["namespace"]}),
        Tool(name="kubectl_describe_pod", description="Get detailed information about a specific pod.",
             inputSchema={"type": "object", "properties": {
                 "pod_name": {"type": "string"},
             }, "required": ["pod_name"]}),
        Tool(name="kubectl_get_events", description="List Kubernetes events in a namespace.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "default": "default"},
             }, "required": ["namespace"]}),
        Tool(name="kubectl_logs", description="Get logs from a pod/container.",
             inputSchema={"type": "object", "properties": {
                 "pod_name": {"type": "string"},
                 "container": {"type": "string"},
                 "tail": {"type": "integer", "default": 100},
             }, "required": ["pod_name"]}),

        # --- AWS CloudWatch ---
        Tool(name="cloudwatch_get_metrics", description="Get CloudWatch metric data.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string"}, "metric": {"type": "string"},
             }, "required": ["namespace", "metric"]}),
        Tool(name="cloudwatch_list_alarms", description="List all CloudWatch alarms.",
             inputSchema={"type": "object", "properties": {}}),

        # --- Datadog APM ---
        Tool(name="datadog_list_traces", description="List recent traces for a service.",
             inputSchema={"type": "object", "properties": {
                 "service": {"type": "string"}, "status": {"type": "string", "enum": ["error", "ok"]},
             }, "required": ["service"]}),
        Tool(name="datadog_get_trace", description="Get detailed trace information.",
             inputSchema={"type": "object", "properties": {
                 "trace_id": {"type": "string"},
             }, "required": ["trace_id"]}),
        Tool(name="datadog_query_metrics", description="Query Datadog metrics.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"},
             }, "required": ["query"]}),

        # --- CI/CD ---
        Tool(name="ci_list_runs", description="List recent CI/CD workflow runs.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"},
             }}),
        Tool(name="ci_get_run_logs", description="Get detailed logs for a CI/CD workflow run.",
             inputSchema={"type": "object", "properties": {
                 "run_id": {"type": "integer"},
             }, "required": ["run_id"]}),

        # --- Status Page ---
        Tool(name="statuspage_get_status", description="Get current system status.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="statuspage_list_incidents", description="List recent status page incidents.",
             inputSchema={"type": "object", "properties": {}}),

        # --- On-Call ---
        Tool(name="oncall_who_is_on_call", description="Show who is currently on-call.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="oncall_get_schedule", description="Get the full on-call rotation schedule.",
             inputSchema={"type": "object", "properties": {
                 "team": {"type": "string"},
             }}),

        # --- Terraform ---
        Tool(name="terraform_show_state", description="Show Terraform state for a specific resource.",
             inputSchema={"type": "object", "properties": {
                 "resource": {"type": "string"},
             }, "required": ["resource"]}),
        Tool(name="terraform_list_resources", description="List all Terraform-managed resources.",
             inputSchema={"type": "object", "properties": {}}),

        # --- Docker Registry ---
        Tool(name="registry_list_tags", description="List image tags for a repository.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"},
             }, "required": ["repo"]}),
        Tool(name="registry_get_manifest", description="Get the manifest for a specific image tag.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"}, "tag": {"type": "string"},
             }, "required": ["repo", "tag"]}),
    ]


def _text(data) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _call_server(service: str, method: str, endpoint: str, params: dict) -> dict:
    """Route a call to the appropriate evidence server.

    For logs, metrics, and sentry: merges static (planted) evidence with
    live traffic data from SQLite. Static evidence appears as "historical"
    entries; SQLite has real-time data the simulator is continuously generating.
    """
    db = str(TRAFFIC_DB)

    # --- Logs: merge static + live ---
    if service == "logs":
        if endpoint == "/services":
            # Combine static service list with live services
            static = SERVERS.get("logs")
            static_resp = static.make_request(method, endpoint, params) if static else None
            static_services = static_resp.body.get("services", []) if static_resp and static_resp.status == 200 else []
            # Get live services from SQLite
            live = db_backed.query_logs(db, limit=0)  # just to check
            return _add_verbose_metadata({"services": static_services, "note": "Live traffic data is also available"})

        if endpoint.startswith("/services/") and endpoint.endswith("/logs"):
            svc = endpoint.split("/")[2]
            # Get live data from SQLite
            live_result = db_backed.query_logs(
                db,
                service=svc,
                level=params.get("level", ""),
                grep=params.get("grep", params.get("search", "")),
                since=params.get("since", ""),
                limit=int(params.get("limit", 50)),
            )
            # Also get static evidence
            static = SERVERS.get("logs")
            if static:
                static_resp = static.make_request(method, endpoint, params)
                if static_resp and static_resp.status == 200:
                    static_entries = static_resp.body.get("entries", [])
                    # Merge: static first (historical), then live (recent)
                    combined = static_entries + live_result.get("entries", [])
                    # Sort by timestamp descending
                    combined.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
                    return _add_verbose_metadata({
                        "service": svc,
                        "entries": combined[:int(params.get("limit", 50))],
                        "total": len(combined),
                        "has_more": live_result.get("has_more", False),
                    })
            return _add_verbose_metadata(live_result)

        if endpoint == "/search":
            query = params.get("query", params.get("q", ""))
            live_result = db_backed.search_logs(db, query, limit=int(params.get("limit", 20)))
            return _add_verbose_metadata(live_result)

    # --- Metrics: live data preferred, static as fallback ---
    if service == "prometheus":
        if endpoint == "/query":
            q = params.get("q", params.get("query", ""))
            # Try live data first
            live_result = db_backed.query_metrics(db, q)
            if "result" in live_result:
                return _add_verbose_metadata(live_result)
            # Fall back to static evidence
            static = SERVERS.get("prometheus")
            if static:
                static_resp = static.make_request(method, endpoint, params)
                if static_resp and static_resp.status == 200:
                    return _add_verbose_metadata(static_resp.body if isinstance(static_resp.body, dict) else {"data": static_resp.body})
            return _add_verbose_metadata(live_result)

        if endpoint == "/metrics":
            # Merge static + live metric names
            live = db_backed.list_metrics(db)
            static = SERVERS.get("prometheus")
            if static:
                static_resp = static.make_request(method, endpoint, params)
                if static_resp and static_resp.status == 200:
                    static_metrics = static_resp.body.get("metrics", [])
                    live_metrics = live.get("metrics", [])
                    # Combine, dedup by name
                    seen = set()
                    combined = []
                    for m in live_metrics + static_metrics:
                        name = m.get("name", "")
                        if name not in seen:
                            seen.add(name)
                            combined.append(m)
                    return _add_verbose_metadata({"metrics": combined})
            return _add_verbose_metadata(live)

    # --- Sentry: merge static + live ---
    if service == "sentry":
        if endpoint == "/projects":
            live = db_backed.list_sentry_projects(db)
            static = SERVERS.get("sentry")
            if static:
                static_resp = static.make_request(method, endpoint, params)
                if static_resp and static_resp.status == 200:
                    static_projects = static_resp.body.get("projects", [])
                    live_projects = live.get("projects", [])
                    seen = set()
                    combined = []
                    for p in static_projects + live_projects:
                        name = p.get("name", "")
                        if name not in seen:
                            seen.add(name)
                            combined.append(p)
                    return _add_verbose_metadata({"projects": combined})
            return _add_verbose_metadata(live)

        if endpoint == "/issues":
            project = params.get("project", "")
            live = db_backed.query_sentry(db, project=project)
            static = SERVERS.get("sentry")
            if static:
                static_resp = static.make_request(method, endpoint, params)
                if static_resp and static_resp.status == 200:
                    static_issues = static_resp.body.get("issues", [])
                    live_issues = live.get("issues", [])
                    return _add_verbose_metadata({
                        "issues": static_issues + live_issues,
                        "total": len(static_issues) + len(live_issues),
                    })
            return _add_verbose_metadata(live)

    # --- Default: static evidence server ---
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

    # --- Slack (LLM-powered for post_message) ---
    if name == "slack_list_channels":
        return _text(_call_server("slack", "GET", "/channels", {}))
    if name == "slack_read_channel":
        ch = arguments.get("channel", "").lstrip("#")
        # Use LLM_SLACK to get conversation history injected
        response = LLM_SLACK.make_request("GET", f"/channels/{ch}/messages", {
            "limit": str(arguments.get("limit", 50)),
            "cursor": str(arguments.get("cursor", 0)),
        })
        return _text(_add_verbose_metadata(response.body if isinstance(response.body, dict) else {"data": response.body}))
    if name == "slack_search":
        return _text(_call_server("slack", "GET", "/search", {
            "query": arguments.get("query", ""),
            "limit": str(arguments.get("limit", 20)),
        }))
    if name == "slack_post_message":
        # Use LLM coworker engine for responses
        ch = arguments.get("channel", "#incidents").lstrip("#")
        text = arguments.get("text", "")
        response = LLM_SLACK.make_request("POST", f"/channels/{ch}/messages", {"text": text})
        return _text(response.body)

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
        return _text(_add_verbose_metadata({"label": metric, "datapoints": [], "message": f"No data found for {ns}/{metric}."}))

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
        return _text(_add_verbose_metadata({"service": service, "traces": summary}))

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
        return _text(_add_verbose_metadata({"error": f"Resource not found: {resource}. Use terraform_list_resources."}))

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
