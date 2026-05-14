#!/bin/bash

REGISTRY_URL="http://127.0.0.1:8280"
REQUEST_HANDLER_URL="http://127.0.0.1:9116"

# 색상
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 헤더
echo -e "${BLUE}"
cat << 'EOF'
╔═══════════════════════════════════════╗
║       CoWater Demo - Mission Flow      ║
╚═══════════════════════════════════════╝
EOF
echo -e "${NC}"
echo ""

# 목표 입력받기
if [ -n "$1" ]; then
    goal="$1"
else
    read -p "미션 목표를 입력하세요: " goal
fi

if [ -z "$goal" ]; then
    echo "미션 목표를 입력하지 않았습니다"
    exit 1
fi

echo ""

# [1/5] 시스템 확인
echo -e "${BLUE}[1/5]${NC} 시스템 확인 중..."
if ! curl -s "$REGISTRY_URL/health" > /dev/null 2>&1; then
    echo "❌ Registry 연결 실패"
    exit 1
fi
echo -e "${GREEN}✓${NC} Registry 연결됨"
sleep 1

# [2/5] 미션 생성
echo ""
echo -e "${BLUE}[2/5]${NC} 미션 생성 중..."
response=$(curl -s -X POST "$REQUEST_HANDLER_URL/mission-proposals/generate" \
    -H 'Content-Type: application/json' \
    -d "{\"goal\":\"$goal\"}")

proposal_id=$(echo "$response" | jq -r '.proposal.proposal_id' 2>/dev/null)
if [ -z "$proposal_id" ] || [ "$proposal_id" == "null" ]; then
    echo "❌ 미션 생성 실패"
    echo "응답: $response"
    exit 1
fi

echo -e "${GREEN}✓${NC} 미션 생성됨 (ID: $proposal_id)"
echo "  제목: $(echo "$response" | jq -r '.proposal.title')"
echo "  상태: $(echo "$response" | jq -r '.proposal.status')"
sleep 1

# [3/5] 미션 상세 정보 표시
echo ""
echo -e "${BLUE}[3/5]${NC} 미션 상세 정보"
echo ""

mission_type=$(echo "$response" | jq -r '.proposal.mission_type' 2>/dev/null)
mission_goal=$(echo "$response" | jq -r '.proposal.goal' 2>/dev/null)

echo "📋 미션 정보:"
echo "  • 제목: $(echo "$response" | jq -r '.proposal.title')"
echo "  • 목표: $mission_goal"
echo "  • 타입: $mission_type"
echo "  • 우선순위: $(echo "$response" | jq -r '.proposal.priority')"
echo ""

# 미션 타입별 상세 정보 및 예상 Task
echo "📋 예상 Task 계획:"
echo ""

case "$mission_type" in
    mine_clearance)
        echo "🔴 기뢰 탐지/제거 작업"
        echo "  필요 장비: ROV, 소나, 기뢰 처리 도구"
        echo "  예상 시간: 8-12시간"
        echo "  위험도: 🔴 매우 높음"
        echo "  비용: 약 50,000 USD"
        echo ""
        echo "🎯 Task 순서:"
        echo "  [1] 작업용 USV → 항만 진입로 소나 스캔 (1시간)"
        echo "  [2] 작업용 ROV → 기뢰 위치 정밀 탐지 (4시간)"
        echo "  [3] 작업용 ROV → 기뢰 제거 작업 (3시간)"
        echo "  [4] 통제 함정 → 최종 안전성 확인 (1시간)"
        ;;
    survey)
        echo "📊 조사 미션"
        echo "  필요 장비: AUV, GPS, 카메라"
        echo "  예상 시간: 4-6시간"
        echo "  위험도: 🟡 보통"
        echo "  비용: 약 15,000 USD"
        echo ""
        echo "🎯 Task 순서:"
        echo "  [1] 정찰용 AUV → 해역 지형 스캔 (3시간)"
        echo "  [2] 작업용 USV → 표층 샘플 채집 (1시간)"
        echo "  [3] 통제 함정 → 데이터 수집 및 정리 (1시간)"
        ;;
    monitoring)
        echo "📡 모니터링 미션"
        echo "  필요 장비: USV, 센서"
        echo "  예상 시간: 연속 24시간"
        echo "  위험도: 🟢 낮음"
        echo "  비용: 약 5,000 USD/일"
        echo ""
        echo "🎯 Task 순서:"
        echo "  [1] 작업용 USV → 센서 배포 (30분)"
        echo "  [2] 작업용 USV → 실시간 데이터 수집 (23시간)"
        echo "  [3] 통제 함정 → 센서 회수 및 분석 (30분)"
        ;;
    *)
        echo "🔧 일반 미션"
        echo "  필요 장비: 기본 해양 장비"
        echo "  예상 시간: 미정"
        echo "  위험도: 🟡 보통"
        echo ""
        echo "🎯 Task 순서:"
        echo "  [1] 작업용 USV → 초기 정찰"
        echo "  [2] 정찰용 AUV → 상세 조사"
        echo "  [3] 통제 함정 → 최종 확인"
        ;;
esac

echo ""
echo -e "${BLUE}승인 요청${NC}"
if [ -z "$TERM" ] || [ "$TERM" == "dumb" ]; then
    approval="y"
    echo "자동 승인 모드"
else
    read -p "이 미션을 승인하시겠습니까? (y/n): " approval
fi

if [[ ! $approval =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⚠${NC} 미션 승인이 취소되었습니다"
    exit 0
fi

echo -e "${GREEN}✓${NC} 미션이 승인되었습니다"
sleep 1

# [4/5] Task 할당
echo ""
echo -e "${BLUE}[4/5]${NC} Task 할당 중..."
devices=$(curl -s "$REGISTRY_URL/devices" | jq '.' 2>/dev/null)
device_count=$(echo "$devices" | jq 'length' 2>/dev/null || echo "0")
echo -e "${GREEN}✓${NC} $device_count개 디바이스에 Task 할당"
sleep 1

# [5/5] 모니터링
echo ""
echo -e "${BLUE}[5/5]${NC} 실시간 모니터링 중..."
echo ""
echo "📡 디바이스 상태:"
echo "$devices" | jq -r '.[] | "  • \(.name) (\(.id)): \(if .connected then "🟢 ONLINE" else "🔴 OFFLINE" end) - Battery: \(.battery // "N/A")%"' 2>/dev/null
echo ""
echo "📊 미션 진행:"

# 진행률 애니메이션
for i in 0 10 20 30 40 50 60 70 80 90 100; do
    filled=$((i / 10))
    empty=$((10 - filled))
    printf "  Progress: ["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "] %d%%\r" "$i"
    sleep 0.3
done
echo ""
echo ""

# 완료
echo -e "${GREEN}✓ 미션 완료!${NC}"
echo ""
echo "📋 최종 요약:"
echo "  미션 ID: $proposal_id"
echo "  목표: $goal"
echo "  상태: 완료"
echo "  디바이스: $device_count 개"
echo ""
