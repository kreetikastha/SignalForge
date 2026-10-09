"""Evaluation report over data/sample_reports.json. Run from ai/:
    DISASTERLENS_STUB=1 python scripts/eval.py [--limit N] [--out results.json]
A report, not a gate: the exit code is always 0."""
import argparse
import json
from pathlib import Path
from disasterlens_ai import analyze_report, find_duplicate
from disasterlens_ai.schemas import IncidentRef

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _rate(part: int, whole: int) -> float | None:
    return 100.0 * part / whole if whole else None


def _fmt(rate: float | None) -> str:
    return "   n/a" if rate is None else f"{rate:5.1f}%"


def _load(limit: int | None):
    samples = json.loads((DATA_DIR / "sample_reports.json").read_text(encoding="utf-8"))
    expected = json.loads((DATA_DIR / "expected_outputs.json").read_text(encoding="utf-8"))
    if limit is not None:
        samples = samples[:max(limit, 0)]
    return samples, expected


def _sample_results(samples: list[dict], expected: dict, analyses: dict) -> dict:
    results = {}
    for s in samples:
        sid, exp, got = s["id"], expected[s["id"]], analyses[s["id"]]
        results[sid] = {
            "expected": exp,
            "got": {"incident_type": got.incident_type.value, "severity": got.severity,
                    "people_trapped": got.people_trapped, "road_blocked": got.road_blocked,
                    "needs": list(got.needs), "language": got.language,
                    "confidence": got.confidence},
            "incident_type_ok": got.incident_type.value == exp["incident_type"],
            "severity_ok": exp["severity_min"] <= got.severity <= exp["severity_max"],
            "people_trapped_ok": got.people_trapped == exp["people_trapped"],
            "road_blocked_ok": got.road_blocked == exp["road_blocked"],
            "needs_missing": sorted(set(exp["needs_include"]) - set(got.needs)),
            "language_ok": got.language == exp["language"],
            "valid": got.confidence > 0.1,
        }
    return results


def _summary(results: dict) -> dict:
    n = len(results)

    def ok(key: str) -> int:
        return sum(1 for r in results.values() if r[key])

    want = sum(len(r["expected"]["needs_include"]) for r in results.values())
    hit = sum(len(r["expected"]["needs_include"]) - len(r["needs_missing"])
              for r in results.values())
    return {
        "incident_type accuracy": (ok("incident_type_ok"), n),
        "severity in range": (ok("severity_ok"), n),
        "people_trapped accuracy": (ok("people_trapped_ok"), n),
        "road_blocked accuracy": (ok("road_blocked_ok"), n),
        "needs recall": (hit, want),
        "language accuracy": (ok("language_ok"), n),
        "valid output (conf > 0.1)": (ok("valid"), n),
    }


def _duplicates(samples: list[dict], expected: dict, analyses: dict) -> dict:
    ids = [s["id"] for s in samples]
    refs = {sid: IncidentRef(id=sid, incident_type=analyses[sid].incident_type,
                             location_text=analyses[sid].location_text,
                             summary=analyses[sid].summary) for sid in ids}
    grouped = {sid for sid in ids if expected[sid]["dup_group"]}
    truth, evaluated = set(), set()
    for a in ids:
        for b in ids:
            if a == b:
                continue
            if expected[a]["dup_group"] and expected[a]["dup_group"] == expected[b]["dup_group"]:
                truth.add((a, b))          # both directions of each in-group pair
            if a in grouped or b in grouped:
                evaluated.add((a, b))
    predicted = {p for p in evaluated
                 if find_duplicate(analyses[p[0]], [refs[p[1]]]).is_duplicate}
    tp = predicted & truth
    return {"precision": (_rate(len(tp), len(predicted)), len(tp), len(predicted)),
            "recall": (_rate(len(tp), len(truth)), len(tp), len(truth)),
            "missed": sorted(truth - predicted),
            "false_positives": sorted(predicted - truth)}


def _safety(results: dict) -> dict:
    """Safety-critical counts plus the sample ids behind each of them.

    ``trapped`` is the set of samples where a rescue should have been flagged;
    missing one delays a rescue, so that recall is the headline number.
    """
    ids = sorted(results)
    return {
        "trapped": [sid for sid in ids
                    if results[sid]["expected"]["people_trapped"] == "yes"],
        "trapped_caught": [sid for sid in ids
                           if results[sid]["expected"]["people_trapped"] == "yes"
                           and results[sid]["got"]["people_trapped"] == "yes"],
        "trapped_false_alarms": [sid for sid in ids
                                 if results[sid]["expected"]["people_trapped"] != "yes"
                                 and results[sid]["got"]["people_trapped"] == "yes"],
        "severity_under_triage": [sid for sid in ids
                                   if results[sid]["got"]["severity"]
                                   < results[sid]["expected"]["severity_min"]],
        "severity_over_triage": [sid for sid in ids
                                  if results[sid]["got"]["severity"]
                                  > results[sid]["expected"]["severity_max"]],
    }


