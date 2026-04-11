#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/script_sh"

if [ ! -d "$SCRIPTS_DIR" ]; then
  echo "ERROR: scripts directory not found: $SCRIPTS_DIR" >&2
  exit 1
fi

mapfile -t scripts < <(find "$SCRIPTS_DIR" -maxdepth 1 -type f -name "*.sh" | sort)

if [ "${#scripts[@]}" -eq 0 ]; then
  echo "ERROR: no shell scripts found in $SCRIPTS_DIR" >&2
  exit 1
fi

echo "Found ${#scripts[@]} scripts in $SCRIPTS_DIR"

syntax_ok=0
for script in "${scripts[@]}"; do
  first_line="$(head -n 1 "$script" || true)"
  if [ "$first_line" != "#!/bin/bash" ] && [ "$first_line" != "#!/usr/bin/env bash" ]; then
    echo "WARN: $script has a non-standard bash shebang: $first_line"
  fi

  bash -n "$script"
  syntax_ok=$((syntax_ok + 1))
  echo "OK: syntax check passed -> $script"
done

echo "Syntax checks passed: $syntax_ok/${#scripts[@]}"

if command -v shellcheck >/dev/null 2>&1; then
  echo "Running shellcheck..."
  shellcheck -x "${scripts[@]}"
  echo "OK: shellcheck passed"
else
  echo "WARN: shellcheck is not installed; skipping lint stage"
  echo "Install hint: apt-get install -y shellcheck"
fi

echo "All script_sh checks completed successfully."
