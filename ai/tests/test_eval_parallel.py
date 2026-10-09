"""A live eval is dominated by provider latency, so `--workers` overlaps those waits.
That must not change a single number. No network here: analyze_report is stand-in'd.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

from disasterlens_ai import config
from disasterlens_ai.schemas import ReportAnalysis

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval.py"


def _load():
    spec = importlib.util.spec_from_file_location("eval_script_parallel", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eval_script = _load()


def _samples(n: int) -> list[dict]:
    return [{"id": f"s{i:02d}", "text": f"report {i}"} for i in range(1, n + 1)]


def test_parallel_analysis_preserves_sample_order(monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", True)  # never touch the real provider
    ids = list(eval_script._analyze_all(_samples(5), workers=4))
    assert ids == ["s01", "s02", "s03", "s04", "s05"]


def test_parallel_analysis_is_faster_than_serial(monkeypatch):
    def slow_analyze(_text, image=None):
        time.sleep(0.25)
        return ReportAnalysis(incident_type="flood", severity=3, summary="x", confidence=0.8)

    monkeypatch.setattr(eval_script, "analyze_report", slow_analyze)
    samples = _samples(4)

    t0 = time.perf_counter()
    eval_script._analyze_all(samples, workers=1)
    serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    eval_script._analyze_all(samples, workers=4)
    parallel = time.perf_counter() - t0

    assert parallel < serial / 2, f"serial={serial:.2f}s parallel={parallel:.2f}s"


def test_report_metrics_do_not_depend_on_worker_count(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STUB_MODE", True)
    payloads = {}
    for workers in (1, 4):
        out = tmp_path / f"stub_{workers}.json"
        monkeypatch.setattr(
            sys, "argv",
            ["eval.py", "--limit", "6", "--workers", str(workers), "--out", str(out)])

        assert eval_script.main() == 0

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["run"]["workers"] == workers
        del payload["run"]["generated_at"], payload["run"]["workers"]
        payloads[workers] = payload

    assert payloads[1] == payloads[4]
