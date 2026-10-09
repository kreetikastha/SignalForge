import pytest
from pydantic import ValidationError
from disasterlens_ai.schemas import ReportAnalysis


def test_valid():
    r = ReportAnalysis(incident_type="flood", severity=3, summary="x", confidence=0.5)
    assert r.needs == []


def test_severity_bounds():
    with pytest.raises(ValidationError):
        ReportAnalysis(incident_type="flood", severity=9, summary="x", confidence=0.5)
