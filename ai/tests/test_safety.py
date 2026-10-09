import pytest
from disasterlens_ai import adapter, analyze_report, config
from disasterlens_ai.analyzer import _normalize
from disasterlens_ai.safety import apply_safety_net
from disasterlens_ai.schemas import IncidentType, ReportAnalysis


def _analysis(**kwargs) -> ReportAnalysis:
    defaults = {
        "incident_type": IncidentType.FLOOD,
        "severity": 3,
        "summary": "Sample summary",
        "confidence": 0.8,
        "people_trapped": "unknown",
        "road_blocked": "unknown",
        "flags": [],
    }
    defaults.update(kwargs)
    return ReportAnalysis(**defaults)


def test_normalize_devanagari_digits():
    res = _normalize("५ जना घाइते")
    assert res == "5 जना घाइते"


def test_normalize_truncation():
    long_text = "a" * 5000
    res = _normalize(long_text)
    assert len(res) == 2000


def test_normalize_nfc_and_control_chars_and_spaces():
    text = "word1\x00   word2\t\n  word3"
    res = _normalize(text)
    assert res == "word1 word2\t\n word3"


def test_rule_b_trapped_terms_english():
    a = _analysis(people_trapped="unknown", severity=4)
    res = apply_safety_net("People are trapped inside the building", a)
    assert res.people_trapped == "yes"
    assert "trapped_keyword_override" in res.flags


def test_rule_b_trapped_terms_devanagari():
    a = _analysis(people_trapped="unknown", severity=4)
    res = apply_safety_net("पहिरोमा दुई जना पुरिएका छन्", a)
    assert res.people_trapped == "yes"
    assert "trapped_keyword_override" in res.flags


def test_rule_b_trapped_terms_romanized_nepali():
    a = _analysis(people_trapped="unknown", severity=3)
    res = apply_safety_net("Ghar bhatkiyo, 2 jana phaseka chan", a)
    assert res.people_trapped == "yes"
    assert res.severity == 4
    assert "trapped_keyword_override" in res.flags


def test_rule_b_trapped_terms_romanized_variants():
    for text, term in [
        ("Ghar bhattyo, faseko cha", "faseko"),
        ("2 jana adkiyeko cha", "adkiyeko"),
        ("Pahiro le puriyeka chan", "puriyeka"),
        ("Bhitta le chyapiyeko cha", "chyapiyeko"),
        ("2 jana under the debris chan", "under the debris"),
        ("Gadi stuck inside cha", "stuck inside"),
    ]:
        a = _analysis(people_trapped="unknown", severity=3)
        res = apply_safety_net(text, a)
        assert res.people_trapped == "yes", term
        assert res.severity == 4, term
        assert "trapped_keyword_override" in res.flags, term


def test_rule_b_word_boundaries_reject_substring_hits():
    # "untrapped"/"unburied"/"unstuck" contain trapped terms as substrings but
    # do not denote trapped people, so \b matching must keep them out.
    a = _analysis(people_trapped="unknown", severity=3)
    res = apply_safety_net("The unburied waste was cleared; nobody was untrapped or unstuck", a)
    assert res.people_trapped == "unknown"
    assert res.severity == 3
    assert "trapped_keyword_override" not in res.flags
    assert "severity_floor_trapped" not in res.flags


def test_rule_b_still_matches_next_to_punctuation():
    a = _analysis(people_trapped="unknown", severity=3)
    res = apply_safety_net("Ghar bhatkiyo, 2 jana phaseka!", a)
    assert res.people_trapped == "yes"
    assert "trapped_keyword_override" in res.flags


def test_rule_c_severity_floor_english():
    a = _analysis(people_trapped="unknown", severity=2)
    res = apply_safety_net("Two people are stuck in the elevator", a)
    assert res.people_trapped == "yes"
    assert res.severity == 4
    assert "severity_floor_trapped" in res.flags


def test_rule_c_severity_floor_devanagari():
    a = _analysis(people_trapped="unknown", severity=1)
    res = apply_safety_net("भग्नावशेषमुनि मानिसहरू च्यापिएका छन्", a)
    assert res.people_trapped == "yes"
    assert res.severity == 4
    assert "severity_floor_trapped" in res.flags


def test_rule_d_low_confidence_english():
    a = _analysis(confidence=0.3)
    res = apply_safety_net("Some incident happened here", a)
    assert "low_confidence" in res.flags


def test_rule_d_low_confidence_devanagari():
    a = _analysis(confidence=0.4)
    res = apply_safety_net("कतै केही भयो कि", a)
    assert "low_confidence" in res.flags


