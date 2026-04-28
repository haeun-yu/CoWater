# 🚀 CoWater POC 배포 및 운영 가이드

**최종 구현 상태**: 모든 배포 시나리오 지원 ✅  
**작성일**: 2026-04-28

---

## 📋 목차

1. [빠른 시작 (3분)](#빠른-시작-3분)
2. [배포 시나리오](#배포-시나리오)
3. [시뮬레이터 실행](#시뮬레이터-실행)
4. [분산 배포 (멀티 호스트)](#분산-배포-멀티-호스트)
5. [보안 설정](#보안-설정)
6. [트러블슈팅](#트러블슈팅)
7. [FAQ](#faq)

---

## 빠른 시작 (3분)

### 로컬 개발 환경 (단일 호스트)

```bash
cd infra

# ⚠️ 필수: 호스트 시스템에서 LLM 서버 실행
# Mac: ollama serve (또는 Ollama 앱 실행) → 호스트 11434 포트
# Linux: ollama serve → 호스트 11434 포트

# 기본 실행
docker compose up -d

# 모든 서비스 상태 확인
docker compose ps

# 특정 서비스 로그 보기
docker compose logs -f core
```

### POC 시스템 (POC 01-06)

```bash
cd pocs

# Device Registration Server 시작 (포트 8280)
cd pocs/00-device-registration-server
python -m src.device_registration_server --port 8286

# 다른 터미널에서: Lower Agents 시작
cd pocs/01-usv-lower-agent && python -m src.main --port 9010
cd pocs/02-auv-lower-agent && python -m src.main --port 9011
cd pocs/03-rov-lower-agent && python -m src.main --port 9012

# Middle Layer 시작
cd pocs/04-usv-middle-agent && python -m src.main --port 9013
cd pocs/05-control-ship-middle-agent && python -m src.main --port 9014

# Supervisor 시작
cd pocs/06-system-supervisor-agent && python -m src.main --port 9015
```

---

## 배포 시나리오

### 시나리오 1: 단일 호스트 (개발/테스트)

**특징**: 모든 서비스가 하나의 컴퓨터에서 실행

```bash
cd infra
docker compose up -d

# 확인
docker compose ps
# STATUS: healthy
```

**접근 가능한 포트**:
- Core API: http://localhost:7700
- Frontend: http://localhost:7702
- Agent Gateway: http://localhost:7701-7709
- Moth Bridge: http://localhost:7703

**네트워크**: localhost만 접근 가능

---

### 시나리오 2: 분산 배포 (로컬 네트워크)

**특징**: 여러 PC가 같은 와이파이/LAN에 연결된 환경

#### PC1 (중앙 서버): Database + Redis + Core

```bash
cd infra

# .env.local 생성 (강한 비밀번호 자동 생성)
cat > .env.local <<EOF
POSTGRES_BIND_ADDR=0.0.0.0
REDIS_BIND_ADDR=0.0.0.0
CORE_BIND_ADDR=0.0.0.0
POSTGRES_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
EOF

# 시작
docker compose --env-file .env.local up -d postgres redis core moth-bridge agent-gateway
```

#### PC2 (워커 A): Detection + Analysis Agents

```bash
# PC1의 IP 확인: 192.168.1.100이라고 가정

cat > .env.local <<EOF
DATABASE_URL=postgresql+asyncpg://cowater:PASSWORD@192.168.1.100:5432/cowater
REDIS_URL=redis://:PASSWORD@192.168.1.100:6379
CORE_API_URL=http://192.168.1.100:7700
EOF

cd infra
docker compose --env-file .env.local up -d detection-agents analysis-agents
```

#### PC3 (워커 B): Response + Report Agents

```bash
cat > .env.local <<EOF
DATABASE_URL=postgresql+asyncpg://cowater:PASSWORD@192.168.1.100:5432/cowater
REDIS_URL=redis://:PASSWORD@192.168.1.100:6379
CORE_API_URL=http://192.168.1.100:7700
EOF

cd infra
docker compose --env-file .env.local up -d response-agents report-agents
```

#### 접근

- 웹 브라우저: http://192.168.1.100:7702
- Agent Gateway: http://192.168.1.100:7701-7709

---

### 시나리오 3: 원격 접근 (SSH 터널 - 권장)

**특징**: 원격 PC에서 안전하게 중앙 서버에 접속

#### PC1 (중앙 서버): 모든 서비스 실행

```bash
bash setup-distributed.sh remote-tunnel
docker compose --env-file .env up -d
```

#### PC2 (원격 워커): SSH 터널로 연결

```bash
# Terminal 1: SSH 터널 생성 (계속 실행 유지)
ssh -L 6379:localhost:6379 \
    -L 5432:localhost:5432 \
    -L 7700:localhost:7700 \
    user@192.168.1.100

# Terminal 2: 환경변수 설정
export REDIS_URL="redis://:PASSWORD@localhost:6379"
export CORE_API_URL="http://localhost:7700"
export DATABASE_URL="postgresql+asyncpg://cowater:PASSWORD@localhost:5432/cowater"

# 에이전트 실행
cd services/detection-agents
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

**보안 수준**: ⭐⭐⭐ 높음 (SSH 암호화)

---

### 시나리오 4: 클라우드 배포 (AWS/Azure)

**특징**: AWS EC2 또는 Azure VM에서 실행

#### EC2 인스턴스 생성

```bash
# AWS 보안 그룹 설정 (필수)
# - SSH (22): 내 IP만 허용
# - PostgreSQL (5432): 에이전트 IP만 허용
# - Redis (6379): 에이전트 IP만 허용
# - Core API (7700): 에이전트 IP만 허용
# - Web (7702): 모든 곳 허용 (또는 특정 IP)
```

#### EC2에서 실행

```bash
bash setup-distributed.sh cloud
docker compose --env-file .env up -d

# EC2의 public IP 확인: ec2-1-2-3-4.amazonaws.com
```

#### 원격 PC에서 접속

```bash
# SSH 터널 (권장)
ssh -L 6379:localhost:6379 \
    -L 5432:localhost:5432 \
    -L 7700:localhost:7700 \
    ec2-user@ec2-1-2-3-4.amazonaws.com

# 또는 직접 연결 (보안 그룹에서 IP 허용 필요)
export REDIS_URL="redis://:PASSWORD@ec2-1-2-3-4.amazonaws.com:6379"
export CORE_API_URL="http://ec2-1-2-3-4.amazonaws.com:7700"
```

**보안 수준**: ⭐⭐⭐ 높음 (보안 그룹 + 강한 비밀번호)

---

## 시뮬레이터 실행

### 기본 시뮬레이터 (Demo 시나리오, 3배속)

```bash
cd infra

# 시뮬레이터 포함 실행
SCENARIO=demo docker compose --profile simulation up -d

# 실시간 로그 보기
docker compose logs -f simulator
```

### 시나리오별 실행

#### 1. Demo (기본)
```bash
SCENARIO=demo docker compose --profile simulation up -d
# 일반적인 선박 움직임 시뮬레이션
```

#### 2. 충돌 위험 (Collision Risk)
```bash
SCENARIO=collision_risk docker compose --profile simulation up -d
# 두 선박이 충돌 경로로 접근하는 시나리오
```

#### 3. 조난 신호 (Distress Response)
```bash
SCENARIO=distress_response docker compose --profile simulation up -d
# 선박의 조난 신호와 구조 요청
```

#### 4. 구역 침입 (Zone Intrusion)
```bash
SCENARIO=zone_intrusion docker compose --profile simulation up -d
# 금지 구역으로의 불법 진입
```

### 호스트 Ollama 사용

호스트 시스템에서 Ollama 실행:

```bash
# Mac
ollama serve

# 또는 Ollama 앱 시작

# Linux
ollama serve
```

Docker 컨테이너는 자동으로 호스트 Ollama (11434 포트)에 연결됩니다.

### 시뮬레이터 중지

```bash
docker compose --profile simulation down
# 또는
docker compose down
```

---

## 분산 배포 (멀티 호스트)

### 아키텍처 개요

```
┌─────────────────────────────────────────┐
│ PC1 (Central Server)                    │
│ - PostgreSQL (5432)                     │
│ - Redis (6379)                          │
│ - Core API (7700)                       │
│ - Agent Gateway (7701-7709)             │
│ - Frontend (7702)                       │
└─────────────────────────────────────────┘
           ↓ (환경변수로 연결)
    ┌──────┴──────────┐
    ↓                 ↓
PC2 (Workers)    PC3 (Workers)
- Detection      - Response
- Analysis       - Report
- Supervision    - Learning
```

### 환경변수 설정

**PC1 (중앙 서버) - infra/.env**:

```bash
# 데이터 바인딩
POSTGRES_BIND_ADDR=0.0.0.0      # 모든 IP에서 접근 가능
REDIS_BIND_ADDR=0.0.0.0
CORE_BIND_ADDR=0.0.0.0

# Agent Gateway upstream (PC2, PC3의 IP)
DETECTION_AGENTS_UPSTREAM=http://192.168.1.101:7704
ANALYSIS_AGENTS_UPSTREAM=http://192.168.1.101:7705
RESPONSE_AGENTS_UPSTREAM=http://192.168.1.102:7706
REPORT_AGENTS_UPSTREAM=http://192.168.1.102:7709
SUPERVISION_AGENTS_UPSTREAM=http://192.168.1.102:7707
LEARNING_AGENTS_UPSTREAM=http://192.168.1.102:7708
```

**PC2 (워커) - .env.local**:

```bash
DATABASE_URL=postgresql+asyncpg://cowater:PASSWORD@192.168.1.100:5432/cowater
REDIS_URL=redis://:PASSWORD@192.168.1.100:6379
CORE_API_URL=http://192.168.1.100:7700
```

### 유연한 배포

**원칙**: 서비스 개수와 위치는 환경변수로 **동적 결정**

```bash
# 3대 호스트
호스트 A: postgres, redis, core, frontend
호스트 B: detection-agents, analysis-agents
호스트 C: response-agents, report-agents, supervision-agents, learning-agents

# 5대 호스트
호스트 A: postgres, redis, core
호스트 B: detection-agents, analysis-agents
호스트 C: response-agents, report-agents
호스트 D: supervision-agents, learning-agents
호스트 E: frontend

# 모두 다른 호스트에
호스트 A: postgres, redis
호스트 B: core, frontend
호스트 C: detection-agents
호스트 D: analysis-agents
호스트 E: response-agents
호스트 F: report-agents
호스트 G: supervision-agents, learning-agents

# 환경변수로 각 위치 지정 → 자유로운 구성 가능
```

---

## 보안 설정

### 모든 환경 필수 체크리스트

- [ ] `.env` 파일 생성 (강한 비밀번호 사용)
- [ ] `.env` 파일을 `.gitignore`에 추가
  ```bash
  echo ".env" >> .gitignore
  echo ".env.local" >> .gitignore
  ```
- [ ] 비밀번호를 안전한 곳에 저장 (1Password, Notion 등)

### 로컬 네트워크 (같은 와이파이/LAN)

- [ ] 같은 네트워크 확인
- [ ] 방화벽 설정 (필요시)
- [ ] 신뢰할 수 있는 네트워크만 사용

### 원격 접근

- [ ] **SSH 터널 사용 (권장)**: 암호화된 연결
  ```bash
  ssh -L 6379:localhost:6379 user@remote_ip
  ```
- [ ] 또는 **VPN 사용**: 기업 VPN 네트워크 활용
- [ ] PostgreSQL/Redis는 **localhost만 바인드** (기본값)
  ```bash
  POSTGRES_BIND_ADDR=127.0.0.1
  REDIS_BIND_ADDR=127.0.0.1
  ```

### 클라우드 배포 (AWS/Azure)

- [ ] **보안 그룹**: 필요한 IP만 허용
  - SSH (22): 내 IP만
  - PostgreSQL (5432): 에이전트 IP만
  - Redis (6379): 에이전트 IP만
  - Core API (7700): 에이전트 IP만
  - Frontend (7702): 모든 곳 (또는 특정 IP)
- [ ] **SSH 키페어**: 비밀번호 로그인 비활성화
- [ ] **강한 비밀번호**: 32자 이상 무작위
  ```bash
  openssl rand -base64 32
  ```
- [ ] **모니터링**: CloudWatch/Azure Monitor 활성화
- [ ] **백업**: 자동 백업 활성화

### 네트워크 격리 확인

```bash
# 중앙 서버에서
docker exec cowater-redis redis-cli -a PASSWORD ping
# 응답: PONG

# 에이전트 PC에서
redis-cli -h 192.168.1.100 -a PASSWORD ping
# 응답: PONG (네트워크 접근 확인)

# 접근 불가능한 IP에서
redis-cli -h 192.168.1.100 -a PASSWORD ping
# 응답: Error (정상 - 격리됨)
```

---

## 트러블슈팅

### Redis 연결 실패

**증상**: `Error: Could not connect to Redis`

```bash
# 1. Redis 상태 확인 (중앙 서버)
docker exec cowater-redis redis-cli -a ${REDIS_PASSWORD} ping
# 응답: PONG (정상)

# 2. 방화벽 확인 (에이전트 PC)
nc -zv 192.168.1.100 6379
# 응답: Connection successful (정상)

# 3. 비밀번호 확인
# .env의 REDIS_PASSWORD와 일치하는지 확인

# 4. 바인드 주소 확인 (중앙 서버)
# REDIS_BIND_ADDR=0.0.0.0이어야 외부 접근 가능
```

### PostgreSQL 연결 실패

**증상**: `could not connect to server: Connection refused`

```bash
# 1. PostgreSQL 상태 확인 (중앙 서버)
docker exec cowater-postgres pg_isready -U cowater
# 응답: accepting connections (정상)

# 2. 포트 확인 (에이전트 PC)
nc -zv 192.168.1.100 5432
# 응답: Connection successful (정상)

# 3. 자격증명 확인
psql -h 192.168.1.100 -U cowater -d cowater
# 비밀번호: .env의 POSTGRES_PASSWORD

# 4. 바인드 주소 확인
# POSTGRES_BIND_ADDR=0.0.0.0이어야 외부 접근 가능
```

### Core API 접근 불가

**증상**: `Failed to fetch http://192.168.1.100:7700`

```bash
# 1. Core 서비스 상태 (중앙 서버)
docker compose ps core
# STATUS: healthy

# 2. 포트 확인 (에이전트 PC)
nc -zv 192.168.1.100 7700
# 응답: Connection successful (정상)

# 3. 방화벽 확인
# 포트 7700이 열려있는지 확인

# 4. Core 로그 확인
docker logs cowater-core -f
```

### 에이전트 연결 불가

**증상**: Agent Gateway가 에이전트를 찾을 수 없음

```bash
# 1. Upstream 설정 확인 (중앙 서버)
# infra/.env의 *_AGENTS_UPSTREAM이 정확한지 확인
cat infra/.env | grep AGENTS_UPSTREAM

# 2. 에이전트 상태 확인 (워커 PC)
docker compose ps detection-agents
# STATUS: healthy

# 3. 에이전트 포트 확인
nc -zv 192.168.1.101 8001
# 응답: Connection successful (정상)

# 4. Agent Gateway 로그
docker logs cowater-agent-gateway -f
```

### 시뮬레이터 데이터 없음

**증상**: Moth Server에서 데이터 수신 안 됨

```bash
# 1. 시뮬레이터 상태 확인
docker compose ps simulator
# STATUS: running

# 2. 시뮬레이터 로그 확인
docker compose logs -f simulator

# 3. Moth Server 연결 확인
# MOTH_SERVER_URL=wss://cobot.center:8287이 정확한지 확인

# 4. 네트워크 확인
curl -I wss://cobot.center:8287
```

### 포트 충돌

**증상**: `Address already in use`

```bash
# 1. 포트 사용 프로세스 확인 (Mac/Linux)
lsof -i :7700
# 또는
netstat -tlnp | grep 7700

# 2. 사용 중인 프로세스 종료
kill -9 <PID>

# 3. Docker 컨테이너 충돌 (여러 compose 실행)
docker compose ps
docker compose down  # 정리
```

### SSH 터널 연결 문제

**증상**: `ssh: connect to host... Connection refused`

```bash
# 1. SSH 서버 확인
ssh -v user@192.168.1.100 "echo ok"

# 2. 터널 포트 확인 (로컬에서 이미 사용 중)
lsof -i :6379
# 다른 로컬 포트로 터널 생성
ssh -L 16379:localhost:6379 user@192.168.1.100

# 3. 터널로 접근
redis-cli -h localhost -p 16379 -a PASSWORD ping
```

---

## FAQ

**Q: 같은 와이파이에서도 SSH 터널이 필요한가?**

A: 아니오. 같은 로컬 네트워크면 직접 연결 가능합니다. 하지만 보안을 위해 SSH 터널 사용을 권장합니다.

---

**Q: 클라우드에서 호스팅하려면?**

A: AWS EC2 또는 Azure VM에 docker compose를 실행하고, 보안 그룹에서 IP를 제한하세요. SSH 터널로 안전하게 접속 가능합니다.

---

**Q: 비밀번호를 잊어버렸다면?**

A: `.env` 파일을 다시 생성하고 docker compose를 재시작하면 됩니다:

```bash
bash setup-distributed.sh remote-tunnel
docker compose down
docker compose --env-file .env up -d
```

---

**Q: HTTPS(SSL)를 사용하려면?**

A: 현재는 SSH 터널로 암호화합니다. 추후 nginx reverse proxy에 SSL 설정 가능합니다.

---

**Q: 여러 환경에서 동시 실행 가능한가?**

A: 예. 환경별로 다른 `.env` 파일 사용:

```bash
# 개발
docker compose --env-file .env.dev up -d

# 운영
docker compose --env-file .env.prod up -d

# 테스트
docker compose --env-file .env.test up -d
```

---

**Q: 데이터베이스 마이그레이션은?**

A: docker compose up 시 자동으로 수행됩니다. 수동 마이그레이션:

```bash
docker exec cowater-core alembic upgrade head
```

---

**Q: Redis 데이터 영속성은?**

A: docker-compose.yml에서 Redis volume 설정되어 있습니다:

```yaml
redis:
  volumes:
    - redis_data:/data
```

데이터는 컨테이너 재시작 후에도 보존됩니다.

---

**Q: POC 시스템과 메인 서비스는 독립적인가?**

A: 예. POC 시스템(POC 01-06)은 별도의 포트(8286, 9010-9015)에서 실행되며, 메인 CoWater 서비스(7700-7709)와는 독립적입니다.

---

**마지막 업데이트**: 2026-04-28  
**포함 내용**: 로컬 개발, 분산 배포, 클라우드, 보안, 시뮬레이터, 트러블슈팅
