"""Slack message artifact generator for incident communications."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .generator import ArtifactGenerator
from ..models import Pattern


class SlackArtifactGenerator(ArtifactGenerator):
    """Generates realistic Slack incident channel messages."""

    def generate(self) -> dict[str, Any]:
        """Generate Slack channel conversation for incident."""
        return {
            "channel": self._generate_channel_info(),
            "messages": self._generate_messages(),
            "threads": self._generate_threads(),
        }

    def _generate_channel_info(self) -> dict[str, Any]:
        """Generate Slack channel metadata."""
        return {
            "id": f"C{self.random_uuid()[:8].upper()}",
            "name": f"incident-{self.pattern.id.lower()}-{self.rng.randint(100, 999)}",
            "purpose": f"Incident channel for {self.pattern.name}",
            "created": self.random_timestamp(offset_minutes=-120),
            "topic": f"Status: INVESTIGATING | Severity: SEV-2 | IC: @oncall-engineer",
            "num_members": self.rng.randint(5, 20),
        }

    def _generate_messages(self) -> list[dict[str, Any]]:
        """Generate incident channel message timeline."""
        messages = []

        # Incident timeline
        timeline = [
            (-120, "incident-bot", self._alert_message()),
            (-115, "oncall-engineer", "Acknowledged. Looking into this now."),
            (-110, "oncall-engineer", self._initial_investigation()),
            (-100, "senior-engineer", "I've seen this before. Check the buffer locking code."),
            (-90, "oncall-engineer", self._metrics_findings()),
            (-80, "oncall-engineer", self._log_findings()),
            (-60, "senior-engineer", self._code_review_hint()),
            (-45, "oncall-engineer", self._root_cause_hypothesis()),
            (-30, "tech-lead", "Good find. Let's get a fix in."),
            (-15, "oncall-engineer", self._fix_in_progress()),
            (-5, "oncall-engineer", self._fix_deployed()),
            (0, "incident-bot", self._resolution_message()),
        ]

        for offset, user, text in timeline:
            messages.append({
                "ts": self._slack_timestamp(offset),
                "user": user,
                "text": text,
                "type": "message",
                "reactions": self._maybe_reactions(),
            })

        return messages

    def _generate_threads(self) -> list[dict[str, Any]]:
        """Generate threaded discussions."""
        return [
            {
                "parent_ts": self._slack_timestamp(-100),
                "replies": [
                    {
                        "ts": self._slack_timestamp(-98),
                        "user": "oncall-engineer",
                        "text": "Which file should I look at specifically?",
                    },
                    {
                        "ts": self._slack_timestamp(-95),
                        "user": "senior-engineer",
                        "text": f"Start with `{self._get_primary_file()}` - the lock acquisition logic",
                    },
                ],
            },
            {
                "parent_ts": self._slack_timestamp(-45),
                "replies": [
                    {
                        "ts": self._slack_timestamp(-43),
                        "user": "tech-lead",
                        "text": "Can you explain more? What's the race window?",
                    },
                    {
                        "ts": self._slack_timestamp(-40),
                        "user": "oncall-engineer",
                        "text": self._detailed_explanation(),
                    },
                ],
            },
        ]

    def _alert_message(self) -> str:
        """Generate initial alert message."""
        symptoms = self.pattern.observable_symptoms
        user_symptoms = symptoms.user_visible if symptoms else []

        symptom_text = ""
        if user_symptoms:
            symptom_text = "\n".join(f"  - {s.symptom}" for s in user_symptoms[:3])

        return f"""🚨 *INCIDENT DETECTED*

*Service:* {self.pattern.target_codebase.name}
*Severity:* SEV-2
*Alert:* {self.pattern.name}

*Symptoms Reported:*
{symptom_text or "  - Service degradation detected"}

*Affected Users:* ~{self.rng.randint(50, 500)} users
*Error Rate:* {self.rng.uniform(1, 10):.1f}% (baseline: 0.1%)

<@oncall-engineer> has been paged.
"""

    def _initial_investigation(self) -> str:
        """Generate initial investigation message."""
        return f"""Starting investigation. Here's what I see so far:

1. ✅ Service is up and responding
2. ⚠️ Error rate elevated for `/api/buffers/acquire` endpoint
3. ⚠️ Latency p99 increased from 50ms to 2000ms
4. 🔍 Checking logs and metrics now...

Dashboard: <https://grafana.internal/d/{self.pattern.id.lower()}|{self.pattern.id} Dashboard>
"""

    def _metrics_findings(self) -> str:
        """Generate metrics analysis message."""
        metrics = self.pattern.observable_symptoms.metrics if self.pattern.observable_symptoms else []

        metric_text = ""
        for m in metrics[:3]:
            metric_text += f"  - `{m.name}`: {m.anomaly or 'elevated'}\n"

        return f"""📊 *Metrics Analysis*

Found some anomalies:
{metric_text or "  - Connection pool utilization: 100%"}
  - Request queue depth: growing unbounded
  - Successful lock acquisitions: trending down

This looks like resource contention, not a service outage.
"""

    def _log_findings(self) -> str:
        """Generate log analysis message."""
        logs = self.pattern.observable_symptoms.log_messages if self.pattern.observable_symptoms else []

        log_text = ""
        for log in logs[:3]:
            log_text += f"```{log.pattern}```\n"

        return f"""📝 *Log Analysis*

Found these patterns in the last hour:
{log_text or "```ERROR: lock acquisition failed```"}

Frequency: {self.rng.randint(100, 1000)} occurrences in last 30 min

