import datetime
from unittest.mock import patch, MagicMock
import pytest

from disasterlens_ai.dedup import find_duplicate
from disasterlens_ai.schemas import IncidentRef, IncidentType, ReportAnalysis
from disasterlens_ai import config


def _make_analysis(incident_type: IncidentType, location: str, summary: str) -> ReportAnalysis:
    return ReportAnalysis(
        incident_type=incident_type,
        location_text=location,
        summary=summary,
        severity=3,
        confidence=0.9,
        people_trapped="unknown",
        road_blocked="unknown",
    )


def _make_ref(sid: str, incident_type: IncidentType, location: str, summary: str,
              lat: float | None = None, lon: float | None = None) -> IncidentRef:
    return IncidentRef(
        id=sid,
        incident_type=incident_type,
        location_text=location,
        summary=summary,
        latitude=lat,
        longitude=lon,
        received_at=datetime.datetime.now(datetime.timezone.utc),
    )


@pytest.fixture(autouse=True)
def _enable_judge(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", False)
    monkeypatch.setattr(config, "JUDGE_ENABLED", True)
    monkeypatch.setattr(config, "DUP_JUDGE_NEAR_KM", 1.0)
    monkeypatch.setattr(config, "DUP_JUDGE_MAX_CANDIDATES", 2)
    monkeypatch.setattr(config, "DUP_HARD_CUTOFF_KM", 5.0)
    monkeypatch.setattr(config, "DUP_WINDOW_HOURS", 24)
    monkeypatch.setattr(config, "DUPLICATE_THRESHOLD", 0.55)


def test_geo_near_judge_true_returns_duplicate():
    """Near pair with zero text overlap and judge returning True -> duplicate."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    existing = [_make_ref("s1", IncidentType.FLOOD, "कालिमाटी", "कालिमाटी मा बाढी", 27.69, 85.31)]

    with patch("disasterlens_ai.dedup._judge", return_value=(True, "same place")) as mock_judge:
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is True
    assert result.incident_id == "s1"
    assert "geo-near judge" in result.reason
    mock_judge.assert_called_once()


def test_geo_near_judge_false_returns_not_duplicate():
    """Near pair with zero text overlap and judge returning False -> not duplicate."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    existing = [_make_ref("s1", IncidentType.FLOOD, "कालिमाटी", "कालिमाटी मा बाढी", 27.69, 85.31)]

    with patch("disasterlens_ai.dedup._judge", return_value=(False, "different")) as mock_judge:
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is False
    assert result.incident_id is None
    mock_judge.assert_called_once()


def test_pair_beyond_judge_near_km_judge_never_called():
    """Pair 2.5 km apart (beyond DUP_JUDGE_NEAR_KM=1.0) -> judge never called."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    existing = [_make_ref("s1", IncidentType.FLOOD, "कालिमाटी", "कालिमाटी मा बाढी", 27.72, 85.35)]  # ~3.5 km away

    with patch("disasterlens_ai.dedup._judge") as mock_judge:
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is False
    mock_judge.assert_not_called()


def test_incompatible_types_judge_never_called():
    """Incompatible incident types -> judge never called even if near."""
    new = _make_analysis(IncidentType.FIRE, "Kalimati", "Fire in Kalimati")
    existing = [_make_ref("s1", IncidentType.FLOOD, "कालिमाटी", "कालिमाटी मा बाढी", 27.69, 85.31)]  # incompatible

    with patch("disasterlens_ai.dedup._judge") as mock_judge:
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is False
    mock_judge.assert_not_called()


def test_judge_raises_exception_returns_not_duplicate():
    """Judge raising exception -> not duplicate and no exception propagated."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    existing = [_make_ref("s1", IncidentType.FLOOD, "कालिमाटी", "कालिमाटी मा बाढी", 27.69, 85.31)]

    with patch("disasterlens_ai.dedup._judge", side_effect=Exception("LLM down")):
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is False
    assert result.incident_id is None


def test_at_most_two_judge_calls_with_five_near_candidates():
    """With 5 near candidates, judge is called at most DUP_JUDGE_MAX_CANDIDATES=2 times."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    # 5 candidates all within 1 km
    existing = [
        _make_ref(f"s{i}", IncidentType.FLOOD, f"place{i}", "summary", 27.69 + i * 0.001, 85.31 + i * 0.001)
        for i in range(5)
    ]

    with patch("disasterlens_ai.dedup._judge", return_value=(False, "no")) as mock_judge:
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert mock_judge.call_count == 2
    assert result.is_duplicate is False


def test_geo_near_judge_stops_at_first_true():
    """Judge stops after first True, doesn't call remaining candidates."""
    new = _make_analysis(IncidentType.FLOOD, "Kalimati", "Flood in Kalimati")
    existing = [
        _make_ref("s1", IncidentType.FLOOD, "place1", "summary", 27.69, 85.31),
        _make_ref("s2", IncidentType.FLOOD, "place2", "summary", 27.691, 85.311),
        _make_ref("s3", IncidentType.FLOOD, "place3", "summary", 27.692, 85.312),
    ]

    call_count = 0

    def judge_side_effect(new_analysis, inc, dist_km):
        nonlocal call_count
        call_count += 1
        if inc.id == "s2":
            return (True, "match")
        return (False, "no")

    with patch("disasterlens_ai.dedup._judge", side_effect=judge_side_effect):
        result = find_duplicate(
            new, existing,
            latitude=27.692, longitude=85.308,
            now=datetime.datetime.now(datetime.timezone.utc)
        )

    assert result.is_duplicate is True
    assert result.incident_id == "s2"
    assert call_count == 2  # Only called for s1 and s2, stopped before s3