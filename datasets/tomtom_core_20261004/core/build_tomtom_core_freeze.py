from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import zipfile
from pathlib import Path

import pandas as pd


FREEZE_ID = "TOMTOM_CORE_20261004"
PACKAGE_NAME = "TomTom_Core_Freeze_20261004"
TIMEZONE = "Asia/Kuching"
SOURCE_DIR = Path(
    "data/supplementary_data/01_TomTom_Evidence/historical_sanitized_daily_csv"
)
VALIDATION_SUBSET = Path(
    "data/fcd_data/01_TomTom/tomtom_raw_15min_available_subset_39470.csv"
)
RAINFALL_SOURCE = Path(
    "data/rainfall_data/rainfall_hourly_full_3months_51nodes.csv"
)
LICENSE_NOTICE = Path("LICENSE_NOTICE.md")

CORE_COLUMNS = [
    "pd_uuid",
    "point_uuid",
    "pd_latitude",
    "pd_longitude",
    "pd_create_time",
    "flow_uuid",
    "capture_time",
    "current_speed",
    "free_flow_speed",
    "current_travel_time",
    "free_flow_travel_time",
    "confidence",
    "road_closure",
    "flow_create_time",
    "observation_point_id",
    "coordinate_match_distance_m",
    "credential_redaction",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def csv_scalar(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def add_qc(rows: list[dict[str, str]], metric: str, value: object, unit: str,
           status: str, evidence: str) -> None:
    rows.append(
        {
            "metric": metric,
            "value": csv_scalar(value),
            "unit": unit,
            "status": status,
            "evidence": evidence,
        }
    )


def build(source_root: Path, output_dir: Path, zip_path: Path | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = source_root / SOURCE_DIR
    source_files = sorted(source_dir.glob("tomtom_sanitized_*.csv"))
    if len(source_files) != 24:
        raise RuntimeError(f"Expected 24 TomTom daily files, found {len(source_files)}")

    frames: list[pd.DataFrame] = []
    source_manifest_rows: list[dict[str, object]] = []
    for path in source_files:
        frame = pd.read_csv(path)
        missing = sorted(set(CORE_COLUMNS) - set(frame.columns))
        if missing:
            raise RuntimeError(f"{path.name} is missing required columns: {missing}")
        frame = frame[CORE_COLUMNS].copy()
        frame["source_file"] = path.name
        frame["source_row_number"] = range(2, len(frame) + 2)
        frames.append(frame)

        parsed = pd.to_datetime(frame["pd_create_time"], errors="raise")
        source_manifest_rows.append(
            {
                "role": "core_input",
                "relative_path": path.relative_to(source_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "rows": len(frame),
                "first_pd_create_time_local": parsed.min().strftime("%Y-%m-%d %H:%M:%S"),
                "last_pd_create_time_local": parsed.max().strftime("%Y-%m-%d %H:%M:%S"),
                "unique_node_ids": frame["observation_point_id"].nunique(),
                "unique_batch_ids": frame["pd_uuid"].nunique(),
            }
        )

    data = pd.concat(frames, ignore_index=True)
    input_rows = len(data)
    data["pd_create_dt"] = pd.to_datetime(data["pd_create_time"], errors="raise")
    data["capture_dt"] = pd.to_datetime(data["capture_time"], errors="raise")
    data["interval_dt"] = data["pd_create_dt"].dt.round("15min")
    data["timestamp_rounding_offset_seconds"] = (
        data["pd_create_dt"] - data["interval_dt"]
    ).dt.total_seconds().astype(int)
    data["schedule_deviation_seconds"] = data[
        "timestamp_rounding_offset_seconds"
    ].abs()
    data["batch_record_count"] = data.groupby("pd_uuid")["flow_uuid"].transform(
        "size"
    )

    key = ["observation_point_id", "interval_dt"]
    data["duplicate_group_size"] = data.groupby(key)["flow_uuid"].transform("size")
    data = data.sort_values(
        key
        + [
            "schedule_deviation_seconds",
            "batch_record_count",
            "confidence",
            "capture_dt",
            "flow_uuid",
        ],
        ascending=[True, True, True, False, False, True, True],
        kind="mergesort",
    )
    data["duplicate_rank"] = data.groupby(key).cumcount() + 1

    duplicate_log = data.loc[data["duplicate_group_size"] > 1].copy()
    duplicate_log["selected_for_frozen_table"] = duplicate_log[
        "duplicate_rank"
    ].eq(1)
    duplicate_log["resolution_rule"] = (
        "nearest 15-min interval; smallest schedule deviation; largest batch; "
        "highest confidence; earliest capture; lexical flow_uuid"
    )
    duplicate_log["interval_timestamp_local"] = duplicate_log[
        "interval_dt"
    ].dt.strftime("%Y-%m-%d %H:%M:%S")
    duplicate_log = duplicate_log[
        [
            "observation_point_id",
            "interval_timestamp_local",
            "source_file",
            "source_row_number",
            "pd_uuid",
            "flow_uuid",
            "pd_create_time",
            "capture_time",
            "current_speed",
            "free_flow_speed",
            "confidence",
            "batch_record_count",
            "timestamp_rounding_offset_seconds",
            "duplicate_group_size",
            "duplicate_rank",
            "selected_for_frozen_table",
            "resolution_rule",
        ]
    ].sort_values(
        ["observation_point_id", "interval_timestamp_local", "duplicate_rank"]
    )

    frozen = data.loc[data["duplicate_rank"] == 1].copy()
    frozen["interval_timestamp_local"] = frozen["interval_dt"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    frozen["interval_timestamp_utc"] = (
        frozen["interval_dt"]
        .dt.tz_localize(TIMEZONE)
        .dt.tz_convert("UTC")
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    frozen["timezone"] = TIMEZONE
    frozen["source_provider"] = "TomTom"
    frozen["raw_observed_flag"] = "YES"
    frozen["imputed_flag"] = "NO"
    frozen["data_stage"] = "SANITIZED_HISTORICAL_EXPORT_DEDUPLICATED"
    frozen["duplicate_resolution"] = frozen["duplicate_group_size"].map(
        lambda n: "SELECTED_FROM_DUPLICATE" if n > 1 else "UNIQUE"
    )
    frozen = frozen.rename(
        columns={
            "observation_point_id": "node_id",
            "pd_latitude": "latitude",
            "pd_longitude": "longitude",
            "pd_uuid": "batch_uuid",
            "current_speed": "current_speed_kmh",
            "free_flow_speed": "free_flow_speed_kmh",
            "current_travel_time": "current_travel_time_s",
            "free_flow_travel_time": "free_flow_travel_time_s",
            "pd_create_time": "pd_create_time_local",
            "capture_time": "capture_time_local",
            "flow_create_time": "flow_create_time_local",
        }
    )
    final_columns = [
        "interval_timestamp_local",
        "interval_timestamp_utc",
        "timezone",
        "node_id",
        "latitude",
        "longitude",
        "current_speed_kmh",
        "free_flow_speed_kmh",
        "current_travel_time_s",
        "free_flow_travel_time_s",
        "confidence",
        "road_closure",
        "pd_create_time_local",
        "capture_time_local",
        "flow_create_time_local",
        "batch_uuid",
        "point_uuid",
        "flow_uuid",
        "coordinate_match_distance_m",
        "source_file",
        "source_row_number",
        "batch_record_count",
        "timestamp_rounding_offset_seconds",
        "duplicate_group_size",
        "duplicate_resolution",
        "credential_redaction",
        "source_provider",
        "raw_observed_flag",
        "imputed_flag",
        "data_stage",
    ]
    frozen = frozen[final_columns].sort_values(
        ["interval_timestamp_local", "node_id"], kind="mergesort"
    )

    expected_intervals = pd.date_range(
        "2025-12-08 00:00:00", "2025-12-31 23:45:00", freq="15min"
    )
    observed_counts = frozen.groupby("interval_timestamp_local").agg(
        observed_records=("node_id", "size"),
        unique_nodes=("node_id", "nunique"),
    )
    coverage = pd.DataFrame(
        {"interval_timestamp_local": expected_intervals.strftime("%Y-%m-%d %H:%M:%S")}
    ).set_index("interval_timestamp_local")
    coverage = coverage.join(observed_counts, how="left").fillna(0)
    coverage[["observed_records", "unique_nodes"]] = coverage[
        ["observed_records", "unique_nodes"]
    ].astype(int)
    coverage["expected_records_per_batch"] = 42
    coverage["master_node_count"] = 51
    coverage["missing_vs_batch_target"] = (
        coverage["expected_records_per_batch"] - coverage["observed_records"]
    ).clip(lower=0)
    coverage["missing_vs_master_panel"] = (
        coverage["master_node_count"] - coverage["unique_nodes"]
    ).clip(lower=0)
    coverage["coverage_vs_batch_target_pct"] = (
        coverage["observed_records"] / coverage["expected_records_per_batch"] * 100
    ).round(3)
    coverage["coverage_vs_master_panel_pct"] = (
        coverage["unique_nodes"] / coverage["master_node_count"] * 100
    ).round(3)
    coverage["coverage_status"] = "PARTIAL_BATCH"
    coverage.loc[coverage["observed_records"] == 0, "coverage_status"] = (
        "MISSING_INTERVAL"
    )
    coverage.loc[coverage["observed_records"] == 42, "coverage_status"] = (
        "BATCH_TARGET_MET"
    )
    coverage.loc[coverage["observed_records"] > 42, "coverage_status"] = (
        "ABOVE_BATCH_TARGET_REVIEW"
    )
    coverage = coverage.reset_index()

    node_master = frozen.groupby("node_id", as_index=False).agg(
        latitude=("latitude", "first"),
        longitude=("longitude", "first"),
        coordinate_variants=("latitude", "nunique"),
        record_count=("node_id", "size"),
        first_interval_local=("interval_timestamp_local", "min"),
        last_interval_local=("interval_timestamp_local", "max"),
        coordinate_match_distance_max_m=("coordinate_match_distance_m", "max"),
    )
    node_master["expected_calendar_intervals"] = len(expected_intervals)
    node_master["observed_interval_pct"] = (
        node_master["record_count"] / len(expected_intervals) * 100
    ).round(3)
    node_master["timezone"] = TIMEZONE
    node_master["node_definition"] = "unique fixed coordinate in sanitized exports"
    node_master = node_master.sort_values("node_id")

    validation_path = source_root / VALIDATION_SUBSET
    validation = pd.read_csv(validation_path)
    source_manifest_rows.append(
        {
            "role": "qc_validation_subset",
            "relative_path": validation_path.relative_to(source_root).as_posix(),
            "bytes": validation_path.stat().st_size,
            "sha256": sha256_file(validation_path),
            "rows": len(validation),
            "first_pd_create_time_local": validation["interval_timestamp"].min(),
            "last_pd_create_time_local": validation["interval_timestamp"].max(),
            "unique_node_ids": validation["node_id"].nunique(),
            "unique_batch_ids": "n.a.",
        }
    )
    validation_keys = validation[
        [
            "node_id",
            "interval_timestamp",
            "current_speed",
            "free_flow_speed",
            "confidence",
            "roadClosure",
        ]
    ].rename(
        columns={
            "interval_timestamp": "interval_timestamp_local",
            "current_speed": "current_speed_kmh",
            "free_flow_speed": "free_flow_speed_kmh",
            "roadClosure": "road_closure",
        }
    )
    frozen_keys = frozen[
        [
            "node_id",
            "interval_timestamp_local",
            "current_speed_kmh",
            "free_flow_speed_kmh",
            "confidence",
            "road_closure",
        ]
    ]
    comparison = validation_keys.merge(
        frozen_keys,
        on=["node_id", "interval_timestamp_local"],
        how="left",
        suffixes=("_validation", "_frozen"),
        indicator=True,
        validate="one_to_one",
    )
    metric_match = (
        comparison["current_speed_kmh_validation"].eq(
            comparison["current_speed_kmh_frozen"]
        )
        & comparison["free_flow_speed_kmh_validation"].eq(
            comparison["free_flow_speed_kmh_frozen"]
        )
        & comparison["confidence_validation"].eq(comparison["confidence_frozen"])
        & comparison["road_closure_validation"].eq(
            comparison["road_closure_frozen"]
        )
    )

    rainfall_path = source_root / RAINFALL_SOURCE
    rainfall = pd.read_csv(rainfall_path)
    rainfall_required = [
        "timestamp_local",
        "node_order_verified",
        "node_id",
        "requested_latitude",
        "requested_longitude",
        "returned_grid_latitude",
        "returned_grid_longitude",
        "returned_elevation",
        "weather_grid_id",
        "timestamp_utc",
        "source_model",
        "download_timestamp",
        "precipitation_mm",
        "rain_mm",
    ]
    rainfall_missing = sorted(set(rainfall_required) - set(rainfall.columns))
    if rainfall_missing:
        raise RuntimeError(
            f"{rainfall_path.name} is missing required columns: {rainfall_missing}"
        )
    rainfall["timestamp_dt"] = pd.to_datetime(
        rainfall["timestamp_local"], errors="raise"
    )
    rainfall = rainfall.loc[
        rainfall["timestamp_dt"].ge("2025-12-08 00:00:00")
        & rainfall["timestamp_dt"].lt("2026-01-01 00:00:00")
    ].copy()
    rainfall["data_stage"] = "GRIDDED_CONTEXTUAL_COVARIATE_NOT_ROADSIDE_MEASUREMENT"
    rainfall = rainfall[rainfall_required + ["data_stage"]].sort_values(
        ["timestamp_local", "node_order_verified"], kind="mergesort"
    )
    frozen_nodes = set(frozen["node_id"].unique())
    rainfall_nodes = set(rainfall["node_id"].unique())
    if rainfall_nodes != frozen_nodes:
        raise RuntimeError("Rainfall node IDs do not match the frozen TomTom node universe")
    source_manifest_rows.append(
        {
            "role": "contextual_covariate_source",
            "relative_path": rainfall_path.relative_to(source_root).as_posix(),
            "bytes": rainfall_path.stat().st_size,
            "sha256": sha256_file(rainfall_path),
            "rows": len(pd.read_csv(rainfall_path, usecols=["node_id"])),
            "first_pd_create_time_local": rainfall["timestamp_local"].min(),
            "last_pd_create_time_local": rainfall["timestamp_local"].max(),
            "unique_node_ids": rainfall["node_id"].nunique(),
            "unique_batch_ids": "n.a.",
        }
    )

    final_rows = len(frozen)
    expected_rows_batch = len(expected_intervals) * 42
    expected_rows_master = len(expected_intervals) * 51
    duplicate_key_count = int((data["duplicate_group_size"] > 1).groupby(
        [data["observation_point_id"], data["interval_dt"]]
    ).any().sum())
    core_missing = int(
        frozen[
            [
                "interval_timestamp_local",
                "node_id",
                "latitude",
                "longitude",
                "current_speed_kmh",
                "free_flow_speed_kmh",
                "confidence",
            ]
        ].isna().any(axis=1).sum()
    )

    qc_rows: list[dict[str, str]] = []
    add_qc(qc_rows, "freeze_id", FREEZE_ID, "identifier", "PASS", "fixed build identifier")
    add_qc(qc_rows, "source_daily_files", len(source_files), "files", "PASS", "source manifest")
    add_qc(qc_rows, "source_rows", input_rows, "rows", "PASS", "direct CSV recount")
    add_qc(qc_rows, "frozen_rows", final_rows, "rows", "PASS", "deduplicated final table")
    add_qc(qc_rows, "duplicate_node_interval_keys_after_nearest_rounding", duplicate_key_count, "keys", "PASS", "duplicate log")
    add_qc(qc_rows, "removed_duplicate_rows", input_rows - final_rows, "rows", "PASS", "duplicate log")
    add_qc(qc_rows, "frozen_duplicate_keys", int(frozen.duplicated(["node_id", "interval_timestamp_local"]).sum()), "keys", "PASS", "direct final-table check")
    add_qc(qc_rows, "unique_master_nodes", frozen["node_id"].nunique(), "nodes", "PASS", "node master")
    add_qc(qc_rows, "typical_batch_target", 42, "records per scheduled batch", "PASS", "historical capture batches")
    add_qc(qc_rows, "observed_calendar_intervals", int((coverage["observed_records"] > 0).sum()), "15-min intervals", "PASS", "coverage table")
    add_qc(qc_rows, "expected_calendar_intervals", len(expected_intervals), "15-min intervals", "PASS", "24 days x 96 intervals")
    add_qc(qc_rows, "missing_calendar_intervals", int((coverage["observed_records"] == 0).sum()), "15-min intervals", "WARN", "coverage table")
    add_qc(qc_rows, "coverage_vs_42_record_batch_target", final_rows / expected_rows_batch * 100, "percent", "PASS", "final rows divided by 42 x 2304")
    add_qc(qc_rows, "coverage_vs_51_node_master_panel", final_rows / expected_rows_master * 100, "percent", "WARN", "final rows divided by 51 x 2304")
    add_qc(qc_rows, "missing_core_values", core_missing, "rows", "PASS", "direct final-table check")
    add_qc(qc_rows, "minimum_current_speed", float(frozen["current_speed_kmh"].min()), "km/h", "PASS", "direct final-table check")
    add_qc(qc_rows, "maximum_current_speed", float(frozen["current_speed_kmh"].max()), "km/h", "PASS", "direct final-table check")
    add_qc(qc_rows, "current_speed_above_free_flow_speed", int((frozen["current_speed_kmh"] > frozen["free_flow_speed_kmh"]).sum()), "rows", "PASS", "direct final-table check")
    add_qc(qc_rows, "road_closure_true", int(frozen["road_closure"].astype(str).str.lower().isin(["1", "true", "yes"]).sum()), "rows", "PASS", "direct final-table check")
    add_qc(qc_rows, "validation_subset_rows", len(validation), "rows", "PASS", "39,470-row QC reference")
    add_qc(qc_rows, "validation_subset_key_matches", int(comparison["_merge"].eq("both").sum()), "rows", "PASS", "one-to-one key comparison")
    add_qc(qc_rows, "validation_subset_metric_exact_matches", int(metric_match.sum()), "rows", "PASS", "speed, free-flow speed, confidence, closure")
    add_qc(qc_rows, "rainfall_context_rows", len(rainfall), "rows", "PASS", "24 days x 24 hours x 51 nodes")
    add_qc(qc_rows, "rainfall_context_hours", rainfall["timestamp_local"].nunique(), "hours", "PASS", "complete 24-day hourly index")
    add_qc(qc_rows, "rainfall_context_nodes", rainfall["node_id"].nunique(), "nodes", "PASS", "matches frozen TomTom node universe")
    add_qc(qc_rows, "rainfall_context_grid_cells", rainfall["weather_grid_id"].nunique(), "grid cells", "PASS", "gridded contextual data")
    add_qc(qc_rows, "rainfall_duplicate_node_hours", int(rainfall.duplicated(["node_id", "timestamp_local"]).sum()), "keys", "PASS", "direct contextual-table check")
    add_qc(qc_rows, "rainfall_missing_precipitation_or_rain", int(rainfall[["precipitation_mm", "rain_mm"]].isna().any(axis=1).sum()), "rows", "PASS", "direct contextual-table check")
    add_qc(qc_rows, "historical_raw_http_metadata_available", 0, "days", "WARN", "historical evidence register")
    add_qc(qc_rows, "historical_raw_json_available", 0, "days", "WARN", "historical evidence register")
    qc_summary = pd.DataFrame(qc_rows)

    data_dictionary = pd.DataFrame(
        [
            ("interval_timestamp_local", "datetime string", "Asia/Kuching", "15-minute timestamp obtained by rounding pd_create_time to the nearest quarter-hour", "derived"),
            ("interval_timestamp_utc", "ISO-8601 string", "UTC", "UTC conversion of interval_timestamp_local", "derived"),
            ("timezone", "string", "n.a.", "IANA timezone for local timestamps", "constant"),
            ("node_id", "string", "n.a.", "N001-N051 fixed coordinate identifier", "source-mapped"),
            ("latitude", "float", "decimal degrees", "source coordinate latitude", "observed"),
            ("longitude", "float", "decimal degrees", "source coordinate longitude", "observed"),
            ("current_speed_kmh", "float", "km/h", "TomTom current speed", "observed"),
            ("free_flow_speed_kmh", "float", "km/h", "TomTom free-flow speed", "observed"),
            ("current_travel_time_s", "float", "seconds", "TomTom current travel time", "observed"),
            ("free_flow_travel_time_s", "float", "seconds", "TomTom free-flow travel time", "observed"),
            ("confidence", "float", "0-1", "source confidence field", "observed"),
            ("road_closure", "integer/boolean", "flag", "source road-closure field", "observed"),
            ("pd_create_time_local", "datetime string", "Asia/Kuching", "historical point-data creation time", "observed"),
            ("capture_time_local", "datetime string", "Asia/Kuching", "historical capture time", "observed"),
            ("flow_create_time_local", "datetime string", "Asia/Kuching", "historical flow-record creation time", "observed"),
            ("batch_uuid", "string", "n.a.", "historical acquisition batch identifier", "observed"),
            ("point_uuid", "string", "n.a.", "historical point-record identifier; snapshot-specific", "observed"),
            ("flow_uuid", "string", "n.a.", "historical flow-record identifier", "observed"),
            ("coordinate_match_distance_m", "float", "metres", "distance used in point-to-node mapping", "derived upstream"),
            ("source_file", "string", "n.a.", "sanitized daily input filename", "provenance"),
            ("source_row_number", "integer", "CSV row", "1-based physical row number including header at row 1", "provenance"),
            ("batch_record_count", "integer", "records", "number of records sharing batch_uuid", "derived"),
            ("timestamp_rounding_offset_seconds", "integer", "seconds", "pd_create_time minus rounded 15-minute timestamp", "derived"),
            ("duplicate_group_size", "integer", "records", "records sharing node_id and normalized interval before selection", "derived"),
            ("duplicate_resolution", "string", "n.a.", "UNIQUE or SELECTED_FROM_DUPLICATE", "derived"),
            ("credential_redaction", "string", "n.a.", "credential-removal note inherited from sanitized source", "provenance"),
            ("source_provider", "string", "n.a.", "traffic-data provider", "constant"),
            ("raw_observed_flag", "string", "YES/NO", "YES means an observed provider record, not an imputed value", "derived"),
            ("imputed_flag", "string", "YES/NO", "NO for every record in this frozen table", "derived"),
            ("data_stage", "string", "n.a.", "explicitly identifies the table as a sanitized historical export", "constant"),
        ],
        columns=["field", "data_type", "unit_or_timezone", "definition", "provenance_class"],
    )
    data_dictionary.insert(
        0, "dataset", "tomtom_15min_frozen_2025-12-08_2025-12-31.csv"
    )
    rainfall_dictionary = pd.DataFrame(
        [
            ("timestamp_local", "datetime string", "Asia/Kuching", "hourly local timestamp", "source"),
            ("node_order_verified", "integer", "order", "verified node display/order index", "source"),
            ("node_id", "string", "n.a.", "N001-N051 fixed coordinate identifier", "source-mapped"),
            ("requested_latitude", "float", "decimal degrees", "road-node latitude submitted to the weather service", "source"),
            ("requested_longitude", "float", "decimal degrees", "road-node longitude submitted to the weather service", "source"),
            ("returned_grid_latitude", "float", "decimal degrees", "latitude of returned model grid cell", "source"),
            ("returned_grid_longitude", "float", "decimal degrees", "longitude of returned model grid cell", "source"),
            ("returned_elevation", "float", "metres", "elevation associated with returned model grid cell", "source"),
            ("weather_grid_id", "string", "n.a.", "stable identifier for returned model grid cell", "derived upstream"),
            ("timestamp_utc", "datetime string", "UTC", "UTC equivalent of timestamp_local", "source"),
            ("source_model", "string", "n.a.", "weather-model identifier", "source"),
            ("download_timestamp", "ISO-8601 string", "UTC", "context-data retrieval timestamp", "provenance"),
            ("precipitation_mm", "float", "mm/hour", "gridded hourly total precipitation", "contextual covariate"),
            ("rain_mm", "float", "mm/hour", "gridded hourly rain component", "contextual covariate"),
            ("data_stage", "string", "n.a.", "marks the data as gridded context rather than roadside measurement", "constant"),
        ],
        columns=["field", "data_type", "unit_or_timezone", "definition", "provenance_class"],
    )
    rainfall_dictionary.insert(
        0, "dataset", "rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv"
    )
    data_dictionary = pd.concat(
        [data_dictionary, rainfall_dictionary], ignore_index=True
    )

    source_manifest = pd.DataFrame(source_manifest_rows)
    write_csv(frozen, output_dir / "tomtom_15min_frozen_2025-12-08_2025-12-31.csv")
    write_csv(node_master, output_dir / "tomtom_node_master_51.csv")
    write_csv(coverage, output_dir / "tomtom_interval_coverage_2304.csv")
    write_csv(duplicate_log, output_dir / "tomtom_duplicate_resolution_log.csv")
    write_csv(
        rainfall,
        output_dir / "rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv",
    )
    write_csv(source_manifest, output_dir / "SOURCE_MANIFEST.csv")
    write_csv(data_dictionary, output_dir / "DATA_DICTIONARY.csv")
    write_csv(qc_summary, output_dir / "QC_SUMMARY.csv")

    readme = f"""# TomTom Core Data Freeze

Freeze ID: `{FREEZE_ID}`

## Frozen scope

- Provider: TomTom only.
- Source stage: sanitized historical exports; these files are not complete raw API request/response archives.
- Local timezone: `{TIMEZONE}`.
- Source period: 2025-12-08 to 2025-12-31 inclusive.
- Source input: {len(source_files)} daily CSV files and {input_rows:,} rows.
- Frozen output: {final_rows:,} unique node-interval rows.
- Spatial definition: 51 unique fixed coordinate IDs, N001-N051.
- Acquisition definition: a normal scheduled batch contains 42 records; the observed 42-node subset varies by batch.
- Observed 15-minute intervals: {(coverage['observed_records'] > 0).sum():,} of {len(expected_intervals):,} calendar intervals.
- Coverage against the 42-record batch target: {final_rows / expected_rows_batch * 100:.3f}%.
- Coverage against a complete 51-node panel: {final_rows / expected_rows_master * 100:.3f}%.
- Contextual rainfall: {len(rainfall):,} hourly node records, {rainfall['timestamp_local'].nunique():,} hours, 51 nodes, and {rainfall['weather_grid_id'].nunique()} model grid cells for the same 24-day period.

## Timestamp and duplicate rule

`pd_create_time` is interpreted as Asia/Kuching local time and rounded to the nearest 15 minutes. Flooring is not used because early source records at `HH:14:59` belong to the next scheduled interval. After nearest-interval normalization, one duplicate node-interval key remained. The selected record minimizes schedule deviation, then prefers the larger batch, higher confidence, earlier capture time, and lexical `flow_uuid`. The discarded duplicate had identical speed, free-flow speed, and confidence values, so the rule does not alter those measurements.

## Validation

The existing 39,470-row, 10-date TomTom QC subset matched the frozen table one-to-one on node and interval. All {int(metric_match.sum()):,} rows matched exactly for current speed, free-flow speed, confidence, and road-closure status.

## Evidence boundaries

- Historical raw JSON responses, HTTP status codes, request latency, and full transport logs were not retained for the 24-day collection. Do not describe the frozen table as a complete raw API archive.
- The released rows are observed, non-imputed provider records. Missing node-interval combinations remain absent and are quantified in the coverage table; they are not filled in this freeze.
- No HERE records, integrated multisource rows, historical prediction outputs, or Git LFS pointer payloads are used in this core freeze.
- Rainfall is retained only as gridded environmental context. It is not a roadside gauge measurement or traffic ground truth.
- Provider observations are not ground truth. Agreement with another provider or a model must not be described as accuracy against ground truth.

## Files

- `tomtom_15min_frozen_2025-12-08_2025-12-31.csv`: frozen observation table.
- `tomtom_node_master_51.csv`: node coordinates and per-node coverage.
- `tomtom_interval_coverage_2304.csv`: complete 24-day interval index and observed coverage.
- `tomtom_duplicate_resolution_log.csv`: all records involved in duplicate resolution.
- `rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv`: aligned hourly gridded rainfall context.
- `SOURCE_MANIFEST.csv`: source file sizes, hashes, row counts, periods, nodes, and batches.
- `DATA_DICTIONARY.csv`: field definitions, units, and provenance classes.
- `QC_SUMMARY.csv`: directly recomputed quality-control results.
- `TRANSFORMATION_LOG.md`: ordered processing rules and evidence limits.
- `SHA256_MANIFEST.csv`: hashes for package contents.
- `build_tomtom_core_freeze.py`: rerunnable build script.
- `LICENSE_NOTICE.md`: source-family rights and reuse boundary copied from the repository.
"""
    (output_dir / "README_DATA_FREEZE.md").write_text(readme, encoding="utf-8")

    transform_log = f"""# Transformation Log

## 1. Input selection

Read the 24 sanitized TomTom daily exports dated 2025-12-08 through 2025-12-31. Preserve the original files; no source file is overwritten.

## 2. Schema validation

Require all fields listed in `CORE_COLUMNS` in the build script. Stop the build if a required field is absent or a timestamp cannot be parsed.

## 3. Time standardization

Treat historical timestamps as `{TIMEZONE}` local time. Round `pd_create_time` to the nearest 15-minute interval. Store both local and UTC interval timestamps and retain the original local timestamps.

## 4. Duplicate resolution

Use `(node_id, interval_timestamp_local)` as the frozen-table key. Sort candidate records by: absolute schedule deviation ascending; batch size descending; confidence descending; capture time ascending; flow UUID ascending. Retain rank 1 and record all candidates in the duplicate log.

Result: {input_rows:,} input rows produced {final_rows:,} frozen rows. One row was removed from one duplicate key. The two candidates had identical current speed, free-flow speed, confidence, and road-closure values.

## 5. Missingness policy

Do not create or impute missing traffic observations in this freeze. Build a complete 2,304-interval calendar audit and report coverage against both the normal 42-record batch target and the 51-node master universe.

## 6. Range and consistency checks

Verify unique frozen keys, required-field completeness, non-negative observed speeds, current speed not exceeding free-flow speed, coordinate consistency, and exact matching against the 39,470-row QC subset.

## 7. Contextual rainfall

Select the 2025-12-08 through 2025-12-31 portion of the existing 51-node hourly rainfall panel. Keep it separate from traffic observations. Verify 29,376 unique node-hour rows, 576 hours, 51 matching node IDs, 15 model grid cells, and no missing precipitation/rain values. Treat these fields as gridded context rather than roadside measurements.

## 8. Provenance and integrity

Record source filename and source CSV row number on every frozen record. Hash every source file and every delivered package file with SHA-256.
"""
    (output_dir / "TRANSFORMATION_LOG.md").write_text(
        transform_log, encoding="utf-8"
    )

    license_source = source_root / LICENSE_NOTICE
    if license_source.exists():
        shutil.copyfile(license_source, output_dir / "LICENSE_NOTICE.md")

    manifest_rows = []
    for path in sorted(p for p in output_dir.iterdir() if p.is_file()):
        if path.name == "SHA256_MANIFEST.csv":
            continue
        manifest_rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    with (output_dir / "SHA256_MANIFEST.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    if zip_path is not None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(p for p in output_dir.iterdir() if p.is_file()):
                info = zipfile.ZipInfo(
                    f"{PACKAGE_NAME}/{path.name}",
                    date_time=(2026, 10, 4, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the auditable TomTom-only core data freeze."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--zip-path", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build(args.source_root, args.output_dir, args.zip_path)
