import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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
    monkeypatch.setattr(backend_main.ai_config, "STUB_MODE", True)
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
        root = _report(
            session,
            operation_status="rescue_active",
            assigned_team="North Team",
            dispatched_at=datetime.now(timezone.utc),
        )
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
            "people_trapped_count": 2,
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
    assert report["operation_status"] == "rescue_active"
    assert report["assigned_team"] == "North Team"
    assert report["people_trapped_count"] == 2


def test_grouping_precedes_triage_and_repeat_reporter_is_hashed(api, monkeypatch):
    from disasterlens_ai.schemas import (
        GroupingAnalysis,
        LegitimacyAnalysis,
    )

    client, session_factory = api
    calls = []
    monkeypatch.setattr(backend_main.ai_config, "STUB_MODE", False)
    monkeypatch.setattr(backend_main, "group_report", lambda _text: (
        calls.append("grouping")
        or GroupingAnalysis(
            incident_type="flood",
            location_text="Balkhu",
            summary="Flood near Balkhu.",
        )
    ))
    monkeypatch.setattr(backend_main, "find_duplicate", lambda *_args, **_kwargs: (
        calls.append("group-match")
        or IncidentMatch(is_duplicate=False, similarity=0)
    ))
    monkeypatch.setattr(backend_main, "analyze_report", lambda *_args, **_kwargs: (
        calls.append("triage")
        or {
            "analysis_status": "completed",
            "incident_type": "flood",
            "severity": "high",
            "people_trapped": "unknown",
            "road_blocked": "unknown",
            "ai_summary": "Flood reported near Balkhu.",
            "priority_reason": "Human verification advised.",
            "confidence": 0.9,
            "location_text": "Balkhu",
            "needs": [],
        }
    ))
    monkeypatch.setattr(backend_main, "assess_legitimacy", lambda _text: (
        calls.append("legitimacy")
        or LegitimacyAnalysis(
            label="genuine",
            confidence=0.9,
            reason="Specific event details are given.",
        )
    ))

    payload = {
        "description": "Flood near the Balkhu bridge after rain.",
        "latitude": 27.7,
        "longitude": 85.3,
        "reporter_id": "opaque-eval-reporter-0001",
    }
    first = client.post("/reports", json=payload)
    second = client.post(
        "/reports",
        json={**payload, "description": "Floodwater is still rising near Balkhu."},
    )

    assert first.status_code == second.status_code == 201
    assert calls[:4] == ["grouping", "group-match", "triage", "legitimacy"]
    first_report, second_report = first.json()["report"], second.json()["report"]
    assert first_report["repeat_reporter"] is False
    assert second_report["repeat_reporter"] is True
    assert second_report["reporter_repeat_count"] == 1
    assert second_report["legitimacy_label"] == "genuine"
    assert second_report["legitimacy_reason"] == "Specific event details are given."
    assert "reporter_hash" not in second_report
    with session_factory() as session:
        saved = session.query(Report).order_by(Report.id.asc()).all()
        assert saved[0].reporter_hash == saved[1].reporter_hash
        assert saved[0].reporter_hash != payload["reporter_id"]

    monkeypatch.setattr(backend_main.ai_config, "LEGIT_CONFIDENCE_THRESHOLD", 0.95)
    uploaded = client.post(
        "/reports/upload",
        data={**payload, "description": "Flood update sent as multipart data."},
        files={"image": ("", b"", "application/octet-stream")},
    )
    assert uploaded.status_code == 201
    uploaded_report = uploaded.json()["report"]
    assert uploaded_report["repeat_reporter"] is True
    assert uploaded_report["legitimacy_label"] == "uncertain"
    assert uploaded_report["urgency_score"] == first_report["urgency_score"]


def test_repeat_reporter_flag_respects_configured_time_window(api, monkeypatch):
    client, session_factory = api
    current = datetime.now(timezone.utc)
    with session_factory() as session:
        expired = _report(
            session,
            reporter_hash="same-hash",
            received_at=current - timedelta(
                hours=backend_main.ai_config.REPEAT_REPORTER_WINDOW_HOURS + 1
            ),
        )
        current_report = _report(
            session,
            reporter_hash="same-hash",
            received_at=current,
        )
        expected_ids = {expired.id, current_report.id}

    rows = client.get("/reports").json()
    current_entry = next(row for row in rows if row["id"] == current_report.id)
    assert current_entry["repeat_reporter"] is False
    assert {row["id"] for row in rows} >= expected_ids


