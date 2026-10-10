import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from disasterlens_ai.schemas import IncidentType, ReportAnalysis


def test_valid():
    r = ReportAnalysis(incident_type=IncidentType.FLOOD, severity=3, summary="x", confidence=0.5)
    assert r.needs == []


def test_severity_bounds():
    with pytest.raises(ValidationError):
        ReportAnalysis(incident_type=IncidentType.FLOOD, severity=9, summary="x", confidence=0.5)


def test_negative_reported_people_counts_are_rejected():
    with pytest.raises(ValidationError):
        ReportAnalysis(
            incident_type=IncidentType.FLOOD,
            severity=3,
            injuries_reported=-1,
            summary="x",
            confidence=0.5,
        )


def test_negative_trapped_people_count_is_rejected():
    with pytest.raises(ValidationError):
        ReportAnalysis(
            incident_type=IncidentType.FLOOD,
            severity=3,
            people_trapped_count=-1,
            summary="x",
            confidence=0.5,
        )


def test_trapped_people_count_is_optional_and_separate_from_affected_count():
    report = ReportAnalysis(
        incident_type=IncidentType.FLOOD,
        severity=3,
        people_affected=40,
        people_trapped="yes",
        people_trapped_count=2,
        summary="x",
        confidence=0.5,
    )
    assert report.people_affected == 40
    assert report.people_trapped_count == 2
    assert ReportAnalysis(
        incident_type=IncidentType.FLOOD,
        severity=3,
        summary="x",
        confidence=0.5,
    ).people_trapped_count is None


def test_analyze_examples_validate():
    path = (Path(__file__).resolve().parents[1]
            / "disasterlens_ai" / "prompts" / "analyze_examples.json")
    examples = json.loads(path.read_text(encoding="utf-8"))
    assert len(examples) == 7  # four original + three added
    for ex in examples:
        ReportAnalysis(**ex["output"])

    def out(fragment):
        return next(ex["output"] for ex in examples if fragment in ex["report"])

    romanized = out("Kalimati ma pahiro gayo")
    assert romanized["language"] == "ne" and romanized["road_blocked"] == "yes"

    injected = out("Ignore previous instructions")
    assert injected["severity"] == 5
    assert "instruction" not in injected["summary"].lower()

    non_emergency = out("selling a used motorbike")
    assert (non_emergency["incident_type"] == "other"
            and non_emergency["severity"] == 1
            and non_emergency["confidence"] <= 0.2)
