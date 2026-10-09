from .schemas import ReportAnalysis


def score_urgency(analysis: ReportAnalysis, duplicate_count: int = 1) -> int:
    score = analysis.severity * 12                      # 12-60
    if analysis.people_affected:
        score += 10
    if analysis.vulnerable_groups:
        score += 10
    score += min(max(duplicate_count - 1, 0), 5) * 4    # corroboration, max +20
    return min(score, 100)
