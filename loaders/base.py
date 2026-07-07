from __future__ import annotations

from pathlib import Path

from models import Source


class LoaderError(Exception):
    pass


class Loader:
    extensions: tuple[str, ...] = ()

    def load(self, path: Path, source_id: str) -> Source:
        raise NotImplementedError
