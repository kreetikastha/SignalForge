import re

from .schemas import ReportAnalysis

NEGATION_PHRASES = (
    # English
    "no one is trapped",
    "nobody is trapped",
    "no one trapped",
    "nobody trapped",
    "not trapped",
    "no casualties",
    # Romanized Nepali
    "koi faseko chaina",
    "kohe faseko chaina",
    "koohe faseko xaina",
    "faseko chaina",
    "kasailai kehi bhayeko chaina",
    # Devanagari
    "फसेको छैन",
    "कोही फसेको छैन",
)

TRAPPED_TERMS = (
    # English
    "trapped",
    "stuck",
    "buried",
    "under rubble",
    "under the rubble",
    "under the debris",
    "stuck inside",
    "cannot escape",
    "can't escape",
    # Romanized Nepali: फसेका/पुरिएका/च्यापिएका/अड्किएका and common spellings
    "faseka",
    "faseko",
    "phaseka",
    "phaseko",
    "adkeko",
    "adkiyo",
    "adkiyeko",
    "puriye",
    "puriyeko",
    "puriyeka",
    "chyapiyo",
    "chyapiyeko",
    "chyapieka",
    # Devanagari
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

# Word-boundary matching so short romanized stems ("fase", "puriye", "stuck")
# never match as substrings of unrelated words ("unstuck", "unburied").
# Plain \b is unusable: Devanagari terms end in a combining matra (category Mn),
# which is not a \w char, so the trailing \b would fail before a space. Looking
# for "no word char on either side" keeps the English-substring protection and
# still fires on मात्रा-ending terms. Each alternative carries its own guards,
# so "puriye" cannot shadow "puriyeko".
_TRAPPED_RE = re.compile("|".join(
    r"(?<!\w)%s(?!\w)" % re.escape(term)
    for term in sorted(TRAPPED_TERMS, key=len, reverse=True)))


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
        # Rule b: Trapped terms (word-boundary match on the lowered text)
        if _TRAPPED_RE.search(text_lower):
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
