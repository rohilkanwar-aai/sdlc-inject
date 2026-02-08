"""SQLite-backed MCP server helpers.

Read from the traffic simulator's SQLite database instead of static YAML.
"""

import sqlite3
from typing import Any


def query_logs(db_path: str, service: str = "", level: str = "",
               grep: str = "", since: str = "", limit: int = 50) -> dict:
    """Query logs from the traffic database.

    Args:
        db_path: Path to the SQLite database.
        service: Filter by service name (exact match).
        level: Filter by log level (INFO, WARN, ERROR).
        grep: Keyword search in message and function fields.
        since: ISO timestamp -- only return logs after this time.
        limit: Maximum number of log entries to return.

    Returns:
        Dict with entries list, total count, and has_more flag.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM logs WHERE 1=1"
    args = []
    if service:
        query += " AND service = ?"
        args.append(service)
    if level:
        query += " AND level = ?"
        args.append(level.upper())
    if grep:
        query += " AND (message LIKE ? OR function LIKE ?)"
        args.extend([f"%{grep}%", f"%{grep}%"])
    if since:
        query += " AND timestamp > ?"
        args.append(since)

    # Count total
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, args).fetchone()[0]

    query += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)

    rows = conn.execute(query, args).fetchall()
    entries = [dict(r) for r in rows]
    conn.close()

    return {"entries": entries, "total": total, "has_more": total > limit}


def query_metrics(db_path: str, metric_name: str) -> dict:
    """Query latest metric value from the traffic database.

    Args:
        db_path: Path to the SQLite database.
        metric_name: Exact metric name or partial name for fuzzy matching.

    Returns:
        Dict with current value, timestamp, and recent history.
        If not found, returns similar metric names or an error.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get latest value
    row = conn.execute(
        "SELECT * FROM metrics WHERE name = ? ORDER BY timestamp DESC LIMIT 1",
        (metric_name,)
    ).fetchone()

    if not row:
        # Fuzzy match
        rows = conn.execute(
            "SELECT DISTINCT name FROM metrics WHERE name LIKE ? LIMIT 10",
            (f"%{metric_name}%",)
        ).fetchall()
        conn.close()
        if rows:
            return {"matches": [{"name": r["name"]} for r in rows], "note": "Exact metric not found, showing similar."}
        return {"error": "Metric not found", "available": []}

    # Get historical values
    history = conn.execute(
        "SELECT timestamp, value FROM metrics WHERE name = ? ORDER BY timestamp DESC LIMIT 10",
        (metric_name,)
    ).fetchall()
    conn.close()

    return {
        "query": metric_name,
        "result": {
            "current": row["value"],
            "timestamp": row["timestamp"],
            "history": [{"timestamp": h["timestamp"], "value": h["value"]} for h in history],
        }
    }


def list_metrics(db_path: str) -> dict:
    """List all available metrics.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Dict with list of metric names and their latest values.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT DISTINCT name, MAX(value) as latest_value FROM metrics GROUP BY name ORDER BY name"
    ).fetchall()
    conn.close()
    return {"metrics": [{"name": r[0], "latest_value": r[1]} for r in rows]}


def query_sentry(db_path: str, project: str = "") -> dict:
    """Query Sentry events from the traffic database.

    Args:
        db_path: Path to the SQLite database.
        project: Optional project name filter.

    Returns:
        Dict with aggregated issues (grouped by project and title) and total count.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if project:
        rows = conn.execute(
            "SELECT project, title, level, COUNT(*) as count, MAX(timestamp) as last_seen "
            "FROM sentry_events WHERE project = ? GROUP BY project, title ORDER BY count DESC",
            (project,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT project, title, level, COUNT(*) as count, MAX(timestamp) as last_seen "
            "FROM sentry_events GROUP BY project, title ORDER BY count DESC LIMIT 50"
        ).fetchall()

    conn.close()
    return {"issues": [dict(r) for r in rows], "total": len(rows)}


def list_sentry_projects(db_path: str) -> dict:
    """List Sentry projects with issue counts.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Dict with list of projects and their distinct issue counts.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT project, COUNT(DISTINCT title) as issue_count FROM sentry_events GROUP BY project"
    ).fetchall()
    conn.close()
    return {"projects": [{"name": r[0], "issue_count": r[1]} for r in rows]}


def query_slack(db_path: str, channel: str = "", limit: int = 50, cursor: int = 0) -> dict:
    """Query Slack messages from the traffic database.

    Args:
        db_path: Path to the SQLite database.
        channel: Channel name to query (required).
        limit: Maximum number of messages to return.
        cursor: Pagination offset.

    Returns:
        Dict with messages list, total count, and has_more flag.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if channel:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM slack_messages WHERE channel = ?", (channel,)
        ).fetchone()
        total = total_row[0]
        rows = conn.execute(
            "SELECT * FROM slack_messages WHERE channel = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (channel, limit, cursor)
        ).fetchall()
    else:
        total = 0
        rows = []

    conn.close()
    messages = [{"user": r["user_name"], "text": r["text"], "timestamp": r["timestamp"]} for r in rows]
    return {"channel": channel, "messages": messages, "total": total, "has_more": cursor + limit < total}


def list_slack_channels(db_path: str) -> dict:
    """List Slack channels with message counts.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Dict with list of channels and their message counts.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT channel, COUNT(*) as message_count FROM slack_messages GROUP BY channel"
    ).fetchall()
    conn.close()
    return {"channels": [{"name": r[0], "message_count": r[1]} for r in rows]}


def search_logs(db_path: str, query: str, limit: int = 20) -> dict:
    """Search logs across all services.

    Args:
        db_path: Path to the SQLite database.
        query: Keyword to search for in log messages.
        limit: Maximum number of results.

    Returns:
        Dict with matching log entries and total count.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM logs WHERE message LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


def search_slack(db_path: str, query: str, limit: int = 20) -> dict:
    """Search Slack messages across all channels.

    Args:
        db_path: Path to the SQLite database.
        query: Keyword to search for in message text.
        limit: Maximum number of results.

    Returns:
        Dict with matching messages and total count.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM slack_messages WHERE text LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return {"results": [{"channel": r["channel"], "user": r["user_name"], "text": r["text"], "timestamp": r["timestamp"]} for r in rows], "total": len(rows)}
