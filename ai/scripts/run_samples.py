"""Print one preview line per sample analysis. Run from ai/:  DISASTERLENS_STUB=1 python scripts/run_samples.py"""
import json
from pathlib import Path
from disasterlens_ai import analyze_report

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    samples = json.loads((DATA_DIR / "sample_reports.json").read_text(encoding="utf-8"))
    for s in samples:
        a = analyze_report(s["text"])
        print(f"{s['id']}  {s['text'][:80]}")
        print(f"     type={a.incident_type.value} severity={a.severity} "
              f"trapped={a.people_trapped} blocked={a.road_blocked} confidence={a.confidence:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
