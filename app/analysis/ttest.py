import numpy as np
import pandas as pd
from scipy import stats


_REFERENCES = [
    "Student (1908). The probable error of a mean. Biometrika, 6(1), 1-25.",
    "Welch (1947). The generalization of \"Student's\" problem when several different population variances are involved. Biometrika, 34(1-2), 28-35.",
    "Mann & Whitney (1947). On a test of whether one of two random variables is stochastically larger than the other. Annals of Mathematical Statistics, 18(1), 50-60.",
    "Shapiro & Wilk (1965). An analysis of variance test for normality (complete samples). Biometrika, 52(3-4), 591-611.",
    "Brown & Forsythe (1974). Robust tests for the equality of variances. Journal of the American Statistical Association, 69(346), 364-367.",
    "Cohen (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum Associates.",
]


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _fmt_p(p: float) -> str:
    if p < 0.001:
        return "< 0,001"
    return "= " + f"{p:.3f}".replace(".", ",")


def _descriptives(x: np.ndarray) -> dict:
    return {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "sd": float(np.std(x, ddof=1)),
        "median": float(np.median(x)),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def _shapiro(x: np.ndarray):
    try:
        w, p = stats.shapiro(x)
    except Exception:
        return None
    if not np.isfinite(w) or not np.isfinite(p):
        return None
    return {"W": float(w), "p": float(p)}


def _effect_label(value: float, thresholds: tuple) -> str:
    small, medium, large = thresholds
    if value < small:
        return "очень малый"
    if value < medium:
        return "малый"
    if value < large:
        return "средний"
    return "большой"


def _t_result(a: np.ndarray, b: np.ndarray, equal_var: bool, alpha: float) -> dict:
    n_a, n_b = a.size, b.size
    var_a, var_b = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    diff = float(np.mean(a) - np.mean(b))
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    pooled_sd = np.sqrt(pooled_var)
    if equal_var:
        name = "t-тест Стьюдента для независимых выборок"
        df = float(n_a + n_b - 2)
        se = float(np.sqrt(pooled_var * (1 / n_a + 1 / n_b)))
    else:
        name = "t-тест Уэлча для независимых выборок"
        v_a, v_b = var_a / n_a, var_b / n_b
        df = float((v_a + v_b) ** 2 / (v_a ** 2 / (n_a - 1) + v_b ** 2 / (n_b - 1)))
        se = float(np.sqrt(v_a + v_b))
    t, p = stats.ttest_ind(a, b, equal_var=equal_var)
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    d = float(diff / pooled_sd)
    g = float(d * (1 - 3 / (4 * (n_a + n_b) - 9)))
    return {
        "name": name,
        "t": float(t),
        "df": df,
        "p": float(p),
        "mean_diff": diff,
        "ci": [diff - t_crit * se, diff + t_crit * se],
        "cohens_d": d,
        "hedges_g": g,
        "effect": _effect_label(abs(d), (0.2, 0.5, 0.8)),
    }


def _mwu_result(a: np.ndarray, b: np.ndarray) -> dict:
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    r = float(1 - (2 * u) / (a.size * b.size))
    return {
        "name": "U-тест Манна-Уитни",
        "u": float(u),
        "p": float(p),
        "median_diff": float(np.median(a) - np.median(b)),
        "rank_biserial": r,
        "effect": _effect_label(abs(r), (0.1, 0.3, 0.5)),
    }


def _normality_text(label: str, norm) -> str:
    if norm is None:
        return f"группа «{label}»: проверка недоступна"
    return f"группа «{label}»: W = {_fmt(norm['W'], 3)}, p {_fmt_p(norm['p'])}"


def _result_text(primary: dict) -> str:
    if "t" in primary:
        return (
            f"{primary['name']}: t = {_fmt(primary['t'], 3)}, df = {_fmt(primary['df'], 1)}, "
            f"p {_fmt_p(primary['p'])}; разность средних = {_fmt(primary['mean_diff'], 3)}, "
            f"95% ДИ [{_fmt(primary['ci'][0], 3)}; {_fmt(primary['ci'][1], 3)}]; "
            f"d Коэна = {_fmt(primary['cohens_d'], 3)} ({primary['effect']}); "
            f"g Хеджеса = {_fmt(primary['hedges_g'], 3)}."
        )
    return (
        f"{primary['name']}: U = {_fmt(primary['u'], 1)}, p {_fmt_p(primary['p'])}; "
        f"разность медиан = {_fmt(primary['median_diff'], 3)}; "
        f"рангово-бисериальная корреляция r = {_fmt(primary['rank_biserial'], 3)} ({primary['effect']})."
    )


def run(df: pd.DataFrame, value_col: str, group_col: str, alpha: float = 0.05) -> dict:
    if value_col == group_col:
        raise ValueError("Анализируемая и группирующая переменные должны различаться")
    for col in (value_col, group_col):
        if col not in df.columns:
            raise ValueError(f"Столбец «{col}» не найден в данных")

    total_rows = int(len(df))
    work = df[[value_col, group_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna()
    dropped = total_rows - int(len(work))

    if len(work) < 6:
        raise ValueError("Недостаточно полных наблюдений: нужно минимум 6")

    group_values = list(work[group_col].unique())
    if len(group_values) != 2:
        raise ValueError(
            f"Группирующая переменная должна содержать ровно 2 группы, найдено: {len(group_values)}"
        )

    label_a, label_b = str(group_values[0]), str(group_values[1])
    a = work.loc[work[group_col] == group_values[0], value_col].to_numpy(dtype=float)
    b = work.loc[work[group_col] == group_values[1], value_col].to_numpy(dtype=float)

    if min(a.size, b.size) < 3:
        raise ValueError("В каждой группе должно быть не менее 3 наблюдений")
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        raise ValueError("В одной из групп все значения одинаковы - сравнение невозможно")

    desc_a, desc_b = _descriptives(a), _descriptives(b)
    norm_a, norm_b = _shapiro(a), _shapiro(b)
    levene = stats.levene(a, b, center="median")

    normal_ok = bool(norm_a and norm_b and norm_a["p"] > alpha and norm_b["p"] > alpha)
    variance_ok = bool(levene.pvalue > alpha)

    if normal_ok:
        primary = _t_result(a, b, equal_var=variance_ok, alpha=alpha)
        reference = None
        if variance_ok:
            reason = (
                "Обе группы не отклоняются от нормального распределения, дисперсии однородны: "
                "выбран t-тест Стьюдента для независимых выборок."
            )
        else:
            reason = (
                "Обе группы не отклоняются от нормального распределения, но дисперсии неоднородны: "
                "выбран t-тест Уэлча, не требующий равенства дисперсий."
            )
    else:
        primary = _mwu_result(a, b)
        reference = _t_result(a, b, equal_var=variance_ok, alpha=alpha)
        reason = (
            "Хотя бы в одной группе выявлено отклонение от нормального распределения: "
            "основным выбран непараметрический U-тест Манна-Уитни; t-тест приведён справочно. "
            "При больших выборках (n >= 30 в каждой группе) t-тест устойчив к умеренным "
            "отклонениям от нормальности (центральная предельная теорема)."
        )

    significant = bool(primary["p"] < alpha)

    if significant:
        if "t" in primary:
            direction = "выше" if primary["mean_diff"] > 0 else "ниже"
            conclusion = (
                f"Различия статистически значимы (t = {_fmt(primary['t'], 3)}, "
                f"df = {_fmt(primary['df'], 1)}, p {_fmt_p(primary['p'])} при a = {_fmt(alpha)}). "
                f"Среднее значение в группе «{label_a}» (M = {_fmt(desc_a['mean'])}, "
                f"SD = {_fmt(desc_a['sd'])}) {direction}, чем в группе «{label_b}» "
                f"(M = {_fmt(desc_b['mean'])}, SD = {_fmt(desc_b['sd'])}). "
                f"Размер эффекта: d Коэна = {_fmt(primary['cohens_d'], 3)} ({primary['effect']})."
            )
        else:
            direction = "выше" if primary["median_diff"] > 0 else "ниже"
            conclusion = (
                f"Различия статистически значимы (U = {_fmt(primary['u'], 1)}, "
                f"p {_fmt_p(primary['p'])} при a = {_fmt(alpha)}). "
                f"Медиана в группе «{label_a}» (Md = {_fmt(desc_a['median'])}) {direction}, "
                f"чем в группе «{label_b}» (Md = {_fmt(desc_b['median'])}). "
                f"Размер эффекта: рангово-бисериальная корреляция "
                f"r = {_fmt(primary['rank_biserial'], 3)} ({primary['effect']})."
            )
    else:
        conclusion = (
            f"Статистически значимых различий не обнаружено ({primary['name']}: "
            f"p {_fmt_p(primary['p'])} при a = {_fmt(alpha)}). "
            "Наблюдаемые различия групп могут объясняться случайной вариацией выборки."
        )

    steps = [
        {
            "title": "Шаг 1. Подготовка данных",
            "text": (
                f"Загружено строк: {total_rows}. В анализ включено {int(len(work))} наблюдений."
                + (
                    f" Исключено строк с пропусками или нечисловыми значениями: {dropped}."
                    if dropped
                    else ""
                )
            ),
        },
        {
            "title": "Шаг 2. Сравниваемые группы",
            "text": f"«{label_a}»: n = {int(a.size)}; «{label_b}»: n = {int(b.size)}.",
        },
        {
            "title": "Шаг 3. Проверка нормальности (тест Шапиро-Уилка)",
            "text": f"{_normality_text(label_a, norm_a)}; {_normality_text(label_b, norm_b)}.",
            "decision": (
                "H0 теста: распределение нормальное. "
                + (
                    "Отклонений от нормальности не выявлено в обеих группах (p > a)."
                    if normal_ok
                    else "Нормальность отклонена хотя бы в одной группе (p <= a)."
                )
            ),
        },
        {
            "title": "Шаг 4. Проверка однородности дисперсий (Левен по медиане, Браун-Форсайт)",
            "text": f"F = {_fmt(float(levene.statistic), 3)}, p {_fmt_p(float(levene.pvalue))}.",
            "decision": (
                "H0 теста: дисперсии равны. "
                + (
                    "Дисперсии признаны однородными (p > a)."
                    if variance_ok
                    else "Дисперсии неоднородны (p <= a)."
                )
            ),
        },
        {
            "title": "Шаг 5. Выбор метода",
            "text": reason,
        },
        {
            "title": "Шаг 6. Результат",
            "text": _result_text(primary),
        },
    ]

    return {
        "procedure": {
            "id": "ttest_ind",
            "title": "t-тест для независимых выборок",
            "alpha": float(alpha),
            "steps": steps,
            "references": _REFERENCES,
        },
        "significant": significant,
        "variables": {"value": value_col, "group": group_col},
        "descriptives": [
            {"group": label_a, **desc_a},
            {"group": label_b, **desc_b},
        ],
        "assumptions": {
            "normality": {
                "test": "Шапиро-Уилк",
                "passed": normal_ok,
                "groups": [
                    {
                        "group": label_a,
                        "W": norm_a["W"] if norm_a else None,
                        "p": norm_a["p"] if norm_a else None,
                    },
                    {
                        "group": label_b,
                        "W": norm_b["W"] if norm_b else None,
                        "p": norm_b["p"] if norm_b else None,
                    },
                ],
            },
            "homogeneity": {
                "test": "Левен по медиане (Браун-Форсайт)",
                "statistic": float(levene.statistic),
                "p": float(levene.pvalue),
                "passed": variance_ok,
            },
        },
        "primary": primary,
        "reference": reference,
        "conclusion": conclusion,
    }
