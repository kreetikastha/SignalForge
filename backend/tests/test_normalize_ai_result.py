"""`_normalize_ai_result` must trust adapter.analyze_for_backend() output.

Keyword inference (`_infer_from_text`) is a fallback for mock/failed payloads
only -- running it on a completed analysis clobbered model decisions:
  * severity "low" became "high" because the text said "landslide" or "fire",
  * incident_type "other" (spam/advertisements) became an emergency type,
  * adapter's priority_reason (with its safety flags) was thrown away.
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
_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp(prefix="disasterlens-tests-"))
try:
    import main as backend_main  # noqa: E402  (sys.path prepared above)
finally:
    os.chdir(_cwd)

_normalize_ai_result = backend_main._normalize_ai_result

LANDSLIDE_TEXT = "Minor landslide near Kalimati, one lane still usable"
FIRE_TEXT = "Buy fire extinguishers at half price today"


def _completed(**overrides) -> dict:
    payload = {
        "incident_type": "landslide",
        "severity": "low",  # model: minor (severity 2)
        "people_trapped": "no",
        "road_blocked": "no",
        "ai_summary": "Small slide at the shoulder; traffic still moving.",
        "priority_reason": (
            "severity 2/5 (low); access road open. "
            "Model confidence 90%; human verification advised."
        ),
        "analysis_status": "completed",
        "location_text": "Kalimati",
        "confidence": 0.9,
        "urgency_score": 40,
        "needs": [],
        "language": "en",
    }
    payload.update(overrides)
    return payload


def test_completed_analysis_keeps_model_severity():
    # "landslide" in the text must not promote a model severity of 2 to "high".
    out = _normalize_ai_result(_completed(), original_text=LANDSLIDE_TEXT)
    assert out["severity"] == "low"
    assert out["analysis_status"] == "completed"


def test_completed_analysis_never_runs_keyword_overrides():
    out = _normalize_ai_result(
        _completed(incident_type="other", severity="info", people_trapped="unknown"),
        original_text=FIRE_TEXT,
    )
    assert out["incident_type"] == "other"  # spam/ad stays "other"
    assert out["severity"] == "info"
    assert out["people_trapped"] == "unknown"
    assert out["analysis_status"] == "completed"


def test_completed_analysis_accepts_adapter_fields_verbatim():
    out = _normalize_ai_result(_completed(), original_text=LANDSLIDE_TEXT)
    assert out["ai_summary"] == "Small slide at the shoulder; traffic still moving."
    assert out["location_text"] == "Kalimati"
    assert out["confidence"] == 0.9
    assert out["urgency_score"] == 40


def test_priority_reason_keeps_safety_flags():
    reason = (
        "severity 4/5 (high); people reported trapped; "
        "safety rule applied: trapped_keyword_override. "
        "Model confidence 80%; human verification advised."
    )
    out = _normalize_ai_result(
        _completed(severity="low", priority_reason=reason), original_text=FIRE_TEXT
    )
    assert out["priority_reason"] == reason
    assert "safety rule applied: trapped_keyword_override" in out["priority_reason"]
    assert "Human verification is recommended" not in out["priority_reason"]


def test_mock_result_uses_keyword_fallback_and_is_marked_mock():
    out = _normalize_ai_result(
        {"analysis_status": "mock"},
        original_text="Landslide blocked the highway at Muglin",
    )
    assert out["incident_type"] == "landslide"
    assert out["severity"] == "high"
    assert out["analysis_status"] == "mock"
    assert "Preliminary assessment" in out["ai_summary"]


def test_failed_analysis_falls_back_to_keywords():
    out = _normalize_ai_result(
        {"analysis_status": "failed"}, original_text="Fire in a shop at Kalimati"
    )
    assert out["analysis_status"] == "mock"
    assert out["incident_type"] == "fire"
    assert out["severity"] == "high"


def test_unhandled_exception_payload_is_keyword_mock():
    out = _normalize_ai_result(None, original_text="Fire in a shop at Kalimati")
    assert out["analysis_status"] == "mock"
    assert out["incident_type"] == "fire"
    assert out["severity"] == "high"


def test_mock_result_fields_are_kept_when_present():
    out = _normalize_ai_result(
        {
            "analysis_status": "mock",
            "incident_type": "flood",
            "severity": "medium",
            "people_trapped": "no",
            "road_blocked": "unknown",
            "ai_summary": "River rising at Balkhu.",
            "priority_reason": "keyword-based fallback used.",
        },
        original_text="Landslide on the Muglin highway",
    )
    assert out["incident_type"] == "flood"
    assert out["severity"] == "medium"
    assert out["people_trapped"] == "no"
    assert out["priority_reason"] == "keyword-based fallback used."
    assert out["analysis_status"] == "mock"


def test_missing_priority_reason_gets_placeholder():
    out = _normalize_ai_result(_completed(priority_reason=""), original_text=LANDSLIDE_TEXT)
    assert "Severity is low" in out["priority_reason"]
    assert "Human verification is recommended" in out["priority_reason"]
