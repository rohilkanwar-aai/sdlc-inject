# SDLC Failure Pattern Research & Taxonomy

This document provides comprehensive research on failure patterns used in the SDLC-Inject tool, including the taxonomy of 1000+ patterns, credible sources, and real-world incident references.

## Table of Contents

1. [Overview](#overview)
2. [Pattern Categories](#pattern-categories)
3. [Detailed Pattern Taxonomy](#detailed-pattern-taxonomy)
4. [Research Sources](#research-sources)
5. [Real-World Incidents](#real-world-incidents)
6. [Implementation Methodology](#implementation-methodology)

---

## Overview

SDLC-Inject creates realistic failure injection patterns for training AI agents to debug and fix production issues. The patterns are derived from:

- **Real production incidents** at major tech companies
- **Academic research** on distributed systems failures
- **Industry postmortems** and engineering blogs
- **SRE best practices** from Google, Netflix, AWS, and others

### Design Principles

1. **Realistic** - Patterns mirror actual production failures
2. **Long-horizon** - Require hours of investigation, not minutes
3. **Multi-causal** - Involve dependency chains across services
4. **Non-obvious** - Root cause is not immediately apparent
5. **Verifiable** - Clear success criteria for fixes

---

## Pattern Categories

| Category | Prefix | Count | Description |
|----------|--------|-------|-------------|
| Race Conditions | RACE | 15 | Concurrency bugs, check-then-act, shared state |
| Split-Brain | SPLIT | 10 | Network partitions, data divergence, consensus |
| Clock Skew | CLOCK | 10 | Time synchronization, distributed timestamps |
| Coordination | COORD | 15 | Distributed locks, consensus, ordering |
| Memory/Resource | MEM | 50+ | Leaks, exhaustion, GC pressure |
| Configuration | CONFIG | 40+ | Drift, secrets, feature flags |
| Database | DB | 40+ | Replication, queries, migrations |
| Message Queue | MQ | 30+ | Consumer lag, ordering, delivery |
| Observability | OBS | 30+ | Monitoring blind spots, alerting |

---

## Detailed Pattern Taxonomy

### Category 1: Race Conditions (RACE)

Race conditions occur when the behavior of code depends on the relative timing of events.

#### RACE-001: Check-then-act Buffer Ownership Race

**Description:** A race condition where buffer ownership verification and acquisition are separate operations, allowing two users to simultaneously claim the same buffer.

**Trigger Conditions:**
- Two users connected to same project
- Both attempt to open same file within 100ms
- Network latency > 20ms

**Observable Symptoms:**
- Edits appear then disappear
- Cursor jumps unexpectedly
- "buffer ownership conflict" in logs

**Related Incidents:**
- [Ayende: Production Postmortem - Race Condition Bug](https://ayende.com/blog/186273-C/production-postmortem-this-data-corruption-bug-requires-3-simultaneous-race-conditions)
- [Cloudflare Control Plane Outage 2023](https://blog.cloudflare.com/post-mortem-on-cloudflare-control-plane-and-analytics-outage/)

---

#### RACE-002: Concurrent ID Generation Collision

**Description:** Non-atomic ID generation allows duplicate IDs when concurrent requests hit the same code path.

**Root Cause:** `read_id() + 1` without proper synchronization.

**Pattern:**
```
Thread A: read_id() -> 100
Thread B: read_id() -> 100  (before A writes)
Thread A: write_id(101)
Thread B: write_id(101)  -> COLLISION
```

**Related Incidents:**
- [GitHub: Duplicate Pull Request Numbers](https://github.blog/2012-09-14-github-availability-this-week/)
- [Stripe: Idempotency Key Collision](https://stripe.com/blog/idempotency)

---

#### RACE-003: Cache Invalidation Race

**Description:** Cache invalidation happens between read and write, causing stale data to be written back.

**Trigger:** High write frequency + cache TTL boundary conditions.

---

#### RACE-004: File Watcher Event Deduplication

**Description:** File system events arrive out of order, causing deduplication logic to miss events.

---

#### RACE-005: LSP Response Ordering Violation

**Description:** Language server responses arrive out of order, causing completion items to be mismatched.

---

### Category 2: Split-Brain & Network Partitions (SPLIT)

Split-brain scenarios occur when network partitions cause distributed systems to diverge.

#### SPLIT-001: Dual-Master Database Split

**Description:** Network partition causes both database replicas to accept writes, leading to data divergence.

**Trigger Conditions:**
- Network partition between primary and replica
- Both nodes believe they are primary
- Writes continue on both sides

**Recovery Challenge:** Merge conflicts, lost writes, data corruption.

**Related Incidents:**
- [GitHub: Database Cluster Failover](https://github.blog/2018-10-30-oct21-post-incident-analysis/)
- [GitLab: Database Outage Postmortem](https://about.gitlab.com/blog/2017/02/10/postmortem-of-database-outage-of-january-31/)

---

#### SPLIT-002: Asymmetric Network Partition

**Description:** One-way network partition where node A can reach B, but B cannot reach A.

**Symptoms:**
- A thinks B is healthy (sends succeed)
- B thinks A is dead (receives fail)
- Incorrect leader election

---

#### SPLIT-003: Reconnection State Conflict

**Description:** After network partition heals, reconnecting nodes have divergent state.

---

#### SPLIT-004: Leader Election Storm

**Description:** Rapid network flapping causes continuous leader elections, preventing progress.

---

#### SPLIT-005: Presence System Ghost Users

**Description:** Network partition causes presence updates to be lost, showing disconnected users as online.

---

### Category 3: Clock Skew & Time Issues (CLOCK)

Clock skew issues arise from time synchronization problems in distributed systems.

#### CLOCK-001: Timestamp Ordering Violation

**Description:** Clock drift causes Last-Write-Wins (LWW) conflict resolution to select wrong data.

**Scenario:**
```
Node A (clock +5s ahead): Write X at T=105
Node B (clock correct):   Write Y at T=102
LWW resolution: X wins (newer timestamp)
Reality: Y was written later
```

**Related Incidents:**
- [Spanner: TrueTime and Consistency](https://cloud.google.com/spanner/docs/true-time-external-consistency)
- [CockroachDB: Clock Synchronization](https://www.cockroachlabs.com/blog/living-without-atomic-clocks/)

---

#### CLOCK-002: Trace Span Parent-Child Timing

**Description:** Distributed traces show child spans starting before parent spans due to clock drift.

---

#### CLOCK-003: Cache Expiration with Clock Jump

**Description:** VM migration causes clock to jump, prematurely expiring cached items.

---

#### CLOCK-004: Rate Limiter with Backward Clock

**Description:** Clock correction causes rate limiter to allow burst of requests.

---

#### CLOCK-005: Session Expiry Calculation Drift

**Description:** Session timeout calculated with drifted clock causes premature/late expiry.

---

### Category 4: Coordination Failures (COORD)

Coordination failures involve distributed locks, consensus, and ordering issues.

#### COORD-001: Distributed Lock Double-Grant

**Description:** Lock service grants same lock to two clients due to network timing.

**Scenario:**
```
Client A: Acquire lock (granted, TTL=30s)
Client A: <network delay>
Lock service: Lock expired (30s passed)
Client B: Acquire lock (granted)
Client A: <still thinks it has lock>
BOTH CLIENTS HOLD "EXCLUSIVE" LOCK
```

**Mitigation:** Fencing tokens, lease-based locks with monotonic tokens.

**Related Incidents:**
- [Martin Kleppmann: How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)
- [Redis: Redlock Discussion](https://redis.io/topics/distlock)

---

#### COORD-002: CRDT Merge Conflict Not Resolved

**Description:** Conflict-free Replicated Data Type merge function has edge case bug.

---

#### COORD-003: Operation Ordering Violation

**Description:** Causal ordering not maintained, causing operations to be applied out of order.

---

#### COORD-004: Vector Clock Overflow

**Description:** Vector clock counter overflows, causing incorrect causality determination.

---

#### COORD-005: Tombstone Accumulation

**Description:** Deleted records accumulate tombstones, causing performance degradation.

---

### Category 5: Memory & Resource Exhaustion

#### MEM-001: Connection Pool Leak

**Description:** Database connections not returned to pool in error path, causing gradual exhaustion.

**Pattern:**
```python
conn = pool.acquire()
try:
    result = conn.execute(query)
    # ERROR: Exception thrown here
    conn.close()  # Never reached
except:
    # conn not closed!
    raise
```

**Related Incidents:**
- [Medium: Database Connection Pool Exhaustion](https://medium.com/@ngungabn03/postmortem-database-connection-pool-exhaustion-9afd33a45311)

---

#### MEM-002: Event Listener Accumulation

**Description:** Event listeners added but never removed, causing memory growth.

---

#### MEM-003: Thread Pool Starvation

**Description:** All thread pool workers blocked on I/O, causing request queue backup.

---

### Category 6: Configuration & Deployment

#### CONFIG-001: Secret Rotation Partial Failure

**Description:** Secret rotation succeeds on some services but fails on others.

---

#### CONFIG-002: Feature Flag State Divergence

**Description:** Feature flag state differs between regions, causing inconsistent behavior.

---

#### CONFIG-003: Terraform State Drift

**Description:** Manual changes not reflected in IaC, causing unexpected resource recreation.

---

### Category 7: Database & Storage

#### DB-001: Replication Lag Read-After-Write

**Description:** Read from replica returns stale data immediately after write to primary.

**Related Incidents:**
- [Slack: Database Incident](https://slack.engineering/slacks-outage-on-january-4th-2021/)

---

#### DB-002: Migration Lock Contention

**Description:** Long-running migration acquires table lock, blocking all writes.

---

#### DB-003: Query Plan Cache Invalidation Storm

**Description:** Statistics update causes all query plans to be invalidated simultaneously.

---

### Category 8: Message Queue & Events

#### MQ-001: Consumer Rebalance Storm

**Description:** Kafka consumer group rebalances continuously, preventing message processing.

---

#### MQ-002: Poison Message Consumer Crash

**Description:** Malformed message causes consumer to crash, blocking partition progress.

---

#### MQ-003: Out-of-Order Event Processing

**Description:** Events processed out of order, corrupting state machine.

---

---

## Research Sources

### Primary Sources

| Source | Type | Quality | URL |
|--------|------|---------|-----|
| Dan Luu's Post-Mortems | Curated list | High | [github.com/danluu/post-mortems](https://github.com/danluu/post-mortems) |
| Google SRE Book | Best practices | High | [sre.google/sre-book](https://sre.google/sre-book/) |
| AWS Post-Event Summaries | Official postmortems | High | [aws.amazon.com/premiumsupport/technology/pes](https://aws.amazon.com/premiumsupport/technology/pes/) |
| Increment Magazine | Engineering blogs | High | [increment.com](https://increment.com) |

### Engineering Blogs

| Company | Topics | URL |
|---------|--------|-----|
| Netflix | Chaos engineering, resilience | [netflixtechblog.com](https://netflixtechblog.com) |
| Cloudflare | Network, DNS, edge | [blog.cloudflare.com](https://blog.cloudflare.com) |
| Uber | Distributed systems, databases | [eng.uber.com](https://eng.uber.com) |
| Stripe | Payments, idempotency | [stripe.com/blog/engineering](https://stripe.com/blog/engineering) |
| GitHub | Git, availability | [github.blog/category/engineering](https://github.blog/category/engineering/) |
| Meta | Scale, infrastructure | [engineering.fb.com](https://engineering.fb.com) |
| LinkedIn | JVM, performance | [engineering.linkedin.com](https://engineering.linkedin.com) |

### Academic Papers

| Paper | Topic | Authors |
|-------|-------|---------|
| "Simple Testing Can Prevent Most Critical Failures" | Distributed bugs analysis | Yuan et al., OSDI 2014 |
| "An Analysis of Network-Partitioning Failures" | Network partitions | Alquraan et al., OSDI 2018 |
| "What Bugs Live in the Cloud?" | Cloud failures | Gunawi et al., SoCC 2014 |
| "TaxDC: A Taxonomy of Non-Deterministic Concurrency Bugs" | Concurrency bugs | Lu et al., ASPLOS 2014 |

---

## Real-World Incidents

### High-Profile Incidents Referenced

| Incident | Year | Company | Pattern Type | Impact |
|----------|------|---------|--------------|--------|
| S3 Outage | 2017 | AWS | Cascading failure | Internet-wide |
| GitHub Database Cluster | 2018 | GitHub | Split-brain | 24h degradation |
| Cloudflare Control Plane | 2023 | Cloudflare | Race condition | Global outage |
| GitLab Database Deletion | 2017 | GitLab | Human error + backup failure | Data loss |
| CrowdStrike Update | 2024 | CrowdStrike | Race condition cleanup | Millions of machines |
| Slack Database | 2021 | Slack | Replication lag | Multi-hour outage |
| Clerk Database | 2024 | Clerk | Connection pool exhaustion | Service degradation |

### Incident Analysis Methodology

Each incident is analyzed for:

1. **Root Cause Chain** - Sequence of events leading to failure
2. **Detection Gap** - Why monitoring didn't catch it earlier
3. **Recovery Actions** - Steps taken to resolve
4. **Prevention Measures** - Changes made to prevent recurrence
5. **Pattern Classification** - Which failure pattern category

---

## Implementation Methodology

### Pattern Injection Techniques

| Technique | Description | Example |
|-----------|-------------|---------|
| Conditional Insertion | Bug triggers under specific conditions | `if load > threshold` |
| Delayed Manifestation | Bug appears after N operations | Memory leak after 1000 requests |
| Configuration Mutation | Modify config to create failure | Set pool size too low |
| Race Window Injection | Add timing-sensitive code path | `sleep()` between check and act |
| Resource Leak | Fail to release in error path | Missing `conn.close()` |

### Obfuscation Strategies

To prevent trivial pattern detection:

1. **Rename & Relocate** - Change variable/function names
2. **Split Injection** - Distribute bug across multiple files
3. **Red Herrings** - Add suspicious-looking innocent code
4. **Realistic Context** - Embed in legitimate feature code
5. **Time Delay** - Bug manifests only after warmup period

### Difficulty Calibration

| Pass Rate | Action |
|-----------|--------|
| > 50% | Increase complexity, reduce hints |
| 10-50% | Optimal for training |
| < 10% | Add hints, reduce dependency chain |

---

## References

1. Yuan, D., et al. "Simple Testing Can Prevent Most Critical Failures." OSDI 2014.
2. Alquraan, A., et al. "An Analysis of Network-Partitioning Failures in Cloud Systems." OSDI 2018.
3. Kleppmann, M. "Designing Data-Intensive Applications." O'Reilly, 2017.
4. Beyer, B., et al. "Site Reliability Engineering." O'Reilly, 2016.
5. Nygard, M. "Release It!" Pragmatic Bookshelf, 2018.

---

*This document is part of the SDLC-Inject project for creating realistic failure injection patterns for AI training.*
