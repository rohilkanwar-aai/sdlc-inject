# [Bug] Check-then-act buffer ownership race

**Opened by:** @affected-user
**Labels:** bug, priority: high, distributed-system-failures, needs-investigation
**Assignees:** @oncall-engineer

---

## Description

A race condition in buffer ownership checking allows two users to
simultaneously claim ownership of the same buffer, leading to
conflicting edits and potential data loss. The bug occurs because
the ownership check and acquisition are not atomic operations.


## Steps to Reproduce

1. Start collab server with sdlc_inject feature enabled
2. User A connects and opens project P
3. User B joins project P
4. Simultaneously (within 100ms), both users open file F
5. Observe: Both users see 'buffer acquired' but subsequent edits conflict


## Expected Behavior

Operations should complete successfully without conflicts.

## Actual Behavior

- Edits appear then disappear
- Cursor jumps unexpectedly to other user's position
- Undo doesn't restore expected state
- Content appears duplicated or garbled


## Environment

- OS: macOS 14.0
- App Version: v0.129.2
- Users affected: ~37

## Additional Context

This appears to happen more frequently when multiple users are editing the same file.

Possibly related to #418 (similar symptoms).


---

## Comments

### @maintainer

Thanks for the report! I've added this to our triage queue.

A few questions:
1. How frequently does this occur?
2. Are both users on the same network?
3. Can you share any logs from when this happens?

cc @oncall-engineer for investigation.

---

### @affected-user

I can reproduce this consistently when collaborating with another user.

---

### @oncall-engineer

I'm investigating this now.

Initial findings:
- Error rate spiked around the time of the report
- Seeing `WARN.*buffer ownership conflict detected` in logs
- Appears to correlate with concurrent buffer operations

Will update once I have more info.

---

### @senior-dev

This looks familiar. I think I've seen this before in the lock acquisition code.

@oncall-engineer check `crates/collab/src/db/buffers.rs` - specifically look at how we check availability before acquiring a lock. There might be a race window there.

---

### @oncall-engineer

Found it! This is a classic TOCTOU (Time-of-check to time-of-use) bug.

**The Problem:**
```
1. Check if buffer available (separate query)
2. If yes, acquire lock (another query)
```

Between steps 1 and 2, another request can swoop in and grab the lock.

**The Fix:**
Make the check-and-acquire atomic using a single `UPDATE ... WHERE ... RETURNING` query.

PR incoming.

---

### @oncall-engineer

Fix PR opened: #4528

The fix makes lock acquisition atomic and adds concurrent tests to prevent regression.

Will close this issue once the PR is merged.

---
