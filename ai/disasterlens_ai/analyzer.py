import json
import re
from pydantic import ValidationError
from . import config
from .client import chat
from .schemas import IncidentType, ReportAnalysis


def _load_prompt() -> str:
    return (config.PROMPTS_DIR / "analyze_system.txt").read_text(encoding="utf-8")


def _load_examples() -> list[dict]:
    path = config.PROMPTS_DIR / "analyze_examples.json"
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    msgs: list[dict] = []
    for ex in data:
        msgs.append({"role": "user", "content": ex["report"]})
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})
    return msgs


def _extract_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(raw[start:end + 1])


def _stub(text: str) -> ReportAnalysis:
    return ReportAnalysis(incident_type=IncidentType.OTHER, location_text=None,
                          severity=3, summary=text[:100], confidence=0.1)


def analyze_report(text: str, image: bytes | None = None) -> ReportAnalysis:
    if config.STUB_MODE:
        return _stub(text)
    system, shots = _load_prompt(), _load_examples()
    last_err: Exception | None = None
    for _ in range(config.MAX_RETRIES + 1):
        try:
            raw = chat(system, text, image=image, history=shots)
            return ReportAnalysis(**_extract_json(raw))
        except (ValueError, ValidationError) as e:  # bad JSON / schema mismatch
            last_err = e
    # Never crash the pipeline: return a low-confidence fallback for human review
    fb = _stub(text)
    fb.summary = f"[analysis failed: {last_err}] {text[:80]}"
    return fb
