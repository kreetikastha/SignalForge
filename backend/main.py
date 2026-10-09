import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, TypedDict

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.responses import Response

from ai_service import analyze_report
from database import Base, SessionLocal, engine
from models import Report
logger = logging.getLogger(__name__)

from disasterlens_ai import find_duplicate, score_urgency
from disasterlens_ai.schemas import IncidentRef, IncidentType, ReportAnalysis

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}

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
    "location_text": "VARCHAR",
    "confidence": "FLOAT",
    "urgency_score": "INTEGER",
    "duplicate_of": "INTEGER",
    "image_data": "BLOB",
    "image_mime_type": "VARCHAR",
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


class NormalizedAnalysis(TypedDict):
    incident_type: str
    severity: str
    people_trapped: Literal["yes", "no", "unknown"]
    road_blocked: Literal["yes", "no", "unknown"]
    ai_summary: str
    priority_reason: str
    analysis_status: str
    location_text: str | None
    confidence: float | None
    urgency_score: int | None
    needs: list[str]
    language: Literal["ne", "en", "other"]


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


def _normalize_report_flag(value: object) -> Literal["yes", "no", "unknown"]:
    normalized = str(value).lower()
    if normalized == "yes":
        return "yes"
    if normalized == "no":
        return "no"
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
    if any(word in text for word in ["landslide", "mudslide"]):
        return {
            "incident_type": "landslide",
            "severity": "high",
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
    return {
        "incident_type": "other",
        "severity": "medium",
        "people_trapped": "unknown",
        "road_blocked": "unknown",
    }


def _normalize_ai_result(
    raw_result, original_text: str = ""
) -> NormalizedAnalysis:
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

    # A completed result comes from adapter.analyze_for_backend(): it is the
    # model's structured decision and is taken verbatim. Keyword inference is
    # ONLY a fallback for mock/failed results (or an exception payload with no
    # fields) - never an override, otherwise a model severity 2 / type "other"
    # gets clobbered by the mere presence of "landslide" or "fire".
    status = str(result.get("analysis_status") or "").strip().lower()
    completed = status == "completed"
    fallback = None if completed else _infer_from_text(original_text)
    analysis_status = "completed" if completed else "mock"

    incident_type = result.get("incident_type") or result.get("incidentType")
    if isinstance(incident_type, Enum):
        incident_type = incident_type.value
    incident_type = str(incident_type or "").strip().lower().replace(" ", "_")
    if incident_type in {"", "unknown"}:
        # Missing value only: keywords may fill it in for mock results, while
        # a completed analysis that says "other" keeps "other".
        incident_type = (fallback["incident_type"] if fallback else "other") or "other"

    normalized_severity = _normalize_severity(result.get("severity"))
    if fallback is not None and normalized_severity == "unknown":
        normalized_severity = fallback["severity"]

    people_trapped = result.get("people_trapped") or result.get("people_trapped_by_ai")
    if people_trapped is None:
        needs = result.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        text_tokens = " ".join(str(item).lower() for item in needs)
        people_trapped = "yes" if any(
            keyword in text_tokens for keyword in ["rescue", "trapped", "stuck", "medical"]
        ) else (fallback["people_trapped"] if fallback else "unknown")

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
            road_blocked = fallback["road_blocked"] if fallback else "unknown"

    ai_summary = (
        result.get("ai_summary")
        or result.get("summary")
        or (
            f"Preliminary assessment: {original_text[:250]}"
            if original_text else "Preliminary assessment completed."
        )
    )
    # Keep adapter.py's priority_reason verbatim - it carries the safety flags
    # ("safety rule applied: trapped_keyword_override"). A generic placeholder
    # is only generated when nobody supplied one.
    priority_reason = str(result.get("priority_reason") or (
        "Severity is "
        + normalized_severity
        + " based on the report details. Human verification is recommended "
        "before dispatch."
    ))
    people_trapped = _normalize_report_flag(people_trapped)
    road_blocked = _normalize_report_flag(road_blocked)

    location_value = result.get("location_text")
    confidence_value = result.get("confidence")
    urgency_value = result.get("urgency_score")
    needs_value = result.get("needs", [])
    language_value = result.get("language", "en")

    return {
        "incident_type": str(incident_type),
        "severity": str(normalized_severity),
        "people_trapped": people_trapped,
        "road_blocked": road_blocked,
        "ai_summary": str(ai_summary),
        "priority_reason": str(priority_reason),
        "analysis_status": str(analysis_status),
        "location_text": (
            str(location_value) if location_value is not None else None
        ),
        "confidence": (
            float(confidence_value)
            if isinstance(confidence_value, (int, float))
            and 0 <= confidence_value <= 1
            else None
        ),
        "urgency_score": (
            int(urgency_value)
            if isinstance(urgency_value, (int, float))
            and 0 <= urgency_value <= 100
            else None
        ),
        "needs": (
            [str(value) for value in needs_value]
            if isinstance(needs_value, list)
            else []
        ),
        "language": (
            "ne"
            if language_value == "ne"
            else "en"
            if language_value == "en"
            else "other"
        ),
    }


def _severity_level(severity: str) -> int:
    return {
        "info": 1,
        "low": 2,
        "medium": 3,
        "high": 4,
        "critical": 5,
    }.get(severity.lower(), 3)


def _analysis_from_result(result: NormalizedAnalysis) -> ReportAnalysis:
    try:
        incident_type = IncidentType(str(result.get("incident_type", "other")))
    except ValueError:
        incident_type = IncidentType.OTHER
    confidence = result["confidence"] if result["confidence"] is not None else 0.1
    return ReportAnalysis(
        incident_type=incident_type,
        location_text=result["location_text"],
        severity=_severity_level(result["severity"]),
        people_trapped=result["people_trapped"],
        road_blocked=result["road_blocked"],
        needs=result["needs"],
        summary=result["ai_summary"],
        language=result["language"],
        confidence=confidence,
    )


def _incident_refs(reports: list[Report]):
    refs: list[IncidentRef] = []
    for report in reports:
        try:
            incident_type = IncidentType(report.incident_type)
        except ValueError:
            continue
        refs.append(
            IncidentRef(
                id=str(report.id),
                incident_type=incident_type,
                location_text=report.location_text,
                summary=report.ai_summary or report.description,
                latitude=report.latitude,
                longitude=report.longitude,
                received_at=report.received_at,
            )
        )
    return refs


def _duplicate_roots(reports: list[Report]) -> dict[int, int]:
    by_id = {report.id: report for report in reports}
    roots: dict[int, int] = {}
    for report in reports:
        current = report.id
        seen: set[int] = set()
        while current in by_id:
            if current in seen:
                break
            seen.add(current)
            parent = by_id[current].duplicate_of
            if parent is None:
                break
            current = parent
        roots[report.id] = current
    return roots


def report_to_dict(
    report: Report,
    *,
    duplicate: bool | None = None,
    supporting_reports: int = 1,
):
    received_at = report.received_at
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    else:
        received_at = received_at.astimezone(timezone.utc)

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
        "location_text": report.location_text,
        "confidence": report.confidence,
        "urgency_score": report.urgency_score,
        "duplicate": (
            report.duplicate_of is not None if duplicate is None else duplicate
        ),
        "duplicate_of": report.duplicate_of,
        "supporting_reports": supporting_reports,
        "status": report.status,
        "received_at": received_at.isoformat(),
        "has_image": report.image_data is not None,
        "image_url": f"/reports/{report.id}/image" if report.image_data else None,
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



def _save_report(
    report: ReportCreate,
    db: Session,
    image_data: bytes | None = None,
    image_mime_type: str | None = None,
):
    existing_reports = db.query(Report).order_by(Report.id.asc()).all()
    db_report = Report(
        description=report.description,
        latitude=report.latitude,
        longitude=report.longitude,
        analysis_status="pending",
        image_data=image_data,
        image_mime_type=image_mime_type,
    )

    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    report_id = db_report.id

    try:
        raw_result = analyze_report(db_report.description, image=image_data)
        result = _normalize_ai_result(
            raw_result,
            original_text=db_report.description,
        )
        analysis = _analysis_from_result(result)
        duplicate_count = 1
        try:
            match = find_duplicate(
                analysis,
                _incident_refs(existing_reports),
                latitude=db_report.latitude,
                longitude=db_report.longitude,
                now=datetime.now(timezone.utc),
            )
            if match.is_duplicate and match.incident_id is not None:
                duplicate_target = int(match.incident_id)
                roots = _duplicate_roots(existing_reports)
                db_report.duplicate_of = roots.get(
                    duplicate_target, duplicate_target
                )
                duplicate_count += sum(
                    root == db_report.duplicate_of
                    for root in roots.values()
                )
        except Exception:
            logger.exception(
                "Duplicate matching failed for report %s; saving it as a new incident.",
                report_id,
            )
        result["urgency_score"] = score_urgency(analysis, duplicate_count)
        if db_report.duplicate_of is not None:
            result["priority_reason"] = (
                result["priority_reason"]
                + f" Corroborating reports in this incident: {duplicate_count}."
            )

        db_report.incident_type = result["incident_type"]
        db_report.severity = result["severity"]
        db_report.people_trapped = result["people_trapped"]
        db_report.road_blocked = result["road_blocked"]
        db_report.ai_summary = result["ai_summary"]
        db_report.priority_reason = result["priority_reason"]
        db_report.analysis_status = result["analysis_status"]
        db_report.location_text = (
            str(result["location_text"])
            if result["location_text"] is not None
            else None
        )
        confidence_value = result["confidence"]
        db_report.confidence = (
            confidence_value
            if confidence_value is not None
            else None
        )
        db_report.urgency_score = (
            result["urgency_score"]
            if result["urgency_score"] is not None
            else score_urgency(analysis, duplicate_count)
        )

        db.commit()
        db.refresh(db_report)

    except Exception:
        db.rollback()
        logger.exception("AI analysis failed for report %s.", report_id)
        db_report = db.query(Report).filter(Report.id == report_id).first()
        if db_report is None:
            raise HTTPException(
                status_code=500,
                detail="The report was saved but could not be reloaded after analysis failed.",
            )
        db_report.analysis_status = "failed"
        db.commit()
        db.refresh(db_report)

    saved_reports = db.query(Report).all()
    roots = _duplicate_roots(saved_reports)
    report_root = roots.get(db_report.id, db_report.id)
    supporting_reports = sum(
        root == report_root for root in roots.values()
    )
    return {
        "message": "Disaster report saved",
        "report": report_to_dict(
            db_report,
            duplicate=report_root != db_report.id,
            supporting_reports=supporting_reports,
        ),
    }


def _read_validated_image(image: UploadFile | None) -> tuple[bytes | None, str | None]:
    if image is None or not image.filename:
        return None, None

    mime_type = (image.content_type or "").lower()
    if mime_type not in IMAGE_SIGNATURES:
        raise HTTPException(
            status_code=415,
            detail="Image must be a JPEG, PNG, or WebP file.",
        )

    if image.size is not None and image.size > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image must be 5 MB or smaller.",
        )

    image_data = image.file.read(MAX_IMAGE_BYTES + 1)
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image must be 5 MB or smaller.",
        )

    signature_matches = image_data.startswith(IMAGE_SIGNATURES[mime_type])
    if mime_type == "image/webp":
        signature_matches = (
            signature_matches and image_data[8:12] == b"WEBP"
        )
    if not signature_matches:
        raise HTTPException(
            status_code=415,
            detail="The image content does not match its declared file type.",
        )
    return image_data, mime_type