def test_negation_guard_blocks_b_and_c_english():
    a = _analysis(people_trapped="no", severity=2)
    text = "A wall fell down but no one is trapped under the rubble"
    res = apply_safety_net(text, a)
    assert res.people_trapped == "no"
    assert res.severity == 2
    assert "trapped_keyword_override" not in res.flags
    assert "severity_floor_trapped" not in res.flags


def test_negation_guard_blocks_b_and_c_devanagari():
    a = _analysis(people_trapped="no", severity=2)
    text = "घर भत्किएको छ तर कोही फसेको छैन"
    res = apply_safety_net(text, a)
    assert res.people_trapped == "no"
    assert res.severity == 2
    assert "trapped_keyword_override" not in res.flags
    assert "severity_floor_trapped" not in res.flags


def test_negation_guard_romanized_nepali():
    a = _analysis(people_trapped="no", severity=2)
    res = apply_safety_net("Ghar bhatkiyo tara koi faseko chaina", a)
    assert res.people_trapped == "no"
    assert res.severity == 2
    assert "trapped_keyword_override" not in res.flags
    assert "severity_floor_trapped" not in res.flags


@pytest.mark.parametrize("negation", [
    "kohe faseko chaina",
    "koohe faseko xaina",
    "kasailai kehi bhayeko chaina",
    "no casualties",
    "faseko chaina",
])
def test_negation_guard_romanized_variants(negation):
    # A trapped term appears elsewhere in the text, but the negation must win.
    a = _analysis(people_trapped="unknown", severity=2)
    res = apply_safety_net(f"2 jana phaseka chan, tara {negation}", a)
    assert res.people_trapped != "yes"
    assert "trapped_keyword_override" not in res.flags


def test_severity_5_stays_5():
    a = _analysis(people_trapped="yes", severity=5)
    res = apply_safety_net("people trapped in the building", a)
    assert res.severity == 5
    assert "severity_floor_trapped" not in res.flags


def test_model_result_trapped_yes_severity_2_becomes_4():
    a = _analysis(people_trapped="yes", severity=2)
    res = apply_safety_net("Heavy water flooding the residential streets", a)
    assert res.people_trapped == "yes"
    assert res.severity == 4
    assert "severity_floor_trapped" in res.flags


def test_original_object_not_mutated():
    a = _analysis(people_trapped="unknown", severity=2, flags=[])
    res = apply_safety_net("people trapped", a)
    assert a.people_trapped == "unknown"
    assert a.severity == 2
    assert a.flags == []
    assert res is not a
    assert res.people_trapped == "yes"
    assert res.severity == 4


def test_stub_mode_output_has_empty_flags(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", True)
    res = analyze_report("People trapped in house under rubble")
    assert res.flags == []


def test_adapter_output_contains_flags_and_needs_review():
    a = _analysis(confidence=0.8, flags=["trapped_keyword_override"])
    d = adapter.to_backend_dict(a)
    assert "flags" in d and d["flags"] == ["trapped_keyword_override"]
    assert "needs_review" in d and d["needs_review"] is True
    assert "safety rule applied: trapped_keyword_override" in d["priority_reason"]

    a_floor = _analysis(confidence=0.8, flags=["severity_floor_trapped"])
    d_floor = adapter.to_backend_dict(a_floor)
    assert "safety rule applied: severity_floor_trapped" in d_floor["priority_reason"]

    a_low = _analysis(confidence=0.4, flags=[])
    d_low = adapter.to_backend_dict(a_low)
    assert d_low["flags"] == []
    assert d_low["needs_review"] is True
    assert "safety rule applied" not in d_low["priority_reason"]

    a_high = _analysis(confidence=0.9, flags=[])
    d_high = adapter.to_backend_dict(a_high)
    assert d_high["flags"] == []
    assert d_high["needs_review"] is False
    assert "safety rule applied" not in d_high["priority_reason"]


def test_analyzer_successful_model_call_applies_safety_net(monkeypatch):
    from disasterlens_ai import analyzer

    monkeypatch.setattr(config, "STUB_MODE", False)
    canned = (
        '{"incident_type": "flood", "severity": 2, "people_trapped": "unknown", '
        '"summary": "Flood", "confidence": 0.8}'
    )
    monkeypatch.setattr(analyzer, "chat", lambda *args, **kwargs: canned)

    res = analyzer.analyze_report("People are trapped inside the basement")
    assert res.people_trapped == "yes"
    assert res.severity == 4
    assert "trapped_keyword_override" in res.flags
    assert "severity_floor_trapped" in res.flags
