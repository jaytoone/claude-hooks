# claude-hooks

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20WSL2-lightgrey)](https://github.com/anthropics/claude-code)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-%3E%3D1.0-blueviolet)](https://claude.ai/code)

Persistent memory for Claude Code — across sessions, across projects.

---

## The Problem

Claude Code starts fresh every session. No memory of what you built yesterday, what decisions you made, or what your codebase looks like. You re-explain everything. Every time.

## The Fix: 3 Hooks

```
hooks/memory/
├── git-memory.py      # G1 — time memory
├── g2-augment.py      # G2 — space memory
└── chat-memory.py     # CM — conversation memory
```

### G1 — Time Memory (`git-memory.py`)

Runs on every prompt. Reads the last 7 days of git history and injects a structured summary — commits, changed files, project state — so Claude always knows what you've been working on.

### G2 — Space Memory (`g2-augment.py`)

Runs after Grep/Glob tool calls. Queries a SQLite codebase graph to find related entities (files, functions, classes) and surfaces them automatically. Requires a pre-built graph index.

### CM — Conversation Memory (`chat-memory.py`)

Runs on every prompt. Searches past Claude Code conversations using BM25 (FTS5) + vector hybrid retrieval. Recalls relevant decisions, context, and notes from previous sessions instantly.

---

## Setup

Copy the hooks to your Claude Code hooks directory:

```bash
cp hooks/memory/*.py ~/.claude/hooks/
```

Register them in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "python3 ~/.claude/hooks/git-memory.py" },
          { "type": "command", "command": "python3 ~/.claude/hooks/chat-memory.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Grep|Glob|Read",
        "hooks": [
          { "type": "command", "command": "python3 ~/.claude/hooks/g2-augment.py" }
        ]
      }
    ]
  }
}
```

---

## Dependencies

```bash
pip install rank-bm25 sqlite-utils
```

G2 requires a pre-built SQLite codebase graph. See `g2-augment.py` for indexing instructions.

---

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE) for details.
