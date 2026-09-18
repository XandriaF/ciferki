import re
from typing import Optional

SERVICE_COLUMNS = {
    "№ записи",
    "id",
    "ac",
    "starttime",
    "endtime",
    "surveytime",
    "status",
    "Answer ID",
    "URL Tag: ID",
    "Device",
    "Device OS",
    "Browser",
    "Window size",
    "Source",
    "Status",
    "Reward",
    "Completion time, s",
    "Answer Date",
    "Shuffle order",
}

AGREEMENT_SCALE = {
    "Полностью согласен (а)": 5,
    "Скорее согласен(а)": 4,
    "Ни то, ни другое": 3,
    "Скорее НЕ согласен(а)": 2,
    "Совершенно НЕ согласен(а)": 1,
    "Полностью согласен(на)": 5,
    "Скорее согласен(на)": 4,
    "Ни согласен(на), ни не согласен(на)": 3,
    "Скорее НЕ согласен(на)": 2,
    "Совершенно НЕ согласен(на)": 1,
    "Полностью согласен(а)": 5,
    "Скорее согласен(а)": 4,
    "Ни согласен(а), ни не согласен(а)": 3,
    "Скорее НЕ согласен(а)": 2,
    "Совершенно НЕ согласен(а)": 1,
    "Точно НЕ согласен(на)": 1,
}

PRO_ME_SCALE = {
    "Это точно НЕ обо мне": 1,
    "Это скорее НЕ обо мне": 2,
    "Это скорее обо мне": 3,
    "Это точно обо мне": 4,
}

PRO_ME3_SCALE = {
    "Нет, это не про меня": 1,
    "Это частично про меня": 2,
    "Да, это точно про меня": 3,
}

MISSING_VALUES = {
    "Затрудняюсь ответить",
    "Затрудняюсь ответить(ась)",
    "Не знаю",
    "Нет ответа",
    "Отказ от ответа",
}

TOP2_MIN_BY_SCALE = {"agreement5": 4, "pro_me4": 3, "pro_me3": 2}

PARSER_VERSION = 3

MATRIX_RE = re.compile(r"^(\d+)\.\s*Matrix[,，]?\s*(.*)$")
BASE_MATRIX_RE = re.compile(r"^[Qq](\d+)_r(\d+)$")
CHOICE_RE = re.compile(r"^(\d+)\.\s*Choice")
QUESTION_RE = re.compile(r"^\d+\.\s*(Choice|Matrix)")


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except (ValueError, AttributeError):
        return False


def _sample_values(matrix: list, index: int, data_start: int, limit: int = 30) -> list:
    values = []
    for row in matrix[data_start : data_start + limit * 3]:
        if index < len(row):
            value = (row[index] or "").strip()
            if value:
                values.append(value)
        if len(values) >= limit:
            break
    return values


def _matrix_scale(matrix: list, index: int, data_start: int) -> str:
    values = _sample_values(matrix, index, data_start, 30)
    if not values:
        return "numeric"
    if all(value in AGREEMENT_SCALE or value in MISSING_VALUES for value in values):
        return "agreement5"
    if all(value in PRO_ME_SCALE or value in MISSING_VALUES for value in values):
        return "pro_me4"
    if all(value in PRO_ME3_SCALE or value in MISSING_VALUES for value in values):
        return "pro_me3"
    return "numeric"


def find_header_row(matrix: list, max_scan: int = 12) -> int:
    best_score, best_row = -1, 0
    for i, row in enumerate(matrix[:max_scan]):
        score = 0
        for cell in row:
            name = (cell or "").strip()
            if not name:
                continue
            if name in SERVICE_COLUMNS:
                score += 4
            if name.startswith("URL Tag:"):
                score += 4
            if QUESTION_RE.match(name):
                score += 2
            if re.match(r"^[Qq]\w+$", name) and len(name) < 40:
                score += 1
        if score > best_score:
            best_score, best_row = score, i
    return best_row if best_score >= 4 else 0


def detect_format(headers: list) -> str:
    names = [(h or "").strip() for h in headers]
    if any(QUESTION_RE.match(n) for n in names):
        return "report"
    lowered = {n.lower() for n in names}
    if "ac" in lowered and "id" in lowered:
        return "base"
    return "generic"


