import json
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_conn, db_write_lock
from app.auth import current_user
from app.ws import manager

router = APIRouter(prefix="/api")


def _err(code, message, status):
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


async def _user_exists(username: str) -> bool:
    conn = await get_conn()
    row = await (await conn.execute("SELECT 1 FROM users WHERE username=?", (username,))).fetchone()
    return row is not None


async def _row_to_message(row) -> dict:
    return {
        "id": row["id"],
        "from_user": row["from_user"],
        "to_user": row["to_user"],
        "kind": row["kind"],
        "content": row["content"],
        "reply_to_id": row["reply_to_id"],
        "mentions": json.loads(row["mentions"]) if row["mentions"] else [],
        "created_at": row["created_at"],
        "recalled": bool(row["recalled"]),
    }


async def handle_send(username: str, msg: dict, websocket):
    to_user = msg.get("to")
    kind = msg.get("kind", "text")
    content = msg.get("content", "")
    reply_to_id = msg.get("reply_to_id")
    mentions = msg.get("mentions") or []
    client_temp_id = msg.get("temp_id")

    if not to_user or kind not in ("text", "image", "file"):
        await websocket.send_json({"type": "error", "code": "bad_payload", "message": "字段错误"})
        return
    if not await _user_exists(to_user):
        await websocket.send_json({"type": "error", "code": "unknown_peer", "message": "目标用户不存在"})
        return

    now = int(time.time())
    conn = await get_conn()
    async with db_write_lock:
        cur = await conn.execute(
            """INSERT INTO messages(from_user, to_user, kind, content, reply_to_id, mentions, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (username, to_user, kind, content, reply_to_id, json.dumps(mentions) if mentions else None, now),
        )
        msg_id = cur.lastrowid
        await conn.commit()

    row = await (await conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,))).fetchone()
    message = await _row_to_message(row)
    envelope = {"type": "message", "message": message}
    if client_temp_id is not None:
        envelope["temp_id"] = client_temp_id
    await manager.send_to(username, envelope)
    if to_user != username:
        await manager.send_to(to_user, {"type": "message", "message": message})


async def handle_recall(username: str, msg: dict, websocket):
    pass  # implemented in Task 10


class ReadRequest(BaseModel):
    peer: str


@router.get("/messages")
async def get_messages(peer: str, before: int | None = None, limit: int = 30, me: str = Depends(current_user)):
    if limit < 1 or limit > 100:
        limit = 30
    conn = await get_conn()
    query = """SELECT * FROM messages
               WHERE ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))"""
    params = [me, peer, peer, me]
    if before is not None:
        query += " AND id<?"
        params.append(before)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = await (await conn.execute(query, params)).fetchall()
    msgs = [await _row_to_message(r) for r in reversed(rows)]
    return {"messages": msgs}


@router.post("/messages/read")
async def mark_read(req: ReadRequest, me: str = Depends(current_user)):
    conn = await get_conn()
    row = await (await conn.execute("SELECT read_state FROM users WHERE username=?", (me,))).fetchone()
    state = json.loads(row["read_state"]) if row else {}
    state[req.peer] = int(time.time())
    async with db_write_lock:
        await conn.execute(
            "UPDATE users SET read_state=? WHERE username=?",
            (json.dumps(state), me),
        )
        await conn.commit()
    return {"ok": True}