@app.post("/reports", status_code=201)
def create_report(report: ReportCreate, db: Session = Depends(get_db)):
    return _save_report(report, db)


@app.post("/reports/upload", status_code=201)
def create_report_with_image(
    description: str = Form(..., min_length=5, max_length=5000),
    latitude: float = Form(..., ge=-90, le=90),
    longitude: float = Form(..., ge=-180, le=180),
    image: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    image_data, image_mime_type = _read_validated_image(image)
    report = ReportCreate(
        description=description,
        latitude=latitude,
        longitude=longitude,
    )
    return _save_report(report, db, image_data, image_mime_type)


@app.get("/reports/{report_id}/image")
def get_report_image(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None or report.image_data is None or report.image_mime_type is None:
        raise HTTPException(status_code=404, detail="Report image not found.")
    return Response(
        content=report.image_data,
        media_type=report.image_mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/reports")
def get_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.id.desc()).all()
    roots = _duplicate_roots(reports)
    group_sizes: dict[int, int] = {}
    for root in roots.values():
        group_sizes[root] = group_sizes.get(root, 0) + 1
    return [
        report_to_dict(
            report,
            duplicate=roots.get(report.id, report.id) != report.id,
            supporting_reports=group_sizes.get(
                roots.get(report.id, report.id), 1
            ),
        )
        for report in reports
    ]



@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):
    reports = (
        db.query(Report)
        .order_by(Report.id.desc())
        .all()
    )

    roots = _duplicate_roots(reports)
    group_sizes: dict[int, int] = {}
    for root in roots.values():
        group_sizes[root] = group_sizes.get(root, 0) + 1

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
            "location_text": report.location_text,
            "confidence": report.confidence,
            "urgency_score": report.urgency_score,
            "duplicate": roots.get(report.id, report.id) != report.id,
            "duplicate_of": report.duplicate_of,
            "has_image": report.image_data is not None,
            "image_url": f"/reports/{report.id}/image" if report.image_data else None,
            "status": report.status,
            "received_at": report_to_dict(report)["received_at"],
            "supporting_reports": group_sizes.get(
                roots.get(report.id, report.id), 1
            ),
        }
        for report in reports
    ]