#!/bin/bash

# ============================================================================
# CoWater 분산 배포 설정 스크립트
# 사용: bash setup-distributed.sh [scenario]
# 시나리오: local | remote-tunnel | cloud
# ============================================================================

set -e

SCENARIO=${1:-local}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo "=================================================="
echo "CoWater 분산 배포 설정"
echo "시나리오: $SCENARIO"
echo "=================================================="
echo

# ──────────────────────────────────────────────────────────────────────────
# 함수: 강한 비밀번호 생성
# ──────────────────────────────────────────────────────────────────────────
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
}

# ──────────────────────────────────────────────────────────────────────────
# 시나리오 1: 로컬 테스트 (같은 네트워크)
# ──────────────────────────────────────────────────────────────────────────
if [ "$SCENARIO" = "local" ]; then
    echo "✓ 로컬 네트워크 설정"
    echo "  - PostgreSQL: localhost:5432 (로컬 접근만)"
    echo "  - Redis: localhost:6379 (로컬 접근만)"
    echo

    cat > "$ENV_FILE" << 'EOF'
# 로컬 테스트 설정
POSTGRES_PASSWORD=cowater_dev
POSTGRES_BIND_ADDR=127.0.0.1
REDIS_PASSWORD=
REDIS_BIND_ADDR=127.0.0.1
CORE_BIND_ADDR=127.0.0.1
MOTH_BIND_ADDR=0.0.0.0
LOG_LEVEL=info
EOF

    echo "✓ .env 파일 생성됨"
    echo "실행 방법:"
    echo "  cd $(dirname $SCRIPT_DIR)"
    echo "  docker compose -f infra/docker-compose.yml up -d"
    echo

# ──────────────────────────────────────────────────────────────────────────
# 시나리오 2: 원격 접근 (같은 와이파이)
# ──────────────────────────────────────────────────────────────────────────
elif [ "$SCENARIO" = "remote-tunnel" ]; then
    echo "✓ 원격 접근 설정 (SSH 터널)"
    echo "  - PostgreSQL: 강화된 비밀번호"
    echo "  - Redis: 강화된 비밀번호 + 인증"
    echo "  - 접근: SSH 터널 필수"
    echo

    POSTGRES_PASS=$(generate_password)
    REDIS_PASS=$(generate_password)

    cat > "$ENV_FILE" << EOF
# 원격 접근 설정 (SSH 터널)
POSTGRES_PASSWORD=$POSTGRES_PASS
POSTGRES_BIND_ADDR=127.0.0.1
REDIS_PASSWORD=$REDIS_PASS
REDIS_BIND_ADDR=127.0.0.1
CORE_BIND_ADDR=127.0.0.1
MOTH_BIND_ADDR=0.0.0.0
LOG_LEVEL=info
EOF

    echo "✓ .env 파일 생성됨 (강한 비밀번호 적용)"
    echo
    echo "PostgreSQL 비밀번호: $POSTGRES_PASS"
    echo "Redis 비밀번호: $REDIS_PASS"
    echo
    echo "실행 방법 (중앙 서버):"
    echo "  cd $(dirname $SCRIPT_DIR)/infra"
    echo "  docker compose --env-file .env up -d"
    echo
    echo "실행 방법 (에이전트 PC):"
    echo "  # SSH 터널 생성 (다른 터미널에서 계속 실행)"
    echo "  ssh -L 6379:localhost:6379 -L 5432:localhost:5432 -L 7700:localhost:7700 user@central_server_ip"
    echo
    echo "  # 다른 터미널에서 에이전트 실행"
    echo "  export REDIS_URL=\"redis://:$REDIS_PASS@localhost:6379\""
    echo "  export CORE_API_URL=\"http://localhost:7700\""
    echo "  export DATABASE_URL=\"postgresql+asyncpg://cowater:$POSTGRES_PASS@localhost:5432/cowater\""
    echo "  cd services/detection-agents"
    echo "  pip install -r requirements.txt"
    echo "  PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704"
    echo

# ──────────────────────────────────────────────────────────────────────────
# 시나리오 3: 클라우드 배포 (VPS/EC2)
# ──────────────────────────────────────────────────────────────────────────
elif [ "$SCENARIO" = "cloud" ]; then
    echo "✓ 클라우드 배포 설정"
    echo "  - PostgreSQL: 외부 접근 가능 (보안 그룹으로 제한)"
    echo "  - Redis: 외부 접근 가능 (보안 그룹으로 제한)"
    echo "  - 강한 비밀번호 + 방화벽 필수"
    echo

    POSTGRES_PASS=$(generate_password)
    REDIS_PASS=$(generate_password)

    cat > "$ENV_FILE" << EOF
# 클라우드 배포 설정
POSTGRES_PASSWORD=$POSTGRES_PASS
POSTGRES_BIND_ADDR=0.0.0.0
REDIS_PASSWORD=$REDIS_PASS
REDIS_BIND_ADDR=0.0.0.0
CORE_BIND_ADDR=0.0.0.0
MOTH_BIND_ADDR=0.0.0.0
LOG_LEVEL=info
EOF

    echo "✓ .env 파일 생성됨 (외부 접근 활성화)"
    echo
    echo "PostgreSQL 비밀번호: $POSTGRES_PASS"
    echo "Redis 비밀번호: $REDIS_PASS"
    echo
    echo "⚠️  중요: 방화벽/보안 그룹 설정 필요"
    echo
    echo "AWS 보안 그룹:"
    echo "  - Port 5432: 에이전트 IP/32만 허용"
    echo "  - Port 6379: 에이전트 IP/32만 허용"
    echo "  - Port 7700: 필요한 IP만 허용"
    echo
    echo "실행 방법:"
    echo "  cd $(dirname $SCRIPT_DIR)/infra"
    echo "  docker compose --env-file .env up -d"
    echo
    echo "에이전트 접속 (원격 PC):"
    echo "  export REDIS_URL=\"redis://:$REDIS_PASS@your_public_ip:6379\""
    echo "  export CORE_API_URL=\"http://your_public_ip:7700\""
    echo "  export DATABASE_URL=\"postgresql+asyncpg://cowater:$POSTGRES_PASS@your_public_ip:5432/cowater\""
    echo "  cd services/detection-agents"
    echo "  pip install -r requirements.txt"
    echo "  PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704"
    echo

else
    echo "❌ 알 수 없는 시나리오: $SCENARIO"
    echo "사용법: bash setup-distributed.sh [local | remote-tunnel | cloud]"
    exit 1
fi

echo "=================================================="
echo "✓ 설정 완료"
echo "=================================================="
