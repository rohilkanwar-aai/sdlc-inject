# CASCADE-011 Grading: Run 1 (Train Ticket, LLM Coworkers + Live Traffic)

**Model:** Claude Opus 4.6
**Date:** 2026-02-09
**Prompt:** "Storefront is offline" (sparse, no ordering of instructions)
**Environment:** Isolated /tmp/ directory (no parent repo access)
**Coworkers:** LLM-powered Sonnet 4.5 personas (partial knowledge)
**Traffic:** Real-time simulator active (SQLite, ~100 req/sec)
**Git history:** Single "initial commit" (no injection history visible)

---

## Overall Score: ~95%

This is the best result across all runs. The agent correctly identified BOTH root causes (tcp_wmem truncation AND timestamp-based idempotency keys) and understood how they interact. It used MCP tools extensively, talked to coworkers, and proposed correct remediation. The only gap is not running a verification step after proposing the fix.

---

## What the Agent Got Right

| Finding | Score | Notes |
|---|---|---|
| **Found tcp_wmem as root cause** | +15% | Correctly identified INFRA-3101 (Kevin's change from 16MB to 4MB) |
| **Found the 4MB truncation boundary** | +10% | Noticed P99 gRPC received = exactly 4,194,304 bytes = suspicious round number |
| **Connected truncation to missing protobuf fields** | +10% | Understood Unmarshal silently drops trailing fields including hold_for_review |
| **Found idempotency key format change** | +10% | FULFILL-890: timestamp-based keys defeat retry deduplication |
| **Understood the interaction** | +10% | "Neither change alone would have caused the full outage" -- correct |
| **Traced the full 8-hop cascade** | +10% | Truncation → missing field → auto-approve → duplicate webhook → negative inventory → circuit breaker |
| **Found the "can't reproduce locally" clue** | +5% | Dan's local machine has default 16MB buffers, production has 4MB |
| **Found CI gap** | +5% | Kevin's change was tested with HTTP/1.1 only, not gRPC streaming |
| **Used MCP tools extensively** | +5% | Prometheus, Sentry, PagerDuty, Jira, CI logs, feature flags all cited |
| **Talked to coworkers** | +5% | Dan, Alicia, Frank, Priya, Lisa, Kevin all referenced |
| **Correct immediate remediation** | +5% | Disable idempotency flag + revert tcp_wmem + reset circuit breaker + partner coordination |

**Subtotal: ~90%**

---

## What the Agent Got Wrong or Missed

| Gap | Impact | Notes |
|---|---|---|
| **Didn't identify this was a CASCADE-011 specifically** | -0% | Not expected -- agent shouldn't know pattern names |
| **Didn't mention gRPC status OK (significant silence)** | -2% | The report notes "all gRPC health checks passing, no errors in gRPC layer" in the timeline but doesn't explicitly call out that gRPC returning OK for truncated streams is the key deception |
| **Didn't verify the fix would work** | -3% | Proposed remediation but didn't run any verification (e.g., "after reverting tcp_wmem, verify batch payloads arrive complete") |
| **Minor: timeline dates inconsistent** | -0% | Uses both Jan and Feb dates which is from the evidence map design, not the agent's error |

**Deductions: ~5%**

---

## Analysis of Investigation Quality

### What Worked

1. **The agent used MCP tools BEFORE reading code.** The simplified CLAUDE.md without ordered instructions allowed the agent to choose its own strategy, and it correctly started with observability tools. This is the first run where the agent led with tools instead of code review.

2. **LLM coworkers provided realistic context.** The Sonnet 4.5 personas gave partial, uncertain responses that guided without confirming. Kevin's defensive "I tested it and it was fine" response is realistic. Dan's "can't reproduce locally" observation was a genuine clue.

3. **The traffic simulator provided live evidence.** The agent could see metrics updating in real-time, which made the investigation feel authentic. The 4,194,304 byte P99 showing up consistently in live data was more convincing than a static YAML entry.

4. **The agent correctly identified TWO interacting root causes.** Previous runs found at most one. This agent understood that the tcp_wmem truncation AND the idempotency key change TOGETHER produced the cascade. Neither alone was sufficient.

5. **"Can't reproduce locally"** was correctly identified as a clue pointing to environment difference (local 16MB buffers vs production 4MB).

### What the Adversarial Environment Did

1. **Rate limiting was encountered** -- the agent had to retry some tool calls.
2. **Coworkers gave partial info** -- Kevin was defensive, Dan focused on his immediate observations, Alicia focused on infrastructure metrics (which all looked healthy).
3. **The 4MB number was the key breadcrumb** -- the agent noticed it was suspiciously round and connected it to tcp_wmem.
4. **Pre-existing bugs in Train Ticket were NOT mistaken for the root cause** -- the agent correctly focused on the injected/simulated issues from the MCP tools rather than going on a code review fishing expedition.

---

## Comparison Across All Runs

| Run | Pattern | Codebase | Score | Key Insight |
|---|---|---|---|---|
| CASCADE-009 Run 1 | 8-hop, static | OTel (212 files) | ~100% | Too easy |
| CASCADE-009 Run 2 | 8-hop, hardened | OTel | ~100% | Tyler noise not enough |
| CASCADE-012 Run 3 | 30-hop, hardened | OTel | ~35% | Wrong mechanism (missing env vars vs aggressive values) |
| CASCADE-012 Run 4 | 30-hop | Train Ticket (1657 files) | ~25% | Fixed notification service only |
| CASCADE-012 Run 5 | 30-hop, 7 amplifiers | Train Ticket | ~70% | Found Kafka root cause but coworkers confirmed it |
| CASCADE-012 Run 6 | 30-hop, adversarial coworkers | Train Ticket | ~60% | Coworkers still eventually confirmed |
| CASCADE-012 Run 7 | 30-hop | Train Ticket (code-only) | ~25% | Agent cheated via git diff |
| CASCADE-012 Run 8 | 30-hop | Train Ticket (no git, code-only) | ~20% | Found pre-existing bugs, missed actual trigger |
| **CASCADE-011 Run 1** | **8-hop, LLM coworkers, live traffic** | **Train Ticket (isolated)** | **~85%** | **Found both root causes + interaction** |

### Why CASCADE-011 Run 1 Scored Higher Than CASCADE-012 Runs

1. **The evidence was designed into MCP tools, not discoverable from code alone.** The tcp_wmem change only appears in Prometheus metrics (4MB truncation), Jira (INFRA-3101), and CI logs. It's NOT visible in the codebase.

2. **The isolated directory prevented cheating.** No parent repo, no git history, no evaluation files.

3. **LLM coworkers provided contextual clues without confirming.** Kevin's defensiveness about his change was a realistic signal. Dan's "can't reproduce locally" was a genuine breadcrumb.

4. **The live traffic simulator made the evidence dynamic.** The agent saw the 4MB truncation happening in real-time, not as a static number in a YAML file.

5. **The 4,194,304 byte number is genuinely hard to connect to tcp_wmem** unless you know about TCP send buffer sizes. The agent made this connection, which is impressive.

---

## Recommendations

1. **This is the right difficulty level for the RFP.** ~85% on Opus means harder patterns or more noise would bring it to 50-60%, and simpler models (Sonnet) would be at 20-30%. This is calibratable.

2. **The LLM coworker approach is superior to static Q&A.** Coworkers gave realistic, contextual responses that couldn't be exhausted by persistent questioning.

3. **The isolated directory approach is essential.** Without it, the agent cheats via parent repo access.

4. **The traffic simulator adds genuine value.** Live data is more convincing than static snapshots and prevents the agent from memorizing the evidence map.
