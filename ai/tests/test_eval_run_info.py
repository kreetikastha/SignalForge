"""Guard rails on the eval artifact: it must say which model produced it."""
import importlib.util
import json
import sys
from pathlib import Path

from disasterlens_ai import config

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval.py"

METRIC_NAMES = [
    "incident_type accuracy",
    "severity in range",
    "people_trapped accuracy",
    "road_blocked accuracy",
    "needs recall",
    "language accuracy",
    "valid output (conf > 0.1)",
]


def _load():
    spec = importlib.util.spec_from_file_location("eval_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eval_script = _load()


def test_run_info_reports_stub_and_live_modes(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", True)
    stub = eval_script._run_info()
    assert stub["mode"] == "stub"
    assert stub["provider"] == config.LLM_BASE_URL
    assert stub["generated_at"]

    monkeypatch.setattr(config, "STUB_MODE", False)
    assert eval_script._run_info()["mode"] == "live"


def test_offline_run_is_self_describing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STUB_MODE", True)
    out = tmp_path / "stub.json"
    monkeypatch.setattr(sys, "argv", ["eval.py", "--limit", "2", "--out", str(out)])

    assert eval_script.main() == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["run"]["mode"] == "stub"
    assert payload["run"]["provider"] == config.LLM_BASE_URL
    # pre-existing keys and metric names must survive untouched
    assert set(payload) >= {"metrics", "duplicate", "safety", "failures", "samples"}
    assert list(payload["metrics"]) == METRIC_NAMES
    assert list(payload["duplicate"]) == ["precision", "recall", "missed", "false_positives"]
    assert "WARNING: stub mode" in capsys.readouterr().out
