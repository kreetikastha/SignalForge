import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from . import config
from .schemas import IncidentMatch, IncidentRef, ReportAnalysis


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


def find_duplicate(new: ReportAnalysis, existing: list[IncidentRef], *,
                   latitude: float | None = None, longitude: float | None = None,
                   now: datetime | None = None) -> IncidentMatch:
    """v1 heuristic: same type required; score = 0.6*location overlap + 0.4*summary overlap.
    When BOTH sides carry coordinates: score = 0.4*loc + 0.3*txt + 0.3*geo, and an
    incident farther than DUP_HARD_CUTOFF_KM is never a duplicate. Incidents with
    received_at older than DUP_WINDOW_HOURS before `now` are ignored.
    TODO: add embeddings / LLM judge for borderline cases, plus time window tuning."""
    best = IncidentMatch(is_duplicate=False, similarity=0.0)
    for inc in existing:
        if inc.incident_type != new.incident_type:
            continue
        if now is not None and inc.received_at is not None:
            if _as_utc(now) - _as_utc(inc.received_at) > timedelta(hours=config.DUP_WINDOW_HOURS):
                continue
        loc = _jaccard(_tokens(new.location_text), _tokens(inc.location_text))
        txt = _jaccard(_tokens(new.summary), _tokens(inc.summary))
        geo_reason = ""
        if (latitude is not None and longitude is not None
                and inc.latitude is not None and inc.longitude is not None):
            dist_km = _haversine_km(latitude, longitude, inc.latitude, inc.longitude)
            if dist_km > config.DUP_HARD_CUTOFF_KM:
                continue
            score = 0.4 * loc + 0.3 * txt + 0.3 * _geo_score(dist_km)
            geo_reason = f", distance {dist_km:.2f} km"
        else:
            score = 0.6 * loc + 0.4 * txt
        if score > best.similarity:
            best = IncidentMatch(is_duplicate=score >= config.DUPLICATE_THRESHOLD,
                                 incident_id=inc.id, similarity=round(score, 3),
                                 reason=f"location {loc:.2f}, text {txt:.2f}{geo_reason}")
    if not best.is_duplicate:
        best.incident_id = None
    return best
