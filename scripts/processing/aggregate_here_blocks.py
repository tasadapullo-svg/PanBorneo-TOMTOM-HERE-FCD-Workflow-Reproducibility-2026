"""De-identified processing script copied from the development workflow as aggregate_here_blocks.py."""

"""
02_here_cleaning.py
HERE 30 min 数据清洗与 block-time 聚合。

对应论文方法：
- HERE 数据作为外部 benchmark signal，不作为 ground truth。
- HERE 保持 30 min 分辨率，不进行 upsampling。
- HERE segment records 聚合到 benchmark block-time unit。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


COLUMN_ALIASES: Dict[str, List[str]] = {
    "block_id": ["block_id", "benchmark_block", "benchmark_block_id", "block", "here_block"],
    "timestamp": ["timestamp", "time", "datetime", "collect_time", "record_time", "created_at"],
    "speed": ["speed", "current_speed", "speed_kmh", "here_speed", "mean_speed"],
    "jam_factor": ["jam_factor", "jamFactor", "jf", "here_jam_factor", "jamfactor"],
    "confidence": ["confidence", "conf", "here_confidence"],
    "segment_id": ["segment_id", "segmentId", "link_id", "road_segment_id"],
}

CORE_FIELDS = ["block_id", "timestamp", "speed", "jam_factor"]
NUMERIC_FIELDS = ["speed", "jam_factor", "confidence"]


def _standardize_colname(name: str) -> str:
    return str(name).strip().replace(" ", "_").replace("-", "_")


def normalize_columns(df: pd.DataFrame, aliases: Dict[str, List[str]] = COLUMN_ALIASES) -> pd.DataFrame:
    """把 HERE 字段名统一为标准字段名。"""
    df = df.copy()
    original_columns = list(df.columns)
    normalized_lookup = {_standardize_colname(c).lower(): c for c in original_columns}
    rename_map = {}
    for standard_name, candidates in aliases.items():
        for candidate in candidates:
            key = _standardize_colname(candidate).lower()
            if key in normalized_lookup:
                rename_map[normalized_lookup[key]] = standard_name
                break
    return df.rename(columns=rename_map)


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


def parse_and_standardize_here(raw: pd.DataFrame) -> pd.DataFrame:
    """
    解析 HERE 原始表。

    处理逻辑：
    1. 字段名标准化；
    2. timestamp 转 datetime；
    3. 向下取整到 30 min；
    4. 数值字段转 numeric。
    """
    df = normalize_columns(raw)
    missing = [c for c in CORE_FIELDS if c not in df.columns]
    if missing:
        raise ValueError(f"HERE 输入表缺少核心字段: {missing}。如果没有 block_id，请先完成空间分配。")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["interval_30min"] = df["timestamp"].dt.floor("30min")
    df["date"] = df["interval_30min"].dt.date

    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "segment_id" not in df.columns:
        # 如果没有 segment_id，使用行号作为临时 ID，不影响 block-time 均值。
        df["segment_id"] = np.arange(len(df))

    return df


def add_here_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    添加 HERE 清洗标记。

    HERE jam_factor 理论上通常在 0-10，但不同导出方式可能有差异。
    这里默认只要求 jam_factor 非负，不强行截断 10。
    如果你确认平台字段范围固定为 0-10，可增加上限规则。
    """
    df = df.copy()
    df["valid_time"] = df["interval_30min"].notna()
    df["valid_core_fields"] = df[CORE_FIELDS].notna().all(axis=1)
    df["valid_speed"] = df["speed"] > 0
    df["valid_jam_factor"] = df["jam_factor"] >= 0
    if "confidence" in df.columns:
        df["confidence_exists"] = df["confidence"].notna()
    else:
        df["confidence"] = np.nan
        df["confidence_exists"] = False
    df["is_valid"] = df["valid_time"] & df["valid_core_fields"] & df["valid_speed"] & df["valid_jam_factor"]
    return df


def clean_here(raw: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    清洗 HERE 数据，并聚合为 block-time 表。

    返回
    ----
    block_time : pd.DataFrame
        block_id + interval_30min 的聚合表。
    cleaning_summary : pd.DataFrame
        HERE 清洗日志按日汇总。
    """
    parsed = parse_and_standardize_here(raw)
    flagged = add_here_quality_flags(parsed)
    valid = flagged.loc[flagged["is_valid"]].copy()

    # segment-level 到 block-time 聚合。论文 Eq. (17) 使用简单平均。
    block_time = valid.groupby(["block_id", "interval_30min"], as_index=False).agg(
        here_mean_speed=("speed", "mean"),
        here_median_speed=("speed", "median"),
        here_mean_jam_factor=("jam_factor", "mean"),
        here_median_jam_factor=("jam_factor", "median"),
        here_segment_count=("segment_id", "nunique"),
        here_record_count=("segment_id", "size"),
        here_mean_confidence=("confidence", "mean"),
    )
    block_time["date"] = block_time["interval_30min"].dt.date

    cleaning_summary = flagged.groupby("date", dropna=False).agg(
        raw_records=("block_id", "size"),
        invalid_time_records=("valid_time", lambda x: int((~x).sum())),
        missing_core_field_records=("valid_core_fields", lambda x: int((~x).sum())),
        non_positive_speed_records=("valid_speed", lambda x: int((~x).sum())),
        negative_jam_factor_records=("valid_jam_factor", lambda x: int((~x).sum())),
        valid_records=("is_valid", lambda x: int(x.sum())),
    ).reset_index()
    cleaning_summary["cleaning_pass_rate"] = np.where(
        cleaning_summary["raw_records"] > 0,
        cleaning_summary["valid_records"] / cleaning_summary["raw_records"],
        np.nan,
    )

    return block_time, cleaning_summary


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="HERE 30 min 数据清洗与 block-time 聚合。")
    parser.add_argument("--input", required=True, help="HERE raw table 路径。")
    parser.add_argument("--output_dir", required=True, help="输出目录。")
    args = parser.parse_args()

    raw = read_table(args.input)
    block_time, cleaning_summary = clean_here(raw)

    out = Path(args.output_dir)
    write_csv(block_time, out / "here_cleaned_block_time.csv")
    write_csv(cleaning_summary, out / "here_cleaning_log_by_date.csv")

    print("HERE 清洗完成。")
    print(f"输出目录: {out}")
    print(f"block-time 记录数: {len(block_time):,}")


if __name__ == "__main__":
    run_cli()
