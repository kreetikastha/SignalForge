import re
import unicodedata
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


def find_duplicate(new: ReportAnalysis, existing: list[IncidentRef]) -> IncidentMatch:
    """v1 heuristic: same type required; score = 0.6*location overlap + 0.4*summary overlap.
    TODO: add embeddings / LLM judge for borderline cases, plus geo + time window."""
    best = IncidentMatch(is_duplicate=False, similarity=0.0)
    for inc in existing:
        if inc.incident_type != new.incident_type:
            continue
        loc = _jaccard(_tokens(new.location_text), _tokens(inc.location_text))
        txt = _jaccard(_tokens(new.summary), _tokens(inc.summary))
        score = 0.6 * loc + 0.4 * txt
        if score > best.similarity:
            best = IncidentMatch(is_duplicate=score >= config.DUPLICATE_THRESHOLD,
                                 incident_id=inc.id, similarity=round(score, 3),
                                 reason=f"location {loc:.2f}, text {txt:.2f}")
    if not best.is_duplicate:
        best.incident_id = None
    return best
