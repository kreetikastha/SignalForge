import json
import logging
import re
import time
import unicodedata
from openai import APIError
from pydantic import ValidationError
from . import config
from .client import chat
from .safety import apply_safety_net
from .schemas import IncidentType, ReportAnalysis, normalize_needs

log = logging.getLogger(__name__)

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# ASCII control characters we drop from model output; \t \n \r stay legal.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate(_DEV_DIGITS)
    text = "".join(ch for ch in text if ch in ("\n", "\t") or unicodedata.category(ch) != "Cc")
    text = re.sub(r" +", " ", text)
    return text[:2000]


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
    """Pull the first JSON object out of noisy model output.

    Tolerates markdown code fences, prose around the object, trailing commas
    before a closing brace/bracket, and stray ASCII control characters.
    Raises ValueError when no object is present or the body is not JSON.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|```\s*$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in model output")
    sub = text[start:end + 1]
    sub = re.sub(r",\s*([\]}])", r"\1", sub)      # trailing commas
    sub = _CONTROL.sub("", sub)                    # 0x00-0x1F except \t \n \r
    return json.loads(sub)


def _stub(text: str) -> ReportAnalysis:
    return ReportAnalysis(incident_type=IncidentType.OTHER, location_text=None,
                          severity=3, summary=text[:100], confidence=0.1)


def _chat(system: str, norm_text: str, image: bytes | None, shots: list[dict],
          timeout: float) -> str:
    """One JSON-mode model call, degraded to text-only when vision fails.

    A vision failure (API error, truncated/invalid response) retries the same
    attempt without the image instead of consuming a slot of the retry budget.
    """
    if image is None:
        return chat(system, norm_text, image=None, history=shots,
                    timeout=timeout, json_mode=True)
    try:
        return chat(system, norm_text, image=image, history=shots,
                    timeout=timeout, json_mode=True)
    except (APIError, ValueError) as e:
        log.warning("vision call failed (%s: %s); retrying text-only", type(e).__name__, e)
        return chat(system, norm_text, image=None, history=shots,
                    timeout=timeout, json_mode=True)


def analyze_report(text: str, image: bytes | None = None) -> ReportAnalysis:
    norm_text = _normalize(text)
    if config.STUB_MODE:
        return _stub(norm_text)
    system, shots = _load_prompt(), _load_examples()
    deadline = time.monotonic() + config.TOTAL_TIMEOUT
    last_err: Exception | None = None
    for _ in range(config.MAX_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:  # out of budget: do not start an attempt that cannot finish
            last_err = last_err or TimeoutError("analysis budget exhausted")
            break
        try:
            raw = _chat(system, norm_text, image, shots,
                        timeout=min(config.REQUEST_TIMEOUT, remaining))
            parsed_dict = _extract_json(raw)
            # Normalize needs to canonical vocabulary before validation
            if "needs" in parsed_dict and isinstance(parsed_dict["needs"], list):
                parsed_dict["needs"] = normalize_needs(parsed_dict["needs"])
            parsed = ReportAnalysis(**parsed_dict)
            return apply_safety_net(norm_text, parsed)
        except (ValueError, ValidationError) as e:  # bad JSON / schema mismatch
            last_err = e
        except (APIError, OSError) as e:  # provider timeout / transport / HTTP error
            last_err = e
    # Never crash the pipeline: return a low-confidence fallback for human review.
    # The safety net still runs, so trapped/rescue keywords survive a dead provider.
    fb = apply_safety_net(norm_text, _stub(norm_text))
    fb.summary = f"[analysis failed: {last_err}] {text[:80]}"
    return fb
