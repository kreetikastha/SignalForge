from disasterlens_ai.adapter import analyze_for_backend, to_backend_dict
from disasterlens_ai.schemas import ReportAnalysis

# keys backend/main.py reads from the analyzer result
REQUIRED = {"incident_type", "severity", "people_trapped", "road_blocked",
            "ai_summary", "priority_reason", "analysis_status"}


def test_stub_has_all_backend_keys(monkeypatch):
    monkeypatch.setenv("DISASTERLENS_STUB", "1")
    from disasterlens_ai import config
    monkeypatch.setattr(config, "STUB_MODE", True)
    out = analyze_for_backend("Flood near the bridge, people trapped")
    assert REQUIRED <= out.keys()
    assert out["analysis_status"] == "mock"


def test_severity_mapping_and_reason():
    a = ReportAnalysis(incident_type="building_collapse", severity=5, summary="s", confidence=0.9,
                       people_trapped="yes", road_blocked="yes", vulnerable_groups=["children"])
    out = to_backend_dict(a, duplicate_count=3)
    assert out["severity"] == "critical" and out["analysis_status"] == "complete"
    assert "trapped" in out["priority_reason"] and "3 corroborating" in out["priority_reason"]
    assert 0 < out["urgency_score"] <= 100
