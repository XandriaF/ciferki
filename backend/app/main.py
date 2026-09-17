import os

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from .analysis import ttest
from .auth import current_user, router as auth_router
from .db import connect, init_db, utcnow
from .security import hash_password
from .tables import read_table
from .uploads import router as uploads_router
from .users import router as users_router

app = FastAPI(title="Циферки", version="0.2.0")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(uploads_router)


def _seed_admin() -> None:
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin").strip().lower() or "admin"
    conn = connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
                (username, "Администратор", hash_password(password), utcnow()),
            )
            conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    _seed_admin()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/ttest")
async def run_ttest(
    file: UploadFile = File(...),
    value_col: str = Form(...),
    group_col: str = Form(...),
    alpha: float = Form(0.05),
    _: dict = Depends(current_user),
) -> dict:
    df = read_table(file.filename, await file.read())
    try:
        return ttest.run(df, value_col, group_col, alpha)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
