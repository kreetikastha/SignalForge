"""Compare two eval.py JSON reports. Run from ai/:
    python scripts/compare_runs.py old.json new.json
Prints each metric old -> new with its delta, then the per-sample regressions and
fixes. A report, not a gate: the exit code is always 0."""
import json
import sys
from pathlib import Path

_CHECKS = ("incident_type_ok", "severity_ok", "people_trapped_ok", "road_blocked_ok",
           "language_ok", "valid")

_SAFETY_COUNTS = (
    ("trapped false alarms", "trapped_false_alarms"),
    ("severity under-triage", "severity_under_triage"),
    ("severity over-triage", "severity_over_triage"),
)


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.1f}%"


def _num(value: int | None) -> str:
    return "  n/a" if value is None else f"{value:5d}"


def _pct_row(name: str, old: float | None, new: float | None) -> str:
    delta = "   n/a" if old is None or new is None else f"{new - old:+6.1f}"
    return f"{name:<30} {_pct(old)} -> {_pct(new)}   {delta}"


def _count_row(name: str, old: int | None, new: int | None) -> str:
    delta = "   n/a" if old is None or new is None else f"{new - old:+6d}"
    return f"{name:<30} {_num(old)} -> {_num(new)}   {delta}"


def _passed(sample: dict) -> bool:
    """A sample passes only when every check passes and no expected need is missing."""
    return all(sample.get(k) for k in _CHECKS) and not sample.get("needs_missing")


def _status(report: dict) -> dict:
    return {sid: _passed(s) for sid, s in report.get("samples", {}).items()}


def _metric_names(old: dict, new: dict) -> list[str]:
    names = list(old.get("metrics", {}))
    names += [n for n in new.get("metrics", {}) if n not in names]
    return names


def _rows(old: dict, new: dict) -> list[str]:
    lines = []
    for name in _metric_names(old, new):
        lines.append(_pct_row(name,
                              old.get("metrics", {}).get(name, {}).get("rate"),
                              new.get("metrics", {}).get(name, {}).get("rate")))
    for name in ("precision", "recall"):
        lines.append(_pct_row(f"duplicate {name}", old.get("duplicate", {}).get(name),
                              new.get("duplicate", {}).get(name)))
    old_safety, new_safety = old.get("safety", {}), new.get("safety", {})
    lines.append(_pct_row("trapped recall",
                          old_safety.get("trapped_recall", {}).get("rate"),
                          new_safety.get("trapped_recall", {}).get("rate")))
    for name, key in _SAFETY_COUNTS:
        lines.append(_count_row(name, old_safety.get(key, {}).get("count"),
                                new_safety.get(key, {}).get("count")))
    return lines


def _flips(old: dict, new: dict) -> tuple[list[str], list[str]]:
    before, after = _status(old), _status(new)
    shared = sorted(set(before) & set(after))
    regressions = [sid for sid in shared if before[sid] and not after[sid]]
    fixes = [sid for sid in shared if not before[sid] and after[sid]]
    return regressions, fixes


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python scripts/compare_runs.py old.json new.json")
        return 0
    try:
        old = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        new = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read the two reports: {e}")
        return 0

    print(f"old: {args[0]}\nnew: {args[1]}\n")
    print(f"{'metric':<30} {'old':>7} -> {'new':>7}   delta")
    print("-" * 58)
    for line in _rows(old, new):
        print(line)

    regressions, fixes = _flips(old, new)
    print(f"\nregressions (pass -> fail) ({len(regressions)}): {regressions}")
    print(f"fixes (fail -> pass) ({len(fixes)}): {fixes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
