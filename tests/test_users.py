import pytest


async def _register(client, username, pin="1234"):
    r = await client.post("/api/register", json={
        "username": username, "pin": pin, "display_name": username.title()
    })
    return r.json()["token"]


async def test_users_list_includes_self(client):
    token = await _register(client, "alice")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    names = {u["username"] for u in body["users"]}
    assert "alice" in names


async def test_users_list_shows_others(client):
    await _register(client, "alice")
    token = await _register(client, "bob")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    names = {u["username"] for u in r.json()["users"]}
    assert names == {"alice", "bob"}


async def test_users_list_default_offline(client):
    token = await _register(client, "alice")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    users = {u["username"]: u for u in r.json()["users"]}
    assert users["alice"]["online"] is False
    assert users["alice"]["unread"] == 0


async def test_users_unauthorized(client):
    r = await client.get("/api/users")
    assert r.status_code == 401
