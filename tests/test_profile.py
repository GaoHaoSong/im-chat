import pytest


async def _register(client, username, pin="1234"):
    r = await client.post("/api/register", json={
        "username": username, "pin": pin, "display_name": username.title()
    })
    return r.json()["token"]


async def test_update_profile_display_name(client):
    token = await _register(client, "alice")
    r = await client.post("/api/me/profile", json={"display_name": "Alice New"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user"]["display_name"] == "Alice New"


async def test_update_profile_avatar(client):
    token = await _register(client, "alice")
    r = await client.post("/api/me/profile", json={"avatar": "🌟"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user"]["avatar"] == "🌟"


async def test_update_profile_both(client):
    token = await _register(client, "alice")
    r = await client.post("/api/me/profile", json={"display_name": "X", "avatar": "🦊"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()["user"]
    assert body["display_name"] == "X"
    assert body["avatar"] == "🦊"


async def test_update_profile_empty(client):
    token = await _register(client, "alice")
    r = await client.post("/api/me/profile", json={},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


async def test_update_profile_unauthorized(client):
    r = await client.post("/api/me/profile", json={"display_name": "x"})
    assert r.status_code == 401


async def test_change_pin_success(client):
    token = await _register(client, "alice", pin="1234")
    r = await client.post("/api/me/pin", json={"current_pin": "1234", "new_pin": "5678"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # Login with new PIN
    r2 = await client.post("/api/login", json={"username": "alice", "pin": "5678"})
    assert r2.status_code == 200


async def test_change_pin_wrong_current(client):
    token = await _register(client, "alice", pin="1234")
    r = await client.post("/api/me/pin", json={"current_pin": "9999", "new_pin": "5678"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_delete_account(client):
    token = await _register(client, "alice", pin="1234")
    # Upload a file so we can verify it gets cleaned up
    files = {"file": ("h.txt", b"x", "text/plain")}
    meta = (await client.post("/api/upload", files=files, headers={"Authorization": f"Bearer {token}"})).json()
    fid = meta["file_id"]
    # Verify the file exists on disk
    from app import config
    path = config.UPLOAD_DIR / f"{fid}_h.txt"
    assert path.exists()
    # Delete account
    r = await client.request("DELETE", "/api/me", json={"pin": "1234"},
                             headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # Token should be invalid
    r2 = await client.post("/api/auto_login", json={"token": token})
    assert r2.status_code == 401
    # File should be deleted
    assert not path.exists()


async def test_delete_account_wrong_pin(client):
    token = await _register(client, "alice", pin="1234")
    r = await client.request("DELETE", "/api/me", json={"pin": "9999"},
                             headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_users_includes_avatar(client):
    token = await _register(client, "alice")
    r = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    user = r.json()["users"][0]
    assert "avatar" in user
    assert user["avatar"] == ""


async def test_auto_login_includes_avatar(client):
    token = await _register(client, "alice")
    r = await client.post("/api/me/profile", json={"avatar": "🎉"},
                          headers={"Authorization": f"Bearer {token}"})
    r2 = await client.post("/api/auto_login", json={"token": token})
    assert r2.json()["avatar"] == "🎉"