def _failures(results: dict) -> list[str]:
    lines = []
    for sid in sorted(results):
        r, exp, got = results[sid], results[sid]["expected"], results[sid]["got"]
        if not r["incident_type_ok"]:
            lines.append(f"  [incident_type] {sid}: expected {exp['incident_type']}, got {got['incident_type']}")
        if not r["severity_ok"]:
            lines.append(f"  [severity] {sid}: expected {exp['severity_min']}-{exp['severity_max']}, got {got['severity']}")
        if not r["people_trapped_ok"]:
            lines.append(f"  [people_trapped] {sid}: expected {exp['people_trapped']}, got {got['people_trapped']}")
        if not r["road_blocked_ok"]:
            lines.append(f"  [road_blocked] {sid}: expected {exp['road_blocked']}, got {got['road_blocked']}")
        if r["needs_missing"]:
            lines.append(f"  [needs] {sid}: missing {r['needs_missing']}, expected {exp['needs_include']}, got {got['needs']}")
        if not r["language_ok"]:
            lines.append(f"  [language] {sid}: expected {exp['language']}, got {got['language']}")
        if not r["valid"]:
            lines.append(f"  [valid_output] {sid}: confidence {got['confidence']} <= 0.1")
    return lines


def main() -> int:
    p = argparse.ArgumentParser(description="Print an evaluation report for the sample set.")
    p.add_argument("--limit", type=int, default=None, help="evaluate only the first N samples")
    p.add_argument("--out", default=None, help="also write full results to this JSON file")
    args = p.parse_args()

    samples, expected = _load(args.limit)
    analyses = {s["id"]: analyze_report(s["text"]) for s in samples}
    results = _sample_results(samples, expected, analyses)
    metrics = _summary(results)
    dup = _duplicates(samples, expected, analyses)
    safety = _safety(results)
    trapped_recall = _rate(len(safety["trapped_caught"]), len(safety["trapped"]))

    print(f"samples evaluated: {len(samples)}\n")
    print(f"{'metric':<28} {'rate':>7}  detail")
    print("-" * 52)
    for name, (part, whole) in metrics.items():
        print(f"{name:<28} {_fmt(_rate(part, whole)):>7}  {part}/{whole}")
    for name in ("precision", "recall"):
        rate, part, whole = dup[name]
        print(f"{'duplicate ' + name:<28} {_fmt(rate):>7}  {part}/{whole}")

    print("\nsafety metrics:")
    print(f"{'trapped recall':<28} {_fmt(trapped_recall):>7}  "
          f"{len(safety['trapped_caught'])}/{len(safety['trapped'])}")
    for name, key in (("trapped false alarms", "trapped_false_alarms"),
                      ("severity under-triage", "severity_under_triage"),
                      ("severity over-triage", "severity_over_triage")):
        print(f"{name:<28} {len(safety[key]):>7}  {safety[key]}")

    failures = _failures(results)
    print(f"\nfailures ({len(failures)}):")
    for line in failures:
        print(line)
    if dup["missed"]:
        print(f"  [duplicate missed] {dup['missed']}")
    if dup["false_positives"]:
        print(f"  [duplicate false positive] {dup['false_positives']}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"metrics": {k: {"correct": a, "total": b, "rate": _rate(a, b)}
                         for k, (a, b) in metrics.items()},
             "duplicate": {"precision": dup["precision"][0], "recall": dup["recall"][0],
                           "missed": dup["missed"], "false_positives": dup["false_positives"]},
             "safety": {
                 "trapped_recall": {"correct": len(safety["trapped_caught"]),
                                    "total": len(safety["trapped"]),
                                    "rate": trapped_recall},
                 "trapped_false_alarms": {"count": len(safety["trapped_false_alarms"]),
                                          "sample_ids": safety["trapped_false_alarms"]},
                 "severity_under_triage": {"count": len(safety["severity_under_triage"]),
                                           "sample_ids": safety["severity_under_triage"]},
                 "severity_over_triage": {"count": len(safety["severity_over_triage"]),
                                          "sample_ids": safety["severity_over_triage"]},
             },
             "failures": failures, "samples": results},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
