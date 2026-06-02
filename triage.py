#!/usr/bin/env python3
"""Module 2 — Triage Web App."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    from flask import Flask, jsonify, request, send_from_directory, send_file
except ImportError:
    print("ERROR: Flask not found. Install it with:")
    print("  pip install flask")
    sys.exit(1)

BASE = Path(__file__).parent
TRIAGE_DIR = BASE / "input" / "triage"
TIKTOKS_DIR = BASE / "input" / "tiktoks"
SKIPPED_DIR = BASE / "input" / "skipped"
TRIAGE_JSON = BASE / "triage_data" / "triage.json"

app = Flask(__name__)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
shutdown_event = threading.Event()


def get_video_duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if "duration" in stream:
                return float(stream["duration"])
    except Exception:
        pass
    return 0.0


def load_triage():
    if TRIAGE_JSON.exists():
        return json.loads(TRIAGE_JSON.read_text())
    return {}


def save_triage(data):
    TRIAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRIAGE_JSON.write_text(json.dumps(data, indent=2))


def get_clips():
    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)
    clips = []
    for f in sorted(TRIAGE_DIR.iterdir()):
        if f.suffix.lower() in VIDEO_EXTENSIONS:
            clips.append(f.name)
    return clips


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>React Pipeline — Triage</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #111; color: #eee; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
  header { position: sticky; top: 0; background: #1a1a1a; border-bottom: 1px solid #333; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; z-index: 100; }
  header h1 { font-size: 18px; font-weight: 600; color: #fff; }
  #progress { font-size: 14px; color: #aaa; }
  #controls { display: flex; gap: 10px; }
  .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; transition: opacity .15s; }
  .btn:hover { opacity: .8; }
  .btn-primary { background: #2563eb; color: #fff; }
  .btn-danger { background: #dc2626; color: #fff; }
  .btn-success { background: #16a34a; color: #fff; }
  .btn-outline { background: transparent; border: 1px solid #555; color: #ccc; }
  #filters { padding: 12px 24px; background: #161616; border-bottom: 1px solid #2a2a2a; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  #filters label { font-size: 13px; color: #aaa; }
  #filters select { background: #222; color: #eee; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; font-size: 13px; }
  #filters input[type=checkbox] { accent-color: #2563eb; }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; padding: 24px; }
  .card { background: #1c1c1c; border: 2px solid #2a2a2a; border-radius: 10px; overflow: hidden; transition: border-color .15s; }
  .card.kept { border-color: #16a34a; }
  .card.skipped { border-color: #dc2626; opacity: .6; }
  .card.focused { outline: 2px solid #2563eb; outline-offset: 2px; }
  .card video { width: 100%; display: block; max-height: 300px; background: #000; object-fit: contain; }
  .card-body { padding: 12px; }
  .card-name { font-size: 12px; color: #999; margin-bottom: 6px; word-break: break-all; }
  .card-duration { font-size: 12px; color: #666; margin-bottom: 10px; }
  .card-actions { display: flex; gap: 8px; margin-bottom: 10px; }
  .card-actions .btn { flex: 1; padding: 8px; font-size: 13px; }
  .card textarea { width: 100%; background: #111; border: 1px solid #333; color: #ccc; border-radius: 4px; padding: 6px 8px; font-size: 12px; resize: vertical; min-height: 52px; }
  .card textarea:focus { outline: none; border-color: #555; }
  #toast { position: fixed; bottom: 24px; right: 24px; background: #16a34a; color: #fff; padding: 10px 18px; border-radius: 6px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity .3s; }
  #toast.show { opacity: 1; }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 6px; }
  .badge-kept { background: #14532d; color: #4ade80; }
  .badge-skipped { background: #7f1d1d; color: #f87171; }
</style>
</head>
<body>
<header>
  <h1>Triage <span id="progress-badge"></span></h1>
  <div id="controls">
    <select id="sort-select" class="btn btn-outline">
      <option value="name">Sort: Name</option>
      <option value="dur-asc">Sort: Shortest first</option>
      <option value="dur-desc">Sort: Longest first</option>
    </select>
    <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#aaa;cursor:pointer;">
      <input type="checkbox" id="unreviewed-only"> Unreviewed only
    </label>
    <button class="btn btn-success" onclick="processApproved()">Process Approved Clips</button>
    <button class="btn btn-danger" onclick="quitApp()">Quit</button>
  </div>
</header>
<div id="grid"></div>
<div id="toast"></div>

<script>
let clips = [];
let triage = {};
let focusedIdx = 0;

async function init() {
  const [clipsRes, triageRes] = await Promise.all([
    fetch('/api/clips').then(r => r.json()),
    fetch('/api/triage').then(r => r.json())
  ]);
  clips = clipsRes;
  triage = triageRes;
  render();
}

function fmt(sec) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return m + ':' + String(s).padStart(2, '0');
}

function render() {
  let sorted = [...clips];
  const sort = document.getElementById('sort-select').value;
  if (sort === 'dur-asc') sorted.sort((a, b) => (triage[a]?.duration||0) - (triage[b]?.duration||0));
  else if (sort === 'dur-desc') sorted.sort((a, b) => (triage[b]?.duration||0) - (triage[a]?.duration||0));

  const unrevOnly = document.getElementById('unreviewed-only').checked;
  if (unrevOnly) sorted = sorted.filter(f => !triage[f]?.decision);

  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  sorted.forEach((fname, i) => {
    const t = triage[fname] || {};
    const decision = t.decision || '';
    const card = document.createElement('div');
    card.className = 'card' + (decision === 'keep' ? ' kept' : decision === 'skip' ? ' skipped' : '');
    card.dataset.file = fname;
    card.dataset.idx = i;
    card.innerHTML = `
      <video src="/video/${encodeURIComponent(fname)}" preload="metadata" tabindex="-1"></video>
      <div class="card-body">
        <div class="card-name">${fname}</div>
        <div class="card-duration">${t.duration ? fmt(t.duration) : '—'}</div>
        <div class="card-actions">
          <button class="btn ${decision==='keep'?'btn-success':'btn-outline'}" onclick="decide('${fname}','keep')">K Keep</button>
          <button class="btn ${decision==='skip'?'btn-danger':'btn-outline'}" onclick="decide('${fname}','skip')">S Skip</button>
        </div>
        <textarea placeholder="Notes (e.g. react at 0:14)" onchange="saveNote('${fname}',this.value)">${t.notes||''}</textarea>
      </div>`;
    grid.appendChild(card);
  });

  const kept = Object.values(triage).filter(v => v.decision === 'keep').length;
  const skipped = Object.values(triage).filter(v => v.decision === 'skip').length;
  const reviewed = kept + skipped;
  document.getElementById('progress-badge').innerHTML =
    `<span class="badge badge-kept">${kept} kept</span><span class="badge badge-skipped">${skipped} skipped</span> <span style="color:#666;font-size:14px">${reviewed}/${clips.length} reviewed</span>`;
}

async function decide(fname, decision) {
  if (!triage[fname]) triage[fname] = {};
  triage[fname].decision = triage[fname].decision === decision ? null : decision;
  await fetch('/api/triage', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({file: fname, decision: triage[fname].decision, notes: triage[fname].notes||''})});
  render();
  showToast(decision === 'keep' ? 'Kept' : 'Skipped');
}

async function saveNote(fname, notes) {
  if (!triage[fname]) triage[fname] = {};
  triage[fname].notes = notes;
  await fetch('/api/triage', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({file: fname, decision: triage[fname].decision||null, notes})});
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 1500);
}

async function processApproved() {
  if (!confirm('Move all KEEP clips to input/tiktoks and SKIP clips to input/skipped?')) return;
  const res = await fetch('/api/process', {method:'POST'});
  const data = await res.json();
  alert(`Done! ${data.kept} clips kept, ${data.skipped} clips skipped.`);
  location.reload();
}

async function quitApp() {
  if (confirm('Quit the triage server?')) {
    fetch('/api/quit', {method:'POST'});
    document.body.innerHTML = '<div style="padding:40px;color:#aaa;font-size:18px">Server stopped. You can close this tab.</div>';
  }
}

document.getElementById('sort-select').addEventListener('change', render);
document.getElementById('unreviewed-only').addEventListener('change', render);

document.addEventListener('keydown', e => {
  const cards = [...document.querySelectorAll('.card')];
  if (!cards.length) return;
  if (focusedIdx >= cards.length) focusedIdx = 0;
  const card = cards[focusedIdx];
  const fname = card.dataset.file;
  const video = card.querySelector('video');

  if (e.key === 'k' || e.key === 'K') { e.preventDefault(); decide(fname, 'keep'); }
  else if (e.key === 's' || e.key === 'S') { e.preventDefault(); decide(fname, 'skip'); }
  else if (e.key === ' ') {
    e.preventDefault();
    video.paused ? video.play() : video.pause();
  } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    focusedIdx = Math.min(focusedIdx + 1, cards.length - 1);
    cards[focusedIdx].scrollIntoView({behavior:'smooth', block:'center'});
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    focusedIdx = Math.max(focusedIdx - 1, 0);
    cards[focusedIdx].scrollIntoView({behavior:'smooth', block:'center'});
  }
});

init();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/video/<filename>")
def serve_video(filename):
    return send_from_directory(str(TRIAGE_DIR), filename)


@app.route("/api/clips")
def api_clips():
    return jsonify(get_clips())


@app.route("/api/triage", methods=["GET"])
def api_triage_get():
    return jsonify(load_triage())


@app.route("/api/triage", methods=["POST"])
def api_triage_post():
    data = request.json
    fname = data.get("file")
    triage = load_triage()
    if fname not in triage:
        triage[fname] = {}
    triage[fname]["decision"] = data.get("decision")
    triage[fname]["notes"] = data.get("notes", "")
    # Lazily compute duration if not already stored
    if "duration" not in triage[fname]:
        path = TRIAGE_DIR / fname
        if path.exists():
            triage[fname]["duration"] = get_video_duration(path)
    save_triage(triage)
    return jsonify({"ok": True})


@app.route("/api/process", methods=["POST"])
def api_process():
    triage = load_triage()
    TIKTOKS_DIR.mkdir(parents=True, exist_ok=True)
    SKIPPED_DIR.mkdir(parents=True, exist_ok=True)

    kept = 0
    skipped = 0
    for fname, info in triage.items():
        src = TRIAGE_DIR / fname
        if not src.exists():
            continue
        decision = info.get("decision")
        if decision == "keep":
            shutil.move(str(src), str(TIKTOKS_DIR / fname))
            kept += 1
        elif decision == "skip":
            shutil.move(str(src), str(SKIPPED_DIR / fname))
            skipped += 1

    triage["_session_complete"] = True
    save_triage(triage)
    return jsonify({"kept": kept, "skipped": skipped})


@app.route("/api/quit", methods=["POST"])
def api_quit():
    def shutdown():
        time.sleep(0.5)
        shutdown_event.set()
        os._exit(0)
    threading.Thread(target=shutdown, daemon=True).start()
    return jsonify({"ok": True})


def preload_durations():
    """Pre-populate durations in triage.json on startup."""
    clips = get_clips()
    if not clips:
        return
    triage = load_triage()
    changed = False
    for fname in clips:
        if fname not in triage:
            triage[fname] = {}
        if "duration" not in triage[fname]:
            path = TRIAGE_DIR / fname
            triage[fname]["duration"] = get_video_duration(path)
            changed = True
    if changed:
        save_triage(triage)


def main():
    port = 5050
    preload_durations()
    print(f"Starting triage server at http://localhost:{port}")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
