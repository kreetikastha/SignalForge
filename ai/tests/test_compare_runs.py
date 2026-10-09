import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_runs.py"


def _load():
    spec = importlib.util.spec_from_file_location("compare_runs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


compare_runs = _load()


def _sample(**over):
    base = {"incident_type_ok": True, "severity_ok": True, "people_trapped_ok": True,
            "road_blocked_ok": True, "language_ok": True, "valid": True,
            "needs_missing": []}
    base.update(over)
    return base


def _report(samples, rate=50.0):
    return {
        "metrics": {"incident_type accuracy": {"correct": 1, "total": 2, "rate": rate}},
        "duplicate": {"precision": rate, "recall": rate, "missed": [], "false_positives": []},
        "safety": {
            "trapped_recall": {"correct": 1, "total": 2, "rate": rate},
            "trapped_false_alarms": {"count": 0, "sample_ids": []},
            "severity_under_triage": {"count": 0, "sample_ids": []},
            "severity_over_triage": {"count": 0, "sample_ids": []},
        },
        "failures": [],
        "samples": samples,
    }


def _write(tmp_path, name, report):
    path = tmp_path / name
    path.write_text(json.dumps(report), encoding="utf-8")
    return str(path)


def test_identical_runs_report_zero_deltas(tmp_path, capsys):
    report = _report({"s01": _sample(), "s02": _sample(severity_ok=False)})
    old = _write(tmp_path, "old.json", report)
    new = _write(tmp_path, "new.json", report)

    assert compare_runs.main([old, new]) == 0

    out = capsys.readouterr().out
    deltas = [line.split()[-1] for line in out.splitlines() if " -> " in line]
    assert deltas, "no metric rows were printed"
    assert set(deltas) <= {"+0.0", "+0"}, deltas
    assert "regressions (pass -> fail) (0): []" in out
    assert "fixes (fail -> pass) (0): []" in out


def test_regressions_and_fixes_are_listed_by_id(tmp_path, capsys):
    old = _write(tmp_path, "old.json",
                 _report({"s01": _sample(), "s02": _sample(incident_type_ok=False)}))
    new = _write(tmp_path, "new.json",
                 _report({"s01": _sample(incident_type_ok=False), "s02": _sample()}))

    assert compare_runs.main([old, new]) == 0

    out = capsys.readouterr().out
    assert "regressions (pass -> fail) (1): ['s01']" in out
    assert "fixes (fail -> pass) (1): ['s02']" in out


def test_missing_need_counts_as_failing():
    assert compare_runs._passed(_sample(needs_missing=["food"])) is False
    assert compare_runs._passed(_sample()) is True


def test_unreadable_reports_still_exit_zero(tmp_path, capsys):
    missing = str(tmp_path / "nope.json")
    assert compare_runs.main([missing, missing]) == 0
    assert "cannot read the two reports" in capsys.readouterr().out
    assert compare_runs.main([]) == 0
