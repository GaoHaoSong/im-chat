import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app import db, config


@pytest_asyncio.fixture
async def isolated_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    test_uploads = tmp_path / "uploads"
    test_uploads.mkdir()
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(config, "UPLOAD_DIR", test_uploads)
    monkeypatch.setattr(db, "_conn", None)
    await db.init_db()
    yield
    await db.close_db()


@pytest_asyncio.fixture
async def client(isolated_db):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
