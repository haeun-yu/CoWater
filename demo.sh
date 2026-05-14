#!/bin/bash

set -e

# 색상 정의
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 로그 파일 설정
LOG_DIR=".logs/demo"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
LOG_FILE="$LOG_DIR/demo-$TIMESTAMP.log"
echo "=== CoWater Demo: $(date) ===" > "$LOG_FILE"

# 함수
log_to_file() {
    echo "$1" >> "$LOG_FILE"
}

log_both() {
    echo "$1"
    log_to_file "$1"
}

section_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    log_to_file ""
    log_to_file "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_to_file "$1"
    log_to_file "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

print_json() {
    echo "$1" | jq '.' 2>/dev/null || echo "$1"
}

# 헤더
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CoWater Demo - 사용자 명령 처리 시스템 (UI 전용)       ║"
echo "║  각 Agent의 실제 처리 데이터를 표시합니다               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 사용자 입력
echo ""
echo "사용자 명령을 입력하세요:"
echo ""

if [ -n "$1" ]; then
    USER_COMMAND="$1"
    echo "입력: $USER_COMMAND"
else
    read -p "> " USER_COMMAND
fi

if [ -z "$USER_COMMAND" ]; then
    echo "❌ 명령을 입력하지 않았습니다"
    exit 1
fi

log_both ""
log_both "=== 사용자 명령 ==="
log_both "입력: $USER_COMMAND"
log_both ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서버 사전 체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if ! curl -s --max-time 2 http://127.0.0.1:9116/health >/dev/null 2>&1; then
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  서버가 실행 중이지 않습니다 (포트 9116 응답 없음)${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  시작 방법:"
    echo -e "  ${YELLOW}./cowaterctl.sh start --no-client${NC}"
    echo ""
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: 명령을 RequestHandler로 전달
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "Step 1: RequestHandler 호출"

log_to_file "사용자 명령을 RequestHandler로 전달:"
log_to_file "POST http://127.0.0.1:9116/execute"
log_to_file "Payload: {\"user_input\": \"$USER_COMMAND\"}"

RESPONSE=$(curl -s -X POST http://127.0.0.1:9116/execute \
    -H 'Content-Type: application/json' \
    -d "{\"user_input\":\"$USER_COMMAND\"}" 2>/dev/null)

if [ -z "$RESPONSE" ]; then
    echo -e "${RED}❌ RequestHandler 응답 없음${NC}"
    echo "  시스템이 실행 중인지 확인하세요."
    log_to_file "❌ RequestHandler 응답 없음"
    exit 1
fi

echo "RequestHandler 응답:"
print_json "$RESPONSE"
log_to_file ""
log_to_file "RequestHandler 응답:"
echo "$RESPONSE" | jq '.' 2>/dev/null >> "$LOG_FILE" || echo "$RESPONSE" >> "$LOG_FILE"

# 상태 확인
STATUS=$(echo "$RESPONSE" | jq -r '.status' 2>/dev/null)

if [ "$STATUS" = "ERROR" ]; then
    MESSAGE=$(echo "$RESPONSE" | jq -r '.message' 2>/dev/null)
    echo ""
    echo -e "${RED}❌ 오류: $MESSAGE${NC}"
    log_to_file ""
    log_to_file "❌ 오류: $MESSAGE"
    exit 1
fi

# 처리 단계 수
STEPS=$(echo "$RESPONSE" | jq -r '.steps // "?"' 2>/dev/null)
echo ""
echo -e "${GREEN}✓ 처리 완료 (${STEPS}단계)${NC}"
log_to_file "처리 단계: $STEPS"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: AI 응답 출력
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "Step 2: AI 응답"

MESSAGE=$(echo "$RESPONSE" | jq -r '.message // empty' 2>/dev/null)
if [ -n "$MESSAGE" ]; then
    echo "$MESSAGE"
    log_to_file "AI 응답:"
    log_to_file "$MESSAGE"
else
    echo "(응답 메시지 없음)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 완료
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "완료"

echo -e "${GREEN}✓ 명령 처리 완료${NC}"
echo ""
echo "로그 파일: $LOG_FILE"
log_to_file ""
log_to_file "=== 명령 처리 완료 ==="
