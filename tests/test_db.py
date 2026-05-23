import pytest
from app import db


async def test_init_db_creates_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(db.config, "DB_PATH", tmp_path / "test.db")
    await db.init_db()
    conn = await db.get_conn()
    rows = await (await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )).fetchall()
    names = [r[0] for r in rows]
    assert "users" in names
    assert "messages" in names
    assert "sessions" in names
    await db.close_db()
