from . import config
from .analyzer import _extract_json
from .client import chat
from .schemas import LegitimacyAnalysis


def assess_legitimacy(text: str) -> LegitimacyAnalysis:
    if config.STUB_MODE:
        return LegitimacyAnalysis(
            label="uncertain",
            confidence=0.0,
            reason="Legitimacy assessment is disabled in stub mode.",
        )
    system = (config.PROMPTS_DIR / "legitimacy_system.txt").read_text(
        encoding="utf-8"
    )
    payload = _extract_json(
        chat(
            system,
            text,
            timeout=config.REQUEST_TIMEOUT,
            model=config.LEGIT_MODEL,
        )
    )
    return LegitimacyAnalysis(**payload)
