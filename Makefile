.PHONY: up-host-ollama up-docker-ollama up-vllm up-host-ollama-sim up-docker-ollama-sim up-vllm-sim rebuild-host-ollama-sim rebuild-docker-ollama-sim rebuild-vllm-sim down-host-ollama down-docker-ollama down-vllm down-host-ollama-sim down-docker-ollama-sim down-vllm-sim downall-host-ollama start-host-ollama stop-host-ollama restart-host-ollama ps-host-ollama ps-docker-ollama ps-vllm logs-host-ollama logs-docker-ollama logs-vllm install-host-ollama-launchd uninstall-host-ollama-launchd docker-doctor docker-cleanup-safe

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
	cd infra && docker compose --env-file env/local-host-ollama.env --profile simulation up -d

up-docker-ollama-sim:
	cd infra && docker compose --env-file env/local-docker-ollama.env --profile ollama --profile simulation up -d

up-vllm-sim:
	cd infra && docker compose --env-file env/local-vllm.env --profile vllm --profile simulation up -d

# 시뮬레이션 포함 + 재빌드
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
