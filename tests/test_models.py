from models import Segment, Source


def test_source_round_trips_through_dict():
    src = Source(
        source_id="book-a",
        title="A Book",
        author="Jane Doe",
        year=2019,
        venue=None,
        type="book",
        segments=[Segment(loc="p.1", text="Hello world.")],
    )
    restored = Source.from_dict(src.to_dict())
    assert restored == src
    assert restored.segments[0].loc == "p.1"


def test_source_from_dict_defaults_missing_optionals():
    d = {"source_id": "s", "title": "T", "type": "paper", "segments": []}
    src = Source.from_dict(d)
    assert src.author == ""
    assert src.year is None
    assert src.venue is None
    assert src.segments == []
