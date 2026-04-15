.PHONY: help up up-sim up-ollama down logs status \
	dev-core dev-control-agents dev-detection-agents dev-analysis-agents dev-response-agents dev-learning-agents dev-supervision-agents dev-report-agents dev-moth-bridge dev-frontend dev-simulator \
	bootstrap-python bootstrap-frontend bootstrap-dev dev-infra down-infra logs-infra status-infra \
	dev-stop dev-stop-apps dev-all-tmux dev-all-stop-tmux dev-all-manual dev-all-quick dev-local dev-local-sim \
	test-e2e test-unit test-all \
	install setup clean \
	up-host-ollama up-docker-ollama up-vllm up-host-ollama-sim up-docker-ollama-sim up-vllm-sim \
	rebuild-host-ollama-sim rebuild-docker-ollama-sim rebuild-vllm-sim \
	down-host-ollama down-docker-ollama down-vllm down-host-ollama-sim down-docker-ollama-sim down-vllm-sim \
	downall-host-ollama start-host-ollama stop-host-ollama restart-host-ollama \
	ps-host-ollama ps-docker-ollama ps-vllm \
	logs-host-ollama logs-docker-ollama logs-vllm \
	install-host-ollama-launchd uninstall-host-ollama-launchd \
	docker-doctor docker-cleanup-safe

# ─────────────────────────────────────────────────────
# 헬프
# ─────────────────────────────────────────────────────
help:
	@echo "CoWater Development Commands"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make up               - 전체 스택 실행 (기본: Ollama 로컬)"
	@echo "  make up-sim           - 시뮬레이터 포함 실행"
	@echo "  make down             - 전체 스택 종료"
	@echo "  make logs             - 전체 로그 보기"
	@echo "  make status           - 서비스 상태 확인"
	@echo ""
	@echo "로컬 개발 (개별 실행):"
	@echo "  make bootstrap-dev             - 로컬 개발 의존성 한 번에 설치 (.venv + frontend)"
	@echo "  make dev-infra                 - postgres + redis만 Docker로 실행"
	@echo "  make dev-local                 - 개발용 전체 스택 실행 (infra Docker + 앱 로컬 tmux) ⚡ 추천"
	@echo "  make dev-local-sim             - 개발용 전체 스택 + simulator"
	@echo "  make dev-stop                  - dev-local/dev-local-sim 종료 (tmux + infra)"
	@echo "  make dev-stop-apps             - 로컬 tmux 앱 세션만 종료"
	@echo "  make dev-core                  - Core (FastAPI + WebSocket hub)"
	@echo "  make dev-control-agents        - Control (Chat Agent)"
	@echo "  make dev-detection-agents      - Detection (CPA, Anomaly, Zone, Distress agents)"
	@echo "  make dev-analysis-agents       - Analysis (Ollama 로컬 LLM 분석)"
	@echo "  make dev-response-agents       - Response (Alert 생성)"
	@echo "  make dev-learning-agents       - Learning (거짓 경보율 추적)"
	@echo "  make dev-supervision-agents    - Supervision (에이전트 모니터링)"
	@echo "  make dev-report-agents         - Report (AI 리포트 생성)"
	@echo "  make dev-moth-bridge           - Moth Bridge (WebSocket relay + Redis publish)"
	@echo "  make dev-frontend              - Frontend (Next.js 대시보드)"
	@echo "  make dev-simulator             - Simulator (AIS 데이터 시뮬레이션)"
	@echo ""
	@echo "로컬 개발 (한번에 실행 - tmux 필수):"
	@echo "  make dev-all-tmux              - 모든 서비스 tmux 윈도우에서 실행 ⚡ 추천"
	@echo "  make dev-all-stop-tmux         - dev-all-tmux tmux 세션 종료"
	@echo "  make dev-all-quick             - Core + Frontend만 빠르게 실행"
	@echo "  make dev-all-manual            - 수동 실행 가이드 (터미널 9개 필요)"
	@echo ""
	@echo "테스트:"
	@echo "  make test-e2e         - E2E 이벤트 흐름 테스트"
	@echo "  make test-unit        - Unit 테스트"
	@echo "  make test-all         - 모든 테스트"
	@echo ""
	@echo "설정:"
	@echo "  make setup            - 개발 환경 초기화"
	@echo "  make clean            - 임시 파일 정리"

