"""De-identified TomTom acquisition template.

This template documents the collection logic used by the development system.
It requires user-supplied TomTom developer credentials and writes raw responses
only to private local storage. Do not commit raw responses or credentials.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Iterable

import requests


TOMTOM_API_KEY = "YOUR_TOMTOM_API_KEY"
TOMTOM_BASE_URL = "TomTom Traffic API endpoint from developer documentation"
PRIVATE_RAW_OUTPUT_DIR = Path("path/to/private/raw_tomtom_responses")


def read_monitoring_points(point_config_csv: Path) -> Iterable[dict]:
    with point_config_csv.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def request_tomtom_flow(latitude: float, longitude: float, api_key: str) -> dict:
    params = {"point": f"{latitude},{longitude}", "key": api_key}
    response = requests.get(TOMTOM_BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_tomtom_response(payload: dict) -> dict:
    flow = payload.get("flowSegmentData", {})
    return {
        "current_speed": flow.get("currentSpeed"),
        "free_flow_speed": flow.get("freeFlowSpeed"),
        "current_travel_time": flow.get("currentTravelTime"),
        "free_flow_travel_time": flow.get("freeFlowTravelTime"),
        "confidence": flow.get("confidence"),
        "road_closure_status": flow.get("roadClosure"),
    }


def collect_once(point_config_csv: Path, private_raw_dir: Path = PRIVATE_RAW_OUTPUT_DIR) -> list[dict]:
    private_raw_dir.mkdir(parents=True, exist_ok=True)
    cleaned_rows = []
    for point in read_monitoring_points(point_config_csv):
        payload = request_tomtom_flow(float(point["latitude"]), float(point["longitude"]), TOMTOM_API_KEY)
        private_file = private_raw_dir / f"{point['point_id']}_{int(time.time())}.json"
        private_file.write_text(json.dumps(payload), encoding="utf-8")
        row = {"point_id": point["point_id"], **parse_tomtom_response(payload)}
        cleaned_rows.append(row)
        time.sleep(1)
    return cleaned_rows


if __name__ == "__main__":
    collect_once(Path("configs/point_panel_config.csv"))
