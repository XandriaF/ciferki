from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import admin_user
from .db import connect, utcnow
from .security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


class NewUser(BaseModel):
    username: str
    display_name: str = ""
    password: str
    is_admin: bool = False


@router.get("")
def list_users(_: dict = Depends(admin_user)) -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, is_admin, created_at FROM users ORDER BY username"
        ).fetchall()
    finally:
        conn.close()
    return {"users": [{**dict(row), "is_admin": bool(row["is_admin"])} for row in rows]}


@router.post("")
def create_user(payload: NewUser, _: dict = Depends(admin_user)) -> dict:
    username = payload.username.strip().lower()
    if not username or len(payload.password) < 6:
        raise HTTPException(400, "Укажите логин и пароль (минимум 6 символов)")
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(400, "Такой логин уже занят")
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, payload.display_name.strip() or username, hash_password(payload.password), int(payload.is_admin), utcnow()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class RenameUser(BaseModel):
    display_name: str


@router.patch("/{user_id}")
def rename_user(user_id: int, payload: RenameUser, _: dict = Depends(admin_user)) -> dict:
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(400, "Имя не может быть пустым")
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            raise HTTPException(404, "Пользователь не найден")
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/{user_id}")
def delete_user(user_id: int, admin: dict = Depends(admin_user)) -> dict:
    if user_id == admin["id"]:
        raise HTTPException(400, "Нельзя удалить самого себя")
    conn = connect()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
