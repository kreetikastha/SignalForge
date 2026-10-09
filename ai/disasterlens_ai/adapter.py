"""Translate structured AI analysis into the backend report contract."""

from . import config
from .analyzer import analyze_report
from .schemas import ReportAnalysis
from .urgency import score_urgency

_SEVERITY_WORD = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "critical"}

_ROAD_BLOCKAGE_PHRASES = (
    "road blocked",
    "road is blocked",
    "blocked road",
    "cars cannot pass",
    "vehicles cannot pass",
    "traffic cannot pass",
    "vehicles are unable to pass",
    "cannot get through",
    "unable to pass",
    "impassable",
    "road is closed",
    "road closed",
    "across the road",
    "across a road",
    "across the main road",
    "fell across",
    "fallen across",
)


def _report_confirms_road_blockage(description: str) -> bool:
    text = description.lower()
    return any(phrase in text for phrase in _ROAD_BLOCKAGE_PHRASES)


def explain_urgency(
    analysis: ReportAnalysis,
    duplicate_count: int = 1,
    *,
    people_trapped: str | None = None,
    road_blocked: str | None = None,
) -> str:
    parts = [
        f"severity {analysis.severity}/5 "
        f"({_SEVERITY_WORD[analysis.severity]})"
    ]
    trapped = people_trapped or analysis.people_trapped
    blocked = road_blocked or analysis.road_blocked
    if trapped == "yes":
        parts.append("people reported trapped")
    if analysis.people_affected:
        parts.append(f"~{analysis.people_affected} people affected")
    if analysis.vulnerable_groups:
        parts.append("vulnerable: " + ", ".join(analysis.vulnerable_groups))
    if blocked == "yes":
        parts.append("access road blocked")
    if duplicate_count > 1:
        parts.append(f"{duplicate_count} corroborating reports")
    return (
        "; ".join(parts)
        + f". Model confidence {analysis.confidence:.0%}; "
        "human verification advised."
    )


def to_backend_dict(
    analysis: ReportAnalysis,
    duplicate_count: int = 1,
    *,
    description: str = "",
) -> dict[str, object]:
    incident_type = analysis.incident_type.value
    needs = {need.lower() for need in analysis.needs}
    description_confirms_blockage = _report_confirms_road_blockage(description)

    if incident_type == "other" and description_confirms_blockage:
        incident_type = "road_blockage"

    people_trapped = analysis.people_trapped
    if people_trapped == "unknown" and "rescue" in needs:
        people_trapped = "yes"

    road_blocked = analysis.road_blocked
    if (
        road_blocked != "yes"
        and (
            incident_type == "road_blockage"
            or "road_clearing" in needs
            or description_confirms_blockage
        )
    ):
        road_blocked = "yes"

    priority_reason = explain_urgency(
        analysis,
        duplicate_count,
        people_trapped=people_trapped,
        road_blocked=road_blocked,
    )
    stub = config.STUB_MODE or analysis.confidence <= 0.1
    return {
        "incident_type": incident_type,
        "severity": _SEVERITY_WORD[analysis.severity],
        "people_trapped": people_trapped,
        "road_blocked": road_blocked,
        "ai_summary": analysis.summary,
        "priority_reason": priority_reason,
        "analysis_status": "mock" if stub else "completed",
        "urgency_score": score_urgency(analysis, duplicate_count),
        "location_text": analysis.location_text,
        "needs": analysis.needs,
        "language": analysis.language,
        "confidence": analysis.confidence,
    }


def analyze_for_backend(
    description: str, image: bytes | None = None
) -> dict[str, object]:
    """Analyze a report and return fields ready for backend persistence."""
    analysis = analyze_report(description, image=image)
    return to_backend_dict(analysis, description=description)
