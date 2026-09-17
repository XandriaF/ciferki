import io
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analysis import ttest

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Циферки", version="0.1.0")


def read_table(filename: Optional[str], content: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".xls"):
        raise HTTPException(400, "Формат .xls не поддерживается - сохраните файл как .xlsx или .csv")
    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(content))
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            last_error = exc
    raise HTTPException(400, "Не удалось прочитать файл. Поддерживаются CSV и Excel (.xlsx)") from last_error


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/columns")
async def columns(file: UploadFile = File(...)) -> dict:
    df = read_table(file.filename, await file.read())
    return {
        "rows": int(len(df)),
        "columns": [{"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
        "preview": df.head(5).astype(str).to_dict(orient="records"),
    }


@app.post("/api/ttest")
async def run_ttest(
    file: UploadFile = File(...),
    value_col: str = Form(...),
    group_col: str = Form(...),
    alpha: float = Form(0.05),
) -> dict:
    df = read_table(file.filename, await file.read())
    try:
        return ttest.run(df, value_col, group_col, alpha)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
