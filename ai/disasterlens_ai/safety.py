from .schemas import ReportAnalysis

NEGATION_PHRASES = (
    "no one is trapped",
    "nobody is trapped",
    "no one trapped",
    "nobody trapped",
    "not trapped",
    "फसेको छैन",
    "कोही फसेको छैन",
)

TRAPPED_TERMS = (
    "trapped",
    "stuck",
    "buried",
    "under rubble",
    "under the rubble",
    "cannot escape",
    "can't escape",
    "फसेका",
    "फसेको",
    "फस्यो",
    "फसे",
    "पुरिएका",
    "पुरिएको",
    "च्यापिएका",
    "च्यापिएको",
    "अड्किएका",
)


def _add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def apply_safety_net(text: str, a: ReportAnalysis) -> ReportAnalysis:
    out = a.copy(deep=True)
    if out.flags is None:
        out.flags = []
    else:
        out.flags = list(out.flags)

    text_lower = text.lower()

    # Rule a: Negation guard
    negation = any(phrase in text_lower for phrase in NEGATION_PHRASES)

    if not negation:
        # Rule b: Trapped terms
        if any(term in text_lower for term in TRAPPED_TERMS):
            if out.people_trapped != "yes":
                out.people_trapped = "yes"
                _add_flag(out.flags, "trapped_keyword_override")

        # Rule c: Severity floor for trapped
        if out.people_trapped == "yes" and out.severity < 4:
            out.severity = 4
            _add_flag(out.flags, "severity_floor_trapped")

    # Rule d: Low confidence
    if out.confidence < 0.5:
        _add_flag(out.flags, "low_confidence")

    return out
