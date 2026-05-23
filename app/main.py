from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app import config
from app.db import init_db, close_db

app = FastAPI(title="IM Chat")

STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.on_event("shutdown")
async def on_shutdown():
    await close_db()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
