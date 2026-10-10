"""Evaluation report over data/sample_reports.json. Run from ai/:
    DISASTERLENS_STUB=1 python scripts/eval.py [--limit N] [--out results.json]
A report, not a gate: the exit code is always 0."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from disasterlens_ai import (
    analyze_report,
    assess_legitimacy,
    config,
    find_duplicate,
    group_report,
)
from disasterlens_ai.schemas import GroupingAnalysis, IncidentRef, ReportAnalysis

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _run_info(workers: int = 1) -> dict:
    """Provenance for a run, so a stub result can never pass as a live baseline."""
    return {
        "mode": "stub" if config.STUB_MODE else "live",
        "model": config.LLM_MODEL or None,
        "grouping_model": config.GROUPING_MODEL or config.LLM_MODEL or None,
        "legitimacy_model": config.LEGIT_MODEL or config.LLM_MODEL or None,
        "provider": config.LLM_BASE_URL,
        "judge_enabled": config.JUDGE_ENABLED,
        "workers": workers,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _analyze_all(samples: list[dict], workers: int) -> dict:
    """Analyze every sample. One model call per sample, so a live run is rate-limited
    by provider latency, not by CPU: `workers` overlaps those waits. Result order
    follows `samples` either way."""
    def one(sample: dict) -> tuple[str, ReportAnalysis]:
        return sample["id"], analyze_report(sample["text"])

    if workers <= 1:
        pairs = [one(sample) for sample in samples]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pairs = list(pool.map(one, samples))
    return dict(pairs)


def _group_all(samples: list[dict], workers: int) -> tuple[dict, dict]:
    def one(sample: dict) -> tuple[str, GroupingAnalysis | None, str | None]:
        try:
            return sample["id"], group_report(sample["text"]), None
        except Exception as exc:
            return sample["id"], None, f"{type(exc).__name__}: {exc}"

    if workers <= 1:
        results = [one(sample) for sample in samples]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, samples))
    groupings = {sid: result for sid, result, _error in results}
    errors = {sid: error for sid, _result, error in results if error}
    return groupings, errors


def _legitimacy_all(samples: list[dict], expected: dict, workers: int) -> dict:
    labeled = [sample for sample in samples if expected[sample["id"]].get("legitimacy")]

    def one(sample: dict) -> tuple[str, dict]:
        try:
            assessment = assess_legitimacy(sample["text"])
            label = (
                assessment.label
                if assessment.confidence >= config.LEGIT_CONFIDENCE_THRESHOLD
                else "uncertain"
            )
            return sample["id"], {
                "label": label,
                "confidence": assessment.confidence,
                "reason": assessment.reason,
                "error": None,
            }
        except Exception as exc:
            return sample["id"], {
                "label": "unassessed",
                "confidence": None,
                "reason": "Legitimacy assessment failed.",
                "error": f"{type(exc).__name__}: {exc}",
            }

    if workers <= 1:
        pairs = [one(sample) for sample in labeled]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pairs = list(pool.map(one, labeled))
    return dict(pairs)


def _repeat_reporter_flags(samples: list[dict]) -> dict[str, bool]:
    seen: set[str] = set()
    flags: dict[str, bool] = {}
    for sample in samples:
        reporter_id = str(sample.get("reporter_id") or "").strip()
        flags[sample["id"]] = bool(reporter_id and reporter_id in seen)
        if reporter_id:
            seen.add(reporter_id)
    return flags


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


def _sample_results(
    samples: list[dict],
    expected: dict,
    analyses: dict,
    groupings: dict | None = None,
    legitimacy: dict | None = None,
) -> dict:
    results = {}
    for s in samples:
        sid, exp, got = s["id"], expected[s["id"]], analyses[s["id"]]
        grouping = (groupings or {}).get(sid)
        legitimacy_result = (legitimacy or {}).get(sid)
        results[sid] = {
            "expected": exp,
            "got": {"incident_type": got.incident_type.value, "severity": got.severity,
                    "people_trapped": got.people_trapped, "road_blocked": got.road_blocked,
                    "needs": list(got.needs), "language": got.language,
                    "confidence": got.confidence},
            "grouping": {
                "incident_type": grouping.incident_type.value,
                "location_text": grouping.location_text,
                "summary": grouping.summary,
            } if grouping is not None else None,
            "legitimacy": legitimacy_result,
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


def _duplicates(
    samples: list[dict],
    expected: dict,
    analyses: dict,
    groupings: dict | None = None,
) -> dict:
    """Pairwise duplicate precision/recall, scored two ways.

    * with coordinates (headline): what the backend does. The NEW report's
      lat/lon go in the keyword arguments; the existing incident's lat/lon ride
      on its IncidentRef, so find_duplicate measures a real distance.
    * without coordinates: text/location overlap only.
    """
    ids = [s["id"] for s in samples]
    coords = {s["id"]: (s.get("lat"), s.get("lon")) for s in samples}
    grouping_data = groupings or analyses

    def ref(sid: str, with_coords: bool) -> IncidentRef:
        lat, lon = coords[sid] if with_coords else (None, None)
        return IncidentRef(id=sid, incident_type=grouping_data[sid].incident_type,
                           location_text=grouping_data[sid].location_text,
                           summary=grouping_data[sid].summary,
                           latitude=lat, longitude=lon)

    refs = {True: {sid: ref(sid, True) for sid in ids},
            False: {sid: ref(sid, False) for sid in ids}}
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

    def predict(with_coords: bool) -> set:
        out = set()
        for a, b in evaluated:
            kwargs = {}
            if with_coords:  # `a` is the new report, `b` the existing incident
                kwargs = {"latitude": coords[a][0], "longitude": coords[a][1]}
            if find_duplicate(
                grouping_data[a], [refs[with_coords][b]], **kwargs
            ).is_duplicate:
                out.add((a, b))
        return out

    def score(predicted: set) -> tuple:
        tp = predicted & truth
        return ((_rate(len(tp), len(predicted)), len(tp), len(predicted)),
                (_rate(len(tp), len(truth)), len(tp), len(truth)))

    with_c, without_c = predict(True), predict(False)
    prec_c, rec_c = score(with_c)
    prec_n, rec_n = score(without_c)
    return {"precision": prec_c, "recall": rec_c,
            "precision_no_coords": prec_n, "recall_no_coords": rec_n,
            "missed": sorted(truth - with_c),
            "false_positives": sorted(with_c - truth),
            "missed_no_coords": sorted(truth - without_c),
            "false_positives_no_coords": sorted(without_c - truth)}


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


def _trust_metrics(samples: list[dict], expected: dict, results: dict) -> dict:
    reporter_flags = _repeat_reporter_flags(samples)
    labeled_ids = [
        sample["id"]
        for sample in samples
        if expected[sample["id"]].get("legitimacy")
    ]
    repeat_ids = [
        sample["id"]
        for sample in samples
        if "repeat_reporter" in expected[sample["id"]]
    ]
    legitimacy_correct = [
        sid for sid in labeled_ids
        if results[sid]["legitimacy"] is not None
        and results[sid]["legitimacy"]["label"] == expected[sid]["legitimacy"]
    ]
    repeat_correct = [
        sid for sid in repeat_ids
        if reporter_flags[sid] == expected[sid]["repeat_reporter"]
    ]
    return {
        "legitimacy": {
            "correct": len(legitimacy_correct),
            "total": len(labeled_ids),
            "accuracy": _rate(len(legitimacy_correct), len(labeled_ids)),
            "incorrect_ids": sorted(set(labeled_ids) - set(legitimacy_correct)),
        },
        "repeat_reporter": {
            "correct": len(repeat_correct),
            "total": len(repeat_ids),
            "accuracy": _rate(len(repeat_correct), len(repeat_ids)),
            "incorrect_ids": sorted(set(repeat_ids) - set(repeat_correct)),
        },
        "predicted_repeat_reporter": reporter_flags,
    }


def _grouping_type_summary(samples: list[dict], expected: dict, results: dict) -> dict:
    compared = [
        sample["id"] for sample in samples
        if results[sample["id"]]["grouping"] is not None
    ]
    correct = [
        sid for sid in compared
        if results[sid]["grouping"]["incident_type"]
        == expected[sid]["incident_type"]
    ]
    return {
        "correct": len(correct),
        "total": len(compared),
        "accuracy": _rate(len(correct), len(compared)),
        "incorrect_ids": sorted(set(compared) - set(correct)),
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
    p.add_argument("--workers", type=int, default=4,
                   help="parallel model calls (1 = serial; use 1 for a rate-limited provider)")
    args = p.parse_args()

    samples, expected = _load(args.limit)
    analyses = _analyze_all(samples, args.workers)
    groupings, grouping_errors = _group_all(samples, args.workers)
    legitimacy = _legitimacy_all(samples, expected, args.workers)
    results = _sample_results(
        samples, expected, analyses, groupings=groupings, legitimacy=legitimacy
    )
    metrics = _summary(results)
    grouping_metrics = _grouping_type_summary(samples, expected, results)
    trust = _trust_metrics(samples, expected, results)
    effective_groupings = {
        sid: grouping or analyses[sid] for sid, grouping in groupings.items()
    }
    dup = _duplicates(samples, expected, analyses, groupings=effective_groupings)
    safety = _safety(results)
    trapped_recall = _rate(len(safety["trapped_caught"]), len(safety["trapped"]))

    run = _run_info(args.workers)
    print(f"samples evaluated: {len(samples)}")
    print(f"mode: {run['mode']}  model: {run['model'] or '(unset)'}  "
          f"provider: {run['provider']}  workers: {run['workers']}  at: {run['generated_at']}")
    print(f"grouping model: {run['grouping_model'] or '(unset)'}  "
          f"legitimacy model: {run['legitimacy_model'] or '(unset)'}")
    if run["mode"] == "stub":
        print("WARNING: stub mode (DISASTERLENS_STUB=1) - these numbers are not a "
              "live model baseline.")
    print()
    print(f"{'metric':<28} {'rate':>7}  detail")
    print("-" * 52)
    for name, (part, whole) in metrics.items():
        print(f"{name:<28} {_fmt(_rate(part, whole)):>7}  {part}/{whole}")
    for label, key in (("duplicate precision", "precision"),
                       ("duplicate recall", "recall"),
                       ("  precision (no coords)", "precision_no_coords"),
                       ("  recall (no coords)", "recall_no_coords")):
        rate, part, whole = dup[key]
        print(f"{label:<28} {_fmt(rate):>7}  {part}/{whole}")
    print(f"{'grouping type accuracy':<28} "
          f"{_fmt(grouping_metrics['accuracy']):>7}  "
          f"{grouping_metrics['correct']}/{grouping_metrics['total']}")
    print(f"{'legitimacy accuracy':<28} "
          f"{_fmt(trust['legitimacy']['accuracy']):>7}  "
          f"{trust['legitimacy']['correct']}/{trust['legitimacy']['total']}")
    print(f"{'repeat reporter rule':<28} "
          f"{_fmt(trust['repeat_reporter']['accuracy']):>7}  "
          f"{trust['repeat_reporter']['correct']}/{trust['repeat_reporter']['total']}")
    if grouping_errors:
        print(f"grouping stage failures: {json.dumps(grouping_errors, ensure_ascii=False)}")
    legitimacy_errors = {
        sid: result["error"]
        for sid, result in legitimacy.items()
        if result["error"]
    }
    if legitimacy_errors:
        print(f"legitimacy stage failures: {json.dumps(legitimacy_errors, ensure_ascii=False)}")

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
    for key, label in (("missed", "duplicate missed"),
                       ("false_positives", "duplicate false positive"),
                       ("missed_no_coords", "duplicate missed (no coords)"),
                       ("false_positives_no_coords", "duplicate false positive (no coords)")):
        if dup[key]:
            print(f"  [{label}] {dup[key]}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"run": run,
             "metrics": {k: {"correct": a, "total": b, "rate": _rate(a, b)}
                         for k, (a, b) in metrics.items()},
             "duplicate": {"precision": dup["precision"][0], "recall": dup["recall"][0],
                           "precision_no_coords": dup["precision_no_coords"][0],
                           "recall_no_coords": dup["recall_no_coords"][0],
                           "missed": dup["missed"], "false_positives": dup["false_positives"],
                           "missed_no_coords": dup["missed_no_coords"],
                           "false_positives_no_coords": dup["false_positives_no_coords"]},
             "grouping": grouping_metrics,
             "grouping_errors": grouping_errors,
             "trust": trust,
             "legitimacy_errors": legitimacy_errors,
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
