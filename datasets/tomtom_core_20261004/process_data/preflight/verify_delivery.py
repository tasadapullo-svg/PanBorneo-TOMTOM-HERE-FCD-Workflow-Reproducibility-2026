"""Independent key/time validation and final inventory for Batch 01.

Uses csv/datetime for traffic checks, independently of pandas timestamp parsing.
Only writes delivery diagnostics and inventories; does not modify inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_csv(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows, fields):
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(out):
    out = out.resolve()
    if (out / "DELIVERY_QA.json").exists() or (out / "OUTPUT_MANIFEST.csv").exists():
        raise FileExistsError("Final verification exists; use a new delivery or preserve the earlier attempt first")
    summary = json.loads((out / "DATA_AUDIT_SUMMARY.json").read_text(encoding="utf-8"))
    context = json.loads((out / "RUN_CONTEXT.json").read_text(encoding="utf-8"))
    locks = read_csv(out / "INPUT_LOCK.csv")
    qa = []

    def check(name, a, b):
        qa.append({"check": name, "actual": a, "expected": b, "status": "PASS" if a == b else "FAIL"})

    core = Path(next(a["path"] for a in locks if a["role"] == "core_manifest")).parent
    traffic = read_csv(core / "tomtom_15min_frozen_2025-12-08_2025-12-31.csv")
    parse = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    counts, partition, late_partition, keys, delayed_keys = Counter(), Counter(), Counter(), set(), set()
    differences = {"point_minus_slot_seconds": [], "capture_minus_point_seconds": [], "capture_minus_slot_seconds": [], "flow_minus_capture_seconds": []}
    for a in traffic:
        slot, point, cap, flow = [parse(a[c]) for c in ["interval_timestamp_local", "pd_create_time_local", "capture_time_local", "flow_create_time_local"]]
        key = (a["node_id"], a["interval_timestamp_local"])
        counts["duplicate_keys"] += key in keys
        keys.add(key)
        counts["capture_before_point"] += cap < point
        counts["flow_before_capture"] += flow < cap
        counts["capture_before_slot"] += cap < slot
        counts["flow_equals_capture"] += flow == cap
        counts["boundary_failures"] += slot.minute % 15 != 0 or slot.second != 0
        u = datetime.fromisoformat(a["interval_timestamp_utc"].replace("Z", "+00:00"))
        counts["utc_mismatch"] += slot.replace(tzinfo=ZoneInfo("Asia/Kuching")).astimezone(timezone.utc) != u
        offset = (point - slot).total_seconds()
        counts["offset_mismatch"] += offset != float(a["timestamp_rounding_offset_seconds"])
        # Independent nearest-quarter rule; this data has no half-quarter ties.
        origin = point.replace(hour=0, minute=0, second=0)
        seconds = (point - origin).total_seconds()
        counts["half_quarter_ties"] += seconds % 900 == 450
        rounded = origin + timedelta(seconds=900 * int((seconds + 450) // 900))
        counts["round_mismatch"] += rounded != slot
        for name, value in [("point_minus_slot_seconds", offset), ("capture_minus_point_seconds", (cap-point).total_seconds()),
                            ("capture_minus_slot_seconds", (cap-slot).total_seconds()), ("flow_minus_capture_seconds", (flow-cap).total_seconds())]:
            differences[name].append(value)
        split, end = ("train", parse("2025-12-24 00:00:00")) if slot < parse("2025-12-24 00:00:00") else ("validation", parse("2025-12-28 00:00:00")) if slot < parse("2025-12-28 00:00:00") else ("test", parse("2026-01-01 00:00:00"))
        partition[split] += 1
        late_partition[split] += cap >= end
        if cap > slot + timedelta(minutes=15):
            delayed_keys.add((a["node_id"], a["source_file"], a["source_row_number"]))
    check("traffic_rows_from_standard_csv", len(traffic), summary["traffic"]["rows"])
    for name in ["duplicate_keys", "capture_before_point", "flow_before_capture", "capture_before_slot", "boundary_failures", "utc_mismatch", "offset_mismatch", "round_mismatch", "half_quarter_ties"]:
        check("independent_" + name, counts[name], 0)
    check("independent_capture_flow_equality", counts["flow_equals_capture"], summary["traffic"]["flow_equals_capture_rows"])
    for row in summary["traffic"]["time_difference_overall"]:
        name = row["field_or_difference"]
        if name in differences:
            v = differences[name]
            check(name + "_minimum", min(v), row["minimum"])
            check(name + "_maximum", max(v), row["maximum"])
            check(name + "_median", statistics.median(v), row["q50"])
    anomalies = read_csv(out / "TIME_FIELD_ANOMALIES.csv")
    observed_keys = {(a["node_id"], a["source_file"], a["source_row_number"]) for a in anomalies if a["reason"] == "ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15"}
    check("exact_delayed_anchor_key_set", sorted(delayed_keys), sorted(observed_keys))
    check("delayed_anchor_records", len(delayed_keys), summary["traffic"]["anomaly_counts"]["ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15"])
    for a in summary["traffic"]["partition_cutoff_diagnostics"]:
        check(a["partition"] + "_row_count", partition[a["partition"]], a["existing_frozen_rows"])
        check(a["partition"] + "_capture_cutoff", late_partition[a["partition"]], a["capture_at_or_after_partition_cutoff"])
    rainfall = read_csv(core / "rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv")
    check("rainfall_rows_from_standard_csv", len(rainfall), summary["background"]["rows"])
    check("rain_precipitation_unequal_count", sum(float(a["precipitation_mm"]) != float(a["rain_mm"]) for a in rainfall), summary["background"]["rain_precipitation_differing_rows"])
    check("frozen_next_day_endpoint_absent", sum(a["timestamp_local"] == "2026-01-01 00:00:00" for a in rainfall), 0)
    # Exact parsed-number comparison preserves the supplied map; no distance calculation.
    source_map_path = Path(next(a["path"] for a in locks if a["role"] == "weather_spatial_mapping"))
    source_map = {a["node_id"]: a for a in read_csv(source_map_path)}
    frozen_map = {a["node_id"]: a for a in rainfall}
    mapping_mismatches = {}
    for c in ["requested_latitude", "requested_longitude", "returned_grid_latitude", "returned_grid_longitude", "weather_grid_id"]:
        n = sum((a[c] != source_map[node][c]) if c == "weather_grid_id" else (float(a[c]) != float(source_map[node][c])) for node, a in frozen_map.items())
        mapping_mismatches[c] = n
        check("source_frozen_mapping_" + c, n, 0)
    check("source_mapping_nodes", sorted(source_map), sorted(frozen_map))
    needed = ["node_id", "current_speed_kmh", "free_flow_speed_kmh", "confidence", "road_closure", "source_file", "source_row_number"]
    missing_records = sum(any(a[c] == "" for c in needed) for a in traffic)
    check("mandatory_value_missing_records", missing_records, 0)
    check("diagnostic_script_sha_still_matches", digest(Path(context["script"])), context["script_sha256"])
    unchanged = [a["path"] for a in locks if not Path(a["path"]).is_file() or digest(Path(a["path"])) != a["sha256"]]
    check("all_input_hashes_still_unchanged", unchanged, [])
    check("main_machine_QA_failures", sum(a["status"] != "PASS" for a in read_csv(out / "QA_CHECKS.csv")), 0)
    trace = read_csv(out / "SOURCE_ROW_TRACE.csv")
    check("trace_rows", len(trace), summary["evidence_scope"]["traced_source_rows"])
    check("all_delayed_anchors_have_source_trace", sorted(delayed_keys), sorted((a["node_id"], a["source_file"], a["source_row_number"]) for a in trace if a["is_delayed_anchor_diagnostic"] == "True"))
    # Review report references to actual outputs; do not treat prose as computation.
    for name in ["BATCH01_ACCEPTANCE.md", "SEMANTICS_AUDIT.md"]:
        content = (out / name).read_text(encoding="utf-8")
        check(name + "_numbers_present", all(token in content for token in ["90,929", "29,376", "10,019", "9条"]), True)
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "independent_traffic_engine": "Python standard-library csv/datetime/statistics",
              "status": "PASS" if all(a["status"] == "PASS" for a in qa) else "FAIL", "checks": len(qa), "failures": sum(a["status"] == "FAIL" for a in qa),
              "failed_first_attempt_preserved": (out / "attempt01_failed/RUN_FAILURE.txt").is_file(),
              "spatial_mapping_exact_mismatch_counts": mapping_mismatches, "details": qa,
              "scientific_boundary": "Delivery QA checks calculations and file integrity; E02/E03 unresolved semantics remain in the reports"}
    (out / "DELIVERY_QA.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    excluded = {"OUTPUT_MANIFEST.csv", "SHA256_MANIFEST.csv", "MANIFEST_VERIFY.json"}
    rows = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name not in excluded:
            rows.append({"file": p.relative_to(out).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p),
                         "role": "failed_attempt_archive_not_final_result" if "attempt01_failed" in p.parts else "final_diagnostic_delivery"})
    write_csv(out / "OUTPUT_MANIFEST.csv", rows, ["file", "bytes", "sha256", "role"])
    write_csv(out / "SHA256_MANIFEST.csv", [{k: a[k] for k in ["file", "bytes", "sha256"]} for a in rows], ["file", "bytes", "sha256"])
    # SHA list has the same payload rows; no recursive self-inclusion.
    checked = read_csv(out / "OUTPUT_MANIFEST.csv")
    errors = [a["file"] for a in checked if (out/a["file"]).stat().st_size != int(a["bytes"]) or digest(out/a["file"]) != a["sha256"]]
    inventory_check = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "payload_files": len(checked), "payload_errors": errors,
                       "output_manifest_sha256": digest(out / "OUTPUT_MANIFEST.csv"), "sha_manifest_sha256": digest(out / "SHA256_MANIFEST.csv"),
                       "self_inclusion": False, "exclusions": sorted(excluded), "status": "PASS" if not errors else "FAIL"}
    (out / "MANIFEST_VERIFY.json").write_text(json.dumps(inventory_check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"independent_checks": len(qa), "failed_checks": result["failures"], "manifest_payload_files": len(rows), "manifest_status": inventory_check["status"]}, ensure_ascii=False))
    if result["status"] != "PASS" or errors:
        raise RuntimeError("Delivery verification failed; inspect DELIVERY_QA.json/MANIFEST_VERIFY.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    main(parser.parse_args().output_dir)
