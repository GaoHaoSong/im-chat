import json
import pytest
from fastapi.testclient import TestClient


def _setup_two_users(c):
    ta = c.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"}).json()["token"]
    tb = c.post("/api/register", json={"username": "bob", "pin": "1234", "display_name": "B"}).json()["token"]
    return ta, tb


def test_send_text_message(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        ta, tb = _setup_two_users(c)
        with c.websocket_connect(f"/ws?token={ta}") as ws_a, c.websocket_connect(f"/ws?token={tb}") as ws_b:
            ws_a.receive_json()  # bob presence
            ws_a.send_json({"type": "send", "to": "bob", "kind": "text", "content": "hi"})
            msg_a = ws_a.receive_json()
            msg_b = ws_b.receive_json()
            assert msg_a["type"] == "message"
            assert msg_a["message"]["content"] == "hi"
            assert msg_a["message"]["from_user"] == "alice"
            assert msg_a["message"]["to_user"] == "bob"
            assert msg_b["type"] == "message"
            assert msg_b["message"]["id"] == msg_a["message"]["id"]


def test_send_to_unknown_user(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        ta, _ = _setup_two_users(c)
        with c.websocket_connect(f"/ws?token={ta}") as ws_a:
            ws_a.send_json({"type": "send", "to": "ghost", "kind": "text", "content": "hi"})
            msg = ws_a.receive_json()
            assert msg["type"] == "error"
            assert msg["code"] == "unknown_peer"


async def test_history_returns_messages(client):
    ta = (await client.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"})).json()["token"]
    await client.post("/api/register", json={"username": "bob", "pin": "1234", "display_name": "B"})
    from app.main import app
    with TestClient(app) as c:
        tb = c.post("/api/login", json={"username": "bob", "pin": "1234"}).json()["token"]
        with c.websocket_connect(f"/ws?token={ta}") as ws_a, c.websocket_connect(f"/ws?token={tb}") as ws_b:
            ws_a.receive_json()
            for i in range(3):
                ws_a.send_json({"type": "send", "to": "bob", "kind": "text", "content": f"msg{i}"})
                ws_a.receive_json()
                ws_b.receive_json()
    r = await client.get("/api/messages?peer=bob&limit=10", headers={"Authorization": f"Bearer {ta}"})
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 3
    assert msgs[0]["content"] == "msg0"
    assert msgs[-1]["content"] == "msg2"


async def test_mark_read_clears_unread(client):
    ta = (await client.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"})).json()["token"]
    tb = (await client.post("/api/register", json={"username": "bob", "pin": "1234", "display_name": "B"})).json()["token"]
    from app.main import app
    with TestClient(app) as c:
        t_alice = c.post("/api/login", json={"username": "alice", "pin": "1234"}).json()["token"]
        with c.websocket_connect(f"/ws?token={t_alice}") as ws_a:
            ws_a.send_json({"type": "send", "to": "bob", "kind": "text", "content": "hi"})
            ws_a.receive_json()
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {tb}"})
    bob_view = {u["username"]: u for u in r.json()["users"]}
    assert bob_view["alice"]["unread"] == 1
    await client.post("/api/messages/read", json={"peer": "alice"}, headers={"Authorization": f"Bearer {tb}"})
    r2 = await client.get("/api/users", headers={"Authorization": f"Bearer {tb}"})
    bob_view2 = {u["username"]: u for u in r2.json()["users"]}
    assert bob_view2["alice"]["unread"] == 0
