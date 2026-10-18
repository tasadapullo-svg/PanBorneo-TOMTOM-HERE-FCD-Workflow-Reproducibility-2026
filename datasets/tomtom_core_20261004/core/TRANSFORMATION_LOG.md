# Transformation Log

## 1. Input selection

Read the 24 sanitized TomTom daily exports dated 2025-12-08 through 2025-12-31. Preserve the original files; no source file is overwritten.

## 2. Schema validation

Require all fields listed in `CORE_COLUMNS` in the build script. Stop the build if a required field is absent or a timestamp cannot be parsed.

## 3. Time standardization

Treat historical timestamps as `Asia/Kuching` local time. Round `pd_create_time` to the nearest 15-minute interval. Store both local and UTC interval timestamps and retain the original local timestamps.

## 4. Duplicate resolution

Use `(node_id, interval_timestamp_local)` as the frozen-table key. Sort candidate records by: absolute schedule deviation ascending; batch size descending; confidence descending; capture time ascending; flow UUID ascending. Retain rank 1 and record all candidates in the duplicate log.

Result: 90,930 input rows produced 90,929 frozen rows. One row was removed from one duplicate key. The two candidates had identical current speed, free-flow speed, confidence, and road-closure values.

## 5. Missingness policy

Do not create or impute missing traffic observations in this freeze. Build a complete 2,304-interval calendar audit and report coverage against both the normal 42-record batch target and the 51-node master universe.

## 6. Range and consistency checks

Verify unique frozen keys, required-field completeness, non-negative observed speeds, current speed not exceeding free-flow speed, coordinate consistency, and exact matching against the 39,470-row QC subset.

## 7. Contextual rainfall

Select the 2025-12-08 through 2025-12-31 portion of the existing 51-node hourly rainfall panel. Keep it separate from traffic observations. Verify 29,376 unique node-hour rows, 576 hours, 51 matching node IDs, 15 model grid cells, and no missing precipitation/rain values. Treat these fields as gridded context rather than roadside measurements.

## 8. Provenance and integrity

Record source filename and source CSV row number on every frozen record. Hash every source file and every delivered package file with SHA-256.
