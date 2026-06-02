# React Channel Production Pipeline

A complete local production pipeline for YouTube react channels. Eliminates every manual prep and post-production step that doesn't require creative judgment.

---

## Prerequisites

### Mac (recommended)

```bash
# 1. Python 3.10+
brew install python

# 2. FFmpeg (required by all modules)
brew install ffmpeg

# 3. Python dependencies
pip install yt-dlp flask faster-whisper
```

`faster-whisper` requires Python 3.8+ and works on Apple Silicon (M1/M2/M3) via CPU.

If `faster-whisper` fails to install, fall back to:
```bash
pip install openai-whisper
```

---

## Folder Structure

```
react_pipeline/
├── input/
│   ├── urls.txt          # One TikTok URL per line
│   ├── triage/           # Raw downloads land here
│   ├── tiktoks/          # Approved clips (after triage)
│   ├── comments/         # Comment screenshot images
│   └── skipped/          # Rejected clips (not deleted)
├── output/
│   ├── tiktoks/          # Processed MOV with alpha
│   ├── comments/         # Processed comment MOVs
│   ├── normalized/       # Audio-normalized MP4s
│   ├── transcripts/      # SRT + TXT files per clip
│   ├── timeline/         # FCPXML timeline files
│   └── editor_handoff/   # Self-contained editor package
├── triage_data/
│   └── triage.json       # Triage decisions and notes
├── config.json           # All settings
└── *.py                  # Pipeline modules
```

---

## Full Workflow

### Step 1 — Add URLs

Edit `input/urls.txt` and add one TikTok URL per line:
```
https://www.tiktok.com/@user/video/123456789
https://www.tiktok.com/@user/video/987654321
# This line is ignored (comment)
```

### Step 2 — Download

```bash
python download.py
```

Downloads all clips to `input/triage/`. Already-downloaded URLs are skipped automatically.

### Step 3 — Triage

```bash
python triage.py
```

Opens a browser UI at `http://localhost:5050`. For each clip:
- Watch the video inline
- Add notes (e.g. `react at 0:14`, `good for segment 2`)
- Click **Keep** or **Skip** (keyboard: `K` / `S`, spacebar to play/pause)
- Use arrow keys to move between clips

When done, click **Process Approved Clips**. Kept clips move to `input/tiktoks/`, skipped clips to `input/skipped/`.

### Step 4 — Normalize Audio

```bash
python normalize.py
```

Two-pass EBU R128 normalization to -14 LUFS. Prints before/after values per clip. Originals in `input/tiktoks/` are untouched; normalized versions go to `output/normalized/`.

### Step 5 — Transcribe

```bash
python transcribe.py
```

Runs Whisper locally (no internet required after model download). Outputs:
- `output/transcripts/clipname.srt` — subtitle file with timestamps
- `output/transcripts/clipname.txt` — plain transcript for writing reactions

### Step 6 — Composite

```bash
# Process TikTok clips only
python process.py --mode tiktoks

# Process comment screenshots only
python process.py --mode comments

# Process both
python process.py --mode all
```

Outputs ProRes 4444 MOV files with alpha channel on a transparent 1920×1080 canvas. Drop directly onto a DaVinci timeline above your reaction footage.

### Step 7 — Generate Timelines

```bash
python timeline.py
```

Generates two FCPXML files:
- `output/timeline/creator_timeline.fcpxml` — for the creator, with labeled reaction gaps
- `output/timeline/editor_timeline.fcpxml` — for the editor, with lock labels and triage notes as markers
- `output/editor_handoff/` — self-contained package (see Editor Handoff below)

---

## Running the Full Pipeline

```bash
python run_all.py
```

Runs all steps in order. Pauses at triage (waits for you to finish in the browser), then continues automatically.

---

## Editing config.json

| Key | Description |
|-----|-------------|
| `canvas.width/height` | Output canvas size (default 1920×1080) |
| `tiktok_frame` | Position/size of TikTok overlay on canvas |
| `comment_frame` | Center point and max size for comment screenshots |
| `audio.target_lufs` | Loudness target (default -14 LUFS for YouTube) |
| `audio.true_peak` | True peak ceiling (default -1.0 dBTP) |
| `transcription.model` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `timeline.default_reaction_gap_seconds` | Length of each reaction slot in the timeline |
| `timeline.color_label` | Color tag for TikTok clips in DaVinci |
| `editor.notes_in_markers` | If true, triage notes appear as DaVinci markers |

---

## Comment Screenshots

1. Drop JPG or PNG screenshots into `input/comments/`
2. Run `python process.py --mode comments`
3. Each image becomes a 5-second MOV (duration configurable in config.json) centered on the canvas with rounded corners and transparent background

---

## Editor Handoff

After running `timeline.py`, send the editor the entire `output/editor_handoff/` folder. It contains:

```
editor_handoff/
├── editor_timeline.fcpxml   # Import this into DaVinci Resolve
├── BRIEF.txt                # Instructions and clip summary
├── tiktok_clips/            # All processed TikTok MOVs
└── transcripts/             # Plain text transcripts (if enabled)
```

Tell the editor:
> "Import `editor_timeline.fcpxml` into DaVinci Resolve. TikTok segments are pre-placed on V2 — do not move them. Record/edit reaction footage into the labeled gaps on V1."

---

## Importing FCPXML into DaVinci Resolve

1. Open DaVinci Resolve
2. Go to **File > Import > Timeline…**
3. Select the `.fcpxml` file
4. In the import dialog, confirm the frame rate matches (default 30fps)
5. The timeline opens with TikTok clips on V2 and reaction gaps on V1

---

## Troubleshooting

**`yt-dlp` fails to download**
- Update yt-dlp: `pip install -U yt-dlp`
- Some TikTok URLs require being logged in: `yt-dlp --cookies-from-browser safari <url>`

**FFmpeg not found**
```bash
brew install ffmpeg
```

**`faster-whisper` install fails**
```bash
pip install openai-whisper
```
The pipeline auto-detects which library is available.

**ProRes export is slow**
- ProRes 4444 is CPU-intensive. For a 1-minute clip, expect 30–120 seconds on an M1 Mac.
- The alpha channel is required for compositing in DaVinci — do not change the codec.

**Triage UI doesn't open**
- Make sure port 5050 is free: `lsof -i :5050`
- Manually open `http://localhost:5050` in your browser

**FCPXML import shows wrong frame rate**
- Open `config.json` and confirm `timeline.framerate` matches your DaVinci project settings

---

## Module Reference

| Script | Command | Description |
|--------|---------|-------------|
| `download.py` | `python download.py` | Download all URLs from urls.txt |
| `triage.py` | `python triage.py` | Browser-based clip review |
| `normalize.py` | `python normalize.py` | Audio normalization |
| `transcribe.py` | `python transcribe.py` | Local Whisper transcription |
| `process.py` | `python process.py --mode all` | Composite TikToks + comments |
| `timeline.py` | `python timeline.py` | Generate DaVinci FCPXML |
| `run_all.py` | `python run_all.py` | Run full pipeline end to end |
