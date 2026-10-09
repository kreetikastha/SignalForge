
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, LargeBinary, String, Text
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
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_mime_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Human-managed incident status
    status: Mapped[str] = mapped_column(String, nullable=False, default="new")

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )