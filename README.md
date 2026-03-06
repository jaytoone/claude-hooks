# claude-hooks-basic

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20WSL2-lightgrey)](https://github.com/anthropics/claude-code)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-%3E%3D1.0-blueviolet)](https://claude.ai/code)

A lightweight hook system that makes Claude Code follow your rules automatically — every session, without repeating yourself.

---

## What is this?

Every time you open Claude Code, this hook system runs before Claude responds. It automatically injects your workflow guidelines, restores what you were working on last session, and loads recently changed documentation — so Claude always has the context it needs to behave consistently.

- **Prompt injection** — your AI behavior rules are delivered on every prompt, hands-free
- **Session memory** — Claude knows what you were doing last time without you explaining it again
- **Git-Smart doc loading** — recently modified docs are loaded automatically based on git history

No configuration required for basic use. Install once, benefit forever.

---

## Features

- **Auto-injects workflow guidelines every prompt** — define how Claude should think and act; it follows those rules every session without you repeating them
- **Restores previous work context across sessions** — Claude picks up where you left off, even after closing and reopening
- **Git-Smart document loading** — scans recent git commits and auto-loads changed `docs/*.md` files; auto-tunes depth and line limits based on project size
- **Project-isolated context** — each project gets its own work-progress file; multiple projects never interfere with each other
- **Token budget management** — Git-Smart output is capped and scaled automatically to avoid flooding the context window

---

## Quick Start

```bash
git clone https://github.com/jaytoone/claude-hooks
cd claude-hooks-basic
bash install.sh
```

Restart Claude Code. The hooks are active immediately.

**Requirements**: `bash`, `jq` (install with `brew install jq` or `sudo apt-get install -y jq`)

---

## What Gets Installed

```
~/.claude/
├── hooks/
│   ├── inject-system-prompt.sh     # UserPromptSubmit hook — core of the system
│   ├── session-end-hint.sh         # SessionEnd hook — writes MEMORY.md reminder
│   └── agent_nodes_template.md     # Your workflow rules (edit this to customize)
└── settings.json                   # Hook registration (merged, not overwritten)
```

| File | Purpose |
|------|---------|
| `inject-system-prompt.sh` | Runs on every user prompt. Injects guidelines, restores context, loads docs. |
| `session-end-hint.sh` | Runs when the session ends. Saves a reminder for Claude to update MEMORY.md. |
| `agent_nodes_template.md` | Markdown file that defines your workflow rules. Injected verbatim every session. |
| `settings.json` | Claude Code hook configuration. Existing keys are preserved during install. |

---

## How It Works

```
Claude Code starts session
         |
         v
UserPromptSubmit hook fires
         |
         v
inject-system-prompt.sh runs
    |-- Inject agent_nodes_template.md  --> AI follows your workflow rules
    |-- Check MEMORY.md hint            --> Reminds AI to update memory
    |-- Restore work-progress           --> AI knows what you were working on
    `-- Git-Smart doc loading           --> AI reads your recent doc changes
         |
         v
Claude receives enriched context --> responds consistently
```

On session end, `session-end-hint.sh` writes a hint file. The next time you open Claude Code, the hook detects the hint and reminds Claude to update `MEMORY.md` with the current project state before continuing.

---

## Customization

### Edit your workflow rules

Open `~/.claude/hooks/agent_nodes_template.md` and add your project-specific rules. This file is injected on every prompt, so anything you write here becomes standing instructions for Claude.

```markdown
## Project: my-app

- Tech stack: Next.js 15, TypeScript, Supabase
- Test command: pnpm test
- Do not modify files under src/generated/ — they are auto-generated.
```

Keep the file under 200 lines to avoid significant per-prompt token overhead.

### Tune Git-Smart with environment variables

Set these before launching Claude Code to override the auto-tuned defaults:

| Variable | Default (auto) | Description |
|----------|---------------|-------------|
| `GIT_SMART_COMMIT_RANGE` | 3–10 | How many recent commits to scan |
| `GIT_SMART_MAX_FILES` | 2–5 | Maximum docs files to load |
| `GIT_SMART_LINES_PER_FILE` | 100–200 | Lines to read per file |
| `GIT_SMART_FILE_PATTERN` | `docs/.*\.md$` | File path regex filter |

Example for a large monorepo:

```bash
export GIT_SMART_COMMIT_RANGE=2
export GIT_SMART_MAX_FILES=1
export GIT_SMART_LINES_PER_FILE=50
claude
```

For the full customization guide, see [CUSTOMIZE.md](CUSTOMIZE.md).

---

## Pro Version

The Pro version includes everything in this package plus a more advanced hook system designed for complex, multi-step AI workflows.

Additional contents:

- Multi-agent orchestration template (DIRECT / PIPELINE / SWARM mode selection)
- Pre-compact context save and automatic recovery after compaction
- Work-progress save/restore scripts
- Session-aware MEMORY.md with structured update protocol
- Extended Git-Smart with token usage logging and analytics
- Post-tool-use hooks for automatic doc indexing
- Full runbook and skills system integration

[Available on PromptBase →](https://promptbase.com/prompt/code-workflow-3-execution-modes?via=bejay)

---

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE) for details.
