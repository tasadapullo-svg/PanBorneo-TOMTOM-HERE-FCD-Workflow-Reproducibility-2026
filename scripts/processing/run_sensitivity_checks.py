"""De-identified processing script copied from the development workflow as run_sensitivity_checks.py."""

"""
04_sensitivity_analysis.py
TomTom–HERE benchmark 敏感性分析。

对应论文 Table 6：
1. Threshold sensitivity: q = 0.80, 0.85, 0.90, 0.95
2. Temporal-lag sensitivity: HERE shifted by -30, 0, +30 min relative to TomTom
3. Per-block sensitivity: block 1, block 2, block 3 separately
4. Daily-stratified sensitivity: 按日期计算相关性与 peak overlap

解释边界：
这些结果用于检查 cross-platform consistency 是否稳定，不用于证明绝对精度。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

# 允许从同目录直接运行。
try:
    from scripts._benchmark_utils import pearson_spearman, peak_overlap_index, write_csv, read_table
except Exception:
    # 如果没有作为 package 运行，则使用本文件中的轻量函数。
    pass


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"不支持的文件格式: {path.suffix}")


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def pearson_spearman(df: pd.DataFrame, x: str, y: str) -> Tuple[float, float, int]:
    sub = df[[x, y]].dropna()
    n = len(sub)
    if n < 3:
        return np.nan, np.nan, n
    return float(sub[x].corr(sub[y], method="pearson")), float(sub[x].corr(sub[y], method="spearman")), n


def peak_overlap_index(df: pd.DataFrame, x: str, y: str, q: float = 0.85) -> float:
    sub = df[[x, y]].dropna().copy()
    if sub.empty:
        return np.nan
    x_thr = sub[x].quantile(q)
    y_thr = sub[y].quantile(q)
    sx = set(sub.index[sub[x] >= x_thr])
    sy = set(sub.index[sub[y] >= y_thr])
    union = sx.union(sy)
    if not union:
        return np.nan
    return len(sx.intersection(sy)) / len(union)


def threshold_sensitivity(
    matched: pd.DataFrame,
    thresholds: Iterable[float] = (0.80, 0.85, 0.90, 0.95),
    x: str = "tomtom_mean_ci_percent",
    y: str = "here_mean_jam_factor",
) -> pd.DataFrame:
    """不同 peak threshold 下的 Jaccard overlap。"""
    rows = []
    for q in thresholds:
        rows.append({
            "threshold_quantile": q,
            "matched_n": matched[[x, y]].dropna().shape[0],
            "peak_overlap_index": peak_overlap_index(matched, x, y, q=q),
        })
    return pd.DataFrame(rows)


def lag_sensitivity(
    matched_or_tom_here: pd.DataFrame,
    lags_minutes: Iterable[int] = (-30, 0, 30),
    x: str = "tomtom_mean_ci_percent",
    y: str = "here_mean_jam_factor",
    q: float = 0.85,
) -> pd.DataFrame:
    """
    时间滞后敏感性。

    使用方式：
    输入表必须已经包含 block_id、interval_30min、TomTom 与 HERE 变量。
    这里通过移动 HERE 的时间戳实现：
    - lag = -30 表示 HERE 提前 30 min 与 TomTom 匹配；
    - lag = 0 表示原始匹配；
    - lag = +30 表示 HERE 滞后 30 min 与 TomTom 匹配。

    技术处理：
    因 matched table 已经是合并后的表，最好传入含 TomTom block 表与 HERE block 表合并前的数据。
    为了兼容已有 matched table，本函数将表拆成 TomTom 与 HERE 两侧，再重新按移动后的 HERE 时间匹配。
    """
    df = matched_or_tom_here.copy()
    df["interval_30min"] = pd.to_datetime(df["interval_30min"], errors="coerce")
    df["block_id"] = df["block_id"].astype(str)

    tom_cols = ["block_id", "interval_30min", x]
    here_cols = ["block_id", "interval_30min", y]
    tom = df[tom_cols].dropna().drop_duplicates()
    here = df[here_cols].dropna().drop_duplicates()

    rows = []
    for lag in lags_minutes:
        shifted = here.copy()
        shifted["interval_30min"] = shifted["interval_30min"] + pd.to_timedelta(lag, unit="min")
        joined = tom.merge(shifted, on=["block_id", "interval_30min"], how="inner")
        r, rho, n = pearson_spearman(joined, x, y)
        po = peak_overlap_index(joined, x, y, q=q)
        rows.append({
            "here_shift_minutes": lag,
            "matched_n": n,
            "pearson_r": r,
            "spearman_rho": rho,
            "peak_overlap_q": q,
            "peak_overlap_index": po,
        })
    return pd.DataFrame(rows)


def per_block_sensitivity(
    matched: pd.DataFrame,
    x: str = "tomtom_mean_ci_percent",
    y: str = "here_mean_jam_factor",
    q: float = 0.85,
) -> pd.DataFrame:
    """按 benchmark block 分别计算相关性与 peak overlap。"""
    rows = []
    for block_id, sub in matched.groupby("block_id"):
        r, rho, n = pearson_spearman(sub, x, y)
        rows.append({
            "block_id": block_id,
            "matched_n": n,
            "pearson_r": r,
            "spearman_rho": rho,
            "peak_overlap_q": q,
            "peak_overlap_index": peak_overlap_index(sub, x, y, q=q),
            "tomtom_ci_mean": sub[x].mean(),
            "here_jf_mean": sub[y].mean(),
        })
    return pd.DataFrame(rows)


def daily_stratified_sensitivity(
    matched: pd.DataFrame,
    x: str = "tomtom_mean_ci_percent",
    y: str = "here_mean_jam_factor",
    q: float = 0.85,
) -> pd.DataFrame:
    """按日期分层计算 benchmark consistency。"""
    df = matched.copy()
    if "date" not in df.columns:
        df["interval_30min"] = pd.to_datetime(df["interval_30min"], errors="coerce")
        df["date"] = df["interval_30min"].dt.date

    rows = []
    for date, sub in df.groupby("date"):
        r, rho, n = pearson_spearman(sub, x, y)
        rows.append({
            "date": date,
            "matched_n": n,
            "pearson_r": r,
            "spearman_rho": rho,
            "peak_overlap_q": q,
            "peak_overlap_index": peak_overlap_index(sub, x, y, q=q),
            "tomtom_ci_mean": sub[x].mean(),
            "here_jf_mean": sub[y].mean(),
        })
    return pd.DataFrame(rows)


def run_all_sensitivity(matched: pd.DataFrame, q: float = 0.85) -> Dict[str, pd.DataFrame]:
    """一次性生成四类敏感性分析结果。"""
    return {
        "sensitivity_threshold": threshold_sensitivity(matched),
        "sensitivity_lag": lag_sensitivity(matched, q=q),
        "sensitivity_per_block": per_block_sensitivity(matched, q=q),
        "sensitivity_daily": daily_stratified_sensitivity(matched, q=q),
    }


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="TomTom–HERE benchmark 敏感性分析。")
    parser.add_argument("--matched", required=True, help="matched_tomtom_here_30min.csv")
    parser.add_argument("--output_dir", required=True, help="输出目录。")
    parser.add_argument("--peak_q", type=float, default=0.85, help="Peak overlap 主阈值，默认 0.85。")
    args = parser.parse_args()

    matched = read_table(args.matched)
    results = run_all_sensitivity(matched, q=args.peak_q)

    out = Path(args.output_dir)
    for name, df in results.items():
        write_csv(df, out / f"{name}.csv")

    print("敏感性分析完成。")
    for name, df in results.items():
        print(f"{name}: {len(df):,} rows")


if __name__ == "__main__":
    run_cli()
