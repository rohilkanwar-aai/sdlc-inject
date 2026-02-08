# CASCADE-012 Grading: Run 3 (Hardened v3 + 42 Tools + Response Delays)

**Model:** Claude Opus 4.6
**Date:** 2026-02-07
**Prompt:** "Carts randomly emptying" (Branch D — 4 hops from Kafka root cause)
**Suggested starting point:** Valkey memory/connection pool (wrong)
**Tools available:** 42 (18 real + 24 noise)
**Noise:** 50K messages/channel, 50K log entries/service, 117 metrics, 25 channels, 22 Sentry projects, 53 git commits
**Config values hidden:** Yes (code throws if env var not set, no defaults visible)
**Response delays:** Yes (Kevin 3 ticks, Frank 2 ticks, etc.)

---

## Overall Score: ~35-40%

The agent escaped the wrong starting point (cart/Valkey), found the Kafka rebalance storm, and produced a workable fix. But it misidentified the root cause mechanism, missed 3 of 5 branches, didn't use reactive Slack for missing information, and left the system fragile.

---

## What the Agent Got Right

| Finding | Score | Notes |
|---|---|---|
| Escaped the Valkey red herring | +5% | Correctly identified Valkey at 23% memory is healthy |
| Found Kafka consumer rebalance storm | +10% | Identified 847 rebalances, PreparingRebalance state |
| Found Kevin's two commits | +5% | `k7f2b91` (consumer config) and `r3t8a92` (retention) |
| Found `KAFKA_LOG_RETENTION_HOURS=4` as data loss amplifier | +5% | Correctly identified 3,554 lost messages |
| Traced cart emptying to checkout `PlaceOrder` ordering | +5% | Correctly found `emptyUserCart()` happens before Kafka send |
| Found connection pool exhaustion | +3% | Identified goroutines at 18x normal, transport at max |
| Found checkout success rate at 40% | +2% | Discovered this wasn't just a cart issue |
| Reverted Kafka retention to 24h | +3% | Correct fix for data loss prevention |
| Proposed CI validation for env vars | +2% | Good preventive measure |
| Proposed consumer group monitoring | +2% | Alert on stuck PreparingRebalance |

**Subtotal: ~42%**

---

## What the Agent Got Wrong

### 1. WRONG ROOT CAUSE MECHANISM (Critical)

**Agent's claim:** "Environment variables were never added to `.env`. The consumer throws `InvalidOperationException` on every startup."

**Reality:** The `.env` file on the deployment server HAS the values — they're just aggressive: `KAFKA_SESSION_TIMEOUT_MS=6000`, `KAFKA_HEARTBEAT_INTERVAL_MS=2000`, `KAFKA_MAX_POLL_RECORDS=500`. The consumer starts fine and works under normal load. It only rebalances under 2x Monday traffic because the larger batch size (500 records) causes poll processing to exceed the 6-second session timeout.

**Why this matters:** The agent's theory ("missing env vars → crash loop") is a deployment bug. The actual issue is a config tuning problem that's load-dependent. These have completely different fixes:
- Agent's fix: Add safe defaults (45000ms) → consumer never crashes
- Correct fix: Revert Kevin's aggressive values (6000→30000) → consumer handles Monday traffic

**Score impact:** -15% (misidentified the fundamental mechanism)

### 2. DIDN'T USE REACTIVE SLACK FOR MISSING INFORMATION (Major)

**What happened:** The agent read `Consumer.cs`, saw `?? throw new InvalidOperationException(...)`, and concluded the env vars were missing. It never asked Kevin "what values did you set?" because its wrong theory was self-consistent.

**What should have happened:** The agent should have:
1. Noticed the code throws if env var is not set
2. Asked Kevin via `slack_post_message`: "@kevin what are the actual KAFKA_SESSION_TIMEOUT_MS values?"
3. Kevin would respond (after 3-tick delay): "session.timeout.ms=6000, heartbeat=2000, max.poll.records=500"
4. Agent recognizes 6s session timeout is extremely aggressive
5. Connects to Monday 2x traffic causing poll interval exceeded

**Why this matters:** The reactive Slack system was designed specifically for this — critical information that exists nowhere in the codebase. The agent bypassed it entirely by constructing a plausible-but-wrong theory from the code alone.

**Score impact:** -10%

### 3. MISSED BRANCH C: OBSERVABILITY BLINDNESS (Major)

**What the agent should have found:**
- OTel Collector exports spans/metrics to Kafka
- Kafka instability causes collector's Kafka exporter to back up
- Collector's `memory_limiter` drops all incoming data
- Prometheus shows stale metrics, Jaeger shows incomplete traces
- The PagerDuty alert for recommendation service "auto-resolved" because Prometheus stopped receiving data — `rate()` returned NaN, not because the issue resolved
- The agent's own investigation tools were degraded

**What the agent said:** Nothing. No mention of OTel Collector, Prometheus staleness, or monitoring degradation.

**Why this matters:** Branch C is the most important branch because it means the agent's investigation tools are unreliable. An expert engineer would notice stale metrics and factor that into their investigation. The agent blindly trusted the metrics it received.

**Score impact:** -8%

### 4. MISSED BRANCH E: STALE RECOMMENDATIONS + AD FAILURES (Minor)

**What the agent should have found:**
- Recommendation service can't refresh its model (gRPC blocked by collector backpressure)
- Falls back to 48-hour-old cached model with discontinued products
- Ad service gets NullPointerException from stale recommendation data
- Blank ad slots on product pages

