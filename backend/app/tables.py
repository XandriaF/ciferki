import io
from typing import Optional

import pandas as pd
from fastapi import HTTPException


def read_table(filename: Optional[str], content: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".xls"):
        raise HTTPException(400, "Формат .xls не поддерживается — сохраните файл как .xlsx или .csv")
    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(content))
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            last_error = exc
    raise HTTPException(400, "Не удалось прочитать файл. Поддерживаются CSV и Excel (.xlsx)") from last_error
