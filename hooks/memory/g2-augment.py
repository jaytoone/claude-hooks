#!/usr/bin/env python3
"""
g2-augment: Auto-augment Grep/Glob results with codebase graph data.

PostToolUse hook for Grep: reads the search pattern, queries codebase-memory-mcp's
SQLite DB directly (no MCP call needed), and injects related code entities as
additionalContext.

Also serves as PreToolUse for Grep|Glob: injects "try graph first" guidance.

DB location: ~/.cache/codebase-memory-mcp/{project-slug}.db
"""
import json
import os
import re
import sqlite3
import sys


def find_db(project_dir):
    """Find the codebase-memory-mcp SQLite DB for this project."""
    cache_dir = os.path.expanduser("~/.cache/codebase-memory-mcp")
    if not os.path.isdir(cache_dir):
        return None
    # Project slug: path with / replaced by -
    slug = project_dir.replace("/", "-").lstrip("-")
    db_path = os.path.join(cache_dir, f"{slug}.db")
    if os.path.exists(db_path):
        return db_path
    # Try partial match
    for f in os.listdir(cache_dir):
        if f.endswith(".db") and os.path.basename(project_dir).lower() in f.lower():
            return os.path.join(cache_dir, f)
    return None


def search_graph(db_path, pattern, limit=5):
    """Search nodes table for matching entities."""
    try:
        db = sqlite3.connect(db_path)
        # Clean pattern: extract likely symbol name
        clean = re.sub(r'[^a-zA-Z0-9_]', '%', pattern)
        rows = db.execute(
            "SELECT DISTINCT label, name, file_path FROM nodes "
            "WHERE name LIKE ? AND label NOT IN ('Variable', 'Section', 'File', 'Folder', 'Project', 'Module') "
            "ORDER BY length(name) ASC LIMIT ?",
            (f"%{clean}%", limit)
        ).fetchall()
        db.close()
        return rows
    except Exception:
        return []


def get_callers(db_path, node_name, limit=3):
    """Find who calls this node."""
    try:
        db = sqlite3.connect(db_path)
        rows = db.execute(
            "SELECT DISTINCT n2.name, n2.file_path FROM edges e "
            "JOIN nodes n1 ON e.target_id = n1.id "
            "JOIN nodes n2 ON e.source_id = n2.id "
            "WHERE n1.name = ? AND e.type = 'CALLS' LIMIT ?",
            (node_name, limit)
        ).fetchall()
        db.close()
        return rows
    except Exception:
        return []


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    hook_event = input_data.get("hook_event_name", "")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Extract search pattern
    pattern = tool_input.get("pattern", "") or tool_input.get("name_pattern", "") or ""
    if not pattern:
        sys.exit(0)

    db_path = find_db(project_dir)

    lines = []

    if hook_event == "PreToolUse":
        # Method 1: Inject guidance before Grep/Glob
        if db_path:
            lines.append(f"[G2-AUTO] codebase graph available for this project.")
            lines.append(f"  Before grep, consider: mcp__codebase-memory-mcp__search_graph(name_pattern=\"{pattern[:30]}\")")
            lines.append(f"  For call chains: mcp__codebase-memory-mcp__trace_call_path(function_name=\"{pattern[:30]}\")")

    elif hook_event == "PostToolUse":
        # Method 2: Augment Grep results with graph data
        if not db_path:
            sys.exit(0)

        results = search_graph(db_path, pattern)
        if results:
            lines.append(f"[G2-GRAPH] Code entities matching '{pattern[:20]}':")
            for label, name, fpath in results:
                callers = get_callers(db_path, name, limit=2)
                caller_str = ""
                if callers:
                    caller_str = f" <- called by: {', '.join(c[0] for c in callers)}"
                lines.append(f"  {label}: {name} @ {fpath}{caller_str}")

    if lines:
        output = {"additionalContext": "\n".join(lines)}
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
