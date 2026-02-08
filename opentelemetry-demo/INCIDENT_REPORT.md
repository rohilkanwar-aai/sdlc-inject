# Incident Report: Carts Randomly Emptying

**Severity:** P0
**Date:** 2026-02-07
**Duration:** 3+ hours (ongoing at time of investigation)
**Impact:** 58+ support tickets, zero orders processed by accounting for 3+ hours, ~3,554 Kafka messages lost permanently

---

## Summary

Customers reported shopping carts randomly becoming empty. The cart service was restarted but the issue returned within minutes. Investigation revealed the root cause was **not** in the cart service or Valkey — it was a cascading failure originating from two commits that broke the Kafka consumer in the accounting service and reduced Kafka log retention below a safe threshold.

## Timeline

| Time | Event |
|------|-------|
| Nov 15 | kevin-sre reduces Kafka `log.retention.hours` from 24 to 4 (commit `r3t8a92`) |
| Nov 27 | kevin-sre refactors accounting consumer to read session/heartbeat/poll settings from env vars, but **never adds those env vars to `.env`** (commit `k7f2b91`) |
| ~Dec 02 07:30 | Kafka producer timeouts begin appearing in checkout (CHKOUT-5014) |
| Dec 02 07:45 | `context deadline exceeded` errors spike in checkout — 4,847 occurrences (CHKOUT-5012) |
| Dec 02 08:00 | Accounting consumer offset gap detected: expected 48293, got 51847 (ACCT-847) |
| Dec 02 08:10 | Email confirmation failures cascade (CHKOUT-5013) |
| Dec 02 08:30 | Cart service reports `connection reset by peer` from checkout callers (CART-456, 347 occurrences) |
| Dec 02 09:10 | Recommendation service latency alert fires (auto-resolves — stale metrics) |
| Dec 02 09:15 | **PagerDuty alert: checkout success rate drops to 40%** (PD-94012) |
| Dec 02 09:17 | alicia (SRE on-call) acknowledges, sets up incident bridge |
| Dec 02 09:45 | Escalated to P0 — multiple teams affected, revenue impact |

## Root Cause

**Two interacting failures:**

### 1. Accounting Kafka Consumer Crash Loop (Primary)

Commit `k7f2b91` by kevin-sre changed the accounting service's Kafka consumer (`Consumer.cs`) to read `SessionTimeoutMs`, `HeartbeatIntervalMs`, and `MaxPollIntervalMs` from environment variables:

```csharp
SessionTimeoutMs = int.Parse(
    Environment.GetEnvironmentVariable("KAFKA_SESSION_TIMEOUT_MS")
    ?? throw new InvalidOperationException("KAFKA_SESSION_TIMEOUT_MS not configured")),
```

These environment variables were **never added to `.env`**. The docker-compose file passes them through (lines 37-39), but with no values defined, the consumer throws `InvalidOperationException` on every startup.

Docker's `restart: unless-stopped` policy restarts the container, creating a **rebalance storm**: 847 rebalances in 24 hours (normal: <10/week). The consumer group is perpetually stuck in `PreparingRebalance` state and never successfully consumes messages.

**Result:** Zero orders processed by accounting for 3+ hours. Consumer lag grew to 52,847 messages.

### 2. Kafka Log Retention Too Low (Amplifier)

Commit `r3t8a92` (also kevin-sre, Nov 15) reduced `KAFKA_LOG_RETENTION_HOURS` from 24 to 4 for "cost optimization." With the consumer unable to process messages, messages older than 4 hours are deleted by the Kafka broker before the consumer can read them.

**Result:** Offset gap of 3,554 messages (expected 48293, got 51847) — these orders are **permanently lost**. The accounting service can never process them.

### How This Causes "Empty Carts"

The checkout `PlaceOrder` flow (in `src/checkout/main.go:314-392`) operates in this order:

1. Get cart items
2. Charge credit card
3. Ship order
4. **Empty the user's cart** (line 349)
5. Build order result
6. Send confirmation email
7. Send to Kafka (for accounting)

