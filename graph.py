"""Turn a chapter's connection report into a standalone map.html, an
Obsidian-style force graph. The chapter is the hub, connections and sources
are nodes, kept links are bright and dropped ones fade out. Self-contained
canvas, no libraries, opens in any browser offline."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import render
import store


def _node_id(source_id: str) -> str:
    return "p-" + re.sub(r"[^a-zA-Z0-9]+", "-", source_id).strip("-")


def _source_label(src) -> tuple[str, str]:
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
    if (chapter_dir / "store" / "segments.json").exists():
        for s in store.load_segments(chapter_dir):
            head, sub = _source_label(s)
            sources.append({"id": s.source_id, "head": head, "sub": sub})
    out = chapter_dir / "map.html"
    out.write_text(render_map_html(report, chapter_dir.name, sources, decisions),
                   encoding="utf-8")
    return out


def graph_data(report: dict, chapter: str, sources: list[dict],
               decisions: dict[str, dict]) -> dict:
    conns = report.get("connections", []) or []
    known = {s["id"] for s in sources}
    for c in conns:
        for sid in c.get("sources_involved", []) or []:
            if sid not in known:
                sources.append({"id": sid, "head": sid, "sub": ""})
                known.add(sid)

    nodes = [{"id": "__hub__", "type": "hub", "label": chapter, "size": 20}]
    for s in sources:
        nodes.append({"id": s["id"], "type": "paper", "label": s["head"],
                      "sub": s["sub"], "size": 13})
    edges = []
    kept = 0
    for c in conns:
        cid = str(c.get("id", "?"))
        decision = (decisions.get(cid, {}).get("decision")
                    or c.get("status") or "candidate").lower()
        if decision not in ("keep", "drop", "candidate"):
            decision = "candidate"
        kept += decision == "keep"
        title, rest = _first_sentence(c.get("move", cid))
        involved = [s for s in (c.get("sources_involved") or []) if s in known]
        ev = c.get("evidence", []) or []
        nodes.append({"id": cid, "type": "conn", "label": title, "status": decision,
                      "size": 10, "ev": len(ev), "sources": involved,
                      "sub": (rest or c.get("interpretation", "")[:160]).strip()})
        edges.append({"s": "__hub__", "t": cid, "status": decision})
        for sid in involved:
            edges.append({"s": cid, "t": sid, "status": decision})
    return {"chapter": chapter, "nodes": nodes, "edges": edges,
            "counts": {"sources": len(sources), "connections": len(conns), "kept": kept}}


def render_map_html(report: dict, chapter: str, sources: list[dict],
                    decisions: dict[str, dict]) -> str:
    data = graph_data(report, chapter, sources, decisions)
    # escape "<" so no content string can close the script tag or inject markup
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    c = data["counts"]
    subtitle = f"{c['sources']} sources, {c['connections']} connections, {c['kept']} kept"
    return (_TEMPLATE
            .replace("__CHAPTER_TITLE__", html.escape(chapter))
            .replace("__SUBTITLE__", html.escape(subtitle))
            .replace("/*__DATA__*/", payload))


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Throughline map, __CHAPTER_TITLE__</title>
<style>
  :root {
    --bg: #12151a; --ink: #E6E4DD; --ink2: #8A9299; --line: #2A2F37;
    --hub: #ECEAE2; --paper: #6FA8C7; --keep: #23B79C; --cand: #D2A24A; --drop: #5E666E;
  }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { position: fixed; top: 0; left: 0; right: 0; padding: 16px 20px 14px;
    background: linear-gradient(var(--bg), rgba(18,21,26,0)); z-index: 3; pointer-events: none; }
  h1 { margin: 0; font-size: 19px; font-weight: 600; letter-spacing: .2px; }
  .sub { margin: 2px 0 0; font-size: 13px; color: var(--ink2); }
  .legend { margin-top: 9px; font-size: 12px; color: var(--ink2); display: flex; gap: 16px; flex-wrap: wrap; }
  .legend b { font-weight: 600; color: var(--ink); }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; vertical-align: baseline; }
  .hint { position: fixed; bottom: 12px; left: 0; right: 0; text-align: center;
    font-size: 12px; color: var(--ink2); z-index: 3; pointer-events: none; }
  canvas { display: block; width: 100vw; height: 100vh; }
  #tip { position: fixed; z-index: 4; max-width: 280px; padding: 9px 12px; border-radius: 7px;
    background: #1C222A; border: 1px solid #2E353E; color: var(--ink); font-size: 13px;
    line-height: 1.4; box-shadow: 0 6px 20px rgba(0,0,0,.4); pointer-events: none; opacity: 0;
    transition: opacity .12s; }
  #tip .t { font-weight: 600; margin-bottom: 3px; }
  #tip .m { color: var(--ink2); font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>__CHAPTER_TITLE__</h1>
  <p class="sub">__SUBTITLE__ &middot; drag a dot to move it</p>
  <div class="legend">
    <span><span class="dot" style="background:#ECEAE2"></span><b>chapter</b></span>
    <span><span class="dot" style="background:#6FA8C7"></span>source</span>
    <span><span class="dot" style="background:#23B79C"></span>kept connection</span>
    <span><span class="dot" style="background:#D2A24A"></span>undecided</span>
    <span><span class="dot" style="background:#5E666E"></span>dropped</span>
  </div>
</header>
<canvas id="c"></canvas>
<div class="hint">every quotation behind these connections was machine-checked against its source</div>
<div id="tip"></div>
<script type="application/json" id="gdata">/*__DATA__*/</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("gdata").textContent);
  var COL = { hub:"#ECEAE2", paper:"#6FA8C7", keep:"#23B79C", cand:"#D2A24A", drop:"#5E666E" };
  function nodeColor(n){ return n.type==="conn" ? COL[n.status==="keep"?"keep":n.status==="drop"?"drop":"cand"] : COL[n.type]; }

  var canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
  var tip = document.getElementById("tip");
  var W = 0, H = 0, dpr = 1;
  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W*dpr; canvas.height = H*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  resize(); window.addEventListener("resize", resize);

  var nodes = data.nodes, byId = {};
  nodes.forEach(function(n,i){
    var a = (i/nodes.length)*Math.PI*2;
    n.x = W/2 + Math.cos(a)*180*(0.4+Math.random()*0.6);
    n.y = H/2 + Math.sin(a)*180*(0.4+Math.random()*0.6);
    n.vx = 0; n.vy = 0; n.r = n.size;
    byId[n.id] = n;
  });
  var edges = data.edges.filter(function(e){ return byId[e.s] && byId[e.t]; });
  var deg = {}; edges.forEach(function(e){ deg[e.s]=(deg[e.s]||0)+1; deg[e.t]=(deg[e.t]||0)+1; });
  var neighbors = {}; nodes.forEach(function(n){ neighbors[n.id]=new Set(); });
  edges.forEach(function(e){ neighbors[e.s].add(e.t); neighbors[e.t].add(e.s); });

  function step() {
    var cx = W/2, cy = H/2;
    for (var i=0;i<nodes.length;i++){ nodes[i].fx=0; nodes[i].fy=0; }
    // repulsion
    for (var a=0;a<nodes.length;a++){
      for (var b=a+1;b<nodes.length;b++){
        var na=nodes[a], nb=nodes[b];
        var dx=na.x-nb.x, dy=na.y-nb.y, d2=dx*dx+dy*dy+0.01;
        var d=Math.sqrt(d2), f=2600/d2;
        var ux=dx/d, uy=dy/d;
        na.fx+=ux*f; na.fy+=uy*f; nb.fx-=ux*f; nb.fy-=uy*f;
      }
    }
    // springs
    edges.forEach(function(e){
      var s=byId[e.s], t=byId[e.t];
      var dx=t.x-s.x, dy=t.y-s.y, d=Math.sqrt(dx*dx+dy*dy)+0.01;
      var L=(s.type==="hub"||t.type==="hub")?150:110;
      var f=(d-L)*0.02, ux=dx/d, uy=dy/d;
      s.fx+=ux*f; s.fy+=uy*f; t.fx-=ux*f; t.fy-=uy*f;
    });
    for (var k=0;k<nodes.length;k++){
      var n=nodes[k];
      if (n===dragging) continue;
      n.fx += (cx-n.x)*0.012; n.fy += (cy-n.y)*0.012;
      n.vx=(n.vx+n.fx)*0.85; n.vy=(n.vy+n.fy)*0.85;
      n.x+=n.vx; n.y+=n.vy;
    }
  }

  function draw() {
    ctx.clearRect(0,0,W,H);
    var hi = hover ? neighbors[hover.id] : null;
    edges.forEach(function(e){
      var s=byId[e.s], t=byId[e.t], drop=e.status==="drop";
      var active = !hover || e.s===hover.id || e.t===hover.id;
      ctx.beginPath(); ctx.moveTo(s.x,s.y); ctx.lineTo(t.x,t.y);
      ctx.strokeStyle = "rgba(150,164,178," + (drop?0.09:0.20)*(active?1:0.25) + ")";
      ctx.lineWidth = drop?1:1.4;
      if (drop) ctx.setLineDash([4,4]); else ctx.setLineDash([]);
      ctx.stroke(); ctx.setLineDash([]);
    });
    nodes.forEach(function(n){
      var dim = hover && n!==hover && !(hi&&hi.has(n.id));
      ctx.globalAlpha = dim?0.35:1;
      var faded = n.type==="conn" && n.status==="drop";
      if (faded) ctx.globalAlpha *= 0.6;
      ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,Math.PI*2);
      ctx.fillStyle = nodeColor(n); ctx.fill();
      if (n===hover){ ctx.lineWidth=2; ctx.strokeStyle="rgba(255,255,255,.7)"; ctx.stroke(); }
      ctx.globalAlpha = dim?0.4:0.92;
      ctx.fillStyle = "#C9CEC6";
      ctx.font = (n.type==="hub"?"600 13px":"12px")+" system-ui, sans-serif";
      ctx.textAlign="center"; ctx.textBaseline="top";
      var lab=n.label.length>26?n.label.slice(0,25)+"…":n.label;
      ctx.fillText(lab, n.x, n.y+n.r+4);
      ctx.globalAlpha=1;
    });
  }

  var hover=null, dragging=null, down=false, px=0, py=0;
  function pick(x,y){
    var best=null, bd=1e9;
    nodes.forEach(function(n){ var d=Math.hypot(n.x-x,n.y-y); if(d<n.r+8 && d<bd){bd=d;best=n;} });
    return best;
  }
  function pos(ev){ var t=ev.touches?ev.touches[0]:ev; return [t.clientX,t.clientY]; }
  canvas.addEventListener("mousemove", function(ev){
    var p=pos(ev);
    if (dragging){ dragging.x=p[0]; dragging.y=p[1]; dragging.vx=0; dragging.vy=0; return; }
    hover = pick(p[0],p[1]);
    canvas.style.cursor = hover?"pointer":"default";
    if (hover){
      var m = hover.type==="conn" ? (hover.status.toUpperCase()+" · "+hover.ev+" verified quotation"+(hover.ev===1?"":"s"))
            : hover.type==="paper" ? (hover.sub||"source") : "the chapter";
      tip.innerHTML = '<div class="t"></div><div class="m"></div>';
      tip.querySelector(".t").textContent = hover.label;
      tip.querySelector(".m").textContent = m;
      tip.style.left = Math.min(p[0]+14, W-292)+"px";
      tip.style.top = (p[1]+14)+"px"; tip.style.opacity=1;
    } else tip.style.opacity=0;
  });
  canvas.addEventListener("mousedown", function(ev){ var p=pos(ev); dragging=pick(p[0],p[1]); down=true; });
  window.addEventListener("mouseup", function(){ dragging=null; down=false; });

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce){ for (var i=0;i<450;i++) step(); draw(); }
  else (function loop(){ step(); draw(); requestAnimationFrame(loop); })();
})();
</script>
</body>
</html>
"""
