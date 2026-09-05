#!/usr/bin/env bash
# start-dev.sh — launches all 4 services, each in its own Terminal.app window.
#
# Usage: run this from your project root (e.g. ~/Workbench):
#   ./start-dev.sh
#
# Adjust VENV_ACTIVATE below if your virtualenv lives somewhere other than
# <project-root>/.venv, or set it to "" if you don't use one.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="source '$PROJECT_ROOT/.venv/bin/activate' && "

run_in_new_window() {
  local title="$1"
  local cmd="$2"
  osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$PROJECT_ROOT' && echo '--- $title ---' && $cmd"
end tell
EOF
}

run_in_new_window "client_ui"      "cd client_ui && npm run dev"
run_in_new_window "orchestrator"   "${VENV_ACTIVATE}uvicorn orchestrator.main:app --port 8001 --reload"
run_in_new_window "RAG service"    "cd RAG && ${VENV_ACTIVATE}uvicorn rag_server:app --port 8000"
run_in_new_window "router"         "${VENV_ACTIVATE}ollama-agent-router serve --config ollama-agent-router.yaml"

echo "Launched 4 Terminal windows: client_ui, orchestrator, RAG service, router."