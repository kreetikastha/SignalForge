from disasterlens_ai import score_urgency
from disasterlens_ai.schemas import ReportAnalysis


def _a(sev=2, **kw):
    return ReportAnalysis(incident_type="flood", severity=sev, summary="s",
                          confidence=0.8, **kw)


def test_people_trapped_adds_exactly_12():
    trapped = score_urgency(_a(2, people_trapped="yes"))
    unknown = score_urgency(_a(2, people_trapped="unknown"))
    assert trapped - unknown == 12
    assert score_urgency(_a(2, people_trapped="no")) == unknown


def test_road_blocked_adds_exactly_6():
    blocked = score_urgency(_a(2, road_blocked="yes"))
    none = score_urgency(_a(2, road_blocked="unknown"))
    assert blocked - none == 6
    assert score_urgency(_a(2, road_blocked="no")) == none


def test_every_flag_severity_5_caps_at_100():
    a = _a(5, people_affected=50, vulnerable_groups=["children"],
           people_trapped="yes", road_blocked="yes")
    assert score_urgency(a, duplicate_count=10) == 100


def test_severity_1_no_flags_is_12():
    assert score_urgency(_a(1)) == 12


def test_non_decreasing_in_duplicate_count():
    a = _a(3, people_affected=10, vulnerable_groups=["elderly"],
           people_trapped="yes", road_blocked="yes")
    scores = [score_urgency(a, duplicate_count=n) for n in range(1, 9)]
    assert scores == sorted(scores)


def test_people_affected_tiers():
    base = score_urgency(_a(2))  # severity only: 2*12 = 24
    tiers = [
        (None, 0), (0, 0), (-3, 0),
        (1, 6), (5, 6),
        (6, 12), (20, 12),
        (21, 18), (50, 18),
        (51, 24), (5_000, 24),
    ]
    for affected, points in tiers:
        assert score_urgency(_a(2, people_affected=affected)) - base == points, affected


def test_mass_casualty_tier_outranks_small_casualty():
    # Same severity: 400 affected must beat 4 affected by 24 - 6 = 18 points.
    small = score_urgency(_a(3, people_affected=4))
    large = score_urgency(_a(3, people_affected=400))
    assert large - small == 18


def test_score_is_monotonic_in_people_affected():
    affected = [None, 0, 1, 5, 6, 20, 21, 50, 51, 1_000]
    scores = [score_urgency(_a(3, people_affected=n)) for n in affected]
    assert scores == sorted(scores)
    assert scores[0] < scores[-1]


def test_corroboration_bonus_saturates_at_20():
    a = _a(3)
    assert score_urgency(a, duplicate_count=1) == score_urgency(a, duplicate_count=0)
    assert score_urgency(a, duplicate_count=6) - score_urgency(a) == 20
    assert score_urgency(a, duplicate_count=99) == score_urgency(a, duplicate_count=6)


def test_every_score_is_positive_and_capped_at_100():
    for severity in range(1, 6):
        for affected in (None, 0, 3, 15, 40, 10_000):
            for duplicates in (1, 4, 12):
                score = score_urgency(
                    _a(severity, people_affected=affected,
                       vulnerable_groups=["children"], people_trapped="yes",
                       road_blocked="yes"),
                    duplicate_count=duplicates,
                )
                assert 0 < score <= 100, (severity, affected, duplicates, score)
                assert score == max(0, min(100, score))


def test_tiers_keep_scores_monotonic_in_severity():
    for affected in (None, 3, 15, 45, 900):
        scores = [score_urgency(_a(sev, people_affected=affected))
                  for sev in range(1, 6)]
        assert scores == sorted(scores), affected
