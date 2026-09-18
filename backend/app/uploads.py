import hashlib
import json
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .auth import current_user
from .db import UPLOADS_DIR, connect, utcnow
from .parsing import PARSER_VERSION, analyze_table, read_matrix

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MAX_SIZE = 50 * 1024 * 1024


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    return cleaned[:80] or "file"


@router.get("")
def list_uploads(_: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT up.id, up.filename, up.size, up.rows, up.columns, up.uploaded_at,
                   u.username AS uploader, u.display_name AS uploader_name
            FROM uploads up LEFT JOIN users u ON u.id = up.uploader_id
            ORDER BY up.id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return {"uploads": [dict(row) for row in rows]}


@router.post("")
async def upload(file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Пустой файл")
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "Файл больше 50 МБ")
    try:
        matrix = read_matrix(file.filename, content)
        structure = analyze_table(matrix)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not structure["columns"]:
        raise HTTPException(400, "В файле не найдено ни одной колонки")
    stored_name = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(4)}_{_safe_name(file.filename or 'file')}"
    )
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOADS_DIR / stored_name).write_bytes(content)
    conn = connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO uploads (filename, stored_name, size, rows, columns, sha256, uploader_id, uploaded_at, structure)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file.filename or stored_name,
                stored_name,
                len(content),
                int(structure["rows"]),
                int(len(structure["columns"])),
                hashlib.sha256(content).hexdigest(),
                user["id"],
                utcnow(),
                json.dumps(structure, ensure_ascii=False),
            ),
        )
        conn.commit()
        upload_id = cursor.lastrowid
    finally:
        conn.close()
    return {
        "id": upload_id,
        "filename": file.filename,
        "rows": int(structure["rows"]),
        "columns": int(len(structure["columns"])),
        "format": structure["format"],
    }


@router.get("/{upload_id}/preview")
def preview(upload_id: int, _: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT filename, stored_name, structure FROM uploads WHERE id = ?", (upload_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "Файл не найден")
    path = UPLOADS_DIR / row["stored_name"]
    if not path.exists():
        raise HTTPException(404, "Файл отсутствует в архиве")
    try:
        matrix = read_matrix(row["filename"], path.read_bytes())
        structure = None
        if row["structure"]:
            try:
                structure = json.loads(row["structure"])
            except (TypeError, ValueError):
                structure = None
        if not structure or structure.get("version") != PARSER_VERSION:
            structure = analyze_table(matrix)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    start = structure["data_start"]
    preview_rows = matrix[start : start + 50]
    return {"filename": row["filename"], "structure": structure, "preview": preview_rows}


@router.get("/{upload_id}/download")
def download(upload_id: int, _: dict = Depends(current_user)):
    conn = connect()
    try:
        row = conn.execute("SELECT filename, stored_name FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "Файл не найден")
    path = UPLOADS_DIR / row["stored_name"]
    if not path.exists():
        raise HTTPException(404, "Файл отсутствует в архиве")
    return FileResponse(path, filename=row["filename"])
