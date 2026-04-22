# CoWater Simulation + Host Ollama Runbook

이 문서는 로컬에서 `host Ollama + 전체 CoWater 시스템 + 시뮬레이터`를 실행하고 완전히 종료하기 위한 개인용 메모입니다.

## 현재 지원 시나리오

시뮬레이터 시나리오는 `services/simulator/scenarios/` 아래 YAML 파일로 선택합니다.

```bash
default
demo
collision_risk
distress_response
zone_intrusion
```

현재 `demo` 시나리오는 화물선, 여객선, 어선, 탱커, 벌크선, 해경 순시선 중심입니다. README에는 USV, ROV, AUV, 드론, 부이 같은 플랫폼을 지원한다고 되어 있지만, 현재 시뮬레이터 등록 로직은 기본적으로 `platform_type: vessel`로 등록합니다.

따라서 USV/ASV 전용 시뮬레이션을 실제 타입까지 반영하려면 별도 시나리오 YAML과 `services/simulator/scenario_runner.py`의 `platform_type` 처리 수정이 필요합니다. ASV는 일반적으로 무인수상정 계열이라 이 시스템에서는 `usv` 타입으로 다루면 됩니다.

## 실행 명령어

아래 명령어는 repo 루트가 `/Users/teamgrit/Downloads/CoWater`라는 전제입니다.

### 1. Host Ollama를 launchd로 실행

이 방식은 macOS LaunchAgent로 Ollama를 띄우기 때문에 터미널 세션이 끝나도 유지됩니다.

```bash
cd /Users/teamgrit/Downloads/CoWater
bash infra/install-host-ollama-launchd.sh
```

Ollama 확인:

```bash
curl http://127.0.0.1:11434/api/tags
```

### 2. 전체 시스템 + 시뮬레이터 실행

기본 데모 시나리오:

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
SCENARIO=demo docker compose --env-file env/local-host-ollama.env --profile simulation up -d
```

다른 시나리오 실행:

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
SCENARIO=collision_risk docker compose --env-file env/local-host-ollama.env --profile simulation up -d
```

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
SCENARIO=distress_response docker compose --env-file env/local-host-ollama.env --profile simulation up -d
```

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
SCENARIO=zone_intrusion docker compose --env-file env/local-host-ollama.env --profile simulation up -d
```

## 상태 확인

Docker 서비스 상태:

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
docker compose --env-file env/local-host-ollama.env --profile simulation ps
```

Core API health:

```bash
curl http://127.0.0.1:7700/health
```

Frontend:

```text
http://localhost:7702
```

시뮬레이터 로그:

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
docker compose --env-file env/local-host-ollama.env --profile simulation logs -f simulator
```

Ollama 상태:

```bash
curl http://127.0.0.1:11434/api/tags
```

## 완전 종료 명령어

### 1. Docker 시스템 + 시뮬레이터 종료

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
docker compose --env-file env/local-host-ollama.env --profile simulation down
```

### 2. Host Ollama LaunchAgent 종료 및 제거

```bash
cd /Users/teamgrit/Downloads/CoWater
bash infra/uninstall-host-ollama-launchd.sh
```

### 3. 종료 확인

Docker 컨테이너가 없어야 합니다.

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
docker compose --env-file env/local-host-ollama.env --profile simulation ps
```

Ollama가 꺼져 있으면 아래 명령어는 연결 실패가 나야 정상입니다.

```bash
curl http://127.0.0.1:11434/api/tags
```

## 세션용 Ollama 실행 방식

LaunchAgent를 쓰지 않고 현재 세션에서만 host Ollama를 띄우려면 아래 명령어를 사용할 수 있습니다.

실행:

```bash
cd /Users/teamgrit/Downloads/CoWater
bash infra/run.sh host-ollama start-host-ollama

cd infra
SCENARIO=demo docker compose --env-file env/local-host-ollama.env --profile simulation up -d
```

종료:

```bash
cd /Users/teamgrit/Downloads/CoWater/infra
docker compose --env-file env/local-host-ollama.env --profile simulation down

cd ..
bash infra/run.sh host-ollama stop-host-ollama
```

## 참고

현재 `infra/docker-compose.yml`에서는 `agent-gateway`가 `7701`, `7704-7709` 포트를 외부에 노출합니다. 개별 agent 컨테이너가 같은 포트를 직접 노출하면 포트 충돌이 납니다.

TimescaleDB 이미지 태그 `timescale/timescaledb-ha:pg15.13-ts2.17.2-all`이 로컬에 없거나 registry에서 해석되지 않으면 실행이 실패할 수 있습니다. 이 경우 로컬에 있는 `timescale/timescaledb-ha:pg15-latest`를 같은 태그로 붙여 임시 복구할 수 있습니다.

```bash
docker tag timescale/timescaledb-ha:pg15-latest timescale/timescaledb-ha:pg15.13-ts2.17.2-all
```
