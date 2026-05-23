import secrets
import time
import bcrypt
from fastapi import APIRouter, HTTPException, Depends, Header

from app.db import get_conn, db_write_lock
from app.models import RegisterRequest, LoginRequest, AutoLoginRequest

router = APIRouter(prefix="/api")


def _err(code: str, message: str, status: int):
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


async def _create_session(username: str) -> str:
    token = secrets.token_hex(32)
    conn = await get_conn()
    async with db_write_lock:
        await conn.execute(
            "INSERT INTO sessions(token, username, created_at) VALUES(?,?,?)",
            (token, username, int(time.time())),
        )
        await conn.commit()
    return token


@router.post("/register")
async def register(req: RegisterRequest):
    conn = await get_conn()
    pin_hash = bcrypt.hashpw(req.pin.encode(), bcrypt.gensalt()).decode()
    async with db_write_lock:
        cur = await conn.execute("SELECT 1 FROM users WHERE username=?", (req.username,))
        if await cur.fetchone():
            _err("username_taken", "用户名已被占用", 409)
        await conn.execute(
            "INSERT INTO users(username, pin_hash, display_name, created_at) VALUES(?,?,?,?)",
            (req.username, pin_hash, req.display_name, int(time.time())),
        )
        await conn.commit()
    token = await _create_session(req.username)
    return {"token": token}


@router.post("/login")
async def login(req: LoginRequest):
    conn = await get_conn()
    row = await (await conn.execute(
        "SELECT pin_hash FROM users WHERE username=?", (req.username,)
    )).fetchone()
    if not row:
        _err("invalid_credentials", "用户名或 PIN 错误", 401)
    if not bcrypt.checkpw(req.pin.encode(), row["pin_hash"].encode()):
        _err("invalid_credentials", "用户名或 PIN 错误", 401)
    token = await _create_session(req.username)
    return {"token": token}


async def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        _err("unauthorized", "缺少 token", 401)
    token = authorization.split(" ", 1)[1]
    conn = await get_conn()
    row = await (await conn.execute(
        "SELECT username FROM sessions WHERE token=?", (token,)
    )).fetchone()
    if not row:
        _err("unauthorized", "token 无效", 401)
    return row["username"]
