"""Linear/Jira issue artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class LinearArtifactGenerator(ArtifactGenerator):
    """Generates realistic Linear/Jira issue tickets."""

    def generate(self) -> dict[str, Any]:
        """Generate issue ticket with comments."""
        return {
            "issue": self._generate_issue(),
            "comments": self._generate_comments(),
            "activity": self._generate_activity(),
            "related_issues": self._generate_related(),
        }

    def _generate_issue(self) -> dict[str, Any]:
        """Generate the main issue."""
        symptoms = self.pattern.observable_symptoms
        user_symptoms = symptoms.user_visible if symptoms else []

        description = self._build_description(user_symptoms)

        return {
            "id": self.random_uuid(),
            "identifier": f"ENG-{self.rng.randint(1000, 9999)}",
            "title": f"[Incident] {self.pattern.name}",
            "description": description,
            "state": {
                "name": "In Progress",
                "type": "started",
            },
            "priority": 1,  # Urgent
            "priorityLabel": "Urgent",
            "labels": self._generate_labels(),
            "assignee": {
                "id": self.random_uuid()[:8],
                "name": "On-Call Engineer",
                "email": "oncall@company.com",
            },
            "creator": {
                "id": self.random_uuid()[:8],
                "name": "Incident Bot",
                "email": "incidents@company.com",
            },
            "team": {
                "id": self.random_uuid()[:8],
                "name": "Platform",
                "key": "ENG",
            },
            "project": {
                "id": self.random_uuid()[:8],
                "name": self.pattern.target_codebase.name,
            },
            "createdAt": self.random_timestamp(offset_minutes=-120),
            "updatedAt": self.random_timestamp(offset_minutes=-5),
            "startedAt": self.random_timestamp(offset_minutes=-115),
            "estimate": self.pattern.difficulty.estimated_human_time_hours,
            "cycle": {
                "id": self.random_uuid()[:8],
                "name": "Sprint 23",
            },
            "parent": None,
            "children": [],
            "attachments": self._generate_attachments(),
            "url": f"https://linear.app/company/issue/ENG-{self.rng.randint(1000, 9999)}",
        }

    def _build_description(self, user_symptoms: list) -> str:
        """Build issue description from pattern."""
        symptom_list = ""
        for s in user_symptoms[:5]:
            symptom_list += f"- {s.symptom} ({s.frequency})\n"

        trigger_list = ""
        if self.pattern.trigger:
            for c in self.pattern.trigger.conditions[:3]:
                req = "Required" if c.required else "Optional"
                trigger_list += f"- {c.description} ({req})\n"

        return f"""## Summary

{self.pattern.description[:500]}

## Symptoms Reported

{symptom_list or "- Service degradation reported by users"}

## Trigger Conditions

{trigger_list or "- High traffic conditions"}

## Impact

- **Affected Users:** ~{self.rng.randint(50, 500)} users
- **Error Rate:** {self.rng.uniform(1, 10):.1f}%
- **Duration:** ~2 hours (ongoing)

## Investigation Notes

See Slack thread: #incident-{self.pattern.id.lower()}-{self.rng.randint(100, 999)}

## References

