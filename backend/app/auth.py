import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

from .db import connect, utcnow
from .security import hash_password, verify_password

SESSION_COOKIE = "ciferki_session"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


class PasswordPayload(BaseModel):
    current_password: str
    new_password: str


def _session_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()


def current_user(session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    if not session:
        raise HTTPException(401, "Требуется вход")
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.display_name, u.is_admin
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (session, utcnow()),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(401, "Сессия истекла, войдите заново")
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "is_admin": bool(row["is_admin"])}


def admin_user(user: dict = Depends(current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(403, "Доступно только администратору")
    return user


@router.post("/login")
def login(payload: LoginPayload, response: Response) -> dict:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (payload.username.strip().lower(),)).fetchone()
        if row is None or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], utcnow(), _session_expiry()),
        )
        conn.commit()
        user = {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "is_admin": bool(row["is_admin"])}
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_DAYS * 86400)
    return {"user": user}


@router.post("/logout")
def logout(response: Response, session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    if session:
        conn = connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (session,))
            conn.commit()
        finally:
            conn.close()
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}


@router.post("/password")
def change_password(payload: PasswordPayload, user: dict = Depends(current_user)) -> dict:
    if len(payload.new_password) < 6:
        raise HTTPException(400, "Пароль должен быть не короче 6 символов")
    conn = connect()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row is None or not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(400, "Текущий пароль указан неверно")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(payload.new_password), user["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
