
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # AI analysis fields
    incident_type: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown"
    )
    severity: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    people_trapped: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown"
    )
    road_blocked: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown"
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
    location_text: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    people_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injuries_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hazards: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    vulnerable_groups: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    needs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_mime_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Human-managed incident status
    status: Mapped[str] = mapped_column(String, nullable=False, default="new")
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class IncidentStatusEvent(Base):
    __tablename__ = "incident_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    previous_status: Mapped[str] = mapped_column(String, nullable=False)
    new_status: Mapped[str] = mapped_column(String, nullable=False)
    changed_by: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )