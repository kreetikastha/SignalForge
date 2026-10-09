from disasterlens_ai import adapter
from disasterlens_ai.schemas import IncidentType, ReportAnalysis
from backend import ai_service


def test_adapter_translates_analysis_for_backend(monkeypatch):
    analysis = ReportAnalysis(
        incident_type=IncidentType.ROAD_BLOCKAGE,
        severity=4,
        people_affected=12,
        needs=["road_clearing", "rescue"],
        vulnerable_groups=["children"],
        summary="A landslide has blocked the road.",
        confidence=0.9,
    )
    monkeypatch.setattr(adapter, "analyze_with_ai", lambda _: analysis)

    result = adapter.analyze_for_backend("Road blocked after landslide")

    assert result == {
        "incident_type": "road_blockage",
        "severity": "high",
        "people_trapped": "yes",
        "road_blocked": "yes",
        "ai_summary": "A landslide has blocked the road.",
        "priority_reason": (
            "AI severity is high (4/5). People affected: 12. "
            "Vulnerable groups: children. Human verification is "
            "recommended before dispatch."
        ),
        "analysis_status": "completed",
    }


def test_adapter_leaves_unreported_fields_unknown(monkeypatch):
    analysis = ReportAnalysis(
        incident_type=IncidentType.OTHER,
        severity=1,
        summary="Unconfirmed incident.",
        confidence=0.3,
    )
    monkeypatch.setattr(adapter, "analyze_with_ai", lambda _: analysis)

    result = adapter.analyze_for_backend("Something happened")

    assert result["severity"] == "info"
    assert result["people_trapped"] == "unknown"
    assert result["road_blocked"] == "unknown"


def test_adapter_uses_explicit_blocked_access_in_report(monkeypatch):
    analysis = ReportAnalysis(
        incident_type=IncidentType.OTHER,
        severity=3,
        summary="A fallen tree is blocking access.",
        confidence=0.8,
    )
    monkeypatch.setattr(adapter, "analyze_with_ai", lambda _: analysis)

    result = adapter.analyze_for_backend(
        "Strong winds caused a tree to fall across a local road. "
        "Cars cannot pass and the road needs to be cleared."
    )

    assert result["incident_type"] == "road_blockage"
    assert result["road_blocked"] == "yes"


def test_backend_service_falls_back_when_ai_analysis_fails(monkeypatch, caplog):
    def fail_analysis(_):
        raise RuntimeError("AI unavailable")

    monkeypatch.setattr(adapter, "analyze_for_backend", fail_analysis)

    result = ai_service.analyze_report("Smoke near the market")

    assert result["incident_type"] == "fire"
    assert result["analysis_status"] == "mock"
    assert "RuntimeError" in result["priority_reason"]
    assert "AI analysis failed" in caplog.text


def test_mock_fallback_does_not_mistake_trapped_flood_victims_for_collapse():
    result = ai_service._mock_analyze(
        "Flooding near a bridge; two people are trapped and the road is blocked."
    )

    assert result["incident_type"] == "flood"
    assert result["severity"] == "critical"
    assert result["people_trapped"] == "yes"
    assert result["road_blocked"] == "yes"
