#!/bin/bash

set -e

# 색상 정의
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# 로그 파일 설정
LOG_DIR=".logs/demo"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
LOG_FILE="$LOG_DIR/demo-$TIMESTAMP.log"
echo "=== CoWater Demo: $(date) ===" > "$LOG_FILE"

log_to_file() { echo "$1" >> "$LOG_FILE"; }
log_both()    { echo "$1"; log_to_file "$1"; }

section_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    log_to_file "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_to_file "$1"
    log_to_file "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

print_json() { echo "$1" | jq '.' 2>/dev/null || echo "$1"; }

# ── 헤더 ─────────────────────────────────────────
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CoWater Demo - 사용자 명령 처리 시스템                 ║"
echo "║  RequestHandler → MissionPlanner → DeviceBridge → Device║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 사용자 입력 ───────────────────────────────────
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

# ── 서버 사전 체크 ────────────────────────────────
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
# Step 1: RequestHandler 호출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "Step 1: RequestHandler → 의도 분류"

log_to_file "POST http://127.0.0.1:9116/execute"

RESPONSE=$(curl -s -X POST http://127.0.0.1:9116/execute \
    -H 'Content-Type: application/json' \
    -d "{\"user_input\":\"$USER_COMMAND\"}" 2>/dev/null)

if [ -z "$RESPONSE" ]; then
    echo -e "${RED}❌ RequestHandler 응답 없음${NC}"
    log_to_file "❌ RequestHandler 응답 없음"
    exit 1
fi

echo "RequestHandler 응답:"
print_json "$RESPONSE"
echo "$RESPONSE" | jq '.' 2>/dev/null >> "$LOG_FILE" || echo "$RESPONSE" >> "$LOG_FILE"

STATUS=$(echo "$RESPONSE" | jq -r '.status' 2>/dev/null)
MESSAGE=$(echo "$RESPONSE" | jq -r '.message // empty' 2>/dev/null)

# ── 에러 처리 ─────────────────────────────────────
if [ "$STATUS" = "ERROR" ]; then
    echo ""
    echo -e "${RED}❌ 오류: $MESSAGE${NC}"
    log_to_file "❌ 오류: $MESSAGE"
    exit 1
fi

if [ "$STATUS" = "INFEASIBLE" ]; then
    echo ""
    echo -e "${YELLOW}⚠ 미션 수행 불가${NC}"
    echo ""
    echo "$MESSAGE"
    log_to_file "⚠ 미션 수행 불가: $MESSAGE"
    exit 0
fi

# ── 즉시 응답 (QUERY/REPORT) ─────────────────────
if [ "$STATUS" = "SUCCESS" ]; then
    section_header "Step 2: 응답"
    echo "$MESSAGE"
    log_to_file "응답: $MESSAGE"
    section_header "완료"
    echo -e "${GREEN}✓ 명령 처리 완료${NC}"
    echo ""
    echo "로그 파일: $LOG_FILE"
    log_to_file "=== 명령 처리 완료 ==="
    exit 0
fi

