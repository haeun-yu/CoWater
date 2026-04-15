#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"

MODE="${1:-host-ollama}"
ACTION="${2:-up}"
PRESET="${3:-full}"

ENV_FILE_OVERRIDE="${COWATER_ENV_FILE:-}"
SCENARIO="${SCENARIO:-}"
NO_DEPS=false
SERVICES=()

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
    printf 'Usage: bash infra/run.sh [host-ollama|docker-ollama|vllm] [up|down|down-all|restart|ps|logs|stop-host-ollama] [full|data-node|core-node|agents-node|frontend-node|bridge-node|llm-node]\n' >&2
    exit 1
    ;;
esac

# SCENARIO이 설정되면 simulation 프로필 활성화
if [[ -n "$SCENARIO" ]]; then
  PROFILES+=(--profile simulation)
fi

if [[ -n "$ENV_FILE_OVERRIDE" ]]; then
  ENV_FILE="$ENV_FILE_OVERRIDE"
fi

case "$PRESET" in
  full)
    SERVICES=()
    ;;
  data-node)
    NO_DEPS=true
    SERVICES=(postgres redis)
    ;;
  core-node)
    NO_DEPS=true
    SERVICES=(core)
    ;;
  agents-node)
    NO_DEPS=true
    SERVICES=(agents)
    if [[ "$MODE" == "docker-ollama" ]]; then
      SERVICES+=(ollama ollama-init)
    elif [[ "$MODE" == "vllm" ]]; then
      SERVICES+=(vllm)
    fi
    ;;
  frontend-node)
    NO_DEPS=true
    SERVICES=(frontend)
    ;;
  bridge-node)
    NO_DEPS=true
    SERVICES=(moth-bridge)
    ;;
  llm-node)
    NO_DEPS=true
    case "$MODE" in
      host-ollama)
        SERVICES=()
        ;;
      docker-ollama)
        SERVICES=(ollama ollama-init)
        ;;
      vllm)
        SERVICES=(vllm)
        ;;
    esac
    ;;
  *)
    printf 'Unknown preset: %s\n' "$PRESET" >&2
    printf 'Allowed presets: full|data-node|core-node|agents-node|frontend-node|bridge-node|llm-node\n' >&2
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

warn_if_disk_low() {
  local data_line used_pct avail_kb
  data_line="$(df -k /System/Volumes/Data 2>/dev/null | awk 'NR==2 {print $5" "$4}')"
  if [[ -z "$data_line" ]]; then
    return 0
  fi

  used_pct="${data_line%% *}"
  used_pct="${used_pct%%%}"
  avail_kb="${data_line##* }"

  if [[ "$used_pct" -ge 95 || "$avail_kb" -le 20971520 ]]; then
    printf 'WARNING: Low disk headroom detected on /System/Volumes/Data (%s%% used, %s KB available).\n' "$used_pct" "$avail_kb" >&2
    printf 'Postgres previously crashed with "No space left on device" in this condition.\n' >&2
  fi
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
  local subcommand="$1"
  local -a cmd=(docker compose --env-file "$ENV_FILE" -f "$INFRA_DIR/docker-compose.yml")
  local -a no_deps_args=()
  local -a service_args=()

  if $NO_DEPS && [[ "$subcommand" == "up" ]]; then
    no_deps_args=(--no-deps)
  fi

  if [[ ${#SERVICES[@]} -gt 0 ]]; then
    service_args=("${SERVICES[@]}")
  fi

  if [[ ${#PROFILES[@]} -gt 0 ]]; then
    cmd+=("${PROFILES[@]}")
  fi

  # SCENARIO 환경변수 전달
  if [[ -n "$SCENARIO" ]]; then
    cmd+=(-e SCENARIO="$SCENARIO")
  fi

  cmd+=("$@")

  if [[ ${#no_deps_args[@]} -gt 0 ]]; then
    cmd+=("${no_deps_args[@]}")
  fi

  if [[ ${#service_args[@]} -gt 0 ]]; then
    cmd+=("${service_args[@]}")
  fi

  "${cmd[@]}"
}

case "$ACTION" in
  up)
    warn_if_disk_low
    ensure_host_ollama
    compose up -d
    ;;
  down)
    if [[ ${#SERVICES[@]} -gt 0 ]]; then
      compose stop
    else
      compose down
    fi
    ;;
  down-all)
    if [[ ${#SERVICES[@]} -gt 0 ]]; then
      compose stop
    else
      compose down
    fi
    if [[ "$MODE" == "host-ollama" ]]; then
      stop_host_ollama
    fi
    ;;
  restart)
    warn_if_disk_low
    ensure_host_ollama
    if [[ ${#SERVICES[@]} -gt 0 ]]; then
      compose stop
    else
      compose down
    fi
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
  start-host-ollama)
    if [[ "$MODE" != "host-ollama" ]]; then
      printf 'start-host-ollama is only meaningful in host-ollama mode.\n' >&2
      exit 1
    fi
    ensure_host_ollama
    ;;
  *)
    printf 'Unknown action: %s\n' "$ACTION" >&2
    printf 'Usage: bash infra/run.sh [host-ollama|docker-ollama|vllm] [up|down|down-all|restart|ps|logs|stop-host-ollama|start-host-ollama] [full|data-node|core-node|agents-node|frontend-node|bridge-node|llm-node]\n' >&2
    exit 1
    ;;
esac
