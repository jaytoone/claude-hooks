#!/bin/bash
# Claude Code Hooks: install.sh
# Version: 1.0.0
#
# Installs Claude Code hooks to ~/.claude/hooks/ and merges hook
# configuration into ~/.claude/settings.json.
#
# Supports: macOS, Linux, WSL2

set -euo pipefail

# -----------------------------------------------------------------------
# Colors
# -----------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------------------
# Resolve script location (works with symlinks)
# -----------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_SRC="$SCRIPT_DIR/hooks"

CLAUDE_DIR="$HOME/.claude"
HOOKS_DEST="$CLAUDE_DIR/hooks"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

# -----------------------------------------------------------------------
# Dependency check
# -----------------------------------------------------------------------
echo ""
echo "Claude Code Hooks — Installer v1.0.0"
echo "======================================"
echo ""

info "Checking dependencies..."

MISSING_DEPS=()
command -v bash >/dev/null 2>&1 || MISSING_DEPS+=("bash")
command -v jq   >/dev/null 2>&1 || MISSING_DEPS+=("jq")

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    error "Missing required tools: ${MISSING_DEPS[*]}"
    echo ""
    echo "Install them with:"
    if command -v apt-get >/dev/null 2>&1; then
        echo "  sudo apt-get install -y ${MISSING_DEPS[*]}"
    elif command -v brew >/dev/null 2>&1; then
        echo "  brew install ${MISSING_DEPS[*]}"
    else
        echo "  Install jq from https://jqlang.github.io/jq/"
    fi
    exit 1
fi
success "All dependencies found (bash, jq)"

# -----------------------------------------------------------------------
# Create hooks directory
# -----------------------------------------------------------------------
info "Creating $HOOKS_DEST ..."
mkdir -p "$HOOKS_DEST"
success "Directory ready: $HOOKS_DEST"

# -----------------------------------------------------------------------
# Copy hook files
# -----------------------------------------------------------------------
info "Copying hook files..."

HOOK_FILES=(
    "inject-system-prompt.sh"
    "session-end-hint.sh"
    "agent_nodes_template.md"
)

for file in "${HOOK_FILES[@]}"; do
    src="$HOOKS_SRC/$file"
    dest="$HOOKS_DEST/$file"

    if [ ! -f "$src" ]; then
        warn "Source file not found, skipping: $src"
        continue
    fi

    # Backup existing file if it differs
    if [ -f "$dest" ]; then
        if ! diff -q "$src" "$dest" >/dev/null 2>&1; then
            BACKUP="$dest.bak.$(date +%Y%m%d_%H%M%S)"
            cp "$dest" "$BACKUP"
            warn "Backed up existing file: $BACKUP"
        fi
    fi

    cp "$src" "$dest"

    # Make shell scripts executable
    if [[ "$file" == *.sh ]]; then
        chmod +x "$dest"
    fi

    success "Installed: $dest"
done

# -----------------------------------------------------------------------
# Merge settings.json
# -----------------------------------------------------------------------
info "Updating $SETTINGS_FILE ..."

TEMPLATE="$SCRIPT_DIR/settings-template.json"

if [ ! -f "$TEMPLATE" ]; then
    warn "settings-template.json not found. Skipping settings merge."
    warn "Add hooks manually — see INSTALL.md for the manual installation section."
else
    # Create settings.json if it does not exist
    if [ ! -f "$SETTINGS_FILE" ]; then
        echo '{}' > "$SETTINGS_FILE"
        info "Created new settings.json"
    fi

    # Validate existing settings.json
    if ! jq empty "$SETTINGS_FILE" 2>/dev/null; then
        error "settings.json is not valid JSON. Please fix it before running install.sh."
        exit 1
    fi

    # Backup current settings
    SETTINGS_BACKUP="$SETTINGS_FILE.backup-$(date +%Y%m%d_%H%M%S)"
    cp "$SETTINGS_FILE" "$SETTINGS_BACKUP"
    success "Settings backed up: $SETTINGS_BACKUP"

    # Merge: template hooks take precedence; existing non-hook keys are preserved
    MERGED=$(jq -s '
        .[0] as $existing |
        .[1] as $template |
        $existing * { hooks: ($existing.hooks // {} | . * $template.hooks) }
    ' "$SETTINGS_FILE" "$TEMPLATE")

    if [ -z "$MERGED" ]; then
        error "jq merge failed. Check both JSON files."
        exit 1
    fi

    echo "$MERGED" > "$SETTINGS_FILE"
    success "settings.json updated with hook configuration"
fi

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "======================================"
success "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Customize your workflow rules:"
echo "     $HOOKS_DEST/agent_nodes_template.md"
echo ""
echo "  2. Restart Claude Code for hooks to take effect."
echo ""
echo "  3. (Optional) Read CUSTOMIZE.md to learn how to tune Git-Smart"
echo "     parameters and add your own hooks."
echo ""
