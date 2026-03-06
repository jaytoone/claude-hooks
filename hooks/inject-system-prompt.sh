#!/bin/bash
# Claude Code Hook: inject-system-prompt.sh
# Version: 1.0.0
#
# Features:
#   1. agent_nodes_template.md injection (workflow guidelines)
#   2. MEMORY.md update hint detection
#   3. Work-progress restoration across sessions
#   4. Git-Smart document loading (auto-tuned by project size)
#
# Usage: Set as UserPromptSubmit hook in ~/.claude/settings.json

COMPACT_MARKER="$HOME/.claude/.compact-marker"
RECOVERY_PATH="$HOME/.claude/hooks/post-compact-recovery.md"
SYSTEM_PROMPT_PATH="$HOME/.claude/hooks/agent_nodes_template.md"

# Project-isolated work-progress: hash by PROJECT_ROOT so each project
# gets its own progress file without collisions
PROJECT_HASH=$(echo "${PROJECT_ROOT:-$PWD}" | md5sum | head -c8)
WORK_PROGRESS="$HOME/.claude/.work-progress-${PROJECT_HASH}.md"

TOKEN_LOG="$HOME/.claude/.git-smart-token-usage.log"
MEMORY_HINT="$HOME/.claude/.memory-update-hint.md"

# -----------------------------------------------------------------------
# Section 1: Post-compact recovery
# -----------------------------------------------------------------------
if [ -f "$COMPACT_MARKER" ]; then
    if [ -f "$RECOVERY_PATH" ]; then
        cat "$RECOVERY_PATH"
        echo ""
    fi
    rm -f "$COMPACT_MARKER"
fi

# -----------------------------------------------------------------------
# Section 2: MEMORY.md update hint
# Written by session-end-hint.sh; Claude removes it after updating MEMORY.md
# -----------------------------------------------------------------------
if [ -f "$MEMORY_HINT" ]; then
    HINT_CONTENT=$(head -2 "$MEMORY_HINT" 2>/dev/null)
    echo "<!-- MEMORY.md Update Required -->"
    echo "**[Auto-detected]** MEMORY.md update is required."
    echo "> $HINT_CONTENT"
    echo ""
    echo "> Check the current project state, update MEMORY.md, then run:"
    echo "> \`rm ~/.claude/.memory-update-hint.md\`"
    echo ""
fi

# -----------------------------------------------------------------------
# Section 3: Agent Nodes pipeline injection
# Source of truth for DIRECT / PIPELINE / SWARM mode selection
# -----------------------------------------------------------------------
if [ -f "$SYSTEM_PROMPT_PATH" ]; then
    cat "$SYSTEM_PROMPT_PATH"
else
    echo "<!-- agent_nodes_template.md not found at $SYSTEM_PROMPT_PATH -->"
    echo "Run install.sh or copy hooks/agent_nodes_template.md to ~/.claude/hooks/"
fi

# -----------------------------------------------------------------------
# Section 4: Work-progress restoration
# Saved by save-work-progress.sh or manually by Claude
# -----------------------------------------------------------------------
if [ -f "$WORK_PROGRESS" ]; then
    echo ""
    echo "<!-- Work Progress Restoration -->"
    echo "## Previous Work Progress"
    echo ""
    cat "$WORK_PROGRESS"
fi

# -----------------------------------------------------------------------
# Section 5: Git-Smart document loading
# Loads recently changed docs/*.md files, auto-tuned by project size
# Cooldown: 1 hour to avoid redundant loading within a session
# -----------------------------------------------------------------------
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
DOCS_DIR="$PROJECT_ROOT/docs"
GIT_SMART_FLAG="$HOME/.claude/.git-smart-cooldown"
GIT_SMART_COOLDOWN=3600  # seconds (1 hour)

