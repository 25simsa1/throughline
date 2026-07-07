from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    loc: str
    text: str

    def to_dict(self) -> dict:
        return {"loc": self.loc, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(loc=d["loc"], text=d["text"])


@dataclass
class Source:
    source_id: str
    title: str
    type: str
    segments: list[Segment] = field(default_factory=list)
    author: str = ""
    year: int | None = None
    venue: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "venue": self.venue,
            "type": self.type,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            source_id=d["source_id"],
            title=d["title"],
            type=d["type"],
            author=d.get("author", ""),
            year=d.get("year"),
            venue=d.get("venue"),
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
        )
