import time
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse

from app import config
from app.db import get_conn, db_write_lock
from app.auth import current_user

router = APIRouter(prefix="/api")


def _err(code, message, status):
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


@router.post("/upload")
async def upload(file: UploadFile = File(...), me: str = Depends(current_user)):
    data = await file.read()
    size = len(data)
    is_image = (file.content_type or "").startswith("image/")
    limit = config.MAX_IMAGE_SIZE if is_image else config.MAX_FILE_SIZE
    if size > limit:
        _err("file_too_large", f"文件超过 {limit} 字节限制", 413)

    file_id = uuid.uuid4().hex
    safe_name = Path(file.filename or "file").name
    path = config.UPLOAD_DIR / f"{file_id}_{safe_name}"
    path.write_bytes(data)

    conn = await get_conn()
    async with db_write_lock:
        await conn.execute(
            "INSERT INTO files(file_id, original_name, size, mime, uploader, created_at) VALUES(?,?,?,?,?,?)",
            (file_id, safe_name, size, file.content_type or "application/octet-stream", me, int(time.time())),
        )
        await conn.commit()
    return {
        "file_id": file_id,
        "name": safe_name,
        "size": size,
        "mime": file.content_type or "application/octet-stream",
    }


@router.get("/files/{file_id}")
async def download(file_id: str, me: str = Depends(current_user)):
    conn = await get_conn()
    row = await (await conn.execute(
        "SELECT original_name, mime FROM files WHERE file_id=?", (file_id,)
    )).fetchone()
    if not row:
        _err("not_found", "文件不存在", 404)
    path = config.UPLOAD_DIR / f"{file_id}_{row['original_name']}"
    if not path.exists():
        _err("not_found", "文件不存在", 404)
    disposition = "inline" if row["mime"].startswith("image/") else "attachment"
    return FileResponse(
        path,
        media_type=row["mime"],
        filename=row["original_name"],
        content_disposition_type=disposition,
    )
