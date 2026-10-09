from datetime import datetime, timedelta, timezone

from disasterlens_ai import config, dedup, find_duplicate, score_urgency
from disasterlens_ai.dedup import _tokens
from disasterlens_ai.schemas import IncidentRef, IncidentType, ReportAnalysis


def _a(loc, summ, typ=IncidentType.FLOOD, sev=3):
    return ReportAnalysis(incident_type=typ, location_text=loc, severity=sev, summary=summ, confidence=0.8)


def _ref(id, loc, summ, typ=IncidentType.FLOOD, lat=None, lon=None, received_at=None):
    return IncidentRef(id=id, incident_type=typ, location_text=loc, summary=summ,
                       latitude=lat, longitude=lon, received_at=received_at)


def test_duplicate_found():
    existing = [IncidentRef(id="i1", incident_type=IncidentType.FLOOD, location_text="Balkhu bridge",
                            summary="River flooding houses near Balkhu bridge")]
    m = find_duplicate(_a("Balkhu bridge", "Flooding houses near Balkhu bridge"), existing)
    assert m.is_duplicate and m.incident_id == "i1"


def test_different_type_not_duplicate():
    existing = [IncidentRef(id="i1", incident_type=IncidentType.FIRE, location_text="Balkhu bridge", summary="fire")]
    assert not find_duplicate(_a("Balkhu bridge", "flood"), existing).is_duplicate


def test_urgency_scales_and_caps():
    assert score_urgency(_a("x", "y", sev=5), duplicate_count=10) <= 100
    assert score_urgency(_a("x", "y", sev=5)) > score_urgency(_a("x", "y", sev=1))


def test_nepali_tokens_keep_vowel_signs():
    assert _tokens("बनेपामा पहिरो") == {"बनेपामा", "पहिरो"}


def test_nepali_danda_not_glued_to_word():
    assert _tokens("बाटो बन्द छ।") == {"बाटो", "बन्द", "छ"}


