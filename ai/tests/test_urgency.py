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