**What the agent said:** Nothing about recommendations or ad service.

**Score impact:** -3%

### 5. MISSED THE MONDAY TRAFFIC TRIGGER (Major)

**Agent's claim:** The consumer crashes on every startup (missing env vars).

**Reality:** The config worked fine for 5 days under normal traffic (~300 req/s). Monday morning 2x spike (~600 req/s) is what triggered the rebalance storm. This is visible in `frontend_request_rate: current=612, 24h_ago=298`.

**Why this matters:** Understanding the trigger explains why the issue started NOW, not 5 days ago when Kevin deployed. The agent's "missing env vars" theory doesn't explain the timing — if env vars were missing, the consumer would have crashed immediately on deploy, not 5 days later.

**The agent didn't question its own theory's temporal inconsistency.**

**Score impact:** -5%

### 6. DIDN'T VERIFY THE .ENV FILE EXISTS ON THE DEPLOYMENT SERVER

**What the agent assumed:** `.env` file doesn't have the Kafka vars.

**What it should have done:** Asked Frank or Kevin via Slack: "Can you check what's in the .env on the deployment server?" Frank would have responded (after 2-tick delay): "The .env file has KAFKA_SESSION_TIMEOUT_MS=6000, KAFKA_HEARTBEAT_INTERVAL_MS=2000."

**The agent made an assumption about infrastructure state without verifying it.**

**Score impact:** -3%

### 7. FIX IS WORKABLE BUT IMPRECISE

**Agent's fix:** Add defaults of 45000/3000/300000 to `Consumer.cs` and add env vars to `.env`.

**Correct fix:** Revert to original values (30000/10000/100) in the `.env` on the deployment server, then commit those values to version control so they're not invisible.

**The agent's fix happens to work** because 45000ms session timeout is safe (standard range is 30-45s). But:
- It doesn't explain to the team WHY Kevin's values were wrong
- It doesn't address `max.poll.records=500` (the batch size that causes slow polls)
- It sets `HeartbeatIntervalMs=3000` which is non-standard (should be ~1/3 of session timeout)

**Score impact:** -3%

---

## Cognitive Bias Analysis

### Anchoring: Escaped but Re-Anchored

The agent correctly escaped the initial cart/Valkey anchor. But it re-anchored on `?? throw` in the code — once it saw the exception, it concluded "missing env vars" and never questioned this.

### Confirmation Bias: Self-Consistent Wrong Theory

The agent's "missing env vars → crash loop → rebalance storm" theory is internally consistent:
- Code throws if var not set ✓
- Rebalance storm happening ✓
- Data loss from retention ✓

Because the theory explains the evidence, the agent never sought disconfirming evidence (like asking Kevin for actual values, or checking why the issue started on Monday not Wednesday).

### Satisficing: Found a Workable Fix and Stopped

The agent's fix (add defaults) actually resolves the symptoms. It's a 45000ms timeout — well within safe range. So the agent stopped investigating further branches because the immediate problem was "solved."

### Tool Overload: Didn't Work

Having 42 tools available didn't significantly slow the agent. It efficiently filtered to the relevant tools (Sentry, Prometheus, git, code reading) and ignored most noise tools. The agent didn't try Jira, Confluence, Terraform, CloudWatch, or Docker Registry — it went straight to the diagnostic tools.

### Response Delays: Not Triggered

The agent never used `slack_post_message` to ask questions, so the delay mechanism was never activated. Kevin's "brb pulling up laptop" response and Frank's "in standup" response were never seen.

---

## Comparison Across Runs

| Metric | Run 1 (CASCADE-009 v1) | Run 2 (CASCADE-009 v2) | Run 3 (CASCADE-012 v3) |
|---|---|---|---|
| Pattern | 8-hop linear | 8-hop linear | 30-hop branching |
| Tools | 17 | 17 | 42 |
| Noise | None | 71 Slack msgs | 50K/channel |
| Config visible in code | Yes (defaults) | Yes (defaults) | No (throws) |
| Starting point | Correct (checkout) | Correct (checkout) | Wrong (cart) |
| Response delays | No | No | Yes |
| Root cause found | 100% | 100% | ~40% (wrong mechanism) |
| Branches found | 1/1 | 1/1 | 2/5 |
| Used reactive Slack | No (not needed) | No (not needed) | No (should have) |
| Fix quality | Perfect | Perfect | Workable but imprecise |
| Overall score | ~100% | ~100% | ~35-40% |

---

## Recommendations for Further Difficulty

1. **The `?? throw` pattern was too effective as a wrong signal.** The agent interpreted it as "env var missing" rather than "env var has an aggressive value." Consider making the code more ambiguous — e.g., `?? "30000"` as default but the ACTUAL deployed value is different (from `.env`). This forces the agent to ask "what's the actual value?" rather than reading the code.

2. **The agent doesn't use reactive Slack proactively.** It only uses Slack when it's stuck. To force Slack usage, make the code completely generic (just reads env vars with safe defaults) and put the aggressive values ONLY on the deployment server. The code gives no clue that the values are unusual.

3. **The agent efficiently filters noise tools.** 42 tools didn't slow it down meaningfully. Consider making the noise tools return data that is ALMOST relevant — e.g., Terraform state showing `session_timeout_ms = 30000` (the OLD value, before Kevin changed it) which would mislead the agent into thinking the config is fine.

4. **The auto-resolved PagerDuty alert (monitoring blindness) was not noticed.** Consider making the stale metrics more prominently broken — e.g., Prometheus queries returning explicit "stale" warnings instead of silently returning old data.
