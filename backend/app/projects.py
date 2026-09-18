import json
import math
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from .auth import current_user
from .db import UPLOADS_DIR, connect, utcnow
from .export import build_project_export
from .parsing import analyze_table, build_dataframe, read_matrix

router = APIRouter(prefix="/api/projects", tags=["projects"])

OP_LABELS = {
    "eq": "=",
    "ne": "≠",
    "in": "в списке",
    "gt": ">",
    "lt": "<",
    "between": "в диапазоне",
    "not_empty": "заполнено",
    "empty": "пусто",
}


class ProjectPayload(BaseModel):
    name: str
    upload_id: int
    settings: dict = {}


class StepPayload(BaseModel):
    type: str = "filter"
    params: dict = {}


def json_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _project(project_id: int) -> dict:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "Проект не найден")
    return dict(row)


def _steps(project_id: int) -> list:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM steps WHERE project_id = ? ORDER BY position, id", (project_id,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _base_dataframe(project: dict):
    conn = connect()
    try:
        upload = conn.execute("SELECT * FROM uploads WHERE id = ?", (project["upload_id"],)).fetchone()
    finally:
        conn.close()
    if upload is None:
        raise HTTPException(404, "Исходный файл не найден")
    path = UPLOADS_DIR / upload["stored_name"]
    if not path.exists():
        raise HTTPException(404, "Файл отсутствует в архиве")
    try:
        matrix = read_matrix(upload["filename"], path.read_bytes())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    structure = json.loads(upload["structure"]) if upload["structure"] else analyze_table(matrix)
    settings = json.loads(project["settings"] or "{}")
    return build_dataframe(matrix, structure, settings), structure


