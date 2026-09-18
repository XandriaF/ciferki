from io import BytesIO
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .analysis.top2 import concept_metric_columns

FLAG_FILLS = {
    "выше": PatternFill("solid", fgColor="D8F0E2"),
    "ниже": PatternFill("solid", fgColor="FDEAEA"),
    "не значимо": PatternFill("solid", fgColor="F2F4F6"),
    "нет данных": PatternFill("solid", fgColor="FFFFFF"),
}


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
    sheet = wb.create_sheet("Частоты")
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


def _add_top2_sheet(wb: Workbook, df: pd.DataFrame, structure: dict, config: dict, result: dict) -> None:
    sheet = wb.create_sheet("Top2 и нормы")
    sheet["A1"] = "Top2% (доля «Скорее согласен(а)» и «Полностью согласен (а)») и 95% интервал Уилсона"
    sheet["A1"].font = Font(bold=True)
    sheet["K1"] = "z (95%)"
    sheet["L1"] = 1.959964

    headers = ["Концепт", "Метрика", "N", "Top2", "%", "Нижняя 95%", "Верхняя 95%", "Норма", "Вывод"]
    header_row = 3
    for i, title in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=i, value=title)
        cell.font = Font(bold=True)

    triples = concept_metric_columns(structure, result["metrics"], config.get("concept_map", {}))
    column_letters = {name: get_column_letter(list(df.columns).index(name) + 1) for _, _, name in triples}
    last_data_row = len(df) + 1

    row = header_row + 1
    for metric in result["metrics"]:
        metric_rows = [(concept, col) for concept, m, col in triples if m == metric]
        metric_start = row
        metric_end = row + len(metric_rows) - 1
        for concept_name, column_name in metric_rows:
            letter = column_letters[column_name]
            data_range = f"'Данные'!${letter}$2:${letter}${last_data_row}"
            sheet.cell(row=row, column=1, value=concept_name)
            sheet.cell(row=row, column=2, value=metric)
            sheet.cell(row=row, column=3, value=f"=COUNT({data_range})")
            sheet.cell(row=row, column=4, value=f'=COUNTIF({data_range},">=4")')
            sheet.cell(row=row, column=5, value=f'=IF(C{row}=0,"",D{row}/C{row})')
            wilson_base = f"(E{row}+$L$1^2/(2*C{row}))/(1+$L$1^2/C{row})"
            wilson_margin = f"$L$1*SQRT(E{row}*(1-E{row})/C{row}+$L$1^2/(4*C{row}^2))/(1+$L$1^2/C{row})"
            sheet.cell(row=row, column=6, value=f'=IF(OR(C{row}=0,E{row}=""),"",{wilson_base}-{wilson_margin})')
            sheet.cell(row=row, column=7, value=f'=IF(OR(C{row}=0,E{row}=""),"",{wilson_base}+{wilson_margin})')
            if result["norm_mode"] == "manual":
                norm_value = result["norms"].get(metric)
                sheet.cell(row=row, column=8, value=None if norm_value is None else norm_value / 100)
            else:
                sheet.cell(
                    row=row,
                    column=8,
                    value=f'=IF(COUNT(F{metric_start}:F{metric_end})=0,"",QUARTILE.INC(F{metric_start}:F{metric_end},3))',
                )
            sheet.cell(
                row=row,
                column=9,
                value=f'=IF(OR(F{row}="",H{row}=""),"",IF(F{row}>H{row},"выше",IF(G{row}<H{row},"ниже","не значимо")))',
            )
            for col in (5, 6, 7, 8):
                sheet.cell(row=row, column=col).number_format = "0.0%"
            flag = result["cells"].get(concept_name, {}).get(metric, {}).get("flag")
            sheet.cell(row=row, column=9).fill = FLAG_FILLS.get(flag, FLAG_FILLS["нет данных"])
            row += 1


def build_project_export(
    project_name: str,
    df: pd.DataFrame,
    structure: dict,
    history: list,
    column: Optional[str] = None,
    task: Optional[dict] = None,
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

    if task and task.get("task") == "top2_norms":
        _add_top2_sheet(wb, df, structure, task.get("config", {}), task.get("result", {}))

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
