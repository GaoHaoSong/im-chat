import pytest
from fastapi.testclient import TestClient


async def _register(client, username, pin="1234"):
    r = await client.post("/api/register", json={
        "username": username, "pin": pin, "display_name": username.title()
    })
    return r.json()["token"]


def test_ws_connect_invalid_token(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        with pytest.raises(Exception):
            with c.websocket_connect("/ws?token=bad") as ws:
                ws.receive_json()


def test_ws_connect_valid_token(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"})
        token = r.json()["token"]
        with c.websocket_connect(f"/ws?token={token}") as ws:
            ws.send_json({"type": "ping"})
            msg = ws.receive_json()
            assert msg["type"] == "pong"


def test_ws_kicks_old_connection(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"})
        token = r.json()["token"]
        with c.websocket_connect(f"/ws?token={token}") as ws1:
            with c.websocket_connect(f"/ws?token={token}") as ws2:
                msg = ws1.receive_json()
                assert msg["type"] == "kicked"


def test_ws_presence_broadcast(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        ta = c.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"}).json()["token"]
        tb = c.post("/api/register", json={"username": "bob", "pin": "1234", "display_name": "B"}).json()["token"]
        with c.websocket_connect(f"/ws?token={ta}") as ws_a:
            with c.websocket_connect(f"/ws?token={tb}") as ws_b:
                msg = ws_a.receive_json()
                assert msg["type"] == "presence"
                assert msg["user"] == "bob"
                assert msg["online"] is True


def test_register_broadcasts_user_added(isolated_db):
    from app.main import app
    with TestClient(app) as c:
        ta = c.post("/api/register", json={"username": "alice", "pin": "1234", "display_name": "A"}).json()["token"]
        with c.websocket_connect(f"/ws?token={ta}") as ws_a:
            r = c.post("/api/register", json={"username": "bob", "pin": "1234", "display_name": "Bob"})
            assert r.status_code == 200
            msg = ws_a.receive_json()
            assert msg["type"] == "user_added"
            assert msg["user"]["username"] == "bob"
            assert msg["user"]["display_name"] == "Bob"
            assert msg["user"]["online"] is False
            assert msg["user"]["unread"] == 0
