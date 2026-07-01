"""De-identified processing script copied from the development workflow as clean_tomtom_data.py."""

"""
01_tomtom_cleaning.py
TomTom 15 min 点位数据清洗、质量控制、指标计算、日可用率统计。

对应论文方法：
- Eq. (1): D_clean = raw records that pass all Boolean constraints
- Eq. (2): core-field completeness
- Eq. (3): positive speed constraint
- Eq. (4): positive travel-time constraint
- Eq. (5)-(6): daily cleaned count and cleaning pass rate
- Eq. (7)-(8): daily availability and missing-interval ratio
- Eq. (10)-(14): SRR, TTI, ETT, CI

作者使用建议：
- 本脚本只处理已经导出的 TomTom raw table，不直接请求 TomTom API。
- 论文主分析不建议对缺失值插值，因为插值会虚增 acquisition availability。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


# =========================
# 1. 参数区：与论文保持一致
# =========================

POINT_COUNT = 42                # 论文中的 TomTom 虚拟监测点数量
SLOTS_PER_DAY_15MIN = 96        # 24 h × 4 = 96 个 15 min 时间槽
EXPECTED_RECORDS_PER_DAY = POINT_COUNT * SLOTS_PER_DAY_15MIN  # 42 × 96 = 4032


# 常见字段别名。不同导出表可能使用 currentSpeed/current_speed/v_cur 等字段名。
# 脚本会把这些字段统一改名为标准字段，便于后续复现。
COLUMN_ALIASES: Dict[str, List[str]] = {
    "point_id": ["point_id", "point", "pointid", "site_id", "station_id", "virtual_point_id"],
    "timestamp": ["timestamp", "time", "datetime", "collect_time", "record_time", "created_at"],
    "current_speed": ["current_speed", "currentspeed", "currentSpeed", "v_cur", "speed", "current_speed_kmh"],
    "free_flow_speed": ["free_flow_speed", "freeflowspeed", "freeFlowSpeed", "v_ff", "free_speed", "free_flow_speed_kmh", "free_flow_speedz"],
    "current_travel_time": ["current_travel_time", "currenttraveltime", "currentTravelTime", "tt_cur", "travel_time", "current_travel_time_s"],
    "free_flow_travel_time": ["free_flow_travel_time", "freeflowtraveltime", "freeFlowTravelTime", "tt_ff", "free_travel_time", "free_flow_travel_time_s", "free_flow_travel_timez"],
    "confidence": ["confidence", "conf", "tomtom_confidence"],
    "road_closure": ["road_closure", "roadClosure", "closure", "is_closed", "closed", "road_closed"],
    "segment_id": ["segment_id", "segmentId", "road_segment_id", "frc", "road_id"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng"],
}

CORE_FIELDS = ["point_id", "timestamp", "current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time"]
NUMERIC_FIELDS = ["current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time", "confidence"]


def _standardize_colname(name: str) -> str:
    """把字段名统一成小写、去空格、去常见分隔符，便于别名匹配。"""
    return str(name).strip().replace(" ", "_").replace("-", "_")


def normalize_columns(df: pd.DataFrame, aliases: Dict[str, List[str]] = COLUMN_ALIASES) -> pd.DataFrame:
    """
    将输入表字段名统一为脚本标准字段名。

    参数
    ----
    df : pd.DataFrame
        原始 TomTom 表。
    aliases : dict
        标准字段名与候选字段名的映射。

    返回
    ----
    pd.DataFrame
        字段名已标准化的数据表。
    """
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

    df = df.rename(columns=rename_map)
    return df


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
    raise ValueError(f"不支持的文件格式: {path.suffix}。请使用 .csv, .xlsx, .xls 或 .parquet。")


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    """保存 CSV，并自动创建目录。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def parse_and_standardize_tomtom(raw: pd.DataFrame) -> pd.DataFrame:
    """
    解析 TomTom 原始表，并生成基础时间字段。

    主要处理：
    1. 字段名标准化；
    2. timestamp 转为 pandas datetime；
    3. 生成 date 与 interval_15min；
    4. 数值字段转为 numeric。
    """
    df = normalize_columns(raw)

    missing = [c for c in CORE_FIELDS if c not in df.columns]
    if missing:
        raise ValueError(f"TomTom 输入表缺少核心字段: {missing}。请检查字段名或在 COLUMN_ALIASES 中增加别名。")

    # 时间标准化：无法解析的时间会变成 NaT，后续会被标记为 invalid_time。
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # 论文采样间隔为 15 min。这里统一向下取整到 15 min，避免秒级差异导致重复键不一致。
    df["interval_15min"] = df["timestamp"].dt.floor("15min")
    df["date"] = df["interval_15min"].dt.date

    # 数值字段转为 numeric。无法转换的值变成 NaN，后续进入 missing-field 或 invalid-field 标记。
    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # road_closure 不同表可能是 True/False、0/1、yes/no、closed/open。
    if "road_closure" not in df.columns:
        df["road_closure"] = False
    df["road_closure_bool"] = df["road_closure"].map(_to_bool_closure)

    return df


