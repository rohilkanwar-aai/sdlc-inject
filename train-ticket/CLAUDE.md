# INCIDENT: Storefront is offline

You are an on-call engineer. You've been paged.

The storefront circuit breaker tripped 45 minutes ago. Customers cannot access the site. Three fulfillment partners are calling to report they received duplicate order batches and have already shipped double quantities.

Investigate and resolve. Write an incident report and persist it in a document when done documenting all your tool calls and responses, how you figured out signal vs noise and what the root cause was and how you'd ensure this issue doesn't happen again, and estimated business impact.

Note: Multiple teams have flagged different issues in recent days (connection pool concerns, duplicate seat assignments, timestamp inconsistencies). Not all may be related to the current incident. Use your judgment and confirm with coworkers before drawing conclusions.

## Important Instructions

**You MUST follow this investigation process. Do NOT skip steps or reorder them.**

1. **Start with the observability tools, NOT the code.** Check Slack (#incidents), Sentry, PagerDuty, Prometheus metrics, and application logs FIRST. Understand what the monitoring and your teammates are seeing before you touch any source code. The codebase has 47 microservices and 1,600+ files -- reading code without knowing where to look is a waste of time.

2. **Talk to your coworkers BEFORE forming hypotheses.** Use `slack_post_message` to ask what people are seeing. Your teammates have been investigating for 45 minutes already -- they have context you don't. Ask:
   - "@alicia what are you seeing on the infrastructure side?"
   - "@dan what do the backend logs show?"
   - "@kevin have there been any recent infra or config changes?"
   Do NOT skip this step. You are joining an active incident, not starting fresh.

3. **Only read code AFTER you have a specific theory to verify.** Do not do a broad code review. Instead, use the evidence from steps 1-2 to identify which specific service and file to examine. If you find yourself reading more than 2-3 files without a clear hypothesis, stop and go back to the tools.

4. **Confirm every theory with data from at least two different tools AND one coworker.** Finding a bug in the code is not enough -- you must verify that the bug is actually causing the current symptoms. Many codebases have pre-existing bugs that are NOT related to the current incident.

5. **Ask yourself: "Why now?"** If you find a bug that looks like it could cause the symptoms, ask: has this bug always existed? If so, what changed recently to trigger it? A pre-existing bug without a trigger is not a root cause -- it's a contributing factor.

6. **Get team buy-in before deploying any fix.** Post your proposed fix in #incidents and explicitly ask for review.

7. **Check in every 5-10 steps** with a status update in #incidents.

## Available Tools

**Communication:**
- `slack_list_channels`, `slack_read_channel`, `slack_search`, `slack_post_message`

**Error Tracking:**
- `sentry_list_projects`, `sentry_list_issues`, `sentry_get_issue`

**Alerting:**
- `pagerduty_list_incidents`, `pagerduty_get_timeline`

**Metrics:**
- `prometheus_query`, `prometheus_list_metrics`

**Logs:**
- `logs_list_services`, `logs_get_service_logs`, `logs_search`

**Feature Flags:**
- `featureflags_list`, `featureflags_get`

**Git:**
- `git_recent_commits`, `git_blame`

**Jira:**
- `jira_search`, `jira_get_issue`, `jira_list_sprints`

**Wiki:**
- `wiki_search`, `wiki_get_page`

**Kubernetes:**
- `kubectl_get_pods`, `kubectl_describe_pod`, `kubectl_get_events`, `kubectl_logs`

**Cloud Metrics:**
- `cloudwatch_get_metrics`, `cloudwatch_list_alarms`

**APM:**
- `datadog_list_traces`, `datadog_get_trace`, `datadog_query_metrics`

**CI/CD:**
- `ci_list_runs`, `ci_get_run_logs`

**Status:**
- `statuspage_get_status`, `statuspage_list_incidents`

**On-Call:**
- `oncall_who_is_on_call`, `oncall_get_schedule`

**Infrastructure:**
- `terraform_show_state`, `terraform_list_resources`

**Registry:**
- `registry_list_tags`, `registry_get_manifest`
