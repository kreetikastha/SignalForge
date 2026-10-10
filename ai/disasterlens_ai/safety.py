import re

from .schemas import ReportAnalysis

NEGATION_PHRASES = (
    # English
    "no one is trapped",
    "nobody is trapped",
    "no one trapped",
    "nobody trapped",
    "no one was trapped",
    "nobody was trapped",
    "none trapped",
    "no people trapped",
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
    # Bare "stuck" is deliberately NOT a term: "bus stuck in mud", "cars stuck
    # in traffic" describe vehicles, not trapped people. These specific senses
    # always denote someone who cannot get out; person-subject and
    # "stuck on the roof" senses are handled by _stuck_means_trapped().
    "stuck inside",
    "stuck under",
    "stuck in the rubble",
    "stuck in the house",
    "stuck in the building",
    "stuck in the debris",
    "buried",
    "under rubble",
    "under the rubble",
    "under the debris",
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

# Word-boundary matching so short stems ("fase", "puriye") and short English
# terms ("buried", "trapped") never match as substrings of unrelated words
# ("unburied", "untrapped").
# Plain \b is unusable: Devanagari terms end in a combining matra (category Mn),
# which is not a \w char, so the trailing \b would fail before a space. Looking
# for "no word char on either side" keeps the English-substring protection and
# still fires on मात्रा-ending terms. Each alternative carries its own guards,
# so "puriye" cannot shadow "puriyeko".
_TRAPPED_RE = re.compile("|".join(
    r"(?<!\w)%s(?!\w)" % re.escape(term)
    for term in sorted(TRAPPED_TERMS, key=len, reverse=True)))

# "stuck" is ambiguous: "2 children stuck on roof" is a rescue, "bus stuck in
# mud" is not. Bare "stuck" is therefore not in TRAPPED_TERMS; it counts only
# when a person-noun is the subject, or when it names a place people are
# stranded (roof, tree...). Vehicle-in-traffic/mud phrasing is excluded first.
_PERSON_NOUNS = (r"(?:people|persons?|children|child|kids?|babies|baby|family|families|"
                 r"men|man|women|woman|elderly|residents?|villagers?|passengers?|"
                 r"students?|workers?|labou?rers?|someone|somebody)")
_STUCK_PERSON_RE = re.compile(r"(?<!\w)%s(?:\s+\w+){0,2}?\s+stuck(?!\w)" % _PERSON_NOUNS)
_STUCK_PLACE_RE = re.compile(
    r"(?<!\w)stuck\s+(?:on|at|atop|up)\s+(?:the\s+|a\s+|their\s+|his\s+|her\s+)?"
    r"(?:roof|rooftop|tree|terrace|island|hilltop)(?!\w)")
_STUCK_BENIGN_RE = re.compile(
    r"(?<!\w)stuck\s+in\s+(?:the\s+|a\s+)?(?:traffic|mud|jam|queue)(?!\w)")

# Clause delimiters for the negation guard. । (U+0964 DEVANAGARI DANDA) is the
# Devanagari full stop, so Devanagari sentences split the same way English ones
# do. A run of delimiters ("...!", "a; b") collapses into a single cut.
_CLAUSE_RE = re.compile(r"[.!?।\n;,]+")


def _add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _clauses(text_lower: str) -> list[str]:
    return [clause for clause in _CLAUSE_RE.split(text_lower) if clause.strip()]


def _stuck_means_trapped(clause: str) -> bool:
    if _STUCK_BENIGN_RE.search(clause):
        return False
    return bool(_STUCK_PERSON_RE.search(clause) or _STUCK_PLACE_RE.search(clause))


def _negated(clause: str) -> bool:
    return any(phrase in clause for phrase in NEGATION_PHRASES)


def _reports_trapped(text_lower: str) -> bool:
    """True when some clause names a trapped term that its own negation allows.

    Negation is clause-local: "...but nobody was trapped" cancels the trapped
    terms of that clause only, so it can no longer silence a trapped report in
    a different clause of the same message.
    """
    return any(
        not _negated(clause)
        and (_TRAPPED_RE.search(clause) or _stuck_means_trapped(clause))
        for clause in _clauses(text_lower)
    )


def apply_safety_net(text: str, a: ReportAnalysis) -> ReportAnalysis:
    out = a.model_copy(deep=True)
    if out.flags is None:
        out.flags = []
    else:
        out.flags = list(out.flags)

    text_lower = text.lower()

    # Rule b: Trapped terms, evaluated per clause (see _reports_trapped).
    if _reports_trapped(text_lower):
        if out.people_trapped != "yes":
            out.people_trapped = "yes"
            _add_flag(out.flags, "trapped_keyword_override")

    # Rule c: Severity floor for trapped. Keyed off the final value rather than
    # off the text, so a negated clause elsewhere can neither cancel the floor
    # for a trapped person reported in another clause nor create one.
    if out.people_trapped == "yes" and out.severity < 4:
        out.severity = 4
        _add_flag(out.flags, "severity_floor_trapped")

    # Rule d: Low confidence
    if out.confidence < 0.5:
        _add_flag(out.flags, "low_confidence")

    return out
