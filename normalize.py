#!/usr/bin/env python3
"""Module 4 — Audio Normalization (EBU R128 two-pass loudnorm)."""

import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
TIKTOKS_IN = BASE / "input" / "tiktoks"
NORMALIZED_OUT = BASE / "output" / "normalized"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found. Install it with:\n  brew install ffmpeg")
        sys.exit(1)


def load_config():
    return json.loads(CONFIG_FILE.read_text())


def parse_loudnorm_stats(stderr):
    """Extract loudnorm JSON stats block from ffmpeg stderr."""
    match = re.search(r"\{[^}]+\"input_i\"[^}]+\}", stderr, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def normalize_clip(clip, target_lufs, true_peak):
    out_file = NORMALIZED_OUT / clip.name
    print(f"\n[{clip.name}]")

    # Pass 1: measure loudness
    print("  Pass 1: analyzing audio...")
    pass1_cmd = [
        "ffmpeg", "-y", "-i", str(clip),
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:print_format=json",
        "-vn", "-f", "null", "-",
    ]
    result1 = subprocess.run(pass1_cmd, capture_output=True, text=True)
    stats = parse_loudnorm_stats(result1.stderr)

    if not stats:
        print("  WARNING: Could not parse loudnorm stats. Skipping.")
        return

    input_i = stats.get("input_i", "?")
    print(f"  Input integrated loudness: {input_i} LUFS")

    # Pass 2: apply normalization with measured values
    print("  Pass 2: applying normalization...")
    measured_i = stats.get("input_i", "-70")
    measured_lra = stats.get("input_lra", "0")
    measured_tp = stats.get("input_tp", "-70")
    measured_thresh = stats.get("input_thresh", "-70")
    offset = stats.get("target_offset", "0")

    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
        f":measured_I={measured_i}"
        f":measured_LRA={measured_lra}"
        f":measured_TP={measured_tp}"
        f":measured_thresh={measured_thresh}"
        f":offset={offset}"
        f":linear=true:print_format=summary"
    )

    pass2_cmd = [
        "ffmpeg", "-y", "-i", str(clip),
        "-af", loudnorm_filter,
        "-c:v", "copy",
        str(out_file),
    ]
    result2 = subprocess.run(pass2_cmd, capture_output=True, text=True)

    if result2.returncode != 0:
        print(f"  ERROR: {result2.stderr[-400:]}")
        return

    # Parse output stats for before/after display
    out_stats = parse_loudnorm_stats(result2.stderr)
    output_i = out_stats.get("output_i", target_lufs)
    print(f"  Output integrated loudness: {output_i} LUFS (target: {target_lufs})")
    print(f"  Saved: {out_file.name}")


def main():
    check_ffmpeg()
    cfg = load_config()
    target_lufs = cfg["audio"]["target_lufs"]
    true_peak = cfg["audio"]["true_peak"]

    NORMALIZED_OUT.mkdir(parents=True, exist_ok=True)
    TIKTOKS_IN.mkdir(parents=True, exist_ok=True)

    clips = [f for f in sorted(TIKTOKS_IN.iterdir()) if f.suffix.lower() in VIDEO_EXTENSIONS]
    if not clips:
        print("No clips found in input/tiktoks/.")
        return

    print(f"Normalizing {len(clips)} clip(s) to {target_lufs} LUFS (true peak {true_peak} dBTP)...")
    for clip in clips:
        normalize_clip(clip, target_lufs, true_peak)

    print(f"\nDone. Normalized files saved to {NORMALIZED_OUT}/")


if __name__ == "__main__":
    main()
