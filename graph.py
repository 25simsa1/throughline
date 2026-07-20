"""Turn a chapter's connection report into a standalone map.html, the papers
as nodes, the connections as cards wired to the papers they draw on, keep and
drop shown as the scholar marked them. Self-contained, opens in any browser."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import render
import store

_STATUS = {
    "keep": ("KEPT", "kept"),
    "drop": ("DROPPED", "dropped"),
    "candidate": ("UNDECIDED", "candidate"),
}


def _node_id(source_id: str) -> str:
    return "p-" + re.sub(r"[^a-zA-Z0-9]+", "-", source_id).strip("-")


def _source_label(src) -> tuple[str, str]:
    # (headline, sub) e.g. ("Curry et al. 2025", "A question of alignment...")
    author = (getattr(src, "author", "") or "").strip()
    year = getattr(src, "year", None)
    title = (getattr(src, "title", "") or src.source_id).strip()
    if author and year:
        return f"{author} {year}", title
    if author:
        return author, title
    return title, ""


def _first_sentence(move: str) -> tuple[str, str]:
    parts = move.split(". ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return move.rstrip("."), ""


def build_map(chapter_dir: Path) -> Path:
    report = json.loads((chapter_dir / "report.json").read_text(encoding="utf-8"))
    decisions = {}
    md = chapter_dir / "report.md"
    if md.exists():
        decisions = render.parse_decisions(md.read_text(encoding="utf-8"))
    sources = []
    seg = chapter_dir / "store" / "segments.json"
    if seg.exists():
        for s in store.load_segments(chapter_dir):
            head, sub = _source_label(s)
            sources.append({"id": s.source_id, "head": head, "sub": sub})
    html_text = render_map_html(report, chapter_dir.name, sources, decisions)
    out = chapter_dir / "map.html"
    out.write_text(html_text, encoding="utf-8")
    return out


def render_map_html(report: dict, chapter: str, sources: list[dict],
                    decisions: dict[str, dict]) -> str:
    conns = report.get("connections", []) or []

    # any source referenced by a connection but not in the store still gets a node
    known = {s["id"] for s in sources}
    for c in conns:
        for sid in c.get("sources_involved", []) or []:
            if sid not in known:
                sources.append({"id": sid, "head": sid, "sub": ""})
                known.add(sid)

    id_map = {s["id"]: _node_id(s["id"]) for s in sources}

    paper_cards = []
    for s in sources:
        paper_cards.append(
            f'<div class="paper" id="{id_map[s["id"]]}">'
            f'<span class="who">{html.escape(s["head"])}</span>'
            + (f'<div class="what">{html.escape(s["sub"])}</div>' if s["sub"] else "")
            + "</div>"
        )

    conn_cards = []
    for c in conns:
        cid = str(c.get("id", "?"))
        decision = (decisions.get(cid, {}).get("decision")
                    or c.get("status") or "candidate").lower()
        label, css = _STATUS.get(decision, _STATUS["candidate"])
        title, rest = _first_sentence(c.get("move", cid))
        summary = rest or (c.get("interpretation", "")[:200]).strip()
        note = decisions.get(cid, {}).get("note", "")
        ev = c.get("evidence", []) or []
        involved = [id_map[s] for s in (c.get("sources_involved") or []) if s in id_map]
        meta = f"{len(ev)} verified quotation" + ("" if len(ev) == 1 else "s")
        if decision == "drop" and note:
            meta = html.escape(note)
        conn_cards.append(
            f'<div class="conn {css}" data-papers="{",".join(involved)}">'
            f'<span class="chip">{html.escape(cid)} &middot; {label}</span>'
            f'<h3>{html.escape(title)}</h3>'
            f'<p>{html.escape(summary)}</p>'
            f'<div class="meta">{meta}</div>'
            "</div>"
        )

    n_kept = sum(1 for c in conns
                 if (decisions.get(str(c.get("id")), {}).get("decision")
                     or c.get("status") or "candidate").lower() == "keep")
    subtitle = (f"{len(sources)} sources, {len(conns)} connections, "
                f"{n_kept} kept")

    return _TEMPLATE.format(
        chapter=html.escape(chapter),
        subtitle=html.escape(subtitle),
        papers="\n".join(paper_cards),
        conns="\n".join(conn_cards),
    )


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Throughline map, {chapter}</title>
<style>
  :root {{
    --paper: #F5F4EF; --card: #FFFFFF; --ink: #232A31; --ink2: #5C6660;
    --line: #DAD8CF; --teal: #0A8A72; --teal-soft: rgba(10,138,114,.38);
    --amber: #A86B00; --drop: #8A9089; --shadow: 0 1px 3px rgba(35,42,49,.07);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --paper: #15191D; --card: #1E242A; --ink: #E8E6DF; --ink2: #9BA5A0;
      --line: #343B41; --teal: #12A188; --teal-soft: rgba(18,161,136,.45);
      --amber: #B5821F; --drop: #6E7770; --shadow: 0 1px 3px rgba(0,0,0,.35);
    }}
  }}
  html {{ background: var(--paper); }}
  body {{ margin: 0; color: var(--ink); background: var(--paper);
    font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
    -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 44px 26px 70px; }}
  .eyebrow {{ font-family: system-ui, sans-serif; font-size: 12px;
    letter-spacing: .18em; text-transform: uppercase; color: var(--teal);
    font-weight: 700; margin: 0 0 8px; }}
  h1 {{ font-size: clamp(28px, 4.4vw, 40px); line-height: 1.12; margin: 0 0 6px;
    font-weight: 600; }}
  .sub {{ font-family: system-ui, sans-serif; color: var(--ink2); margin: 0 0 30px; }}
  .map {{ position: relative; }}
  .map svg.wires {{ position: absolute; inset: 0; width: 100%; height: 100%;
    pointer-events: none; }}
  .papers {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; position: relative; }}
  .paper {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px;
    padding: 13px 15px; box-shadow: var(--shadow); position: relative; z-index: 2; }}
  .paper .who {{ font-weight: 650; }}
  .paper .what {{ font-family: system-ui, sans-serif; color: var(--ink2);
    font-size: 13px; line-height: 1.4; margin-top: 3px; }}
  .conns {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px; margin-top: 90px; position: relative; }}
  .conn {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px;
    padding: 15px 17px; box-shadow: var(--shadow); position: relative; z-index: 2; }}
  .conn.dropped {{ background: transparent; border-style: dashed; box-shadow: none; }}
  .chip {{ font-family: system-ui, sans-serif; display: inline-block; font-size: 11px;
    font-weight: 700; letter-spacing: .09em; padding: 2px 9px; border-radius: 999px;
    color: #fff; background: var(--teal); }}
  .conn.candidate .chip {{ background: var(--amber); }}
  .conn.dropped .chip {{ background: var(--drop); }}
  .conn h3 {{ font-size: 18px; margin: 9px 0 7px; line-height: 1.24; font-weight: 600; }}
  .conn p {{ font-family: system-ui, sans-serif; margin: 0; font-size: 14px;
    color: var(--ink2); }}
  .conn .meta {{ font-family: ui-monospace, Menlo, monospace; font-size: 11.5px;
    color: var(--teal); margin-top: 10px; }}
  .conn.dropped .meta {{ color: var(--drop); }}
  footer {{ font-family: system-ui, sans-serif; margin-top: 54px; color: var(--ink2);
    font-size: 12.5px; border-top: 1px solid var(--line); padding-top: 14px; }}
  @media (max-width: 640px) {{
    .conns {{ margin-top: 24px; }} .map svg.wires {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">Throughline &middot; connection map</p>
  <h1>{chapter}</h1>
  <p class="sub">{subtitle}. Lines join each connection to the sources it draws on. Every quotation behind it was machine-checked against the source.</p>
  <div class="map">
    <svg class="wires" aria-hidden="true"></svg>
    <div class="papers">
{papers}
    </div>
    <div class="conns">
{conns}
    </div>
  </div>
  <footer>Generated by Throughline. Page numbers in the report refer to PDF pages pending journal pagination.</footer>
</div>
<script>
(function () {{
  var svg = document.querySelector(".wires"), map = document.querySelector(".map");
  function draw() {{
    if (window.innerWidth <= 640) {{ svg.innerHTML = ""; return; }}
    var mb = map.getBoundingClientRect();
    svg.setAttribute("viewBox", "0 0 " + mb.width + " " + mb.height);
    var cs = getComputedStyle(document.documentElement);
    var teal = cs.getPropertyValue("--teal-soft").trim();
    var drop = cs.getPropertyValue("--drop").trim();
    var out = [];
    document.querySelectorAll(".conn").forEach(function (conn) {{
      var dropped = conn.classList.contains("dropped");
      var cb = conn.getBoundingClientRect();
      var ids = (conn.getAttribute("data-papers") || "").split(",").filter(Boolean);
      ids.forEach(function (id, i) {{
        var p = document.getElementById(id);
        if (!p) return;
        var pb = p.getBoundingClientRect();
        var x1 = cb.left - mb.left + cb.width * ((i + 1) / (ids.length + 1));
        var y1 = cb.top - mb.top;
        var x2 = pb.left - mb.left + pb.width / 2;
        var y2 = pb.bottom - mb.top;
        var midY = (y1 + y2) / 2;
        out.push('<path d="M' + x1 + ',' + y1 + ' C' + x1 + ',' + midY + ' ' +
          x2 + ',' + midY + ' ' + x2 + ',' + y2 + '" fill="none" stroke="' +
          (dropped ? drop : teal) + '" stroke-width="2"' +
          (dropped ? ' stroke-dasharray="5 5" opacity="0.55"' : "") + ' />');
      }});
    }});
    svg.innerHTML = out.join("");
  }}
  window.addEventListener("resize", draw);
  window.addEventListener("load", draw);
  requestAnimationFrame(draw);
}})();
</script>
</body>
</html>
"""
