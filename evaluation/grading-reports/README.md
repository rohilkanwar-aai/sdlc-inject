# Grading Reports Archive

Agent incident reports and grading analyses from evaluation runs.

## Naming Convention

```
{pattern}-{codebase}-run{N}-{type}.md
```

Examples:
- `cascade-009-otel-run1-incident-report.md` -- CASCADE-009 on OTel Demo, Run 1
- `cascade-012-train-ticket-run3-grading.md` -- CASCADE-012 on Train Ticket, Run 3 grading analysis
- `cascade-011-train-ticket-run1-incident-report.md` -- CASCADE-011 on Train Ticket, Run 1

## After Each Test Run

Copy the agent's incident report from the target codebase:

```bash
# From the train-ticket directory:
cp train-ticket/INCIDENT_REPORT.md evaluation/grading-reports/cascade-011-train-ticket-runN-incident-report.md

# From the opentelemetry-demo directory:
cp opentelemetry-demo/INCIDENT_REPORT.md evaluation/grading-reports/cascade-012-otel-runN-incident-report.md
```

Then write a grading analysis comparing the report against the golden path.
