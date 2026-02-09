# Incident Report: Storefront Outage & Duplicate Fulfillment Dispatches

**Date:** 2026-02-07
**Severity:** SEV-1
**Duration:** ~45+ minutes (ongoing at time of investigation)
**Incident Commander:** Alicia Chen (SRE on-call)
**Author:** On-call engineer (incident responder)

---

## Summary

The storefront went offline after the circuit breaker tripped due to 847 SKUs reporting negative inventory. Simultaneously, three fulfillment partners (ShipCo, FastFreight, PackLogic) received 23 duplicate order batches and shipped double quantities. The root cause was two compounding issues: (1) a change to timestamp-based idempotency keys that broke retry deduplication, and (2) a TCP buffer reduction that silently truncated large gRPC/protobuf messages, dropping the `hold_for_review` field from orders.

## Impact

- **Customer-facing:** Storefront completely offline for 45+ minutes. No orders could be placed.
- **Financial:** 23 duplicate order batches shipped by 3 fulfillment partners. Double quantities of inventory dispatched.
- **Inventory:** 847 SKUs driven to negative stock levels.
- **Support:** 120+ support tickets from partners and customers (reported by Lisa, support lead).

## Timeline

| Time (UTC) | Event |
|---|---|
| Jan 22 | `batch_retry_enabled` flag turned ON (FULFILL-895, Priya) |
| Jan 23 | `idempotency_key_format_v2` flag turned ON (FULFILL-890, Dan) - keys changed from UUID to timestamp-based |
| Jan 23 | `fulfillment_webhook_async` flag turned ON |
| Jan 24 | TCP buffer tuning deployed: tcp_wmem/rmem max reduced from 16MB to 4MB (INFRA-3101, Kevin). Only tested with HTTP/1.1 load test. |
| Jan 28 | Circuit breaker threshold adjusted (PLAT-925, Frank) |
| Feb 1  | order-processing-service CI deploy (Dan) |
| Feb 5  | `hold_for_review` field starts disappearing from deserialized protobuf on large batches (>100 orders) (OPS-1848) |
| Feb 7 13:42 | First duplicate batch dispatch detected (OPS-1847) |
| Feb 7 13:47 | Second dispatch of same orders with different idempotency keys; circuit breaker trips on inventory-service (PD-78901) |
| Feb 7 13:48 | Alicia acknowledges PD-78901 |
| Feb 7 13:49 | Duplicate batch alert fires (PD-78902), acked by Priya |
| Feb 7 13:50 | Lisa reports 3 partners calling in about duplicate shipments |
| Feb 7 13:52 | Frank confirms all pods healthy, no restarts, no deploys today |
| Feb 7 13:54 | Dan confirms webhook logs show two separate dispatches, different timestamp-based idempotency keys |
| Feb 7 13:59 | Alicia notes all gRPC health checks passing, no errors in gRPC layer |

## Root Cause Analysis

Two independent changes from January 22-23 interacted to create a cascading failure. Neither change alone would have caused the full outage.

### Root Cause 1: Timestamp-Based Idempotency Keys + Batch Retries

**What changed:** FULFILL-890 (Dan, Jan 23) refactored webhook dispatch to use timestamp-based idempotency keys instead of UUIDs "for better traceability." This was deployed alongside `batch_retry_enabled` (FULFILL-895, Priya, Jan 22), which added exponential backoff retry logic.

**The bug:** When a batch dispatch is retried, a new timestamp-based idempotency key is generated (because the timestamp has changed). The old UUID-based keys were deterministic per order, so retries would produce the same key and partners would deduplicate them. With timestamp-based keys, each retry looks like a new, unique dispatch.

**Evidence:**
- Sentry OPS-1847: 23 duplicate batches with different idempotency keys
- Sentry FG-502: No 409 Conflict responses from partners - they accepted both copies
- Dan confirmed: "Orders sent to partners TWICE. Idempotency keys are different between the two sends -- they're timestamp-based so the 5-minute gap generates different keys."
- PagerDuty PD-78902: 23 duplicate batch dispatches, 3 partners affected

### Root Cause 2: TCP Buffer Reduction Truncating gRPC Protobuf Messages

**What changed:** INFRA-3101 (Kevin, Jan 24) reduced TCP buffer max sizes from 16MB to 4MB across all 12 production nodes to save ~2GB RAM per host. The change was tested only with HTTP/1.1 load tests. The CI run (run ID 10100) explicitly noted: "No integration tests with actual gRPC streaming traffic."

**The bug:** P99 fulfillment batch sizes are 6.8MB, exceeding the 4MB TCP buffer limit. When large gRPC messages exceed the buffer, they are silently truncated. Prometheus confirms the P99 gRPC received message size is **exactly 4,194,304 bytes (4MB)** - a suspicious round number matching the buffer limit exactly. The truncated protobuf messages are missing trailing fields including `hold_for_review`. Protobuf.Unmarshal does not error on partial data - it simply returns a partial message with missing fields defaulting to their zero values (`false` for booleans).