SKIP_GIT_SMART=false
if [ -f "$GIT_SMART_FLAG" ]; then
    LAST_RUN=$(cat "$GIT_SMART_FLAG" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    ELAPSED=$((NOW - LAST_RUN))
    if [ $ELAPSED -lt $GIT_SMART_COOLDOWN ]; then
        SKIP_GIT_SMART=true
    fi
fi

if [ "$SKIP_GIT_SMART" = false ] && [ -d "$DOCS_DIR" ] && git rev-parse --git-dir > /dev/null 2>&1; then
    date +%s > "$GIT_SMART_FLAG"

    # Auto-tune parameters based on project size
    TOTAL_FILES=$(find "$DOCS_DIR" -name "*.md" 2>/dev/null | wc -l)
    AVG_SIZE=$(find "$DOCS_DIR" -name "*.md" -exec wc -l {} \; 2>/dev/null | \
               awk '{sum+=$1; count++} END {if(count>0) print int(sum/count); else print 500}')

    if [ "$TOTAL_FILES" -gt 100 ]; then
        # Large project
        AUTO_COMMIT_RANGE=3
        AUTO_MAX_FILES=2
        AUTO_LINES_PER_FILE=100
    elif [ "$TOTAL_FILES" -gt 50 ]; then
        # Medium project
        AUTO_COMMIT_RANGE=5
        AUTO_MAX_FILES=3
        AUTO_LINES_PER_FILE=150
    else
        # Small project
        AUTO_COMMIT_RANGE=10
        AUTO_MAX_FILES=5
        AUTO_LINES_PER_FILE=200
    fi

    # Reduce lines-per-file for very long documents
    if [ "$AVG_SIZE" -gt 1000 ]; then
        AUTO_LINES_PER_FILE=$((AUTO_LINES_PER_FILE * 80 / 100))
    fi

    # Allow per-session environment variable overrides
    COMMIT_RANGE="${GIT_SMART_COMMIT_RANGE:-$AUTO_COMMIT_RANGE}"
    MAX_FILES="${GIT_SMART_MAX_FILES:-$AUTO_MAX_FILES}"
    LINES_PER_FILE="${GIT_SMART_LINES_PER_FILE:-$AUTO_LINES_PER_FILE}"
    FILE_PATTERN="${GIT_SMART_FILE_PATTERN:-docs/.*\.md$}"

    # Token budget tracking (~4 tokens per line estimate)
    TOKEN_BUDGET=2000
    TOTAL_LINES=0
    TOTAL_TOKENS=0

    RECENT_FILES=$(git diff --name-only HEAD~${COMMIT_RANGE}..HEAD 2>/dev/null | \
                   grep "$FILE_PATTERN" | \
                   head -${MAX_FILES})

    if [ -n "$RECENT_FILES" ]; then
        # Calculate projected token usage
        while IFS= read -r file; do
            if [ -f "$file" ]; then
                file_lines=$(wc -l < "$file" 2>/dev/null || echo 0)
                actual_lines=$((file_lines < LINES_PER_FILE ? file_lines : LINES_PER_FILE))
                TOTAL_LINES=$((TOTAL_LINES + actual_lines))
                TOTAL_TOKENS=$((TOTAL_TOKENS + actual_lines * 4))
            fi
        done <<< "$RECENT_FILES"

        # Scale down lines-per-file if over budget (single pass)
        if [ $TOTAL_TOKENS -gt $TOKEN_BUDGET ]; then
            LINES_PER_FILE=$((LINES_PER_FILE * TOKEN_BUDGET / TOTAL_TOKENS))
            TOTAL_TOKENS=$TOKEN_BUDGET
        fi

        # Append to token usage log
        echo "$(date +"%Y-%m-%d %H:%M:%S"),${TOTAL_FILES},${AVG_SIZE},${COMMIT_RANGE},${MAX_FILES},${LINES_PER_FILE},${TOTAL_TOKENS},${TOKEN_BUDGET}" >> "$TOKEN_LOG"

        echo ""
        echo "<!-- Git-Smart Document Loading -->"
        echo "## Recently Modified Docs (Git-Smart)"
        echo ""
        echo "**Auto-Tuning**: ${TOTAL_FILES} docs, avg ${AVG_SIZE} lines | range: ${COMMIT_RANGE} commits, max: ${MAX_FILES} files, ${LINES_PER_FILE} lines/file"
        echo "**Token Usage**: ${TOTAL_TOKENS}/${TOKEN_BUDGET} ($(((TOTAL_TOKENS * 100) / TOKEN_BUDGET))%)"
        echo ""

        echo "$RECENT_FILES" | while IFS= read -r file; do
            if [ -f "$file" ]; then
                echo "### $file"
                echo ""
                head -${LINES_PER_FILE} "$file"
                echo ""
                echo "---"
                echo ""
            fi
        done
    fi
fi
