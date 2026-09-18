import numpy as np
import pandas as pd
from scipy import stats

from .top2 import concept_metric_columns, top2_min_for


def _flag(lower, upper) -> str:
    if lower is None or upper is None:
        return "нет данных"
    if lower > 0:
        return "выше"
    if upper < 0:
        return "ниже"
    return "не значимо"


def _independent_stats(a: pd.Series, b: pd.Series, alpha: float) -> dict:
    n1, n2 = int(len(a)), int(len(b))
    if n1 == 0 or n2 == 0:
        return {"n1": n1, "n2": n2, "p1": None, "p2": None, "diff": None, "lower": None, "upper": None, "p_value": None, "flag": "нет данных"}
    p1 = float(a.mean())
    p2 = float(b.mean())
    diff = p1 - p2
    se = float(np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2))
    z_crit = float(stats.norm.ppf(1 - alpha / 2))
    if se > 0:
        z = diff / se
        p_value = float(2 * (1 - stats.norm.cdf(abs(z))))
        lower, upper = diff - z_crit * se, diff + z_crit * se
    else:
        p_value = 1.0
        lower = upper = diff
    return {
        "n1": n1,
        "n2": n2,
        "p1": round(p1 * 100, 1),
        "p2": round(p2 * 100, 1),
        "diff": round(diff * 100, 1),
        "lower": round(lower * 100, 1),
        "upper": round(upper * 100, 1),
        "p_value": round(p_value, 4),
        "flag": _flag(lower, upper),
    }


def _paired_stats(a: pd.Series, b: pd.Series, alpha: float) -> dict:
    n = int(len(a))
    if n == 0:
        return {"n1": 0, "n2": 0, "p1": None, "p2": None, "diff": None, "lower": None, "upper": None, "p_value": None, "flag": "нет данных", "b": 0, "c": 0}
    a = a.astype(bool)
    b = b.astype(bool)
    p1 = float(a.mean())
    p2 = float(b.mean())
    diff = p1 - p2
    b_count = int((a & ~b).sum())
    c_count = int((~a & b).sum())
    discordant = b_count + c_count
    if discordant > 0:
        chi2 = (abs(b_count - c_count) - 1) ** 2 / discordant
        p_value = float(1 - stats.chi2.cdf(max(chi2, 0.0), 1))
    else:
        p_value = 1.0
    se = float(np.sqrt(max(discordant - (b_count - c_count) ** 2 / n, 0.0)) / n)
    z_crit = float(stats.norm.ppf(1 - alpha / 2))
    if se > 0:
        lower, upper = diff - z_crit * se, diff + z_crit * se
    else:
        lower = upper = diff
    return {
        "n1": n,
        "n2": n,
        "p1": round(p1 * 100, 1),
        "p2": round(p2 * 100, 1),
        "diff": round(diff * 100, 1),
        "lower": round(lower * 100, 1),
        "upper": round(upper * 100, 1),
        "p_value": round(p_value, 4),
        "flag": _flag(lower, upper),
        "b": b_count,
        "c": c_count,
    }


