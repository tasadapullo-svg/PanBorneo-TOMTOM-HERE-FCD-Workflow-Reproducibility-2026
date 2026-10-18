# TomTom Core Data Freeze

Freeze ID: `TOMTOM_CORE_20261004`

## Frozen scope

- Provider: TomTom only.
- Source stage: sanitized historical exports; these files are not complete raw API request/response archives.
- Local timezone: `Asia/Kuching`.
- Source period: 2025-12-08 to 2025-12-31 inclusive.
- Source input: 24 daily CSV files and 90,930 rows.
- Frozen output: 90,929 unique node-interval rows.
- Spatial definition: 51 unique fixed coordinate IDs, N001-N051.
- Acquisition definition: a normal scheduled batch contains 42 records; the observed 42-node subset varies by batch.
- Observed 15-minute intervals: 2,166 of 2,304 calendar intervals.
- Coverage against the 42-record batch target: 93.966%.
- Coverage against a complete 51-node panel: 77.384%.
- Contextual rainfall: 29,376 hourly node records, 576 hours, 51 nodes, and 15 model grid cells for the same 24-day period.

## Timestamp and duplicate rule

`pd_create_time` is interpreted as Asia/Kuching local time and rounded to the nearest 15 minutes. Flooring is not used because early source records at `HH:14:59` belong to the next scheduled interval. After nearest-interval normalization, one duplicate node-interval key remained. The selected record minimizes schedule deviation, then prefers the larger batch, higher confidence, earlier capture time, and lexical `flow_uuid`. The discarded duplicate had identical speed, free-flow speed, and confidence values, so the rule does not alter those measurements.

## Validation

The existing 39,470-row, 10-date TomTom QC subset matched the frozen table one-to-one on node and interval. All 39,470 rows matched exactly for current speed, free-flow speed, confidence, and road-closure status.

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
