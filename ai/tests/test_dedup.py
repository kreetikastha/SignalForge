from disasterlens_ai import find_duplicate, score_urgency
from disasterlens_ai.dedup import _tokens
from disasterlens_ai.schemas import IncidentRef, ReportAnalysis


def _a(loc, summ, typ="flood", sev=3):
    return ReportAnalysis(incident_type=typ, location_text=loc, severity=sev, summary=summ, confidence=0.8)


def test_duplicate_found():
    existing = [IncidentRef(id="i1", incident_type="flood", location_text="Balkhu bridge",
                            summary="River flooding houses near Balkhu bridge")]
    m = find_duplicate(_a("Balkhu bridge", "Flooding houses near Balkhu bridge"), existing)
    assert m.is_duplicate and m.incident_id == "i1"


def test_different_type_not_duplicate():
    existing = [IncidentRef(id="i1", incident_type="fire", location_text="Balkhu bridge", summary="fire")]
    assert not find_duplicate(_a("Balkhu bridge", "flood"), existing).is_duplicate


def test_urgency_scales_and_caps():
    assert score_urgency(_a("x", "y", sev=5), duplicate_count=10) <= 100
    assert score_urgency(_a("x", "y", sev=5)) > score_urgency(_a("x", "y", sev=1))


def test_nepali_tokens_keep_vowel_signs():
    assert _tokens("बनेपामा पहिरो") == {"बनेपामा", "पहिरो"}


def test_nepali_danda_not_glued_to_word():
    assert _tokens("बाटो बन्द छ।") == {"बाटो", "बन्द", "छ"}


def test_nepali_duplicate_landslide_found():
    existing = [IncidentRef(id="n1", incident_type="landslide", location_text="बनेपा",
                            summary="बनेपामा पहिरोले बाटो रोकियो")]
    m = find_duplicate(_a("बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ="landslide"), existing)
    assert m.is_duplicate and m.incident_id == "n1"


def test_nepali_different_locations_not_duplicate():
    existing = [IncidentRef(id="n2", incident_type="landslide", location_text="ललितपुर",
                            summary="ललितपुरमा पहिरोले बाटो रोकियो")]
    m = find_duplicate(_a("बनेपा", "बनेपामा ठूलो पहिरोले बाटो रोकियो", typ="landslide"), existing)
    assert not m.is_duplicate
