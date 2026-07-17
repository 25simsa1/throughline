from stages import connect_stage


def test_cosine_basics():
    assert connect_stage.cosine([1, 0], [1, 0]) == 1.0
    assert connect_stage.cosine([1, 0], [0, 1]) == 0.0
    assert connect_stage.cosine([0, 0], [1, 0]) == 0.0


def test_shortlist_pairs_cross_source_only_and_capped():
    units = [
        {"source_id": "a"}, {"source_id": "a"},
        {"source_id": "b"}, {"source_id": "c"},
    ]
    vectors = [
        [1.0, 0.0], [0.9, 0.1],
        [0.95, 0.05], [0.0, 1.0],
    ]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=2)
    assert (0, 2) in pairs
    assert all(units[i]["source_id"] != units[j]["source_id"] for i, j in pairs)
    assert len(pairs) == 2


def test_shortlist_respects_max_per_unit():
    units = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "c"}, {"source_id": "d"}]
    vectors = [[1, 0], [0.99, 0.01], [0.98, 0.02], [0.97, 0.03]]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=10, max_per_unit=1)
    flat = [i for p in pairs for i in p]
    assert len(flat) == len(set(flat))
