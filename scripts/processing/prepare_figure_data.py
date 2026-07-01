"""De-identified processing script copied from the development workflow as prepare_figure_data.py."""

"""
05_plot_reproduction.py
可选：根据清洗结果复现论文中的 Fig 4 / Fig 5 基础图形数据。

说明：
- 本脚本重点输出图形所需统计表，不强制复现最终排版。
- 投稿用 TIFF/PNG/SVG 建议在最终图形脚本中单独调整字体、尺寸和 dpi。
- 不使用 seaborn，避免额外依赖。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"不支持的文件格式: {path.suffix}")


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def build_intraday_profile(tomtom_cleaned: pd.DataFrame) -> pd.DataFrame:
    """
    构造 Fig 5 所需的 intraday profile。

    输出字段：
    - time_of_day
    - mean_current_speed
    - mean_ci_percent
    - mean_tti
    - weekday/weekend 分组均值
    """
    df = tomtom_cleaned.copy()
    df["interval_15min"] = pd.to_datetime(df["interval_15min"], errors="coerce")
    df["time_of_day"] = df["interval_15min"].dt.strftime("%H:%M")
    df["day_type"] = np.where(df["interval_15min"].dt.dayofweek < 5, "weekday", "weekend")

    profile = df.groupby("time_of_day", as_index=False).agg(
        mean_current_speed=("current_speed", "mean"),
        mean_ci_percent=("ci_percent", "mean"),
        mean_tti=("tti", "mean"),
        mean_srr=("srr", "mean"),
        record_count=("point_id", "size"),
    )

    day_type_profile = df.groupby(["time_of_day", "day_type"], as_index=False).agg(
        mean_current_speed=("current_speed", "mean"),
        mean_ci_percent=("ci_percent", "mean"),
        mean_tti=("tti", "mean"),
        record_count=("point_id", "size"),
    )

    return profile, day_type_profile


def zscore(series: pd.Series) -> pd.Series:
    """标准化，用于 Fig 5(c) 中不同量纲指标的同步比较。"""
    sd = series.std(ddof=1)
    if sd == 0 or pd.isna(sd):
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean()) / sd


def add_standardized_profile(profile: pd.DataFrame) -> pd.DataFrame:
    """增加标准化 CI 与 TTI。"""
    out = profile.copy()
    out["z_ci_percent"] = zscore(out["mean_ci_percent"])
    out["z_tti"] = zscore(out["mean_tti"])
    return out


def save_basic_plots(daily_availability: pd.DataFrame, intraday_profile: pd.DataFrame, output_dir: Path) -> None:
    """
    保存基础 PNG 图，仅用于快速检查。
    最终论文图可基于输出 CSV 重新排版成 300/600 dpi TIFF。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    daily = daily_availability.copy()
    daily["date"] = pd.to_datetime(daily["date"])

    plt.figure(figsize=(10, 4))
    plt.plot(daily["date"], daily["availability_rate"] * 100, marker="o", linewidth=1)
    plt.axhline(100, linestyle="--", linewidth=1)
    plt.ylabel("Availability (%)")
    plt.xlabel("Date")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "quick_check_daily_availability.png", dpi=300)
    plt.close()

    prof = intraday_profile.copy()
    plt.figure(figsize=(10, 4))
    plt.plot(prof["time_of_day"], prof["mean_current_speed"], linewidth=1)
    plt.ylabel("Mean current speed (km/h)")
    plt.xlabel("Time of day")
    plt.xticks(prof["time_of_day"][::8], rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "quick_check_intraday_speed.png", dpi=300)
    plt.close()


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="生成 Fig 4/Fig 5 的基础复现数据与快速检查图。")
    parser.add_argument("--tomtom_cleaned", required=True, help="tomtom_cleaned_point_time.csv")
    parser.add_argument("--daily_availability", required=True, help="tomtom_daily_availability.csv")
    parser.add_argument("--output_dir", required=True, help="输出目录。")
    args = parser.parse_args()

    tom = read_table(args.tomtom_cleaned)
    daily = read_table(args.daily_availability)
    out = Path(args.output_dir)

    profile, day_type_profile = build_intraday_profile(tom)
    profile = add_standardized_profile(profile)

    write_csv(profile, out / "fig5_intraday_profile_data.csv")
    write_csv(day_type_profile, out / "fig5_weekday_weekend_profile_data.csv")
    save_basic_plots(daily, profile, out)

    print("图形复现基础数据已生成。")


if __name__ == "__main__":
    run_cli()
