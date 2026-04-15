# 분산 배포 가이드 (보안 강화)

## 📋 시나리오별 설정

### 시나리오 1: 같은 와이파이 (사무실)
```
MacBook1 (중앙)           MacBook2 (에이전트)        MacBook3 (에이전트)
├─ PostgreSQL:5432   ←──  redis://192.168.1.100  ── redis://192.168.1.100
├─ Redis:6379        ←──  postgresql://...      ── postgresql://...
└─ Core API:7700
```

**설정:**
```bash
# MacBook1 (중앙 서버)
cd infra
docker compose up -d

# MacBook2 (에이전트)
export REDIS_URL="redis://192.168.1.100:6379"
export CORE_API_URL="http://192.168.1.100:7700"
cd services/detection-agents
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

---

### 시나리오 2: 다른 와이파이 (원격 + 보안)
```
MacBook1 (중앙)           인터넷              MacBook2 (에이전트)
├─ PostgreSQL:5432   ◄───────────────────►  SSH Tunnel
├─ Redis:6379        ◄───────────────────►  포트 포워딩
└─ Core API:7700
```

**보안 설정:**

#### Step 1: 중앙 서버 - Redis 인증 활성화
```bash
# infra/docker-compose.yml 수정
redis:
  command: redis-server --requirepass CoWater_redis_123456 --save 60 1 --loglevel warning
```

#### Step 2: 중앙 서버 - PostgreSQL 비밀번호 변경
```bash
# infra/docker-compose.yml 수정
postgres:
  environment:
    POSTGRES_PASSWORD: CoWater_postgres_123456
```

#### Step 3: 에이전트 PC - SSH 터널 생성
```bash
# MacBook2에서
ssh -L 6379:localhost:6379 \
    -L 5432:localhost:5432 \
    -L 7700:localhost:7700 \
    user@central_server_ip

# 그 후 다른 터미널에서
export REDIS_URL="redis://:CoWater_redis_123456@localhost:6379"
export CORE_API_URL="http://localhost:7700"
export DATABASE_URL="postgresql+asyncpg://cowater:CoWater_postgres_123456@localhost:5432/cowater"

cd services/detection-agents
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

---

### 시나리오 3: 클라우드 배포 (향후)
```
AWS/Azure EC2 (중앙)      인터넷              MacBook (에이전트)
├─ PostgreSQL:5432   ◄───────────────────►  VPN 또는 보안 그룹
├─ Redis:6379        ◄───────────────────►
└─ Core API:7700
```

**보안 그룹 설정 (AWS):**
```
Port 5432:   Allow from <에이전트_IP>/32
Port 6379:   Allow from <에이전트_IP>/32
Port 7700:   Allow from <에이전트_IP>/32 또는 0.0.0.0/0 (API 접근)
```

---

## 🔐 보안 체크리스트

### 로컬 네트워크 (시나리오 1)
- [ ] 같은 와이파이 또는 LAN에 연결됨
- [ ] 방화벽에서 5432, 6379, 7700 포트 허용 (로컬만)

### 원격 (시나리오 2-3)
- [ ] Redis 인증 (`--requirepass`) 활성화
- [ ] PostgreSQL 강한 비밀번호 설정
- [ ] SSH 터널 또는 VPN 사용
- [ ] 방화벽/보안 그룹으로 허용된 IP만 접속
- [ ] SSL/TLS 인증서 (선택)

### 모든 환경
- [ ] 기본 비밀번호 변경 (`cowater_dev` → 강한 비밀번호)
- [ ] `.env` 파일 `.gitignore`에 추가
- [ ] 로그에 민감한 정보 노출 안 함
- [ ] 정기적 업데이트 및 보안 패치

---

## 🚀 빠른 시작 (로컬 테스트)

```bash
# MacBook1 - 중앙 서버
cd /Users/teamgrit/Documents/CoWater/infra
docker compose up -d

# MacBook2 - 에이전트 PC
cd /Users/teamgrit/Documents/CoWater
export REDIS_URL="redis://192.168.1.100:6379"
export CORE_API_URL="http://192.168.1.100:7700"

# detection-agents 실행
cd services/detection-agents
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704

# analysis-agents 실행 (다른 터미널)
cd services/analysis-agents
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7705
```

---

## 🔍 트러블슈팅

### Redis 연결 실패
```bash
# Redis 상태 확인
docker exec cowater-redis redis-cli ping
# 또는
redis-cli -h 192.168.1.100 ping
```

### PostgreSQL 연결 실패
```bash
# PostgreSQL 상태 확인
docker exec cowater-postgres pg_isready -U cowater
# 또는
psql -h 192.168.1.100 -U cowater -d cowater
```

### 에이전트 로그 확인
```bash
# detection-agents 로그
docker logs cowater-detection-agents -f
```

---

## 🌐 인터넷 노출 체크리스트

#### 중앙 서버 (EC2/VPS)
- [ ] 보안 그룹에서 필요한 IP만 허용
- [ ] SSH 키페어 설정 (비밀번호 로그인 비활성화)
- [ ] Fail2ban 또는 Rate Limiting 설정
- [ ] 자동 백업 활성화

#### 에이전트 PC
- [ ] VPN 또는 SSH 터널로만 연결
- [ ] 로컬 방화벽 설정
- [ ] 주기적 보안 업데이트

#### 데이터
- [ ] TLS 암호화 전송 (선택)
- [ ] 정기적 데이터베이스 백업
- [ ] 접근 로그 모니터링
