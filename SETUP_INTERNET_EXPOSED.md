# 🌐 인터넷 노출 배포 가이드

인터넷에 노출되는 환경에서 CoWater를 안전하게 배포하는 방법입니다.

---

## 📋 빠른 시작 (3단계)

### Step 1: 중앙 서버 설정 생성

현재 디렉토리에서:
```bash
cd infra
bash setup-distributed.sh remote-tunnel
```

**출력 예시:**
```
✓ .env 파일 생성됨 (강한 비밀번호 적용)

PostgreSQL 비밀번호: AbCdEfGhIjKlMnOpQrStUvWxYz123456
Redis 비밀번호: XyZaBcDeFgHiJkLmNoPqRsTuVwXyZ789
```

### Step 2: Docker 컨테이너 시작

```bash
cd /Users/teamgrit/Documents/CoWater/infra
docker compose --env-file .env up -d

# 상태 확인
docker compose ps
```

**확인 사항:**
```bash
✓ postgres   (healthy)
✓ redis      (healthy)
✓ core       (started)
✓ moth-bridge (started)
```

### Step 3: 에이전트 PC 연결

**중앙 서버 IP 확인:**
```bash
# Mac
ipconfig getifaddr en0
# 예: 192.168.1.100
```

**에이전트 PC (MacBook2)에서:**

#### 방법 A: SSH 터널 (권장 - 안전)
```bash
# Terminal 1: SSH 터널 생성 (계속 실행 유지)
ssh -L 6379:localhost:6379 \
    -L 5432:localhost:5432 \
    -L 7700:localhost:7700 \
    user@192.168.1.100

# 터널이 열리면 다른 터미널로 이동

# Terminal 2: 환경변수 설정
export REDIS_URL="redis://:AbCdEfGhIjKlMnOpQrStUvWxYz123456@localhost:6379"
export CORE_API_URL="http://localhost:7700"
export DATABASE_URL="postgresql+asyncpg://cowater:AbCdEfGhIjKlMnOpQrStUvWxYz123456@localhost:5432/cowater"

# 에이전트 실행
cd ~/CoWater/services/detection-agents
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

#### 방법 B: 직접 연결 (같은 와이파이)
```bash
# 환경변수 설정
export REDIS_URL="redis://:AbCdEfGhIjKlMnOpQrStUvWxYz123456@192.168.1.100:6379"
export CORE_API_URL="http://192.168.1.100:7700"
export DATABASE_URL="postgresql+asyncpg://cowater:AbCdEfGhIjKlMnOpQrStUvWxYz123456@192.168.1.100:5432/cowater"

# 에이전트 실행
cd ~/CoWater/services/detection-agents
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

---

## 🔐 3가지 배포 시나리오

### 시나리오 1: 로컬 테스트 (같은 네트워크)

```bash
# 중앙 서버
bash setup-distributed.sh local
docker compose --env-file .env up -d

# 에이전트 PC (같은 와이파이)
export REDIS_URL="redis://192.168.1.100:6379"
export CORE_API_URL="http://192.168.1.100:7700"
cd services/detection-agents
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

**보안 수준:** ⭐ 낮음 (로컬 네트워크만 신뢰)

---

### 시나리오 2: 원격 접근 (권장)

```bash
# 중앙 서버
bash setup-distributed.sh remote-tunnel
docker compose --env-file .env up -d

# 에이전트 PC (SSH 터널 사용)
ssh -L 6379:localhost:6379 -L 5432:localhost:5432 -L 7700:localhost:7700 user@central_ip

# (다른 터미널)
export REDIS_URL="redis://:PASSWORD@localhost:6379"
export CORE_API_URL="http://localhost:7700"
cd services/detection-agents
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

**보안 수준:** ⭐⭐⭐ 높음 (SSH 터널로 암호화)

---

### 시나리오 3: 클라우드 배포 (AWS/Azure)

```bash
# 중앙 서버 (AWS EC2)
bash setup-distributed.sh cloud
docker compose --env-file .env up -d

# 에이전트 PC (원격)
export REDIS_URL="redis://:PASSWORD@ec2-xxx.amazonaws.com:6379"
export CORE_API_URL="http://ec2-xxx.amazonaws.com:7700"
cd services/detection-agents
PYTHONPATH=../.. uvicorn main:app --host 0.0.0.0 --port 7704
```

