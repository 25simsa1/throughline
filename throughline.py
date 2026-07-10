from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ingest
import store
import verify

_THESIS_STUB = "# Chapter thesis\n\nWrite the chapter thesis and theme note here.\n"


def _chapter_dir(name: str) -> Path:
    return Path("chapters") / name


def cmd_new(args) -> int:
    ch = _chapter_dir(args.chapter)
    (ch / "sources").mkdir(parents=True, exist_ok=True)
    (ch / "drafts").mkdir(parents=True, exist_ok=True)
    thesis = ch / "thesis.md"
    if not thesis.exists():
        thesis.write_text(_THESIS_STUB, encoding="utf-8")
    print(f"created chapter scaffold at {ch}")
    return 0


def cmd_ingest(args) -> int:
    try:
        sources = ingest.ingest_chapter(_chapter_dir(args.chapter))
    except ingest.IngestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"ingested {len(sources)} source(s)")
    return 0


def cmd_verify(args) -> int:
    ch = _chapter_dir(args.chapter)
    if not (ch / "store" / "segments.json").exists():
        print(
            f"error: chapter '{args.chapter}' not ingested yet; run 'ingest' first",
            file=sys.stderr,
        )
        return 1
    for src in store.load_segments(ch):
        if not (ch / "store" / f"{src.source_id}.units.json").exists():
            print(f"{src.source_id}: not extracted yet")
            continue
        r = verify.verify_units_file(ch, src.source_id)
        print(f"{src.source_id}: {r['verified']} verified, {r['unverified']} UNVERIFIED")
    if (ch / "report.json").exists():
        r = verify.verify_report_file(ch)
        print(f"report: {r['unverified_evidence']} UNVERIFIED evidence item(s)")
    return 0


def cmd_status(args) -> int:
    ch = _chapter_dir(args.chapter)
    seg = ch / "store" / "segments.json"
    n_sources = len(store.load_segments(ch)) if seg.exists() else 0
    n_units = len(list((ch / "store").glob("*.units.json"))) if seg.exists() else 0
    n_drafts = len(list((ch / "drafts").glob("*.md"))) if (ch / "drafts").exists() else 0
    has_report = (ch / "report.md").exists()
    print(f"{n_sources} source(s) ingested")
    print(f"{n_units} source(s) with extracted units")
    print(f"report present: {has_report}")
    print(f"{n_drafts} draft(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="throughline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in [("new", cmd_new), ("ingest", cmd_ingest),
                     ("verify", cmd_verify), ("status", cmd_status)]:
        p = sub.add_parser(name)
        p.add_argument("chapter")
        p.set_defaults(func=fn)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
