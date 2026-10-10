from . import config
from .analyzer import _extract_json
from .client import chat
from .schemas import GroupingAnalysis, IncidentType


def group_report(text: str) -> GroupingAnalysis:
    if config.STUB_MODE:
        return GroupingAnalysis(
            incident_type=IncidentType.OTHER,
            summary=text.strip()[:500] or "Report details unavailable",
        )
    system = (config.PROMPTS_DIR / "grouping_system.txt").read_text(
        encoding="utf-8"
    )
    payload = _extract_json(
        chat(
            system,
            text,
            timeout=config.REQUEST_TIMEOUT,
            model=config.GROUPING_MODEL,
        )
    )
    if payload.get("incident_type") is None:
        payload["incident_type"] = IncidentType.OTHER.value
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        payload["summary"] = text.strip()[:500] or "Report details unavailable"
    return GroupingAnalysis(**payload)
