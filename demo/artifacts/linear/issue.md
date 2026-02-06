# ENG-6719: [Incident] Check-then-act buffer ownership race

**Status:** In Progress
**Priority:** Urgent
**Assignee:** On-Call Engineer
**Created:** 2026-02-05T18:09:25.395862Z
**Labels:** incident, sev-2, distributed-system-failures, race-condition, check-then-act, TOCTOU

---

## Summary

A race condition in buffer ownership checking allows two users to
simultaneously claim ownership of the same buffer, leading to
conflicting edits and potential data loss. The bug occurs because
the ownership check and acquisition are not atomic operations.


## Symptoms Reported

- Edits appear then disappear (Every occurrence)
- Cursor jumps unexpectedly to other user's position (Intermittent)
- Undo doesn't restore expected state (When conflict occurs)
- Content appears duplicated or garbled (Severe cases)


## Trigger Conditions

- Two users connected to same project (Required)
- Both attempt to open same file within 100ms window (Required)
- Network latency > 20ms between clients and server (Optional)


## Impact

- **Affected Users:** ~286 users
- **Error Rate:** 2.5%
- **Duration:** ~2 hours (ongoing)

## Investigation Notes

See Slack thread: #incident-race-001-514

## References

- Sentry Issue: [View in Sentry](https://sentry.io/issues/8c2a693f)
- Dashboard: [Grafana](https://grafana.internal/d/race-001)
- Runbook: [On-Call Runbook](https://docs.internal/runbooks/distributed-system-failures)


---

## Comments

### On-Call Engineer - 2026-02-05T18:18:25.395862Z

Acknowledged. Starting investigation.

---

### On-Call Engineer - 2026-02-05T18:37:25.395862Z

## Investigation Update

### Metrics Analysis
- Error rate elevated on buffer acquisition endpoint
- Connection pool utilization at 100%
- Latency p99 increased 40x

### Log Analysis
Found correlated errors:
```
WARN.*buffer ownership conflict detected
```

### Hypothesis
Possible resource contention under high concurrency.


---

### Senior Engineer - 2026-02-05T19:11:25.395862Z

This looks like a race condition we've seen before.

Check `crates/collab/src/db/buffers.rs` - specifically the lock acquisition logic.

Look for:
1. Separate check and acquire operations
2. Missing transaction boundaries
3. Non-atomic updates


---

### On-Call Engineer - 2026-02-05T19:41:25.395862Z

## Root Cause Identified

Found a TOCTOU (Time-of-check to time-of-use) race condition.

### The Bug
```
1. Check if resource available (Query 1)
2. If available, acquire lock (Query 2)
```

Between steps 1 and 2, another request can acquire the lock.

### The Fix
Make check-and-acquire atomic using `SELECT ... FOR UPDATE` or single `UPDATE ... WHERE ... RETURNING`.

PR in progress.


---

### On-Call Engineer - 2026-02-05T19:58:25.395862Z

## Fix Update

PR opened: #2688

Changes:
- Replaced check-then-acquire with atomic operation
- Added concurrent test
- Updated metrics for better observability

Currently in review. Will deploy once approved.


---
