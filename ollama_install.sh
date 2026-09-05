#!/usr/bin/env bash
#
# setup-ollama-mac.sh
# Installs Ollama on Apple Silicon (M-series) Macs and pulls the models
# referenced in the router config (nodeId: ryzen-local).
#
# Usage:
#   chmod +x setup-ollama-mac.sh
#   ./setup-ollama-mac.sh

set -euo pipefail

MODELS=(
  "smollm2:360m"
  "qwen2.5:0.5b"
  "qwen2.5-coder:1.5b"
  "qwen2.5-coder:7b"
  "llama3.2:1b"
)

OLLAMA_HOST_DEFAULT="127.0.0.1:11434"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1"; exit 1; }

# --- 0. Sanity checks -------------------------------------------------------
if [[ "$(uname -s)" != "Darwin" ]]; then
  die "This script is for macOS only."
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  warn "This doesn't look like Apple Silicon (arm64). Continuing anyway, but performance/steps may differ."
fi

# --- 1. Install Ollama -------------------------------------------------------
if command -v ollama >/dev/null 2>&1; then
  log "Ollama already installed ($(ollama -v 2>&1 | head -n1))."
else
  if command -v brew >/dev/null 2>&1; then
    log "Installing Ollama via Homebrew..."
    brew install ollama
  else
    log "Homebrew not found — installing Ollama via official installer script..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi

command -v ollama >/dev/null 2>&1 || die "Ollama install failed — 'ollama' not on PATH."

# --- 2. Start the Ollama server ---------------------------------------------
# If installed via Homebrew, prefer the brew service (auto-restarts, logs to brew log dir).
# Otherwise fall back to running 'ollama serve' in the background.
is_server_up() {
  curl -fsS "http://${OLLAMA_HOST_DEFAULT}/api/version" >/dev/null 2>&1
}

if is_server_up; then
  log "Ollama server already running on ${OLLAMA_HOST_DEFAULT}."
else
  if command -v brew >/dev/null 2>&1 && brew list --formula 2>/dev/null | grep -q '^ollama$'; then
    log "Starting Ollama via brew services..."
    brew services start ollama
  else
    log "Starting 'ollama serve' in the background..."
    nohup ollama serve > "${HOME}/ollama-serve.log" 2>&1 &
    disown
  fi

  log "Waiting for Ollama server to become reachable on ${OLLAMA_HOST_DEFAULT}..."
  for i in $(seq 1 30); do
    if is_server_up; then
      break
    fi
    sleep 1
    if [[ "$i" -eq 30 ]]; then
      die "Ollama server did not come up after 30s. Check ~/ollama-serve.log (or 'brew services list')."
    fi
  done
fi

log "Ollama server is up."

# --- 3. Pull models used by the router config -------------------------------
# Order: smallest/cheapest first so you get something usable quickly;
# the 7B coder model is last since it's the largest (~4.7GB) and slowest to pull.
for model in "${MODELS[@]}"; do
  log "Pulling model: ${model}"
  ollama pull "${model}"
done

# --- 4. Summary --------------------------------------------------------------
log "Installed models:"
ollama list

cat <<EOF

Done.

Ollama is listening on http://${OLLAMA_HOST_DEFAULT} (matches ollama.baseUrl in your router config).
Your router service (nodeId: ryzen-local) should run separately on 127.0.0.1:11435 as configured.

Notes:
  - qwen2.5-coder:7b is ~4.7GB on disk and marked 'exclusive: true' / 'allowWhenBusy: false'
    in your router config — expect it to be slow on CPU-only inference and to block other
    requests while running, which matches that config's intent.
  - To keep Ollama running persistently across reboots when installed via Homebrew:
      brew services start ollama
  - To stop the background 'ollama serve' process (non-brew install):
      pkill -f "ollama serve"
  - Re-run this script any time to verify/re-pull missing models; already-downloaded
    models are skipped by 'ollama pull'.
EOF