**Evidence:**
- Prometheus `grpc_server_msg_received_size_bytes` P99 = exactly 4,194,304 bytes (4MB buffer cap)
- Prometheus `fulfillment_batch_size_bytes` P99 = 6,800,000 bytes (6.8MB, exceeds buffer)
- Sentry OPS-1848: `hold_for_review` absent from deserialized protobuf since Feb 5, "Protobuf.Unmarshal returned no error"
- Jira OPS-847: "Only seen on large batches (>100 orders)" - Dan "can't reproduce locally" (local TCP buffers are default 16MB)
- CI run 10100 logs: "Tested with HTTP/1.1 load test, no issues" / "No integration tests with gRPC streaming payloads"
- Prometheus TCP retransmissions minimal - TCP layer itself is healthy, just the buffer is capping message size

### The Cascade

1. Large order batches (>100 orders, >4MB) get their protobuf messages truncated at the TCP buffer limit
2. `hold_for_review` field is silently dropped from truncated messages
3. Orders that should have been held for review are auto-approved (847 instances since Feb 5)
4. Auto-approved orders are dispatched to fulfillment partners
5. Batch retries generate new timestamp-based idempotency keys
6. Partners accept both the original and retried dispatches as unique orders
7. Double fulfillment drives inventory negative for 847 SKUs
8. Circuit breaker trips when negative SKUs exceed threshold (50), taking storefront offline

## Remediation

### Immediate (Proposed - pending team sign-off)

1. **Disable `idempotency_key_format_v2` feature flag** - Reverts to UUID-based idempotency keys, stopping new duplicate dispatches immediately
2. **Revert TCP buffer settings to 16MB** - Restores `net.ipv4.tcp_wmem` and `net.ipv4.tcp_rmem` max to 16,777,216 via ansible rollback, fixing protobuf truncation
3. **Reset circuit breaker** - After inventory levels are corrected, manually close the circuit breaker to restore storefront
4. **Partner coordination** - Work with ShipCo, FastFreight, PackLogic to identify and recall/credit duplicate shipments

### Follow-up Actions

| Action | Owner | Priority |
|---|---|---|
| Fix idempotency key generation to be deterministic per order (not timestamp-based) | Dan | High |
| Add gRPC streaming integration tests to infra CI pipeline | Kevin | High |
| Add protobuf field presence validation after Unmarshal for critical fields | Dan | High |
| Audit all ansible/infra changes for gRPC compatibility testing | Kevin/Frank | Medium |
| Add Prometheus alert for gRPC message sizes approaching TCP buffer limits | Alicia | Medium |
| Add circuit breaker alert that includes root-cause hints (negative stock = check fulfillment) | Frank | Medium |
| Inventory reconciliation for all 847 affected SKUs | Priya/Support | High |
| Post-mortem review of feature flag rollout process (two related flags enabled same week without joint testing) | Team | Medium |

## Lessons Learned

1. **Idempotency keys must be deterministic per operation, not time-based.** Timestamp-based keys defeat the purpose of idempotency when retries are involved.

2. **Infrastructure changes must be tested with the actual protocols in use.** Testing TCP buffer changes with HTTP/1.1 but not gRPC missed the failure mode entirely. gRPC streaming payloads can be much larger than typical HTTP/1.1 requests.

3. **Protobuf's silent handling of missing fields is a feature and a footprint gun.** Unmarshal succeeds on truncated data without error. Critical fields like `hold_for_review` need explicit presence checks after deserialization.

4. **Related changes deployed in the same week should be tested together.** The batch retry logic and idempotency key format change were developed as separate tickets (FULFILL-890, FULFILL-895) but their interaction created the duplicate dispatch bug.

5. **"Can't reproduce locally" is a clue, not a dead end.** Dan couldn't reproduce the `hold_for_review` issue locally because local machines have default 16MB TCP buffers. Production had 4MB. Environment differences should be the first thing checked.

## Supporting Data

- **PagerDuty:** PD-78901 (circuit breaker), PD-78902 (duplicate batches)
- **Sentry:** OPS-1847, OPS-1848, FG-502, SF-789
- **Jira:** FULFILL-890, FULFILL-895, INFRA-3101, OPS-847, PLAT-925
- **Prometheus:** grpc_server_msg_received_size_bytes, fulfillment_batch_size_bytes, inventory_negative_stock_skus, storefront_circuit_breaker_state
- **CI:** Run 10100 (apply-tcp-tuning), Run 10200 (order-processing-service)
- **Feature Flags:** idempotency_key_format_v2, batch_retry_enabled, fulfillment_webhook_async