- Sentry Issue: [View in Sentry](https://sentry.io/issues/{self.random_uuid()[:8]})
- Dashboard: [Grafana](https://grafana.internal/d/{self.pattern.id.lower()})
- Runbook: [On-Call Runbook](https://docs.internal/runbooks/{self.pattern.category.lower().replace(' ', '-')})
"""

    def _generate_labels(self) -> list[dict[str, str]]:
        """Generate issue labels."""
        labels = [
            {"id": "1", "name": "incident", "color": "#FF0000"},
            {"id": "2", "name": f"sev-2", "color": "#FFA500"},
            {"id": "3", "name": self.pattern.category.lower().replace(" ", "-"), "color": "#0000FF"},
        ]

        # Add pattern-specific labels
        if self.pattern.tags:
            for i, tag in enumerate(self.pattern.tags[:3]):
                labels.append({
                    "id": str(10 + i),
                    "name": tag,
                    "color": "#808080",
                })

        return labels

    def _generate_comments(self) -> list[dict[str, Any]]:
        """Generate issue comments."""
        comments = [
            (-115, "On-Call Engineer", "Acknowledged. Starting investigation."),
            (-90, "On-Call Engineer", self._investigation_update()),
            (-60, "Senior Engineer", self._senior_input()),
            (-30, "On-Call Engineer", self._root_cause_found()),
            (-10, "On-Call Engineer", self._fix_update()),
        ]

        return [
            {
                "id": self.random_uuid()[:8],
                "body": body,
                "user": {
                    "id": self.random_uuid()[:8],
                    "name": user,
                },
                "createdAt": self.random_timestamp(offset_minutes=offset),
            }
            for offset, user, body in comments
        ]

    def _investigation_update(self) -> str:
        """Generate investigation update comment."""
        return f"""## Investigation Update

### Metrics Analysis
- Error rate elevated on buffer acquisition endpoint
- Connection pool utilization at 100%
- Latency p99 increased 40x

### Log Analysis
Found correlated errors:
```
{self._get_log_pattern()}
```

### Hypothesis
Possible resource contention under high concurrency.
"""

    def _get_log_pattern(self) -> str:
        """Get log pattern from symptoms."""
        if self.pattern.observable_symptoms and self.pattern.observable_symptoms.log_messages:
            return self.pattern.observable_symptoms.log_messages[0].pattern
        return "ERROR: operation failed"

    def _senior_input(self) -> str:
        """Generate senior engineer input."""
        files = self.pattern.injection.files if self.pattern.injection else []
        primary_file = files[0].path if files else "unknown"

        return f"""This looks like a race condition we've seen before.

Check `{primary_file}` - specifically the lock acquisition logic.

Look for:
1. Separate check and acquire operations
2. Missing transaction boundaries
3. Non-atomic updates
"""

    def _root_cause_found(self) -> str:
        """Generate root cause found comment."""
        return f"""## Root Cause Identified

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
"""

    def _fix_update(self) -> str:
        """Generate fix update comment."""
        return f"""## Fix Update

PR opened: #{self.rng.randint(1000, 9999)}

Changes:
- Replaced check-then-acquire with atomic operation
- Added concurrent test
- Updated metrics for better observability

Currently in review. Will deploy once approved.
"""

    def _generate_activity(self) -> list[dict[str, Any]]:
        """Generate issue activity timeline."""
        activities = [
            (-120, "created", "Issue created from incident alert"),
            (-115, "state_change", "Status changed from Triage to In Progress"),
            (-115, "assignee_change", "Assigned to On-Call Engineer"),
            (-90, "label_added", "Added label: investigation"),
            (-30, "label_added", "Added label: root-cause-found"),
            (-10, "attachment_added", "Added PR link"),
        ]

        return [
            {
                "id": self.random_uuid()[:8],
                "type": activity_type,
                "description": desc,
                "createdAt": self.random_timestamp(offset_minutes=offset),
            }
            for offset, activity_type, desc in activities
        ]

    def _generate_related(self) -> list[dict[str, Any]]:
        """Generate related issues."""
        related = []

        if self.pattern.related_patterns:
            for rp in self.pattern.related_patterns[:2]:
                related.append({
                    "id": self.random_uuid()[:8],
                    "identifier": f"ENG-{self.rng.randint(100, 999)}",
                    "title": f"[Investigation] {rp.id}: {rp.description[:50]}",
                    "relationship": rp.relationship,
                    "state": "Backlog",
                })

        return related

    def _generate_attachments(self) -> list[dict[str, Any]]:
        """Generate issue attachments."""
        return [
            {
                "id": self.random_uuid()[:8],
                "title": "Grafana Dashboard Screenshot",
                "url": f"https://attachments.linear.app/{self.random_uuid()}/dashboard.png",
                "type": "image/png",
            },
            {
                "id": self.random_uuid()[:8],
                "title": "Sentry Error Export",
                "url": f"https://attachments.linear.app/{self.random_uuid()}/sentry_export.json",
                "type": "application/json",
            },
        ]

    def save(self, output_dir: Path) -> list[Path]:
        """Save Linear artifacts to files."""
        linear_dir = output_dir / "linear"
        linear_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save issue
        issue_path = linear_dir / "issue.json"
        issue_path.write_text(json.dumps(artifacts["issue"], indent=2))
        files.append(issue_path)

        # Save comments
        comments_path = linear_dir / "comments.json"
        comments_path.write_text(json.dumps(artifacts["comments"], indent=2))
        files.append(comments_path)

        # Save full export
        export_path = linear_dir / "linear_export.json"
        export_path.write_text(json.dumps(artifacts, indent=2))
        files.append(export_path)

        # Save readable markdown
        md_path = linear_dir / "issue.md"
        md_path.write_text(self._format_markdown(artifacts))
        files.append(md_path)

        return files

    def _format_markdown(self, artifacts: dict[str, Any]) -> str:
        """Format issue as markdown."""
        issue = artifacts["issue"]
        comments = artifacts["comments"]

        lines = [
            f"# {issue['identifier']}: {issue['title']}\n",
            f"**Status:** {issue['state']['name']}",
            f"**Priority:** {issue['priorityLabel']}",
            f"**Assignee:** {issue['assignee']['name']}",
            f"**Created:** {issue['createdAt']}",
            f"**Labels:** {', '.join(l['name'] for l in issue['labels'])}",
            "\n---\n",
            issue["description"],
            "\n---\n",
            "## Comments\n",
        ]

        for comment in comments:
            lines.append(f"### {comment['user']['name']} - {comment['createdAt']}\n")
            lines.append(comment["body"])
            lines.append("\n---\n")

        return "\n".join(lines)
