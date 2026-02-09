#!/bin/bash
# Save a test run's artifacts (incident report + prompt used) to the grading archive.
#
# Usage:
#   ./save-run.sh <pattern> <codebase> <run-number>
#
# Example:
#   ./save-run.sh cascade-011 train-ticket 1
#   ./save-run.sh cascade-012 otel 6

set -e

PATTERN="${1:?Usage: ./save-run.sh <pattern> <codebase> <run-number>}"
CODEBASE="${2:?Usage: ./save-run.sh <pattern> <codebase> <run-number>}"
RUN="${3:?Usage: ./save-run.sh <pattern> <codebase> <run-number>}"

DEST="evaluation/grading-reports"
PREFIX="${PATTERN}-${CODEBASE}-run${RUN}"

# Determine source directory
if [ "$CODEBASE" = "otel" ] || [ "$CODEBASE" = "opentelemetry-demo" ]; then
    SRC="opentelemetry-demo"
elif [ "$CODEBASE" = "train-ticket" ]; then
    SRC="train-ticket"
else
    echo "Unknown codebase: $CODEBASE (use 'train-ticket' or 'otel')"
    exit 1
fi

# Find and copy the incident report (try common filenames)
REPORT=""
for name in INCIDENT_REPORT.md incident-report.md incident_report.md formal_investigation_report.md; do
    if [ -f "${SRC}/${name}" ]; then
        REPORT="${SRC}/${name}"
        break
    fi
done

if [ -n "$REPORT" ]; then
    cp "$REPORT" "${DEST}/${PREFIX}-incident-report.md"
    echo "Saved: ${DEST}/${PREFIX}-incident-report.md"
else
    echo "Warning: No incident report found in ${SRC}/"
fi

# Copy the prompt (CLAUDE.md) that was used for this run
if [ -f "${SRC}/CLAUDE.md" ]; then
    cp "${SRC}/CLAUDE.md" "${DEST}/${PREFIX}-prompt.md"
    echo "Saved: ${DEST}/${PREFIX}-prompt.md"
fi

# Clean up project memory so next session starts fresh
echo "Cleaning project memory..."
for dir in ~/.claude/projects/*train-ticket* ~/.claude/projects/*train_ticket* ~/.claude/projects/*tmp*train*; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "  Removed: $dir"
    fi
done

echo "Done. Run 'git add ${DEST}/ && git commit -m \"grade: ${PREFIX}\"' to persist."
