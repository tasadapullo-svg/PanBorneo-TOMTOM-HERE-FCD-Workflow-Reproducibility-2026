# TomTom-HERE acquisition pseudocode

```text
Every 15 minutes:
  load 42 TomTom monitoring points
  for each point:
    request TomTom traffic-flow data using user-supplied credential
    parse current speed, free-flow speed, travel times, confidence, closure flag
    write complete raw response to private storage
    write analysis fields to private working table

Every 30 minutes:
  load three HERE benchmark areas
  for each area:
    request HERE traffic-flow data using user-supplied credential
    parse speed, jam factor, confidence, and segment identifiers
    write complete raw response to private storage
    aggregate analysis fields to benchmark block-time table

For public release:
  publish cleaned point-time, block-time, matched benchmark, figure, sensitivity, and metadata tables
  do not publish complete raw responses, request logs, credentials, or full vendor-returned geometry
```
