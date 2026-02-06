"""GitHub issues and PR comments artifact generator."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class GitHubArtifactGenerator(ArtifactGenerator):
    """Generates realistic GitHub issues, PRs, and comments."""

    def generate(self) -> dict[str, Any]:
        """Generate GitHub artifacts."""
        return {
            "issue": self._generate_issue(),
            "pull_request": self._generate_pr(),
            "issue_comments": self._generate_issue_comments(),
            "pr_comments": self._generate_pr_comments(),
            "commit": self._generate_commit(),
        }

    def _generate_issue(self) -> dict[str, Any]:
        """Generate a bug report issue."""
        symptoms = self.pattern.observable_symptoms
        user_symptoms = symptoms.user_visible if symptoms else []

        body = self._build_issue_body(user_symptoms)

        return {
            "id": self.rng.randint(1000000, 9999999),
            "number": self.rng.randint(1000, 9999),
            "title": f"[Bug] {self.pattern.name}",
            "body": body,
            "state": "open",
            "labels": self._generate_labels(),
            "user": {
                "login": "affected-user",
                "id": self.rng.randint(1000, 99999),
                "type": "User",
            },
            "assignees": [
                {
                    "login": "oncall-engineer",
                    "id": self.rng.randint(1000, 99999),
                }
            ],
            "milestone": {
                "title": "v0.130.0",
                "number": self.rng.randint(10, 50),
            },
            "created_at": self.random_timestamp(offset_minutes=-180),
            "updated_at": self.random_timestamp(offset_minutes=-10),
            "comments": self.rng.randint(5, 15),
            "html_url": f"https://github.com/org/{self.pattern.target_codebase.name}/issues/{self.rng.randint(1000, 9999)}",
        }

    def _build_issue_body(self, user_symptoms: list) -> str:
        """Build issue body from pattern."""
        symptom_list = ""
        for s in user_symptoms[:5]:
            symptom_list += f"- {s.symptom}\n"

        reproduction = ""
        if self.pattern.trigger and self.pattern.trigger.reproduction_steps:
            for step in self.pattern.trigger.reproduction_steps[:5]:
                reproduction += f"{step.step}. {step.action}\n"

        return f"""## Description

{self.pattern.description[:300]}

## Steps to Reproduce

{reproduction or "1. Use the application under high load"}

## Expected Behavior

Operations should complete successfully without conflicts.

## Actual Behavior

{symptom_list or "- Service experiences intermittent failures"}

## Environment

- OS: macOS 14.0
- App Version: v0.{self.rng.randint(120, 130)}.{self.rng.randint(0, 9)}
- Users affected: ~{self.rng.randint(10, 100)}

## Additional Context

This appears to happen more frequently when multiple users are editing the same file.

Possibly related to #{self.rng.randint(100, 999)} (similar symptoms).
"""

    def _generate_labels(self) -> list[dict[str, str]]:
        """Generate issue labels."""
        return [
            {"name": "bug", "color": "d73a4a"},
            {"name": "priority: high", "color": "ff6b6b"},
            {"name": self.pattern.category.lower().replace(" ", "-"), "color": "0366d6"},
            {"name": "needs-investigation", "color": "fbca04"},
        ]

    def _generate_issue_comments(self) -> list[dict[str, Any]]:
        """Generate issue comments."""
        comments = [
            (-170, "maintainer", self._triage_comment()),
            (-160, "affected-user", "I can reproduce this consistently when collaborating with another user."),
            (-150, "oncall-engineer", self._investigation_comment()),
            (-120, "senior-dev", self._hint_comment()),
            (-60, "oncall-engineer", self._root_cause_comment()),
            (-30, "oncall-engineer", self._fix_pr_comment()),
        ]

        return [
            {
                "id": self.rng.randint(1000000, 9999999),
                "body": body,
                "user": {"login": user},
                "created_at": self.random_timestamp(offset_minutes=offset),
            }
            for offset, user, body in comments
        ]

    def _triage_comment(self) -> str:
        """Generate triage comment."""
        return """Thanks for the report! I've added this to our triage queue.

