"""A slow or dead provider must not crash the analyzer, hang forever, or lose
safety signals. No network: `chat` is replaced with a failing stand-in.
"""
import time

from openai import APITimeoutError

from disasterlens_ai import analyzer, config
from disasterlens_ai.schemas import ReportAnalysis

TRAPPED = "Flood near Balkhu bridge, 2 children stuck on roof, need rescue"
DROWNING = "बाढीले घर डुबायो, दुई जना फसेका छन्, उद्धार चाहिन्छ"


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
