# Installation Guide — Claude Code Hooks Basic

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Claude Code | Any | Must be installed and configured |
| bash | 4.0+ | macOS ships bash 3.x; upgrade via Homebrew if needed |
| jq | 1.6+ | JSON processor used by install.sh |

Install `jq` if missing:
```bash
# Ubuntu / Debian / WSL2
sudo apt-get install -y jq

# macOS
brew install jq
```

---

## Automated Installation (Recommended)

### Step 1 — Download

Clone or download this repository:

```bash
git clone https://github.com/your-org/claude-hooks-basic.git
cd claude-hooks-basic
```

Or download and extract the ZIP from the releases page.

### Step 2 — Run the installer

```bash
bash install.sh
```

The installer will:
- Create `~/.claude/hooks/` if it does not exist
- Copy `hooks/*.sh` and `hooks/agent_nodes_template.md`
- Back up your existing `~/.claude/settings.json`
- Merge the hook configuration into `~/.claude/settings.json`

### Step 3 — Restart Claude Code

Close and reopen Claude Code, or run:
```bash
claude restart
```

The hooks are now active. On your next prompt, `inject-system-prompt.sh`
will inject `agent_nodes_template.md` into the system context.

---

## Manual Installation

Use this method if you prefer not to run `install.sh`.

### 1. Create the hooks directory

```bash
mkdir -p ~/.claude/hooks
```

### 2. Copy the hook files

```bash
cp hooks/inject-system-prompt.sh   ~/.claude/hooks/
cp hooks/session-end-hint.sh       ~/.claude/hooks/
cp hooks/agent_nodes_template.md   ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

### 3. Edit `~/.claude/settings.json`

If the file does not exist, create it with `{}`.

Add (or merge) the following `hooks` block:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/hooks/inject-system-prompt.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/hooks/session-end-hint.sh"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "node $HOME/.claude/hooks/pre-compact-save.js"
          }
        ]
      }
    ]
  }
}
```

Note: The `PreCompact` entry references `pre-compact-save.js`, which is NOT
included in this package. Remove that block if you do not have it.

### 4. Restart Claude Code

---

## Verifying the Installation

After restarting, submit any prompt in Claude Code.
You should see content from `agent_nodes_template.md` appear at the top
of the system context (visible in debug mode or transcript logs).

To check the hook is registered:
```bash
cat ~/.claude/settings.json | jq '.hooks.UserPromptSubmit'
```

Expected output:
```json
[
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "bash $HOME/.claude/hooks/inject-system-prompt.sh"
      }
    ]
  }
]
```

---

## Troubleshooting

### Hook does not trigger

- Confirm `~/.claude/settings.json` contains the `UserPromptSubmit` entry.
- Confirm `~/.claude/hooks/inject-system-prompt.sh` is executable:
  ```bash
  ls -l ~/.claude/hooks/inject-system-prompt.sh
  # Should show -rwxr-xr-x
  ```
- Restart Claude Code after any settings change.

### agent_nodes_template.md not found

The hook prints a warning comment and continues. Copy the file:
```bash
cp hooks/agent_nodes_template.md ~/.claude/hooks/
```

### settings.json is invalid JSON

Run:
```bash
jq empty ~/.claude/settings.json
```

Fix any syntax errors, then re-run `install.sh`.

### jq not found

```bash
# Ubuntu / WSL2
sudo apt-get install -y jq

# macOS
brew install jq
```

### Git-Smart section shows no docs

Git-Smart only runs when:
1. The current directory is a git repository (`git rev-parse --git-dir` succeeds).
2. A `docs/` subdirectory exists.
3. The cooldown period (1 hour) has elapsed since the last run.

If all three conditions are met but nothing appears, check that docs contain
`*.md` files that were changed within the last 10 commits.

---

## Uninstallation

```bash
# Remove hook files
rm -f ~/.claude/hooks/inject-system-prompt.sh
rm -f ~/.claude/hooks/session-end-hint.sh
rm -f ~/.claude/hooks/agent_nodes_template.md

# Remove hook entries from settings.json
jq 'del(.hooks.UserPromptSubmit, .hooks.SessionEnd)' \
  ~/.claude/settings.json > /tmp/settings_clean.json \
  && mv /tmp/settings_clean.json ~/.claude/settings.json
```