A few questions:
1. How frequently does this occur?
2. Are both users on the same network?
3. Can you share any logs from when this happens?

cc @oncall-engineer for investigation."""

    def _investigation_comment(self) -> str:
        """Generate investigation comment."""
        return f"""I'm investigating this now.

Initial findings:
- Error rate spiked around the time of the report
- Seeing `{self._get_log_pattern()}` in logs
- Appears to correlate with concurrent buffer operations

Will update once I have more info."""

    def _get_log_pattern(self) -> str:
        """Get a log pattern from the pattern."""
        symptoms = self.pattern.observable_symptoms
        if symptoms and symptoms.log_messages:
            return symptoms.log_messages[0].pattern
        return "lock acquisition failed"

    def _hint_comment(self) -> str:
        """Generate hint from senior developer."""
        files = self.pattern.injection.files if self.pattern.injection else []
        primary_file = files[0].path if files else "unknown"

        return f"""This looks familiar. I think I've seen this before in the lock acquisition code.

@oncall-engineer check `{primary_file}` - specifically look at how we check availability before acquiring a lock. There might be a race window there."""

    def _root_cause_comment(self) -> str:
        """Generate root cause identification comment."""
        return """Found it! This is a classic TOCTOU (Time-of-check to time-of-use) bug.

**The Problem:**
```
1. Check if buffer available (separate query)
2. If yes, acquire lock (another query)
```

Between steps 1 and 2, another request can swoop in and grab the lock.

**The Fix:**
Make the check-and-acquire atomic using a single `UPDATE ... WHERE ... RETURNING` query.

PR incoming."""

    def _fix_pr_comment(self) -> str:
        """Generate PR link comment."""
        return f"""Fix PR opened: #{self.rng.randint(1000, 9999)}

The fix makes lock acquisition atomic and adds concurrent tests to prevent regression.

Will close this issue once the PR is merged."""

    def _generate_pr(self) -> dict[str, Any]:
        """Generate the fix pull request."""
        return {
            "id": self.rng.randint(1000000, 9999999),
            "number": self.rng.randint(1000, 9999),
            "title": f"fix: resolve race condition in buffer lock acquisition",
            "body": self._build_pr_body(),
            "state": "open",
            "draft": False,
            "user": {"login": "oncall-engineer"},
            "head": {"ref": f"fix/buffer-lock-race-{self.rng.randint(100, 999)}"},
            "base": {"ref": "main"},
            "labels": [
                {"name": "bug-fix", "color": "00ff00"},
                {"name": self.pattern.category.lower().replace(" ", "-"), "color": "0366d6"},
            ],
            "created_at": self.random_timestamp(offset_minutes=-25),
            "updated_at": self.random_timestamp(offset_minutes=-5),
            "mergeable": True,
            "additions": self.rng.randint(20, 100),
            "deletions": self.rng.randint(5, 30),
            "changed_files": len(self.pattern.injection.files) if self.pattern.injection else 2,
            "html_url": f"https://github.com/org/{self.pattern.target_codebase.name}/pull/{self.rng.randint(1000, 9999)}",
        }

    def _build_pr_body(self) -> str:
        """Build PR description."""
        files = self.pattern.injection.files if self.pattern.injection else []
        file_list = "\n".join(f"- `{f.path}`" for f in files[:5])

        return f"""## Summary

Fixes #{self.rng.randint(1000, 9999)}

This PR resolves a TOCTOU (Time-of-check to time-of-use) race condition in buffer lock acquisition that was causing conflicts when multiple users tried to open the same file simultaneously.

## Changes

{file_list or "- Modified lock acquisition logic"}

## Root Cause

The previous implementation had a race window:
1. Check if buffer is available (Query 1)
2. If available, acquire lock (Query 2)

Between these two operations, another request could acquire the lock.

## Solution

