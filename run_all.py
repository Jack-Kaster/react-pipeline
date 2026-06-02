#!/usr/bin/env python3
"""Module 7 — Master Runner: runs the full pipeline in order."""

import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"


def fmt_duration(secs):
    m, s = int(secs // 60), int(secs % 60)
    return f"{m}m {s}s"


def run_step(label, cmd, wait_for_user=False):
    print(f"\n{'='*60}")
    print(f"  STEP: {label}")
    print(f"{'='*60}")

    if wait_for_user:
        input("  Press ENTER when ready to continue...")

    start = time.time()
    result = subprocess.run(cmd, cwd=str(BASE))
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n[!] Step '{label}' failed (exit code {result.returncode})")
        answer = input("Continue anyway? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborting pipeline.")
            sys.exit(1)
    else:
        print(f"\n[OK] {label} ({elapsed:.1f}s)")

    return result.returncode == 0


def count_clips(folder):
    exts = {".mp4", ".mov", ".avi", ".mkv"}
    folder = Path(folder)
    if not folder.exists():
        return 0
    return sum(1 for f in folder.iterdir() if f.suffix.lower() in exts)


def total_duration(folder):
    """Sum durations of all video files in folder."""
    import json as _json
    exts = {".mp4", ".mov", ".avi", ".mkv"}
    folder = Path(folder)
    if not folder.exists():
        return 0
    total = 0.0
    for f in folder.iterdir():
        if f.suffix.lower() not in exts:
            continue
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(f)],
                capture_output=True, text=True
            )
            data = _json.loads(res.stdout)
            for stream in data.get("streams", []):
                if "duration" in stream:
                    total += float(stream["duration"])
                    break
        except Exception:
            pass
    return total


def main():
    print("\nReact Channel Production Pipeline")
    print("===================================")
    print(f"Working directory: {BASE}\n")

    py = sys.executable

    # Step 1: Download
    run_step("Download TikToks", [py, str(BASE / "download.py")])

    # Step 2: Triage (blocks until user finishes in browser)
    print("\n[Triage] Opening browser for clip review. Complete triage and click 'Process Approved Clips', then return here.")
    run_step("Triage", [py, str(BASE / "triage.py")], wait_for_user=False)

    print("\n  Triage server has exited.")
    input("  Confirm triage is complete and press ENTER to continue...")

    # Step 3: Normalize
    run_step("Audio Normalization", [py, str(BASE / "normalize.py")])

    # Step 4: Transcribe
    run_step("Auto-Transcription", [py, str(BASE / "transcribe.py")])

    # Step 5: Composite
    run_step("Compositing (TikToks + Comments)", [py, str(BASE / "process.py"), "--mode", "all"])

    # Step 6: Timeline
    run_step("Generate DaVinci Timelines", [py, str(BASE / "timeline.py")])

    # Final summary
    clips = count_clips(BASE / "output" / "tiktoks")
    tiktok_runtime = total_duration(BASE / "input" / "tiktoks")
    cfg = json.loads(CONFIG_FILE.read_text())

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Clips processed:        {clips}")
    print(f"  TikTok runtime:         {fmt_duration(tiktok_runtime)}")
    print(f"  Composites:             {BASE}/output/tiktoks/")
    print(f"  Normalized audio:       {BASE}/output/normalized/")
    print(f"  Transcripts:            {BASE}/output/transcripts/")
    print(f"  Creator timeline:       {BASE}/output/timeline/creator_timeline.fcpxml")
    print(f"  Editor timeline:        {BASE}/output/timeline/editor_timeline.fcpxml")
    print(f"  Editor handoff:         {BASE}/output/editor_handoff/")
    print(f"\n  Next: Import .fcpxml into DaVinci Resolve via File > Import > Timeline")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
