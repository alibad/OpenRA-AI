"""Local, player-controlled feedback bundles for live OpenRA sessions."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from uuid import uuid4


_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_CATEGORIES = ("bug", "voice", "ai", "balance", "visual", "other")


def default_feedback_dir() -> Path:
    configured = os.environ.get("OPENRA_AI_FEEDBACK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "OpenRA-AI" / "Feedback"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OpenRA AI" / "Feedback"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "openra-ai" / "feedback"


def _safe_id(feedback_id: str) -> str:
    if not _ID_PATTERN.fullmatch(feedback_id):
        raise ValueError("invalid feedback id")
    return feedback_id


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class FeedbackStore:
    """Persist feedback drafts outside the repository and never overwrite one."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_feedback_dir()).resolve()

    def _directory(self, feedback_id: str) -> Path:
        directory = (self.root / _safe_id(feedback_id)).resolve()
        if directory.parent != self.root:
            raise ValueError("invalid feedback path")
        return directory

    def capture(
        self,
        *,
        frame_png: bytes,
        frame: dict[str, Any],
        snapshot: dict[str, Any],
        companion: dict[str, Any],
    ) -> dict[str, Any]:
        if not frame_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("OpenRA returned an invalid screenshot")
        if len(frame_png) > 20_000_000:
            raise ValueError("OpenRA screenshot is unexpectedly large")

        self.root.mkdir(parents=True, exist_ok=True)
        feedback_id = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid4().hex[:8]}"
        directory = self._directory(feedback_id)
        directory.mkdir()
        (directory / "screenshot.png").write_bytes(frame_png)
        record = {
            "feedback_id": feedback_id,
            "created_at": _utc_now(),
            "status": "draft",
            "category": "bug",
            "title": "",
            "description": "",
            "frame": frame,
            "snapshot": snapshot,
            "companion": companion,
            "screenshot": "screenshot.png",
        }
        self._write(directory, record)
        return record

    def get(self, feedback_id: str) -> dict[str, Any]:
        directory = self._directory(feedback_id)
        path = directory / "feedback.json"
        if not path.is_file():
            raise FileNotFoundError(feedback_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, feedback_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.get(feedback_id)
        title = str(payload.get("title", record.get("title", ""))).strip()
        description = str(payload.get("description", record.get("description", ""))).strip()
        category = str(payload.get("category", record.get("category", "bug"))).strip().lower()
        if len(title) > 160:
            raise ValueError("feedback title is too long")
        if len(description) > 20_000:
            raise ValueError("feedback description is too long")
        if category not in _CATEGORIES:
            raise ValueError("unknown feedback category")
        record.update({
            "title": title,
            "description": description,
            "category": category,
            "status": "saved",
            "updated_at": _utc_now(),
        })
        self._write(self._directory(feedback_id), record)
        return record

    def screenshot_path(self, feedback_id: str) -> Path:
        record = self.get(feedback_id)
        path = (self._directory(feedback_id) / str(record.get("screenshot", "screenshot.png"))).resolve()
        if path.parent != self._directory(feedback_id) or path.suffix.lower() != ".png" or not path.is_file():
            raise FileNotFoundError(feedback_id)
        return path

    @staticmethod
    def _write(directory: Path, record: dict[str, Any]) -> None:
        temporary = directory / ".feedback.json.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(directory / "feedback.json")


def feedback_page(feedback_id: str, record: dict[str, Any]) -> str:
    """Render a deliberately local feedback form with explicit external sharing."""
    safe_id = html.escape(_safe_id(feedback_id), quote=True)
    category_options = "".join(
        f'<option value="{category}"{(" selected" if record.get("category") == category else "")}>{category.title()}</option>'
        for category in _CATEGORIES
    )
    initial = json.dumps({
        "feedback_id": feedback_id,
        "title": record.get("title", ""),
        "description": record.get("description", ""),
        "category": record.get("category", "bug"),
        "created_at": record.get("created_at", ""),
        "frame": record.get("frame", {}),
        "snapshot": record.get("snapshot", {}),
    }).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenRA AI — Feedback</title>
<style>
:root{{--bg:#070908;--surface:#101610;--line:#2a392d;--text:#f2f5ef;--muted:#9aa79c;--green:#86f59a;--amber:#f4c95d;--red:#ff705f}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 78% -5%,#1a3b22,transparent 34%),var(--bg);color:var(--text);font:14px/1.5 Inter,system-ui,sans-serif}}
main{{width:min(1060px,100%);margin:0 auto;padding:34px 22px 70px}}.eyebrow{{color:var(--green);font:700 10px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase}}
h1{{font-size:clamp(28px,5vw,48px);letter-spacing:-.04em;line-height:1.05;margin:9px 0 10px}}p{{color:var(--muted)}}.lede{{font-size:16px;max-width:720px}}
.grid{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:16px;margin-top:24px}}.card{{border:1px solid var(--line);border-radius:12px;background:rgba(16,22,16,.92);padding:18px;box-shadow:0 20px 60px rgba(0,0,0,.24)}}
.frame{{background:#050706;border:1px solid var(--line);border-radius:8px;overflow:hidden;min-height:260px;display:grid;place-items:center}}.frame img{{width:100%;max-height:520px;object-fit:contain;image-rendering:pixelated}}
.meta{{font:10px ui-monospace,monospace;color:var(--muted);margin-top:9px}}label{{display:grid;gap:7px;margin-bottom:14px;color:var(--muted);font:700 10px ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}}input,select,textarea{{width:100%;border:1px solid #405444;border-radius:7px;background:#090d0a;color:var(--text);padding:10px;font:14px/1.45 Inter,system-ui,sans-serif}}textarea{{min-height:180px;resize:vertical}}input:focus,select:focus,textarea:focus{{outline:1px solid var(--green);border-color:var(--green)}}.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}}button,.button{{border:1px solid #4b654f;border-radius:7px;background:#172219;color:var(--text);padding:10px 13px;font-weight:750;cursor:pointer;text-decoration:none}}button.primary{{background:var(--green);border-color:var(--green);color:#071008}}button:hover,.button:hover{{filter:brightness(1.15)}}button:disabled{{opacity:.55;cursor:wait}}.notice{{border-left:2px solid var(--amber);padding:9px 11px;background:#1b1910;color:#d4c997;font-size:12px;margin-top:16px}}.status{{min-height:22px;color:var(--green);font-size:12px;margin-top:12px}}details{{margin-top:15px;border:1px solid var(--line);border-radius:7px}}summary{{padding:10px;cursor:pointer;color:var(--muted);font-weight:700}}pre{{white-space:pre-wrap;max-height:280px;overflow:auto;padding:10px;border-top:1px solid var(--line);color:#aebcaf;font:10px/1.5 ui-monospace,monospace}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}main{{padding:24px 14px 50px}}}}
</style></head><body><main>
<div class="eyebrow">OPENRA AI / PLAYER FEEDBACK</div><h1>Report what happened.</h1>
<p class="lede">This draft already contains the exact fog-respecting game viewport and live state captured when you clicked REPORT. Add the human context only you can see.</p>
<div class="grid"><section class="card"><div class="eyebrow">CAPTURED EVIDENCE</div><div class="frame"><img src="/v1/feedback/{safe_id}/screenshot" alt="OpenRA game viewport captured with fog of war"></div><div class="meta">DRAFT {safe_id} // {html.escape(str(record.get('created_at', '')))} // {html.escape(str(record.get('frame', {}).get('scope', '')))}</div><details><summary>Show captured state</summary><pre id="state"></pre></details></section>
<section class="card"><div class="eyebrow">YOUR REPORT</div><form id="form"><label>Category<select id="category">{category_options}</select></label><label>Short title<input id="title" maxlength="160" placeholder="e.g. voice input stopped after opening the map"></label><label>What happened?<textarea id="description" maxlength="20000" placeholder="What did you expect, and what happened instead?"></textarea></label><div class="actions"><button class="primary" id="save" type="submit">SAVE FEEDBACK</button><button id="github" type="button">OPEN GITHUB DRAFT</button></div><div class="notice">Saving stays on this computer. “Open GitHub draft” prepares a browser tab; review the report and attach the bundle yourself before submitting.</div><div class="status" id="status" role="status"></div></form></section></div>
<script>
const draft={initial}; const id={json.dumps(feedback_id)}; const $=s=>document.querySelector(s);
$('#title').value=draft.title||''; $('#description').value=draft.description||''; $('#category').value=draft.category||'bug'; $('#state').textContent=JSON.stringify({{frame:draft.frame,snapshot:draft.snapshot}},null,2);
$('#form').addEventListener('submit',async event=>{{event.preventDefault();$('#save').disabled=true;$('#status').textContent='Saving locally...';try{{const response=await fetch('/v1/feedback/'+encodeURIComponent(id),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{title:$('#title').value,description:$('#description').value,category:$('#category').value}})}});const value=await response.json();if(!response.ok)throw new Error(value.detail||value.error||'Save failed');$('#status').textContent='Saved locally. The evidence bundle is ready.'}}catch(error){{$('#status').textContent=error.message}}finally{{$('#save').disabled=false}}}});
$('#github').addEventListener('click',()=>{{const title=$('#title').value.trim()||'OpenRA AI feedback';const body=[`Category: ${{$('#category').value}}`,`Draft: ${{id}}`,'','What happened:', $('#description').value.trim()||'(add details before submitting)','',`Captured evidence: http://127.0.0.1:${{location.port}}/feedback/${{encodeURIComponent(id)}}`].join('\\n');const url='https://github.com/alibad/OpenRA-AI/issues/new?title='+encodeURIComponent(title)+'&body='+encodeURIComponent(body);window.open(url,'_blank','noopener,noreferrer')}});
</script></main></body></html>"""