def _to_bool_closure(value) -> bool:
    """把 road_closure 字段统一为布尔值。True 表示封路记录。"""
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "closed", "closure", "road_closed"}


def add_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    添加质量控制标记，对应论文 Eq. (1)-(4)。

    标记说明：
    - valid_time: 时间可解析，且能映射到 15 min interval。
    - valid_core_fields: 核心字段不缺失。
    - valid_speed: current_speed 和 free_flow_speed 均大于 0。
    - valid_travel_time: current_travel_time 和 free_flow_travel_time 均大于 0。
    - valid_closure: 非封路记录。
    - confidence_exists: confidence 字段存在且非空；如果 raw 表没有 confidence，设为 False 但不强制删除。
    - is_valid: 进入 D_clean 的最终判断。
    """
    df = df.copy()

    df["valid_time"] = df["interval_15min"].notna()

    # Eq. (2): 核心字段完整性。这里把 point_id 与核心交通字段都纳入检查。
    df["valid_core_fields"] = df[CORE_FIELDS].notna().all(axis=1)

    # Eq. (3): 速度字段必须为正。0 或负数不具备常规交通状态解释意义。
    df["valid_speed"] = (df["current_speed"] > 0) & (df["free_flow_speed"] > 0)

    # Eq. (4): 旅行时间字段必须为正。
    df["valid_travel_time"] = (df["current_travel_time"] > 0) & (df["free_flow_travel_time"] > 0)

    # 封路记录不进入 regular traffic-state calculation。
    df["valid_closure"] = ~df["road_closure_bool"]

    # 置信度用于审计。论文 Eq. (1) 写作 C_conf exists for audit checking。
    # 实际数据如果没有 confidence，不建议把全部记录删掉；这里保留 confidence_missing 标记。
    if "confidence" in df.columns:
        df["confidence_exists"] = df["confidence"].notna()
    else:
        df["confidence"] = np.nan
        df["confidence_exists"] = False

    # 主清洗规则：不把 confidence 缺失作为硬删除条件，避免因某些导出表无 confidence 字段而误删全表。
    # 如果你的原始表始终有 confidence，可把 require_confidence=True 传入 clean_tomtom()。
    df["is_valid_base"] = (
        df["valid_time"]
        & df["valid_core_fields"]
        & df["valid_speed"]
        & df["valid_travel_time"]
        & df["valid_closure"]
    )

    return df


def remove_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    根据 point_id + interval_15min 删除重复记录。

    论文逻辑：同一个点位和同一个时间槽只能保留一条记录。
    处理规则：先按 timestamp 排序，再保留第一条 valid record。
    返回：
    - deduped_df: 去重后的表；
    - duplicate_log: 被移除的重复记录，供审计。
    """
    df = df.copy()
    df = df.sort_values(["point_id", "interval_15min", "is_valid_base", "timestamp"], ascending=[True, True, False, True])

    duplicate_mask = df.duplicated(subset=["point_id", "interval_15min"], keep="first")
    duplicate_log = df.loc[duplicate_mask].copy()
    deduped_df = df.loc[~duplicate_mask].copy()

    deduped_df["is_duplicate_removed"] = False
    duplicate_log["is_duplicate_removed"] = True
    return deduped_df, duplicate_log