Replace the two-step process with an atomic operation:
```sql
UPDATE buffers SET locked_by = $1
WHERE id = $2 AND locked_by IS NULL
RETURNING id
```

## Testing

- [x] Added concurrent acquisition test
- [x] Existing tests pass
- [x] Manual testing with 2 clients

## Checklist

- [x] Code follows project conventions
- [x] Tests added/updated
- [x] Documentation updated (if needed)
"""

    def _generate_pr_comments(self) -> list[dict[str, Any]]:
        """Generate PR review comments."""
        comments = [
            ("senior-dev", "LGTM! The atomic approach is the right fix. One small suggestion:", True),
            ("oncall-engineer", "Good point, updated.", False),
            ("maintainer", "Approved. Let's get this merged and deployed.", True),
        ]

        return [
            {
                "id": self.rng.randint(1000000, 9999999),
                "body": body,
                "user": {"login": user},
                "created_at": self.random_timestamp(offset_minutes=-20 + i * 5),
                "pull_request_review_id": self.rng.randint(1000000, 9999999) if is_review else None,
            }
            for i, (user, body, is_review) in enumerate(comments)
        ]

    def _generate_commit(self) -> dict[str, Any]:
        """Generate the fix commit."""
        files = self.pattern.injection.files if self.pattern.injection else []

        return {
            "sha": self.random_uuid().replace("-", "")[:40],
            "message": f"""fix: make buffer lock acquisition atomic

Resolves race condition where concurrent requests could both pass
the availability check before either acquired the lock.

Replaces check-then-acquire pattern with atomic UPDATE...RETURNING.

Closes #{self.rng.randint(1000, 9999)}
""",
            "author": {
                "name": "On-Call Engineer",
                "email": "oncall@company.com",
                "date": self.random_timestamp(offset_minutes=-25),
            },
            "committer": {
                "name": "On-Call Engineer",
                "email": "oncall@company.com",
                "date": self.random_timestamp(offset_minutes=-25),
            },
            "files": [
                {
                    "filename": f.path,
                    "status": "modified",
                    "additions": self.rng.randint(5, 30),
                    "deletions": self.rng.randint(2, 15),
                }
                for f in files
            ],
        }

    def save(self, output_dir: Path) -> list[Path]:
        """Save GitHub artifacts to files."""
        gh_dir = output_dir / "github"
        gh_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save issue
        issue_path = gh_dir / "issue.json"
        issue_path.write_text(json.dumps(artifacts["issue"], indent=2))
        files.append(issue_path)

        # Save PR
        pr_path = gh_dir / "pull_request.json"
        pr_path.write_text(json.dumps(artifacts["pull_request"], indent=2))
        files.append(pr_path)

        # Save comments
        comments_path = gh_dir / "issue_comments.json"
        comments_path.write_text(json.dumps(artifacts["issue_comments"], indent=2))
        files.append(comments_path)

        # Save full export
        export_path = gh_dir / "github_export.json"
        export_path.write_text(json.dumps(artifacts, indent=2))
        files.append(export_path)

        # Save readable markdown (issue thread)
        md_path = gh_dir / "issue_thread.md"
        md_path.write_text(self._format_issue_thread(artifacts))
        files.append(md_path)

        return files

    def _format_issue_thread(self, artifacts: dict[str, Any]) -> str:
        """Format issue as readable markdown thread."""
        issue = artifacts["issue"]
        comments = artifacts["issue_comments"]

        lines = [
            f"# {issue['title']}\n",
            f"**Opened by:** @{issue['user']['login']}",
            f"**Labels:** {', '.join(l['name'] for l in issue['labels'])}",
            f"**Assignees:** {', '.join('@' + a['login'] for a in issue['assignees'])}",
            "\n---\n",
            issue["body"],
            "\n---\n",
            "## Comments\n",
        ]

        for comment in comments:
            lines.append(f"### @{comment['user']['login']}\n")
            lines.append(comment["body"])
            lines.append("\n---\n")

        return "\n".join(lines)
