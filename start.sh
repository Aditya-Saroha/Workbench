set -uo pipefail

# --- Config ------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="ollama-agent-router.yaml"
CLIENT_DIR="client_ui"
RAG_DIR="RAG"
RAG_PORT=8080
LOG_DIR="${ROOT_DIR}/logs"

mkdir -p "${LOG_DIR}"

ROUTER_LOG="${LOG_DIR}/router.log"
CLIENT_LOG="${LOG_DIR}/client_ui.log"
RAG_LOG="${LOG_DIR}/rag_server.log"

PIDS=()

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1"; exit 1; }

# --- Sanity checks -------------------------------------------------------
[[ -f "${ROOT_DIR}/${CONFIG_FILE}" ]] || die "Config not found: ${ROOT_DIR}/${CONFIG_FILE}"
[[ -d "${ROOT_DIR}/${CLIENT_DIR}" ]]   || die "Directory not found: ${ROOT_DIR}/${CLIENT_DIR}"
[[ -d "${ROOT_DIR}/${RAG_DIR}" ]]      || die "Directory not found: ${ROOT_DIR}/${RAG_DIR}"

command -v ollama-agent-router >/dev/null 2>&1 || die "'ollama-agent-router' not found on PATH."
command -v npm >/dev/null 2>&1 || die "'npm' not found on PATH."
command -v uvicorn >/dev/null 2>&1 || die "'uvicorn' not found on PATH."

# --- Cleanup on exit -------------------------------------------------------
cleanup() {
  log "Shutting down..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null
    fi
  done
  wait 2>/dev/null
  log "All services stopped."
}
trap cleanup EXIT INT TERM

# --- 1. Router -------------------------------------------------------------
log "Starting ollama-agent-router (config: ${CONFIG_FILE})..."
(
  cd "${ROOT_DIR}"
  ollama-agent-router serve --config "${CONFIG_FILE}"
) > "${ROUTER_LOG}" 2>&1 &
PIDS+=($!)

# --- 2. Client UI ------------------------------------------------------------
log "Starting client_ui (npm run dev)..."
(
  cd "${ROOT_DIR}/${CLIENT_DIR}"
  npm run dev
) > "${CLIENT_LOG}" 2>&1 &
PIDS+=($!)

# --- 3. RAG server -----------------------------------------------------------
log "Starting RAG server (uvicorn rag_server:app --port ${RAG_PORT})..."
(
  cd "${ROOT_DIR}/${RAG_DIR}"
  uvicorn rag_server:app --port "${RAG_PORT}"
) > "${RAG_LOG}" 2>&1 &
PIDS+=($!)

log "All services launching. PIDs: ${PIDS[*]}"
log "Logs: ${LOG_DIR}/{router,client_ui,rag_server}.log"
log "Press Ctrl-C to stop everything."

# --- Tail all logs together, and exit if any process dies early ------------
tail -n 0 -f "${ROUTER_LOG}" "${CLIENT_LOG}" "${RAG_LOG}" &
TAIL_PID=$!
PIDS+=("${TAIL_PID}")

while true; do
  for pid in "${PIDS[@]}"; do
    if [[ "${pid}" != "${TAIL_PID}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
      warn "A service (PID ${pid}) exited. Check logs in ${LOG_DIR}."
      exit 1
    fi
  done
  sleep 2
done