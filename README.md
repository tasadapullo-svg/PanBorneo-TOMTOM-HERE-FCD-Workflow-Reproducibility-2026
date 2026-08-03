# PLOS ONE revised reproducibility package

This repository supports the revised PLOS ONE manuscript:

**Reproducible floating car data monitoring for data-scarce highway corridors: A TomTom-HERE benchmark study**

## Study scope

- Case corridor: Kuching-Telok Melano section of the Pan Borneo Highway, Sarawak, Malaysia.
- TomTom monitoring panel: 42 fixed virtual monitoring points.
- HERE benchmark design: three benchmark blocks.
- Manuscript benchmark period: 2025-12-08 to 2025-12-31.

Final manuscript availability uses `expected_records = 4032`, calculated as 42 monitoring points times 96 daily 15 min slots. The final availability results are: mean daily availability 97.45%, minimum 94.35%, maximum 99.18%, standard deviation 1.31 percentage points, and median missing records 85.

The manuscript TomTom-HERE benchmark contains 3243 matched observations. The pooled benchmark statistics are Pearson r = 0.925, Spearman rho = 0.656, and rank-based peak-overlap index = 0.814.

## API data sources

This repository supports the revised PLOS ONE manuscript. The study used developer-accessible TomTom and HERE traffic API services for academic corridor-monitoring research.

TomTom traffic-flow data were used as the main virtual monitoring source. The TomTom monitoring panel used 42 fixed virtual monitoring points along the Kuching-Telok Melano section of the Pan Borneo Highway, Sarawak, Malaysia.

HERE traffic-flow data were used as an external benchmark source. HERE records were aggregated into three benchmark blocks and matched with TomTom block-time records during the overlapping benchmark period from 2025-12-08 to 2025-12-31.

The acquisition code is provided as de-identified template code to document the data-collection workflow. Users need their own valid TomTom and HERE developer credentials to run acquisition scripts. No API keys, tokens, account credentials, request headers, full key-bearing URLs, request logs, complete raw API dumps, or full vendor-returned road geometries are included.


## Coordinate metadata

The public metadata include the complete TomTom latitude-longitude coordinate set for the 42 virtual monitoring points and the three HERE benchmark bounding boxes used for contextual traffic queries. These files are provided as metadata only and do not contain complete vendor-returned raw road geometry.

Coordinate files:

- `data/metadata/tomtom_point_block_assignment.csv`: 42 TomTom virtual monitoring point coordinates and point-to-block assignment.
- `data/metadata/here_bounding_box_coordinate_set.csv`: four corner coordinates for each of the three HERE benchmark bounding boxes.
- `data/metadata/here_benchmark_block_definition.csv`: block-level definitions, point ID lists, and bounding-box coordinate lists.

## Public release structure

The public release includes:

- cleaned TomTom point-time tables
- cleaned HERE block-time tables
- matched TomTom-HERE benchmark records
- figure-reproduction data
- sensitivity-check outputs
- TomTom point-to-block assignment table
- HERE benchmark-block definition table
- data dictionary
- processing scripts
- configuration templates
- de-identified representative raw API response examples

The public release does not include:

- complete raw API response dumps
- full vendor-returned road geometry dumps
- API keys
- access tokens
- account credentials
- private request headers
- full key-bearing request URLs
- request logs
- local database dumps
- private source-data folders

## Reproducing the public tables

The `scripts/processing/` directory contains de-identified processing scripts derived from the development workflow. The current public package already includes the cleaned and matched outputs used for the revised manuscript. Acquisition templates in `scripts/acquisition/` document the collection logic but require user-supplied developer credentials and should write complete raw responses only to private local storage.
##
20260803 S5_Table_TomTom_HERE_Benchmark_Sensitivity_Results.xlsx
