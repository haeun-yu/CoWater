#!/bin/bash
# Unified CoWater service manager: start|stop|status|restart|logs

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVICE_DIR="$PROJECT_ROOT/device"
SERVER_DIR="$PROJECT_ROOT/server/registration"
CLIENT_DIR="$PROJECT_ROOT/client"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOG_DIR="$PROJECT_ROOT/.logs"
PID_FILE="$PROJECT_ROOT/.cowater_pids"

mkdir -p "$LOG_DIR"
touch "$PID_FILE"

SYSTEM_AGENT_DIR="$PROJECT_ROOT/server/system-agent"

SERVICES=(
  "Registry|cd '$SERVER_DIR' && '$VENV_PYTHON' device_registration_server.py|http://127.0.0.1:8280/health|device_registration_server.py"
  "System-Agent|cd '$SYSTEM_AGENT_DIR' && '$VENV_PYTHON' system_agent.py|http://127.0.0.1:9116/health|system_agent.py"
  "Ship-Middle|cd '$DEVICE_DIR' && '$VENV_PYTHON' device_agent.py --type ship --layer middle|http://127.0.0.1:9115/health|device_agent.py --type ship --layer middle"
  "USV-Lower|cd '$DEVICE_DIR' && '$VENV_PYTHON' device_agent.py --type usv --layer lower|http://127.0.0.1:9111/health|device_agent.py --type usv --layer lower"
  "AUV-Lower|cd '$DEVICE_DIR' && '$VENV_PYTHON' device_agent.py --type auv --layer lower|http://127.0.0.1:9112/health|device_agent.py --type auv --layer lower"
  "ROV-Lower|cd '$DEVICE_DIR' && '$VENV_PYTHON' device_agent.py --type rov --layer lower|http://127.0.0.1:9113/health|device_agent.py --type rov --layer lower"
)

print_header() {
  echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BLUE}║                CoWater Unified Service Ctrl               ║${NC}"
  echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
}

start_one() {
  local name="$1"
  local cmd="$2"
  local log_file="$LOG_DIR/$name.log"

  echo -e "${YELLOW}[*] $name 시작 중...${NC}"
  nohup bash -lc "$cmd" > "$log_file" 2>&1 &
  local pid=$!
  echo "$name:$pid" >> "$PID_FILE"
  sleep 1

  if kill -0 "$pid" 2>/dev/null; then
    echo -e "${GREEN}[✓] $name 시작됨 (PID: $pid)${NC}"
    echo "    로그: $log_file"
  else
    echo -e "${RED}[✗] $name 시작 실패${NC}"
    echo "    로그 확인: $log_file"
    return 1
  fi
}

service_name() { echo "$1" | cut -d'|' -f1; }
service_cmd() { echo "$1" | cut -d'|' -f2; }
service_health() { echo "$1" | cut -d'|' -f3; }
service_pattern() { echo "$1" | cut -d'|' -f4-; }

health_ok() {
  local url="$1"
  [ -n "$url" ] && curl -fsS "$url" >/dev/null 2>&1
}

ollama_ok() {
  curl -fsS "http://127.0.0.1:11434/api/version" >/dev/null 2>&1
}

pattern_running() {
  local pattern="$1"
  [ -n "$pattern" ] && pgrep -f "$pattern" >/dev/null 2>&1
}

record_running_pid() {
  local name="$1"
  local pattern="$2"
  local pid
  pid="$(pgrep -f "$pattern" | head -n 1 || true)"
  if [ -n "$pid" ]; then
    echo "$name:$pid" >> "$PID_FILE"
  fi
}

ensure_one() {
  local spec="$1"
  local name cmd health pattern
  IFS='|' read -r name cmd health pattern <<< "$spec"

  if health_ok "$health"; then
    if pattern_running "$pattern"; then
      record_running_pid "$name" "$pattern"
    fi
    echo -e "${GREEN}[✓] $name 이미 준비됨${NC}"
    return 0
  fi

  if pattern_running "$pattern"; then
    echo -e "${YELLOW}[!] $name 프로세스는 있으나 헬스체크 실패 — 재시작합니다.${NC}"
    pkill -f "$pattern" 2>/dev/null || true
    sleep 1
  fi

  start_one "$name" "$cmd"

  local max_attempts=30
  local attempt=0
  while [ "$attempt" -lt "$max_attempts" ]; do
    if health_ok "$health"; then
      if pattern_running "$pattern"; then
        record_running_pid "$name" "$pattern"
      fi
      echo -e "${GREEN}[✓] $name 준비 완료${NC}"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done

  echo -e "${RED}[✗] $name 준비 실패${NC}"
  echo "    로그 확인: $LOG_DIR/$name.log"
  return 1
}

wait_registry() {
  local max_attempts=30
  local attempt=0
  echo -e "${YELLOW}[*] Registry(/health) 대기 중...${NC}"
  while [ "$attempt" -lt "$max_attempts" ]; do
    if curl -fsS http://127.0.0.1:8280/health >/dev/null 2>&1; then
      echo -e "${GREEN}[✓] Registry 준비 완료${NC}"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  echo -e "${RED}[✗] Registry 준비 실패${NC}"
  return 1
}

start_all() {
  print_header
  : > "$PID_FILE"

  if ! ollama_ok; then
    echo -e "${RED}[✗] Ollama가 실행 중이 아닙니다. Agent를 시작할 수 없습니다.${NC}"
    echo "    먼저 Ollama를 켜주세요: ollama serve"
    return 1
  fi

  for spec in "${SERVICES[@]}"; do
    ensure_one "$spec"
  done

  echo
  status_all
  echo
  echo -e "${GREEN}3D 대시보드: file://$CLIENT_DIR/index.html${NC}"
  echo -e "${GREEN}운영 대시보드: file://$CLIENT_DIR/ops.html${NC}"
}

