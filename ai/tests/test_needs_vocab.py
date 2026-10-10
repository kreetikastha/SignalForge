from disasterlens_ai.schemas import normalize_needs


def test_normalize_needs_synonyms():
    # medical synonyms
    assert normalize_needs(["ambulance"]) == ["medical"]
    assert normalize_needs(["doctor"]) == ["medical"]
    assert normalize_needs(["first_aid"]) == ["medical"]
    assert normalize_needs(["medical_aid"]) == ["medical"]
    assert normalize_needs(["medical_help"]) == ["medical"]

    # rescue synonyms
    assert normalize_needs(["search_and_rescue"]) == ["rescue"]
    assert normalize_needs(["extraction"]) == ["rescue"]
    assert normalize_needs(["trapped"]) == ["rescue"]

    # firefighting synonyms
    assert normalize_needs(["fire_brigade"]) == ["firefighting"]
    assert normalize_needs(["fire_fighting"]) == ["firefighting"]

    # water synonyms
    assert normalize_needs(["drinking_water"]) == ["water"]

    # shelter synonyms
    assert normalize_needs(["housing"]) == ["shelter"]
    assert normalize_needs(["tent"]) == ["shelter"]
    assert normalize_needs(["shelter_needed"]) == ["shelter"]

    # road_clearing synonyms
    assert normalize_needs(["clear_road"]) == ["road_clearing"]
    assert normalize_needs(["debris_removal"]) == ["road_clearing"]
    assert normalize_needs(["road_clearance"]) == ["road_clearing"]

    # evacuation synonyms
    assert normalize_needs(["evacuate"]) == ["evacuation"]


def test_normalize_needs_canonical_terms_pass_through():
    assert normalize_needs(["rescue", "medical", "food", "water", "shelter", "road_clearing", "firefighting", "evacuation"]) == [
        "rescue", "medical", "food", "water", "shelter", "road_clearing", "firefighting", "evacuation"
    ]


def test_normalize_needs_unknown_terms():
    # Unknown term alone -> "other"
    assert normalize_needs(["unknown_term"]) == ["other"]
    assert normalize_needs(["foo", "bar"]) == ["other"]  # deduped to one "other"


def test_normalize_needs_unknown_dropped_when_canonical_present():
    assert normalize_needs(["medical", "unknown_term"]) == ["medical"]
    assert normalize_needs(["rescue", "foo", "medical"]) == ["rescue", "medical"]


def test_normalize_needs_duplicates_removed_preserving_order():
    assert normalize_needs(["medical", "ambulance", "rescue", "medical"]) == ["medical", "rescue"]
    assert normalize_needs(["food", "food", "water", "shelter", "shelter"]) == ["food", "water", "shelter"]


def test_normalize_needs_empty_list():
    assert normalize_needs([]) == []
    assert normalize_needs(None) == []


def test_normalize_needs_case_and_whitespace():
    assert normalize_needs(["  MEDICAL  ", "Ambulance "]) == ["medical"]
    assert normalize_needs(["Rescue", "SEARCH_AND_RESCUE"]) == ["rescue"]


def test_normalize_needs_other_preserved_if_only_term():
    assert normalize_needs(["other"]) == ["other"]