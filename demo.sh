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

# Intent 추출: event에 포함되어 있거나 응답 구조에서 유추
INTENT=$(echo "$RESPONSE" | jq -r '.event.data.intent // empty' 2>/dev/null)

# Intent가 없으면 응답 구조에서 유추
if [ -z "$INTENT" ]; then
    HAS_PROPOSAL=$(echo "$RESPONSE" | jq 'has("proposal")' 2>/dev/null)
    HAS_REPORT=$(echo "$RESPONSE" | jq 'has("report")' 2>/dev/null)
    HAS_DEVICES=$(echo "$RESPONSE" | jq '.data | has("devices")' 2>/dev/null)

    if [ "$HAS_PROPOSAL" = "true" ]; then
        INTENT="MISSION"
    elif [ "$HAS_REPORT" = "true" ]; then
        INTENT="REPORT"
    elif [ "$HAS_DEVICES" = "true" ]; then
        INTENT="QUERY"
    fi
fi

echo ""
echo -e "${GREEN}✓ 응답 분석됨${NC}"
if [ -n "$INTENT" ]; then
    echo "추론된 Intent: $INTENT"
    log_to_file "추론된 Intent: $INTENT"
fi

# Intent별 처리
if [ -n "$INTENT" ]; then
    case "$INTENT" in
        QUERY)
            section_header "Step 2: QUERY 처리 - RequestHandler가 직접 처리"

            DEVICE_COUNT=$(echo "$RESPONSE" | jq '.data.devices | length' 2>/dev/null || echo "0")
            echo "Device 목록 ($DEVICE_COUNT개):"
            echo "$RESPONSE" | jq -r '.data.devices[] | "  • \(.name) (\(.type)): \(.connectivity_status)"' 2>/dev/null | head -10
            log_to_file "Device 목록:"
            echo "$RESPONSE" | jq '.data.devices' 2>/dev/null >> "$LOG_FILE"

            echo ""
            MISSION_COUNT=$(echo "$RESPONSE" | jq '.data.missions | length' 2>/dev/null || echo "0")
            echo "진행 중인 Mission: $MISSION_COUNT개"
            log_to_file "Mission 개수: $MISSION_COUNT"
            if [ "$MISSION_COUNT" -gt 0 ]; then
                echo "$RESPONSE" | jq -r '.data.missions[] | "  • \(.title) - \(.status)"' 2>/dev/null | head -5
                log_to_file "Mission 목록:"
                echo "$RESPONSE" | jq '.data.missions' 2>/dev/null >> "$LOG_FILE"
            fi
            ;;

        REPORT)
            section_header "Step 2: REPORT 처리 - 분석 리포트"

            REPORT=$(echo "$RESPONSE" | jq -r '.report' 2>/dev/null)
            if [ -n "$REPORT" ] && [ "$REPORT" != "null" ]; then
                echo "생성된 리포트:"
                echo "$RESPONSE" | jq '.report' 2>/dev/null
                log_to_file "리포트:"
                echo "$RESPONSE" | jq '.report' 2>/dev/null >> "$LOG_FILE"
            else
                echo "리포트 생성 중..."
                log_to_file "리포트 생성 처리"
            fi
            ;;

        MISSION)
            section_header "Step 2: MISSION 처리 - 미션 계획"

            PROPOSAL=$(echo "$RESPONSE" | jq '.proposal' 2>/dev/null)
            if [ -n "$PROPOSAL" ] && [ "$PROPOSAL" != "null" ]; then
                echo "생성된 Proposal:"
                PROPOSAL_COUNT=$(echo "$PROPOSAL" | jq '.proposals | length' 2>/dev/null || echo "0")
                echo "  $PROPOSAL_COUNT개의 전략 제안"
                log_to_file "Proposal:"
                echo "$RESPONSE" | jq '.proposal' 2>/dev/null >> "$LOG_FILE"

                APPROVAL_STATUS=$(echo "$RESPONSE" | jq -r '.status' 2>/dev/null)
                if [ "$APPROVAL_STATUS" = "PENDING_APPROVAL" ]; then
                    section_header "Step 3: 사용자 승인 대기"
                    echo "미션 계획이 생성되었습니다."
                    echo "실제 시스템에서는 사용자 승인 후 실행됩니다."
                    log_to_file "미션 생성 완료, 사용자 승인 대기"
                fi
            else
                echo "미션 계획 생성 중..."
                log_to_file "미션 계획 생성 처리"
            fi
            ;;

        SYSTEM_CONTROL)
            section_header "Step 2: SYSTEM_CONTROL 처리"
            echo "시스템 제어 명령 처리 중..."
            echo "$RESPONSE" | jq '.' 2>/dev/null | head -30
            log_to_file "SYSTEM_CONTROL 처리:"
            echo "$RESPONSE" | jq '.' 2>/dev/null >> "$LOG_FILE"
            ;;

        *)
            echo ""
            echo "Intent: $INTENT"
            log_to_file "Intent: $INTENT"
            ;;
    esac
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
