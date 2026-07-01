"""De-identified processing script copied from the development workflow as match_tomtom_here_benchmark.py."""

"""
03_tomtom_here_benchmark.py
TomTom–HERE 30 min block-time benchmark。

对应论文方法：
- Eq. (15): TomTom 15 min 点位值聚合到 30 min
- Eq. (16): TomTom 点位值聚合到 benchmark block
- Eq. (17): HERE segment records 聚合到 benchmark block
- Eq. (18): Pearson correlation
- Eq. (19): Spearman correlation
- Eq. (20)-(21): Peak overlap / Jaccard index

关键解释边界：
TomTom–HERE comparison 是 cross-platform consistency，不是 ground-truth validation。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


TOMTOM_REQUIRED = ["point_id", "interval_15min", "current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time", "ci_percent", "tti", "srr", "ett_seconds"]
POINT_CONFIG_REQUIRED = ["point_id", "block_id"]
HERE_REQUIRED = ["block_id", "interval_30min", "here_mean_jam_factor"]


def read_table(path: str | Path) -> pd.DataFrame:
    """读取 CSV / Excel / Parquet。"""
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


def ensure_columns(df: pd.DataFrame, required: List[str], table_name: str) -> None:
    """检查必须字段是否存在。"""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{table_name} 缺少字段: {missing}")


def aggregate_tomtom_to_30min_blocks(tomtom_cleaned: pd.DataFrame, point_config: pd.DataFrame) -> pd.DataFrame:
    """
    TomTom 15 min point-time → 30 min block-time。

    步骤一：时间聚合，对应 Eq. (15)。
    步骤二：空间聚合，对应 Eq. (16)。

    注意：
    - 这里使用简单平均，与论文公式一致。
    - 若未来要按道路长度加权，需要在 point_config 中增加 weight 字段，并修改聚合逻辑。
    """
    df = tomtom_cleaned.copy()
    cfg = point_config.copy()

    ensure_columns(df, TOMTOM_REQUIRED, "TomTom cleaned table")
    ensure_columns(cfg, POINT_CONFIG_REQUIRED, "point_config table")

    df["interval_15min"] = pd.to_datetime(df["interval_15min"], errors="coerce")
    df["interval_30min"] = df["interval_15min"].dt.floor("30min")

    # 避免 point_id 类型不一致导致 merge 失败。
    df["point_id"] = df["point_id"].astype(str)
    cfg["point_id"] = cfg["point_id"].astype(str)

    df = df.merge(cfg[["point_id", "block_id"]], on="point_id", how="left")
    if df["block_id"].isna().any():
        missing_points = df.loc[df["block_id"].isna(), "point_id"].drop_duplicates().tolist()
        raise ValueError(f"以下 TomTom point_id 没有 block_id 分配: {missing_points[:20]}")

    # 先按 point + 30 min 聚合。一个 30 min period 通常最多有两个 15 min 观测。
    point_30 = df.groupby(["block_id", "point_id", "interval_30min"], as_index=False).agg(
        tomtom_current_speed=("current_speed", "mean"),
        tomtom_free_flow_speed=("free_flow_speed", "mean"),
        tomtom_current_travel_time=("current_travel_time", "mean"),
        tomtom_free_flow_travel_time=("free_flow_travel_time", "mean"),
        tomtom_ci_percent=("ci_percent", "mean"),
        tomtom_tti=("tti", "mean"),
        tomtom_srr=("srr", "mean"),
        tomtom_ett_seconds=("ett_seconds", "mean"),
        tomtom_15min_count=("point_id", "size"),
    )

    # 再按 block + 30 min 聚合。
    block_30 = point_30.groupby(["block_id", "interval_30min"], as_index=False).agg(
        tomtom_mean_current_speed=("tomtom_current_speed", "mean"),
        tomtom_mean_free_flow_speed=("tomtom_free_flow_speed", "mean"),
        tomtom_mean_current_travel_time=("tomtom_current_travel_time", "mean"),
        tomtom_mean_free_flow_travel_time=("tomtom_free_flow_travel_time", "mean"),
        tomtom_mean_ci_percent=("tomtom_ci_percent", "mean"),
        tomtom_median_ci_percent=("tomtom_ci_percent", "median"),
        tomtom_mean_tti=("tomtom_tti", "mean"),
        tomtom_mean_srr=("tomtom_srr", "mean"),
        tomtom_mean_ett_seconds=("tomtom_ett_seconds", "mean"),
        tomtom_point_count=("point_id", "nunique"),
        tomtom_record_count_15min=("tomtom_15min_count", "sum"),
    )
    block_30["date"] = block_30["interval_30min"].dt.date
    return block_30


def match_tomtom_here(tomtom_block_30: pd.DataFrame, here_block_30: pd.DataFrame) -> pd.DataFrame:
    """
    构造 TomTom–HERE matched sample set D_m。

    匹配键：block_id + interval_30min。
    只保留两个平台在同一 block-time 都有效的记录。
    """
    tom = tomtom_block_30.copy()
    here = here_block_30.copy()

    ensure_columns(tom, ["block_id", "interval_30min", "tomtom_mean_ci_percent"], "TomTom block 30min table")
    ensure_columns(here, HERE_REQUIRED, "HERE block 30min table")

    tom["interval_30min"] = pd.to_datetime(tom["interval_30min"], errors="coerce")
    here["interval_30min"] = pd.to_datetime(here["interval_30min"], errors="coerce")

    tom["block_id"] = tom["block_id"].astype(str)
    here["block_id"] = here["block_id"].astype(str)

    matched = tom.merge(here, on=["block_id", "interval_30min"], how="inner", suffixes=("_tomtom", "_here"))
    matched = matched.dropna(subset=["tomtom_mean_ci_percent", "here_mean_jam_factor"])
    matched["date"] = matched["interval_30min"].dt.date
    return matched


def pearson_spearman(df: pd.DataFrame, x: str, y: str) -> Tuple[float, float, int]:
    """
    计算 Pearson 与 Spearman。

    检查说明：
    - Pearson 用于线性共变关系，对应论文 Eq. (18)。
    - Spearman 用 pandas 计算 rank correlation，优点是能处理并列排名 ties，
      比直接套用 1 - 6Σd²/[K(K²-1)] 更稳。
    """
    sub = df[[x, y]].dropna()
    n = len(sub)
    if n < 3:
        return np.nan, np.nan, n
    pearson = sub[x].corr(sub[y], method="pearson")
    spearman = sub[x].corr(sub[y], method="spearman")
    return float(pearson), float(spearman), n


def peak_overlap_index(df: pd.DataFrame, x: str, y: str, q: float = 0.85) -> float:
    """
    计算 Jaccard peak overlap index，对应论文 Eq. (20)-(21)。

    参数
    ----
    df : pd.DataFrame
        matched sample。
    x : str
        TomTom pressure variable，默认应为 tomtom_mean_ci_percent。
    y : str
        HERE pressure variable，默认应为 here_mean_jam_factor。
    q : float
        上分位阈值，例如 0.85 表示取前 15% 高压力记录。

    返回
    ----
    float
        |S_T ∩ S_H| / |S_T ∪ S_H|。
    """
    sub = df[[x, y]].dropna().copy()
    if sub.empty:
        return np.nan

    x_thr = sub[x].quantile(q)
    y_thr = sub[y].quantile(q)
    s_x = set(sub.index[sub[x] >= x_thr])
    s_y = set(sub.index[sub[y] >= y_thr])
    union = s_x.union(s_y)
    if len(union) == 0:
        return np.nan
    return len(s_x.intersection(s_y)) / len(union)


def benchmark_summary(
    matched: pd.DataFrame,
    x: str = "tomtom_mean_ci_percent",
    y: str = "here_mean_jam_factor",
    q: float = 0.85,
) -> pd.DataFrame:
    """
    计算 pooled + per-block benchmark summary。
    """
    rows = []

    def one_summary(label: str, sub: pd.DataFrame) -> Dict[str, object]:
        r, rho, n = pearson_spearman(sub, x, y)
        po = peak_overlap_index(sub, x, y, q=q)
        return {
            "unit": label,
            "matched_n": n,
            "tomtom_ci_mean": sub[x].mean(),
            "tomtom_ci_median": sub[x].median(),
            "tomtom_ci_sd": sub[x].std(ddof=1),
            "tomtom_ci_min": sub[x].min(),
            "tomtom_ci_max": sub[x].max(),
            "here_jf_mean": sub[y].mean(),
            "here_jf_median": sub[y].median(),
            "here_jf_sd": sub[y].std(ddof=1),
            "here_jf_min": sub[y].min(),
            "here_jf_max": sub[y].max(),
            "pearson_r": r,
            "spearman_rho": rho,
            "peak_overlap_q": q,
            "peak_overlap_index": po,
        }

    rows.append(one_summary("pooled", matched))
    for block_id, sub in matched.groupby("block_id"):
        rows.append(one_summary(f"block_{block_id}", sub))

    return pd.DataFrame(rows)


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="TomTom–HERE 30 min block-time benchmark。")
    parser.add_argument("--tomtom_cleaned", required=True, help="tomtom_cleaned_point_time.csv")
    parser.add_argument("--here_block", required=True, help="here_cleaned_block_time.csv")
    parser.add_argument("--point_config", required=True, help="point_config.csv，至少含 point_id 和 block_id。")
    parser.add_argument("--output_dir", required=True, help="输出目录。")
    parser.add_argument("--peak_q", type=float, default=0.85, help="Peak overlap 上分位阈值，默认 0.85。")
    args = parser.parse_args()

    tom = read_table(args.tomtom_cleaned)
    here = read_table(args.here_block)
    cfg = read_table(args.point_config)

    tom_block = aggregate_tomtom_to_30min_blocks(tom, cfg)
    matched = match_tomtom_here(tom_block, here)
    summary = benchmark_summary(matched, q=args.peak_q)

    out = Path(args.output_dir)
    write_csv(tom_block, out / "tomtom_block_30min.csv")
    write_csv(matched, out / "matched_tomtom_here_30min.csv")
    write_csv(summary, out / "benchmark_summary.csv")

    print("TomTom–HERE benchmark 完成。")
    print(f"matched block-time 样本数: {len(matched):,}")
    print(summary[["unit", "matched_n", "pearson_r", "spearman_rho", "peak_overlap_index"]])


if __name__ == "__main__":
    run_cli()
