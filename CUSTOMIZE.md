# Customization Guide — Claude Code Hooks Basic

This guide explains how to tailor the hooks to your specific workflow.

---

## 1. Editing agent_nodes_template.md

`~/.claude/hooks/agent_nodes_template.md` is injected into every Claude session
via the `UserPromptSubmit` hook. It defines how Claude selects between
DIRECT, PIPELINE, and SWARM execution modes.

### Adding project-specific rules

Open the file and locate the placeholder section at the bottom:

```markdown
<!-- PROJECT-SPECIFIC RULES START -->

<!-- PROJECT-SPECIFIC RULES END -->
```

Add your rules between those markers. Examples:

```markdown
<!-- PROJECT-SPECIFIC RULES START -->

## Project: my-app

- Tech stack: Next.js 15, TypeScript, Supabase
- Test command: `pnpm test`
- Lint command: `pnpm lint`
- Do not modify files under `src/generated/` — they are auto-generated.
- Always run `pnpm build` before marking a feature complete.

<!-- PROJECT-SPECIFIC RULES END -->
```

### Adding a skills / runbook reference

If you maintain runbook documents, reference them directly:

```markdown
## Available Runbooks

- API design rules: `docs/api-guide.md`
- Database schema: `docs/db-schema.md`
- Deployment steps: `docs/deploy.md`
```

Claude will load recently modified docs automatically via Git-Smart
(see Section 4), but explicit references help Claude find the right file.

### Keeping the file lean

Each line costs roughly 4 tokens. Keep `agent_nodes_template.md` under
**200 lines** to avoid significant per-prompt overhead.

---

## 2. Adding Your Own Workflow Rules

Beyond `agent_nodes_template.md`, you can add any static content you want
injected at session start. Two options:

### Option A: Append to agent_nodes_template.md (simplest)

Add a section directly to the file. This is injected unconditionally
on every prompt.

### Option B: Conditional injection in inject-system-prompt.sh

Edit `~/.claude/hooks/inject-system-prompt.sh` and add logic between the
existing sections. For example, inject a different file on Mondays:

```bash
DAY=$(date +%u)  # 1=Mon … 7=Sun
if [ "$DAY" = "1" ]; then
    cat "$HOME/.claude/hooks/weekly-review-prompt.md"
fi
```

---

## 3. Tuning Git-Smart Parameters

Git-Smart automatically loads recently changed `docs/*.md` files.
You can override its auto-tuned defaults with environment variables
before starting Claude Code.

| Variable | Default (auto) | Description |
|----------|---------------|-------------|
| `GIT_SMART_COMMIT_RANGE` | 3–10 (by project size) | How many recent commits to scan |
| `GIT_SMART_MAX_FILES` | 2–5 (by project size) | Maximum number of docs files to load |
| `GIT_SMART_LINES_PER_FILE` | 100–200 (by project size) | Lines to read from each file |
| `GIT_SMART_FILE_PATTERN` | `docs/.*\.md$` | Regex pattern to match file paths |

### Example: override for a large monorepo

```bash
export GIT_SMART_COMMIT_RANGE=2
export GIT_SMART_MAX_FILES=1
export GIT_SMART_LINES_PER_FILE=50
export GIT_SMART_FILE_PATTERN="docs/architecture/.*\.md$"
claude
```

### Adjusting the token budget

The default budget is 2000 tokens for Git-Smart output. To change it,
edit `inject-system-prompt.sh`:

```bash
TOKEN_BUDGET=3000  # increase for larger context windows
```

### Adjusting the cooldown period

By default, Git-Smart skips loading if it ran within the last hour
(to avoid redundant output within a long session).

```bash
GIT_SMART_COOLDOWN=1800  # 30 minutes
```

To disable the cooldown entirely (always load):
```bash
GIT_SMART_COOLDOWN=0
```

### Changing the docs directory

If your documentation lives outside `docs/`, edit this line in
`inject-system-prompt.sh`:

```bash
DOCS_DIR="$PROJECT_ROOT/docs"
# Change to:
DOCS_DIR="$PROJECT_ROOT/wiki"
```

---

## 4. Adding Additional Hooks

Claude Code supports multiple hook types. To add a new hook:

### Step 1: Create the script

```bash
cat > ~/.claude/hooks/my-custom-hook.sh << 'EOF'
#!/bin/bash
# My custom hook
echo "Running custom hook..."
# Add your logic here
EOF
chmod +x ~/.claude/hooks/my-custom-hook.sh
```

### Step 2: Register in settings.json

```bash
jq '.hooks.PostToolUse += [{
  "matcher": "Write",
  "hooks": [{
    "type": "command",
    "command": "bash $HOME/.claude/hooks/my-custom-hook.sh"
  }]
}]' ~/.claude/settings.json > /tmp/s.json && mv /tmp/s.json ~/.claude/settings.json
```

### Available hook events

| Event | Trigger |
|-------|---------|
| `UserPromptSubmit` | Every user message |
| `SessionStart` | Session begins |
| `SessionEnd` | Session ends |
| `PreCompact` | Before context compaction |
| `PreToolUse` | Before any tool call |
| `PostToolUse` | After any tool call |
| `Stop` | Claude finishes responding |
| `Notification` | System notification |

### Matcher syntax

- `""` — match all
- `"Write"` — match tool name exactly
- `"permission_prompt"` — match notification type

---

## 5. Work-Progress File

Claude can save the current task state to persist it across sessions.
The file is stored at:

```
~/.claude/.work-progress-<project-hash>.md
```

The hash is derived from `PROJECT_ROOT` (or `$PWD`), so each project
gets its own progress file automatically.

To manually save progress, ask Claude:
```
Save the current work progress to the work-progress file.
```

To clear it:
```bash
PROJECT_HASH=$(echo "$PWD" | md5sum | head -c8)
rm -f ~/.claude/.work-progress-${PROJECT_HASH}.md
```

---

## 6. MEMORY.md Convention

The `session-end-hint.sh` hook writes a hint file on session end.
On the next session, `inject-system-prompt.sh` displays the hint,
prompting Claude to update `MEMORY.md`.

Recommended `MEMORY.md` location:
```
~/.claude/projects/<project-name>/memory/MEMORY.md
```

Keep it under **15 lines**:
- Current status (what is done)
- Unresolved issues
- Next actions

After Claude updates `MEMORY.md`, it should delete the hint file:
```bash
rm ~/.claude/.memory-update-hint.md
```
