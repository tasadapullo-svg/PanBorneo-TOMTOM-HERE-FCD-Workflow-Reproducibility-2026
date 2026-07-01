# Final public-release data consistency check

## Manuscript vs diagnostic v1 vs final_public_release
| metric | manuscript | diagnostic_v1 | final_public_release | status |
| --- | --- | --- | --- | --- |
| mean daily availability percent | 97.45 final | 65.54 | 97.45 | final manuscript result uses expected_records=4032 |
| minimum daily availability percent | 94.35 | 37.77 | 94.35 | reproduced after denominator correction to 4032 |
| maximum daily availability percent | 99.18 | 82.64 | 99.18 | reproduced after denominator correction to 4032 |
| availability SD percentage points | 1.31 final | 15.69 | 1.31 | final manuscript result uses expected_records=4032 |
| median daily missing records | 85 final | n/a | 85 | final manuscript result uses expected_records=4032 |
| matched observations | 3243 | 5190 | 3243 | reproduced using 2025-12-08 to 2025-12-31 benchmark window |
| Block 1/2/3 n | 1082/1081/1080 | 1732/1732/1726 | 1082/1081/1080 | reproduced |
| pooled Pearson | 0.9246 | 0.919 | 0.9246 | reproduced |
| pooled Spearman | 0.6558 | 0.652 | 0.6558 | reproduced |
| rank-based peak overlap | 0.814 | 0.688 | 0.814 | reproduced with rank-based top-quartile peak definition |

## Workbook and sheet dimensions
| workbook | sheet | row_count | column_count |
| --- | --- | --- | --- |
| S1_Data.xlsx | Fig4_daily_availability | 83 | 5 |
| S1_Data.xlsx | Fig5_intraday_profiles | 288 | 7 |
| S1_Data.xlsx | Fig6_benchmark | 4 | 9 |
| S1_Data.xlsx | Matched_data | 3243 | 5 |
| S2_Table_TomTom_points_and_benchmark_blocks.xlsx | TomTom_points | 42 | 7 |
| S2_Table_TomTom_points_and_benchmark_blocks.xlsx | Benchmark_blocks | 3 | 7 |
| S3_Table_Data_dictionary_and_indicator_direction.xlsx | Data_dictionary | 21 | 6 |
| S3_Table_Data_dictionary_and_indicator_direction.xlsx | Indicator_direction | 21 | 2 |
| S4_Table_Cleaning_outcome_summary.xlsx | Cleaning_outcome_summary | 83 | 14 |
| S5_Table_TomTom_HERE_benchmark_sensitivity_results.xlsx | Sensitivity_results | 59 | 23 |

## Source files adopted
- `Data Summary Table/F4_recalculated_availability_4038.xlsx` for manuscript-era acquisition return completeness; final percentages recalculated with 4032 denominator.
- `02 Merge TomTom Original CSV/tomtom_raw_merged.csv` for TomTom point-time traffic-state cleaning and block aggregation.
- `03 HERE/here_clean_30min_segment_fixed_with_audit.csv` for HERE block-time aggregation.
- `Data Summary Table/figure5_internal_consistency_data.xlsx` for manuscript-era Fig5 profile data.
- `01 Organize TomTom_s design point table/tomtom_point_reference_final.csv` for 42-point metadata and block assignment.

## Figure/table support map
| figure_or_table | data_file |
| --- | --- |
| Fig4/Table4 | data/figure_data/fig4_daily_availability.csv; S1_Data.xlsx |
| Fig5 | data/figure_data/fig5_intraday_profiles.csv; S1_Data.xlsx |
| Fig6/Table benchmark | data/cleaned/matched_tomtom_here_benchmark.csv; data/figure_data/fig6_benchmark_summary.csv |
| S2 | data/metadata/tomtom_point_block_assignment.csv; data/metadata/here_benchmark_block_definition.csv |
| S3 | data/metadata/data_dictionary.csv |
| S4 | supporting_information/S4_Table_Cleaning_outcome_summary.xlsx |
| S5 | data/sensitivity/*.csv |

## Reviewer support map
| reviewer_comment_support | data_support |
| --- | --- |
| Data availability/licensing risk | README, raw_examples, diagnostic report |
| Fig4 acquisition completeness | manuscript-era F4 summary re-expressed with 4032 denominator |
| TomTom-HERE benchmark | 3243-row matched table for 2025-12-08 to 2025-12-31 |
| Sensitivity checks | bootstrap, daily, block, lag, rank-based threshold outputs |

## Reproducibility conclusions
- Final manuscript availability uses 4032 denominator.
- Final mean availability = 97.45 percent.
- Final minimum availability = 94.35 percent.
- Final maximum availability = 99.18 percent.
- Final availability SD = 1.31 percentage points.
- Final median missing records = 85.
- The old 97.30 percent value came from the source workbook's 4038 denominator and should not be used as the final manuscript result.
- Matched observations 3243 reproduced: yes.
- Pearson = 0.9246.
- Spearman = 0.6558.
- Rank-based peak overlap = 0.814.
- Historical discrepancy: 97.30 percent was from the old source workbook with a 4038 denominator and is retained only as an audit note.

## Public-release risk checks
- fill-token hits: 0
- ph-token hits: 0
- Secret pattern hits: []
- Complete raw API dumps: []
- Full vendor geometry dumps: []
- Private source folders copied: []
- Can be used for PLOS ONE revised manuscript and Response to Reviewers: yes, with the diagnostic caveats above documented.