# ─────────────────────────────────────────────────────
# Docker Compose - 핵심 명령어
# ─────────────────────────────────────────────────────
up:
	cd infra && docker compose up -d

up-sim:
	cd infra && SCENARIO=demo docker compose --profile simulation up -d

up-ollama:
	cd infra && docker compose --profile ollama up -d

down:
	cd infra && docker compose down

logs:
	cd infra && docker compose logs -f

status:
	cd infra && docker compose ps

build:
	cd infra && docker compose build

# ─────────────────────────────────────────────────────
# 로컬 Python 실행 헬퍼
# ─────────────────────────────────────────────────────
DEV_PYTHON := $(shell if command -v python3.12 >/dev/null 2>&1; then command -v python3.12; elif command -v python3.11 >/dev/null 2>&1; then command -v python3.11; else command -v python3; fi)
VENV_PYTHON := $(CURDIR)/.venv/bin/python

define ensure_dev_venv
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Creating local virtualenv at .venv using $(DEV_PYTHON)"; \
		$(DEV_PYTHON) -m venv .venv; \
	elif ! $(VENV_PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12)} else 1)"; then \
		echo "Recreating .venv with Python 3.11/3.12 (current venv is incompatible)"; \
		rm -rf .venv; \
		$(DEV_PYTHON) -m venv .venv; \
	fi
endef

define ensure_python_service
	$(call ensure_dev_venv)
	@cd services/$(1) && PYTHONPATH=../.. $(VENV_PYTHON) -c "import importlib.util, sys; missing=[m for m in '$(3)'.split() if importlib.util.find_spec(m) is None]; sys.exit(1 if missing else 0)" || \
		( echo "Installing Python dependencies for services/$(1)"; \
		  $(VENV_PYTHON) -m pip install --upgrade pip && \
		  $(VENV_PYTHON) -m pip install -r services/$(1)/requirements.txt )
endef

define run_python_service
	$(call ensure_python_service,$(1),$(2),$(3))
	cd services/$(1) && PYTHONPATH=../.. $(VENV_PYTHON) -m uvicorn main:app --reload --port $(2)
endef

define run_python_script
	$(call ensure_python_service,$(1),$(2),$(3))
	cd services/$(1) && PYTHONPATH=../.. $(VENV_PYTHON) $(2)
endef

define ensure_frontend
	@if [ ! -d "services/frontend/node_modules" ]; then \
		echo "Installing frontend dependencies"; \
		cd services/frontend && npm install; \
	fi
endef

PYTHON_REQUIREMENTS := services/core/requirements.txt services/control-agents/requirements.txt services/detection-agents/requirements.txt services/analysis-agents/requirements.txt services/response-agents/requirements.txt services/learning-agents/requirements.txt services/supervision-agents/requirements.txt services/report-agents/requirements.txt services/moth-bridge/requirements.txt services/simulator/requirements.txt

bootstrap-python:
	$(call ensure_dev_venv)
	$(VENV_PYTHON) -m pip install --upgrade pip
	@for req in $(PYTHON_REQUIREMENTS); do \
		echo "Installing $$req"; \
		$(VENV_PYTHON) -m pip install -r $$req || exit $$?; \
	done

bootstrap-frontend:
	$(call ensure_frontend)

bootstrap-dev: bootstrap-python bootstrap-frontend

dev-infra:
	cd infra && docker compose up -d postgres redis

down-infra:
	cd infra && docker compose stop postgres redis

logs-infra:
	cd infra && docker compose logs -f postgres redis

status-infra:
	cd infra && docker compose ps postgres redis

dev-stop-apps:
	@tmux kill-session -t cowater 2>/dev/null || true

dev-all-stop-tmux: dev-stop-apps

dev-stop: dev-stop-apps down-infra

# ─────────────────────────────────────────────────────
# 로컬 개발 - 각 서비스별 실행
# ─────────────────────────────────────────────────────
dev-core:
	$(call run_python_service,core,7700,fastapi uvicorn redis sqlalchemy asyncpg)

dev-control-agents:
	$(call run_python_service,control-agents,7701,fastapi uvicorn redis)

dev-detection-agents:
	$(call run_python_service,detection-agents,7704,fastapi uvicorn redis)

dev-analysis-agents:
	$(call run_python_service,analysis-agents,7705,fastapi uvicorn redis)

dev-response-agents:
	$(call run_python_service,response-agents,7706,fastapi uvicorn redis)

dev-learning-agents:
	$(call run_python_service,learning-agents,7708,fastapi uvicorn redis)

