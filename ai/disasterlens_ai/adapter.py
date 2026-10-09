from .analyzer import analyze_report as analyze_with_ai


_SEVERITY_LABELS = {
    1: "info",
    2: "low",
    3: "medium",
    4: "high",
    5: "critical",
}


def _report_confirms_road_blockage(description: str) -> bool:
    text = description.lower()
    blockage_phrases = (
        "road blocked",
        "road is blocked",
        "blocked road",
        "cars cannot pass",
        "vehicles cannot pass",
        "traffic cannot pass",
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
    return any(phrase in text for phrase in blockage_phrases)


def analyze_for_backend(description: str) -> dict[str, str]:
    analysis = analyze_with_ai(description)
    incident_type = analysis.incident_type.value
    needs = {need.lower() for need in analysis.needs}

    description_confirms_blockage = _report_confirms_road_blockage(description)
    if incident_type == "other" and description_confirms_blockage:
        incident_type = "road_blockage"

    people_trapped = "yes" if "rescue" in needs else "unknown"
    road_blocked = (
        "yes"
        if (
            incident_type == "road_blockage"
            or "road_clearing" in needs
            or description_confirms_blockage
        )
        else "unknown"
    )
    priority_reason = (
        f"AI severity is {_SEVERITY_LABELS[analysis.severity]} "
        f"({analysis.severity}/5)."
    )
    if analysis.people_affected is not None:
        priority_reason += f" People affected: {analysis.people_affected}."
    if analysis.vulnerable_groups:
        priority_reason += (
            " Vulnerable groups: "
            + ", ".join(analysis.vulnerable_groups)
            + "."
        )
    priority_reason += " Human verification is recommended before dispatch."

    return {
        "incident_type": incident_type,
        "severity": _SEVERITY_LABELS[analysis.severity],
        "people_trapped": people_trapped,
        "road_blocked": road_blocked,
        "ai_summary": analysis.summary,
        "priority_reason": priority_reason,
        "analysis_status": "completed",
    }
