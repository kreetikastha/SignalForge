"""Preflight check for the staged pipeline. Run with:
    uv run python scripts/check_api.py
or with stub mode:
    DISASTERLENS_STUB=1 uv run python scripts/check_api.py

Outputs PASS/WARN/FAIL on the last line. Exit 0 on PASS|WARN, 1 on FAIL.
Never prints API keys.
"""
import os
import time
from disasterlens_ai import config, analyze_report, assess_legitimacy, group_report

TEXT = (
    "Heavy rain caused the river to overflow near Kalimati and water entered "
    "ground-floor shops."
)


def _run_stage(name, fn, *args, **kwargs):
    """Run a single stage, returning (ok, result_or_exception, elapsed, model_name)."""
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        ok = True
        elapsed = time.perf_counter() - t0
        return ok, result, elapsed, None
    except Exception as e:
        ok = False
        elapsed = time.perf_counter() - t0
        return ok, e, elapsed, None


def pass_stage(result) -> bool:
    """Return True when a stage is considered OK."""
    return result is not None


def run_pass(pass_label: str) -> int:
    """Run all three stages once and return exit code (0=OK, 1=FAIL)."""
    stages = [
        ("group_report", group_report, (TEXT,)),
        ("analyze_report", analyze_report, (TEXT,)),
        ("assess_legitimacy", assess_legitimacy, (TEXT,)),
    ]

    model_names = {
        "group_report": config.GROUPING_MODEL,
        "analyze_report": config.LLM_MODEL,
        "assess_legitimacy": config.LEGIT_MODEL,
    }

    all_ok = True
    details = []

    for name, fn, args in stages:
        ok, result, elapsed, exc = _run_stage(name, fn, *args)
        model = model_names[name]
        if ok:
            # For analyze_report, check confidence and fallback warning
            if name == "analyze_report":
                confidence = getattr(result, "confidence", None) or 1.0
                summary = getattr(result, "summary", "") or ""
                warn_fb = confidence <= 0.1 or summary.startswith("[analysis failed")
                label = "WARN" if warn_fb else "OK"
                details.append(
                    f"  {label} {name} ({model}) {elapsed:.2f}s "
                    f"(confidence={confidence})"
                )
                if warn_fb:
                    print("fallback result")
            else:
                details.append(f"  OK {name} ({model}) {elapsed:.2f}s")
        else:
            all_ok = False
            details.append(f"  FAIL {name} ({type(exc).__name__}) {elapsed:.2f}s")

    # Print per-stage labels on separate lines for clarity
    for d in details:
        print(d)

    # Return 0 if all OK, 1 if any FAIL
    return 0 if all_ok else 1


def main() -> int:
    stub = os.getenv("DISASTERLENS_STUB", "0") == "1"

    if stub:
        print("stub mode is on; skipping API calls")
        return 0

    # Cold pass
    cold_exit = run_pass("cold")

    # Warm pass (reuses process state, faster)
    warm_exit = run_pass("warm")

    # Determine final status
    # We need to track whether all stages were OK in both passes
    # PASS: every stage OK and warm total <= 20s
    # WARN: every stage OK but warm total > 20s
    # FAIL: any stage FAIL

    # Re-compute warm total from the warm pass details
    # The warm pass prints details; we need to capture the total time
    # Let's re-run with timing aggregation

    # Actually, let's re-approach: capture warm total time separately
    t0_warm = time.perf_counter()
    warm_exit_code = run_pass("warm2")  # third run to measure pure warm time
    warm_total = time.perf_counter() - t0_warm

    # For simplicity: use the warm pass's total from the 2nd run
    # We'll re-derive from the printout: if all stages said OK, check timing
    # Let's just re-run a clean warm-timed pass

    # Actually, the specification says: "Print total seconds per pass"
    # and "a final line: PASS if every stage is OK and the warm total is <= 20s,
    # WARN if OK but slower, FAIL otherwise"

    # Let me restructure: I'll track totals explicitly
    return 0  # fallback, will be overwritten


if __name__ == "__main__":
    # Quick inline re-run with proper timing
    stub = os.getenv("DISASTERLENS_STUB", "0") == "1"
    if stub:
        print("stub mode is on; skipping API calls")
        raise SystemExit(0)

    # Cold pass with timing
    t0_cold = time.perf_counter()
    cold_code = run_pass("cold")
    cold_total = time.perf_counter() - t0_cold

    # Warm pass with timing
    t0_warm = time.perf_counter()
    warm_code = run_pass("warm")
    warm_total = time.perf_counter() - t0_warm

    # Determine final status line
    # need to know if all stages OK - we can check by re-running quickly
    # or we track it. Let's re-run a verification pass.
    # Actually the run_pass already prints details. Let's just look at
    # whether cold_code and warm_code are 0 (all OK).

    if cold_code != 0 or warm_code != 0:
        final = "FAIL"
    elif warm_total <= 20:
        final = "PASS"
    else:
        final = "WARN"

    # Print totals
    print(f"cold total: {cold_total:.2f}s")
    print(f"warm total: {warm_total:.2f}s")
    print(final)

    # Exit 0 on PASS|WARN, 1 on FAIL
    raise SystemExit(0 if final in ("PASS", "WARN") else 1)