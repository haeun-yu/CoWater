from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_hub import hub

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/platforms")
async def ws_platforms(ws: WebSocket):
    """실시간 플랫폼 위치/상태 스트림."""
    await hub.connect(ws, "platforms")
    try:
        while True:
            # 클라이언트 ping 유지 (연결 드롭 감지)
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws, "platforms")


@router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    """실시간 경보 스트림."""
    await hub.connect(ws, "alerts")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws, "alerts")


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    """실시간 이벤트 스트림 (detection → analysis → response → learning)."""
    await hub.connect(ws, "events")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws, "events")
