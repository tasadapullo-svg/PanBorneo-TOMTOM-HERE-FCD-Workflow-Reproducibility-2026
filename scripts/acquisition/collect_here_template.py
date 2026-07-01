"""De-identified HERE acquisition template.

This template documents the benchmark-area collection logic. Users must provide
their own HERE developer credentials. Complete raw responses and geometry are
private working files and are not part of this public release.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests


HERE_API_KEY = "YOUR_HERE_API_KEY"
HERE_BASE_URL = "HERE Traffic API endpoint from developer documentation"
PRIVATE_RAW_OUTPUT_DIR = Path("path/to/private/raw_here_responses")


BENCHMARK_AREAS = [
    {"block_id": "Block 1", "bbox": "YOUR_BLOCK_1_BBOX"},
    {"block_id": "Block 2", "bbox": "YOUR_BLOCK_2_BBOX"},
    {"block_id": "Block 3", "bbox": "YOUR_BLOCK_3_BBOX"},
]


def request_here_flow(bbox: str, api_key: str) -> dict:
    params = {
        "in": f"bbox:{bbox}",
        "locationReferencing": "shape",
        "apiKey": api_key,
    }
    response = requests.get(HERE_BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def parse_here_response(payload: dict, block_id: str) -> list[dict]:
    rows = []
    for item in payload.get("results", []):
        flow = item.get("currentFlow", {})
        location = item.get("location", {})
        rows.append(
            {
                "block_id": block_id,
                "speed_kmh": flow.get("speed"),
                "jam_factor": flow.get("jamFactor"),
                "confidence": flow.get("confidence"),
                "segment_id": location.get("id"),
            }
        )
    return rows


def collect_once(private_raw_dir: Path = PRIVATE_RAW_OUTPUT_DIR) -> list[dict]:
    private_raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for area in BENCHMARK_AREAS:
        payload = request_here_flow(area["bbox"], HERE_API_KEY)
        private_file = private_raw_dir / f"{area['block_id'].replace(' ', '_')}_{int(time.time())}.json"
        private_file.write_text(json.dumps(payload), encoding="utf-8")
        rows.extend(parse_here_response(payload, area["block_id"]))
        time.sleep(1)
    return rows


if __name__ == "__main__":
    collect_once()