def _apply_filter(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    column = params.get("column")
    if column not in df.columns:
        raise HTTPException(400, f"Колонка «{column}» не найдена в данных")
    op = params.get("op", "eq")
    value = params.get("value")
    series = df[column]
    if op == "eq":
        mask = series.astype(str).str.strip() == str(value).strip()
    elif op == "ne":
        mask = series.astype(str).str.strip() != str(value).strip()
    elif op == "in":
        values = value if isinstance(value, list) else [value]
        mask = series.astype(str).str.strip().isin([str(v).strip() for v in values])
    elif op == "gt":
        mask = pd.to_numeric(series, errors="coerce") > float(value)
    elif op == "lt":
        mask = pd.to_numeric(series, errors="coerce") < float(value)
    elif op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise HTTPException(400, "Для диапазона нужно два значения")
        numeric = pd.to_numeric(series, errors="coerce")
        mask = (numeric >= float(value[0])) & (numeric <= float(value[1]))
    elif op == "not_empty":
        mask = series.notna() & (series.astype(str).str.strip() != "")
    elif op == "empty":
        mask = series.isna() | (series.astype(str).str.strip() == "")
    else:
        raise HTTPException(400, f"Неизвестная операция: {op}")
    return df[mask].reset_index(drop=True)


def _filter_summary(params: dict, before: int, after: int) -> str:
    column = params.get("column", "?")
    op = params.get("op", "eq")
    value = params.get("value")
    if op in ("not_empty", "empty"):
        text = f"{column}: {OP_LABELS[op]}"
    elif op == "between" and isinstance(value, list) and len(value) == 2:
        text = f"{column}: от {value[0]} до {value[1]}"
    elif op == "in" and isinstance(value, list):
        text = f"{column}: один из [{', '.join(str(v) for v in value[:5])}]"
    else:
        text = f"{column} {OP_LABELS.get(op, op)} {value}"
    return f"{text} — осталось {after} из {before}"


def _compute(project: dict):
    df, structure = _base_dataframe(project)
    history = []
    for step in _steps(project["id"]):
        before = int(len(df))
        params = json.loads(step["params"] or "{}")
        df = _apply_filter(df, params)
        history.append(
            {
                "id": step["id"],
                "position": step["position"],
                "type": step["type"],
                "params": params,
                "summary": step["summary"],
                "created_at": step["created_at"],
                "rows_before": before,
                "rows_after": int(len(df)),
            }
        )
    return df, structure, history


@router.get("")
def list_projects(_: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.created_at, p.updated_at,
                   up.filename, u.display_name AS author,
                   (SELECT COUNT(*) FROM steps s WHERE s.project_id = p.id) AS steps_count
            FROM projects p
            LEFT JOIN uploads up ON up.id = p.upload_id
            LEFT JOIN users u ON u.id = p.created_by
            ORDER BY p.id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return {"projects": [dict(row) for row in rows]}


@router.post("")
def create_project(payload: ProjectPayload, user: dict = Depends(current_user)) -> dict:
    name = payload.name.strip() or "Без названия"
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM uploads WHERE id = ?", (payload.upload_id,)).fetchone() is None:
            raise HTTPException(404, "Файл не найден")
        cursor = conn.execute(
            "INSERT INTO projects (name, upload_id, settings, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, payload.upload_id, json.dumps(payload.settings, ensure_ascii=False), user["id"], utcnow(), utcnow()),
        )
        conn.commit()
        project_id = cursor.lastrowid
    finally:
        conn.close()
    return {"id": project_id}


@router.get("/{project_id}")
def get_project(project_id: int, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, structure, history = _compute(project)
    conn = connect()
    try:
        upload = conn.execute(
            "SELECT filename, rows, uploaded_at FROM uploads WHERE id = ?", (project["upload_id"],)
        ).fetchone()
    finally:
        conn.close()
    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "settings": json.loads(project["settings"] or "{}"),
            "created_at": project["created_at"],
        },
        "upload": dict(upload) if upload else None,
        "structure": structure,
        "history": history,
        "rows": int(len(df)),
    }


@router.get("/{project_id}/data")
def project_data(project_id: int, limit: int = 200, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, _structure, _history = _compute(project)
    limit = max(1, min(limit, 1000))
    rows = [[json_value(value) for value in row] for row in df.head(limit).itertuples(index=False)]
    return {"columns": list(df.columns), "rows": rows, "total": int(len(df))}


@router.post("/{project_id}/steps/preview")
def preview_step(project_id: int, payload: StepPayload, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, _structure, _history = _compute(project)
    result = _apply_filter(df, payload.params)
    return {"rows_before": int(len(df)), "rows_after": int(len(result))}


@router.post("/{project_id}/steps")
def add_step(project_id: int, payload: StepPayload, user: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    if payload.type != "filter":
        raise HTTPException(400, "Пока поддерживаются только шаги-фильтры")
    df, _structure, history = _compute(project)
    before = int(len(df))
    result = _apply_filter(df, payload.params)
    after = int(len(result))
    summary = _filter_summary(payload.params, before, after)
    position = (history[-1]["position"] + 1) if history else 1
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO steps (project_id, position, type, params, summary, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, position, "filter", json.dumps(payload.params, ensure_ascii=False), summary, user["id"], utcnow()),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utcnow(), project_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "rows_before": before, "rows_after": after, "summary": summary}


@router.delete("/{project_id}/steps/{step_id}")
def delete_step(project_id: int, step_id: int, _: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT position FROM steps WHERE id = ? AND project_id = ?", (step_id, project_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Шаг не найден")
        conn.execute("DELETE FROM steps WHERE project_id = ? AND position >= ?", (project_id, row["position"]))
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utcnow(), project_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/{project_id}/values")
def column_values(project_id: int, column: str, limit: int = 50, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, _structure, _history = _compute(project)
    if column not in df.columns:
        raise HTTPException(400, "Колонка не найдена в данных")
    counts = df[column].value_counts(dropna=True).head(max(1, min(limit, 200)))
    return {"values": [{"value": json_value(v), "n": int(c)} for v, c in counts.items()]}


@router.get("/{project_id}/frequencies")
def frequencies(project_id: int, column: str, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, structure, _history = _compute(project)
    if column not in df.columns:
        raise HTTPException(400, "Колонка не найдена в данных")
    series = df[column]
    valid = int(series.notna().sum())
    rows = []
    for value, count in series.value_counts(dropna=True).items():
        rows.append(
            {
                "value": json_value(value),
                "n": int(count),
                "pct": round(int(count) / valid * 100, 1) if valid else 0.0,
            }
        )
    numeric = pd.to_numeric(series, errors="coerce")
    stats = None
    if int(numeric.notna().sum()) >= 2:
        stats = {
            "n": int(numeric.notna().sum()),
            "mean": round(float(numeric.mean()), 3),
            "median": round(float(numeric.median()), 3),
            "sd": round(float(numeric.std(ddof=1)), 3),
            "min": round(float(numeric.min()), 3),
            "max": round(float(numeric.max()), 3),
        }
    column_meta = next((c for c in structure["columns"] if c["name"] == column), None)
    return {
        "column": column,
        "column_meta": column_meta,
        "total_rows": int(len(df)),
        "valid": valid,
        "rows": rows,
        "stats": stats,
    }


@router.get("/{project_id}/export")
def export_project(project_id: int, column: Optional[str] = None, _: dict = Depends(current_user)):
    project = _project(project_id)
    df, structure, history = _compute(project)
    content = build_project_export(project["name"], df, structure, history, column)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ciferki_export.xlsx"'},
    )
