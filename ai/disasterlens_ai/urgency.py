from .schemas import ReportAnalysis


def _people_affected_points(people_affected: int | None) -> int:
    """Non-linear casualty tiers (0 / +6 / +12 / +18 / +24).

    A flat bonus treats "3 people seen" and "60 people swept away" the same;
    the tiers make mass-casualty reports outrank small ones at equal severity.
    """
    if people_affected is None or people_affected <= 0:
        return 0
    if people_affected <= 5:
        return 6
    if people_affected <= 20:
        return 12
    if people_affected <= 50:
        return 18
    return 24


def score_urgency(analysis: ReportAnalysis, duplicate_count: int = 1) -> int:
    score = analysis.severity * 12                            # 12-60
    score += _people_affected_points(analysis.people_affected)  # 0-24
    if analysis.vulnerable_groups:
        score += 10
    if analysis.people_trapped == "yes":
        score += 12
    if analysis.road_blocked == "yes":
        score += 6
    score += min(max(duplicate_count - 1, 0), 5) * 4          # corroboration, 0-20
    return max(0, min(100, score))
