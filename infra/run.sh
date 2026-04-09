#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"

MODE="${1:-host-ollama}"
ACTION="${2:-up}"

case "$MODE" in
  host-ollama)
    ENV_FILE="$INFRA_DIR/env/local-host-ollama.env"
    PROFILES=()
    ;;
  docker-ollama)
    ENV_FILE="$INFRA_DIR/env/local-docker-ollama.env"
    PROFILES=(--profile ollama)
    ;;
  vllm)
    ENV_FILE="$INFRA_DIR/env/local-vllm.env"
    PROFILES=(--profile vllm)
    ;;
  *)
    printf 'Unknown mode: %s\n' "$MODE" >&2
    printf 'Usage: bash infra/run.sh [host-ollama|docker-ollama|vllm] [up|down|down-all|restart|ps|logs|stop-host-ollama]\n' >&2
    exit 1
    ;;
esac

ensure_host_ollama() {
  if [[ "$MODE" != "host-ollama" ]]; then
    return 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    printf 'Host Ollama binary not found. Install Ollama or use docker-ollama mode.\n' >&2
    exit 1
  fi

  if curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    return 0
  fi

  printf 'Starting host Ollama...\n'
  nohup ollama serve >/tmp/cowater-host-ollama.log 2>&1 &

  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      printf 'Host Ollama is ready.\n'
      return 0
    fi
    sleep 1
  done

  printf 'Host Ollama failed to start. Check /tmp/cowater-host-ollama.log\n' >&2
  exit 1
}

stop_host_ollama() {
  if ! command -v lsof >/dev/null 2>&1; then
    printf 'lsof not available; cannot detect host Ollama listener.\n' >&2
    return 1
  fi

  local pid
  pid="$(lsof -tiTCP:11434 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"

  if [[ -z "$pid" ]]; then
    printf 'Host Ollama is not running on 127.0.0.1:11434.\n'
    return 0
  fi

  printf 'Stopping host Ollama (pid=%s)...\n' "$pid"
  kill -TERM "$pid"

  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      printf 'Host Ollama stopped.\n'
      return 0
    fi
    sleep 1
  done

  printf 'Host Ollama did not stop in time; sending SIGKILL.\n' >&2
  kill -KILL "$pid" >/dev/null 2>&1 || true
}

compose() {
  if [[ ${#PROFILES[@]} -gt 0 ]]; then
    docker compose --env-file "$ENV_FILE" -f "$INFRA_DIR/docker-compose.yml" "${PROFILES[@]}" "$@"
  else
    docker compose --env-file "$ENV_FILE" -f "$INFRA_DIR/docker-compose.yml" "$@"
  fi
}

case "$ACTION" in
  up)
    ensure_host_ollama
    compose up -d
    ;;
  down)
    compose down
    ;;
  down-all)
    compose down
    if [[ "$MODE" == "host-ollama" ]]; then
      stop_host_ollama
    fi
    ;;
  restart)
    ensure_host_ollama
    compose down
    compose up -d
    ;;
  ps)
    compose ps
    ;;
  logs)
    compose logs -f
    ;;
  stop-host-ollama)
    if [[ "$MODE" != "host-ollama" ]]; then
      printf 'stop-host-ollama is only meaningful in host-ollama mode.\n' >&2
      exit 1
    fi
    stop_host_ollama
    ;;
  *)
    printf 'Unknown action: %s\n' "$ACTION" >&2
    printf 'Usage: bash infra/run.sh [host-ollama|docker-ollama|vllm] [up|down|down-all|restart|ps|logs|stop-host-ollama]\n' >&2
    exit 1
    ;;
esac
