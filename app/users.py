import json
from fastapi import APIRouter, Depends

from app.db import get_conn
from app.auth import current_user

router = APIRouter(prefix="/api")


def _is_online(username: str) -> bool:
    from app.ws import manager
    return manager.is_online(username)


@router.get("/users")
async def list_users(me: str = Depends(current_user)):
    conn = await get_conn()
    rows = await (await conn.execute(
        "SELECT username, display_name, last_seen_at, read_state, avatar FROM users ORDER BY username"
    )).fetchall()

    my_row = await (await conn.execute(
        "SELECT read_state FROM users WHERE username=?", (me,)
    )).fetchone()
    read_state = json.loads(my_row["read_state"]) if my_row else {}

    result = []
    for r in rows:
        peer = r["username"]
        unread = 0
        if peer != me:
            last_read = read_state.get(peer, 0)
            cnt = await (await conn.execute(
                """SELECT COUNT(*) AS c FROM messages
                   WHERE to_user=? AND from_user=? AND created_at>? AND recalled=0""",
                (me, peer, last_read),
            )).fetchone()
            unread = cnt["c"]
        result.append({
            "username": peer,
            "display_name": r["display_name"],
            "online": _is_online(peer),
            "last_seen_at": r["last_seen_at"],
            "unread": unread,
            "avatar": r["avatar"],
        })
    return {"users": result}
