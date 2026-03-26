"""
CoWater Maritime AI Proxy
클라이언트 → FastAPI → Ollama → 모델

실행:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import Optional
from dataclasses import dataclass, field

app = FastAPI(title="CoWater AI Proxy", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE = "http://localhost:11434"


# ── Request / Response 모델 ────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 1024

class ChatResponse(BaseModel):
    text: str
    model: str
    done: bool


# ── Pull 상태 (백그라운드 태스크와 폴링 공유) ──────────────────────────────────

@dataclass
class PullState:
    status: str = "starting"   # starting | pulling | verifying | success | error
    pct: int = 0
    msg: str = ""
    done: bool = False
    error: str = ""

_pull_states: dict[str, PullState] = {}


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

async def _is_model_installed(model_name: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            installed = [m["name"] for m in resp.json().get("models", [])]
            return model_name in installed
    except Exception:
        return False

async def _do_pull(model_name: str) -> None:
    """브라우저 연결과 독립적으로 실행되는 백그라운드 pull 태스크"""
    state = _pull_states[model_name]
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE}/api/pull",
                json={"name": model_name, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status = data.get("status", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)
                    pct = 0
                    if total > 0 and completed > 0:
                        pct = round(completed / total * 100)
                        state.pct = pct

                    # 사람이 읽기 편한 상태 메시지
                    if "pulling" in status:
                        total_mb = data.get("total", 0) / 1024 / 1024
                        done_mb  = data.get("completed", 0) / 1024 / 1024
                        state.msg = f"{done_mb:.0f} / {total_mb:.0f} MB"
                        state.status = "pulling"
                    elif "verifying" in status or "writing" in status:
                        state.status = "verifying"
                        state.msg = status
                        state.pct = 99
                    else:
                        state.msg = status

        state.status = "success"
        state.pct = 100
        state.msg = "완료"
        state.done = True

    except asyncio.CancelledError:
        state.status = "error"
        state.error = "취소됨"
        state.done = True
    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.done = True


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.get(f"{OLLAMA_BASE}/api/tags")
        ollama_ok = True
    except Exception:
        ollama_ok = False
    return {"status": "ok", "ollama": ollama_ok}


@app.get("/api/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            return {"models": [m["name"] for m in resp.json().get("models", [])]}
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ollama 연결 실패")


@app.post("/api/pull/{model_name:path}")
async def start_pull(model_name: str):
    """
    모델 pull을 asyncio 태스크로 시작합니다.
    브라우저 연결과 완전히 독립적으로 실행됩니다.
    """
    existing = _pull_states.get(model_name)
    if existing and not existing.done:
        return {"status": "already_running"}

    _pull_states[model_name] = PullState()
    asyncio.create_task(_do_pull(model_name))
    return {"status": "started"}


@app.get("/api/pull/progress/{model_name:path}")
async def pull_progress(model_name: str):
    """프론트엔드가 폴링으로 pull 진행률을 확인합니다."""
    state = _pull_states.get(model_name)
    if state is None:
        return {"status": "not_started", "pct": 0, "msg": "", "done": False, "error": ""}
    return {
        "status": state.status,
        "pct": state.pct,
        "msg": state.msg,
        "done": state.done,
        "error": state.error,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not await _is_model_installed(req.model):
        raise HTTPException(
            status_code=422,
            detail={"code": "model_not_found", "model": req.model},
        )

    payload = {
        "model": req.model,
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        "stream": False,
        "options": {
            "temperature": req.temperature,
            "num_predict": req.max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ollama 연결 실패")

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        return ChatResponse(
            text=data["message"]["content"],
            model=data.get("model", req.model),
            done=data.get("done", True),
        )
