#!/bin/bash
# Claude Code Hook: session-end-hint.sh
# Version: 1.0.0
#
# Triggered on: SessionEnd
# Purpose: Write a hint file so that the next session's UserPromptSubmit hook
#          (inject-system-prompt.sh) can remind Claude to update MEMORY.md.
#
# Claude should:
#   1. Read the hint at session start
#   2. Update ~/.claude/projects/<project>/memory/MEMORY.md (15 lines max)
#   3. Delete the hint file: rm ~/.claude/.memory-update-hint.md

printf '# MEMORY.md Update Hint\n**Session ended**: %s\n\nThe session ended normally. At the start of the next session, update MEMORY.md to reflect the current project state.\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" \
  > "$HOME/.claude/.memory-update-hint.md" 2>/dev/null

echo '[hooks] Session-end hint saved'
