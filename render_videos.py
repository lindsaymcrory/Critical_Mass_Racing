#!/usr/bin/env python3
"""Renders the Videos page: a list of race-footage links (YouTube, etc.)
with notes, newest first. Reads video_log.json (hand-edited directly, like
boat_setup_log.json), so this page never needs a live database connection."""
import html as html_mod
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent
LOG_PATH = ROOT / "video_log.json"

PAGE_TEMPLATE = """<title>Videos — Critical Mass Racing</title>
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --grid-strong: #2a4e59; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --mark: #f5b942;
    --hair: #24444f; --radius: 3px;
  }
  :root[data-theme="light"] {
    --ink: #eef3f1; --panel: #ffffff; --panel-2: #f4f8f7;
    --grid: #d7e2df; --grid-strong: #c3d3cf; --paper: #10262c;
    --dim: #4c6b71; --dim-2: #7d9ba1; --hair: #d2ddda;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: var(--ink); color: var(--paper);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  a { color: inherit; }
  a.back { text-decoration: none; color: var(--dim); font-size: 12px; }
  a.back:hover { color: var(--paper); }

  header {
    display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
    padding: 16px 24px; border-bottom: 1px solid var(--hair); background: var(--panel-2);
    position: sticky; top: 0; z-index: 30;
  }
  .brand { display: flex; flex-direction: column; gap: 2px; }
  .brand .title { font-size: 19px; font-weight: 700; letter-spacing: 0.02em; }
  .brand .sub { font-size: 13px; color: var(--dim); }
  .intro { padding: 16px 24px 4px; font-size: 15px; color: var(--dim); max-width: 820px; }

  .video-list { padding: 12px 24px 40px; max-width: 900px; display: flex; flex-direction: column; gap: 20px; }
  .video-card { background: var(--panel); border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden; }
  .video-embed { position: relative; padding-bottom: 56.25%; height: 0; background: var(--panel-2); }
  .video-embed iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }
  .video-meta { padding: 14px 18px; }
  .video-date { font-size: 12.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--mark); }
  .video-note { font-size: 14.5px; margin-top: 4px; line-height: 1.5; }
  .video-link { font-size: 12px; color: var(--dim); margin-top: 6px; display: block; }
  .video-link:hover { color: var(--paper); }
  .empty { padding: 24px; color: var(--dim); font-style: italic; }

  footer { padding: 12px 24px; background: var(--panel-2); font-size: 12px; color: var(--dim-2); }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--hair); border-radius: 5px; }
</style>

<header>
  <a class="back" href="/">&larr; All races</a>
  <div class="brand">
    <div class="title">Videos</div>
    <div class="sub">Race Footage</div>
  </div>
</header>

<p class="intro">Race footage with the live performance overlay, newest first.</p>

<div class="video-list">__VIDEO_CARDS__</div>
"""


def _youtube_embed_url(url):
    """Returns a youtube.com/embed/<id> URL for youtu.be/<id> and
    youtube.com/watch?v=<id> links, or None if the video ID can't be found
    (falls back to a plain link instead of a broken embed)."""
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        video_id = parsed.path.lstrip("/")
    elif parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    else:
        video_id = None
    return f"https://www.youtube.com/embed/{video_id}" if video_id else None


def _video_card_html(entry):
    date_str = datetime.fromisoformat(entry["date"]).strftime("%b %-d, %Y")
    note = html_mod.escape(entry["note"])
    url = html_mod.escape(entry["url"])
    embed_url = _youtube_embed_url(entry["url"])

    embed_html = (
        f'<div class="video-embed"><iframe src="{html_mod.escape(embed_url)}" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
        f'allowfullscreen loading="lazy"></iframe></div>'
        if embed_url else ""
    )
    return f"""<div class="video-card">
  {embed_html}
  <div class="video-meta">
    <div class="video-date">{date_str}</div>
    <div class="video-note">{note}</div>
    <a class="video-link" href="{url}" target="_blank" rel="noopener">{url}</a>
  </div>
</div>"""


def render_page():
    log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {"entries": []}
    entries = sorted(log["entries"], key=lambda e: e["date"], reverse=True)
    cards_html = "".join(_video_card_html(e) for e in entries) if entries else \
        '<div class="empty">No videos yet.</div>'
    return PAGE_TEMPLATE.replace("__VIDEO_CARDS__", cards_html)


if __name__ == "__main__":
    print(render_page()[:2000])
