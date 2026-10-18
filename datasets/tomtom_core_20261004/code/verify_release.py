from pathlib import Path
import csv, hashlib, json

base = Path(__file__).resolve().parents[1]
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()
def count(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return sum(1 for _ in csv.DictReader(f))
with (base/'metadata/FILE_MANIFEST.csv').open(encoding='utf-8-sig', newline='') as f:
    entries = list(csv.DictReader(f))
for e in entries:
    path = (base/e['path']).resolve()
    assert path.is_relative_to(base.resolve()), e['path']
    assert path.stat().st_size == int(e['bytes']), e['path']
    assert sha(path) == e['sha256'], e['path']
    if e['csv_rows'] != '': assert count(path) == int(e['csv_rows']), e['path']
checks = {
    'traffic_rows': count(base/'core/tomtom_15min_frozen_2025-12-08_2025-12-31.csv'),
    'weather_rows': count(base/'core/rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv'),
    'nodes': count(base/'core/tomtom_node_master_51.csv'),
    'calendar_slots': count(base/'core/tomtom_interval_coverage_2304.csv'),
    'missing_runs': count(base/'process_data/coverage_hourly/coverage/MISSING_EPISODES.csv'),
    'retained_precipitation_hours': count(base/'figure_data/Fig4/PRECIPITATION_GROUP_HOUR_SAMPLES.csv'),
}
assert checks == dict(traffic_rows=90929, weather_rows=29376, nodes=51, calendar_slots=2304, missing_runs=16447, retained_precipitation_hours=521), checks
with (base/'core/SOURCE_MANIFEST.csv').open(encoding='utf-8-sig', newline='') as f:
    inputs = list(csv.DictReader(f))
with (base/'metadata/FROZEN_INPUT_MAP.csv').open(encoding='utf-8-sig', newline='') as f:
    mapping = {e['original_relative_path']: e['packaged_path'] for e in csv.DictReader(f)}
for e in inputs:
    p = base/mapping[e['relative_path']]
    assert sha(p) == e['sha256'], e['relative_path']
    assert count(p) == int(e['rows']), e['relative_path']
print(json.dumps(dict(status='PASS', verified_payload_files=len(entries), counts=checks)))