def test_rescue_operation_flow_is_separate_audited_and_duplicate_aware(api):
    client, session_factory = api
    with session_factory() as session:
        report = _report(
            session,
            people_trapped="yes",
            people_affected=2,
            people_trapped_count=2,
            hazards=["rising water"],
        )
        duplicate = _report(
            session,
            duplicate_of=report.id,
            people_trapped="yes",
            people_affected=2,
            people_trapped_count=3,
        )
        report_id = report.id
        duplicate_id = duplicate.id

    initial = client.get(f"/incidents/{report_id}/operation")
    assert initial.status_code == 200
    assert initial.json()["operation_status"] == "reported"
    assert initial.json()["analysis_status"] == "completed"
    assert initial.json()["history"] == []
    assert initial.json()["supporting_reports"] == 2

    invalid_jump = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "rescue_active", "assigned_team": "North Team"},
    )
    assert invalid_jump.status_code == 409
    dispatch_without_team = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "verified"},
    )
    assert dispatch_without_team.status_code == 200
    dispatch_without_team = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "dispatched"},
    )
    assert dispatch_without_team.status_code == 422

    dispatched = client.patch(
        f"/incidents/{duplicate_id}/operation",
        json={
            "operation_status": "dispatched",
            "assigned_team": "North Team",
            "changed_by": "Responder B",
        },
    )
    assert dispatched.status_code == 200
    assert dispatched.json()["operation_status"] == "dispatched"
    assert dispatched.json()["assigned_team"] == "North Team"
    assert dispatched.json()["dispatched_at"]

    active = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "rescue_active", "changed_by": "Responder B"},
    )
    assert active.status_code == 200
    assert active.json()["operation_status"] == "rescue_active"
    complete_without_count = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "completed"},
    )
    assert complete_without_count.status_code == 422

    completed = client.patch(
        f"/incidents/{report_id}/operation",
        json={
            "operation_status": "completed",
            "people_rescued": 2,
            "changed_by": "Responder B",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["rescue_outcome"] == "rescued"
    assert completed.json()["people_rescued"] == 2
    assert completed.json()["history"][-1]["status"] == "completed"
    assert completed.json()["history"][-1]["changed_by"] == "Responder B"

    duplicate_state = client.get(f"/incidents/{duplicate_id}/operation").json()
    assert duplicate_state["operation_status"] == "completed"
    incidents = client.get("/incidents").json()
    assert {
        (item["operation_status"], item["assigned_team"], item["people_rescued"])
        for item in incidents
    } == {("completed", "North Team", 2)}
    assert {item["status"] for item in incidents} == {"new"}
    assert {item["analysis_status"] for item in incidents} == {"completed"}
    situation = client.get("/situation").json()["rescue_operations"]
    assert situation["active_operations"] == 0
    assert situation["teams_dispatched"] == 0
    assert situation["people_reported_trapped"] == 3
    assert situation["trapped_incidents"] == 1
    assert situation["people_rescued_confirmed"] == 2
    assert situation["confirmed_rescue_incidents"] == 1
    assert situation["awaiting_verification"] == 0


def test_rescue_summary_does_not_infer_people_or_dispatch_from_ai(api):
    client, session_factory = api
    with session_factory() as session:
        _report(
            session,
            people_trapped="yes",
            people_affected=None,
            analysis_status="completed",
        )
        _report(
            session,
            people_trapped="yes",
            people_affected=3,
            people_trapped_count=2,
            operation_status="dispatched",
            assigned_team="West Team",
        )

    summary = client.get("/situation").json()["rescue_operations"]
    assert summary["active_operations"] == 1
    assert summary["teams_dispatched"] == 1
    assert summary["people_reported_trapped"] == 2
    assert summary["trapped_incidents"] == 2
    assert summary["trapped_count_unknown"] == 1
    assert summary["people_rescued_confirmed"] == 0
    assert summary["awaiting_verification"] == 1


def test_false_alarm_is_a_recorded_terminal_operation_outcome(api):
    client, session_factory = api
    with session_factory() as session:
        report = _report(session, people_trapped="unknown")
        report_id = report.id

    response = client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "false_alarm", "changed_by": "Responder C"},
    )

    assert response.status_code == 200
    assert response.json()["operation_status"] == "false_alarm"
    assert response.json()["rescue_outcome"] == "false_alarm"
    assert response.json()["history"][0]["changed_by"] == "Responder C"
    assert client.patch(
        f"/incidents/{report_id}/operation",
        json={"operation_status": "verified"},
    ).status_code == 409
