import pytest


async def test_register_success(client):
    r = await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    assert r.status_code == 200
    data = r.json()
    assert "token" in data and len(data["token"]) >= 32


async def test_register_duplicate_username(client):
    await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    r = await client.post("/api/register", json={
        "username": "alice", "pin": "5678", "display_name": "A2"
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "username_taken"


async def test_register_invalid_username(client):
    r = await client.post("/api/register", json={
        "username": "ab", "pin": "1234", "display_name": "X"
    })
    assert r.status_code == 422


async def test_register_invalid_pin(client):
    r = await client.post("/api/register", json={
        "username": "alice", "pin": "abc", "display_name": "X"
    })
    assert r.status_code == 422


async def test_login_success(client):
    await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    r = await client.post("/api/login", json={"username": "alice", "pin": "1234"})
    assert r.status_code == 200
    assert "token" in r.json()


async def test_login_wrong_pin(client):
    await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    r = await client.post("/api/login", json={"username": "alice", "pin": "9999"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


async def test_login_unknown_user(client):
    r = await client.post("/api/login", json={"username": "ghost", "pin": "1234"})
    assert r.status_code == 401


async def test_auto_login_success(client):
    r1 = await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    token = r1.json()["token"]
    r = await client.post("/api/auto_login", json={"token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "alice"
    assert body["display_name"] == "Alice"


async def test_auto_login_invalid_token(client):
    r = await client.post("/api/auto_login", json={"token": "deadbeef"})
    assert r.status_code == 401


async def test_logout_invalidates_token(client):
    r1 = await client.post("/api/register", json={
        "username": "alice", "pin": "1234", "display_name": "Alice"
    })
    token = r1.json()["token"]
    r = await client.post("/api/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r2 = await client.post("/api/auto_login", json={"token": token})
    assert r2.status_code == 401