The errors correlate with the latency spike.
"""

    def _code_review_hint(self) -> str:
        """Generate hint from senior engineer."""
        if self.pattern.golden_path and self.pattern.golden_path.steps:
            key_insight = None
            for step in self.pattern.golden_path.steps:
                if step.key_insight:
                    key_insight = step.key_insight
                    break

            if key_insight:
                return f"""I think I know what this is.

Check the lock acquisition flow - there might be a timing issue.

Hint: {key_insight}
"""

        return """Look at the buffer lock acquisition code. There might be a race condition between the availability check and the actual lock acquisition."""

    def _root_cause_hypothesis(self) -> str:
        """Generate root cause identification message."""
        failure_modes = self.pattern.failure_modes
        if failure_modes and failure_modes.common:
            avoid = failure_modes.common[0].description
        else:
            avoid = "simple timeout increase"

        files = self.pattern.injection.files if self.pattern.injection else []
        primary_file = files[0].path if files else "unknown"

        return f"""🎯 *Root Cause Identified*

Found it! In `{primary_file}`:

The issue is a TOCTOU (Time-of-check to time-of-use) race condition:
1. We check if buffer is available (separate query)
2. Then we try to acquire the lock (another query)
3. Between steps 1 and 2, another request can acquire the lock

Under high concurrency, this causes conflicts.

*NOT the fix:* {avoid}
*Actual fix:* Make the check-and-acquire atomic (single transaction)
"""

    def _detailed_explanation(self) -> str:
        """Generate detailed technical explanation."""
        return """Here's the timeline of a race:

```
T0: Request A checks availability → buffer is free
T1: Request B checks availability → buffer is free
T2: Request A acquires lock → success
T3: Request B acquires lock → CONFLICT (A already has it)
```

The window between T0-T2 is the race window. Under load, this happens frequently.

Fix: Use `SELECT ... FOR UPDATE` or atomic `UPDATE ... WHERE ... RETURNING` to make the check-and-acquire a single atomic operation.
"""

    def _fix_in_progress(self) -> str:
        """Generate fix in progress message."""
        solutions = None
        if self.pattern.golden_path:
            for step in self.pattern.golden_path.steps:
                if step.solutions:
                    solutions = step.solutions
                    break

        fix_preview = ""
        if solutions:
            # Handle both dict and object access patterns
            preferred = solutions.get("preferred") if isinstance(solutions, dict) else getattr(solutions, "preferred", None)
            if preferred:
                lines = preferred.strip().split("\n")[:5]
                fix_preview = "\n".join(lines) + "\n..."

        return f"""🔧 *Fix In Progress*

PR opened: <https://github.com/org/repo/pull/{self.rng.randint(1000, 9999)}|Fix buffer lock race condition>

Approach:
- Replace check-then-acquire with atomic operation
- Add concurrent test to prevent regression

```rust
{fix_preview or "// Atomic lock acquisition"}
```

Running tests now...
"""

    def _fix_deployed(self) -> str:
        """Generate fix deployed message."""
        return f"""✅ *Fix Deployed*

- PR merged and deployed to production
- Canary looks good (0 conflicts in last 5 min)
- Error rate back to baseline
- Monitoring for 15 more minutes before resolving

Metrics: <https://grafana.internal/d/{self.pattern.id.lower()}|Dashboard>
"""

    def _resolution_message(self) -> str:
        """Generate incident resolution message."""
        return f"""🎉 *INCIDENT RESOLVED*

*Duration:* 2 hours 0 minutes
*Root Cause:* Race condition in buffer lock acquisition
*Resolution:* Made lock acquisition atomic
*Impact:* ~{self.rng.randint(200, 2000)} users affected

*Action Items:*
- [ ] Schedule post-mortem
- [ ] Add alerting for `buffer_conflicts_total`
- [ ] Review other lock acquisition code for similar issues

Channel will be archived in 7 days.
"""

    def _slack_timestamp(self, offset_minutes: int) -> str:
        """Generate Slack-style timestamp."""
        ts = self.base_time + timedelta(minutes=offset_minutes)
        return f"{ts.timestamp():.6f}"

    def _maybe_reactions(self) -> list[dict[str, Any]]:
        """Maybe add some reactions."""
        if self.rng.random() > 0.7:
            reactions = ["eyes", "white_check_mark", "thumbsup", "raised_hands"]
            return [{"name": self.random_choice(reactions), "count": self.rng.randint(1, 5)}]
        return []

    def _get_primary_file(self) -> str:
        """Get primary injection file."""
        if self.pattern.injection and self.pattern.injection.files:
            return self.pattern.injection.files[0].path
        return "unknown.rs"

    def save(self, output_dir: Path) -> list[Path]:
        """Save Slack artifacts to files."""
        slack_dir = output_dir / "slack"
        slack_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.generate()
        files = []

        # Save full channel export
        export_path = slack_dir / "channel_export.json"
        export_path.write_text(json.dumps(artifacts, indent=2))
        files.append(export_path)

        # Save readable transcript
        transcript = self._format_transcript(artifacts)
        transcript_path = slack_dir / "incident_transcript.md"
        transcript_path.write_text(transcript)
        files.append(transcript_path)

        return files

    def _format_transcript(self, artifacts: dict[str, Any]) -> str:
        """Format messages as readable markdown transcript."""
        lines = [
            f"# Incident Channel: #{artifacts['channel']['name']}\n",
            f"**Topic:** {artifacts['channel']['topic']}\n",
            "---\n",
        ]

        for msg in artifacts["messages"]:
            user = msg["user"]
            text = msg["text"]
            lines.append(f"**@{user}**\n{text}\n")
            lines.append("---\n")

        return "\n".join(lines)
