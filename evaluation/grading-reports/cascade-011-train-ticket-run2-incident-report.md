# Incident Report: Storefront Outage & Duplicate Fulfillment Dispatches

**Severity**: SEV-1
**Date**: 2026-02-09
**Duration**: ~45+ minutes (ongoing at time of report)
**Incident Commander**: On-call engineer
**Status**: Root cause identified, remediation pending

---

## Executive Summary

The storefront circuit breaker tripped, taking the customer-facing site offline. Three fulfillment partners (ShipCo, FastFreight, PackLogic) received 23 duplicate order batch dispatches and shipped double quantities, causing 847 SKUs to go to negative stock levels.

**Root cause**: A TCP buffer tuning change on Jan 24 (INFRA-3101) silently truncated large gRPC protobuf messages, dropping the `hold_for_review` field from order batches. This, combined with a recent change to timestamp-based idempotency keys (FULFILL-890), created a cascade of auto-approved orders, duplicate fulfillment dispatches, negative inventory, and ultimately the circuit breaker trip.

---

## Timeline

| Time (UTC) | Event |
|---|---|
| 2026-01-22 | FULFILL-895: Batch retry with exponential backoff enabled (`batch_retry_enabled` flag) — priya.sharma |
| 2026-01-23 | FULFILL-890: Webhook idempotency keys changed from UUID to timestamp format (`idempotency_key_format_v2` flag) — dan.rogers |
| 2026-01-24 | INFRA-3101: TCP buffer tuning applied via ansible. `tcp_wmem`/`tcp_rmem` max reduced from 16MB to 4MB across 12 prod nodes. Tested only with HTTP/1.1 load test — kevin.park |
| 2026-02-01 | order-processing-service CI build by dan.rogers (image: `p3q4r5s`) |
| 2026-02-05 | OPS-847 filed by dan.rogers: "Some order batches missing hold_for_review protobuf field. Only seen on large batches (>100 orders)." Could not reproduce locally. |
| 2026-02-07 13:47 | **PD-78901**: Alert triggered — inventory-service returning negative stock for 847 SKUs. Circuit breaker OPEN. Acknowledged by alicia. |
| 2026-02-07 13:49 | **PD-78902**: Alert triggered — 23 duplicate batch dispatches detected. 3 fulfillment partners affected. Acknowledged by priya. |
| 2026-02-09 ~14:18 | On-call engineer joins investigation, begins root cause analysis. |
| 2026-02-09 14:20 | Root cause identified and posted to #incidents. |
| 2026-02-09 14:21 | Remediation plan proposed, awaiting team execution. |

---

## Impact

### Customer Impact
- **Storefront completely offline** — zero customer traffic since circuit breaker tripped
- All customer-facing functionality (browsing, cart, checkout) unavailable

### Business Impact
- **23 duplicate batch dispatches** to 3 fulfillment partners
- Partners have already shipped double quantities for affected orders
- **847 SKUs with negative stock** levels (e.g., SKU ELEC-TV-55-SAM went from 412 to -234 units)
- Financial impact from duplicate shipments and inventory discrepancies
- Revenue loss from storefront downtime

### Operational Impact
- Order hold-for-review rate dropped from normal 31% to 0% — all orders auto-approving without human review
- Order processing service returning 500/502/503 errors
- Status page showing "Major System Outage" for Storefront, "Degraded Performance" for Order Processing

---

## Root Cause Analysis

### Primary Cause: TCP Buffer Truncation of gRPC Messages

On Jan 24, INFRA-3101 reduced the TCP socket buffer maximum from 16MB to 4MB across all 12 production nodes to reclaim ~2GB RAM per host. The change was validated with HTTP/1.1 load testing but **not tested with gRPC streaming payloads**.

The order-processing pipeline uses gRPC streaming to send protobuf-serialized order batches. Per the architecture wiki (WIKI-2001), batch sizes range from 500KB (small) to **8MB+ (large seasonal batches)**. With the TCP write buffer capped at 4MB, large messages are silently truncated at the kernel level.

**Key metrics confirming truncation:**
- `grpc_client_msg_sent_size_bytes_p99` = 6,993,276 bytes (~7MB) — what the client sends
- `grpc_server_msg_received_size_bytes_p99` = 4,194,304 bytes (exactly 4MB) — what the server receives
- `net.ipv4.tcp_wmem_max` = 4,194,304 bytes — the TCP buffer cap

The ~3MB difference is lost data.

### Why `hold_for_review` Was Lost

The `hold_for_review` field is **field #47** in the Order protobuf schema (an `optional bool`). Being near the end of the ~50-field schema, it falls in the truncated portion of large messages. When a protobuf field is absent:
- `Protobuf.Unmarshal` returns **no error** (by design — protobuf handles missing fields gracefully for forward compatibility)
- Missing `bool` fields default to `false`
- gRPC returns status **OK** (the transport layer considers the delivery successful)

This explains the "significant silence" — zero gRPC errors, zero protobuf errors, but critical business logic silently broken.

### Contributing Factor: Timestamp-Based Idempotency Keys

FULFILL-890 (Jan 23) changed webhook idempotency keys from UUID to timestamp format for "better traceability." When combined with FULFILL-895's retry logic (Jan 22), each retry attempt generates a **new timestamp**, producing a **new idempotency key**. Fulfillment partners cannot deduplicate because every dispatch appears unique.

**Metrics confirming:**
- `webhook_idempotency_key_collisions` = 0 (keys never collide because timestamps are unique)
- `webhook_retry_attempts_total` = 23 retries, each with a new key
- `webhook_duplicate_dispatches_total` = 23 (matches partner reports exactly)

### The Cascade

```
TCP buffer 16MB → 4MB (Jan 24)
    ↓
Large protobuf messages truncated at 4MB
    ↓
hold_for_review field (#47) silently dropped → defaults to false
    ↓
Order hold rate: 31% → 0% (all orders auto-approve)
    ↓
Unchecked order volume → fulfillment dispatches
    ↓
Timestamp idempotency keys + retries → 23 duplicate dispatches
    ↓
Partners ship double quantities → 847 SKUs go negative
    ↓
inventory-service returns negative stock (>50 SKU threshold)
    ↓
Storefront circuit breaker trips → SITE OFFLINE
```

### Why It Wasn't Caught Earlier

1. **TCP tuning only tested with HTTP/1.1** — gRPC uses HTTP/2 with different message framing patterns
2. **No integration tests with large gRPC payloads** (noted in CI run #10100)
3. **Protobuf silent field handling** — designed for forward compatibility, but creates silent failure mode
4. **OPS-847 couldn't be reproduced locally** — dev machines still have 16MB TCP buffers
5. **Zero gRPC/protobuf errors** — no monitoring alerts for data integrity issues at the transport layer

---

## Remediation

### Immediate Actions (Pending Execution)

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | **Revert TCP buffer settings**: Restore `tcp_wmem`/`tcp_rmem` max to `4096 87380 16777216` (16MB) via ansible playbook | kevin.park | Pending |
| 2 | **Disable `idempotency_key_format_v2`** feature flag: Revert to UUID-based idempotency keys to restore webhook deduplication | dan.rogers | Pending |
| 3 | **Contact fulfillment partners**: Notify ShipCo, FastFreight, PackLogic about 23 duplicate shipments; coordinate halt/recall where possible | priya.sharma | Pending |
| 4 | **Reconcile inventory**: After TCP fix, reprocess affected batches to correct stock levels for 847 SKUs | dan.rogers | Pending |
| 5 | **Verify circuit breaker reset**: CB auto-resets after 5 minutes once <50 SKUs have negative stock | alicia.chen | Pending |

### Short-Term Follow-ups

| # | Action | Priority |
|---|---|---|
| 1 | Set explicit gRPC `MaxRecvMsgSize` in server config (independent of TCP buffers) — recommend 16MB | High |
| 2 | Add gRPC message size monitoring: alert when received size != sent size | High |
| 3 | Add protobuf field presence validation for critical business fields (`hold_for_review`, etc.) | High |
| 4 | Fix idempotency key format: use batch ID + sequence number (deterministic, not timestamp-based) | High |
| 5 | Add integration tests for gRPC streaming with realistic payload sizes to CI pipeline | Medium |

### Long-Term Improvements

| # | Action | Priority |
|---|---|---|
| 1 | Move `hold_for_review` to early fields in protobuf schema (field ordering matters for truncation resilience) | Medium |
| 2 | Implement protobuf message checksums/integrity verification at application layer | Medium |
| 3 | Require gRPC integration testing for any infrastructure change affecting network parameters | High |
| 4 | Add chaos testing for message truncation scenarios | Low |
| 5 | Implement fulfillment partner dedup at partner API level (defense in depth) | Medium |
| 6 | Add circuit breaker dashboard with real-time hold_for_review rate monitoring | Medium |

---

## Related Tickets

| Ticket | Summary | Relevance |
|---|---|---|
| INFRA-3101 | TCP memory tuning for cluster nodes | **Primary trigger** — reduced buffers from 16MB to 4MB |
| OPS-847 | Investigate missing hold_for_review flags | **Direct symptom** — the protobuf field loss Dan noticed |
| FULFILL-890 | Refactor webhook dispatch with timestamp idempotency keys | **Contributing factor** — broke webhook deduplication |
| FULFILL-895 | Improve fulfillment retry logic with exponential backoff | **Contributing factor** — retries now create duplicates due to FULFILL-890 |
| PLAT-925 | Adjust circuit breaker threshold for inventory service | Related — circuit breaker configuration |
| PD-78901 | StorefrontCircuitBreaker: inventory-service negative stock | Active incident alert |
| PD-78902 | FulfillmentDuplicateBatch: duplicate batch IDs in webhook log | Active incident alert |

---

## Lessons Learned

1. **Infrastructure changes must be tested against all transport protocols in use.** HTTP/1.1 testing is insufficient when the critical path uses gRPC/HTTP/2 with large streaming payloads.

2. **Protobuf's silent handling of missing fields is a double-edged sword.** It provides forward compatibility but can silently corrupt business logic. Critical fields need application-level presence validation.

3. **Idempotency keys must be deterministic.** Timestamp-based keys defeat the entire purpose of idempotency when combined with retry logic. Keys should be derived from immutable batch/order identifiers.

4. **"Can't reproduce locally" is a signal, not a dead end.** When a production bug can't be reproduced in development, the difference between environments (in this case, TCP buffer sizes) is likely the cause.

5. **Zero errors doesn't mean zero problems.** The "significant silence" in gRPC error metrics masked a critical data integrity issue. Monitoring should include positive assertions (e.g., "hold_for_review rate should be ~31%") not just error counting.

---

*Report prepared: 2026-02-09*
*PagerDuty incidents: PD-78901, PD-78902*
*Status page: Major System Outage*
