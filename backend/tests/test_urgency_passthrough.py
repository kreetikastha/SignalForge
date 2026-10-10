"""people_affected / vulnerable_groups / flags must survive the backend round trip.

adapter.to_backend_dict() emits all three, but `_normalize_ai_result` dropped
them and `_analysis_from_result` never rebuilt them, so the rebuilt
ReportAnalysis lost the casualty context and `score_urgency` fell back to
severity + trapped only: 60 instead of 94 for the flood below.
"""
import os
import sys
import tempfile
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Importing backend/main.py builds its SQLite schema from a cwd-relative URL;
# do that from a scratch directory so no disasterlens.db appears in the repo.
# main also pulls in ai_service, which puts SignalForge/ai on sys.path -- that
# is what makes disasterlens_ai importable below.
_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp(prefix="disasterlens-tests-"))
try:
    import main as backend_main  # noqa: E402  (sys.path prepared above)
finally:
    os.chdir(_cwd)

from disasterlens_ai import score_urgency  # noqa: E402
from disasterlens_ai.adapter import to_backend_dict  # noqa: E402
from disasterlens_ai.schemas import ReportAnalysis  # noqa: E402

_normalize_ai_result = backend_main._normalize_ai_result
_analysis_from_result = backend_main._analysis_from_result

FLOOD_TEXT = "Flood swept 60 people away, children missing near Balkhu"


def _mass_casualty_flood() -> ReportAnalysis:
    return ReportAnalysis(
        incident_type="flood",
        severity=4,
        people_affected=60,
        vulnerable_groups=["children"],
        people_trapped="yes",
        summary="x",
        confidence=0.9,
        flags=["trapped_keyword_override"],
    )


def test_to_backend_dict_exposes_casualty_fields():
    payload = to_backend_dict(_mass_casualty_flood(), description=FLOOD_TEXT)

    assert payload["people_affected"] == 60
    assert payload["vulnerable_groups"] == ["children"]
    assert payload["flags"] == ["trapped_keyword_override"]
    assert payload["needs_review"] is True
    # 48 severity + 24 (60 people) + 10 vulnerable + 12 trapped.
    assert payload["urgency_score"] == 94


def test_mass_casualty_flood_scores_94_after_round_trip():
    payload = to_backend_dict(_mass_casualty_flood(), description=FLOOD_TEXT)
    normalized = _normalize_ai_result(payload, original_text=FLOOD_TEXT)
    analysis = _analysis_from_result(normalized)

    assert normalized["people_affected"] == 60
    assert normalized["vulnerable_groups"] == ["children"]
    assert normalized["flags"] == ["trapped_keyword_override"]
    assert normalized["needs_review"] is True

    assert analysis.people_affected == 60
    assert analysis.vulnerable_groups == ["children"]
    assert analysis.flags == ["trapped_keyword_override"]
    assert analysis.people_trapped == "yes"

    assert score_urgency(analysis) == 94


def test_mock_payload_without_casualty_keys_still_normalizes():
    normalized = _normalize_ai_result(
        {"analysis_status": "mock"},
        original_text="Landslide blocked the highway at Muglin",
    )

    assert normalized["analysis_status"] == "mock"
    assert normalized["people_affected"] is None
    assert normalized["vulnerable_groups"] == []
    assert normalized["flags"] == []
    assert normalized["needs_review"] is False

    analysis = _analysis_from_result(normalized)
    assert analysis.people_affected is None
    assert analysis.vulnerable_groups == []
    assert analysis.flags == []
    # Keyword fallback: severity "high" only -- no casualty bonus available.
    assert score_urgency(analysis) == 48


def _completed_payload(**overrides) -> dict:
    payload = {
        "incident_type": "flood",
        "severity": "high",
        "people_trapped": "yes",
        "road_blocked": "unknown",
        "ai_summary": "x",
        "priority_reason": "x",
        "analysis_status": "completed",
        "location_text": None,
        "confidence": 0.9,
        "urgency_score": 94,
        "needs": [],
        "language": "en",
        "people_affected": 60,
        "vulnerable_groups": ["children"],
        "flags": ["trapped_keyword_override"],
        "needs_review": True,
    }
    payload.update(overrides)
    return payload


def test_invalid_casualty_field_types_fall_back_to_defaults():
    normalized = _normalize_ai_result(
        _completed_payload(
            people_affected="many",
            vulnerable_groups="children",
            flags="trapped_keyword_override",
            needs_review="yes",
        ),
        original_text=FLOOD_TEXT,
    )

    assert normalized["people_affected"] is None
    assert normalized["vulnerable_groups"] == []
    assert normalized["flags"] == []
    assert normalized["needs_review"] is False
    assert _analysis_from_result(normalized).people_affected is None


def test_valid_casualty_field_types_are_coerced():
    normalized = _normalize_ai_result(
        _completed_payload(
            people_affected=60.0,
            vulnerable_groups=[1, "children"],
            flags=[],
            needs_review=0,
        ),
        original_text=FLOOD_TEXT,
    )

    assert normalized["people_affected"] == 60
    assert normalized["vulnerable_groups"] == ["1", "children"]
    assert normalized["flags"] == []
    assert normalized["needs_review"] is False
    assert score_urgency(_analysis_from_result(normalized)) == 94
