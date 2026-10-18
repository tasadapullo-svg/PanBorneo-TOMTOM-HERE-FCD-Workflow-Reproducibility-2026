# TomTom 51-query-register data and calculation files

Freeze: TOMTOM_CORE_20261004. Assembly: 19 October 2026.
This directory is a separate version of the 8–31 December 2025 TomTom-only
analyses; it does not replace the repository's existing 42-point TomTom–HERE
PLOS ONE package. The 51 registered query IDs (N001–N051) must be distinguished
from the typical acquisition batch of 42 returned records. Observed subsets vary.

## Where each category is stored

| Category | Location | Contents |
|---|---|---|
| Sanitized source inputs | [source_data/](source_data/) | 24 daily sanitized traffic exports (90,930 rows before one duplicate is resolved), the 39,470-row QC subset and the original 110,160-row weather source panel; all 26 inputs match core/SOURCE_MANIFEST.csv. The full weather source has dates outside this study window and is kept only as a build input |
| Frozen observed traffic and weather context | [core/](core/) | 90,929 non-imputed observed traffic records, 29,376 hourly node–weather rows, 51-node master, dictionary, source/QC/transformation logs and original checksum manifest |
| Time, weather and grid audits | [process_data/preflight/](process_data/preflight/) | Source-row trace, timestamp anomalies, weather endpoints and node-to-grid checks; attempt01_failed/ is historical failed audit evidence, not an accepted result |
| Coverage process and calculations | [process_data/coverage_hourly/](process_data/coverage_hourly/) | coverage/ contains daily/node/interval counts and missing episodes; hourly/ contains original-record membership, node hours, joins, retained hours, diurnal/precipitation outputs and sensitivity checks |
| Reconstruction process | [process_data/reconstruction/](process_data/reconstruction/) | inputs/ contains candidate selection, frozen gaps and permitted inputs; reference/ contains withheld provider values; results/ contains point predictions, errors, gap scores and summaries |
| Forecast input admission | [process_data/forecast_admission/](process_data/forecast_admission/) | Exact-slot eligibility, source index, availability strata, sample support and runtime/audit evidence |
| Forecast features, fitting and predictions | [process_data/forecasting/](process_data/forecasting/) | inputs/, features/, models/, validation/ and predictions/ retain the existing calculation outputs; results/ contains test point scores, grouped metrics and paired errors |
| Figure source tables | [figure_data/](figure_data/) | Fig1–Fig5b subdirectories; see [panel mapping](metadata/FIGURE_DATA_MAP.csv) |
| Existing figure assets | [figures/](figures/) | Six existing assets covering Figures 1–4 and the two parts of Figure 5; the supplied 13 October Fig3/Fig4 PNGs are unchanged |
| Calculation and checking code | [code/SOURCE_CODE_INDEX.md](code/SOURCE_CODE_INDEX.md) | Index of original scripts preserved inside core/ and each process_data/ run; package-only verifier is code/verify_release.py |
| File inventory and provenance | [FILE_MANIFEST.csv](metadata/FILE_MANIFEST.csv), [SOURCE_FILE_MAP.csv](metadata/SOURCE_FILE_MAP.csv) | Relative paths, file sizes, CSV row counts, checksums and source mapping |

## Reading the results

Time labels use Asia/Kuching (UTC+08:00) unless explicitly labelled UTC. Speed
and MAE/RMSE are km/h. Empty CSV fields indicate missing or unsupported values,
not zeros. Observed traffic, gridded background, artificial masking,
reconstruction output and forecast output are separate evidence classes.
See [precipitation clarification](metadata/PRECIPITATION_ERRATUM.md): the original
frozen dictionary's mm/hour wording is superseded by preceding-hour accumulation
in mm. Core values and the frozen dictionary have not been modified.

Figure 3 now has three panels: daily record coverage, node missingness and
missing-run counts. Figure 4 has four panels. Historical names Figure7a and
Figure7b correspond to the present Figure5a and Figure5b; source filenames are
retained for traceability. The 602-vertex local geometry reference is derived,
not the full corridor, authoritative road topology or original-response proof.

## Code and verification

Run `python code/verify_release.py` from this directory to check all current
package payload hashes and core counts; it uses only the Python standard library
and does not overwrite data. Historical processing scripts retain their recorded
workstation paths and historical manifests. Relocating them requires configuring
input paths and new output directories; their portability has not been tested by
this assembly. Consult each DATA_GUIDE.md, CONFIG.json and RUN_CONTEXT.json for
method definitions, dependencies, versions and historical execution details.
Assembly copied existing results and did not rerun experiments or produce figures.
Historical manifests inside runs refer to their original directory layouts; the
current package manifest is metadata/FILE_MANIFEST.csv.

To avoid excessively long Windows paths, the original inputs are stored under
short paths in source_data/. metadata/FROZEN_INPUT_MAP.csv maps each one to its
original relative path and hash. Run
`python code/rebuild_frozen_core.py --output-dir NEW_OUTPUT_DIRECTORY` to restore
the original input layout in a temporary directory and invoke the unchanged
core builder. Select a new, separate output directory. pandas is required by
the original builder. This assembly verified source hashes rather than rerunning
that builder.

## Availability and limitations

No complete HTTP response/transport archives, actual online arrival logs or final
Fig3/Fig4 editing programs were found in the collected materials. Figure source
tables and the supplied raster assets are provided, but this is not a claim of
pixel-identical figure regeneration. No new repository DOI, ethics approval or
data-source permission is created by assembling these files. Source-family terms
remain as documented in [core/LICENSE_NOTICE.md](core/LICENSE_NOTICE.md); the
root repository's software licence is not extended here to third-party rights.
Provider observations are reference values, not ground truth. Natural traffic
gaps in core/ remain unfilled. Forecast timing uses a historical record-time
proxy; precipitation group differences are descriptive rather than causal.
