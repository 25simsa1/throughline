import schemas


def test_valid_unit_has_no_errors():
    u = {"source_id": "s", "kind": "claim", "statement": "x",
         "quote": "q", "loc": "p.1"}
    assert schemas.validate_unit(u) == []


def test_unit_missing_quote_and_loc_reports_both():
    errs = schemas.validate_unit({"source_id": "s", "kind": "claim", "statement": "x"})
    assert any("quote" in e for e in errs)
    assert any("loc" in e for e in errs)


def test_unit_bad_kind_is_rejected():
    errs = schemas.validate_unit(
        {"source_id": "s", "kind": "opinion", "statement": "x", "quote": "q", "loc": "p.1"}
    )
    assert any("kind" in e for e in errs)


def test_connection_requires_tensions_and_evidence():
    c = {"id": "c1", "move": "m", "sources_involved": ["a"],
         "interpretation": "i", "evidence": [], "advances_thesis": "t"}
    errs = schemas.validate_connection(c)
    assert any("tensions" in e for e in errs)
    assert any("evidence" in e for e in errs)


def test_connection_with_non_dict_evidence_does_not_crash():
    c = {"id": "c1", "move": "m", "sources_involved": ["a"],
         "interpretation": "i", "evidence": ["not-a-dict"],
         "advances_thesis": "t", "tensions": "x"}
    errs = schemas.validate_connection(c)
    assert any("evidence[0]" in e for e in errs)


def test_validate_units_reports_index_prefixed_errors():
    units = [
        {"source_id": "s", "kind": "claim", "statement": "x", "quote": "q", "loc": "p.1"},
        {"source_id": "s", "kind": "claim", "statement": "x"},  # missing quote + loc
    ]
    errs = schemas.validate_units(units)
    assert errs  # non-empty
    assert all(e.startswith("[1]") for e in errs)  # only the second unit is invalid
