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

assert_env_value() {
  local env_file="$1"
  local key="$2"
  local expected="$3"
  local count

  count=$(grep -c "^${key}=" "$env_file" || true)
  if [ "$count" -ne 1 ]; then
    echo "ERROR: expected exactly one ${key}= entry in $env_file, got $count" >&2
    exit 1
  fi
  if ! grep -qx "${key}=${expected}" "$env_file"; then
    echo "ERROR: expected ${key}=${expected} in $env_file" >&2
    exit 1
  fi
}

assert_env_absent() {
  local env_file="$1"
  local key="$2"

  if grep -q "^${key}=" "$env_file"; then
    echo "ERROR: unexpected ${key}= entry in $env_file" >&2
    exit 1
  fi
}

run_ssl_setup_env_checks() {
  local ssl_script="$ROOT_DIR/script_sh/ssl_setup.sh"
  local tmp_dir
  local cert_path
  local key_path
  local env_file

  if [ ! -f "$ssl_script" ]; then
    echo "ERROR: ssl setup script not found: $ssl_script" >&2
    exit 1
  fi

  tmp_dir="$(mktemp -d)"
  cert_path="$tmp_dir/test.crt"
  key_path="$tmp_dir/test.key"
  env_file="$tmp_dir/.env"
  touch "$cert_path" "$key_path"

  (
    set -euo pipefail
    INSTALL_DIR="$tmp_dir"
    SECRET_KEY="test-secret"
    APP_PORT="18080"
    RED=""
    GREEN=""
    YELLOW=""
    NC=""

    log() { :; }

    # shellcheck source=/dev/null
    source "$ssl_script"

    configure_http >/dev/null
    setup_custom_certs >/dev/null <<EOF
example.com
$cert_path
$key_path
EOF
    apply_nginx_reverse_proxy_env "proxy.example.com"
  )

  assert_env_value "$env_file" "SECRET_KEY" "test-secret"
  assert_env_value "$env_file" "APP_PORT" "18080"
  assert_env_value "$env_file" "USE_HTTPS" "false"
  assert_env_value "$env_file" "SESSION_COOKIE_SECURE" "true"
  assert_env_value "$env_file" "WTF_CSRF_SSL_STRICT" "true"
  assert_env_value "$env_file" "DOMAIN" "proxy.example.com"
  assert_env_value "$env_file" "BIND" "127.0.0.1"
  assert_env_value "$env_file" "TRUSTED_PROXY_IPS" "127.0.0.1,::1"
  assert_env_absent "$env_file" "SSL_CERT"
  assert_env_absent "$env_file" "SSL_KEY"

  rm -rf "$tmp_dir"
  echo "OK: ssl_setup env mode checks passed"
}

run_ssl_setup_env_checks

echo "All script_sh checks completed successfully."
