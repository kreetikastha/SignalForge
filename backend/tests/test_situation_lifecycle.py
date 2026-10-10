import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp(prefix="disasterlens-feature-tests-"))
try:
    import main as backend_main  # noqa: E402
    from database import Base  # noqa: E402
    from models import Report  # noqa: E402
    from disasterlens_ai.schemas import IncidentMatch  # noqa: E402
finally:
    os.chdir(_cwd)


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'feature-tests.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autoflush=False, bind=engine)
    monkeypatch.setattr(backend_main, "SessionLocal", test_session)
    with TestClient(backend_main.app) as client:
        yield client, test_session
    engine.dispose()


def _report(session, **overrides):
    values = {
        "description": "Synthetic test incident",
        "latitude": 27.7172,
        "longitude": 85.324,
        "incident_type": "flood",
        "severity": "high",
        "status": "new",
        "analysis_status": "completed",
        "ai_summary": "Synthetic flood report",
        "received_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    report = Report(**values)
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def test_lifecycle_requires_order_and_records_actor_and_history(api):
    client, session_factory = api
    with session_factory() as session:
        report = _report(session)
        duplicate = _report(session, duplicate_of=report.id)
        report_id = report.id
        duplicate_id = duplicate.id

    invalid = client.patch(
        f"/reports/{report_id}/status",
        json={"status": "verified", "changed_by": "Responder A"},
    )
    assert invalid.status_code == 409

    updated = client.patch(
        f"/reports/{report_id}/status",
        json={"status": "under_review", "changed_by": "Responder A"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "under_review"
    assert updated.json()["status_updated_by"] == "Responder A"
    assert updated.json()["status_updated_at"]
    incidents = client.get("/incidents").json()
    assert {item["status"] for item in incidents} == {"under_review"}

    history = client.get(f"/reports/{report_id}/status-history")
    assert history.status_code == 200
    assert history.json() == [{
        "previous_status": "new",
        "status": "under_review",
        "changed_by": "Responder A",
        "changed_at": updated.json()["status_updated_at"],
    }]
    duplicate_history = client.get(
        f"/reports/{duplicate_id}/status-history"
    ).json()
    assert duplicate_history[0]["status"] == "under_review"


def test_situation_summary_counts_incidents_and_clusters_nearby_reports(api):
    client, session_factory = api
    with session_factory() as session:
        first = _report(session, location_text="Balkhu")
        duplicate = _report(
            session,
            location_text="Balkhu",
            incident_type="flood",
            duplicate_of=first.id,
        )
        _report(
            session,
            latitude=27.718,
            longitude=85.325,
            incident_type="fire",
            severity="critical",
        )
        _report(
            session,
            latitude=29.0,
            longitude=84.0,
            incident_type="landslide",
        )
        assert duplicate.id != first.id

    response = client.get("/situation")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reports"] == 4
    assert data["distinct_incidents"] == 3
    assert data["critical_incidents"] == 1
    assert data["type_counts"]["flood"] == 1
    assert data["hotspots"][0]["incident_count"] == 2
    assert data["hotspots"][0]["report_count"] == 3


def test_situation_briefing_uses_model_output_and_reports_evidence_count(api, monkeypatch):
    client, session_factory = api
    with session_factory() as session:
        _report(session, injuries_reported=1, hazards=["unstable structure"])

    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["system"] = system
        seen["payload"] = json.loads(user)
        return json.dumps({
            "briefing": "One high-severity synthetic flood is reported.",
            "key_points": ["Human verification is advised."],
        })

    monkeypatch.setattr(backend_main, "chat", fake_chat)
    response = client.post("/situation/briefing")

    assert response.status_code == 200
    assert response.json()["analysis_status"] == "completed"
    assert response.json()["based_on_incidents"] == 1
    assert response.json()["briefing"].startswith("One high-severity")
    assert len(seen["payload"]["incidents"]) == 1
    assert seen["payload"]["incidents"][0]["injuries_reported"] == 1
    assert seen["payload"]["incidents"][0]["hazards"] == ["unstable structure"]
    assert "untrusted evidence" in seen["system"]


def test_situation_briefing_provider_failure_is_explicit(api, monkeypatch):
    client, session_factory = api
    with session_factory() as session:
        _report(session)

    def fail_chat(*_args, **_kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(backend_main, "chat", fail_chat)
    response = client.post("/situation/briefing")

    assert response.status_code == 503
    assert "TimeoutError" in response.json()["detail"]


def test_duplicate_match_confidence_and_triage_evidence_are_persisted(api, monkeypatch):
    client, session_factory = api
    with session_factory() as session:
        root = _report(session)
        root_id = root.id

    monkeypatch.setattr(
        backend_main,
        "analyze_report",
        lambda *_args, **_kwargs: {
            "analysis_status": "completed",
            "incident_type": "flood",
            "severity": "critical",
            "people_trapped": "yes",
            "road_blocked": "unknown",
            "ai_summary": "Flood reported near the test bridge.",
            "priority_reason": "Critical: trapped people reported.",
            "confidence": 0.91,
            "location_text": "Balkhu",
            "people_affected": 30,
            "injuries_reported": 2,
            "vulnerable_groups": ["children"],
            "hazards": ["rising water"],
            "needs": ["rescue"],
            "flags": ["trapped_keyword_override"],
            "needs_review": True,
        },
    )
    monkeypatch.setattr(
        backend_main,
        "find_duplicate",
        lambda *_args, **_kwargs: IncidentMatch(
            is_duplicate=True,
            incident_id=str(root_id),
            similarity=0.87,
            reason="same place and similar flood description",
        ),
    )

    response = client.post(
        "/reports",
        json={
            "description": "Synthetic duplicate report near the test bridge",
            "latitude": 27.7172,
            "longitude": 85.324,
        },
    )

    assert response.status_code == 201
    report = response.json()["report"]
    assert report["duplicate"] is True
    assert report["duplicate_similarity"] == 0.87
    assert report["duplicate_reason"] == "same place and similar flood description"
    assert report["supporting_reports"] == 2
    assert report["people_affected"] == 30
    assert report["injuries_reported"] == 2
    assert report["vulnerable_groups"] == ["children"]
    assert report["hazards"] == ["rising water"]
    assert report["needs"] == ["rescue"]
    assert report["needs_review"] is True
