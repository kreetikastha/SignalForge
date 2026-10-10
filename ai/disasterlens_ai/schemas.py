from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


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
