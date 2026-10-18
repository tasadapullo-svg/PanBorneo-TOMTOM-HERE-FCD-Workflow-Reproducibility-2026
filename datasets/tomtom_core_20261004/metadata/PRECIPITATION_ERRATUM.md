# Precipitation units and alignment

The immutable core dictionary is retained byte for byte. Its mm/hour wording for
precipitation_mm and rain_mm is superseded by **mm accumulated over the hour
preceding timestamp_local**, without converting any stored value. precipitation_mm
is total precipitation; rain_mm is a distinct liquid-precipitation variable.
Pair traffic hours [H,H+1 h) with the background label at H+1 h. Unmatched
endpoints remain missing. The retained audit is
../process_data/preflight/SEMANTICS_AUDIT.md and the joined table is
../process_data/coverage_hourly/hourly/NODE_HOUR_ENDPOINT_JOIN.csv.
Gridded precipitation is retrospective environmental context, not a roadside gauge.
