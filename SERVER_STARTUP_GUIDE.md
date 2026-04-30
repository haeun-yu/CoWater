# CoWater 서버 실행 가이드

## 📋 목차
1. [사전 준비](#사전-준비)
2. [Python 버전 확인](#python-버전-확인)
3. [가상 환경 설정](#가상-환경-설정)
4. [각 서버 실행 방법](#각-서버-실행-방법)
5. [한 번에 모든 서버 실행](#한-번에-모든-서버-실행)
6. [서버 상태 확인](#서버-상태-확인)

---

## 사전 준비

```bash
# CoWater 프로젝트 디렉토리로 이동
cd /Users/teamgrit/Documents/CoWater
```

---

## Python 버전 확인

### Python 설치 상태 확인

```bash
# 설치된 Python 버전 확인
python --version
python3 --version

# 어느 것이 사용되는지 확인
which python
which python3
```

### Python 버전별 실행 명령어
- **Python 3.x 이상 단일 설치**: `python` 사용
- **Python 2.x, 3.x 모두 설치**: `python3` 사용
- **불확실한 경우**: `python3` 사용 (권장)

---

## 가상 환경 설정

### 가상 환경 활성화 (`.venv` 사용)

```bash
# 1단계: 가상 환경 활성화 (macOS/Linux)
source .venv/bin/activate

# 1단계: 가상 환경 활성화 (Windows - PowerShell)
.venv\Scripts\Activate.ps1

# 1단계: 가상 환경 활성화 (Windows - CMD)
.venv\Scripts\activate.bat
```

### 가상 환경 비활성화
```bash
deactivate
```

### 확인 방법
활성화된 가상 환경은 프롬프트에 `(.venv)` 표시:
```
(.venv) teamgrit@macbook CoWater % 
```

---

## 각 서버 실행 방법

### 1️⃣ Device Registration Server (POC 00)

**디렉토리**: `pocs/00-device-registration-server`

**포트**: 8280

**가상 환경 활성화 후 실행**:
```bash
# 방법 A: 가상 환경 활성화해서 실행 (권장)
source .venv/bin/activate
cd pocs/00-device-registration-server
python device_registration_server.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/00-device-registration-server
python3 device_registration_server.py
```

**포트 변경 실행**:
```bash
python device_registration_server.py --port 8281
```

**상태 확인**:
```bash
curl http://localhost:8280/health | jq .
```

---

### 2️⃣ System Supervisor Agent (POC 06)

**디렉토리**: `pocs/06-system-supervisor-agent`

**포트**: 9116 (기본값, config.json에서 변경 가능)

**실행 방법**:
```bash
# 방법 A: 가상 환경 활성화 후 실행 (권장)
source .venv/bin/activate
cd pocs/06-system-supervisor-agent
python system_agent.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/06-system-supervisor-agent
python3 system_agent.py

# 방법 C: Config 파일 지정해서 실행
python system_agent.py --config config.yaml
```

**포트 변경**:
`config.json`의 `server.port` 값 수정 후 실행

**상태 확인**:
```bash
curl http://localhost:9116/health | jq .
```

---

### 3️⃣ Control Ship Agent (POC 05)

**디렉토리**: `pocs/05-control-ship-middle-agent`

**포트**: 9015 (기본값, config.json에서 변경 가능)

**실행 방법**:
```bash
# 방법 A: 가상 환경 활성화 후 실행 (권장)
source .venv/bin/activate
cd pocs/05-control-ship-middle-agent
python device_agent.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/05-control-ship-middle-agent
python3 device_agent.py

# 방법 C: Config 파일 지정해서 실행
python device_agent.py --config config.yaml
```

**상태 확인**:
```bash
curl http://localhost:9015/health | jq .
```

---

### 4️⃣ AUV Lower Agent (POC 02)

**디렉토리**: `pocs/02-auv-lower-agent`

**포트**: 9010 (기본값, config.json에서 변경 가능)

**실행 방법**:
```bash
# 방법 A: 가상 환경 활성화 후 실행 (권장)
source .venv/bin/activate
cd pocs/02-auv-lower-agent
python device_agent.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/02-auv-lower-agent
python3 device_agent.py

# 방법 C: Instance ID 지정해서 실행
COWATER_INSTANCE_ID=auv-001 python device_agent.py
```

**상태 확인**:
```bash
curl http://localhost:9010/health | jq .
```

---

### 5️⃣ ROV Lower Agent (POC 03)

**디렉토리**: `pocs/03-rov-lower-agent`

**포트**: 9011 (기본값, config.json에서 변경 가능)

**실행 방법**:
```bash
# 방법 A: 가상 환경 활성화 후 실행 (권장)
source .venv/bin/activate
cd pocs/03-rov-lower-agent
python device_agent.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/03-rov-lower-agent
python3 device_agent.py
```

**상태 확인**:
```bash
curl http://localhost:9011/health | jq .
```

---

### 6️⃣ USV Middle Agent (POC 04)

**디렉토리**: `pocs/04-usv-middle-agent`

**포트**: 9014 (기본값, config.json에서 변경 가능)

**실행 방법**:
```bash
# 방법 A: 가상 환경 활성화 후 실행 (권장)
source .venv/bin/activate
cd pocs/04-usv-middle-agent
python device_agent.py

# 방법 B: 가상 환경 없이 python3로 직접 실행
cd pocs/04-usv-middle-agent
python3 device_agent.py
```

**상태 확인**:
```bash
curl http://localhost:9014/health | jq .
```

---

### 7️⃣ POC 07 실시간 대시보드

**디렉토리**: `pocs/07-realtime-dashboard`

**포트**: 9010 (또는 지정된 포트)

**실행 방법**:

```bash
# 방법 A: Python HTTP 서버 (간단함)
cd pocs/07-realtime-dashboard
python -m http.server 9010

# 방법 B: python3 사용
cd pocs/07-realtime-dashboard
python3 -m http.server 9010

# 방법 C: 다른 포트 사용
python -m http.server 8000
```

**브라우저 접속**:
```
http://localhost:9010
```

---

## 한 번에 모든 서버 실행

### 스크립트로 실행 (macOS/Linux)

**파일**: `start_all_servers.sh`

```bash
#!/bin/bash

ROOT="/Users/teamgrit/Documents/CoWater"
cd "$ROOT"

# 가상 환경 활성화
source .venv/bin/activate

# 1. Device Registry
echo "[1/6] Device Registry 시작..."
cd pocs/00-device-registration-server
python device_registration_server.py > /tmp/registry.log 2>&1 &
sleep 2

# 2. System Supervisor
echo "[2/6] System Supervisor 시작..."
cd ../06-system-supervisor-agent
python system_agent.py > /tmp/supervisor.log 2>&1 &
sleep 2

# 3. Control Ship
echo "[3/6] Control Ship 시작..."
cd ../05-control-ship-middle-agent
python device_agent.py > /tmp/control_ship.log 2>&1 &
sleep 2

# 4. AUV
echo "[4/6] AUV 시작..."
cd ../02-auv-lower-agent
python device_agent.py > /tmp/auv.log 2>&1 &
sleep 2

# 5. ROV
echo "[5/6] ROV 시작..."
cd ../03-rov-lower-agent
python device_agent.py > /tmp/rov.log 2>&1 &
sleep 2

# 6. POC 07 Dashboard
echo "[6/6] POC 07 대시보드 시작..."
cd ../07-realtime-dashboard
python -m http.server 9010 > /tmp/dashboard.log 2>&1 &

echo ""
echo "모든 서버가 시작되었습니다!"
echo "대시보드: http://localhost:9010"
```

**실행 방법**:
```bash
chmod +x start_all_servers.sh
./start_all_servers.sh
```

### 수동으로 각 터미널에서 실행

**터미널 1 - Device Registry**:
```bash
cd pocs/00-device-registration-server
python device_registration_server.py
```

**터미널 2 - System Supervisor**:
```bash
cd pocs/06-system-supervisor-agent
python system_agent.py
```

**터미널 3 - Control Ship**:
```bash
cd pocs/05-control-ship-middle-agent
python device_agent.py
```

**터미널 4 - AUV**:
```bash
cd pocs/02-auv-lower-agent
python device_agent.py
```

**터미널 5 - ROV**:
```bash
cd pocs/03-rov-lower-agent
python device_agent.py
```

**터미널 6 - POC 07 대시보드**:
```bash
cd pocs/07-realtime-dashboard
python -m http.server 9010
```

**웹 브라우저**:
```
http://localhost:9010
```

---

## 서버 상태 확인

### 개별 서버 상태 확인

```bash
# Device Registry
curl http://localhost:8280/health

# System Supervisor
curl http://localhost:9116/health

# Control Ship
curl http://localhost:9015/health

# AUV
curl http://localhost:9010/health

# ROV
curl http://localhost:9011/health
```

### 모든 서버 상태 한 번에 확인

```bash
#!/bin/bash

echo "=== CoWater 서버 상태 확인 ==="
echo ""

for port in 8280 9116 9015 9010 9011 9014; do
    server_name=""
    case $port in
        8280) server_name="Device Registry" ;;
        9116) server_name="System Supervisor" ;;
        9015) server_name="Control Ship" ;;
        9010) server_name="AUV" ;;
        9011) server_name="ROV" ;;
        9014) server_name="USV Middle" ;;
    esac
    
    if curl -s http://localhost:$port/health > /dev/null 2>&1; then
        echo "✓ $server_name (포트 $port) - 온라인"
    else
        echo "✗ $server_name (포트 $port) - 오프라인"
    fi
done

echo ""
echo "대시보드: http://localhost:9010"
```

### 실행 중인 Python 프로세스 확인

```bash
ps aux | grep python | grep -v grep
```

### 포트 사용 확인

```bash
# macOS/Linux
lsof -i :8280
lsof -i :9116
lsof -i :9015
lsof -i :9010

# Windows
netstat -ano | findstr :8280
```

---

## 문제 해결

### "Address already in use" 에러

포트가 이미 사용 중인 경우:

```bash
# 1. 기존 프로세스 확인
lsof -i :포트번호

# 2. 프로세스 종료
kill -9 프로세스ID

# 또는 모든 Python 프로세스 종료 (주의!)
pkill -9 python
```

### "Module not found" 에러

```bash
# 1. 가상 환경 활성화 확인
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 다시 실행
python device_agent.py
```

### Python 버전 문제

```bash
# Python 3.10 이상이 필요한 경우
python3.10 --version
python3.10 device_agent.py

# 또는 pyenv 사용
pyenv install 3.10
pyenv local 3.10
```

### Moth 연결 실패

```bash
# Moth 서버 상태 확인
# wss://cobot.center:8287 가 응답하는지 확인

# 또는 로그에서 상세 정보 확인
tail -f /tmp/registry.log
tail -f /tmp/supervisor.log
```

---

## 요약 테이블

| 서버 | POC | 디렉토리 | 포트 | 명령어 |
|------|-----|---------|------|--------|
| Device Registry | 00 | `pocs/00-device-registration-server` | 8280 | `python device_registration_server.py` |
| System Supervisor | 06 | `pocs/06-system-supervisor-agent` | 9116 | `python system_agent.py` |
| Control Ship | 05 | `pocs/05-control-ship-middle-agent` | 9015 | `python device_agent.py` |
| AUV | 02 | `pocs/02-auv-lower-agent` | 9010 | `python device_agent.py` |
| ROV | 03 | `pocs/03-rov-lower-agent` | 9011 | `python device_agent.py` |
| USV Middle | 04 | `pocs/04-usv-middle-agent` | 9014 | `python device_agent.py` |
| POC 07 Dashboard | 07 | `pocs/07-realtime-dashboard` | 9010 | `python -m http.server 9010` |

---

**마지막 업데이트**: 2026-04-29
