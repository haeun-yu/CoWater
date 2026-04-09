.PHONY: up-host-ollama up-docker-ollama up-vllm down-host-ollama down-docker-ollama down-vllm downall-host-ollama stop-host-ollama ps-host-ollama ps-docker-ollama ps-vllm logs-host-ollama logs-docker-ollama logs-vllm

up-host-ollama:
	bash infra/run.sh host-ollama up

up-docker-ollama:
	bash infra/run.sh docker-ollama up

up-vllm:
	bash infra/run.sh vllm up

down-host-ollama:
	bash infra/run.sh host-ollama down

down-docker-ollama:
	bash infra/run.sh docker-ollama down

down-vllm:
	bash infra/run.sh vllm down

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