dev-supervision-agents:
	$(call run_python_service,supervision-agents,7707,fastapi uvicorn redis)

dev-report-agents:
	$(call run_python_service,report-agents,7709,fastapi uvicorn redis)

dev-moth-bridge:
	$(call run_python_script,moth-bridge,main.py,fastapi uvicorn redis websockets yaml)

dev-frontend:
	$(call ensure_frontend)
	cd services/frontend && npm run dev

dev-simulator:
	$(call run_python_script,simulator,main.py,redis pyais websockets yaml)

# ─────────────────────────────────────────────────────
# 로컬 전체 실행 (빠른 개발 환경)
# ─────────────────────────────────────────────────────
dev-all-tmux:
	@echo "🚀 시작: tmux로 모든 서비스 실행 (각각 새 윈도우)"
	@echo "  명령어: tmux kill-session -t cowater  (종료)"
	@command -v tmux >/dev/null 2>&1 || (echo "❌ tmux 필수: brew install tmux"; exit 1)
	@tmux kill-session -t cowater 2>/dev/null || true
	@tmux new-session -d -s cowater -x 200 -y 50
	@tmux new-window -t cowater -n moth "make dev-moth-bridge"
	@tmux new-window -t cowater -n core "make dev-core"
	@tmux new-window -t cowater -n control "make dev-control-agents"
	@tmux new-window -t cowater -n detection "make dev-detection-agents"
	@tmux new-window -t cowater -n analysis "make dev-analysis-agents"
	@tmux new-window -t cowater -n response "make dev-response-agents"
	@tmux new-window -t cowater -n report "make dev-report-agents"
	@tmux new-window -t cowater -n learning "make dev-learning-agents"
	@tmux new-window -t cowater -n supervision "make dev-supervision-agents"
	@tmux new-window -t cowater -n frontend "cd services/frontend && npm run dev"
	@tmux select-window -t cowater:0
	@echo ""
	@echo "✓ 세션 시작됨: tmux attach -t cowater"
	@echo "  창 이동: Ctrl+B → N (다음), P (이전), 0-9 (번호)"
	@echo ""
	@tmux attach -t cowater

dev-local: bootstrap-dev dev-infra
	@$(MAKE) dev-all-tmux

dev-local-sim: bootstrap-dev dev-infra
	@command -v tmux >/dev/null 2>&1 || (echo "❌ tmux 필수: brew install tmux"; exit 1)
	@tmux kill-session -t cowater 2>/dev/null || true
	@tmux new-session -d -s cowater -x 200 -y 50
	@tmux new-window -t cowater -n moth "make dev-moth-bridge"
	@tmux new-window -t cowater -n core "make dev-core"
	@tmux new-window -t cowater -n control "make dev-control-agents"
	@tmux new-window -t cowater -n detection "make dev-detection-agents"
	@tmux new-window -t cowater -n analysis "make dev-analysis-agents"
	@tmux new-window -t cowater -n response "make dev-response-agents"
	@tmux new-window -t cowater -n report "make dev-report-agents"
	@tmux new-window -t cowater -n learning "make dev-learning-agents"
	@tmux new-window -t cowater -n supervision "make dev-supervision-agents"
	@tmux new-window -t cowater -n simulator "SCENARIO=demo make dev-simulator"
	@tmux new-window -t cowater -n frontend "cd services/frontend && npm run dev"
	@tmux select-window -t cowater:0
	@tmux attach -t cowater

dev-all-manual:
	@echo "📋 모든 서비스 로컬 실행 (터미널 10개 필요)"
	@echo ""
	@echo "각 터미널에서 다음을 실행하세요:"
	@echo ""
	@echo "터미널 1: make dev-moth-bridge"
	@echo "터미널 2: make dev-core"
	@echo "터미널 3: make dev-control-agents"
	@echo "터미널 4: make dev-detection-agents"
	@echo "터미널 5: make dev-analysis-agents"
	@echo "터미널 6: make dev-response-agents"
	@echo "터미널 7: make dev-report-agents"
	@echo "터미널 8: make dev-learning-agents"
	@echo "터미널 9: make dev-supervision-agents"
	@echo "터미널 10: make dev-frontend"
	@echo ""
	@echo "또는 tmux 사용:"
	@echo "  make dev-local"

