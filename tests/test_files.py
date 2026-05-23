import pytest


async def _register(client, username, pin="1234"):
    r = await client.post("/api/register", json={
        "username": username, "pin": pin, "display_name": username.title()
    })
    return r.json()["token"]


async def test_upload_and_download(client):
    token = await _register(client, "alice")
    files = {"file": ("hello.txt", b"world", "text/plain")}
    r = await client.post("/api/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    meta = r.json()
    assert meta["name"] == "hello.txt"
    assert meta["size"] == 5
    assert meta["mime"] == "text/plain"
    fid = meta["file_id"]

    r2 = await client.get(f"/api/files/{fid}", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.content == b"world"


async def test_upload_too_large(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_FILE_SIZE", 4)
    token = await _register(client, "alice")
    files = {"file": ("big.bin", b"12345", "application/octet-stream")}
    r = await client.post("/api/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 413


async def test_download_missing(client):
    token = await _register(client, "alice")
    r = await client.get("/api/files/nonexistent", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


async def test_upload_unauthorized(client):
    files = {"file": ("hello.txt", b"world", "text/plain")}
    r = await client.post("/api/upload", files=files)
    assert r.status_code == 401


async def test_download_with_query_token(client):
    token = await _register(client, "alice")
    files = {"file": ("hi.txt", b"x", "text/plain")}
    meta = (await client.post("/api/upload", files=files, headers={"Authorization": f"Bearer {token}"})).json()
    fid = meta["file_id"]
    # Use ?token= instead of header
    r = await client.get(f"/api/files/{fid}?token={token}")
    assert r.status_code == 200
    assert r.content == b"x"


async def test_download_invalid_token_query(client):
    token = await _register(client, "alice")
    files = {"file": ("hi.txt", b"x", "text/plain")}
    meta = (await client.post("/api/upload", files=files, headers={"Authorization": f"Bearer {token}"})).json()
    fid = meta["file_id"]
    r = await client.get(f"/api/files/{fid}?token=bad")
    assert r.status_code == 401
