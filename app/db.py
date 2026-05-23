import asyncio
import aiosqlite

from app import config

_conn: aiosqlite.Connection | None = None
db_write_lock = asyncio.Lock()


async def get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(str(config.DB_PATH))
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA foreign_keys=ON")
        _conn.row_factory = aiosqlite.Row
    return _conn


async def init_db():
    conn = await get_conn()
    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        pin_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL DEFAULT 0,
        read_state TEXT NOT NULL DEFAULT '{}',
        avatar TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        reply_to_id INTEGER,
        mentions TEXT,
        created_at INTEGER NOT NULL,
        recalled INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_msg_from_to_ts
        ON messages(from_user, to_user, created_at);
    CREATE INDEX IF NOT EXISTS idx_msg_to_from_ts
        ON messages(to_user, from_user, created_at);
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS files (
        file_id TEXT PRIMARY KEY,
        original_name TEXT NOT NULL,
        size INTEGER NOT NULL,
        mime TEXT NOT NULL,
        uploader TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    """)
    await conn.commit()

    # Migration: add avatar column to existing users tables that don't have it
    cur = await conn.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in await cur.fetchall()}
    if "avatar" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")
        await conn.commit()


async def close_db():
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