run_scenario() {
  local scenario="${1:-mine-removal}"
  print_header

  case "$scenario" in
    mine-removal|mine_removal|mine_removal_scenario)
      echo -e "${YELLOW}[*] 기뢰 제거 시나리오 실행 준비 중...${NC}"
      if ! ollama_ok; then
        echo -e "${RED}[✗] Ollama가 실행 중이 아닙니다. 시나리오를 실행할 수 없습니다.${NC}"
        echo "    먼저 Ollama를 켜주세요: ollama serve"
        return 1
      fi

      pkill -f "system_agent.py" 2>/dev/null || true
      pkill -f "device_agent.py --type" 2>/dev/null || true
      sleep 1

      for spec in "${SERVICES[@]}"; do
        ensure_one "$spec"
      done

      echo
      echo -e "${BLUE}[*] 시나리오 실행: docs/run_mine_removal_scenario.py${NC}"
      PYTHONUNBUFFERED=1 "$VENV_PYTHON" "$PROJECT_ROOT/docs/run_mine_removal_scenario.py"
      ;;
    *)
      echo -e "${RED}[✗] 알 수 없는 시나리오: $scenario${NC}"
      echo "    지원: mine-removal"
      return 1
      ;;
  esac
}

stop_all() {
  print_header
  echo -e "${YELLOW}[*] 서비스 중지 중...${NC}"

  if [ -s "$PID_FILE" ]; then
    while IFS=: read -r name pid; do
      [ -z "${pid:-}" ] && continue
      if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
      fi
    done < "$PID_FILE"
    sleep 2
    while IFS=: read -r name pid; do
      [ -z "${pid:-}" ] && continue
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done < "$PID_FILE"
  fi

  pkill -f "device_agent.py --type" 2>/dev/null || true
  pkill -f "device_registration_server.py" 2>/dev/null || true
  pkill -f "system_agent.py" 2>/dev/null || true

  : > "$PID_FILE"
  echo -e "${GREEN}[✓] 중지 완료${NC}"
}

status_all() {
  print_header
  echo -e "${BLUE}프로세스 상태${NC}"
  if ps aux | grep -E "device_agent.py --type|device_registration_server.py|system_agent.py" | grep -v grep >/dev/null; then
    ps aux | grep -E "device_agent.py --type|device_registration_server.py|system_agent.py" | grep -v grep
  else
    echo "실행 중인 CoWater 프로세스 없음"
  fi

  echo
  echo -e "${BLUE}Registry 상태${NC}"
  if curl -fsS http://127.0.0.1:8280/health >/dev/null 2>&1; then
    echo -e "${GREEN}[✓] http://127.0.0.1:8280/health 정상${NC}"
  else
    echo -e "${RED}[✗] Registry 응답 없음${NC}"
  fi

  if curl -fsS http://127.0.0.1:8280/devices >/tmp/.cowater_devices.json 2>/dev/null; then
    local count
    count=$(grep -o '"id"' /tmp/.cowater_devices.json | wc -l | tr -d ' ')
    echo -e "${GREEN}[✓] 등록 디바이스 수: $count${NC}"
  fi
}

logs_one() {
  local svc="${1:-Registry}"
  local file="$LOG_DIR/$svc.log"
  if [ ! -f "$file" ]; then
    echo "로그 파일이 없습니다: $file"
    exit 1
  fi
  tail -f "$file"
}

usage() {
  cat <<EOF
Usage:
  ./cowaterctl.sh start
  ./cowaterctl.sh stop
  ./cowaterctl.sh status
  ./cowaterctl.sh restart
  ./cowaterctl.sh scenario [mine-removal]
  ./cowaterctl.sh llm-command
  ./cowaterctl.sh logs [Registry|System-Agent|Ship-Middle|USV-Lower|AUV-Lower|ROV-Lower]
EOF
}

run_llm_command_scenario() {
  print_header
  echo -e "${YELLOW}[*] LLM 명령 시나리오 실행 준비 중...${NC}"

  if ! ollama_ok; then
    echo -e "${RED}[✗] Ollama가 실행 중이 아닙니다. 시나리오를 실행할 수 없습니다.${NC}"
    echo "    먼저 Ollama를 켜주세요: ollama serve"
    return 1
  fi

  pkill -f "system_agent.py" 2>/dev/null || true
  pkill -f "device_agent.py --type" 2>/dev/null || true
  sleep 3

  for spec in "${SERVICES[@]}"; do
    ensure_one "$spec"
  done

  echo -e "${YELLOW}[*] 디바이스 등록 안정화 대기 (3초)...${NC}"
  sleep 3

  echo
  echo -e "${BLUE}[*] 시나리오 실행: docs/run_llm_command_scenario.py${NC}"
  PYTHONUNBUFFERED=1 "$VENV_PYTHON" "$PROJECT_ROOT/docs/run_llm_command_scenario.py"
}

cmd="${1:-}"
case "$cmd" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  status)
    status_all
    ;;
  restart)
    stop_all
    sleep 1
    start_all
    ;;
  scenario|demo)
    run_scenario "${2:-mine-removal}"
    ;;
  llm-command|command-demo)
    run_llm_command_scenario
    ;;
  logs)
    logs_one "${2:-Registry}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
