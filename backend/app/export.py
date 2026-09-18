from io import BytesIO
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def _safe_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _add_frequencies_sheet(wb: Workbook, df: pd.DataFrame, column: str, structure: dict) -> None:
    sheet = wb.create_sheet("Результат")
    letter = get_column_letter(list(df.columns).index(column) + 1)
    data_range = f"'Данные'!${letter}$2:${letter}${len(df) + 1}"
    column_meta = next((c for c in structure["columns"] if c["name"] == column), None)
    title = column
    if column_meta and column_meta.get("label"):
        title = f"{column} — {column_meta['label']}"
    sheet.append([title])
    sheet["A1"].font = Font(bold=True)
    sheet.append([])
    sheet.append(["Значение", "N", "% от валидных"])
    for cell in sheet[3]:
        cell.font = Font(bold=True)

    counts = df[column].value_counts(dropna=True)
    start_row = 4
    for i, value in enumerate(counts.index):
        row = start_row + i
        sheet.append([_safe_value(value)])
        sheet.cell(row=row, column=2, value=f"=COUNTIF({data_range},A{row})")
        total_row = start_row + len(counts)
        sheet.cell(row=row, column=3, value=f"=IF($B${total_row}=0,0,B{row}/$B${total_row})")
        sheet.cell(row=row, column=3).number_format = "0.0%"
    total_row = start_row + len(counts)
    sheet.cell(row=total_row, column=1, value="Итого валидных").font = Font(bold=True)
    sheet.cell(row=total_row, column=2, value=f"=SUM(B{start_row}:B{total_row - 1})").font = Font(bold=True)

    numeric = pd.to_numeric(df[column], errors="coerce")
    if int(numeric.notna().sum()) >= 2:
        r = total_row + 2
        sheet.cell(row=r, column=1, value="Числовые показатели").font = Font(bold=True)
        metrics = [
            ("Среднее", f"=AVERAGE({data_range})"),
            ("Медиана", f"=MEDIAN({data_range})"),
            ("Стандартное отклонение", f"=STDEV.S({data_range})"),
            ("Минимум", f"=MIN({data_range})"),
            ("Максимум", f"=MAX({data_range})"),
            ("N (числовых)", f"=COUNT({data_range})"),
        ]
        for j, (label, formula) in enumerate(metrics, start=1):
            sheet.cell(row=r + j, column=1, value=label)
            sheet.cell(row=r + j, column=2, value=formula)


def build_project_export(
    project_name: str,
    df: pd.DataFrame,
    structure: dict,
    history: list,
    column: Optional[str] = None,
) -> bytes:
    wb = Workbook()
    data_sheet = wb.active
    data_sheet.title = "Данные"
    data_sheet.append(list(df.columns))
    for cell in data_sheet[1]:
        cell.font = Font(bold=True)
    for row in df.itertuples(index=False):
        data_sheet.append([_safe_value(value) for value in row])
    data_sheet.freeze_panes = "A2"

    steps_sheet = wb.create_sheet("Шаги")
    steps_sheet.append(["№", "Действие", "Строк до", "Строк после", "Когда"])
    for cell in steps_sheet[1]:
        cell.font = Font(bold=True)
    if history:
        for i, step in enumerate(history, start=1):
            steps_sheet.append([i, step["summary"], step["rows_before"], step["rows_after"], step["created_at"]])
    else:
        steps_sheet.append([0, "Исходные данные (без шагов обработки)", len(df), len(df), ""])
    steps_sheet.append([])
    steps_sheet.append(["Проект", project_name])

    if column and column in df.columns:
        _add_frequencies_sheet(wb, df, column, structure)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
