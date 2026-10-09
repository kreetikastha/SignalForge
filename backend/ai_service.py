
def analyze_report(description: str) -> dict:
    """
    Temporary mock analyzer.
    Replace this with the real Gemma integration later.
    """

    text = description.lower()

    incident_type = "unknown"
    severity = "medium"
    people_trapped = "unknown"
    road_blocked = "unknown"

    if any(word in text for word in ["collapse", "collapsed", "trapped"]):
        incident_type = "building_collapse"
        severity = "critical"
        people_trapped = "unknown"

    elif any(word in text for word in ["flood", "flooding", "inundated"]):
        incident_type = "flood"
        severity = "high"

    elif any(word in text for word in ["fire", "burning", "smoke"]):
        incident_type = "fire"
        severity = "high"

    elif any(word in text for word in ["landslide", "mudslide"]):
        incident_type = "landslide"
        severity = "high"

    if any(word in text for word in ["people trapped", "people are trapped"]):
        people_trapped = "yes"

    if any(word in text for word in ["road blocked", "road is blocked"]):
        road_blocked = "yes"

    return {
        "incident_type": incident_type,
        "severity": severity,
        "people_trapped": people_trapped,
        "road_blocked": road_blocked,
        "ai_summary": (
            "Preliminary keyword-based assessment: " + description[:250]
        ),
        "priority_reason": (
            "Potential emergency keywords detected. "
            "Human verification is required."
        ),
        "analysis_status": "mock",
    }