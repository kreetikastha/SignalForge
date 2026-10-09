import json
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from . import config
from .analyzer import _extract_json
from .client import chat
from .schemas import IncidentMatch, IncidentRef, IncidentType, ReportAnalysis

# Naturally correlated emergencies: one event is routinely reported as the
# other (a landslide blocks the road; an earthquake collapses a building; a
# flood strands traffic). Cross-type pairs are only compared when BOTH types
# appear in this matrix -- anything else keeps the strict same-type rule.
COMPATIBLE_INCIDENT_TYPES: dict[IncidentType, set[IncidentType]] = {
    IncidentType.LANDSLIDE: {IncidentType.LANDSLIDE, IncidentType.ROAD_BLOCKAGE},
    IncidentType.ROAD_BLOCKAGE: {IncidentType.ROAD_BLOCKAGE, IncidentType.LANDSLIDE, IncidentType.FLOOD},
    IncidentType.BUILDING_COLLAPSE: {IncidentType.BUILDING_COLLAPSE, IncidentType.EARTHQUAKE},
    IncidentType.EARTHQUAKE: {IncidentType.EARTHQUAKE, IncidentType.BUILDING_COLLAPSE},
    IncidentType.FLOOD: {IncidentType.FLOOD, IncidentType.ROAD_BLOCKAGE},
}

# Prompt file is read at most once per process and then kept in memory.
_JUDGE_SYSTEM_PROMPT: str | None = None


def _tokens(s: str | None) -> set[str]:
    # NFC keeps Devanagari vowel signs as combining marks; \w alone drops them.
    # The class adds the Devanagari block but stops before danda U+0964/U+0965
    # so sentence-ending '।' never glues to a word.
    s = unicodedata.normalize("NFC", s or "")
    return set(re.findall(r"[\w\u0900-\u0963\u0966-\u097F]+", s.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC so naive/aware never collide."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _geo_score(dist_km: float) -> float:
    if dist_km <= config.DUP_NEAR_KM:
        return 1.0
    if dist_km >= config.DUP_FAR_KM:
        return 0.0
    return (config.DUP_FAR_KM - dist_km) / (config.DUP_FAR_KM - config.DUP_NEAR_KM)


def _judge(new: ReportAnalysis, inc: IncidentRef,
           dist_km: float | None = None) -> tuple[bool, str] | None:
    """Ask the LLM whether two borderline reports describe the same incident.
    `dist_km` is the great-circle distance when both sides carry coordinates.
    Returns (same_incident, reason), or None on any failure. Never raises."""
    global _JUDGE_SYSTEM_PROMPT
    try:
        if _JUDGE_SYSTEM_PROMPT is None:  # read the prompt once, not per call
            _JUDGE_SYSTEM_PROMPT = (config.PROMPTS_DIR / "dedup_judge.txt").read_text(encoding="utf-8")
        report_b: dict = {"type": inc.incident_type.value,
                          "location": inc.location_text, "summary": inc.summary}
        if inc.received_at is not None:  # timestamp context for recency judging
            report_b["received_at"] = _as_utc(inc.received_at).isoformat()
        user = json.dumps({
            "report_a": {"type": new.incident_type.value,
                         "location": new.location_text, "summary": new.summary},
            "report_b": report_b,
            "distance_km": round(dist_km, 2) if dist_km is not None else None,
        }, ensure_ascii=False)
        data = _extract_json(chat(_JUDGE_SYSTEM_PROMPT, user))
        if not isinstance(data.get("same_incident"), bool):
            return None
        return data["same_incident"], str(data.get("reason", ""))
    except Exception:
        return None


def find_duplicate(new: ReportAnalysis, existing: list[IncidentRef], *,
                   latitude: float | None = None, longitude: float | None = None,
                   now: datetime | None = None) -> IncidentMatch:
    """v1 heuristic: types must be compatible (see COMPATIBLE_INCIDENT_TYPES);
    score = 0.6*location overlap + 0.4*summary overlap. When BOTH sides carry
    coordinates: score = 0.4*loc + 0.3*txt + 0.3*geo, an incident farther than
    DUP_HARD_CUTOFF_KM is never a duplicate, and pairs with no textual overlap
    score 0.0 -- proximity alone must never merge unrelated reports. Incidents
    with received_at older than DUP_WINDOW_HOURS before `now` are ignored.
    Borderline scores (JUDGE_LOW <= score < DUPLICATE_THRESHOLD) are optionally
    confirmed by an LLM judge when JUDGE_ENABLED and not STUB_MODE; the judge
    sees distance and incident types, and any judge failure silently keeps the
    heuristic result.
    TODO: add embeddings + time window tuning."""
    best = IncidentMatch(is_duplicate=False, similarity=0.0)
    best_inc: IncidentRef | None = None
    best_dist: float | None = None
    for inc in existing:
        allowed_types = COMPATIBLE_INCIDENT_TYPES.get(new.incident_type, {new.incident_type})
        if inc.incident_type not in allowed_types:
            continue
        if now is not None and inc.received_at is not None:
            if _as_utc(now) - _as_utc(inc.received_at) > timedelta(hours=config.DUP_WINDOW_HOURS):
                continue
        loc = _jaccard(_tokens(new.location_text), _tokens(inc.location_text))
        txt = _jaccard(_tokens(new.summary), _tokens(inc.summary))
        dist_km: float | None = None
        geo_reason = ""
        if (latitude is not None and longitude is not None
                and inc.latitude is not None and inc.longitude is not None):
            dist_km = _haversine_km(latitude, longitude, inc.latitude, inc.longitude)
            if dist_km > config.DUP_HARD_CUTOFF_KM:
                continue
            score = 0.4 * loc + 0.3 * txt + 0.3 * _geo_score(dist_km)
            if (loc == 0.0 and txt == 0.0) or (loc + txt < 0.1):
                # Geo guard: unrelated reports a few hundred metres apart must
                # not merge on distance alone. 0.0 keeps the score (and the
                # LLM judge) away as well.
                score = 0.0
            geo_reason = f", distance {dist_km:.2f} km"
        else:
            score = 0.6 * loc + 0.4 * txt
        if score > best.similarity:
            best = IncidentMatch(is_duplicate=score >= config.DUPLICATE_THRESHOLD,
                                 incident_id=inc.id, similarity=round(score, 3),
                                 reason=f"location {loc:.2f}, text {txt:.2f}{geo_reason}")
            best_inc = inc
            best_dist = dist_km
    if (not best.is_duplicate and best_inc is not None
            and config.JUDGE_ENABLED and not config.STUB_MODE
            and config.JUDGE_LOW <= best.similarity < config.DUPLICATE_THRESHOLD):
        verdict = _judge(new, best_inc, dist_km=best_dist)
        if verdict is not None and verdict[0]:
            best.is_duplicate = True
            if verdict[1]:
                best.reason = f"{best.reason}; judge: {verdict[1]}"
    if not best.is_duplicate:
        best.incident_id = None
    return best
