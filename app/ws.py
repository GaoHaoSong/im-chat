import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.db import get_conn, db_write_lock

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    def is_online(self, username: str) -> bool:
        return username in self._connections

    def online_users(self) -> list[str]:
        return list(self._connections.keys())

    async def connect(self, username: str, ws: WebSocket):
        async with self._lock:
            old = self._connections.get(username)
            self._connections[username] = ws
        if old is not None:
            try:
                await old.send_json({"type": "kicked"})
                await old.close()
            except Exception:
                pass

    async def disconnect(self, username: str, ws: WebSocket):
        async with self._lock:
            if self._connections.get(username) is ws:
                del self._connections[username]
                return True
        return False

    async def send_to(self, username: str, payload: dict) -> bool:
        ws = self._connections.get(username)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def broadcast(self, payload: dict, exclude: Optional[str] = None):
        for username, ws in list(self._connections.items()):
            if username == exclude:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                pass


manager = ConnectionManager()


async def _resolve_token(token: str) -> Optional[str]:
    conn = await get_conn()
    row = await (await conn.execute(
        "SELECT username FROM sessions WHERE token=?", (token,)
    )).fetchone()
    return row["username"] if row else None


async def _update_last_seen(username: str):
    conn = await get_conn()
    async with db_write_lock:
        await conn.execute(
            "UPDATE users SET last_seen_at=? WHERE username=?",
            (int(time.time()), username),
        )
        await conn.commit()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = Query(...)):
    username = await _resolve_token(token)
    if not username:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await manager.connect(username, websocket)
    await manager.broadcast({"type": "presence", "user": username, "online": True}, exclude=username)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "code": "bad_json", "message": "无效 JSON"})
                continue

            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "send":
                from app.messages import handle_send
                await handle_send(username, msg, websocket)
            elif mtype == "recall":
                from app.messages import handle_recall
                await handle_recall(username, msg, websocket)
            else:
                await websocket.send_json({"type": "error", "code": "unknown_type", "message": f"未知类型: {mtype}"})
    except WebSocketDisconnect:
        pass
    finally:
        removed = await manager.disconnect(username, websocket)
        if removed:
            await _update_last_seen(username)
            await manager.broadcast({"type": "presence", "user": username, "online": False})
