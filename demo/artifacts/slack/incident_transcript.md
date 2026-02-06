# Incident Channel: #incident-race-001-539

**Topic:** Status: INVESTIGATING | Severity: SEV-2 | IC: @oncall-engineer

---

**@incident-bot**
🚨 *INCIDENT DETECTED*

*Service:* zed
*Severity:* SEV-2
*Alert:* Check-then-act buffer ownership race

*Symptoms Reported:*
  - Edits appear then disappear
  - Cursor jumps unexpectedly to other user's position
  - Undo doesn't restore expected state

*Affected Users:* ~266 users
*Error Rate:* 2.6% (baseline: 0.1%)

<@oncall-engineer> has been paged.


---

**@oncall-engineer**
Acknowledged. Looking into this now.

---

**@oncall-engineer**
Starting investigation. Here's what I see so far:

1. ✅ Service is up and responding
2. ⚠️ Error rate elevated for `/api/buffers/acquire` endpoint
3. ⚠️ Latency p99 increased from 50ms to 2000ms
4. 🔍 Checking logs and metrics now...

Dashboard: <https://grafana.internal/d/race-001|RACE-001 Dashboard>


---

**@senior-engineer**
I've seen this before. Check the buffer locking code.

---

**@oncall-engineer**
📊 *Metrics Analysis*

Found some anomalies:
  - `buffer_conflicts_total`: elevated
  - `buffer_lock_retries_total`: elevated
  - `buffer_acquisition_duration_seconds`: bimodal distribution indicates race

  - Request queue depth: growing unbounded
  - Successful lock acquisitions: trending down

This looks like resource contention, not a service outage.


---

**@oncall-engineer**
📝 *Log Analysis*

Found these patterns in the last hour:
```WARN.*buffer ownership conflict detected```
```ERROR.*multiple owners for buffer_id=\d+```
```DEBUG.*lock acquisition failed after availability check passed```


Frequency: 898 occurrences in last 30 min

The errors correlate with the latency spike.


---

**@senior-engineer**
I think I know what this is.

Check the lock acquisition flow - there might be a timing issue.

Hint: check_buffer_available() and try_acquire_lock() are separate operations


---

**@oncall-engineer**
🎯 *Root Cause Identified*

Found it! In `crates/collab/src/db/buffers.rs`:

The issue is a TOCTOU (Time-of-check to time-of-use) race condition:
1. We check if buffer is available (separate query)
2. Then we try to acquire the lock (another query)
3. Between steps 1 and 2, another request can acquire the lock

Under high concurrency, this causes conflicts.

*NOT the fix:* Assumes network latency is the root cause
*Actual fix:* Make the check-and-acquire atomic (single transaction)


---

**@tech-lead**
Good find. Let's get a fix in.

---

**@oncall-engineer**
🔧 *Fix In Progress*

PR opened: <https://github.com/org/repo/pull/6626|Fix buffer lock race condition>

Approach:
- Replace check-then-acquire with atomic operation
- Add concurrent test to prevent regression

```rust
// Use SELECT FOR UPDATE or atomic UPDATE
let lock_acquired = sqlx::query!(
    "UPDATE buffers SET locked_by = $1
     WHERE id = $2 AND locked_by IS NULL
     RETURNING id",
...
```

Running tests now...


---

**@oncall-engineer**
✅ *Fix Deployed*

- PR merged and deployed to production
- Canary looks good (0 conflicts in last 5 min)
- Error rate back to baseline
- Monitoring for 15 more minutes before resolving

Metrics: <https://grafana.internal/d/race-001|Dashboard>


---

**@incident-bot**
🎉 *INCIDENT RESOLVED*

*Duration:* 2 hours 0 minutes
*Root Cause:* Race condition in buffer lock acquisition
*Resolution:* Made lock acquisition atomic
*Impact:* ~1746 users affected

*Action Items:*
- [ ] Schedule post-mortem
- [ ] Add alerting for `buffer_conflicts_total`
- [ ] Review other lock acquisition code for similar issues

Channel will be archived in 7 days.


---