# ── 미션 의도 (PENDING) — 이벤트 스트리밍 시작 ───
if [ "$STATUS" = "PENDING" ]; then
    INTENT_ID=$(echo "$RESPONSE" | jq -r '.intent_id // empty' 2>/dev/null)

    section_header "Step 2: MissionPlanner 처리 중 — 이벤트 스트림"
    echo -e "${CYAN}RequestHandler → MissionPlanner로 전달됨${NC}"
    echo ""
    echo "$MESSAGE"
    echo ""
    echo -e "${YELLOW}관련 이벤트를 수신하는 중... (최대 60초, Ctrl+C로 중단)${NC}"
    echo ""
    log_to_file "PENDING: $MESSAGE"
    log_to_file "intent_id: $INTENT_ID"

    REGISTRY_URL="http://127.0.0.1:8280"
    SEEN_IDS=""
    DEADLINE=$(($(date +%s) + 60))
    MISSION_DONE=false
    # 데모 시작 시각 (ISO 8601) — 이전 세션 이벤트 필터링용
    DEMO_START_ISO=$(date -u +"%Y-%m-%dT%H:%M:%S")

    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        EVENTS=$(curl -s --max-time 3 "$REGISTRY_URL/events?limit=50" 2>/dev/null)
        if [ -z "$EVENTS" ]; then
            sleep 2
            continue
        fi

        # 새 이벤트만 처리 (event_id 기준)
        ITEMS=$(echo "$EVENTS" | jq -c '.[] // empty' 2>/dev/null || echo "$EVENTS" | jq -c '.items[]? // empty' 2>/dev/null)

        while IFS= read -r ITEM; do
            [ -z "$ITEM" ] && continue
            EID=$(echo "$ITEM" | jq -r '.event_id // .id // empty' 2>/dev/null)
            [ -z "$EID" ] && continue
            echo "$SEEN_IDS" | grep -q "$EID" && continue

            # 데모 시작 이전 이벤트 스킵
            ECREATED=$(echo "$ITEM" | jq -r '.created_at // .timestamp // empty' 2>/dev/null)
            if [ -n "$ECREATED" ] && [ "${ECREATED:0:19}" \< "$DEMO_START_ISO" ]; then
                SEEN_IDS="$SEEN_IDS $EID"
                continue
            fi

            SEEN_IDS="$SEEN_IDS $EID"

            ETYPE=$(echo "$ITEM" | jq -r '.type // .event_type // empty' 2>/dev/null)
            ETITLE=$(echo "$ITEM" | jq -r '.title // empty' 2>/dev/null)
            EMSG=$(echo "$ITEM" | jq -r '.message // empty' 2>/dev/null)
            ESEV=$(echo "$ITEM" | jq -r '.severity // "INFO"' 2>/dev/null)

            # 관련 이벤트 유형만 표시
            case "$ETYPE" in
                SYS_INTENT_CLASSIFIED|SYS_MISSION_UPDATED|SYS_TASK_DISPATCHED|\
                SYS_TASK_COMPLETED|SYS_TASK_FAILED|SYS_MISSION_COMPLETED|\
                SYS_ANOMALY_DETECTED|DEVICE_HEALTHCHECK)
                    ;;
                *) continue ;;
            esac

            # 심각도별 색상
            case "$ESEV" in
                CRITICAL) COLOR="$RED" ;;
                WARNING)  COLOR="$YELLOW" ;;
                *)        COLOR="$CYAN" ;;
            esac

            TIMESTAMP_STR=$(echo "$ITEM" | jq -r '.created_at // .timestamp // empty' 2>/dev/null | cut -c12-19)
            echo -e "${COLOR}[$TIMESTAMP_STR] $ETYPE${NC}"
            [ -n "$ETITLE" ] && echo "  제목: $ETITLE"
            [ -n "$EMSG" ]   && echo "  내용: $EMSG"
            echo ""
            log_to_file "[$TIMESTAMP_STR] $ETYPE: $ETITLE / $EMSG"

            # 미션 완료 감지
            case "$ETYPE" in
                SYS_MISSION_COMPLETED)
                    MISSION_DONE=true
                    DEADLINE=0
                    ;;
            esac
        done <<< "$ITEMS"

        $MISSION_DONE && break
        sleep 2
    done

    echo ""
    if $MISSION_DONE; then
        section_header "완료"
        echo -e "${GREEN}✓ 미션 완료${NC}"
    else
        section_header "처리 중"
        echo -e "${YELLOW}⏳ 미션이 계속 진행 중입니다. UI의 Proposals에서 승인 후 진행 상황을 확인하세요.${NC}"
    fi

    echo ""
    echo "로그 파일: $LOG_FILE"
    log_to_file "=== 명령 처리 완료 ==="
    exit 0
fi

# ── 알 수 없는 상태 ───────────────────────────────
echo ""
echo -e "${RED}알 수 없는 응답 상태: $STATUS${NC}"
log_to_file "알 수 없는 상태: $STATUS"
exit 1
