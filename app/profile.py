import os
import time
import bcrypt
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.db import get_conn, db_write_lock
from app.auth import current_user
from app.ws import manager

router = APIRouter(prefix="/api")


def _err(code, message, status):
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    avatar: str | None = Field(default=None, max_length=10)


class PinChange(BaseModel):
    current_pin: str = Field(pattern=config.PIN_PATTERN)
    new_pin: str = Field(pattern=config.PIN_PATTERN)


class DeleteAccount(BaseModel):
    pin: str = Field(pattern=config.PIN_PATTERN)


@router.post("/me/profile")
async def update_profile(req: ProfileUpdate, me: str = Depends(current_user)):
    if req.display_name is None and req.avatar is None:
        _err("bad_payload", "至少提供一个字段", 422)
    conn = await get_conn()
    sets = []
    params = []
    if req.display_name is not None:
        sets.append("display_name=?")
        params.append(req.display_name)
    if req.avatar is not None:
        sets.append("avatar=?")
        params.append(req.avatar)
    params.append(me)
    async with db_write_lock:
        await conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE username=?", params)
        await conn.commit()
    row = await (await conn.execute(
        "SELECT username, display_name, avatar FROM users WHERE username=?", (me,)
    )).fetchone()
    payload = {"username": row["username"], "display_name": row["display_name"], "avatar": row["avatar"]}
    await manager.broadcast({"type": "user_updated", "user": payload})
    return {"ok": True, "user": payload}


@router.post("/me/pin")
async def change_pin(req: PinChange, me: str = Depends(current_user)):
    conn = await get_conn()
    row = await (await conn.execute("SELECT pin_hash FROM users WHERE username=?", (me,))).fetchone()
    if not row or not bcrypt.checkpw(req.current_pin.encode(), row["pin_hash"].encode()):
        _err("invalid_credentials", "当前 PIN 错误", 401)
    new_hash = bcrypt.hashpw(req.new_pin.encode(), bcrypt.gensalt()).decode()
    async with db_write_lock:
        await conn.execute("UPDATE users SET pin_hash=? WHERE username=?", (new_hash, me))
        await conn.commit()
    return {"ok": True}


@router.delete("/me")
async def delete_me(req: DeleteAccount, me: str = Depends(current_user)):
    conn = await get_conn()
    row = await (await conn.execute("SELECT pin_hash FROM users WHERE username=?", (me,))).fetchone()
    if not row or not bcrypt.checkpw(req.pin.encode(), row["pin_hash"].encode()):
        _err("invalid_credentials", "PIN 错误", 401)
    # Collect files to delete from disk
    file_rows = await (await conn.execute(
        "SELECT file_id, original_name FROM files WHERE uploader=?", (me,)
    )).fetchall()
    async with db_write_lock:
        await conn.execute("DELETE FROM messages WHERE from_user=? OR to_user=?", (me, me))
        await conn.execute("DELETE FROM files WHERE uploader=?", (me,))
        await conn.execute("DELETE FROM sessions WHERE username=?", (me,))
        await conn.execute("DELETE FROM users WHERE username=?", (me,))
        await conn.commit()
    # Delete files from disk (best-effort)
    for fr in file_rows:
        path = config.UPLOAD_DIR / f"{fr['file_id']}_{fr['original_name']}"
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    # Disconnect the user's WebSocket if connected (kicks themselves out)
    await manager.send_to(me, {"type": "kicked"})
    # Forcibly remove from connection table
    try:
        ws = manager._connections.get(me)
        if ws is not None:
            await ws.close()
    except Exception:
        pass
    # Broadcast deletion
    await manager.broadcast({"type": "user_deleted", "username": me})
    return {"ok": True}
