.PHONY: up-host-ollama up-docker-ollama up-vllm up-host-ollama-sim up-docker-ollama-sim up-vllm-sim down-host-ollama down-docker-ollama down-vllm down-host-ollama-sim down-docker-ollama-sim down-vllm-sim downall-host-ollama stop-host-ollama ps-host-ollama ps-docker-ollama ps-vllm logs-host-ollama logs-docker-ollama logs-vllm install-host-ollama-launchd uninstall-host-ollama-launchd docker-doctor docker-cleanup-safe

up-host-ollama:
	bash infra/run.sh host-ollama up

up-docker-ollama:
	bash infra/run.sh docker-ollama up

up-vllm:
	bash infra/run.sh vllm up

# ─────────────────────────────────────────────────────
# 시뮬레이터 포함 실행 (SCENARIO 환경변수로 시나리오 선택)
# 예: make up-host-ollama-sim
#     SCENARIO=collision_risk make up-host-ollama-sim
# ─────────────────────────────────────────────────────
up-host-ollama-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh host-ollama up

up-docker-ollama-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh docker-ollama up

up-vllm-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh vllm up

down-host-ollama:
	bash infra/run.sh host-ollama down

down-docker-ollama:
	bash infra/run.sh docker-ollama down

down-vllm:
	bash infra/run.sh vllm down

down-host-ollama-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh host-ollama down

down-docker-ollama-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh docker-ollama down

down-vllm-sim:
	SCENARIO=${SCENARIO:-demo} bash infra/run.sh vllm down

downall-host-ollama:
	bash infra/run.sh host-ollama down-all

stop-host-ollama:
	bash infra/run.sh host-ollama stop-host-ollama

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
