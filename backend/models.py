
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # AI analysis fields
    incident_type = Column(String, nullable=False, default="unknown")
    severity = Column(String, nullable=False, default="unknown")
    people_trapped = Column(String, nullable=False, default="unknown")
    road_blocked = Column(String, nullable=False, default="unknown")
    ai_summary = Column(Text, nullable=True)
    priority_reason = Column(Text, nullable=True)
    analysis_status = Column(String, nullable=False, default="pending")

    # Human-managed incident status
    status = Column(String, nullable=False, default="new")

    received_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )