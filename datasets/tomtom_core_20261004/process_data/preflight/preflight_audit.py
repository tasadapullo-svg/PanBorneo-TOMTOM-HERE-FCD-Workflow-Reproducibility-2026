"""Batch 01 only: read frozen inputs; write diagnostics to a fresh output directory.

No imputation, weather retrieval, complete benchmark sample construction,
model fitting, performance scoring, plotting, or edits to source materials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path("D:/HuaweiMoveData/Users/stfr2/Documents/ChatGPT/论文 - 1")
CORE = ROOT / "outputs/TomTom_Core_Freeze_20261004"
PREP = ROOT / "outputs/Manuscript_Preparation_20261006"
SOURCE = Path("D:/山田夫人/论文/论文 - 1/GitHub Coding/Coding-1/Pan-Borneo-Multisource-Highway-Traffic-Dataset-202608-main")
JAVA = ROOT / "source_review/MalaysiaTransportationPlanning1205/MalaysiaTransportationPlanning1205-master/src/main/java/com/utm/traffic"
FIGURES = Path("D:/山田夫人/论文/论文 - 1/图/2026_10_5 图")
TRAFFIC = "tomtom_15min_frozen_2025-12-08_2025-12-31.csv"
RAIN = "rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv"
ZONE = "Asia/Kuching"
ANCHORS = {
    "SHA256_MANIFEST.csv": "b38f799858a7af711a81e217e66390d733ae53c53bc2367cf01c988271116111",
    TRAFFIC: "8fb1bd523b560ca4cfe14c1c4eb258cad2c98fffc570d04119f6a4f26048f36d",
    RAIN: "9c85bd5583577030a760caf70952850da31a458654bf9d23ce25dad2e5b6f5c8",
}
FIGURE_HASHES = {
    "Fig1_study_area_600dpi.tiff": "44807a3d2277219a942fc4dedf4bed788a4e289d5b6b11cabfd7149e0a31b996",
    "Fig2_datarich_notitle_88pt_qc_workflow.png": "f4ed88e1aba1dd8b55a924ed997581220a8350769d89776219412c16aeb94f17",
    "Fig3_coverage_missingness_600dpi.tiff": "0881739274ea2cba8336a6c0e3390330c5fe6c185a002b2398c4da5a954d869a",
    "Fig4_spatiotemporal_traffic_state_labeled_600dpi.tiff": "ef573f75662f2b118c784118e5f924932fc04ac155ac6f1804150231bed39d9d",
    "Fig5_TomTom_HERE_consistency_labeled_600dpi.tiff": "03aaade08e20433a81b6bdf439df42301f16cc7a2b5d65c272af98aaba4ab1ca",
    "Fig6_cross_platform_sensitivity_600dpi.tiff": "a51383b125ddf2e27ea5e19fb4e524d4fd568ab48e8cc15a3928a8de015c0824",
    "Fig7_reconstruction_forecast_benchmarks_600dpi.tiff": "9704dae8490fefb0ce2801eacbb5efe25d1abf9b7a5310e752b81ca15626c1ee",
}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")


def scalar(x):
    if isinstance(x, (list, dict, tuple, set)):
        return x
    return None if pd.isna(x) else (x.item() if isinstance(x, np.generic) else x)


def main(out):
    if not out.resolve().is_relative_to((ROOT / "outputs").resolve()) or out.resolve().is_relative_to(CORE.resolve()):
        raise ValueError("Output must be a separate directory within workspace outputs")
    if (out / "DATA_AUDIT_SUMMARY.json").exists():
        raise FileExistsError("Use a new output directory; existing audit results will not be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc)
    logs, locks, checks = [], [], []

    def log(msg):
        logs.append(f"{datetime.now(timezone.utc).isoformat()} {msg}")
        print(msg, flush=True)

    def save_csv(name, rows):
        pd.DataFrame(rows).to_csv(out / name, index=False, encoding="utf-8", lineterminator="\n")

    def check(name, actual, expected):
        ok = actual == expected
        checks.append({"check": name, "actual": scalar(actual), "expected": scalar(expected), "status": "PASS" if ok else "FAIL"})
        return ok

    def lock(path, role, expected_sha="", expected_bytes=None, basis="recorded this run only"):
        path = path.resolve()
        if any(r["path"] == str(path) for r in locks):
            return
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        digest = sha(path) if exists else ""
        with path.open("rb") if exists else open(__file__, "rb") as f:
            pointer = exists and f.read(150).startswith(b"version https://git-lfs.github.com/spec/v1")
        status = "MISSING" if not exists else "LFS_POINTER" if pointer else "DRIFT" if ((expected_sha and digest != expected_sha) or (expected_bytes is not None and size != expected_bytes)) else "MATCH" if expected_sha else "RECORDED_NO_PRIOR_ANCHOR"
        locks.append({"role": role, "path": str(path), "bytes": size, "expected_bytes": expected_bytes,
                      "sha256": digest, "expected_sha256": expected_sha, "status": status, "anchor_basis": basis})

    try:
        lock(CORE / "SHA256_MANIFEST.csv", "core_manifest", ANCHORS["SHA256_MANIFEST.csv"], 1225, "handoff 20.3 and 16.7")
        if locks[-1]["status"] != "MATCH":
            raise RuntimeError("Core manifest anchor drift; stopping input-dependent diagnostics")
        manifest = pd.read_csv(CORE / "SHA256_MANIFEST.csv")
        assert len(manifest) == 12 and manifest["file"].is_unique
        for r in manifest.to_dict("records"):
            lock(CORE / r["file"], "core_payload", r["sha256"], int(r["bytes"]), "anchored core manifest")
            if r["file"] in ANCHORS:
                check("independent_anchor_" + r["file"], sha(CORE / r["file"]), ANCHORS[r["file"]])
        save_csv("INPUT_LOCK.csv", locks)
        if any(r["status"] != "MATCH" for r in locks) or any(r["status"] == "FAIL" for r in checks):
            raise RuntimeError("Core payload drift; stopping")
        lock(ROOT / "PanBorneo_Quality_Annotated_Multisource_Traffic_Dataset_TRR_Draft.docx", "word_version", "11d40ed028bfb3fb313654f23e9c80a9f0aa2252537ce3ad28e42012bf4e441e", basis="handoff 1/20.3")
        for name, digest in FIGURE_HASHES.items():
            lock(FIGURES / name, "figure_version", digest, basis="handoff 7")
        for name in ("论文写作交接与结果证据清单.md", "新会话启动指令_首批核验.md", "audit_hourly_support.py"):
            lock(PREP / name, "handoff_or_auxiliary")
        main_text = (PREP / "论文写作交接与结果证据清单.md").read_text(encoding="utf-8")
        copy_text = (PREP / "新会话启动指令_首批核验.md").read_text(encoding="utf-8")
        check("startup_body_identical", main_text.split("### 启动任务正文", 1)[1].strip(), copy_text.split("## 启动任务正文", 1)[1].strip())
        # Preserve compact QA rather than duplicate the full instructions.
        checks[-1]["actual"] = checks[-1]["expected"] = "startup body compared character-for-character"
        log("Core 12 payloads plus independent manifest anchor verified; Word and 7 figure versions checked")

        evidence = [
            (SOURCE / "data/rainfall_data/rainfall_data_dictionary.csv", "weather_source_dictionary"),
            (SOURCE / "data/rainfall_data/rainfall_request_manifest.csv", "weather_request_parameters"),
            (SOURCE / "data/rainfall_data/rainfall_grid_mapping_51nodes.csv", "weather_spatial_mapping"),
            (SOURCE / "data/rainfall_data/README.md", "weather_source_notes"),
            (SOURCE / "data/supplementary_data/01_TomTom_Evidence/CAPTURE_PROTOCOL.md", "prospective_capture_protocol"),
            (SOURCE / "data/supplementary_data/01_TomTom_Evidence/raw_evidence_gap_register.csv", "historical_evidence_gaps"),
            (SOURCE / "data/supplementary_data/02_Segment_Registry/node_registry_panborneo.csv", "node_registration"),
            (SOURCE / "data/supplementary_data/02_Segment_Registry/SEGMENT_ID_PROTOCOL.md", "spatial_boundaries"),
            (SOURCE / "data/supplementary_data/02_Segment_Registry/segment_geometry_master.csv", "local_geometry_record"),
            (SOURCE / "data/supplementary_data/02_Segment_Registry/segment_attribute_gap_register.csv", "spatial_attribute_gaps"),
            (JAVA / "impl/DataTomtomCoordinateImpl.java", "capture_timestamp_code_definition"),
            (JAVA / "entity/DataTomtomFlow.java", "flow_timestamp_code_definition"),
            (JAVA / "entity/RedisInternalCombination.java", "point_timestamp_entity"),
            (JAVA / "impl/RedisInternalCombinationImpl.java", "point_creation_code_definition"),
            (JAVA / "utils/PointAllocationUtil.java", "batch_allocation_code"),
            (JAVA / "constant/TomTomCollectorTask.java", "request_then_save_code_order"),
            (Path("D:/山田夫人/论文/论文 - 1/论文数据对应关系_20260927/研究区位置_走廊道路_51节点与气象网格对应关系.md"), "older_spatial_summary_not_authoritative_geometry"),
        ]
        for p, role in evidence:
            lock(p, role)
        source_manifest = pd.read_csv(CORE / "SOURCE_MANIFEST.csv")
        weather_full = SOURCE / "data/rainfall_data/rainfall_hourly_full_3months_51nodes.csv"
        source_r = source_manifest.loc[source_manifest["role"].eq("contextual_covariate_source")].iloc[0]
        lock(weather_full, "actually_used_source_manifest_entry", source_r["sha256"], int(source_r["bytes"]), "core SOURCE_MANIFEST")

        t = pd.read_csv(CORE / TRAFFIC)
        r = pd.read_csv(CORE / RAIN)
        nodes = pd.read_csv(CORE / "tomtom_node_master_51.csv")
        dictionary = pd.read_csv(CORE / "DATA_DICTIONARY.csv")
        for name, frame in ((TRAFFIC, t), (RAIN, r)):
            required = dictionary.loc[dictionary["dataset"].eq(name), "field"].tolist()
            check("required_fields_" + name, sorted(set(required) - set(frame.columns)), [])
            if set(required) - set(frame.columns):
                raise RuntimeError("Required schema field absent")
        check("traffic_rows", len(t), 90929)
        check("rain_rows", len(r), 29376)
        check("traffic_unique_nodes", t.node_id.nunique(), 51)
        check("traffic_duplicates", int(t.duplicated(["node_id", "interval_timestamp_local"]).sum()), 0)
        check("rain_duplicates", int(r.duplicated(["node_id", "timestamp_local"]).sum()), 0)
        check("non_imputed_flags", bool(t.imputed_flag.eq("NO").all() and t.raw_observed_flag.eq("YES").all()), True)
        check("provider", sorted(t.source_provider.unique()), ["TomTom"])
        check("node_universes_equal", set(t.node_id) == set(r.node_id) == set(nodes.node_id), True)
        time_cols = ["pd_create_time_local", "capture_time_local", "flow_create_time_local", "interval_timestamp_local"]
        ts = {c: pd.to_datetime(t[c], format="%Y-%m-%d %H:%M:%S", errors="coerce") for c in time_cols}
        slot, point, cap, flow = [ts[c] for c in ["interval_timestamp_local", "pd_create_time_local", "capture_time_local", "flow_create_time_local"]]
        utc = pd.to_datetime(t.interval_timestamp_utc, utc=True, errors="coerce")
        rtime = pd.to_datetime(r.timestamp_local, format="%Y-%m-%d %H:%M:%S", errors="coerce")
        r_utc = pd.to_datetime(r.timestamp_utc, utc=True, errors="coerce")
        for c in time_cols:
            check(c + "_parse_failures", int(ts[c].isna().sum()), 0)
        check("traffic_timezone", sorted(t.timezone.unique()), [ZONE])
        check("traffic_local_utc_mismatch", int((slot.dt.tz_localize(ZONE).dt.tz_convert("UTC") != utc).sum()), 0)
        check("rain_local_utc_mismatch", int((rtime.dt.tz_localize(ZONE).dt.tz_convert("UTC") != r_utc).sum()), 0)
        round_bad = point.dt.round("15min").ne(slot)
        offset = (point - slot).dt.total_seconds()
        offset_bad = offset.ne(pd.to_numeric(t.timestamp_rounding_offset_seconds, errors="coerce"))
        bound_bad = slot.dt.minute.mod(15).ne(0) | slot.dt.second.ne(0)
        check("nearest_round_mismatch", int(round_bad.sum()), 0)
        check("stored_offset_mismatch", int(offset_bad.sum()), 0)
        check("quarter_hour_boundary_failures", int(bound_bad.sum()), 0)
        check("traffic_window_outside", int((slot.lt("2025-12-08") | slot.ge("2026-01-01")).sum()), 0)
        check("rain_hour_boundary_failures", int((rtime.dt.minute.ne(0) | rtime.dt.second.ne(0)).sum()), 0)
        check("rain_unique_hours", rtime.nunique(), 576)
        check("rain_grid_count", r.weather_grid_id.nunique(), 15)

        deltas = {
            "point_minus_slot_seconds": offset,
            "capture_minus_point_seconds": (cap - point).dt.total_seconds(),
            "capture_minus_slot_seconds": (cap - slot).dt.total_seconds(),
            "flow_minus_capture_seconds": (flow - cap).dt.total_seconds(),
            "flow_minus_point_seconds": (flow - point).dt.total_seconds(),
            "flow_minus_slot_seconds": (flow - slot).dt.total_seconds(),
        }
        groups = [("ALL", t.index)] + list(t.groupby("source_file", sort=True).groups.items())
        time_summary = []
        for group, idx in groups:
            for c in time_cols:
                v = ts[c].loc[idx]
                time_summary.append({"source_file": group, "kind": "timestamp", "field_or_difference": c, "rows": len(idx),
                    "parsed_count": int(v.notna().sum()), "missing_or_invalid_count": int(v.isna().sum()), "minimum": str(v.min()), "maximum": str(v.max())})
            for c, v0 in deltas.items():
                v = v0.loc[idx]
                row = {"source_file": group, "kind": "difference_seconds", "field_or_difference": c, "rows": len(idx),
                       "parsed_count": int(v.notna().sum()), "missing_or_invalid_count": int(v.isna().sum()),
                       "minimum": scalar(v.min()), "maximum": scalar(v.max()), "negative_count": int(v.lt(0).sum()), "zero_count": int(v.eq(0).sum())}
                row.update({f"q{int(q*100):02d}": scalar(v.quantile(q)) for q in (.01, .5, .95, .99)})
                time_summary.append(row)
        save_csv("TIME_FIELD_AUDIT.csv", time_summary)
        masks = {"PARSE_FAIL_" + c: ts[c].isna() for c in time_cols}
        masks.update({"NEAREST_ROUND_MISMATCH": round_bad, "STORED_OFFSET_MISMATCH": offset_bad, "NON_QUARTER_HOUR_SLOT": bound_bad,
            "CAPTURE_BEFORE_POINT_TIME": cap.lt(point), "FLOW_BEFORE_CAPTURE": flow.lt(cap), "CAPTURE_BEFORE_NORMALIZED_SLOT": cap.lt(slot),
            "ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15": cap.gt(slot + pd.Timedelta(minutes=15))})
        anomaly_columns = ["node_id", "source_file", "source_row_number"] + time_cols
        anomaly_rows = []
        for reason, mask in masks.items():
            for idx in t.index[mask.fillna(False)]:
                row = t.loc[idx, anomaly_columns].to_dict()
                row.update({"reason": reason, "frozen_csv_row_number": int(idx) + 2,
                    "capture_minus_slot_seconds": scalar(deltas["capture_minus_slot_seconds"].loc[idx]),
                    "diagnostic_decision_slot_plus15": str(slot.loc[idx] + pd.Timedelta(minutes=15))})
                anomaly_rows.append(row)
        save_csv("TIME_FIELD_ANOMALIES.csv", anomaly_rows or [{c: None for c in anomaly_columns + ["reason"]}])
        anomaly_counts = {reason: int(mask.fillna(False).sum()) for reason, mask in masks.items()}
        cutoff_summary = []
        for name, low, high in [("train", "2025-12-08", "2025-12-24"), ("validation", "2025-12-24", "2025-12-28"), ("test", "2025-12-28", "2026-01-01")]:
            mask = slot.ge(low) & slot.lt(high)
            cutoff_summary.append({"partition": name, "slot_start_inclusive": low, "slot_end_exclusive": high,
                "existing_frozen_rows": int(mask.sum()), "capture_unknown": int((mask & cap.isna()).sum()),
                "capture_at_or_after_partition_cutoff": int((mask & cap.ge(high)).sum()),
                "not_available_at_own_slot_plus15": int((mask & cap.gt(slot + pd.Timedelta(minutes=15))).sum()),
                "scope": "row timestamp diagnostic only; not a benchmark sample set"})
        save_csv("TIME_PARTITION_CUTOFF_AUDIT.csv", cutoff_summary)

        request = pd.read_csv(SOURCE / "data/rainfall_data/rainfall_request_manifest.csv")
        request_audit = []
        request_nodes = []
        for a in request.to_dict("records"):
            u = urlsplit(a["request_url"])
            params = parse_qs(u.query)
            ids = str(a["node_ids"]).split("|")
            request_nodes.extend(ids)
            request_audit.append({"batch_id": a["batch_id"], "node_count": len(ids), "host": u.hostname, "endpoint": u.path,
                "timezone": params.get("timezone", [None])[0], "models": params.get("models", [None])[0],
                "precipitation_unit": params.get("precipitation_unit", [None])[0], "cell_selection": params.get("cell_selection", [None])[0],
                "precipitation_requested": "precipitation" in params.get("hourly", [""])[0].split(","),
                "rain_requested": "rain" in params.get("hourly", [""])[0].split(","), "download_timestamp_utc": a["download_timestamp_utc"],
                "evidence_role": "retained request parameters; not an executed HTTP response archive"})
        save_csv("WEATHER_REQUEST_AUDIT.csv", request_audit)
        check("weather_request_batches", len(request_audit), 7)
        check("request_node_support_exact", sorted(request_nodes), sorted(nodes.node_id.tolist()))
        check("request_mm_units", all(a["precipitation_unit"] == "mm" for a in request_audit), True)
        check("request_timezone", all(a["timezone"] == ZONE for a in request_audit), True)
        check("request_model", all(a["models"] == "ecmwf_ifs" for a in request_audit), True)
        mapping_cols = ["node_id", "node_order_verified", "requested_latitude", "requested_longitude", "weather_grid_id", "returned_grid_latitude", "returned_grid_longitude", "source_model"]
        mapping = r[mapping_cols].drop_duplicates().sort_values("node_order_verified")
        check("stable_mapping_rows", len(mapping), 51)
        coordinate = mapping.merge(nodes[["node_id", "latitude", "longitude"]], on="node_id", validate="one_to_one")
        # Exact float equality compares the same serialized coordinate values, not physical accuracy.
        check("requested_latitudes_match_node_master", bool(coordinate.requested_latitude.eq(coordinate.latitude).all()), True)
        check("requested_longitudes_match_node_master", bool(coordinate.requested_longitude.eq(coordinate.longitude).all()), True)
        save_csv("NODE_GRID_MAPPING_AUDIT.csv", mapping)
        grid_conflicts = {}
        for c in ["precipitation_mm", "rain_mm"]:
            check(c + "_missing", int(r[c].isna().sum()), 0)
            check(c + "_negative", int(r[c].lt(0).sum()), 0)
            grid_conflicts[c] = int(r.groupby(["weather_grid_id", "timestamp_local"])[c].nunique(dropna=False).gt(1).sum())
            check(c + "_grid_hour_conflicts", grid_conflicts[c], 0)

        historical_weather = pd.read_csv(weather_full, usecols=[c for c in r.columns if c != "data_stage"])
        selected_weather = historical_weather.loc[pd.to_datetime(historical_weather.timestamp_local).ge("2025-12-08") & pd.to_datetime(historical_weather.timestamp_local).lt("2026-01-01")]
        compare_cols = [c for c in r.columns if c != "data_stage"]
        rr = r[compare_cols].sort_values(["node_id", "timestamp_local"]).reset_index(drop=True)
        sr = selected_weather[compare_cols].sort_values(["node_id", "timestamp_local"]).reset_index(drop=True)
        check("frozen_weather_matches_historical_source_subset", rr.equals(sr), True)
        # Boundary support only: no speed means, groups, complete hourly panel or formal 5.3 result is created.
        last_hour = slot.ge("2025-12-31 23:00") & slot.lt("2026-01-01")
        last_support = t.loc[last_hour].groupby("node_id").size()
        boundary = [{"node_id": n, "traffic_hour_start": "2025-12-31 23:00:00", "required_weather_endpoint": "2026-01-01 00:00:00",
            "traffic_observation_count": int(last_support.get(n, 0)), "meets_node_hour_minimum3": int(last_support.get(n, 0)) >= 3,
            "frozen_weather_endpoint_present": bool((r.node_id.eq(n) & r.timestamp_local.eq("2026-01-01 00:00:00")).any()),
            "action": "UNMATCHED_IF_NEEDED; no zero fill, timestamp substitution, source extension or download"} for n in sorted(nodes.node_id)]
        save_csv("WEATHER_BOUNDARY_AUDIT.csv", boundary)

        # Trace anomalous times plus three deterministic representative rows back to source CSVs.
        idx_to_trace = sorted(set(t.index[masks["ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15"]]) | {0, len(t)//2, len(t)-1})
        trace = []
        for file, group in t.loc[idx_to_trace].groupby("source_file"):
            entry = source_manifest.loc[source_manifest.relative_path.str.endswith("/" + file)].iloc[0]
            p = SOURCE / entry.relative_path
            lock(p, "actually_used_source_manifest_entry", entry.sha256, int(entry.bytes), "core SOURCE_MANIFEST")
            src = pd.read_csv(p, usecols=["observation_point_id", "pd_create_time", "capture_time", "flow_create_time"])
            for idx, a in group.iterrows():
                b = src.iloc[int(a.source_row_number) - 2]
                matched = (a.node_id == b.observation_point_id and a.pd_create_time_local == b.pd_create_time and a.capture_time_local == b.capture_time and a.flow_create_time_local == b.flow_create_time)
                trace.append({"frozen_csv_row_number": int(idx) + 2, "node_id": a.node_id, "source_file": file, "source_row_number": int(a.source_row_number),
                    "source_time_values_exactly_preserved": bool(matched), "is_delayed_anchor_diagnostic": bool(masks["ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15"].loc[idx])})
        save_csv("SOURCE_ROW_TRACE.csv", trace)
        check("selected_source_time_trace_exact", all(a["source_time_values_exactly_preserved"] for a in trace), True)
        source_entries_used = sum(a["role"] == "actually_used_source_manifest_entry" for a in locks)
        summary = {
            "traffic": {"rows": len(t), "nodes": t.node_id.nunique(), "fields": list(t.columns), "slot_start": str(slot.min()), "slot_end": str(slot.max()),
                "source_daily_files_present_in_frozen": t.source_file.nunique(), "anomaly_counts": anomaly_counts,
                "flow_equals_capture_rows": int(flow.eq(cap).sum()), "flow_after_capture_rows": int(flow.gt(cap).sum()),
                "time_difference_overall": [a for a in time_summary if a["source_file"] == "ALL" and a["kind"] == "difference_seconds"],
                "partition_cutoff_diagnostics": cutoff_summary},
            "background": {"rows": len(r), "hours": rtime.nunique(), "nodes": r.node_id.nunique(), "grid_cells": r.weather_grid_id.nunique(),
                "start": str(rtime.min()), "end": str(rtime.max()), "rain_precipitation_differing_rows": int(r.rain_mm.ne(r.precipitation_mm).sum()),
                "precipitation_tenth_mm_precision": bool(np.allclose(r.precipitation_mm * 10, np.round(r.precipitation_mm * 10), rtol=0, atol=1e-8)),
                "source_models": sorted(r.source_model.unique()), "download_timestamps": sorted(r.download_timestamp.unique()),
                "frozen_jan1_00_endpoint_node_count": sum(a["frozen_weather_endpoint_present"] for a in boundary),
                "historical_source_jan1_00_endpoint_nodes_not_used": int(historical_weather.loc[historical_weather.timestamp_local.eq("2026-01-01 00:00:00"), "node_id"].nunique()),
                "last_traffic_hour_observation_count_distribution_by_node": {str(k): int(v) for k, v in pd.Series([a["traffic_observation_count"] for a in boundary]).value_counts().sort_index().items()},
                "last_hour_nodes_meeting_minimum3": sum(a["meets_node_hour_minimum3"] for a in boundary),
                "mapping_latitude_range": [float(mapping.requested_latitude.min()), float(mapping.requested_latitude.max())],
                "mapping_longitude_range": [float(mapping.requested_longitude.min()), float(mapping.requested_longitude.max())]},
            "evidence_scope": {"source_manifest_entries_used_and_rehashed": source_entries_used, "source_manifest_total_entries": len(source_manifest),
                "traced_source_rows": len(trace), "all_26_sources_rechecked": source_entries_used == 26, "zip_rechecked": False,
                "freeze_rebuild_run": False, "formal_statistics_or_benchmarks_run": False},
        }
        dump(out / "DATA_AUDIT_SUMMARY.json", summary)
        # Confirm each referenced input is unchanged after scanning. This includes Word and figures.
        for a in locks:
            a["sha256_after_scan"] = sha(Path(a["path"])) if Path(a["path"]).is_file() else ""
            a["unchanged_during_scan"] = a["sha256_after_scan"] == a["sha256"]
        save_csv("INPUT_LOCK.csv", locks)
        check("all_read_inputs_unchanged", all(a["unchanged_during_scan"] for a in locks), True)
        check("all_anchored_inputs_match", all(a["status"] == "MATCH" for a in locks if a["expected_sha256"]), True)
        save_csv("QA_CHECKS.csv", checks)
        dump(out / "RUN_CONTEXT.json", {"run_id": "20261006_b01_054939Z", "freeze_id": "TOMTOM_CORE_20261004",
            "started_utc": start.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
            "started_sydney": start.astimezone(ZoneInfo("Australia/Sydney")).isoformat(), "data_timezone": ZONE,
            "output_dir": str(out.resolve()), "script": str(Path(__file__).resolve()), "script_sha256": sha(Path(__file__)),
            "python_executable": sys.executable, "python_version": sys.version, "pandas_version": pd.__version__, "numpy_version": np.__version__, "platform": platform.platform(),
            "argv": sys.argv, "command_scope": "Batch01 read-only-input diagnostics; no formal 5.3/5.4/5.5 results",
            "diagnostic_execution_status": "COMPLETED" if all(c["status"] == "PASS" for c in checks) else "COMPLETED_WITH_FAILED_CHECKS",
            "scientific_acceptance_status": "See human-reviewed BATCH01_ACCEPTANCE.md; computational QA does not resolve source semantics",
            "input_lock_rows": len(locks), "qa_checks": len(checks), "qa_failed": sum(c["status"] == "FAIL" for c in checks)})
        log("Timestamp, source-row, background and boundary diagnostics completed; no benchmark samples or models constructed")
        (out / "RUN_LOG.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
        print(json.dumps({"rows": len(t), "delayed_anchor_rows": anomaly_counts["ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15"], "qa_failures": sum(c["status"] == "FAIL" for c in checks), "source_entries_rehashed": source_entries_used}, ensure_ascii=False))
    except Exception:
        save_csv("INPUT_LOCK.csv", locks)
        save_csv("QA_CHECKS.csv", checks)
        (out / "RUN_FAILURE.txt").write_text(traceback.format_exc(), encoding="utf-8")
        (out / "RUN_LOG.txt").write_text("\n".join(logs) + "\nFAILED; see RUN_FAILURE.txt\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    main(parser.parse_args().output_dir)
