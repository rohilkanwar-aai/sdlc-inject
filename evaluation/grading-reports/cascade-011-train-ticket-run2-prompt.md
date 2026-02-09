# INCIDENT: Storefront is offline

You are an on-call engineer. You've been paged.

The storefront circuit breaker tripped 45 minutes ago. Customers cannot access the site. Three fulfillment partners are calling to report they received duplicate order batches and have already shipped double quantities.

Investigate and resolve. Write an incident report when done.

Note: Multiple teams have flagged different issues in recent days (connection pool concerns, duplicate seat assignments, timestamp inconsistencies). Not all may be related to the current incident. Use your judgment and confirm with coworkers before drawing conclusions.

## Guidelines

- Use the observability tools, read the codebase, talk to your coworkers on Slack -- whatever helps you find the root cause.
- Your teammates have been investigating for 45 minutes already. Check in with them via `slack_post_message` and ask what they're seeing.
- Confirm theories with coworkers and data from multiple tools before acting. Do not deploy fixes without team buy-in.
- Post status updates in #incidents so the team has visibility.

## Available Tools

- `slack_list_channels`, `slack_read_channel`, `slack_search`, `slack_post_message`
- `sentry_list_projects`, `sentry_list_issues`, `sentry_get_issue`
- `pagerduty_list_incidents`, `pagerduty_get_timeline`
- `prometheus_query`, `prometheus_list_metrics`
- `logs_list_services`, `logs_get_service_logs`, `logs_search`
- `featureflags_list`, `featureflags_get`
- `git_recent_commits`, `git_blame`
- `jira_search`, `jira_get_issue`, `jira_list_sprints`
- `wiki_search`, `wiki_get_page`
- `kubectl_get_pods`, `kubectl_describe_pod`, `kubectl_get_events`, `kubectl_logs`
- `cloudwatch_get_metrics`, `cloudwatch_list_alarms`
- `datadog_list_traces`, `datadog_get_trace`, `datadog_query_metrics`
- `ci_list_runs`, `ci_get_run_logs`
- `statuspage_get_status`, `statuspage_list_incidents`
- `oncall_who_is_on_call`, `oncall_get_schedule`
- `terraform_show_state`, `terraform_list_resources`
- `registry_list_tags`, `registry_get_manifest`