def compute_tomtom_indicators(clean: pd.DataFrame) -> pd.DataFrame:
    """
    计算 TomTom 交通状态指标，对应论文 Eq. (10)-(14)。

    SRR = (V_ff - V_cur) / V_ff
    TTI = TT_cur / TT_ff
    ETT = TT_cur - TT_ff
    CI  = (TT_cur - TT_ff) / TT_ff * 100 = (TTI - 1) * 100

    注意：
    - 如果平台返回 current_travel_time < free_flow_travel_time，则 CI 为负。
    - 主分析默认不裁剪负值，因为裁剪会人为改变平台信号。
    - 额外生成 ci_negative_flag，便于投稿前检查异常比例。
    """
    df = clean.copy()
    df["srr"] = (df["free_flow_speed"] - df["current_speed"]) / df["free_flow_speed"]
    df["tti"] = df["current_travel_time"] / df["free_flow_travel_time"]
    df["ett_seconds"] = df["current_travel_time"] - df["free_flow_travel_time"]
    df["ci_percent"] = (df["current_travel_time"] - df["free_flow_travel_time"]) / df["free_flow_travel_time"] * 100

    # 用第二种公式复核 CI 是否一致。正常情况下最大误差应接近 0。
    df["ci_percent_from_tti"] = (df["tti"] - 1) * 100
    df["ci_formula_abs_error"] = (df["ci_percent"] - df["ci_percent_from_tti"]).abs()
    df["ci_negative_flag"] = df["ci_percent"] < 0

    return df


def summarize_cleaning_by_date(parsed_with_flags: pd.DataFrame, duplicate_log: pd.DataFrame, cleaned: pd.DataFrame) -> pd.DataFrame:
    """
    生成清洗日志按日汇总表。

    该表可支撑 Supporting Information 中的 Cleaning outcome summary。
    """
    df = parsed_with_flags.copy()

    summary = df.groupby("date", dropna=False).agg(
        raw_records=("point_id", "size"),
        invalid_time_records=("valid_time", lambda x: int((~x).sum())),
        missing_core_field_records=("valid_core_fields", lambda x: int((~x).sum())),
        non_positive_speed_records=("valid_speed", lambda x: int((~x).sum())),
        non_positive_travel_time_records=("valid_travel_time", lambda x: int((~x).sum())),
        closure_related_records=("valid_closure", lambda x: int((~x).sum())),
        confidence_missing_records=("confidence_exists", lambda x: int((~x).sum())),
    ).reset_index()

    dup_by_date = duplicate_log.groupby("date", dropna=False).size().rename("duplicate_records").reset_index()
    valid_by_date = cleaned.groupby("date", dropna=False).size().rename("valid_records").reset_index()

    summary = summary.merge(dup_by_date, on="date", how="left").merge(valid_by_date, on="date", how="left")
    summary["duplicate_records"] = summary["duplicate_records"].fillna(0).astype(int)
    summary["valid_records"] = summary["valid_records"].fillna(0).astype(int)

    # Eq. (6): cleaning pass rate = valid / raw。
    summary["cleaning_pass_rate"] = np.where(
        summary["raw_records"] > 0,
        summary["valid_records"] / summary["raw_records"],
        np.nan,
    )

    return summary.sort_values("date")


def compute_daily_availability(cleaned: pd.DataFrame, expected_per_day: int = EXPECTED_RECORDS_PER_DAY) -> pd.DataFrame:
    """
    计算日可用率，对应论文 Eq. (7)-(8)。

    expected_per_day = 42 × 96 = 4032。
    availability_rate = observed_records / expected_records。
    missing_rate = 1 - availability_rate。
    """
    daily = cleaned.groupby("date").size().rename("observed_records").reset_index()
    daily["expected_records"] = expected_per_day
    daily["availability_rate"] = daily["observed_records"] / daily["expected_records"]
    daily["missing_records"] = daily["expected_records"] - daily["observed_records"]
    daily["missing_rate"] = 1 - daily["availability_rate"]

    # 如果 observed_records > expected_records，说明存在重复键没有被正确处理或点位数不止 42。
    daily["availability_check_flag"] = np.where(
        daily["observed_records"] <= daily["expected_records"],
        "OK",
        "CHECK_OBSERVED_GT_EXPECTED",
    )
    return daily.sort_values("date")


def clean_tomtom(raw: pd.DataFrame, require_confidence: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    TomTom 主清洗函数。

    参数
    ----
    raw : pd.DataFrame
        TomTom 原始表。
    require_confidence : bool
        是否强制要求 confidence 非空。
        - False：推荐默认值。confidence 只用于审计，不因缺失删除。
        - True：严格对应论文 Eq. (1) 中 C_conf=1 的写法。

    返回
    ----
    cleaned : pd.DataFrame
        清洗后且已计算指标的 TomTom point-time 表。
    daily_availability : pd.DataFrame
        日可用率表。
    cleaning_summary : pd.DataFrame
        按日清洗日志汇总表。
    duplicate_log : pd.DataFrame
        重复记录审计表。
    """
    parsed = parse_and_standardize_tomtom(raw)
    flagged = add_quality_flags(parsed)

    if require_confidence:
        flagged["is_valid_base"] = flagged["is_valid_base"] & flagged["confidence_exists"]

    # 先筛选基础有效记录，再按 point_id + interval_15min 去重。
    valid_candidates = flagged.loc[flagged["is_valid_base"]].copy()
    deduped, duplicate_log = remove_duplicates(valid_candidates)
    cleaned = compute_tomtom_indicators(deduped)

    # 生成日期统计。
    daily_availability = compute_daily_availability(cleaned)
    cleaning_summary = summarize_cleaning_by_date(flagged, duplicate_log, cleaned)

    return cleaned, daily_availability, cleaning_summary, duplicate_log


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="TomTom 15 min 点位数据清洗与指标计算。")
    parser.add_argument("--input", required=True, help="TomTom raw table 路径，支持 csv/xlsx/parquet。")
    parser.add_argument("--output_dir", required=True, help="输出目录。")
    parser.add_argument("--require_confidence", action="store_true", help="是否强制要求 confidence 非空。默认不强制。")
    args = parser.parse_args()

    raw = read_table(args.input)
    cleaned, daily, cleaning_summary, duplicate_log = clean_tomtom(raw, require_confidence=args.require_confidence)

    out = Path(args.output_dir)
    write_csv(cleaned, out / "tomtom_cleaned_point_time.csv")
    write_csv(daily, out / "tomtom_daily_availability.csv")
    write_csv(cleaning_summary, out / "tomtom_cleaning_log_by_date.csv")
    write_csv(duplicate_log, out / "tomtom_duplicate_log.csv")

    # 控制台输出关键检查结果，便于投稿前核对。
    max_ci_error = cleaned["ci_formula_abs_error"].max() if not cleaned.empty else np.nan
    print("TomTom 清洗完成。")
    print(f"输出目录: {out}")
    print(f"清洗后记录数: {len(cleaned):,}")
    print(f"日完整记录数 denominator: {EXPECTED_RECORDS_PER_DAY} = {POINT_COUNT} × {SLOTS_PER_DAY_15MIN}")
    print(f"CI 两种公式最大绝对误差: {max_ci_error}")


if __name__ == "__main__":
    run_cli()
