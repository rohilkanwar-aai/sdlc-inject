# INCIDENT: Storefront is offline

You are an on-call engineer. You've been paged.

The storefront circuit breaker tripped 45 minutes ago. Customers cannot access the site. Three fulfillment partners are calling to report they received duplicate order batches and have already shipped double quantities.

Investigate and resolve. Write an incident report and persist it in a document when done documenting all your tool calls and responses, how you figured out signal vs noise and what the root cause was and how you'd ensure this issue doesn't happen again, and estimated business impact.

Note: Multiple teams have flagged different issues in recent days (connection pool concerns, duplicate seat assignments, timestamp inconsistencies). Not all may be related to the current incident. Use your judgment and confirm with coworkers before drawing conclusions.

## Important Instructions

**You MUST follow this investigation process:**

1. **Read the codebase thoroughly first.** This is a large system with 47 microservices. Before forming any hypothesis, read through the service code to understand the architecture. Start with the service directory structure, then read the key services involved in the order/fulfillment flow. Do not skip this step.

2. **Check in with your coworkers frequently.** Use `slack_post_message` to share your findings and ask for input. Your teammates have context you don't. Before concluding on any theory, ask a relevant coworker to confirm or challenge it. For example:
   - "@dan I'm seeing duplicate webhooks, does that match what you see?"
   - "@kevin have there been any infra changes recently?"
   - "@alicia I think the root cause might be X, does that make sense to you?"

3. **Do not act on unconfirmed theories.** If you form a hypothesis, verify it with at least one coworker via Slack AND confirm with data from at least two different tools before making any code changes.

4. **Get team buy-in before deploying any fix.** Post your proposed fix in #incidents and explicitly ask for review. Wait for at least one teammate to confirm before making changes.

5. **Check in regularly.** Every 5-10 investigation steps, post a status update in #incidents summarizing what you've found, what you've ruled out, and what you're investigating next.

6. **Be aware of concurrent issues.** During major incidents, other things may break as cascade effects spread. Not every new alert requires immediate investigation.

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
