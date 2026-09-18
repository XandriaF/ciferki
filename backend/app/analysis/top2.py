import numpy as np
import pandas as pd
from scipy import stats

from ..parsing import TOP2_MIN_BY_SCALE

TOP2_MIN = 4


def top2_min_for(structure: dict, column_name: str) -> int:
    for column in structure["columns"]:
        if column["name"] == column_name:
            return TOP2_MIN_BY_SCALE.get(column.get("scale") or "", TOP2_MIN)
    return TOP2_MIN


def wilson_interval(x: int, n: int, conf: float = 0.95):
    if n == 0:
        return None, None
    z = float(stats.norm.ppf(1 - (1 - conf) / 2))
    p = x / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return float(centre - margin), float(centre + margin)


def concept_metric_columns(structure: dict, metrics: list, concept_map: dict) -> list:
    by_group: dict = {}
    for column in structure["columns"]:
        if column["type"] == "matrix" and column.get("group") in concept_map:
            by_group.setdefault(column["group"], {})[column.get("option")] = column["name"]
    triples = []
    for group, concept_name in concept_map.items():
        for metric in metrics:
            column_name = by_group.get(group, {}).get(metric)
            if column_name:
                triples.append((concept_name, metric, column_name))
    return triples


def compute_top2(df: pd.DataFrame, structure: dict, config: dict) -> dict:
    concept_map = config.get("concept_map", {})
    metrics = config.get("metrics", [])
    alpha = float(config.get("alpha", 0.05))
    norm_mode = config.get("norm_mode", "q3")
    manual_norms = config.get("manual_norms", {}) or {}

    triples = concept_metric_columns(structure, metrics, concept_map)
    cells: dict = {}
    pct_by_metric: dict = {}
    for concept_name, metric, column_name in triples:
        series = pd.to_numeric(df[column_name], errors="coerce").dropna()
        minimum = top2_min_for(structure, column_name)
        n = int(len(series))
        x = int((series >= minimum).sum())
        pct = round(x / n * 100, 1) if n else None
        lower, upper = wilson_interval(x, n, 1 - alpha)
        cells.setdefault(concept_name, {})[metric] = {
            "n": n,
            "top2": x,
            "top2_min": minimum,
            "pct": pct,
            "lower": round(lower * 100, 1) if lower is not None else None,
            "upper": round(upper * 100, 1) if upper is not None else None,
            "column": column_name,
        }
        pct_by_metric.setdefault(metric, []).append(pct if pct is not None else np.nan)

    norms: dict = {}
    for metric in metrics:
        if norm_mode == "manual":
            value = manual_norms.get(metric)
            norms[metric] = float(value) if value not in (None, "") else None
        else:
            values = [v for v in pct_by_metric.get(metric, []) if v is not None and not np.isnan(v)]
            norms[metric] = round(float(np.percentile(values, 75, method="linear")), 1) if values else None

    for concept_cells in cells.values():
        for metric, cell in concept_cells.items():
            norm = norms.get(metric)
            cell["norm"] = norm
            if norm is None or cell["lower"] is None:
                cell["flag"] = "нет данных"
            elif cell["lower"] > norm:
                cell["flag"] = "выше"
            elif cell["upper"] < norm:
                cell["flag"] = "ниже"
            else:
                cell["flag"] = "не значимо"

    return {
        "concepts": list(concept_map.values()),
        "metrics": metrics,
        "cells": cells,
        "norms": norms,
        "norm_mode": norm_mode,
        "alpha": alpha,
    }