**보안 수준:** ⭐⭐⭐ 높음 (보안 그룹 + 강한 비밀번호)
**추가 설정:**
- AWS 보안 그룹에서 IP 제한
- 데이터베이스 백업 활성화

---

## 🛡️ 보안 체크리스트

### 모든 환경
- [ ] `.env` 파일 생성 및 strong password 사용
- [ ] `.env` 파일을 `.gitignore`에 추가
  ```bash
  echo ".env" >> .gitignore
  echo ".env.security" >> .gitignore
  ```
- [ ] 비밀번호를 안전한 곳에 저장 (1password, 노션 등)

### 로컬 네트워크
- [ ] 같은 와이파이 또는 LAN에 연결되었는지 확인
- [ ] 방화벽 설정 (필요시)

### 원격 접근
- [ ] SSH 터널 사용 (평문 전송 방지)
- [ ] 또는 VPN 사용
- [ ] PostgreSQL/Redis 포트를 localhost만으로 바인드

### 클라우드
- [ ] 보안 그룹에서 필요한 IP만 허용
- [ ] SSH 키페어 설정 (비밀번호 로그인 비활성화)
- [ ] CloudWatch/모니터링 활성화
- [ ] 자동 백업 활성화

---

## 🔧 설정 파일 위치

```
/Users/teamgrit/Documents/CoWater/
├── infra/
│   ├── docker-compose.yml       (수정됨 - 환경변수 적용)
│   ├── .env                     (setup-distributed.sh로 생성)
│   ├── .env.security            (참고용 템플릿)
│   └── setup-distributed.sh     (설정 자동화 스크립트)
├── DISTRIBUTED_SETUP.md         (상세 설명)
└── SETUP_INTERNET_EXPOSED.md    (이 파일)
```

---

## 🆘 트러블슈팅

### Redis 연결 실패
```bash
# 중앙 서버에서 Redis 상태 확인
docker exec cowater-redis redis-cli -a ${REDIS_PASSWORD} ping
# 응답: PONG

# 에이전트에서 테스트
redis-cli -h 192.168.1.100 -a ${REDIS_PASSWORD} ping
```

### PostgreSQL 연결 실패
```bash
# 중앙 서버에서 상태 확인
docker exec cowater-postgres pg_isready -U cowater

# 에이전트에서 테스트
psql -h 192.168.1.100 -U cowater -d cowater
# 비밀번호 입력 시 .env의 POSTGRES_PASSWORD 사용
```

### 에이전트 로그 확인
```bash
# 중앙 서버
docker logs cowater-detection-agents -f

# 에이전트 PC (로컬 실행 시)
tail -f ~/.local/share/logs/detection-agents.log
```

### 네트워크 연결 확인
```bash
# 중앙 서버 IP 확인
ifconfig | grep "inet " | grep -v 127.0.0.1

# 에이전트에서 접근 테스트
nc -zv 192.168.1.100 6379  # Redis
nc -zv 192.168.1.100 5432  # PostgreSQL
nc -zv 192.168.1.100 7700  # Core API
```

---

## 📚 참고자료

- [docker-compose 환경변수](https://docs.docker.com/compose/environment-variables/)
- [PostgreSQL 보안](https://www.postgresql.org/docs/current/ssl-tcp.html)
- [Redis 보안](https://redis.io/docs/management/security/)
- [SSH 터널](https://www.ssh.com/ssh/tunneling/example)

---

## ❓ FAQ

**Q: 같은 와이파이에서도 SSH 터널이 필요한가?**
A: 아니오. 같은 로컬 네트워크면 직접 연결 가능합니다. 하지만 보안을 위해 SSH 터널 사용을 권장합니다.

**Q: 클라우드에서 호스팅하려면?**
A: AWS EC2 또는 Azure VM에 docker compose를 실행하고, 보안 그룹에서 IP를 제한하세요.

**Q: 비밀번호를 잊어버렸다면?**
A: `.env` 파일을 다시 생성하고 docker compose를 재시작하면 됩니다:
```bash
bash setup-distributed.sh remote-tunnel
docker compose down
docker compose --env-file .env up -d
```

**Q: HTTPS(SSL)를 사용하려면?**
A: 추후 가이드 추가 예정. 현재는 SSH 터널로 암호화합니다.
