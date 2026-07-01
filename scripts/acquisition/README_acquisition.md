# Acquisition templates

These files are de-identified templates derived from the development acquisition workflow. They document the data-collection logic without exposing credentials, request logs, complete raw API response dumps, or full vendor-returned road geometry.

## TomTom acquisition logic

1. Read 42 fixed monitoring points from `configs/point_panel_config.csv`.
2. Request traffic-flow data from a developer-accessible TomTom traffic API endpoint.
3. Parse current speed, free-flow speed, travel time, confidence, and road-closure status.
4. Save complete raw responses only to private local storage.
5. Export cleaned point-time fields for public reproducibility tables.

## HERE acquisition logic

1. Request HERE traffic-flow data for private benchmark-area definitions.
2. Parse speed, jam factor, confidence, and segment identifiers.
3. Aggregate segment-level records to three benchmark blocks.
4. Match HERE block-time records with TomTom 30 min block-time records.

## Security note

Public scripts are de-identified templates. Users must provide their own valid developer credentials. No credentials, complete raw response dumps, request logs, or full vendor-returned geometries are included in this public release.
