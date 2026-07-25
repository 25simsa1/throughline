#!/usr/bin/env python3
"""
Throughline desktop UI. A tiny local web app so the scholar can click through the
pipeline (ingest, extract, connect, review, draft) instead of typing menu numbers.

Stdlib only, so it packages without pip. It shells out to the repo's own .venv python
running throughline.py, streams the output live, and turns the keep/drop review into
buttons that write back to report.md.

Run:  .venv/bin/python app/server.py     (or just double-click Throughline.app)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent  # server.py, ui.html, projects.json live together here


def _find_repo() -> Path:
    # the dir that holds throughline.py, .venv, and the projects folder. in the
    # repo that is HERE's parent, in her packaged copy it is HERE itself.
    for cand in [HERE, *HERE.parents]:
        if (cand / "throughline.py").exists():
            return cand
    return HERE


REPO = _find_repo()
APP = HERE
CHAPTERS = REPO / "projects"
STAGES = ("ingest", "extract", "connect", "draft", "verify")
ALLOWED_EXT = {".md", ".txt", ".pdf", ".epub", ".jpg", ".jpeg", ".png", ".tiff"}
HOST, PORT = "127.0.0.1", 8756

AUTO_THESIS = (
    "# Chapter thesis\n\n"
    "Surface the strongest and most surprising connections across these sources. "
    "Prefer connections that span more than one source, that are directly supported by "
    "quotable evidence, and that a careful reader would find non-obvious. There is no "
    "predetermined argument here; find what the sources themselves make possible.\n"
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")[:60]


def _wrap_thesis(text: str) -> str:
    text = text.strip()
    if text.startswith("#"):
        return text + "\n"
    return "# Chapter thesis\n\n" + text + "\n"


def parse_multipart(body: bytes, boundary: bytes):
    """Minimal multipart/form-data parser (cgi is gone in 3.13). Returns (fields, files)."""
    fields: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers = raw_headers.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]*)"', headers)
        file_m = re.search(r'filename="([^"]*)"', headers)
        if not name_m:
            continue
        if file_m and file_m.group(1):
            files.append((name_m.group(1), file_m.group(1), content))
        else:
            fields[name_m.group(1)] = content.decode("utf-8", "replace").strip()
    return fields, files

# The interpreter that actually has the deps (fitz, etc.). Fall back to python3.
def _python() -> str:
    for cand in (REPO / ".venv/bin/python", REPO / "venv/bin/python"):
        if cand.exists():
            return str(cand)
    return "python3"

PYTHON = _python()


# On Apple Silicon a server launched under Rosetta runs x86_64, and then its
# child python is x86_64 too, so the arm64 PyMuPDF library refuses to load and
# ingest dies. Probe once at startup: if the interpreter can't import fitz as-is
# but can under `arch -arm64`, prefix every child with that. No-op everywhere the
# import already works (clean installs, Intel Macs).
def _spawn_cmd() -> list[str]:
    def can(prefix: list[str]) -> bool:
        try:
            return subprocess.run(prefix + [PYTHON, "-c", "import fitz"],
                                  capture_output=True, timeout=120).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    if can([]):
        return [PYTHON]
    if can(["arch", "-arm64"]):
        print("(forcing arm64 for the PDF library)")
        return ["arch", "-arm64", PYTHON]
    return [PYTHON]  # give up; the real error will surface in the job log


RUN = _spawn_cmd()

# ---- background jobs ---------------------------------------------------------
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_seq = 0


def start_job(chapter: str, stages: list[str]) -> str:
    """Run one or more throughline stages in sequence as a single streamed job."""
    global _seq
    with _jobs_lock:
        _seq += 1
        jid = f"j{_seq}"
        _jobs[jid] = {"lines": [f"$ {' -> '.join(stages)}  ({chapter})", ""],
                      "running": True, "returncode": None}

    def run():
        rc = 0
        try:
            for stage in stages:
                with _jobs_lock:
                    _jobs[jid]["lines"].append(f"$ throughline {stage} {chapter}")
                proc = subprocess.Popen(RUN + ["throughline.py", stage, chapter],
                                        cwd=str(REPO), stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:  # type: ignore[union-attr]
                    with _jobs_lock:
                        _jobs[jid]["lines"].append(line.rstrip("\n"))
                proc.wait()
                rc = proc.returncode
                with _jobs_lock:
                    _jobs[jid]["lines"].append(f"[{stage} exit {rc}]")
                    _jobs[jid]["lines"].append("")
                if rc != 0:
                    break
        except Exception as e:  # noqa: BLE001
            rc = -1
            with _jobs_lock:
                _jobs[jid]["lines"].append(f"[error launching job: {e}]")
        with _jobs_lock:
            _jobs[jid]["running"] = False
            _jobs[jid]["returncode"] = rc
            _jobs[jid]["lines"].append("[all steps done]" if rc == 0 else "[stopped, a step failed]")

    threading.Thread(target=run, daemon=True).start()
    return jid


# ---- chapter / report inspection --------------------------------------------
def list_chapters() -> list[str]:
    if not CHAPTERS.exists():
        return []
    return sorted(p.name for p in CHAPTERS.iterdir()
                  if p.is_dir() and (p / "thesis.md").exists())


def load_meta() -> dict:
    p = APP / "projects.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def pretty(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def chapters_meta() -> list[dict]:
    """Chapters enriched with friendly title / kind / note, sorted main first."""
    meta = load_meta()
    rank = {"main": 0, "variant": 1, "example": 2}
    out = []
    for name in list_chapters():
        m = meta.get(name, {})
        out.append({"name": name, "title": m.get("title") or pretty(name),
                    "kind": m.get("kind", "main"), "note": m.get("note", "")})
    out.sort(key=lambda c: (rank.get(c["kind"], 0), c["title"].lower()))
    return out


def _decisions_from_md(ch: Path) -> dict[str, dict]:
    """Map connection id -> {'decision':..., 'note':...} parsed from report.md."""
    md = ch / "report.md"
    out: dict[str, dict] = {}
    if not md.exists():
        return out
    cur = None
    for line in md.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s+(C\w+)\.", line.strip())
        if h:
            cur = h.group(1)
            out.setdefault(cur, {"decision": "candidate", "note": ""})
            continue
        if cur:
            d = re.match(r"^Decision:\s*(\w+)", line.strip())
            if d:
                out[cur]["decision"] = d.group(1).lower()
            n = re.match(r"^Note:\s*(.*)", line.strip())
            if n:
                out[cur]["note"] = n.group(1).strip()
    return out


def chapter_detail(name: str) -> dict:
    ch = CHAPTERS / name
    store = ch / "store"
    sources = sorted(p.name for p in (ch / "sources").glob("*") if p.is_file()) if (ch / "sources").exists() else []
    units = sorted(p.name for p in store.glob("*.units.json")) if store.exists() else []
    report_json = ch / "report.json"
    drafts = sorted(p.stem for p in (ch / "drafts").glob("*.md")) if (ch / "drafts").exists() else []
    decisions = _decisions_from_md(ch)

    connections = []
    if report_json.exists():
        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
            for c in data.get("connections", []):
                cid = c.get("id", "")
                dec = decisions.get(cid, {"decision": "candidate", "note": ""})
                connections.append({
                    "id": cid,
                    "move": c.get("move", ""),
                    "interpretation": c.get("interpretation", ""),
                    "sources": c.get("sources_involved", []),
                    "tensions": c.get("tensions", ""),
                    "novelty": c.get("novelty"),
                    "confidence": c.get("confidence"),
                    "evidence": c.get("evidence", []),
                    "decision": dec["decision"],
                    "note": dec["note"],
                })
        except Exception as e:  # noqa: BLE001
            connections = [{"id": "?", "move": f"(could not read report.json: {e})",
                            "interpretation": "", "sources": [], "tensions": "",
                            "evidence": [], "decision": "candidate", "note": ""}]

    n_keep = sum(1 for c in connections if c["decision"] == "keep")
    n_drop = sum(1 for c in connections if c["decision"] == "drop")
    stages = {
        "ingest": (store / "segments.json").exists(),
        "extract": len(units) > 0,
        "connect": report_json.exists(),
        "select": (n_keep + n_drop) > 0,
        "draft": len(drafts) > 0,
    }
    m = load_meta().get(name, {})
    return {
        "name": name,
        "title": m.get("title") or pretty(name),
        "kind": m.get("kind", "main"),
        "note": m.get("note", ""),
        "thesis": (ch / "thesis.md").read_text(encoding="utf-8") if (ch / "thesis.md").exists() else "",
        "sources": sources, "units": units, "drafts": drafts,
        "stages": stages,
        "counts": {"sources": len(sources), "units": len(units),
                   "connections": len(connections), "keep": n_keep, "drop": n_drop},
        "connections": connections,
    }


def set_decision(name: str, cid: str, decision: str, note: str) -> bool:
    """Rewrite the Decision (and Note) line for one connection in report.md."""
    if decision not in ("keep", "drop", "candidate") or not re.fullmatch(r"C\w+", cid):
        return False
    md = (CHAPTERS / name / "report.md")
    if not md.exists():
        return False
    lines = md.read_text(encoding="utf-8").splitlines()
    out, cur, wrote = [], None, False
    i = 0
    while i < len(lines):
        line = lines[i]
        h = re.match(r"^##\s+(C\w+)\.", line.strip())
        if h:
            cur = h.group(1)
        if cur == cid and re.match(r"^Decision:\s*", line.strip()):
            out.append(f"Decision: {decision}")
            wrote = True
            # absorb an existing Note line that immediately follows
            if i + 1 < len(lines) and re.match(r"^Note:\s*", lines[i + 1].strip()):
                i += 1
            if note.strip():
                out.append(f"Note: {note.strip()}")
            i += 1
            continue
        out.append(line)
        i += 1
    if not wrote:
        return False
    md.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


# ---- http --------------------------------------------------------------------
class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            html = (APP / "ui.html").read_text(encoding="utf-8")
            return self._send(200, html, "text/html; charset=utf-8")
        if u.path == "/api/chapters":
            return self._json({"chapters": chapters_meta(), "python": PYTHON,
                               "python_ok": Path(PYTHON).exists() or PYTHON == "python3"})
        if u.path == "/api/chapter":
            name = q.get("name", [""])[0]
            if name not in list_chapters():
                return self._json({"error": "unknown chapter"}, 404)
            return self._json(chapter_detail(name))
        if u.path == "/api/job":
            jid = q.get("id", [""])[0]
            with _jobs_lock:
                j = _jobs.get(jid)
                if not j:
                    return self._json({"error": "no such job"}, 404)
                return self._json({"lines": j["lines"], "running": j["running"],
                                   "returncode": j["returncode"]})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        if u.path == "/api/upload":
            m = re.search(r"boundary=(.*)", ctype)
            if not m:
                return self._json({"error": "no multipart boundary"}, 400)
            fields, files = parse_multipart(raw, m.group(1).strip().strip('"').encode())
            chapter = fields.get("chapter", "")
            if chapter not in list_chapters():
                return self._json({"error": "unknown chapter"}, 404)
            srcdir = CHAPTERS / chapter / "sources"
            srcdir.mkdir(parents=True, exist_ok=True)
            saved, rejected = [], []
            for _n, filename, content in files:
                fn = Path(filename).name
                if not fn or Path(fn).suffix.lower() not in ALLOWED_EXT:
                    rejected.append(fn)
                    continue
                (srcdir / fn).write_bytes(content)
                saved.append(fn)
            return self._json({"saved": saved, "rejected": rejected})

        body = json.loads(raw or b"{}")
        if u.path == "/api/new":
            name = _slug(body.get("name", ""))
            if not name:
                return self._json({"error": "please enter a project name"}, 400)
            if name in list_chapters():
                return self._json({"error": "a project with that name already exists"}, 400)
            r = subprocess.run(RUN + ["throughline.py", "new", name],
                               cwd=str(REPO), capture_output=True, text=True)
            if r.returncode != 0:
                detail = (r.stdout + r.stderr).strip() or "unknown error"
                return self._json({"error": "could not create project: " + detail[-400:]}, 500)
            return self._json({"name": name, "ok": True})
        if u.path == "/api/criteria":
            ch = body.get("chapter", "")
            text = body.get("text", "")
            auto = bool(body.get("auto")) or not text.strip()
            if ch not in list_chapters():
                return self._json({"error": "unknown chapter"}, 404)
            (CHAPTERS / ch / "thesis.md").write_text(
                AUTO_THESIS if auto else _wrap_thesis(text), encoding="utf-8")
            return self._json({"ok": True, "auto": auto})
        if u.path == "/api/run":
            ch, stage = body.get("chapter"), body.get("stage")
            if ch not in list_chapters() or stage not in STAGES:
                return self._json({"error": "bad chapter or stage"}, 400)
            return self._json({"job_id": start_job(ch, [stage])})
        if u.path == "/api/run_all":
            ch = body.get("chapter")
            if ch not in list_chapters():
                return self._json({"error": "unknown chapter"}, 400)
            return self._json({"job_id": start_job(ch, ["ingest", "extract", "connect"])})
        if u.path == "/api/decision":
            ok = set_decision(body.get("chapter", ""), body.get("id", ""),
                              body.get("decision", ""), body.get("note", ""))
            return self._json({"ok": ok}, 200 if ok else 400)
        if u.path == "/api/delete":
            name = body.get("name", "")
            if name not in list_chapters():
                return self._json({"error": "unknown project"}, 404)
            shutil.rmtree(CHAPTERS / name, ignore_errors=True)
            return self._json({"ok": True})
        if u.path == "/api/removefile":
            ch = body.get("chapter", "")
            fn = Path(body.get("file", "")).name  # basename only, no path traversal
            if ch not in list_chapters():
                return self._json({"error": "unknown project"}, 404)
            f = CHAPTERS / ch / "sources" / fn
            if fn and f.is_file():
                f.unlink()
                return self._json({"ok": True})
            return self._json({"error": "no such file"}, 404)
        return self._json({"error": "not found"}, 404)


def main():
    url = f"http://{HOST}:{PORT}/"
    print(f"Throughline UI running at {url}")
    print(f"(using interpreter {PYTHON})")
    print("Close this window to stop.")
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98):  # already in use = already running
            print("Throughline is already open. Opening the existing window.")
            webbrowser.open(url)
            return
        raise
    try:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nThroughline stopped.")


if __name__ == "__main__":
    main()
