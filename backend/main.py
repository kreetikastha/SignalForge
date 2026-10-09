from ai_service import analyze_report
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Report


Base.metadata.create_all(bind=engine)

# Add new columns to an existing SQLite database when needed.
new_columns = {
    "incident_type": "VARCHAR DEFAULT 'unknown' NOT NULL",
    "severity": "VARCHAR DEFAULT 'unknown' NOT NULL",
    "people_trapped": "VARCHAR DEFAULT 'unknown' NOT NULL",
    "road_blocked": "VARCHAR DEFAULT 'unknown' NOT NULL",
    "ai_summary": "TEXT",
    "priority_reason": "TEXT",
    "analysis_status": "VARCHAR DEFAULT 'pending' NOT NULL",
    "status": "VARCHAR DEFAULT 'new' NOT NULL",
}

with engine.begin() as connection:
    existing_columns = {
        column["name"]
        for column in inspect(engine).get_columns("reports")
    }

    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                text(
                    f"ALTER TABLE reports ADD COLUMN "
                    f"{column_name} {column_type}"
                )
            )


app = FastAPI(
    title="DisasterLens API",
    description="AI-powered emergency intelligence for disaster response",
    version="0.3.0",
)


class ReportCreate(BaseModel):
    description: str = Field(min_length=5, max_length=5000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def report_to_dict(report: Report):
    return {
        "id": report.id,
        "description": report.description,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "incident_type": report.incident_type,
        "severity": report.severity,
        "people_trapped": report.people_trapped,
        "road_blocked": report.road_blocked,
        "ai_summary": report.ai_summary,
        "priority_reason": report.priority_reason,
        "analysis_status": report.analysis_status,
        "status": report.status,
        "received_at": report.received_at.isoformat(),
    }


@app.get("/")
def root():
    return {
        "project": "DisasterLens",
        "team": "SignalForge",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}



@app.post("/reports", status_code=201)
def create_report(report: ReportCreate, db: Session = Depends(get_db)):
    # Save the original citizen report first.
    db_report = Report(
        description=report.description,
        latitude=report.latitude,
        longitude=report.longitude,
        analysis_status="pending",
    )

    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    # Run the temporary analyzer.
    try:
        result = analyze_report(db_report.description)

        db_report.incident_type = result["incident_type"]
        db_report.severity = result["severity"]
        db_report.people_trapped = result["people_trapped"]
        db_report.road_blocked = result["road_blocked"]
        db_report.ai_summary = result["ai_summary"]
        db_report.priority_reason = result["priority_reason"]
        db_report.analysis_status = result["analysis_status"]

        db.commit()
        db.refresh(db_report)

    except Exception:
        db.rollback()
        # Preserve the report even if analysis fails.
        db_report = db.query(Report).filter(
            Report.id == db_report.id
        ).first()

        if db_report:
            db_report.analysis_status = "failed"
            db.commit()
            db.refresh(db_report)

    return {
        "message": "Disaster report saved",
        "report": report_to_dict(db_report),
    }

@app.get("/reports")
def get_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.id.desc()).all()
    return [report_to_dict(report) for report in reports]



@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):
    reports = (
        db.query(Report)
        .order_by(Report.id.desc())
        .all()
    )

    return [
        {
            "incident_id": report.id,
            "incident_type": report.incident_type,
            "severity": report.severity,
            "description": report.description,
            "summary": report.ai_summary,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "people_trapped": report.people_trapped,
            "road_blocked": report.road_blocked,
            "priority_reason": report.priority_reason,
            "analysis_status": report.analysis_status,
            "status": report.status,
            "received_at": report.received_at.isoformat(),
            "supporting_reports": 1,
        }
        for report in reports
    ]