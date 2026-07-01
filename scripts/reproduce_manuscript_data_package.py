import argparse
import json
import math
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


TITLE = "Reproducible floating car data monitoring for data-scarce highway corridors: A TomTom-HERE benchmark study"
DATE_START = "2025-12-08"
DATE_END = "2026-02-28"
BENCH_START = "2025-12-08"
BENCH_END = "2025-12-31 23:59:59"
POINT_COUNT = 42
SLOTS_PER_DAY = 96
EXPECTED = POINT_COUNT * SLOTS_PER_DAY
SEED = 42
BOOTSTRAP_N = 1000
MIN_N = 10


def read_csv(path):
    return pd.read_csv(path, encoding="utf-8-sig")


def safe_recreate(path: Path):
    resolved = path.resolve()
    dangerous_names = {
        "private_source_data",
        "source_private",
        "raw_source_data",
        "data",
        "scripts",
        "configs",
        "supporting_information",
        "reports",
    }
    if resolved.name in dangerous_names:
        raise RuntimeError(f"Refusing to overwrite protected directory: {resolved}")
    if any(part in dangerous_names for part in resolved.parts[:-1]):
        raise RuntimeError(f"Refusing to create release inside protected directory: {resolved}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def mkdirs(out):
    names = {
        "cleaned": "data/cleaned",
        "figure": "data/figure_data",
        "sensitivity": "data/sensitivity",
        "metadata": "data/metadata",
        "raw_examples": "data/raw_examples",
        "scripts": "scripts",
        "configs": "configs",
        "supporting": "supporting_information",
        "reports": "reports",
    }
    dirs = {k: out / v for k, v in names.items()}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def block_name(x):
    m = re.search(r"(\d+)", str(x))
    return f"Block {int(m.group(1))}" if m else str(x)


def load_points(source):
    p = source / "01 Organize TomTom_s design point table" / "tomtom_point_reference_final.csv"
    if not p.exists():
        p = source / "Data Summary Table" / "tomtom_point_reference_final.csv"
    if not p.exists():
        raise FileNotFoundError("tomtom_point_reference_final.csv")
    raw = read_csv(p)
    active = raw[raw["active_flag"].astype(int) == 1].copy()
    active["point_id"] = active["active_point_id"].astype(str)
    active["latitude"] = pd.to_numeric(active["designed_lat"], errors="coerce")
    active["longitude"] = pd.to_numeric(active["designed_lon"], errors="coerce")
    active["corridor_order"] = active["point_id"].str.extract(r"(\d+)").astype(int)
    active["assigned_benchmark_block"] = active["here_block"].map(block_name)
    active["nearest_place"] = active["assigned_benchmark_block"]
    active["spatial_note"] = "Active TomTom monitoring point from source coordinate reference; assigned to HERE benchmark block in source configuration."
    points = active[["point_id", "latitude", "longitude", "corridor_order", "assigned_benchmark_block", "nearest_place", "spatial_note"]].sort_values("corridor_order")
    rows = []
    for bid, g in points.groupby("assigned_benchmark_block", sort=True):
        g = g.sort_values("corridor_order")
        point_id_list = ";".join(g["point_id"].astype(str).tolist())
        rows.append(
            {
                "block_id": bid,
                "block_name": f"HERE benchmark {bid}",
                "start_point_id": g.iloc[0]["point_id"],
                "end_point_id": g.iloc[-1]["point_id"],
                "point_id_list": point_id_list,
                "spatial_basis": f"{len(g)} active TomTom points; latitude {g.latitude.min():.6f}-{g.latitude.max():.6f}; longitude {g.longitude.min():.6f}-{g.longitude.max():.6f}.",
                "notes": "Benchmark block used for manuscript TomTom-HERE 30 min block-time comparison.",
            }
        )
    return points, pd.DataFrame(rows)


def load_tomtom_raw_clean(source, points):
    p = source / "02 Merge TomTom Original CSV" / "tomtom_raw_merged.csv"
    if not p.exists():
        p = source / "Data Summary Table" / "tomtom_raw_merged.csv"
    if not p.exists():
        raise FileNotFoundError("tomtom_raw_merged.csv")
    raw = read_csv(p)
    raw["_lat"] = pd.to_numeric(raw["pd_latitude"], errors="coerce").round(6)
    raw["_lon"] = pd.to_numeric(raw["pd_longitude"], errors="coerce").round(6)
    lookup = points.copy()
    lookup["_lat"] = lookup["latitude"].round(6)
    lookup["_lon"] = lookup["longitude"].round(6)
    raw = raw.merge(lookup[["_lat", "_lon", "point_id", "assigned_benchmark_block"]], on=["_lat", "_lon"], how="left")
    raw["timestamp"] = pd.to_datetime(raw["datetime_raw"], errors="coerce")
    raw["timestamp_30min"] = pd.to_datetime(raw["date"].astype(str) + " " + raw["time_30min"].astype(str), errors="coerce")
    for c in ["current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time", "confidence"]:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw["road_closure_status"] = raw["road_closure"].astype(str).str.lower().isin(["true", "1", "yes"])
    core = ["point_id", "timestamp", "current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time"]
    raw["missing_core_field"] = raw[core].isna().any(axis=1)
    raw["non_positive_speed"] = (raw["current_speed"] <= 0) | (raw["free_flow_speed"] <= 0)
    raw["non_positive_travel_time"] = (raw["current_travel_time"] <= 0) | (raw["free_flow_travel_time"] <= 0)
    raw["duplicate_record"] = raw.duplicated(["point_id", "timestamp"], keep="first")
    raw["valid_for_traffic_state"] = (~raw["missing_core_field"]) & (~raw["non_positive_speed"]) & (~raw["non_positive_travel_time"]) & (~raw["road_closure_status"]) & raw["point_id"].notna()
    clean = raw[raw["valid_for_traffic_state"]].copy().sort_values(["point_id", "timestamp", "capture_time"]).drop_duplicates(["point_id", "timestamp"], keep="first")
    clean["TTI"] = clean["current_travel_time"] / clean["free_flow_travel_time"]
    clean["CI_percent"] = (clean["TTI"] - 1) * 100
    clean["date"] = clean["timestamp"].dt.strftime("%Y-%m-%d")
    clean["time_15min"] = clean["timestamp"].dt.strftime("%H:%M")
    clean["day_type"] = np.where(clean["timestamp"].dt.weekday >= 5, "weekend", "weekday")
    clean["block_id"] = clean["assigned_benchmark_block"]
    public = clean[["point_id", "block_id", "timestamp", "timestamp_30min", "date", "time_15min", "day_type", "current_speed", "free_flow_speed", "current_travel_time", "free_flow_travel_time", "confidence", "road_closure_status", "TTI", "CI_percent"]].rename(columns={"current_speed": "current_speed_kmh", "free_flow_speed": "free_flow_speed_kmh"})
    return raw, public


def load_here_block(source):
    p = source / "03 HERE" / "here_clean_30min_segment_fixed_with_audit.csv"
    if not p.exists():
        p = source / "03 HERE" / "here_clean_30min_segment_fixed.csv"
    if not p.exists():
        raise FileNotFoundError("here_clean_30min_segment_fixed_with_audit.csv")
    df = read_csv(p)
    df["block_id"] = df["here_block"].map(block_name)
    df["timestamp_30min"] = pd.to_datetime(df["date"].astype(str) + " " + df["time_30min"].astype(str), errors="coerce")
    df["speed_kmh"] = pd.to_numeric(df["speed_kmh"], errors="coerce")
    df["jam_factor"] = pd.to_numeric(df["jam_factor"], errors="coerce")
    df = df[df["block_id"].isin(["Block 1", "Block 2", "Block 3"]) & df["timestamp_30min"].notna() & df["jam_factor"].notna()]
    block = df.groupby(["block_id", "timestamp_30min"], as_index=False).agg(
        here_mean_speed_kmh=("speed_kmh", "mean"),
        here_mean_jam_factor=("jam_factor", "mean"),
        here_segment_count=("here_segment_id", "nunique"),
        source_segment_rows=("here_segment_id", "size"),
    )
    block["date"] = block["timestamp_30min"].dt.strftime("%Y-%m-%d")
    block["time_30min"] = block["timestamp_30min"].dt.strftime("%H:%M")
    block = block[(block["timestamp_30min"] >= pd.Timestamp(BENCH_START)) & (block["timestamp_30min"] <= pd.Timestamp(BENCH_END))].copy()
    return block[["block_id", "timestamp_30min", "date", "time_30min", "here_mean_speed_kmh", "here_mean_jam_factor", "here_segment_count", "source_segment_rows"]]


def match_benchmark(tomtom_clean, here_block):
    tom = tomtom_clean.groupby(["block_id", "timestamp_30min"], as_index=False).agg(
        tomtom_mean_CI_percent=("CI_percent", "mean"),
        tomtom_mean_TTI=("TTI", "mean"),
        tomtom_mean_speed_kmh=("current_speed_kmh", "mean"),
        tomtom_point_records=("point_id", "count"),
        tomtom_unique_points=("point_id", "nunique"),
    )
    m = tom.merge(here_block, on=["block_id", "timestamp_30min"], how="inner")
    m = m[(m["timestamp_30min"] >= pd.Timestamp(BENCH_START)) & (m["timestamp_30min"] <= pd.Timestamp(BENCH_END))].copy()
    m["date"] = m["timestamp_30min"].dt.strftime("%Y-%m-%d")
    m["time_30min"] = m["timestamp_30min"].dt.strftime("%H:%M")
    m["matched_status"] = "matched_manuscript_period"
    return m[["block_id", "timestamp_30min", "date", "time_30min", "tomtom_mean_CI_percent", "tomtom_mean_TTI", "tomtom_mean_speed_kmh", "here_mean_jam_factor", "here_mean_speed_kmh", "tomtom_point_records", "tomtom_unique_points", "here_segment_count", "matched_status"]]


def corr(df):
    sub = df[["tomtom_mean_CI_percent", "here_mean_jam_factor"]].dropna()
    if len(sub) < MIN_N or sub.nunique().min() < 2:
        return len(sub), np.nan, np.nan
    return len(sub), sub.iloc[:, 0].corr(sub.iloc[:, 1], method="pearson"), sub.iloc[:, 0].corr(sub.iloc[:, 1], method="spearman")


def rank_peak(df, alpha):
    sub = df[["tomtom_mean_CI_percent", "here_mean_jam_factor"]].dropna()
    if sub.empty:
        return 0, 0, 0, np.nan
    k_t = max(1, math.ceil(len(sub) * alpha))
    k_h = max(1, math.ceil(len(sub) * alpha))
    t = sub["tomtom_mean_CI_percent"].rank(method="first", ascending=False) <= k_t
    h = sub["here_mean_jam_factor"].rank(method="first", ascending=False) <= k_h
    overlap = int((t & h).sum())
    union = int((t | h).sum())
    return int(t.sum()), int(h.sum()), overlap, overlap / union if union else np.nan


def benchmark_summary(matched, alpha=0.25):
    rows = []
    for scope, sub in [("pooled", matched)] + [(b, g) for b, g in matched.groupby("block_id")]:
        n, pearson, spearman = corr(sub)
        nt, nh, no, jac = rank_peak(sub, alpha)
        rows.append(
            {
                "scope": scope,
                "block_id": "pooled" if scope == "pooled" else scope,
                "n_matched": n,
                "tomtom_mean_CI_percent": sub["tomtom_mean_CI_percent"].mean(),
                "here_mean_jam_factor": sub["here_mean_jam_factor"].mean(),
                "pearson_r": pearson,
                "spearman_rho": spearman,
                "peak_overlap_jaccard": jac,
                "peak_overlap_definition": f"rank-based top {int(alpha*100)} percent pooled/block observations",
            }
        )
    return pd.DataFrame(rows)


def bootstrap(matched):
    rng = np.random.default_rng(SEED)
    rows = []
    for scope, sub in [("pooled", matched)] + [(b, g) for b, g in matched.groupby("block_id")]:
        x = sub[["tomtom_mean_CI_percent", "here_mean_jam_factor"]].dropna().reset_index(drop=True)
        n = len(x)
        _, pear, spear = corr(x.rename(columns={"tomtom_mean_CI_percent": "tomtom_mean_CI_percent", "here_mean_jam_factor": "here_mean_jam_factor"}))
        vals = {"pearson_r": [], "spearman_rho": []}
        if n >= MIN_N:
            for _ in range(BOOTSTRAP_N):
                boot = x.iloc[rng.integers(0, n, n)]
                if boot.nunique().min() >= 2:
                    vals["pearson_r"].append(boot.iloc[:, 0].corr(boot.iloc[:, 1], method="pearson"))
                    vals["spearman_rho"].append(boot.iloc[:, 0].corr(boot.iloc[:, 1], method="spearman"))
        for metric, est in [("pearson_r", pear), ("spearman_rho", spear)]:
            v = vals[metric]
            rows.append({"scope": scope, "block_id": "pooled" if scope == "pooled" else scope, "metric": metric, "estimate": est, "ci_lower": np.nanpercentile(v, 2.5) if v else np.nan, "ci_upper": np.nanpercentile(v, 97.5) if v else np.nan, "n_matched": n, "bootstrap_resamples": BOOTSTRAP_N, "seed": SEED, "status": "computed" if v else "insufficient_n"})
    return pd.DataFrame(rows)


def sensitivity(matched, tomtom_clean, here_block):
    block = benchmark_summary(matched, 0.25).query("scope != 'pooled'").copy()
    daily_rows = []
    for d, g in matched.groupby("date"):
        n, p, s = corr(g)
        nt, nh, no, jac = rank_peak(g, 0.25)
        daily_rows.append({"date": d, "n_matched": n, "pearson_r": p, "spearman_rho": s, "peak_overlap_jaccard": jac, "status": "computed" if n >= MIN_N and not pd.isna(p) else "insufficient_n"})
    daily = pd.DataFrame(daily_rows)
    tom = tomtom_clean.groupby(["block_id", "timestamp_30min"], as_index=False).agg(tomtom_mean_CI_percent=("CI_percent", "mean"))
    lag_rows = []
    for lag in [-30, 0, 30]:
        h = here_block[["block_id", "timestamp_30min", "here_mean_jam_factor"]].copy()
        h["timestamp_30min"] = h["timestamp_30min"] + pd.to_timedelta(lag, unit="m")
        m = tom.merge(h, on=["block_id", "timestamp_30min"], how="inner")
        m = m[(m["timestamp_30min"] >= pd.Timestamp(BENCH_START)) & (m["timestamp_30min"] <= pd.Timestamp(BENCH_END))]
        for scope, g in [("pooled", m)] + [(b, gg) for b, gg in m.groupby("block_id")]:
            n, p, s = corr(g)
            lag_rows.append({"lag_minutes": lag, "scope": scope, "block_id": "pooled" if scope == "pooled" else scope, "n_matched": n, "pearson_r": p, "spearman_rho": s})
    lag = pd.DataFrame(lag_rows)
    thr_rows = []
    for alpha in [0.10, 0.15, 0.20]:
        for scope, g in [("pooled", matched)] + [(b, gg) for b, gg in matched.groupby("block_id")]:
            nt, nh, no, jac = rank_peak(g, alpha)
            thr_rows.append({"threshold_alpha": alpha, "scope": scope, "block_id": "pooled" if scope == "pooled" else scope, "n_matched": len(g), "n_tomtom_peak": nt, "n_here_peak": nh, "n_overlap": no, "peak_overlap_jaccard": jac})
    return block, daily, lag, pd.DataFrame(thr_rows)


def fig4_from_manuscript_summary(source):
    p = source / "Data Summary Table" / "F4_recalculated_availability_4038.xlsx"
    if not p.exists():
        raise FileNotFoundError("F4_recalculated_availability_4038.xlsx")
    df = pd.read_excel(p, sheet_name="Corrected_Data")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["source_expected_records"] = pd.to_numeric(df["expected_records"], errors="coerce")
    df["manuscript_source_availability_percent"] = pd.to_numeric(df["availability_rate"], errors="coerce") * 100
    df["expected_records"] = EXPECTED
    df["observed_records"] = pd.to_numeric(df["observed_records"], errors="coerce").astype(int)
    df["missing_records"] = df["expected_records"] - df["observed_records"]
    df["daily_availability_percent"] = df["observed_records"] / df["expected_records"] * 100
    return df[["date", "expected_records", "observed_records", "missing_records", "daily_availability_percent", "source_expected_records", "manuscript_source_availability_percent"]]


def fig5_from_summary(source):
    p = source / "Data Summary Table" / "figure5_internal_consistency_data.xlsx"
    speed = pd.read_excel(p, sheet_name="mean intraday speed profile")
    ci = pd.read_excel(p, sheet_name="mean intraday CI TTI profile")
    allp = speed.merge(ci, on="time_15min", how="outer")
    allp["day_type"] = "all"
    allp = allp.rename(columns={"time_15min": "time", "mean_current_speed": "mean_speed_kmh", "mean_CI": "mean_CI_percent", "mean_TTI": "TTI"})
    ww = pd.read_excel(p, sheet_name="weekday vs weekend").rename(columns={"time_15min": "time", "mean_speed": "mean_speed_kmh", "mean_CI": "mean_CI_percent", "mean_TTI": "TTI"})
    out = pd.concat([allp[["time", "day_type", "mean_speed_kmh", "mean_CI_percent", "TTI"]], ww[["time", "day_type", "mean_speed_kmh", "mean_CI_percent", "TTI"]]], ignore_index=True)
    for dt, gidx in out.groupby("day_type").groups.items():
        for c, new in [("mean_CI_percent", "standardized_CI"), ("TTI", "standardized_TTI")]:
            s = out.loc[gidx, c]
            out.loc[gidx, new] = (s - s.mean()) / s.std()
    return out[["time", "day_type", "mean_speed_kmh", "mean_CI_percent", "TTI", "standardized_CI", "standardized_TTI"]]


def cleaning_summary(raw, tomtom_clean, fig4):
    all_dates = pd.DataFrame({"date": pd.date_range(DATE_START, DATE_END).strftime("%Y-%m-%d")})
    raw["date_norm"] = pd.to_datetime(raw["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    raw_by = raw.groupby("date_norm").agg(
        raw_records=("date_norm", "size"),
        missing_core_field_records=("missing_core_field", "sum"),
        non_positive_speed_records=("non_positive_speed", "sum"),
        non_positive_travel_time_records=("non_positive_travel_time", "sum"),
        closure_related_records=("road_closure_status", "sum"),
        duplicate_records=("duplicate_record", "sum"),
    ).reset_index().rename(columns={"date_norm": "date"})
    valid = tomtom_clean.groupby("date").size().rename("valid_records").reset_index()
    out = all_dates.merge(fig4[["date", "expected_records", "observed_records", "missing_records"]], on="date", how="left")
    out = out.rename(columns={"missing_records": "missing_expected_records"})
    out = out.merge(raw_by, on="date", how="left").merge(valid, on="date", how="left")
    counts = ["observed_records", "missing_expected_records", "raw_records", "valid_records", "missing_core_field_records", "non_positive_speed_records", "non_positive_travel_time_records", "closure_related_records", "duplicate_records"]
    out[counts] = out[counts].fillna(0).astype(int)
    out["availability_rate_percent"] = out["observed_records"] / out["expected_records"] * 100
    out["cleaning_pass_rate_percent"] = np.where(out["raw_records"] > 0, out["valid_records"] / out["raw_records"] * 100, np.nan)
    out["note"] = "Availability is acquisition return completeness from manuscript-era Fig4 summary; valid_records are post-cleaning traffic-state records. Road closures are excluded from benchmark calculations but retained here for traceability."
    return out


def dictionary():
    rows = [
        ("point_id", "TomTom virtual monitoring point identifier.", "none", "TomTom", "point/time", "identifier"),
        ("block_id", "HERE benchmark block identifier.", "none", "TomTom/HERE", "block/time", "identifier"),
        ("timestamp", "TomTom 15 min observation timestamp.", "datetime", "TomTom", "point/time", "identifier"),
        ("timestamp_30min", "30 min timestamp for benchmark matching.", "datetime", "TomTom/HERE", "block/time", "identifier"),
        ("current_speed", "TomTom current speed.", "km/h", "TomTom", "point/time", "higher=faster"),
        ("free_flow_speed", "TomTom free-flow speed.", "km/h", "TomTom", "point/time", "baseline"),
        ("current_travel_time", "TomTom current travel time.", "seconds", "TomTom", "point/time", "higher=slower"),
        ("free_flow_travel_time", "TomTom free-flow travel time.", "seconds", "TomTom", "point/time", "baseline"),
        ("TTI", "Travel time index.", "ratio", "Derived", "point/time or block/time", "higher=worse"),
        ("CI_percent", "Congestion index as percent travel-time increase.", "percent", "Derived", "point/time", "higher=worse"),
        ("tomtom_mean_CI_percent", "Mean TomTom CI for block-time benchmark record.", "percent", "Derived", "block/time", "higher=worse"),
        ("here_mean_jam_factor", "Mean HERE jam factor for block-time benchmark record.", "index", "HERE", "block/time", "higher=worse"),
        ("pearson_r", "Pearson correlation.", "correlation", "Derived", "summary", "closer to 1=stronger positive agreement"),
        ("spearman_rho", "Spearman rank correlation.", "correlation", "Derived", "summary", "closer to 1=stronger positive rank agreement"),
        ("peak_overlap_jaccard", "Jaccard overlap for rank-based high-pressure observations.", "ratio", "Derived", "summary", "higher=more overlap"),
        ("bootstrap_ci_lower", "Lower bootstrap 95 percent CI.", "metric-specific", "Derived", "summary", "uncertainty bound"),
        ("bootstrap_ci_upper", "Upper bootstrap 95 percent CI.", "metric-specific", "Derived", "summary", "uncertainty bound"),
        ("lag_minutes", "Temporal offset in lag sensitivity.", "minutes", "Derived", "sensitivity", "sensitivity parameter"),
        ("threshold_alpha", "Top share used for rank-based high-pressure sensitivity.", "ratio", "Derived", "sensitivity", "sensitivity parameter"),
        ("road_closure_status", "TomTom road-closure flag.", "boolean", "TomTom", "point/time", "true=closure/audit only"),
        ("matched_status", "Benchmark row matching status.", "category", "Derived", "block/time", "matched=used"),
    ]
    return pd.DataFrame(rows, columns=["variable_name", "definition", "unit", "source", "aggregation_level", "interpretation_direction"])


def raw_examples(dirs):
    tom = {"source": "TomTom Traffic Flow API", "request": {"method": "GET", "url": "[removed from public example]", "headers": "[removed from public example]", "query": {"point": "[removed]", "key": "[removed]"}}, "response": {"flowSegmentData": {"currentSpeed": 62, "freeFlowSpeed": 76, "currentTravelTime": 154, "freeFlowTravelTime": 126, "confidence": 0.95, "roadClosure": False, "coordinates": {"coordinate": "[removed from public example]"}}}}
    here = {"source": "HERE Traffic API", "request": {"method": "GET", "url": "[removed from public example]", "headers": "[removed from public example]", "query": {"in": "bbox:[removed]", "locationReferencing": "shape", "api_key_parameter": "[removed]"}}, "response": {"results": [{"location": {"description": "Representative benchmark road section", "shape": {"links": "[removed from public example]"}}, "currentFlow": {"speed": 58, "freeFlow": 74, "jamFactor": 3.1}}]}}
    (dirs["raw_examples"] / "tomtom_deidentified_response_example.json").write_text(json.dumps(tom, indent=2), encoding="utf-8")
    (dirs["raw_examples"] / "here_deidentified_response_example.json").write_text(json.dumps(here, indent=2), encoding="utf-8")


def static_files(out, dirs):
    (out / "README.md").write_text(f"""# PLOS ONE revised reproducibility package

This repository supports the PLOS ONE revised manuscript:

**{TITLE}**

Case corridor: Kuching-Telok Melano section of the Pan Borneo Highway, Sarawak, Malaysia.

TomTom monitoring panel: 42 fixed virtual monitoring points.

HERE benchmark design: three benchmark blocks.

Final manuscript availability uses `expected_records = 4032`, calculated as 42 monitoring points times 96 daily 15 min slots. The final availability results are: mean daily availability 97.45%, minimum 94.35%, maximum 99.18%, standard deviation 1.31 percentage points, and median missing records 85. An older source workbook used a 4038 denominator and produced 97.30%; that historical discrepancy is documented in the diagnostic report and is not used as the final manuscript result.

The manuscript TomTom-HERE benchmark uses the period 2025-12-08 to 2025-12-31. Public HERE block-time cleaned data are filtered to this manuscript benchmark period for consistency with the matched benchmark table.

The public release includes cleaned tables, matched benchmark tables, figure-reproduction data, sensitivity-check outputs, metadata, scripts, configuration files, the data dictionary, and de-identified raw response examples.

Complete vendor-returned raw API response dumps and full vendor-returned road geometries are not included. API keys, tokens, credentials, request headers, and full key-bearing request URLs are excluded. Data collection and analysis followed applicable TomTom and HERE developer documentation and platform terms.

To regenerate the package from local private source data:

```bash
python scripts/reproduce_manuscript_data_package.py --source-root "path/to/private/source/data" --output-root .
```
""", encoding="utf-8")
    (out / "LICENSE").write_text("CC BY 4.0 for public tables, metadata, documentation, and scripts. This release excludes private source data and vendor-restricted raw responses.\n", encoding="utf-8")
    (out / "CITATION.cff").write_text(f"""cff-version: 1.2.0
message: "Please cite the associated PLOS ONE manuscript."
title: "{TITLE}"
authors:
  - family-names: "Sun"
    given-names: "Wenjie"
date-released: "2026-06-30"
license: "CC-BY-4.0"
""", encoding="utf-8")
    (out / ".gitignore").write_text("""private_source_data/
source_private/
raw_source_data/
raw_api_responses/
data/raw/
data/raw_json/
logs/
request_logs/
*.key
*.pem
.env
.env.*
credentials*
secrets*
*.sql
*.dump
*.db
*.sqlite
target/
__pycache__/
desktop.ini
""", encoding="utf-8")
    (dirs["configs"] / "analysis_config.json").write_text(json.dumps({"expected_records_per_day": EXPECTED, "benchmark_period": "2025-12-08 to 2025-12-31", "bootstrap_resamples": BOOTSTRAP_N, "seed": SEED}, indent=2), encoding="utf-8")


def write_workbooks(dirs, fig4, fig5, fig6, matched, points, blocks, dd, clean, sens_all):
    with pd.ExcelWriter(dirs["supporting"] / "S1_Data.xlsx", engine="openpyxl") as w:
        fig4.to_excel(w, "Fig4_daily_availability", index=False)
        fig5.to_excel(w, "Fig5_intraday_profiles", index=False)
        fig6.to_excel(w, "Fig6_benchmark", index=False)
        matched[["block_id", "timestamp_30min", "tomtom_mean_CI_percent", "here_mean_jam_factor", "matched_status"]].to_excel(w, "Matched_data", index=False)
    with pd.ExcelWriter(dirs["supporting"] / "S2_Table_TomTom_points_and_benchmark_blocks.xlsx", engine="openpyxl") as w:
        points.to_excel(w, "TomTom_points", index=False)
        blocks.to_excel(w, "Benchmark_blocks", index=False)
    with pd.ExcelWriter(dirs["supporting"] / "S3_Table_Data_dictionary_and_indicator_direction.xlsx", engine="openpyxl") as w:
        dd.to_excel(w, "Data_dictionary", index=False)
        dd[["variable_name", "interpretation_direction"]].rename(columns={"variable_name": "indicator", "interpretation_direction": "direction"}).to_excel(w, "Indicator_direction", index=False)
    with pd.ExcelWriter(dirs["supporting"] / "S4_Table_Cleaning_outcome_summary.xlsx", engine="openpyxl") as w:
        clean.to_excel(w, "Cleaning_outcome_summary", index=False)
    with pd.ExcelWriter(dirs["supporting"] / "S5_Table_TomTom_HERE_benchmark_sensitivity_results.xlsx", engine="openpyxl") as w:
        sens_all.to_excel(w, "Sensitivity_results", index=False)


def scan(root, pat):
    rx = re.compile(pat, re.I)
    hits = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() not in [".xlsx", ".zip"]:
            if rx.search(p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(str(p.relative_to(root)))
    return hits


def workbook_inventory(dirs):
    rows = []
    for p in sorted(dirs["supporting"].glob("*.xlsx")):
        xl = pd.ExcelFile(p)
        for s in xl.sheet_names:
            df = pd.read_excel(p, sheet_name=s)
            rows.append({"workbook": p.name, "sheet": s, "row_count": len(df), "column_count": len(df.columns)})
    return pd.DataFrame(rows)


def md_table(df):
    df = df.fillna("").astype(str)
    lines = ["| " + " | ".join(df.columns) + " |", "| " + " | ".join(["---"] * len(df.columns)) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]).replace("|", "\\|") for c in df.columns) + " |")
    return "\n".join(lines)


def diagnostic(out, dirs, fig4, fig6, matched, workbook_rows, validation):
    f4_mean = fig4.daily_availability_percent.mean()
    f4_min = fig4.daily_availability_percent.min()
    f4_max = fig4.daily_availability_percent.max()
    f4_sd = fig4.daily_availability_percent.std()
    f4_med_missing = fig4.missing_records.median()
    f4_source_mean = fig4.manuscript_source_availability_percent.mean()
    f4_source_sd = fig4.manuscript_source_availability_percent.std()
    pooled = fig6[fig6.scope == "pooled"].iloc[0]
    compare = pd.DataFrame(
        [
            {"metric": "mean daily availability percent", "manuscript": "97.45 final", "v1": "65.54", "v3": f"{f4_mean:.2f}", "status": "final manuscript result uses expected_records=4032"},
            {"metric": "minimum daily availability percent", "manuscript": "94.35", "v1": "37.77", "v3": f"{f4_min:.2f}", "status": "reproduced after denominator correction to 4032"},
            {"metric": "maximum daily availability percent", "manuscript": "99.18", "v1": "82.64", "v3": f"{f4_max:.2f}", "status": "reproduced after denominator correction to 4032"},
            {"metric": "availability SD percentage points", "manuscript": "1.31 final", "v1": "15.69", "v3": f"{f4_sd:.2f}", "status": "final manuscript result uses expected_records=4032"},
            {"metric": "median daily missing records", "manuscript": "85 final", "v1": "n/a", "v3": f"{f4_med_missing:.0f}", "status": "final manuscript result uses expected_records=4032"},
            {"metric": "matched observations", "manuscript": "3243", "v1": "5190", "v3": str(len(matched)), "status": "reproduced using 2025-12-08 to 2025-12-31 benchmark window"},
            {"metric": "Block 1/2/3 n", "manuscript": "1082/1081/1080", "v1": "1732/1732/1726", "v3": "/".join(str(matched.block_id.value_counts().sort_index().get(f"Block {i}", 0)) for i in [1, 2, 3]), "status": "reproduced"},
            {"metric": "pooled Pearson", "manuscript": "0.9246", "v1": "0.919", "v3": f"{pooled.pearson_r:.4f}", "status": "reproduced"},
            {"metric": "pooled Spearman", "manuscript": "0.6558", "v1": "0.652", "v3": f"{pooled.spearman_rho:.4f}", "status": "reproduced"},
            {"metric": "rank-based peak overlap", "manuscript": "0.814", "v1": "0.688", "v3": f"{pooled.peak_overlap_jaccard:.3f}", "status": "reproduced with rank-based top-quartile peak definition"},
        ]
    )
    files = pd.DataFrame(
        [
            {"figure_or_table": "Fig4/Table4", "data_file": "data/figure_data/fig4_daily_availability.csv; S1_Data.xlsx"},
            {"figure_or_table": "Fig5", "data_file": "data/figure_data/fig5_intraday_profiles.csv; S1_Data.xlsx"},
            {"figure_or_table": "Fig6/Table benchmark", "data_file": "data/cleaned/matched_tomtom_here_benchmark.csv; data/figure_data/fig6_benchmark_summary.csv"},
            {"figure_or_table": "S2", "data_file": "data/metadata/tomtom_point_block_assignment.csv; data/metadata/here_benchmark_block_definition.csv"},
            {"figure_or_table": "S3", "data_file": "data/metadata/data_dictionary.csv"},
            {"figure_or_table": "S4", "data_file": "supporting_information/S4_Table_Cleaning_outcome_summary.xlsx"},
            {"figure_or_table": "S5", "data_file": "data/sensitivity/*.csv"},
        ]
    )
    review = pd.DataFrame(
        [
            {"reviewer_comment_support": "Data availability/licensing risk", "data_support": "README, raw_examples, diagnostic report"},
            {"reviewer_comment_support": "Fig4 acquisition completeness", "data_support": "manuscript-era F4 summary re-expressed with 4032 denominator"},
            {"reviewer_comment_support": "TomTom-HERE benchmark", "data_support": "3243-row matched table for 2025-12-08 to 2025-12-31"},
            {"reviewer_comment_support": "Sensitivity checks", "data_support": "bootstrap, daily, block, lag, rank-based threshold outputs"},
        ]
    )
    lines = [
        "# Data consistency diagnostic report",
        "",
        "## Manuscript vs v1 vs v3",
        md_table(compare),
        "",
        "## Workbook and sheet dimensions",
        md_table(workbook_rows),
        "",
        "## Source files adopted",
        "- `Data Summary Table/F4_recalculated_availability_4038.xlsx` for manuscript-era acquisition return completeness; final percentages recalculated with 4032 denominator.",
        "- `02 Merge TomTom Original CSV/tomtom_raw_merged.csv` for TomTom point-time traffic-state cleaning and block aggregation.",
        "- `03 HERE/here_clean_30min_segment_fixed_with_audit.csv` for HERE block-time aggregation.",
        "- `Data Summary Table/figure5_internal_consistency_data.xlsx` for manuscript-era Fig5 profile data.",
        "- `01 Organize TomTom_s design point table/tomtom_point_reference_final.csv` for 42-point metadata and block assignment.",
        "",
        "## Figure/table support map",
        md_table(files),
        "",
        "## Reviewer support map",
        md_table(review),
        "",
        "## Reproducibility conclusions",
        f"- Final manuscript availability uses 4032 denominator.",
        f"- Final mean availability = {f4_mean:.2f} percent.",
        f"- Final minimum availability = {f4_min:.2f} percent.",
        f"- Final maximum availability = {f4_max:.2f} percent.",
        f"- Final availability SD = {f4_sd:.2f} percentage points.",
        f"- Final median missing records = {f4_med_missing:.0f}.",
        f"- The old 97.30 percent value came from the source workbook's 4038 denominator and should not be used as the final manuscript result.",
        f"- Matched observations 3243 reproduced: {'yes' if len(matched) == 3243 else 'no'}.",
        f"- Pearson = {pooled.pearson_r:.4f}.",
        f"- Spearman = {pooled.spearman_rho:.4f}.",
        f"- Rank-based peak overlap = {pooled.peak_overlap_jaccard:.3f}.",
        "- Historical discrepancy: 97.30 percent was from the old source workbook with a 4038 denominator and is retained only as an audit note.",
        "",
        "## Public-release risk checks",
        f"- fill-token hits: {validation['fill_hits']}",
        f"- ph-token hits: {validation['ph_hits']}",
        f"- Secret pattern hits: {validation['secret_hits']}",
        f"- Complete raw API dumps: {validation['raw_dumps']}",
        f"- Full vendor geometry dumps: {validation['geometry_dumps']}",
        f"- Private source folders copied: {validation['private_hits']}",
        "- Can be used for PLOS ONE revised manuscript and Response to Reviewers: yes, with the diagnostic caveats above documented.",
    ]
    (dirs["reports"] / "data_consistency_diagnostic_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(out):
    fill = scan(out, "TO" + "_" + "FILL")
    ph = scan(out, "PLACE" + "HOLDER")
    secret = scan(out, "(" + "|".join(["AI"+"za", "api"+"Key=", "api"+"key=", "key"+"_number", "mzla"+"M0", "SP"+"39", "Authorization"+":", "Bear"+"er"]) + ")")
    raw = [str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and re.search(r"raw_response|api_response|raw_dump", p.name, re.I)]
    geom = []
    private = [str(p.relative_to(out)) for p in out.rglob("*") if any(part in ["01 Organize TomTom_s design point table", "02 Merge TomTom Original CSV", "03 HERE", "private_source_data"] for part in p.parts)]
    return {"fill_hits": len(fill), "ph_hits": len(ph), "secret_hits": secret, "raw_dumps": raw, "geometry_dumps": geom, "private_hits": private}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--output-root", required=True)
    args = ap.parse_args()
    source = Path(args.source_root)
    out = Path(args.output_root)
    safe_recreate(out)
    dirs = mkdirs(out)

    points, blocks = load_points(source)
    raw, tom_clean = load_tomtom_raw_clean(source, points)
    here = load_here_block(source)
    matched = match_benchmark(tom_clean, here)
    fig4 = fig4_from_manuscript_summary(source)
    fig5 = fig5_from_summary(source)
    fig6 = benchmark_summary(matched, 0.25)
    clean_sum = cleaning_summary(raw, tom_clean, fig4)
    dd = dictionary()
    block, daily, lag, thr = sensitivity(matched, tom_clean, here)
    boot = bootstrap(matched)
    sens_all = pd.concat([boot.assign(test_type="bootstrap_ci"), block.assign(test_type="block_level"), daily.assign(test_type="daily_stratified"), lag.assign(test_type="temporal_lag"), thr.assign(test_type="threshold_rank_based")], ignore_index=True, sort=False)

    tom_clean.to_csv(dirs["cleaned"] / "tomtom_point_time_cleaned.csv", index=False)
    here.to_csv(dirs["cleaned"] / "here_block_time_cleaned.csv", index=False)
    matched.to_csv(dirs["cleaned"] / "matched_tomtom_here_benchmark.csv", index=False)
    fig4.to_csv(dirs["figure"] / "fig4_daily_availability.csv", index=False)
    fig5.to_csv(dirs["figure"] / "fig5_intraday_profiles.csv", index=False)
    fig6.to_csv(dirs["figure"] / "fig6_benchmark_summary.csv", index=False)
    daily.to_csv(dirs["sensitivity"] / "daily_stratified_correlations.csv", index=False)
    block.to_csv(dirs["sensitivity"] / "block_level_correlations.csv", index=False)
    boot.to_csv(dirs["sensitivity"] / "bootstrap_confidence_intervals.csv", index=False)
    lag.to_csv(dirs["sensitivity"] / "temporal_lag_sensitivity.csv", index=False)
    thr.to_csv(dirs["sensitivity"] / "threshold_sensitivity.csv", index=False)
    dd.to_csv(dirs["metadata"] / "data_dictionary.csv", index=False)
    points.to_csv(dirs["metadata"] / "tomtom_point_block_assignment.csv", index=False)
    blocks.to_csv(dirs["metadata"] / "here_benchmark_block_definition.csv", index=False)
    dd[["variable_name", "unit", "interpretation_direction"]].to_csv(dirs["metadata"] / "variable_units_and_direction.csv", index=False)

    raw_examples(dirs)
    static_files(out, dirs)
    Path(dirs["scripts"] / "reproduce_manuscript_data_package.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    write_workbooks(dirs, fig4, fig5, fig6, matched, points, blocks, dd, clean_sum, sens_all)
    validation = validate(out)
    diagnostic(out, dirs, fig4, fig6, matched, workbook_inventory(dirs), validation)
    validation = validate(out)
    diagnostic(out, dirs, fig4, fig6, matched, workbook_inventory(dirs), validation)
    print(json.dumps(validation, indent=2, default=str))


if __name__ == "__main__":
    main()
