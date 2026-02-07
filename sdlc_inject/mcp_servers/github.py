"""Mock GitHub MCP server for code and issue tracking simulation.

Generates realistic issues, PRs, commits, and code context
based on the failure pattern being debugged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import BaseMCPServer, Response
from .rate_limiter import RateLimitConfig
from ..models import Pattern


class GitHubMCPServer(BaseMCPServer):
    """Mock GitHub API server.

    Simulates GitHub's API with endpoints for:
    - Issues and issue comments
    - Pull requests
    - Commits and blame
    - Repository information

    Data is deterministically generated from the pattern's
    injection points and related context.
    """

    service_name = "github"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        super().__init__(pattern, seed, rate_limit_config)

    def get_endpoints(self) -> list[str]:
        return [
            "GET /repos/{owner}/{repo}",
            "GET /repos/{owner}/{repo}/issues",
            "GET /repos/{owner}/{repo}/issues/{number}",
            "GET /repos/{owner}/{repo}/issues/{number}/comments",
            "GET /repos/{owner}/{repo}/pulls",
            "GET /repos/{owner}/{repo}/pulls/{number}",
            "GET /repos/{owner}/{repo}/commits",
            "GET /repos/{owner}/{repo}/commits/{sha}",
            "GET /repos/{owner}/{repo}/blame/{path}",
        ]

    def _initialize_data(self) -> None:
        """Generate GitHub data from pattern context."""
        self.repo: dict[str, Any] = {}
        self.issues: list[dict[str, Any]] = []
        self.issue_comments: dict[int, list[dict[str, Any]]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []
        self.blame_data: dict[str, list[dict[str, Any]]] = {}

        # Generate repository info
        self._generate_repo()

        # Generate issues
        self._generate_issues()

        # Generate PRs
        self._generate_pulls()

        # Generate commits
        self._generate_commits()

        # Generate blame data for injection files
        self._generate_blame()

    def _generate_repo(self) -> None:
        """Generate repository information."""
        if self.pattern.target_codebase:
            name = self.pattern.target_codebase.name
            language = self.pattern.target_codebase.language or "Python"
        else:
            name = "main-service"
            language = "Python"

        self.repo = {
            "id": self.rng.randint(100000, 999999),
            "name": name,
            "full_name": f"company/{name}",
            "owner": {
                "login": "company",
                "type": "Organization",
            },
            "private": True,
            "description": f"Main {name} service repository",
            "default_branch": "main",
            "language": language,
            "created_at": (datetime.now() - timedelta(days=730)).isoformat() + "Z",
            "updated_at": datetime.now().isoformat() + "Z",
            "pushed_at": datetime.now().isoformat() + "Z",
            "open_issues_count": 0,  # Updated after generating issues
        }

    def _generate_issues(self) -> None:
        """Generate related issues."""
        # Issue about the bug (primary)
        primary_issue = self._generate_primary_issue()
        self.issues.append(primary_issue)
        self._generate_issue_comments(primary_issue["number"], is_primary=True)

        # Related issues (noise)
        noise_titles = [
            "Refactor database connection handling",
            "Update dependencies to latest versions",
            "Add monitoring for API latency",
            "Improve error messages in logs",
            "Document deployment process",
        ]

        for i, title in enumerate(noise_titles):
            issue = {
                "id": self.rng.randint(100000, 999999),
                "number": i + 2,
                "title": title,
                "body": f"Task: {title}\n\nThis is a routine improvement task.",
                "state": self._random_choice(["open", "closed"]),
                "user": {"login": self._random_choice(["dev1", "dev2", "dev3"])},
                "labels": [{"name": self._random_choice(["enhancement", "documentation", "tech-debt"])}],
                "created_at": self._random_timestamp(30, 7).isoformat() + "Z",
                "updated_at": self._random_timestamp(7, 0).isoformat() + "Z",
                "comments": self.rng.randint(0, 5),
            }
            self.issues.append(issue)
            if self.rng.random() < 0.3:
                self._generate_issue_comments(issue["number"], is_primary=False)

        self.repo["open_issues_count"] = sum(1 for i in self.issues if i["state"] == "open")

    def _generate_primary_issue(self) -> dict[str, Any]:
        """Generate the main bug issue."""
        category = (self.pattern.subcategory or self.pattern.category).lower()

        if "race" in category:
            title = "Intermittent data corruption under load"
            labels = [{"name": "bug"}, {"name": "P1"}, {"name": "concurrency"}]
        elif "split" in category or "partition" in category:
            title = "Inconsistent state across replicas"
            labels = [{"name": "bug"}, {"name": "P1"}, {"name": "distributed"}]
        elif "clock" in category or "time" in category:
            title = "Timestamp ordering issues causing conflicts"
            labels = [{"name": "bug"}, {"name": "P1"}, {"name": "timing"}]
        else:
            title = f"Bug: {self.pattern.name}"
            labels = [{"name": "bug"}, {"name": "P1"}]

        body_parts = [
            f"## Description\n\nWe're seeing {self.pattern.name.lower()} in production.\n",
            "## Symptoms\n",
        ]

        if self.pattern.observable_symptoms and self.pattern.observable_symptoms.user_visible:
            for symptom in self.pattern.observable_symptoms.user_visible[:3]:
                body_parts.append(f"- {symptom.symptom}\n")

        body_parts.append("\n## Reproduction\n\nOccurs intermittently under high load.\n")

        if self.pattern.observable_symptoms and self.pattern.observable_symptoms.log_messages:
            body_parts.append("\n## Related Logs\n```\n")
            for log in self.pattern.observable_symptoms.log_messages[:3]:
                body_parts.append(f"{log.pattern}\n")
            body_parts.append("```\n")

        return {
            "id": self.rng.randint(100000, 999999),
            "number": 1,
            "title": title,
            "body": "".join(body_parts),
            "state": "open",
            "user": {"login": "oncall-engineer"},
            "labels": labels,
            "assignees": [{"login": "senior-dev"}],
            "created_at": self._random_timestamp(48, 24).isoformat() + "Z",
            "updated_at": self._random_timestamp(2, 0).isoformat() + "Z",
            "comments": 5,
        }

    def _generate_issue_comments(self, issue_number: int, is_primary: bool) -> None:
        """Generate comments for an issue."""
        comments = []
        base_time = datetime.now() - timedelta(hours=24)

        if is_primary:
            comment_templates = [
                ("oncall-engineer", "I've reproduced this in staging. Definitely related to concurrent access."),
                ("senior-dev", "Looking at the code, I think the issue is in the lock acquisition path."),
                ("tech-lead", "We should add more instrumentation to understand the exact sequence of events."),
                ("oncall-engineer", "Added trace logging. The logs show two threads entering the critical section."),
                ("senior-dev", "Found it - there's a check-then-act pattern without proper synchronization."),
            ]
        else:
            comment_templates = [
                ("dev1", "I can take this one."),
                ("dev2", "Looks good, let's prioritize for next sprint."),
            ]

        for i, (user, text) in enumerate(comment_templates):
            ts = base_time + timedelta(hours=i * 2)
            comments.append({
                "id": self.rng.randint(100000, 999999),
                "user": {"login": user},
                "body": text,
                "created_at": ts.isoformat() + "Z",
            })

        self.issue_comments[issue_number] = comments

    def _generate_pulls(self) -> None:
        """Generate pull requests."""
        # PR that introduced the bug (if we have injection files)
        if self.pattern.injection and self.pattern.injection.files:
            file_path = self.pattern.injection.files[0].path
            culprit_pr = {
                "id": self.rng.randint(100000, 999999),
                "number": 100 + self.rng.randint(1, 50),
                "title": f"Refactor: Improve performance of {file_path.split('/')[-1].replace('.rs', '').replace('.py', '')}",
                "body": "This PR improves performance by reducing lock contention.\n\n## Changes\n- Optimized critical path\n- Reduced lock scope",
                "state": "closed",
                "merged": True,
                "user": {"login": "junior-dev"},
                "base": {"ref": "main"},
                "head": {"ref": "perf/optimize-locks"},
                "merged_at": self._random_timestamp(72, 48).isoformat() + "Z",
                "created_at": self._random_timestamp(96, 72).isoformat() + "Z",
                "files_changed": [file_path],
            }
            self.pulls.append(culprit_pr)

        # Fix PR (in progress)
        fix_pr = {
            "id": self.rng.randint(100000, 999999),
            "number": 200 + self.rng.randint(1, 20),
            "title": f"Fix: Resolve {self.pattern.id} - {self.pattern.name}",
            "body": "## Summary\nFixes the issue identified in #1\n\n## Solution\nImplement atomic lock acquisition",
            "state": "open",
            "merged": False,
            "user": {"login": "senior-dev"},
            "base": {"ref": "main"},
            "head": {"ref": f"fix/{self.pattern.id.lower()}"},
            "created_at": self._random_timestamp(4, 2).isoformat() + "Z",
            "draft": True,
        }
        self.pulls.append(fix_pr)

    def _generate_commits(self) -> None:
        """Generate recent commits."""
        commit_messages = [
            ("junior-dev", "Optimize lock acquisition performance"),
            ("senior-dev", "Add error handling for edge cases"),
            ("dev1", "Update dependencies"),
            ("dev2", "Add unit tests for new feature"),
            ("junior-dev", "Refactor configuration loading"),
        ]

        base_time = datetime.now() - timedelta(days=7)
        for i, (author, message) in enumerate(commit_messages):
            sha = self._random_id(length=40)
            ts = base_time + timedelta(days=i)

            self.commits.append({
                "sha": sha,
                "message": message,
                "author": {
                    "login": author,
                    "name": author.replace("-", " ").title(),
                    "email": f"{author}@company.com",
                    "date": ts.isoformat() + "Z",
                },
                "committer": {
                    "login": author,
                    "date": ts.isoformat() + "Z",
                },
                "parents": [{"sha": self._random_id(length=40)}],
            })

    def _generate_blame(self) -> None:
        """Generate blame data for injection files."""
        if not self.pattern.injection or not self.pattern.injection.files:
            return

        for file_info in self.pattern.injection.files:
            path = file_info.path
            blame_lines = []

            # Generate blame for ~100 lines
            authors = ["junior-dev", "senior-dev", "tech-lead", "dev1"]

            for line_no in range(1, 101):
                commit_sha = self._random_id(length=40)
                author = self._random_choice(authors)
                date = self._random_timestamp(90, 0)

                # Make certain lines (where bug would be) from recent commit by junior-dev
                if 40 <= line_no <= 60:
                    author = "junior-dev"
                    date = self._random_timestamp(4, 2)  # Recent

                blame_lines.append({
                    "line": line_no,
                    "commit": {
                        "sha": commit_sha,
                        "author": {"login": author, "date": date.isoformat() + "Z"},
                        "message": self._random_choice([
                            "Initial implementation",
                            "Refactor for performance",
                            "Fix edge case",
                            "Add error handling",
                        ]),
                    },
                })

            self.blame_data[path] = blame_lines

    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Handle GitHub API requests."""
        endpoint = endpoint.rstrip("/")

        # GET /repos/{owner}/{repo}
        match = re.match(r"^/repos/[^/]+/[^/]+$", endpoint)
        if match and method == "GET":
            return Response(200, self.repo)

        # GET /repos/{owner}/{repo}/issues
        match = re.match(r"^/repos/[^/]+/[^/]+/issues$", endpoint)
        if match and method == "GET":
            return self._handle_list_issues(params)

        # GET /repos/{owner}/{repo}/issues/{number}
        match = re.match(r"^/repos/[^/]+/[^/]+/issues/(\d+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_issue(int(match.group(1)))

        # GET /repos/{owner}/{repo}/issues/{number}/comments
        match = re.match(r"^/repos/[^/]+/[^/]+/issues/(\d+)/comments$", endpoint)
        if match and method == "GET":
            return self._handle_get_issue_comments(int(match.group(1)))

        # GET /repos/{owner}/{repo}/pulls
        match = re.match(r"^/repos/[^/]+/[^/]+/pulls$", endpoint)
        if match and method == "GET":
            return self._handle_list_pulls(params)

        # GET /repos/{owner}/{repo}/pulls/{number}
        match = re.match(r"^/repos/[^/]+/[^/]+/pulls/(\d+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_pull(int(match.group(1)))

        # GET /repos/{owner}/{repo}/commits
        match = re.match(r"^/repos/[^/]+/[^/]+/commits$", endpoint)
        if match and method == "GET":
            return Response(200, self.commits)

        # GET /repos/{owner}/{repo}/commits/{sha}
        match = re.match(r"^/repos/[^/]+/[^/]+/commits/([a-f0-9]+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_commit(match.group(1))

        # GET /repos/{owner}/{repo}/blame/{path}
        match = re.match(r"^/repos/[^/]+/[^/]+/blame/(.+)$", endpoint)
        if match and method == "GET":
            return self._handle_get_blame(match.group(1))

        return Response(404, {"error": f"Endpoint not found: {method} {endpoint}"})

    def _handle_list_issues(self, params: dict[str, Any]) -> Response:
        """List issues."""
        issues = self.issues.copy()

        state = params.get("state", "open")
        if state != "all":
            issues = [i for i in issues if i["state"] == state]

        return Response(200, issues)

    def _handle_get_issue(self, number: int) -> Response:
        """Get a specific issue."""
        for issue in self.issues:
            if issue["number"] == number:
                return Response(200, issue)
        return Response(404, {"error": f"Issue not found: {number}"})

    def _handle_get_issue_comments(self, number: int) -> Response:
        """Get comments for an issue."""
        if number not in self.issue_comments:
            return Response(200, [])
        return Response(200, self.issue_comments[number])

    def _handle_list_pulls(self, params: dict[str, Any]) -> Response:
        """List pull requests."""
        pulls = self.pulls.copy()

        state = params.get("state", "open")
        if state != "all":
            pulls = [p for p in pulls if p["state"] == state]

        return Response(200, pulls)

    def _handle_get_pull(self, number: int) -> Response:
        """Get a specific pull request."""
        for pr in self.pulls:
            if pr["number"] == number:
                return Response(200, pr)
        return Response(404, {"error": f"Pull request not found: {number}"})

    def _handle_get_commit(self, sha: str) -> Response:
        """Get a specific commit."""
        for commit in self.commits:
            if commit["sha"].startswith(sha):
                return Response(200, commit)
        return Response(404, {"error": f"Commit not found: {sha}"})

    def _handle_get_blame(self, path: str) -> Response:
        """Get blame for a file."""
        if path in self.blame_data:
            return Response(200, {"blame": self.blame_data[path]})

        # Generate blame on the fly for unknown paths
        blame_lines = []
        for line_no in range(1, 51):
            blame_lines.append({
                "line": line_no,
                "commit": {
                    "sha": self._random_id(length=40),
                    "author": {"login": "unknown", "date": self._random_timestamp(90, 0).isoformat() + "Z"},
                    "message": "Historical commit",
                },
            })
        return Response(200, {"blame": blame_lines})