The cart is emptied at step 4 **before** the Kafka message is sent at step 7. When the Kafka producer times out (293 timeout errors — CHKOUT-5014), the order is effectively lost from accounting's perspective, but the **cart is already empty**. The customer sees:
- Cart is empty (step 4 succeeded)
- No order confirmation (step 6 may also fail due to connection pool exhaustion)
- No order in their account (step 7 failed — accounting never processes it)

Additionally, the checkout service's HTTP connection pool is saturated (`net_http_transport_conns_per_host` at maximum, goroutines at 18x normal), causing cascading `context deadline exceeded` errors to shipping, email, and cart services — making many checkouts fail entirely.

## Metrics at Time of Investigation

| Metric | Value | Normal |
|--------|-------|--------|
| `checkout_success_rate` | 0.40 | >0.99 |
| `kafka_consumer_group_lag` | 52,847 | <10 |
| `kafka_consumer_group_rebalances_total` | 847/24h | <10/week |
| `kafka_consumer_group_state` | PreparingRebalance | Stable |
| `accounting_orders_processed_total` | 0 (3+ hours) | ~847/24h |
| `go_goroutines{checkout}` | 18x normal | baseline |
| `net_http_transport_conns_per_host{checkout}` | At maximum | <50% |
| `valkey_memory_used_bytes` | 23% | 23% (healthy) |

## Resolution

### Immediate Fixes Applied

1. **Added missing Kafka consumer env vars to `.env`:**
   ```
   KAFKA_SESSION_TIMEOUT_MS=45000
   KAFKA_HEARTBEAT_INTERVAL_MS=3000
   KAFKA_MAX_POLL_INTERVAL_MS=300000
   ```
   These are the standard Confluent Kafka defaults. The consumer will now start successfully.

2. **Reverted Kafka log retention to 24 hours:**
   Changed `KAFKA_LOG_RETENTION_HOURS` from 4 back to 24 in docker-compose.yml. This provides a much larger buffer for consumer downtime before messages are permanently lost.

3. **Made consumer config use safe defaults instead of crashing:**
   Changed `Consumer.cs` to fall back to Confluent Kafka defaults when env vars are unset, instead of throwing `InvalidOperationException`. This prevents future crash loops if env vars are accidentally removed.

### Recovery Steps Needed

After deploying these fixes:
1. Restart the accounting service — it should now join the consumer group cleanly
2. The consumer will resume from its last committed offset (with the gap)
3. The 3,554 lost messages (offset 48293→51847) are **unrecoverable** — these orders need manual reconciliation
4. Monitor `kafka_consumer_group_lag` to confirm it drains back toward 0
5. Monitor `kafka_consumer_group_rebalances_total` to confirm the storm stops

## Preventive Measures

1. **CI validation:** Add a check that all env vars referenced in docker-compose are defined in `.env` or have explicit defaults
2. **Consumer health monitoring:** Alert when `kafka_consumer_group_state` is stuck in `PreparingRebalance` for more than 5 minutes
3. **Log retention policy:** Kafka retention should be at least 2x the maximum expected consumer downtime. With 24h retention, consumer outages up to ~12h are survivable
4. **Checkout ordering:** Consider moving `emptyUserCart()` to AFTER the Kafka message is successfully produced, to avoid the scenario where cart is emptied but order is lost
5. **Kafka consumer config review:** Require defaults for all operational tuning parameters, not crash-on-missing behavior

## Affected Systems

- **Accounting service** — consumer stuck in crash/rebalance loop, zero orders processed
- **Checkout service** — 40% success rate, HTTP connection pool exhaustion, cascading timeouts
- **Cart service** — receiving `connection reset by peer` from overwhelmed checkout callers
- **Email service** — 1,847 failed confirmation emails

## Data Loss

- ~3,554 Kafka messages permanently lost due to 4h retention expiry
- These represent orders that were placed (cards charged, carts emptied) but never recorded in accounting
- Manual reconciliation required: cross-reference payment processor records against accounting database