def find_data_start(matrix: list, header_row: int, headers: list) -> int:
    id_index: Optional[int] = None
    for target in ("id", "url tag: id", "ac", "answer id"):
        for i, header in enumerate(headers):
            if (header or "").strip().lower() == target:
                id_index = i
                break
        if id_index is not None:
            break
    if id_index is None:
        id_index = 0
    threshold = max(3, len(headers) // 10)
    for r in range(header_row + 1, min(header_row + 12, len(matrix))):
        row = matrix[r]
        value = (row[id_index] or "").strip() if id_index < len(row) else ""
        nonempty = sum(1 for c in row if (c or "").strip())
        if value and " " not in value and nonempty >= threshold:
            return r
    return header_row + 1


def classify_columns(headers: list, labels: Optional[list], matrix: list, data_start: int) -> list:
    columns = []
    for i, raw_name in enumerate(headers):
        name = (raw_name or "").strip()
        label = (labels[i].strip() if labels and i < len(labels) else "")
        column = {
            "index": i,
            "name": name,
            "label": label,
            "type": "categorical",
            "group": None,
            "option": None,
            "scale": None,
        }
        if name in SERVICE_COLUMNS or name.startswith("URL Tag:"):
            column["type"] = "service"
            columns.append(column)
            continue
        matrix_match = MATRIX_RE.match(name)
        if matrix_match:
            column["type"] = "matrix"
            column["group"] = f"Q{matrix_match.group(1)}"
            column["option"] = matrix_match.group(2).strip()
            column["scale"] = _matrix_scale(matrix, i, data_start)
            columns.append(column)
            continue
        base_match = BASE_MATRIX_RE.match(name)
        if base_match:
            option = label
            if " - " in option:
                option = option.rsplit(" - ", 1)[1]
            column["type"] = "matrix"
            column["group"] = f"Q{base_match.group(1)}"
            column["option"] = option.strip() or name
            column["scale"] = _matrix_scale(matrix, i, data_start)
            columns.append(column)
            continue
        if "Choice" in name:
            question = CHOICE_RE.match(name)
            column["group"] = f"Q{question.group(1)}" if question else None
            if "Other (text)" in name or ", other answers" in name:
                column["type"] = "text"
            else:
                column["type"] = "choice"
                parts = name.split(":")
                column["option"] = parts[-1].strip() if len(parts) > 1 else name
            columns.append(column)
            continue
        sample = _sample_values(matrix, i, data_start, 20)
        if sample and all(_is_number(v) for v in sample):
            column["type"] = "numeric"
        elif sample and all(v.upper() in ("TRUE", "FALSE") for v in sample):
            column["type"] = "choice"
        else:
            column["type"] = "categorical"
        columns.append(column)
    return columns


def analyze_table(matrix: list) -> dict:
    header_row = find_header_row(matrix)
    headers = [(c or "").strip() for c in matrix[header_row]] if header_row < len(matrix) else []
    data_start = find_data_start(matrix, header_row, headers)
    labels = matrix[header_row + 1] if data_start > header_row + 1 else None
    columns = classify_columns(headers, labels, matrix, data_start)
    return {
        "version": PARSER_VERSION,
        "format": detect_format(headers),
        "header_row": header_row,
        "data_start": data_start,
        "columns": columns,
        "rows": max(0, len(matrix) - data_start),
    }


def read_matrix(filename: Optional[str], content: bytes) -> list:
    import io

    import pandas as pd

    name = (filename or "").lower()
    if name.endswith(".xls"):
        raise ValueError("Формат .xls не поддерживается — сохраните файл как .xlsx или .csv")
    if name.endswith(".xlsx"):
        frame = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
    else:
        frame = None
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                frame = pd.read_csv(
                    io.BytesIO(content), header=None, dtype=str, sep=None, engine="python", encoding=encoding
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
                last_error = exc
        if frame is None:
            raise ValueError("Не удалось прочитать файл. Поддерживаются CSV и Excel (.xlsx)") from last_error
    frame = frame.fillna("")
    return [[str(value) for value in row] for row in frame.values.tolist()]


def dataframe_columns(structure: dict) -> list:
    headers = []
    seen: dict = {}
    for column in structure["columns"]:
        name = column["name"] or f"col_{column['index']}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        headers.append(name)
    return headers


def build_dataframe(matrix: list, structure: dict, settings: Optional[dict] = None):
    import pandas as pd

    settings = settings or {}
    columns = structure["columns"]
    headers = dataframe_columns(structure)
    rows = matrix[structure["data_start"] :]
    df = pd.DataFrame(rows, columns=headers)
    df = df.loc[:, (df != "").any(axis=0)]
    df = df[df.apply(lambda row: any(str(value).strip() for value in row), axis=1)]
    scale = settings.get("scale", AGREEMENT_SCALE)
    type_overrides = settings.get("types", {})
    for column in columns:
        name = headers[column["index"]]
        if name not in df.columns:
            continue
        column_type = type_overrides.get(column["name"], column["type"])
        if column_type == "matrix":
            if column.get("scale") == "agreement5":
                mapping = scale
            elif column.get("scale") == "pro_me4":
                mapping = PRO_ME_SCALE
            elif column.get("scale") == "pro_me3":
                mapping = PRO_ME3_SCALE
            else:
                mapping = None
            if mapping:
                df[name] = df[name].map(lambda value: mapping.get(value.strip()))
                df[name] = pd.to_numeric(df[name], errors="coerce")
        elif column_type == "choice":
            df[name] = df[name].map(
                lambda value: True
                if value.strip().upper() == "TRUE"
                else (False if value.strip().upper() == "FALSE" else None)
            )
        elif column_type == "numeric":
            df[name] = pd.to_numeric(df[name].str.replace(",", ".", regex=False), errors="coerce")
    return df.reset_index(drop=True)
