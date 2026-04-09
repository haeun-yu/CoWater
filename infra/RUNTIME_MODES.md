# Runtime Modes

CoWater now treats **network endpoints via env** as the deployment boundary. Each service can stay in Docker Compose locally, then later move to a different server by changing env values instead of rewriting code.

## Local modes

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

## Main files

- `infra/docker-compose.yml` — local orchestrator, but all important service endpoints are env-driven.
- `infra/env/local-host-ollama.env`
- `infra/env/local-docker-ollama.env`
- `infra/env/local-vllm.env`
- `infra/env/remote-services.env.example` — example for split-server deployment.
- `infra/run.sh` — single entrypoint that chooses env + compose profiles.

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

## Notes

- On macOS, host Ollama is usually the fastest/easiest path because Metal acceleration works outside Docker.
- On Linux + NVIDIA, Docker Ollama or vLLM are more realistic production GPU options.
- `OLLAMA_FLASH_ATTENTION=1` is already configured for the Docker Ollama container, but whether it helps depends on the underlying runtime/hardware path.