def test_nepali_duplicate_landslide_found():
    existing = [IncidentRef(id="n1", incident_type=IncidentType.LANDSLIDE, location_text="बनेपा",
                            summary="बनेपामा पहिरोले बाटो रोकियो")]
    m = find_duplicate(_a("बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ=IncidentType.LANDSLIDE), existing)
    assert m.is_duplicate and m.incident_id == "n1"


def test_nepali_different_locations_not_duplicate():
    existing = [IncidentRef(id="n2", incident_type=IncidentType.LANDSLIDE, location_text="ललितपुर",
                            summary="ललितपुरमा पहिरोले बाटो रोकियो")]
    m = find_duplicate(_a("बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ=IncidentType.LANDSLIDE), existing)
    assert not m.is_duplicate


def test_near_pair_with_weak_text_is_duplicate():
    # ~100 m apart, same location token, only "road/on/the/main" style overlap
    existing = [_ref("g1", "Kalimati", "Burst water main on the side road",
                     lat=27.7059, lon=85.295)]
    m = find_duplicate(_a("Kalimati", "Fire in a shop on the main road"), existing,
                       latitude=27.705, longitude=85.295)
    assert m.is_duplicate and m.incident_id == "g1"
    assert "distance" in m.reason and "km" in m.reason


def test_same_text_eight_km_apart_not_duplicate():
    existing = [_ref("g2", "Kalimati", "Fire in a shop on the main road",
                     lat=27.77735, lon=85.295)]  # ~8 km north
    m = find_duplicate(_a("Kalimati", "Fire in a shop on the main road"), existing,
                       latitude=27.705, longitude=85.295)
    assert not m.is_duplicate and m.incident_id is None


def test_incident_older_than_window_is_skipped():
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    new = _a("Balkhu bridge", "Flooding houses near Balkhu bridge")
    old = [_ref("i1", "Balkhu bridge", "River flooding houses near Balkhu bridge",
                received_at=now - timedelta(hours=25))]
    fresh = [_ref("i2", "Balkhu bridge", "River flooding houses near Balkhu bridge",
                  received_at=now - timedelta(hours=1))]
    assert not find_duplicate(new, old, now=now).is_duplicate
    assert find_duplicate(new, fresh, now=now).is_duplicate


def test_no_coordinates_keeps_old_formula():
    m = find_duplicate(_a("Balkhu bridge", "Flooding houses near Balkhu bridge"),
                       [_ref("i1", "Balkhu bridge", "River flooding houses near Balkhu bridge")])
    # 0.6*1.0 + 0.4*(5/6) = 0.933...
    assert m.is_duplicate and m.incident_id == "i1" and m.similarity == 0.933
    assert "distance" not in m.reason


def test_naive_and_aware_datetimes_do_not_raise():
    naive_now = datetime(2026, 10, 9, 12, 0)
    aware_now = naive_now.replace(tzinfo=timezone.utc)
    new = _a("Balkhu bridge", "Flooding houses near Balkhu bridge")
    naive_inc = [_ref("i1", "Balkhu bridge", "River flooding houses near Balkhu bridge",
                      received_at=naive_now - timedelta(hours=1))]
    aware_inc = [_ref("i2", "Balkhu bridge", "River flooding houses near Balkhu bridge",
                      received_at=aware_now - timedelta(hours=1))]
    assert find_duplicate(new, naive_inc, now=aware_now).is_duplicate
    assert find_duplicate(new, aware_inc, now=naive_now).is_duplicate
    assert find_duplicate(new, naive_inc, now=naive_now).is_duplicate


def _borderline_pair():
    # heuristic score 0.6*(1/3) + 0.4*(3/5) = 0.44 -> JUDGE_LOW <= x < DUPLICATE_THRESHOLD
    return (_a("Kalimati bridge", "Fire in a shop"),
            [_ref("j1", "Kalimati market", "Fire at a shop")])


def _enable_judge(monkeypatch):
    monkeypatch.setattr(config, "JUDGE_ENABLED", True)
    monkeypatch.setattr(config, "STUB_MODE", False)


def test_judge_true_marks_borderline_duplicate(monkeypatch):
    _enable_judge(monkeypatch)
    seen = {}

    def fake_chat(system, user):
        _ = system, user
        seen["system"], seen["user"] = system, user
        return '{"same_incident": true, "reason": "same shop fire at Kalimati"}'

    monkeypatch.setattr(dedup, "chat", fake_chat)
    new, existing = _borderline_pair()
    m = find_duplicate(new, existing)
    assert m.is_duplicate and m.incident_id == "j1"
    assert "same shop fire at Kalimati" in m.reason
    assert "Kalimati bridge" in seen["user"] and "Kalimati market" in seen["user"]
    assert "same_incident" in seen["system"]


def test_judge_exception_keeps_heuristic(monkeypatch):
    _enable_judge(monkeypatch)

    def boom(system, user):
        _ = system, user
        raise RuntimeError("no network")

    monkeypatch.setattr(dedup, "chat", boom)
    new, existing = _borderline_pair()
    m = find_duplicate(new, existing)
    assert not m.is_duplicate and m.incident_id is None and m.similarity == 0.44


def test_judge_garbage_output_keeps_heuristic(monkeypatch):
    _enable_judge(monkeypatch)
    def garbage_chat(system, user):
        _ = system, user
        return "sorry, no json here"

    monkeypatch.setattr(dedup, "chat", garbage_chat)
    new, existing = _borderline_pair()
    m = find_duplicate(new, existing)
    assert not m.is_duplicate and m.incident_id is None and m.similarity == 0.44


def test_judge_disabled_never_calls_chat(monkeypatch):
    monkeypatch.setattr(config, "JUDGE_ENABLED", False)
    monkeypatch.setattr(config, "STUB_MODE", False)
    calls = []
    monkeypatch.setattr(
        dedup, "chat", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    new, existing = _borderline_pair()
    m = find_duplicate(new, existing)
    assert calls == []
    assert not m.is_duplicate and m.similarity == 0.44
