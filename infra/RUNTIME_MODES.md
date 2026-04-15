# Runtime Modes

CoWater now treats **network endpoints via env** as the deployment boundary. Each service can stay in Docker Compose locally, then later move to a different server by changing env values instead of rewriting code.

## Local modes (simple presets)

### 1. Host Ollama (recommended on macOS)
- Agents/Core/Frontend/etc run in Docker.
- Ollama runs on the macOS host.
- Agents connect to `http://host.docker.internal:11434`.

Run:

```bash
make up-host-ollama
```

This mode auto-starts `ollama serve` if it is not already running.

### 2. Docker Ollama
- Ollama runs as the `cowater-ollama` container.
- Agents connect to `http://ollama:11434`.

Run:

```bash
make up-docker-ollama
```

### 3. vLLM
- vLLM runs as a dedicated container.
- Agents use `LLM_BACKEND=vllm`.

Run:

```bash
make up-vllm
```

## Advanced service-set usage

`infra/run.sh` also supports **service-set presets** so the same entrypoint can be used later for split-server deployment.

Usage:

```bash
bash infra/run.sh <mode> <action> <preset>
```

Modes:
- `host-ollama`
- `docker-ollama`
- `vllm`

Actions:
- `up`
- `down`
- `down-all`
- `restart`
- `ps`
- `logs`

Presets:
- `full` — full local stack for that mode
- `data-node` — `postgres`, `redis`
- `core-node` — `core`
- `agents-node` — `agents` (+ mode-specific LLM service if needed)
- `frontend-node` — `frontend`
- `bridge-node` — `moth-bridge`
- `llm-node` — mode-specific LLM service only

Examples:

```bash
# Local full stack with host Ollama
bash infra/run.sh host-ollama up full

# Agents-only node using Docker Ollama on the same machine
COWATER_ENV_FILE=infra/env/agents-node-docker-ollama.env.example bash infra/run.sh docker-ollama up agents-node

# Core-only node with external Redis/Postgres/Agents
COWATER_ENV_FILE=infra/env/core-node.env.example bash infra/run.sh host-ollama up core-node
```

When a node preset is used, the script starts only that service set and skips Compose dependency auto-start for `up`, assuming external URLs/DSNs are provided in the env file.

## Main files

- `infra/docker-compose.yml` — local orchestrator, but all important service endpoints are env-driven.
- `infra/env/local-host-ollama.env`
- `infra/env/local-docker-ollama.env`
- `infra/env/local-vllm.env`
- `infra/env/*.example` — split-node templates (`core-node`, `agents-node-*`, `frontend-node`, `bridge-node`)
- `infra/env/remote-services.env.example` — example for split-server deployment.
- `infra/env/swarm-stack.env.example` — shared naming/env template for Swarm or multi-node rollout.
- `infra/run.sh` — single entrypoint that chooses env + compose profiles.

## Host Ollama as a macOS service

If you want host Ollama to behave like a real background service instead of a best-effort auto-start from `run.sh`, install the provided launchd agent.

```bash
make install-host-ollama-launchd
```

This registers `com.cowater.ollama` under `~/Library/LaunchAgents`, starts it immediately, and keeps it running across login sessions.

Useful commands:

```bash
make uninstall-host-ollama-launchd
make stop-host-ollama
make docker-doctor
make docker-cleanup-safe
```

Notes:
- The installer rewrites the plist to your actual `ollama` binary path.
- Logs go to `/tmp/cowater-host-ollama.log`.
- This is most useful when `host-ollama` is your default local mode on macOS.

## Split-server / Swarm-friendly boundary

Keep these as the stable contract:

- `DATABASE_URL`
- `REDIS_URL`
- `CORE_API_URL`
- `AGENTS_API_URL`
- `MOTH_SERVER_URL`
- `LLM_BACKEND`
- `OLLAMA_URL` / `VLLM_URL`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_WS_URL`
- `NEXT_PUBLIC_AGENTS_URL`
- `NEXT_PUBLIC_POSITION_WS_URL`

### Important rule

- Service-to-service URLs may use Docker DNS or private addresses.
- Browser-facing `NEXT_PUBLIC_*` URLs must always be reachable from the user's browser.

That lets you move `core`, `agents`, `moth-bridge`, or the LLM server to other machines later without changing app logic.

## Clean shutdown

```bash
# stop only the selected compose services / preset
bash infra/run.sh host-ollama down agents-node

# stop the whole stack and host Ollama too
bash infra/run.sh host-ollama down-all full

# stop only host Ollama
bash infra/run.sh host-ollama stop-host-ollama
```

## Notes

- On macOS, host Ollama is usually the fastest/easiest path because Metal acceleration works outside Docker.
- On Linux + NVIDIA, Docker Ollama or vLLM are more realistic production GPU options.
- `OLLAMA_FLASH_ATTENTION=1` is already configured for the Docker Ollama container, but whether it helps depends on the underlying runtime/hardware path.
- `make docker-cleanup-safe` only prunes build cache and dangling images; it deliberately does **not** prune volumes.

## Swarm / multi-server naming guidance

Keep service names stable by role, not by machine:

- `core`
- `agents`
- `bridge`
- `frontend`
- `postgres`
- `redis`
- `llm`

Then bind each node by env, not code:

- app node → `CORE_API_URL`, browser-facing `NEXT_PUBLIC_*`
- agents node → `CORE_API_URL`, `REDIS_URL`, `OLLAMA_URL` or `VLLM_URL`
- llm node → only model-serving concerns
- data node → `DATABASE_URL`, `REDIS_URL`

This makes it easy to move from local Compose to Swarm stacks while preserving the same endpoint contract.