def compare_waves(main_df: pd.DataFrame, main_structure: dict, prev_df: pd.DataFrame, prev_structure: dict, config: dict) -> dict:
    mode = config.get("mode", "independent")
    if mode not in ("independent", "panel", "panel_lag"):
        raise ValueError("Неизвестный режим сравнения волн")
    alpha = float(config.get("alpha", 0.05))
    concept_map = config.get("concept_map", {})
    prev_concept_map = config.get("prev_concept_map") or concept_map
    metric_map = config.get("metric_map", {})
    metrics = config.get("metrics") or list(metric_map.keys())
    warnings: list = []

    main_triples = concept_metric_columns(main_structure, metrics, concept_map)
    prev_by_group: dict = {}
    for column in prev_structure["columns"]:
        if column["type"] == "matrix" and column.get("group") in prev_concept_map:
            prev_by_group.setdefault(column["group"], {})[column.get("option")] = column["name"]
    prev_triples = []
    for group, concept_name in prev_concept_map.items():
        for metric in metrics:
            prev_metric = metric_map.get(metric, metric)
            column_name = prev_by_group.get(group, {}).get(prev_metric)
            if column_name:
                prev_triples.append((concept_name, metric, column_name))

    main_lookup = {(concept, metric): column for concept, metric, column in main_triples}
    prev_lookup = {(concept, metric): column for concept, metric, column in prev_triples}
    pairs = [(concept, metric) for (concept, metric) in main_lookup if (concept, metric) in prev_lookup]
    missing_main = [f"{concept}: {metric}" for (concept, metric) in prev_lookup if (concept, metric) not in main_lookup]
    missing_prev = [f"{concept}: {metric}" for (concept, metric) in main_lookup if (concept, metric) not in prev_lookup]
    if missing_prev:
        warnings.append("Нет в прошлой волне: " + "; ".join(missing_prev[:5]) + ("…" if len(missing_prev) > 5 else ""))
    if missing_main:
        warnings.append("Нет в текущей волне: " + "; ".join(missing_main[:5]) + ("…" if len(missing_main) > 5 else ""))

    frames: dict = {}
    lag_info = None
    matched_total = None
    matched_used = None
    duplicate_keys = 0

    if mode == "independent":
        cells = {}
        for concept, metric in pairs:
            main_column = main_lookup[(concept, metric)]
            prev_column = prev_lookup[(concept, metric)]
            a = pd.to_numeric(main_df[main_column], errors="coerce").dropna()
            b = pd.to_numeric(prev_df[prev_column], errors="coerce").dropna()
            main_min = top2_min_for(main_structure, main_column)
            prev_min = top2_min_for(prev_structure, prev_column)
            a_top = a >= main_min
            b_top = b >= prev_min
            stats_cell = _independent_stats(a_top, b_top, alpha)
            stats_cell["main_column"] = main_column
            stats_cell["prev_column"] = prev_column
            stats_cell["main_min"] = main_min
            stats_cell["prev_min"] = prev_min
            cells.setdefault(concept, {})[metric] = stats_cell
        frames["prev"] = prev_df
        return {
            "mode": mode,
            "concepts": list(concept_map.values()),
            "metrics": metrics,
            "cells": cells,
            "alpha": alpha,
            "warnings": warnings,
            "main_rows": int(len(main_df)),
            "prev_rows": int(len(prev_df)),
            "matched_total": None,
            "matched_used": None,
            "lag": None,
            "_frames": frames,
        }

    main_key = config.get("main_key")
    prev_key = config.get("prev_key")
    if not main_key or main_key not in main_df.columns:
        raise ValueError(f"Колонка-ключ «{main_key}» не найдена в текущей волне")
    if not prev_key or prev_key not in prev_df.columns:
        raise ValueError(f"Колонка-ключ «{prev_key}» не найдена в предыдущей волне")

    main = main_df.copy()
    prev = prev_df.copy()
    main["_key"] = main[main_key].astype(str).str.strip().str.lower()
    prev["_key"] = prev[prev_key].astype(str).str.strip().str.lower()
    duplicate_keys = int(main["_key"].duplicated().sum()) + int(prev["_key"].duplicated().sum())
    main = main[(main["_key"] != "") & (main["_key"] != "nan")]
    prev = prev[(prev["_key"] != "") & (prev["_key"] != "nan")]
    main = main[~main["_key"].duplicated()].reset_index(drop=True)
    prev = prev[~prev["_key"].duplicated()].reset_index(drop=True)
    main = main.rename(columns={column: f"main__{column}" for column in main.columns if column != "_key"})
    prev = prev.rename(columns={column: f"prev__{column}" for column in prev.columns if column != "_key"})
    merged = main.merge(prev, on="_key", how="inner")
    matched_total = int(len(merged))

    if mode == "panel_lag":
        main_date = config.get("main_date")
        prev_date = config.get("prev_date")
        main_date_column = f"main__{main_date}"
        prev_date_column = f"prev__{prev_date}"
        if main_date_column not in merged.columns:
            raise ValueError(f"Колонка даты «{main_date}» не найдена в текущей волне")
        if prev_date_column not in merged.columns:
            raise ValueError(f"Колонка даты «{prev_date}» не найдена в предыдущей волне")
        first = pd.to_datetime(merged[main_date_column], errors="coerce", dayfirst=True)
        second = pd.to_datetime(merged[prev_date_column], errors="coerce", dayfirst=True)
        lag_days = (first - second).dt.days
        lag_min = float(config.get("lag_min_days", 0) or 0)
        lag_max = float(config.get("lag_max_days", 3650) or 3650)
        mask = lag_days.notna() & (lag_days >= lag_min) & (lag_days <= lag_max)
        excluded = int((~mask).sum())
        merged = merged[mask].reset_index(drop=True)
        valid_lag = lag_days[mask]
        lag_info = {
            "min": lag_min,
            "max": lag_max,
            "excluded": excluded,
            "median_days": int(valid_lag.median()) if len(valid_lag) else None,
            "no_date": int(lag_days.isna().sum()),
        }

    matched_used = int(len(merged))
    cells = {}
    for concept, metric in pairs:
        main_column = f"main__{main_lookup[(concept, metric)]}"
        prev_column = f"prev__{prev_lookup[(concept, metric)]}"
        a = pd.to_numeric(merged[main_column], errors="coerce")
        b = pd.to_numeric(merged[prev_column], errors="coerce")
        mask = a.notna() & b.notna()
        main_min = top2_min_for(main_structure, main_lookup[(concept, metric)])
        prev_min = top2_min_for(prev_structure, prev_lookup[(concept, metric)])
        a_top = a[mask] >= main_min
        b_top = b[mask] >= prev_min
        stats_cell = _paired_stats(a_top, b_top, alpha)
        stats_cell["main_column"] = main_column
        stats_cell["prev_column"] = prev_column
        stats_cell["main_min"] = main_min
        stats_cell["prev_min"] = prev_min
        cells.setdefault(concept, {})[metric] = stats_cell

    if duplicate_keys:
        warnings.append(f"Дубликаты ID: {duplicate_keys} — использована первая запись")
    frames["merged"] = merged
    return {
        "mode": mode,
        "concepts": list(concept_map.values()),
        "metrics": metrics,
        "cells": cells,
        "alpha": alpha,
        "warnings": warnings,
        "main_rows": int(len(main_df)),
        "prev_rows": int(len(prev_df)),
        "matched_total": matched_total,
        "matched_used": matched_used,
        "lag": lag_info,
        "_frames": frames,
    }
