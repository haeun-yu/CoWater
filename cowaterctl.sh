#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"
CONFIG_PATH="$SCRIPT_DIR/server/system-agent/config.json"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수: tmux 세션 확인
session_exists() {
    tmux has-session -t "$1" 2>/dev/null
}

# 함수: 로그 출력
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 변수: 클라이언트 시작 여부
SKIP_CLIENT=${SKIP_CLIENT:-false}

# 함수: venv 활성화 및 서비스 시작
start_service() {
    local session_name=$1
    local service_type=$2
    local cmd=$3
    local cwd=$4

    if session_exists "$session_name"; then
        log_warn "Session '$session_name' already exists"
        return
    fi

    log_info "Starting $service_type..."

    # venv 활성화 + 명령 실행
    tmux new-session -d -s "$session_name" \
        -c "$cwd" \
        "source $VENV_PATH/bin/activate && $cmd"

    log_success "Started $service_type (session: $session_name)"
}

# 함수: 포트 확인 (curl 사용)
check_port() {
    local port=$1
    local service=$2

    # curl로 연결 확인 (timeout 1초)
    if curl -s --max-time 1 http://127.0.0.1:"$port"/health >/dev/null 2>&1 || \
       curl -s --max-time 1 http://127.0.0.1:"$port"/ >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $service (port $port)"
        return 0
    else
        echo -e "  ${RED}✗${NC} $service (port $port)"
        return 1
    fi
}

# =============================================================================
# COMMANDS
# =============================================================================

start() {
    # Parse options
    local skip_client=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-client|--backend-only)
                skip_client=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    log_info "Starting CoWater system..."
    if [ "$skip_client" = true ]; then
        log_info "Backend only mode (skipping client)"
    fi

    # 0. venv 확인
    if [ ! -d "$VENV_PATH" ]; then
        log_error "venv not found at $VENV_PATH"
        log_info "Run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # 1. Registry Server
    start_service "cowater-registry" \
        "Registry Server" \
        "python device_registration_server.py" \
        "$SCRIPT_DIR/server/registration"

    sleep 2

    # 2. System Agent Layer
    start_service "cowater-system-agent" \
        "System Agent Layer" \
        "python run_system_agents.py --config $CONFIG_PATH" \
        "$SCRIPT_DIR/server/system-agent"

    sleep 2

    # 3. Device Agents (Lower Layer)
    start_service "cowater-device-usv" \
        "Device Agent (USV-Lower)" \
        "python device_agent.py --type usv --layer lower" \
        "$SCRIPT_DIR/device"

    sleep 1

    start_service "cowater-device-auv" \
        "Device Agent (AUV-Lower)" \
        "python device_agent.py --type auv --layer lower" \
        "$SCRIPT_DIR/device"

    sleep 1

    start_service "cowater-device-rov" \
        "Device Agent (ROV-Lower)" \
        "python device_agent.py --type rov --layer lower" \
        "$SCRIPT_DIR/device"

    sleep 2

    # 4. Client (React + Vite)
    if [ "$skip_client" != true ] && [ -d "$SCRIPT_DIR/client" ]; then
        log_info "Preparing Client SPA..."

        # node_modules 확인
        if [ ! -d "$SCRIPT_DIR/client/node_modules" ]; then
            log_info "Installing dependencies (npm install)..."
            cd "$SCRIPT_DIR/client" && npm install > /dev/null 2>&1
            log_success "Dependencies installed"
        fi

        start_service "cowater-client" \
            "Client SPA (Vite)" \
            "npm run dev -- --host 127.0.0.1 --port 5173" \
            "$SCRIPT_DIR/client"

        sleep 3
    fi

    log_success "All services started!"
    echo ""
    echo -e "${BLUE}Access points:${NC}"
    echo "  Client SPA:      http://127.0.0.1:5173/"
    echo "  Ops Dashboard:   http://127.0.0.1:5173/ops"
    echo ""
    echo -e "${BLUE}View logs:${NC}"
    echo "  ./cowaterctl.sh logs registry"
    echo "  ./cowaterctl.sh logs system-agent"
    echo "  ./cowaterctl.sh logs device-usv"
    echo "  ./cowaterctl.sh logs device-auv"
    echo "  ./cowaterctl.sh logs device-rov"
    echo "  ./cowaterctl.sh logs client"
}

stop() {
    log_info "Stopping CoWater system..."

    local sessions=("cowater-registry" "cowater-system-agent" "cowater-device-usv" "cowater-device-auv" "cowater-device-rov" "cowater-client")

    for session in "${sessions[@]}"; do
        if session_exists "$session"; then
            tmux kill-session -t "$session"
            log_success "Stopped $session"
        fi
    done

    log_success "All services stopped"
}

restart() {
    stop
    sleep 1
    start "$@"
}

status() {
    log_info "Checking service status..."
    echo ""

    local all_ok=true

    check_port 8280 "Registry Server" || all_ok=false
    check_port 9116 "RequestHandler" || all_ok=false
    check_port 9110 "DeviceBridge" || all_ok=false
    check_port 9111 "MissionPlanner" || all_ok=false
    check_port 9112 "PolicyManager" || all_ok=false
    check_port 9113 "SystemSentinel" || all_ok=false
    check_port 9114 "InsightReporter" || all_ok=false
    check_port 9201 "USV Lower Agent" || all_ok=false
    check_port 9202 "AUV Lower Agent" || all_ok=false
    check_port 9203 "ROV Lower Agent" || all_ok=false

    echo ""
    if [ "$all_ok" = true ]; then
        log_success "All services running"
    else
        log_warn "Some services not responding"
    fi
}

logs() {
    local service=$1

    case "$service" in
        registry)
            tmux attach-session -t "cowater-registry"
            ;;
        system-agent)
            tmux attach-session -t "cowater-system-agent"
            ;;
        device-usv)
            tmux attach-session -t "cowater-device-usv"
            ;;
        device-auv)
            tmux attach-session -t "cowater-device-auv"
            ;;
        device-rov)
            tmux attach-session -t "cowater-device-rov"
            ;;
        client)
            tmux attach-session -t "cowater-client"
            ;;
        *)
            log_error "Unknown service: $service"
            echo ""
            echo "Available services:"
            echo "  registry, system-agent, device-usv, device-auv, device-rov, client"
            exit 1
            ;;
    esac
}

# =============================================================================
# MAIN
# =============================================================================

case "${1:-}" in
    start)
        shift
        start "$@"
        ;;
    stop)
        stop
        ;;
    restart)
        shift
        restart "$@"
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    *)
        echo "CoWater Service Controller"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs} [options]"
        echo ""
        echo "Commands:"
        echo "  start [--no-client]     Start all services (or backend only)"
        echo "  stop                    Stop all services"
        echo "  restart [--no-client]   Restart all services (or backend only)"
        echo "  status                  Check service status"
        echo "  logs <service>          View live logs for a service"
        echo ""
        echo "Options:"
        echo "  --no-client, --backend-only   Skip client startup (backend only)"
        echo ""
        echo "Available services for logs:"
        echo "  registry, system-agent, device-usv, device-auv, device-rov"
        exit 1
        ;;
esac
