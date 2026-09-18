import json
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from .analysis.top2 import compute_top2
from .analysis.waves import compare_waves
from .auth import current_user
from .db import UPLOADS_DIR, connect, utcnow
from .export import build_project_export
from .parsing import PARSER_VERSION, analyze_table, build_dataframe, read_matrix

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
    upload_id: Optional[int] = None
    settings: dict = {}


class FilePayload(BaseModel):
    upload_id: int
    role: str = "main"
    key_column: str = ""
    wave_label: str = ""


class FileUpdatePayload(BaseModel):
    key_column: Optional[str] = None
    role: Optional[str] = None
    wave_label: Optional[str] = None


class ProjectUpdatePayload(BaseModel):
    name: Optional[str] = None
    settings: Optional[dict] = None


class StepPayload(BaseModel):
    type: str = "filter"
    params: dict = {}


class MatchPayload(BaseModel):
    main_file_id: int
    demo_file_id: int
    main_key: str
    demo_key: str
    only_complete: bool = True


class TaskPayload(BaseModel):
    task: str
    config: dict = {}
    save: bool = True


class ExportPayload(BaseModel):
    column: Optional[str] = None
    task: Optional[dict] = None


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


def _project_files(project_id: int) -> list:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT pf.id, pf.project_id, pf.upload_id, pf.role, pf.key_column, pf.wave_label, pf.created_at,
                   up.filename, up.rows, up.columns, up.uploaded_at, up.structure
            FROM project_files pf LEFT JOIN uploads up ON up.id = pf.upload_id
            WHERE pf.project_id = ? ORDER BY pf.id
            """,
            (project_id,),
        ).fetchall()
    finally:
        conn.close()
    files = []
    for row in rows:
        item = dict(row)
        try:
            item["structure"] = json.loads(item["structure"]) if item["structure"] else None
        except (TypeError, ValueError):
            item["structure"] = None
        files.append(item)
    return files


def _upload_row(upload_id: int):
    conn = connect()
    try:
        return conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    finally:
        conn.close()


def _upload_dataframe(upload_row, settings: dict):
    path = UPLOADS_DIR / upload_row["stored_name"]
    if not path.exists():
        raise HTTPException(404, "Файл отсутствует в архиве")
    try:
        matrix = read_matrix(upload_row["filename"], path.read_bytes())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    structure = None
    if upload_row["structure"]:
        try:
            structure = json.loads(upload_row["structure"])
        except (TypeError, ValueError):
            structure = None
    if not structure or structure.get("version") != PARSER_VERSION:
        structure = analyze_table(matrix)
    file_settings = (settings.get("files", {}) or {}).get(str(upload_row["id"]), {})
    types = file_settings.get("types", settings.get("types", {}))
    return build_dataframe(matrix, structure, {"types": types}), structure


def _main_file(project: dict):
    files = _project_files(project["id"])
    for file in files:
        if file["role"] == "main":
            return file
    if project.get("upload_id"):
        return {"id": None, "upload_id": project["upload_id"], "role": "main", "key_column": ""}
    return None


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


def _only_complete(df: pd.DataFrame) -> pd.DataFrame:
    status_column = next((c for c in df.columns if c.lower() == "status"), None)
    if not status_column:
        return df
    values = df[status_column].astype(str).str.strip().str.lower()
    mask = values.isin(["complete", "completed"])
    if not mask.any():
        return df
    return df[mask]


def _apply_match(df: pd.DataFrame, params: dict, project: dict, settings: dict) -> pd.DataFrame:
    main_key = params.get("main_key")
    if main_key not in df.columns:
        raise HTTPException(400, f"Колонка-ключ «{main_key}» не найдена в основном файле")
    demo_file = next((f for f in _project_files(project["id"]) if f["id"] == params.get("demo_file_id")), None)
    if demo_file is None:
        raise HTTPException(400, "Файл для мэтчинга не найден в проекте")
    demo_upload = _upload_row(demo_file["upload_id"])
    if demo_upload is None:
        raise HTTPException(404, "Файл для мэтчинга отсутствует в архиве")
    demo_df, _ = _upload_dataframe(demo_upload, settings)
    demo_key = params.get("demo_key") or demo_file["key_column"]
    if demo_key not in demo_df.columns:
        raise HTTPException(400, f"Колонка-ключ «{demo_key}» не найдена в файле мэтчинга")
    if params.get("only_complete"):
        demo_df = _only_complete(demo_df)
    keys = set(demo_df[demo_key].astype(str).str.strip().str.lower())
    mask = df[main_key].astype(str).str.strip().str.lower().isin(keys)
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


def _match_summary(params: dict, before: int, after: int, project: dict) -> str:
    demo_file = next((f for f in _project_files(project["id"]) if f["id"] == params.get("demo_file_id")), None)
    filename = demo_file["filename"] if demo_file else "?"
    return f"Мэтчинг с «{filename}» по «{params.get('demo_key')}» — осталось {after} из {before}"


def _compute(project: dict):
    settings = json.loads(project["settings"] or "{}")
    main = _main_file(project)
    if main is None:
        raise HTTPException(400, "К проекту ещё не привязан основной файл")
    upload = _upload_row(main["upload_id"])
    if upload is None:
        raise HTTPException(404, "Основной файл не найден в архиве")
    df, structure = _upload_dataframe(upload, settings)
    history = []
    for step in _steps(project["id"]):
        before = int(len(df))
        params = json.loads(step["params"] or "{}")
        if step["type"] == "match":
            df = _apply_match(df, params, project, settings)
        elif step["type"] == "filter":
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


def _previous_wave_frame(project: dict, settings: dict):
    prev = next((f for f in _project_files(project["id"]) if f["role"] == "previous_wave"), None)
    if prev is None:
        raise HTTPException(400, "Привяжите файл предыдущей волны (роль «Предыдущая волна»)")
    upload = _upload_row(prev["upload_id"])
    if upload is None:
        raise HTTPException(404, "Файл предыдущей волны отсутствует в архиве")
    return _upload_dataframe(upload, settings)


def _run_wave_compare(df: pd.DataFrame, structure: dict, project: dict, config: dict) -> dict:
    settings = json.loads(project["settings"] or "{}")
    prev_df, prev_structure = _previous_wave_frame(project, settings)
    try:
        return compare_waves(df, structure, prev_df, prev_structure, config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _pool_for(project: dict, settings: dict, config: dict) -> dict:
    prev = next((f for f in _project_files(project["id"]) if f["role"] == "previous_wave"), None)
    if prev is None:
        raise HTTPException(400, "Для нормы по пулу волн привяжите файл предыдущей волны (роль «Предыдущая волна»)")
    upload = _upload_row(prev["upload_id"])
    if upload is None:
        raise HTTPException(404, "Файл предыдущей волны отсутствует в архиве")
    prev_df, prev_structure = _upload_dataframe(upload, settings)
    prev_result = compute_top2(
        prev_df,
        prev_structure,
        {
            "concept_map": config.get("concept_map", {}),
            "metrics": config.get("metrics", []),
            "norm_mode": "q3",
        },
    )
    pool: dict = {}
    for concept_cells in prev_result["cells"].values():
        for metric, cell in concept_cells.items():
            if cell["pct"] is not None:
                pool.setdefault(metric, []).append(cell["pct"])
    return pool


@router.get("")
def list_projects(_: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.created_at, p.updated_at,
                   u.display_name AS author,
                   (SELECT COUNT(*) FROM steps s WHERE s.project_id = p.id) AS steps_count,
                   (SELECT COUNT(*) FROM project_files f WHERE f.project_id = p.id) AS files_count,
                   (SELECT up.filename FROM project_files f LEFT JOIN uploads up ON up.id = f.upload_id
                     WHERE f.project_id = p.id AND f.role = 'main' ORDER BY f.id LIMIT 1) AS filename
            FROM projects p
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
        cursor = conn.execute(
            "INSERT INTO projects (name, upload_id, settings, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, payload.upload_id or 0, json.dumps(payload.settings, ensure_ascii=False), user["id"], utcnow(), utcnow()),
        )
        project_id = cursor.lastrowid
        if payload.upload_id:
            conn.execute(
                "INSERT INTO project_files (project_id, upload_id, role, key_column, wave_label, created_at) VALUES (?, ?, 'main', '', '', ?)",
                (project_id, payload.upload_id, utcnow()),
            )
        conn.commit()
    finally:
        conn.close()
    return {"id": project_id}


@router.patch("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdatePayload, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    name = payload.name.strip() if payload.name and payload.name.strip() else project["name"]
    settings = (
        json.dumps(payload.settings, ensure_ascii=False) if payload.settings is not None else project["settings"]
    )
    conn = connect()
    try:
        conn.execute(
            "UPDATE projects SET name = ?, settings = ?, updated_at = ? WHERE id = ?",
            (name, settings, utcnow(), project_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name}


@router.delete("/{project_id}")
def delete_project(project_id: int, _: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        conn.execute("DELETE FROM steps WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/{project_id}")
def get_project(project_id: int, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    files = _project_files(project_id)
    main = _main_file(project)
    if main is None:
        return {
            "project": {
                "id": project["id"],
                "name": project["name"],
                "settings": json.loads(project["settings"] or "{}"),
                "created_at": project["created_at"],
            },
            "files": files,
            "main_structure": None,
            "history": [],
            "rows": 0,
        }
    df, structure, history = _compute(project)
    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "settings": json.loads(project["settings"] or "{}"),
            "created_at": project["created_at"],
        },
        "files": files,
        "main_structure": structure,
        "history": history,
        "rows": int(len(df)),
    }


@router.post("/{project_id}/files")
def add_file(project_id: int, payload: FilePayload, _: dict = Depends(current_user)) -> dict:
    _project(project_id)
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM uploads WHERE id = ?", (payload.upload_id,)).fetchone() is None:
            raise HTTPException(404, "Файл не найден в архиве")
        cursor = conn.execute(
            "INSERT INTO project_files (project_id, upload_id, role, key_column, wave_label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, payload.upload_id, payload.role, payload.key_column, payload.wave_label, utcnow()),
        )
        conn.commit()
        file_id = cursor.lastrowid
    finally:
        conn.close()
    return {"id": file_id}


@router.patch("/{project_id}/files/{file_id}")
def update_file(project_id: int, file_id: int, payload: FileUpdatePayload, _: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM project_files WHERE id = ? AND project_id = ?", (file_id, project_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Файл не найден")
        key_column = payload.key_column if payload.key_column is not None else row["key_column"]
        role = payload.role if payload.role is not None else row["role"]
        wave_label = payload.wave_label if payload.wave_label is not None else row["wave_label"]
        conn.execute(
            "UPDATE project_files SET key_column = ?, role = ?, wave_label = ? WHERE id = ?",
            (key_column, role, wave_label, file_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/{project_id}/files/{file_id}")
def delete_file(project_id: int, file_id: int, _: dict = Depends(current_user)) -> dict:
    conn = connect()
    try:
        conn.execute("DELETE FROM project_files WHERE id = ? AND project_id = ?", (file_id, project_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{project_id}/match/preview")
def match_preview(project_id: int, payload: MatchPayload, _: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    settings = json.loads(project["settings"] or "{}")
    files = _project_files(project_id)
    main_file = next((f for f in files if f["id"] == payload.main_file_id), None)
    demo_file = next((f for f in files if f["id"] == payload.demo_file_id), None)
    if main_file is None or demo_file is None:
        raise HTTPException(404, "Файлы не найдены в проекте")
    main_upload = _upload_row(main_file["upload_id"])
    demo_upload = _upload_row(demo_file["upload_id"])
    if main_upload is None or demo_upload is None:
        raise HTTPException(404, "Файлы отсутствуют в архиве")
    main_df, _ = _upload_dataframe(main_upload, settings)
    demo_df, _ = _upload_dataframe(demo_upload, settings)
    if payload.main_key not in main_df.columns:
        raise HTTPException(400, f"Колонка «{payload.main_key}» не найдена в основном файле")
    if payload.demo_key not in demo_df.columns:
        raise HTTPException(400, f"Колонка «{payload.demo_key}» не найдена в файле мэтчинга")
    if payload.only_complete:
        demo_df = _only_complete(demo_df)
    main_set = set(main_df[payload.main_key].astype(str).str.strip().str.lower())
    demo_set = set(demo_df[payload.demo_key].astype(str).str.strip().str.lower())
    return {
        "main_total": int(len(main_df)),
        "demo_total": int(len(demo_df)),
        "main_unique": len(main_set),
        "demo_unique": len(demo_set),
        "matched": len(main_set & demo_set),
        "only_main": len(main_set - demo_set),
        "only_demo": len(demo_set - main_set),
        "only_main_sample": sorted(main_set - demo_set)[:10],
        "only_demo_sample": sorted(demo_set - main_set)[:10],
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
    settings = json.loads(project["settings"] or "{}")
    df, _structure, history = _compute(project)
    before = int(len(df))
    if payload.type == "filter":
        result = _apply_filter(df, payload.params)
        summary = _filter_summary(payload.params, before, int(len(result)))
    elif payload.type == "match":
        result = _apply_match(df, payload.params, project, settings)
        summary = _match_summary(payload.params, before, int(len(result)), project)
    else:
        raise HTTPException(400, "Неизвестный тип шага")
    after = int(len(result))
    position = (history[-1]["position"] + 1) if history else 1
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO steps (project_id, position, type, params, summary, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, position, payload.type, json.dumps(payload.params, ensure_ascii=False), summary, user["id"], utcnow()),
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


@router.post("/{project_id}/tasks/run")
def run_task(project_id: int, payload: TaskPayload, user: dict = Depends(current_user)) -> dict:
    project = _project(project_id)
    df, structure, history = _compute(project)
    if payload.task == "top2_norms":
        pool = None
        if payload.config.get("norm_mode") in ("pool_q3", "pool_median"):
            settings = json.loads(project["settings"] or "{}")
            pool = _pool_for(project, settings, payload.config)
        result = compute_top2(df, structure, payload.config, pool)
        summary = f"Top2 и нормы: {len(result['concepts'])} концептов × {len(result['metrics'])} метрик"
    elif payload.task == "wave_compare":
        result = _run_wave_compare(df, structure, project, payload.config)
        summary = (
            f"Сравнение волн ({result['mode']}): "
            f"{len(result['concepts'])} концептов × {len(result['metrics'])} метрик"
        )
    else:
        raise HTTPException(400, "Неизвестная задача")
    result.pop("_frames", None)
    if payload.save:
        position = (history[-1]["position"] + 1) if history else 1
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO steps (project_id, position, type, params, summary, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    position,
                    "task",
                    json.dumps({"task": payload.task, "config": payload.config}, ensure_ascii=False),
                    summary,
                    user["id"],
                    utcnow(),
                ),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utcnow(), project_id))
            conn.commit()
        finally:
            conn.close()
    return {"result": result, "summary": summary, "rows": int(len(df))}


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


@router.post("/{project_id}/export")
def export_project(project_id: int, payload: ExportPayload, _: dict = Depends(current_user)):
    project = _project(project_id)
    df, structure, history = _compute(project)
    task = None
    if payload.task and payload.task.get("task") == "top2_norms":
        config = payload.task.get("config", {})
        pool = None
        if config.get("norm_mode") in ("pool_q3", "pool_median"):
            settings = json.loads(project["settings"] or "{}")
            pool = _pool_for(project, settings, config)
        result = compute_top2(df, structure, config, pool)
        task = {"task": "top2_norms", "config": config, "result": result}
    elif payload.task and payload.task.get("task") == "wave_compare":
        config = payload.task.get("config", {})
        result = _run_wave_compare(df, structure, project, config)
        task = {"task": "wave_compare", "config": config, "result": result, "frames": result.pop("_frames", {})}
    content = build_project_export(project["name"], df, structure, history, payload.column, task)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ciferki_export.xlsx"'},
    )
