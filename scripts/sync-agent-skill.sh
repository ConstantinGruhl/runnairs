#!/usr/bin/env bash
# Copy skills/platform-agent/SKILL.md into each example agent's
# .claude/skills/platform-agent/ so Claude Code loads it automatically
# when invoked inside the agent directory.
set -euo pipefail
cd "$(dirname "$0")/.."

src=skills/platform-agent/SKILL.md
for agent in examples/*/; do
  dest_dir="${agent}.claude/skills/platform-agent"
  mkdir -p "$dest_dir"
  cp "$src" "$dest_dir/SKILL.md"
  echo "==> wrote $dest_dir/SKILL.md"
done