dev-all-quick:
	@echo "⚡ 빠른 개발: Core + Frontend만 (주요 기능)"
	@echo ""
	@echo "터미널 1: make dev-core"
	@echo "터미널 2: make dev-frontend"
	@echo ""
	@echo "또는 tmux:"
	@tmux kill-session -t cowater 2>/dev/null || true
	@tmux new-session -d -s cowater -x 200 -y 50
	@tmux new-window -t cowater -n core "make dev-core"
	@tmux new-window -t cowater -n frontend "cd services/frontend && npm run dev"
	@tmux select-window -t cowater:0
	@tmux attach -t cowater

# ─────────────────────────────────────────────────────
# 테스트
# ─────────────────────────────────────────────────────
test-e2e:
	cd services && python -m pytest ../tests/test_e2e_event_flow.py -v

test-unit:
	cd services && python -m pytest ../tests/test_event_system.py -v

test-all:
	cd services && python -m pytest ../tests/ -v

# ─────────────────────────────────────────────────────
# 개발 환경 설정
# ─────────────────────────────────────────────────────
setup:
	@echo "Setting up CoWater development environment..."
	pip install -r requirements-dev.txt 2>/dev/null || echo "requirements-dev.txt not found"
	cd services/frontend && npm install
	@echo "✓ Development environment ready"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleanup complete"

# ─────────────────────────────────────────────────────
# 기존 Ollama/vLLM 명령어들 (하위 호환성 유지)
# ─────────────────────────────────────────────────────
up-host-ollama:
	bash infra/run.sh host-ollama up

up-docker-ollama:
	bash infra/run.sh docker-ollama up

up-vllm:
	bash infra/run.sh vllm up

up-host-ollama-sim:
	cd infra && docker compose --env-file env/local-host-ollama.env --profile simulation up -d

up-docker-ollama-sim:
	cd infra && docker compose --env-file env/local-docker-ollama.env --profile ollama --profile simulation up -d

up-vllm-sim:
	cd infra && docker compose --env-file env/local-vllm.env --profile vllm --profile simulation up -d

rebuild-host-ollama-sim:
	cd infra && SCENARIO=${SCENARIO:-demo} docker compose --env-file env/local-host-ollama.env --profile simulation build && docker compose --env-file env/local-host-ollama.env --profile simulation up -d

rebuild-docker-ollama-sim:
	cd infra && SCENARIO=${SCENARIO:-demo} docker compose --env-file env/local-docker-ollama.env --profile ollama --profile simulation build && docker compose --env-file env/local-docker-ollama.env --profile ollama --profile simulation up -d

rebuild-vllm-sim:
	cd infra && SCENARIO=${SCENARIO:-demo} docker compose --env-file env/local-vllm.env --profile vllm --profile simulation build && docker compose --env-file env/local-vllm.env --profile vllm --profile simulation up -d

down-host-ollama:
	bash infra/run.sh host-ollama down

down-docker-ollama:
	bash infra/run.sh docker-ollama down

down-vllm:
	bash infra/run.sh vllm down

down-host-ollama-sim:
	cd infra && docker compose --env-file env/local-host-ollama.env --profile simulation down

down-docker-ollama-sim:
	cd infra && docker compose --env-file env/local-docker-ollama.env --profile ollama --profile simulation down

down-vllm-sim:
	cd infra && docker compose --env-file env/local-vllm.env --profile vllm --profile simulation down

downall-host-ollama:
	bash infra/run.sh host-ollama down-all

start-host-ollama:
	bash infra/run.sh host-ollama start-host-ollama

stop-host-ollama:
	bash infra/run.sh host-ollama stop-host-ollama

restart-host-ollama:
	bash infra/run.sh host-ollama stop-host-ollama && bash infra/run.sh host-ollama start-host-ollama

ps-host-ollama:
	bash infra/run.sh host-ollama ps

ps-docker-ollama:
	bash infra/run.sh docker-ollama ps

ps-vllm:
	bash infra/run.sh vllm ps

logs-host-ollama:
	bash infra/run.sh host-ollama logs

logs-docker-ollama:
	bash infra/run.sh docker-ollama logs

logs-vllm:
	bash infra/run.sh vllm logs

install-host-ollama-launchd:
	bash infra/install-host-ollama-launchd.sh

uninstall-host-ollama-launchd:
	bash infra/uninstall-host-ollama-launchd.sh

docker-doctor:
	bash infra/docker-doctor.sh

docker-cleanup-safe:
	bash infra/docker-cleanup-safe.sh
