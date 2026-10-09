from enum import Enum

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ai_service import analyze_report
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def _normalize_severity(value):
    if isinstance(value, (int, float)):
        value = int(value)
        if value >= 5:
            return "critical"
        if value >= 4:
            return "high"
        if value >= 3:
            return "medium"
        if value >= 2:
            return "low"
        return "info"

    label = str(value or "unknown").strip().lower()
    if label in {"critical", "high", "medium", "low", "info", "unknown"}:
        return label
    if label in {"urgent", "emergency"}:
        return "critical"
    return "unknown"


def _infer_from_text(original_text: str):
    text = (original_text or "").lower()
    if any(word in text for word in ["flood", "flooding", "inundated", "overflowing"]):
        return {
            "incident_type": "flood",
            "severity": "critical" if "people trapped" in text or "stuck" in text else "high",
            "people_trapped": "yes" if "people trapped" in text or "stuck" in text else "unknown",
            "road_blocked": "yes" if "road blocked" in text or "road is blocked" in text else "unknown",
        }
    if any(word in text for word in ["collapse", "collapsed", "trapped", "stuck on roof"]):
        return {
            "incident_type": "building_collapse",
            "severity": "critical" if "people trapped" in text or "stuck" in text else "high",
            "people_trapped": "yes" if "people trapped" in text or "stuck" in text else "unknown",
            "road_blocked": "yes" if "road blocked" in text or "road is blocked" in text else "unknown",
        }
    if any(word in text for word in ["fire", "burning", "smoke"]):
        return {
            "incident_type": "fire",
            "severity": "high",
            "people_trapped": "yes" if "people trapped" in text or "stuck" in text else "unknown",
            "road_blocked": "yes" if "road blocked" in text or "road is blocked" in text else "unknown",
        }
    if any(word in text for word in ["landslide", "mudslide"]):
        return {
            "incident_type": "landslide",
            "severity": "high",
            "people_trapped": "yes" if "people trapped" in text or "stuck" in text else "unknown",
            "road_blocked": "yes" if "road blocked" in text or "road is blocked" in text else "unknown",
        }
    return {
        "incident_type": "other",
        "severity": "medium",
        "people_trapped": "unknown",
        "road_blocked": "unknown",
    }


def _normalize_ai_result(raw_result, original_text: str = ""):
    if hasattr(raw_result, "model_dump"):
        result = raw_result.model_dump()
    elif hasattr(raw_result, "dict"):
        result = raw_result.dict()
    elif isinstance(raw_result, dict):
        result = raw_result
    else:
        result = {}

    if not isinstance(result, dict):
        result = {}

    fallback = _infer_from_text(original_text)
    incident_type = result.get("incident_type") or result.get("incidentType") or fallback["incident_type"]
    if isinstance(incident_type, Enum):
        incident_type = incident_type.value
    incident_type = str(incident_type).strip().lower().replace(" ", "_")
    if incident_type in {"other", "unknown", ""}:
        incident_type = fallback["incident_type"]

    severity_value = result.get("severity")
    normalized_severity = _normalize_severity(severity_value)
    if normalized_severity in {"unknown", "info", "low", "medium"} and fallback["severity"] in {"high", "critical"}:
        normalized_severity = fallback["severity"]

    people_trapped = result.get("people_trapped") or result.get("people_trapped_by_ai")
    if people_trapped is None:
        needs = result.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        text_tokens = " ".join(str(item).lower() for item in needs)
        people_trapped = "yes" if any(
            keyword in text_tokens for keyword in ["rescue", "trapped", "stuck", "medical"]
        ) else fallback["people_trapped"]

    road_blocked = result.get("road_blocked") or result.get("road_blockage")
    if road_blocked is None:
        summary_text = str(result.get("summary", "")).lower()
        if "road_blockage" in incident_type or (
            "road" in summary_text
            and any(
                keyword in summary_text
                for keyword in ["blocked", "closed", "cut off", "impassable"]
            )
        ):
            road_blocked = "yes"
        else:
            road_blocked = fallback["road_blocked"]

    ai_summary = (
        result.get("ai_summary")
        or result.get("summary")
        or (
            f"Preliminary assessment: {original_text[:250]}"
            if original_text else "Preliminary assessment completed."
        )
    )
    priority_reason = result.get("priority_reason") or (
        "Severity is "
        + normalized_severity
        + ". Human verification is recommended before dispatch."
    )
    analysis_status = result.get("analysis_status") or "completed"

    return {
        "incident_type": incident_type,
        "severity": normalized_severity,
        "people_trapped": str(people_trapped).lower() if people_trapped is not None else "unknown",
        "road_blocked": str(road_blocked).lower() if road_blocked is not None else "unknown",
        "ai_summary": str(ai_summary),
        "priority_reason": str(priority_reason),
        "analysis_status": str(analysis_status),
    }


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
    report_id = db_report.id

    # Run the project AI analyzer and normalize its output into the persisted model.
    try:
        result = _normalize_ai_result(
            analyze_report(db_report.description),
            original_text=db_report.description,
        )

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
        db_report = db.query(Report).filter(Report.id == report_id).first()
        if db_report is None:
            raise HTTPException(
                status_code=500,
                detail="The report was saved but could not be reloaded after analysis failed.",
            )
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