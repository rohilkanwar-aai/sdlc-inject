# Incident Report: Storefront Outage & Duplicate Fulfillment Dispatches

**Severity**: SEV-1
**Duration**: 45+ minutes (ongoing at time of report)
**Date**: 2026-02-07 / Investigation: 2026-02-09
**Incident Commander**: Alicia Chen (platform on-call primary)
**Author**: On-call engineer (incident responder)

---

## Executive Summary

The storefront went offline after the inventory-service circuit breaker tripped due to 847 SKUs going negative. Three fulfillment partners (ShipCo, FastFreight, PackLogic) received 23 duplicate order batch dispatches and shipped double quantities. The root cause is a TCP buffer reduction (INFRA-3101, Jan 24) that silently truncates large gRPC protobuf messages, causing the `hold_for_review` field to be dropped. A concurrent change to timestamp-based idempotency keys (FULFILL-890, Jan 23) prevented partners from deduplicating retried webhooks.

---

## Impact

| Category | Detail |
|----------|--------|
| **Customer-facing** | Storefront completely offline; customers cannot browse or purchase |
| **Order processing** | All orders auto-approving (0% hold rate vs. normal 31%) |
| **Fulfillment** | 23 duplicate batch dispatches to 3 partners; double shipments in progress |
| **Inventory** | 847 SKUs with negative stock (e.g., ELEC-TV-55-SAM at -234) |
| **Financial** | Double-shipped inventory; partner recall/return costs pending |

---

## Timeline

| Date/Time (UTC) | Event |
|------------------|-------|
| **2026-01-22** | `batch_retry_enabled` feature flag turned on |
| **2026-01-23** | FULFILL-890 deployed: webhook idempotency keys changed from UUID to timestamp format. `idempotency_key_format_v2` and `fulfillment_webhook_async` flags enabled |
| **2026-01-24 10:30** | INFRA-3101 deployed: `apply-tcp-tuning` ansible playbook reduces `tcp_wmem`/`tcp_rmem` max from 16MB (16777216) to 4MB (4194304). Tested with HTTP/1.1 only. CI note: "No integration tests with gRPC streaming payloads" |
| **~Jan 24 onward** | Large order batches (>100 orders) begin having protobuf messages silently truncated at 4MB TCP buffer cap. `hold_for_review` (optional bool, field #47, near end of schema) is lost. Missing field defaults to `false`. `Protobuf.Unmarshal` returns no error |
| **2026-02-05 10:30** | Dan Rogers files OPS-847: "Some order batches are missing the hold_for_review protobuf field. Only seen on large batches (>100 orders). Protobuf.Unmarshal returns no error." Cannot reproduce locally (dev machines have 16MB buffers) |
| **2026-02-07 13:44** | Inventory-service begins logging NegativeStockError for multiple SKUs |
| **2026-02-07 13:47** | Circuit breaker trips: 847 negative SKUs exceed threshold of 50. PagerDuty alert PD-78901 fires. Storefront goes offline |
| **2026-02-07 13:48** | Alicia Chen acknowledges PD-78901. Status page updated to "Major System Outage" |
| **2026-02-07 13:49** | PagerDuty alert PD-78902 fires: 23 duplicate batch dispatches detected, 3 partners affected |
| **2026-02-07 13:50** | Priya Sharma acknowledges PD-78902. Order Processing status updated to "Degraded Performance" |
| **2026-02-09 ~14:18** | Incident responder joins, begins systematic investigation |
| **2026-02-09 ~14:20** | Root cause identified and posted to #incidents with full evidence chain |

---

## Root Cause Analysis

### Primary Cause: TCP Buffer Reduction Truncating gRPC Messages

**INFRA-3101** (Kevin Park, Jan 24) reduced the TCP socket buffer maximum (`net.ipv4.tcp_wmem` and `net.ipv4.tcp_rmem` third value) from 16MB to 4MB across all cluster nodes to save approximately 2GB RAM per host. The change was tested with HTTP/1.1 load tests, which passed because HTTP/1.1 messages are typically small.

However, the order-processing pipeline uses **gRPC streaming** with protobuf-serialized messages. Large order batches (>100 orders) produce protobuf messages that can exceed 4MB. With the TCP write buffer capped at 4MB, these messages are **silently truncated** at the kernel level.

The `hold_for_review` field is an **optional bool at protobuf field number 47**, positioned near the end of the serialized message schema. When messages are truncated, this field is among those lost. Because it's an optional field, `Protobuf.Unmarshal` on the receiving end **does not return an error** -- it simply uses the default value of `false`, meaning "do not hold for review."

**Result**: All orders auto-approve without human review. The `order_hold_for_review_rate` metric dropped from the normal 31% to 0%.

### Contributing Cause: Timestamp-Based Idempotency Keys

**FULFILL-890** (Dan Rogers, Jan 23) changed webhook idempotency keys from UUIDs to timestamps for better traceability. With `batch_retry_enabled` (Jan 22) active, webhook retries now generate **unique** timestamp-based keys for each attempt.

Previously, UUID-based idempotency keys ensured that if a webhook was retried, the partner would detect the duplicate and return a 409 Conflict. With timestamp keys, each retry looks like a new unique dispatch. Partners accepted all dispatches.

**Evidence from Sentry (FG-502)**: "No 409s -- partners accepted both batches because idempotency keys differed."
**Evidence from Prometheus**: `webhook_idempotency_key_collisions` = 0 (keys are always unique).

### Cascade

1. TCP truncation drops `hold_for_review` -> all orders auto-approve (0% hold rate)
2. Unchecked order volume flows to fulfillment
3. Webhook retries with unique timestamp keys -> partners can't dedup -> 23 duplicate dispatches
4. Partners ship double quantities -> 847 SKUs go negative
5. Circuit breaker threshold (50 negative SKUs) exceeded -> trips OPEN
6. Storefront returns 503 to all customers

---

## Evidence Summary

| Data Source | Evidence |
|-------------|----------|
| **Prometheus: `order_hold_for_review_rate`** | Current: 0%, 24h ago: 31% |
| **Prometheus: `inventory_negative_stock_skus`** | Current: 847, 1h ago: 0 (jumped in 5-minute window) |
| **Prometheus: `storefront_circuit_breaker_state`** | 1.0 (OPEN), consistently |
| **Prometheus: `webhook_duplicate_dispatches_total`** | 23 (matches partner reports exactly) |
| **Prometheus: `webhook_idempotency_key_collisions`** | 0 (timestamp keys never collide) |
| **Prometheus: `order_auto_approved_total`** | Rate 12.4/min (elevated from normal 8.5/min) |
| **Feature Flags: `order_hold_for_review_enabled`** | TRUE (flag is on, but field isn't reaching service) |
| **Feature Flags: `idempotency_key_format_v2`** | TRUE (timestamp keys active since Jan 23) |
| **Sentry: SF-789** | "Circuit breaker OPEN: inventory-service returning negative stock" (threshold 50, actual 847) |
| **Sentry: FG-502** | "No 409s -- partners accepted both batches because idempotency keys differed" |
| **Sentry: INV-934** | "Stock level went negative: SKU ELEC-TV-55-SAM, current: -234" (847 count) |
| **Jira: INFRA-3101** | "Reduce TCP buffer max from 16MB to 4MB. Tested with HTTP/1.1 load test, no issues." |
| **Jira: OPS-847** | "Missing hold_for_review. Only on large batches. Can't reproduce locally." |
| **Jira: FULFILL-890** | "Change idempotency key format from UUID to timestamp" |
| **CI Run 10100** | `apply-tcp-tuning` by kevin.park, Jan 24. Note: "No integration tests with gRPC streaming payloads" |
| **PagerDuty: PD-78901** | "inventory-service returning negative stock for 847 SKUs. Circuit breaker OPEN." |
| **PagerDuty: PD-78902** | "23 duplicate batch dispatches detected. 3 partners affected." |

---

## Remediation

### Immediate Actions (pending team execution)

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | **Revert TCP buffer settings** to `4096 87380 16777216` via ansible playbook | Kevin Park | Pending (Slack issues during incident) |
| 2 | **Disable `idempotency_key_format_v2` flag** to revert to UUID-based idempotency keys | Dan Rogers / on-call | Pending |
| 3 | **Contact fulfillment partners** (ShipCo, FastFreight, PackLogic) to halt/recall 23 duplicate shipments | Priya Sharma | Pending |
| 4 | **Reconcile inventory** after TCP fix restores correct protobuf field delivery | Inventory team | Blocked on #1 |
| 5 | **Monitor circuit breaker** - should auto-reset once negative SKU count drops below 50 | On-call | Blocked on #4 |

### Follow-up Actions

| # | Action | Owner |
|---|--------|-------|
| 6 | Add gRPC streaming integration tests to the `apply-tcp-tuning` playbook CI | Kevin Park |
| 7 | Add protobuf message size validation / checksums for critical fields like `hold_for_review` | Dan Rogers |
| 8 | Redesign idempotency keys to be deterministic (e.g., hash of batch content) rather than timestamp-based | Dan Rogers |
| 9 | Add alerting on `order_hold_for_review_rate` dropping below threshold (e.g., < 20%) | SRE team |
| 10 | Add kernel sysctl change review process requiring service-level impact analysis | Platform team |
| 11 | Close OPS-847 with root cause (TCP buffer truncation, not a data issue) | Dan Rogers |
| 12 | Conduct financial reconciliation with partners for double-shipped inventory | Finance / Priya Sharma |

---

## Lessons Learned

### What went well
- Circuit breaker worked as designed, preventing further damage once threshold was exceeded
- PagerDuty alerts fired promptly for both the circuit breaker and duplicate dispatches
- OPS-847 (Dan's bug report from Feb 5) correctly identified the symptom ("only on large batches, can't reproduce locally") -- the environmental difference was the key clue

### What went wrong
- **Infrastructure change tested with wrong protocol**: TCP buffer reduction was tested with HTTP/1.1 but our critical path uses gRPC streaming with much larger payloads
- **Silent failure mode**: Protobuf deserialization of truncated messages produces no errors. The optional bool defaults to `false` silently
- **Idempotency key design flaw**: Timestamp-based keys defeat the purpose of idempotency (deduplication). Each retry generates a unique key
- **No monitoring on hold rate**: The `order_hold_for_review_rate` dropping from 31% to 0% went undetected for ~2 weeks (Jan 24 -> Feb 7)
- **OPS-847 was not escalated**: Dan's bug from Feb 5 was marked Medium priority. The "can't reproduce locally" clue pointed to an environmental difference that should have triggered deeper investigation

### Action items for process improvement
1. **Require cross-protocol testing** for any kernel/network parameter changes -- HTTP/1.1, HTTP/2, gRPC, WebSocket
2. **Add critical business metric alerts** -- hold rate, approval rate, fulfillment rate should have anomaly detection
3. **Mandatory protobuf field validation** for business-critical fields (not just relying on Unmarshal success)
4. **Idempotency key design review** -- keys must be deterministic for the same logical operation
5. **Escalation criteria** for "can't reproduce locally" bugs -- treat as potential environmental divergence

---

## Related Tickets

- **INFRA-3101**: TCP memory tuning for cluster nodes (root cause)
- **FULFILL-890**: Refactor webhook dispatch with timestamp idempotency keys (contributing cause)
- **OPS-847**: Investigate missing hold_for_review flags (symptom, pre-existing)
- **PD-78901**: StorefrontCircuitBreaker alert
- **PD-78902**: FulfillmentDuplicateBatch alert
- **PLAT-925**: Adjust circuit breaker threshold for inventory service
