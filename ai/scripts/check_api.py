"""Sanity-check the LLM endpoint. Run from ai/:  python scripts/check_api.py [image.jpg]"""
import sys
from disasterlens_ai import analyze_report, config
from disasterlens_ai.client import chat


def main() -> int:
    print(f"endpoint: {config.LLM_BASE_URL}\nmodel:    {config.LLM_MODEL}")
    if not config.LLM_API_KEY or not config.LLM_MODEL:
        print("FAIL: LLM_API_KEY / LLM_MODEL not set in ai/.env")
        return 1

    print("\n[1] raw call ...")
    try:
        print("   ->", chat("Reply with one word.", "Say OK").strip()[:80])
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1

    print("\n[2] structured analysis ...")
    r = analyze_report("Flood near Balkhu bridge, 2 children stuck on roof, need rescue")
    print(r.model_dump_json(indent=2))
    if r.confidence <= 0.1:
        print("WARN: looks like the fallback; model output was not valid JSON")
        return 1

    if len(sys.argv) > 1:
        print("\n[3] image call ...")
        img = open(sys.argv[1], "rb").read()
        print(analyze_report("Describe the damage in this photo", image=img).model_dump_json(indent=2))

    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
