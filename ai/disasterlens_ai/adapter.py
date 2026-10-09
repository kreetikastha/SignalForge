"""Glue between the AI module and the backend's existing `reports` table.

The backend stores severity as a word and expects a flat dict. This module is the
single place that translates `ReportAnalysis` -> that dict, so the backend only needs:

    from disasterlens_ai.adapter import analyze_for_backend
"""
from . import config
from .analyzer import analyze_report
from .schemas import ReportAnalysis
from .urgency import score_urgency

_SEVERITY_WORD = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "critical"}


def explain_urgency(a: ReportAnalysis, duplicate_count: int = 1) -> str:
    """Human-readable reason, built from the same factors score_urgency uses."""
    parts = [f"severity {a.severity}/5 ({_SEVERITY_WORD[a.severity]})"]
    if a.people_trapped == "yes":
        parts.append("people reported trapped")
    if a.people_affected:
        parts.append(f"~{a.people_affected} people affected")
    if a.vulnerable_groups:
        parts.append("vulnerable: " + ", ".join(a.vulnerable_groups))
    if a.road_blocked == "yes":
        parts.append("access road blocked")
    if duplicate_count > 1:
        parts.append(f"{duplicate_count} corroborating reports")
    return "; ".join(parts) + f". Model confidence {a.confidence:.0%}; human verification advised."


def to_backend_dict(a: ReportAnalysis, duplicate_count: int = 1) -> dict:
    stub = config.STUB_MODE or a.confidence <= 0.1
    return {
        "incident_type": a.incident_type.value,
        "severity": _SEVERITY_WORD[a.severity],
        "people_trapped": a.people_trapped,
        "road_blocked": a.road_blocked,
        "ai_summary": a.summary,
        "priority_reason": explain_urgency(a, duplicate_count),
        "analysis_status": "mock" if stub else "complete",
        # extras the backend may start storing (extra keys are safe to ignore)
        "urgency_score": score_urgency(a, duplicate_count),
        "location_text": a.location_text,
        "needs": a.needs,
        "language": a.language,
        "confidence": a.confidence,
    }


def analyze_for_backend(description: str, image: bytes | None = None) -> dict:
    """Drop-in replacement for backend/ai_service.analyze_report()."""
    return to_backend_dict(analyze_report(description, image=image))
