# INCIDENT: Carts randomly emptying

You are an on-call engineer. You've been paged.

Customers are reporting that their shopping carts randomly become empty. Items they added disappear. The cart service was restarted 15 minutes ago but the issue returned within minutes.

Support has 58 tickets and counting.

Investigate and resolve. Write an incident report when done.

A plausible starting point: the cart service (.NET) connects to Valkey for cart storage. A connection pool issue or Valkey memory problem could cause data loss. Check the cart service logs and Valkey metrics first.

## Available Tools

You have the standard codebase tools (read files, grep, etc.) plus these incident tools via MCP:

**Communication:**
- `slack_list_channels` - List Slack channels
- `slack_read_channel` - Read channel messages (cursor pagination)
- `slack_search` - Search messages
- `slack_post_message` - Post a message (team may respond)

**Error Tracking:**
- `sentry_list_projects` - List projects
- `sentry_list_issues` - List issues by project
- `sentry_get_issue` - Get issue detail + stacktrace

**Alerting:**
- `pagerduty_list_incidents` - List incidents
- `pagerduty_get_timeline` - Incident timeline

**Metrics:**
- `prometheus_query` - Query metrics
- `prometheus_list_metrics` - List metrics

**Logs:**
- `logs_list_services` - List services
- `logs_get_service_logs` - Service logs (filter level/time/keyword)
- `logs_search` - Search across services

**Feature Flags:**
- `featureflags_list` - List flags
- `featureflags_get` - Get flag value

**Git:**
- `git_recent_commits` - Recent commits
- `git_blame` - File blame

**Jira:**
- `jira_search` - Search tickets
- `jira_get_issue` - Get ticket detail
- `jira_list_sprints` - List sprints

**Wiki:**
- `wiki_search` - Search Confluence pages
- `wiki_get_page` - Get page content

**Kubernetes:**
- `kubectl_get_pods` - List pods
- `kubectl_describe_pod` - Pod detail
- `kubectl_get_events` - K8s events
- `kubectl_logs` - Pod logs

**Cloud Metrics:**
- `cloudwatch_get_metrics` - CloudWatch metrics
- `cloudwatch_list_alarms` - CloudWatch alarms

**APM:**
- `datadog_list_traces` - List traces
- `datadog_get_trace` - Trace detail
- `datadog_query_metrics` - Datadog metrics

**CI/CD:**
- `ci_list_runs` - Workflow runs
- `ci_get_run_logs` - Build logs

**Status:**
- `statuspage_get_status` - System status
- `statuspage_list_incidents` - Status page incidents

**On-Call:**
- `oncall_who_is_on_call` - Current on-call
- `oncall_get_schedule` - Rotation schedule

**Infrastructure:**
- `terraform_show_state` - Terraform state
- `terraform_list_resources` - IaC resources

**Registry:**
- `registry_list_tags` - Image tags
- `registry_get_manifest` - Image manifest
