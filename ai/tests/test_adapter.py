from backend import ai_service
from disasterlens_ai import adapter
from disasterlens_ai.schemas import IncidentType, ReportAnalysis


def _return_analysis(analysis):
    def analyze(*args, **kwargs):
        _ = args, kwargs
        return analysis

    return analyze


def test_stub_has_all_backend_keys(monkeypatch):
    from disasterlens_ai import config

    monkeypatch.setattr(config, "STUB_MODE", True)
    result = adapter.analyze_for_backend("Flood near the bridge, people trapped")

    required = {
        "incident_type",
        "severity",
        "people_trapped",
        "road_blocked",
        "ai_summary",
        "priority_reason",
        "analysis_status",
    }
    assert required <= result.keys()
    assert result["analysis_status"] == "mock"


def test_severity_mapping_and_urgency_reason(monkeypatch):
    from disasterlens_ai import config

    monkeypatch.setattr(config, "STUB_MODE", False)
    analysis = ReportAnalysis(
        incident_type=IncidentType.BUILDING_COLLAPSE,
        severity=5,
        summary="Structural collapse.",
        confidence=0.9,
        people_trapped="yes",
        road_blocked="yes",
        vulnerable_groups=["children"],
    )
    monkeypatch.setattr(adapter, "analyze_report", _return_analysis(analysis))

    result = adapter.analyze_for_backend("A building collapsed.")

    assert result["severity"] == "critical"
    assert result["analysis_status"] == "completed"
    priority_reason = result["priority_reason"]
    urgency_score = result["urgency_score"]
    assert isinstance(priority_reason, str) and "trapped" in priority_reason
    assert isinstance(urgency_score, int) and 0 < urgency_score <= 100


def test_adapter_uses_explicit_blocked_access_in_report(monkeypatch):
    analysis = ReportAnalysis(
        incident_type=IncidentType.OTHER,
        severity=3,
        summary="A fallen tree is blocking access.",
        confidence=0.8,
    )
    monkeypatch.setattr(adapter, "analyze_report", _return_analysis(analysis))

    result = adapter.analyze_for_backend(
        "Strong winds caused a tree to fall across a local road. "
        "Cars cannot pass and the road needs to be cleared."
    )

    assert result["incident_type"] == "road_blockage"
    assert result["road_blocked"] == "yes"
    priority_reason = result["priority_reason"]
    assert isinstance(priority_reason, str)
    assert "access road blocked" in priority_reason


def test_vehicle_stopped_does_not_infer_trapped_people(monkeypatch):
    analysis = ReportAnalysis(
        incident_type=IncidentType.ROAD_BLOCKAGE,
        severity=4,
        summary="A bus is stopped near a landslide.",
        confidence=0.9,
    )
    monkeypatch.setattr(adapter, "analyze_report", _return_analysis(analysis))

    result = adapter.analyze_for_backend("A bus is stopped nearby.")

    assert result["people_trapped"] == "unknown"
    assert result["road_blocked"] == "yes"


def test_explain_urgency_shows_mass_casualty_tier():
    mass = ReportAnalysis(
        incident_type=IncidentType.FLOOD,
        severity=4,
        summary="Neighbourhood under water.",
        confidence=0.9,
        people_affected=45,
    )
    assert "mass casualty alert: ~45 people affected" in adapter.explain_urgency(mass)

    small = ReportAnalysis(
        incident_type=IncidentType.FLOOD,
        severity=4,
        summary="Two houses flooded.",
        confidence=0.9,
        people_affected=8,
    )
    reason = adapter.explain_urgency(small)
    assert "mass casualty alert" not in reason
    assert "~8 people affected" in reason


def test_adapter_exposes_injuries_and_immediate_hazards():
    analysis = ReportAnalysis(
        incident_type=IncidentType.BUILDING_COLLAPSE,
        severity=5,
        summary="Workers injured in a damaged building.",
        confidence=0.9,
        injuries_reported=2,
        hazards=["unstable structure", "live electrical wires"],
    )
    result = adapter.to_backend_dict(analysis)

    assert result["injuries_reported"] == 2
    assert result["hazards"] == ["unstable structure", "live electrical wires"]
    assert "2 injuries reported" in result["priority_reason"]
    assert "hazards: unstable structure, live electrical wires" in result["priority_reason"]


def test_backend_service_falls_back_when_ai_analysis_fails(monkeypatch, caplog):
    def fail_analysis(description):
        assert description == "Smoke near the market"
        raise RuntimeError("AI unavailable")

    monkeypatch.setattr(adapter, "analyze_for_backend", fail_analysis)

    result = ai_service.analyze_report("Smoke near the market")

    assert result["incident_type"] == "fire"
    assert result["analysis_status"] == "mock"
    priority_reason = result["priority_reason"]
    assert isinstance(priority_reason, str) and "RuntimeError" in priority_reason
    assert "AI analysis failed" in caplog.text


def test_mock_fallback_does_not_mistake_trapped_flood_victims_for_collapse():
    result = ai_service._mock_analyze(
        "Flooding near a bridge; two people are trapped and the road is blocked."
    )

    assert result["incident_type"] == "flood"
    assert result["severity"] == "critical"
    assert result["people_trapped"] == "yes"
    assert result["road_blocked"] == "yes"


def test_mock_fallback_classifies_collapsed_landslide_as_landslide():
    result = ai_service._mock_analyze(
        "A landslide covered the road after the slope collapsed."
    )

    assert result["incident_type"] == "landslide"
