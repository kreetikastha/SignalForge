"""A slow or dead provider must not crash the analyzer, hang forever, or lose
safety signals. No network: `chat` is replaced with a failing stand-in.
"""
import time

import pytest
from openai import APITimeoutError

from disasterlens_ai import analyzer, config
from disasterlens_ai.schemas import ReportAnalysis

TRAPPED = "Flood near Balkhu bridge, 2 children stuck on roof, need rescue"
DROWNING = "बाढीले घर डुबायो, दुई जना फसेका छन्, उद्धार चाहिन्छ"

# Valid model output for a benign report (no safety keywords -> no overrides).
GOOD_JSON = ('{"incident_type": "flood", "location_text": "Kalanki", "severity": 3,'
             ' "summary": "river overflow reported", "confidence": 0.9}')
BENIGN = "River is swelling at Kalanki"
PNG = b"\x89PNG\r\n\x1a\nrest of the bytes"


def _timeout() -> APITimeoutError:
    return APITimeoutError.__new__(APITimeoutError)


def _dead_provider(monkeypatch, exc=None, sleep=0.0):
    """Replace the model call with one that always fails; return the call log."""
    calls = []

    def fail(*_args, **kwargs):
        calls.append(kwargs.get("timeout"))
        if sleep:
            time.sleep(sleep)
        raise exc or _timeout()

    monkeypatch.setattr(config, "STUB_MODE", False)
    monkeypatch.setattr(analyzer, "chat", fail)
    return calls


def test_provider_timeout_returns_a_flagged_fallback(monkeypatch):
    calls = _dead_provider(monkeypatch)

    result = analyzer.analyze_report(TRAPPED)

    assert isinstance(result, ReportAnalysis)
    assert result.confidence <= 0.1
    assert result.summary.startswith("[analysis failed:")
    assert len(calls) == config.MAX_RETRIES + 1
    assert all(t <= config.REQUEST_TIMEOUT for t in calls)


def test_trapped_signal_survives_a_dead_provider(monkeypatch):
    _dead_provider(monkeypatch)

    result = analyzer.analyze_report(TRAPPED)
    assert result.people_trapped == "yes"
    assert result.severity >= 4
    assert "trapped_keyword_override" in result.flags
    assert "low_confidence" in result.flags


def test_connection_error_also_falls_back(monkeypatch):
    _dead_provider(monkeypatch, exc=ConnectionResetError("socket closed"))

    result = analyzer.analyze_report(DROWNING)

    assert result.people_trapped == "yes"  # Devanagari trapped terms still caught
    assert result.confidence <= 0.1


def test_total_budget_stops_further_attempts(monkeypatch):
    calls = _dead_provider(monkeypatch, sleep=0.05)
    monkeypatch.setattr(config, "TOTAL_TIMEOUT", 0.05)

    analyzer.analyze_report(TRAPPED)

    assert len(calls) == 1, f"budget should stop after the first attempt, got {len(calls)}"


def test_bad_json_still_retries_then_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def garbage(*_args, **_kwargs):
        calls.append(1)
        return "definitely not json"

    monkeypatch.setattr(analyzer, "chat", garbage)

    result = analyzer.analyze_report(TRAPPED)

    assert len(calls) == config.MAX_RETRIES + 1
    assert result.confidence <= 0.1


# ---------------------------------------------------------------- JSON parsing

def test_extract_json_survives_fences_prose_and_trailing_commas():
    noisy = ('Sure, here is the analysis:\n```json\n'
             '{"incident_type": "flood", "severity": 3, "needs": ["rescue",],}\n'
             '```\nHope that helps!')
    assert analyzer._extract_json(noisy) == {
        "incident_type": "flood", "severity": 3, "needs": ["rescue"]}


def test_extract_json_strips_control_chars_but_keeps_tab_newline_return():
    assert analyzer._extract_json('{\x00"severity": 2,\x1f\t"summary": "ok"}') == {
        "severity": 2, "summary": "ok"}
    assert analyzer._extract_json('{"summary": "a\\nb"}') == {"summary": "a\nb"}


def test_extract_json_without_object_raises():
    with pytest.raises(ValueError, match="no JSON object in model output"):
        analyzer._extract_json("the model apologised instead of answering")


def test_extract_json_broken_body_raises_value_error():
    with pytest.raises(ValueError):
        analyzer._extract_json('{"severity": 3,,}')


# ------------------------------------------------------------------- JSON mode

def test_every_attempt_requests_json_mode(monkeypatch):
    modes = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake(*_args, **kwargs):
        modes.append(kwargs.get("json_mode"))
        return GOOD_JSON

    monkeypatch.setattr(analyzer, "chat", fake)

    result = analyzer.analyze_report(BENIGN)

    assert modes == [True]
    assert result.confidence == 0.9


# ------------------------------------------------------- multimodal fallback

def test_vision_failure_retries_text_only_in_the_same_attempt(monkeypatch):
    seen = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake(*_args, image=None, **_kwargs):
        seen.append(image)
        if image is not None:
            raise _timeout()
        return GOOD_JSON

    monkeypatch.setattr(analyzer, "chat", fake)

    result = analyzer.analyze_report(BENIGN, image=PNG)

    assert len(seen) == 2, "vision error must be retried text-only, not burn a retry slot"
    assert seen[0] is PNG and seen[1] is None
    assert result.confidence == 0.9  # answered on the fallback, never fell back to the stub
    assert not result.summary.startswith("[analysis failed:")


def test_truncated_vision_response_also_degrades_to_text(monkeypatch):
    seen = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake(*_args, image=None, **_kwargs):
        seen.append(image)
        if image is not None:
            raise ValueError("response truncated")
        return GOOD_JSON

    monkeypatch.setattr(analyzer, "chat", fake)

    result = analyzer.analyze_report(BENIGN, image=PNG)

    assert seen == [PNG, None]
    assert result.confidence == 0.9


def test_failing_vision_and_text_still_uses_one_retry_slot_per_attempt(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fail(*_args, image=None, **_kwargs):
        calls.append(image)
        raise _timeout()

    monkeypatch.setattr(analyzer, "chat", fail)

    result = analyzer.analyze_report(TRAPPED, image=PNG)

    assert len(calls) == 2 * (config.MAX_RETRIES + 1)
    assert result.confidence <= 0.1
    assert result.summary.startswith("[analysis failed:")
    assert result.people_trapped == "yes"  # safety signals survive the dead vision path


def test_successful_vision_call_is_not_retried_text_only(monkeypatch):
    seen = []
    monkeypatch.setattr(config, "STUB_MODE", False)

    def fake(*_args, image=None, **_kwargs):
        seen.append(image)
        return GOOD_JSON

    monkeypatch.setattr(analyzer, "chat", fake)

    analyzer.analyze_report(BENIGN, image=PNG)

    assert seen == [PNG]
