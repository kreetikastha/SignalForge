import json
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

    def fake_chat(system, user, **kwargs):
        _ = system, user, kwargs
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


def test_judge_timeout_keeps_heuristic(monkeypatch):
    _enable_judge(monkeypatch)

    def timeout_chat(system, user):
        _ = system, user
        raise TimeoutError("judge timed out")

    monkeypatch.setattr(dedup, "chat", timeout_chat)
    new, existing = _borderline_pair()
    m = find_duplicate(new, existing)
    # Heuristic score 0.44 should be kept, judge failure silently ignored
    assert not m.is_duplicate and m.incident_id is None and m.similarity == 0.44


def test_judge_timeout_never_raises(monkeypatch):
    """Mock chat that hangs; find_duplicate must not raise and must keep heuristic."""
    _enable_judge(monkeypatch)

    def hang_chat(system, user):
        raise TimeoutError("judge hung")

    monkeypatch.setattr(dedup, "chat", hang_chat)
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


# ------------------------------------------------------- cross-type matching

def test_cross_type_landslide_and_road_blockage_match():
    # A landslide that blocks the road is reported under either type.
    existing = [_ref("x1", "बनेपा", "बनेपामा पहिरोले बाटो रोकियो", typ=IncidentType.LANDSLIDE)]
    m = find_duplicate(_a("बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ=IncidentType.ROAD_BLOCKAGE),
                       existing)
    assert m.is_duplicate and m.incident_id == "x1"

    # ...and the mirror direction must work too.
    reverse = [_ref("x2", "बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ=IncidentType.ROAD_BLOCKAGE)]
    m2 = find_duplicate(_a("बनेपा", "बनेपामा पहिरोले बाटो रोकियो", typ=IncidentType.LANDSLIDE), reverse)
    assert m2.is_duplicate and m2.incident_id == "x2"


def test_cross_type_flood_and_road_blockage_match():
    existing = [_ref("x3", "Kalimati", "Water flowing across the road after the river overtopped",
                     typ=IncidentType.FLOOD)]
    m = find_duplicate(_a("Kalimati", "Road unusable, water flowing across it from the river",
                          typ=IncidentType.ROAD_BLOCKAGE), existing)
    assert m.is_duplicate and m.incident_id == "x3"


def test_cross_type_earthquake_and_building_collapse_match():
    existing = [_ref("x4", "Bhaktapur", "Wall of the five-storey house came down",
                     typ=IncidentType.BUILDING_COLLAPSE)]
    m = find_duplicate(_a("Bhaktapur", "Strong tremor brought the house wall down",
                          typ=IncidentType.EARTHQUAKE), existing)
    assert m.is_duplicate and m.incident_id == "x4"


def test_unrelated_cross_type_pairs_stay_separate():
    # FIRE/MEDICAL are not correlated -> strict same-type rule still applies.
    existing = [_ref("u1", "Kalimati", "Fire in a shop", typ=IncidentType.FIRE)]
    m = find_duplicate(_a("Kalimati", "Fire in a shop", typ=IncidentType.MEDICAL), existing)
    assert not m.is_duplicate and m.incident_id is None


# ------------------------------------------------------- geo-score guard

def _geo_only_pair():
    # 100 m apart, zero location and zero summary overlap -> proximity alone.
    existing = [_ref("g3", "Kalimati", "Shop gutted by flames", typ=IncidentType.FIRE,
                     lat=27.7059, lon=85.295)]
    new = _a("Jorpati", "LPG cylinder blast inside a house", typ=IncidentType.FIRE)
    return new, existing


def test_geo_proximity_alone_never_marks_duplicate():
    new, existing = _geo_only_pair()
    m = find_duplicate(new, existing, latitude=27.705, longitude=85.295)
    assert not m.is_duplicate
    assert m.incident_id is None
    assert m.similarity == 0.0
    assert m.similarity < config.JUDGE_LOW


def test_geo_only_pair_is_never_sent_to_the_judge(monkeypatch):
    _enable_judge(monkeypatch)
    calls = []
    monkeypatch.setattr(dedup, "chat", lambda *a, **k: calls.append((a, k)) or "{}")

    new, existing = _geo_only_pair()
    m = find_duplicate(new, existing, latitude=27.705, longitude=85.295)

    assert calls == []
    assert not m.is_duplicate


def test_weak_textual_overlap_nearby_still_scores_below_judge_low():
    # loc + txt = 0 + 1/11 < 0.1 -> the geo guard zeroes the score, so the
    # candidate is not even recorded and JUDGE_LOW can never be reached.
    existing = [_ref("g4", "Kalimati", "Shop gutted by flames", typ=IncidentType.FIRE,
                     lat=27.7059, lon=85.295)]
    new = _a("Jorpati", "A shop in Kalimati caught fire late evening", typ=IncidentType.FIRE)
    m = find_duplicate(new, existing, latitude=27.705, longitude=85.295)
    assert not m.is_duplicate
    assert m.incident_id is None
    assert m.similarity < config.JUDGE_LOW


# ------------------------------------------------------- judge context/cache

def _borderline_pair_near():
    # ~1.65 km apart -> geo 0.5: 0.4*(1/3) + 0.3*(3/5) + 0.3*0.5 = 0.463,
    # i.e. JUDGE_LOW <= score < DUPLICATE_THRESHOLD.
    new = _a("Kalimati bridge", "Fire in a shop", typ=IncidentType.FIRE)
    existing = [_ref("j2", "Kalimati market", "Fire at a shop", typ=IncidentType.FIRE,
                     lat=27.7198, lon=85.295)]
    return new, existing


def test_judge_payload_carries_types_and_distance(monkeypatch):
    _enable_judge(monkeypatch)
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["system"], seen["user"] = system, user
        return '{"same_incident": false, "reason": "different shops"}'

    monkeypatch.setattr(dedup, "chat", fake_chat)
    new, existing = _borderline_pair_near()
    m = find_duplicate(new, existing, latitude=27.705, longitude=85.295)

    payload = json.loads(seen["user"])
    assert payload["report_a"]["type"] == "fire"
    assert payload["report_a"]["location"] == "Kalimati bridge"
    assert payload["report_a"]["summary"] == "Fire in a shop"
    assert payload["report_b"]["type"] == "fire"
    assert payload["report_b"]["location"] == "Kalimati market"
    assert payload["distance_km"] == round(payload["distance_km"], 2)
    assert 1.0 < payload["distance_km"] < 2.5
    assert not m.is_duplicate  # the judge said "different shops"


def test_judge_payload_without_coordinates_has_null_distance(monkeypatch):
    _enable_judge(monkeypatch)
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["user"] = user
        return '{"same_incident": false, "reason": "no"}'

    monkeypatch.setattr(dedup, "chat", fake_chat)
    new, existing = _borderline_pair()
    find_duplicate(new, existing)

    payload = json.loads(seen["user"])
    assert payload["distance_km"] is None


def test_judge_payload_includes_report_timestamp(monkeypatch):
    _enable_judge(monkeypatch)
    seen = {}

    def fake_chat(system, user, **kwargs):
        seen["user"] = user
        return '{"same_incident": false, "reason": "no"}'

    monkeypatch.setattr(dedup, "chat", fake_chat)
    ref = _ref("j4", "Kalimati market", "Fire at a shop", typ=IncidentType.FIRE,
               lat=27.7198, lon=85.295,
               received_at=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    find_duplicate(_a("Kalimati bridge", "Fire in a shop", typ=IncidentType.FIRE), [ref],
                   latitude=27.705, longitude=85.295)

    payload = json.loads(seen["user"])
    assert payload["report_b"]["received_at"] == "2026-10-09T12:00:00+00:00"


def test_judge_prompt_is_read_once_and_cached(monkeypatch, tmp_path):
    _enable_judge(monkeypatch)
    prompt = "Judge prompt v1: answer same_incident as JSON."
    (tmp_path / "dedup_judge.txt").write_text(prompt, encoding="utf-8")
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_path)
    monkeypatch.setattr(dedup, "_JUDGE_SYSTEM_PROMPT", None)
    systems = []
    monkeypatch.setattr(
        dedup, "chat",
        lambda system, user, **kwargs: systems.append(system)
        or '{"same_incident": false, "reason": "no"}')

    new, existing = _borderline_pair()
    find_duplicate(new, existing)
    assert systems == [prompt]

    # The file is gone now: the cached copy must be reused, not re-read.
    (tmp_path / "dedup_judge.txt").unlink()
    find_duplicate(new, existing)
    assert systems == [prompt, prompt]
