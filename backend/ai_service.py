import logging
import sys
from pathlib import Path

AI_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "ai"
if str(AI_PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_PACKAGE_DIR))

logger = logging.getLogger(__name__)


def _mock_analyze(description: str) -> dict[str, str]:
    text = description.lower()

    incident_type = "unknown"
    severity = "medium"
    people_trapped = "unknown"
    road_blocked = "unknown"

    if any(word in text for word in ["collapse", "collapsed"]):
        incident_type = "building_collapse"
    elif any(word in text for word in ["flood", "flooding", "inundated"]):
        incident_type = "flood"
        severity = (
            "critical"
            if any(
                phrase in text
                for phrase in ["people trapped", "people are trapped", "stuck"]
            )
            else "high"
        )
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


def analyze_report(description: str) -> dict[str, str]:
    try:
        from disasterlens_ai.adapter import analyze_for_backend

        return analyze_for_backend(description)
    except Exception as exc:
        logger.warning(
            "AI analysis failed; using keyword-based fallback.",
            exc_info=True,
        )
        result = _mock_analyze(description)
        result["priority_reason"] = (
            f"AI analysis unavailable ({type(exc).__name__}); "
            "keyword-based fallback used. Human verification is required."
        )
        return result
