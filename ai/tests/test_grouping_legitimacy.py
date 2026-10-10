import json

from disasterlens_ai import config, grouping, legitimacy


def test_grouping_uses_configured_stage_model_and_validates_json(monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake_chat(system, user, **kwargs):
        seen.update(system=system, user=user, kwargs=kwargs)
        return json.dumps({
            "incident_type": "flood",
            "location_text": "Balkhu",
            "summary": "Floodwater entered homes near Balkhu.",
        })

    monkeypatch.setattr(grouping, "chat", fake_chat)
    result = grouping.group_report("Floodwater entered homes near Balkhu.")

    assert result.incident_type.value == "flood"
    assert result.location_text == "Balkhu"
    assert seen["kwargs"]["model"] == config.GROUPING_MODEL
    assert "not decide urgency" in seen["system"]


def test_grouping_falls_back_to_report_text_when_model_summary_is_null(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", False)
    monkeypatch.setattr(
        grouping,
        "chat",
        lambda *_args, **_kwargs: (
            '{"incident_type":"flood","location_text":null,"summary":null}'
        ),
    )

    result = grouping.group_report("Flood water entered the street.")

    assert result.summary == "Flood water entered the street."


def test_grouping_falls_back_to_other_when_model_type_is_null(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", False)
    monkeypatch.setattr(
        grouping,
        "chat",
        lambda *_args, **_kwargs: (
            '{"incident_type":null,"location_text":null,"summary":"Report summary"}'
        ),
    )

    result = grouping.group_report("The report cannot be categorized confidently.")

    assert result.incident_type.value == "other"


def test_legitimacy_uses_separate_model_and_parsed_assessment(monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake_chat(system, user, **kwargs):
        seen.update(system=system, user=user, kwargs=kwargs)
        return '{"label":"prank","confidence":0.91,"reason":"The report explicitly says it is a joke."}'

    monkeypatch.setattr(legitimacy, "chat", fake_chat)
    result = legitimacy.assess_legitimacy("This is a joke, there was no emergency.")

    assert result.label == "prank"
    assert result.confidence == 0.91
    assert seen["kwargs"]["model"] == config.LEGIT_MODEL
    assert "never suppress a report" in seen["system"]


def test_stub_legitimacy_is_uncertain_and_never_claims_genuine(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", True)

    result = legitimacy.assess_legitimacy("A flood was reported.")

    assert result.label == "uncertain"
    assert result.confidence == 0
