import json
import re
from pathlib import Path

from disasterlens_ai.schemas import IncidentType

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _samples() -> list[dict]:
    return json.loads((DATA_DIR / "sample_reports.json").read_text(encoding="utf-8"))


def _expected() -> dict:
    return json.loads((DATA_DIR / "expected_outputs.json").read_text(encoding="utf-8"))


def test_both_files_load():
    samples, expected = _samples(), _expected()
    assert isinstance(samples, list) and isinstance(expected, dict)
    for s in samples:
        assert {"id", "text", "lat", "lon"} <= set(s)
    for exp in expected.values():
        assert {"incident_type", "severity_min", "severity_max", "people_trapped",
                "road_blocked", "needs_include", "language", "dup_group"} <= set(exp)


def test_ids_match_exactly():
    ids = [s["id"] for s in _samples()]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(_expected())


def test_at_least_30_samples():
    assert len(_samples()) >= 30


def test_at_least_8_devanagari_samples():
    count = sum(1 for s in _samples() if DEVANAGARI.search(s["text"]))
    assert count >= 8


def test_severity_ranges_valid():
    for sid, exp in _expected().items():
        assert exp["severity_min"] <= exp["severity_max"], sid
        assert 1 <= exp["severity_min"] and exp["severity_max"] <= 5, sid


def test_incident_type_valid():
    valid = {t.value for t in IncidentType}
    for sid, exp in _expected().items():
        assert exp["incident_type"] in valid, sid
