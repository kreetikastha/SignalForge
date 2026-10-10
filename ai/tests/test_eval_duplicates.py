"""eval.py::_duplicates must pass the NEW report's coordinates to find_duplicate.

Regression: passing the existing incident's own lat/lon as the new report's made
every distance 0 km, so the geo score was always 1.0 and the with-coordinates
numbers were inflated.
"""
import importlib.util
from pathlib import Path

from disasterlens_ai.schemas import GroupingAnalysis, IncidentType, ReportAnalysis

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval.py"
spec = importlib.util.spec_from_file_location("eval_script_dups", SCRIPT)
eval_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_script)


def _analysis():
    return ReportAnalysis(incident_type=IncidentType.FLOOD, location_text="Balkhu bridge",
                          severity=3, summary="river flooding near balkhu bridge", confidence=0.9)


def _exp(group):
    return {"dup_group": group}


def test_far_apart_reports_are_not_duplicates_when_coordinates_are_used():
    # identical text, ~11 km apart: text-only says duplicate, geo must say no.
    samples = [{"id": "a", "lat": 27.70, "lon": 85.30}, {"id": "b", "lat": 27.80, "lon": 85.30}]
    expected = {"a": _exp("g1"), "b": _exp("g1")}
    analyses = {"a": _analysis(), "b": _analysis()}
    dup = eval_script._duplicates(samples, expected, analyses)
    assert dup["recall_no_coords"][1:] == (2, 2)
    assert dup["recall"][1:] == (0, 2)          # old bug: 2/2
    assert dup["missed"] == [("a", "b"), ("b", "a")]


def test_close_reports_are_duplicates_both_ways():
    samples = [{"id": "a", "lat": 27.7000, "lon": 85.30}, {"id": "b", "lat": 27.7005, "lon": 85.30}]
    expected = {"a": _exp("g1"), "b": _exp("g1")}
    analyses = {"a": _analysis(), "b": _analysis()}
    dup = eval_script._duplicates(samples, expected, analyses)
    assert dup["recall"][1:] == (2, 2) and dup["recall_no_coords"][1:] == (2, 2)
    assert dup["false_positives"] == [] and dup["false_positives_no_coords"] == []


def test_duplicate_eval_uses_pre_analysis_grouping_outputs_when_provided():
    samples = [
        {"id": "a", "lat": 27.7000, "lon": 85.30},
        {"id": "b", "lat": 27.7005, "lon": 85.30},
    ]
    expected = {"a": _exp("g1"), "b": _exp("g1")}
    triage_analyses = {
        "a": _analysis(),
        "b": ReportAnalysis(
            incident_type=IncidentType.OTHER,
            location_text=None,
            severity=3,
            summary="Different full-triage output.",
            confidence=0.8,
        ),
    }
    groupings = {
        "a": GroupingAnalysis(
            incident_type=IncidentType.FLOOD,
            location_text="Kalimati",
            summary="Floodwater near Kalimati.",
        ),
        "b": GroupingAnalysis(
            incident_type=IncidentType.FLOOD,
            location_text="Kalimati",
            summary="Floodwater near Kalimati.",
        ),
    }

    dup = eval_script._duplicates(samples, expected, triage_analyses, groupings)

    assert dup["recall"][1:] == (2, 2)
    assert dup["false_positives"] == []
