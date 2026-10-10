from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field

# Canonical needs vocabulary (used for normalization and evaluation)
_NEEDS_CANONICAL = {
    "rescue",
    "medical",
    "food",
    "water",
    "shelter",
    "road_clearing",
    "firefighting",
    "evacuation",
    "other",
}

# Synonym mapping to canonical terms
_NEEDS_SYNONYMS: dict[str, str] = {
    # medical
    "ambulance": "medical",
    "doctor": "medical",
    "first_aid": "medical",
    "medical_aid": "medical",
    "medical_help": "medical",
    # rescue
    "search_and_rescue": "rescue",
    "extraction": "rescue",
    "trapped": "rescue",
    # firefighting
    "fire_brigade": "firefighting",
    "fire_fighting": "firefighting",
    # water
    "drinking_water": "water",
    # shelter
    "housing": "shelter",
    "tent": "shelter",
    "shelter_needed": "shelter",
    # road_clearing
    "clear_road": "road_clearing",
    "debris_removal": "road_clearing",
    "road_clearance": "road_clearing",
    # evacuation
    "evacuate": "evacuation",
}


def normalize_needs(needs: list[str]) -> list[str]:
    """Map needs to canonical vocabulary, deduplicate preserving order.

    Unknown terms map to "other" only if the result would otherwise be empty.
    """
    seen: set[str] = set()
    out: list[str] = []
    for n in needs or []:
        key = str(n).strip().lower()
        if not key:
            continue
        canonical = _NEEDS_SYNONYMS.get(key, key if key in _NEEDS_CANONICAL else "other")
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    # If everything mapped to "other" and there are no other terms, keep one "other"
    if out == ["other"] and needs:
        return ["other"]
    # Drop "other" if we have at least one canonical term
    if len(out) > 1 and "other" in out:
        out = [x for x in out if x != "other"]
    return out


class IncidentType(str, Enum):
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    FIRE = "fire"
    EARTHQUAKE = "earthquake"
    BUILDING_COLLAPSE = "building_collapse"
    ROAD_BLOCKAGE = "road_blockage"
    MEDICAL = "medical"
    OTHER = "other"


class ReportAnalysis(BaseModel):
    incident_type: IncidentType
    location_text: Optional[str] = None
    severity: int = Field(ge=1, le=5)
    people_affected: Optional[int] = None
    people_trapped_count: Optional[int] = Field(default=None, ge=0)
    injuries_reported: Optional[int] = Field(default=None, ge=0)
    people_trapped: Literal["yes", "no", "unknown"] = "unknown"
    road_blocked: Literal["yes", "no", "unknown"] = "unknown"
    hazards: list[str] = Field(default_factory=list)
    vulnerable_groups: list[str] = Field(default_factory=list)  # children, elderly, injured
    needs: list[str] = Field(default_factory=list)  # rescue, medical, food, shelter
    summary: str
    language: Literal["ne", "en", "other"] = "en"
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class GroupingAnalysis(BaseModel):
    incident_type: IncidentType
    location_text: Optional[str] = None
    summary: str = Field(min_length=1, max_length=500)


class LegitimacyAnalysis(BaseModel):
    label: Literal["genuine", "uncertain", "prank", "spam"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)


class IncidentRef(BaseModel):
    """Minimal view of an existing incident, supplied by the backend for dedup."""
    id: str
    incident_type: IncidentType
    location_text: Optional[str] = None
    summary: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    received_at: Optional[datetime] = None


class IncidentMatch(BaseModel):
    is_duplicate: bool
    incident_id: Optional[str] = None
    similarity: float = Field(ge=0, le=1)
    reason: str = ""
