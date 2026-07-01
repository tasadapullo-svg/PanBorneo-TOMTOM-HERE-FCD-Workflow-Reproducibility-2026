"""Export supporting information workbooks from public release CSV files.

This helper is intentionally lightweight. The release already includes S1-S5
workbooks; rerun only after updating public CSV outputs.
"""

from pathlib import Path

import pandas as pd


ROOT = Path(".")


def export_s1() -> None:
    out = ROOT / "supporting_information" / "S1_Data.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.read_csv(ROOT / "data/figure_data/fig4_daily_availability.csv").to_excel(writer, "Fig4_daily_availability", index=False)
        pd.read_csv(ROOT / "data/figure_data/fig5_intraday_profiles.csv").to_excel(writer, "Fig5_intraday_profiles", index=False)
        pd.read_csv(ROOT / "data/figure_data/fig6_benchmark_summary.csv").to_excel(writer, "Fig6_benchmark", index=False)
        pd.read_csv(ROOT / "data/cleaned/matched_tomtom_here_benchmark.csv")[["block_id", "timestamp_30min", "tomtom_mean_CI_percent", "here_mean_jam_factor", "matched_status"]].to_excel(writer, "Matched_data", index=False)


if __name__ == "__main__":
    export_s1()
