#!/usr/bin/env python3
"""Module 1 — Batch TikTok Downloader."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
URLS_FILE = BASE / "input" / "urls.txt"
TRIAGE_DIR = BASE / "input" / "triage"
LOG_FILE = BASE / "input" / "downloaded.log"


def check_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: yt-dlp not found. Install it with:")
        print("  pip install yt-dlp")
        sys.exit(1)


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found. Install it with:")
        print("  brew install ffmpeg")
        sys.exit(1)


def load_downloaded_log():
    if LOG_FILE.exists():
        return set(LOG_FILE.read_text().splitlines())
    return set()


def save_downloaded_log(log):
    LOG_FILE.write_text("\n".join(sorted(log)))


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:100]


def download_url(url, downloaded_log):
    if url in downloaded_log:
        print(f"  SKIP (already downloaded): {url}")
        return "skipped"

    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output", str(TRIAGE_DIR / "%(title)s_%(id)s.%(ext)s"),
        "--restrict-filenames",
        "--no-playlist",
        "--print", "after_move:filepath",
        url,
    ]

    print(f"  Downloading: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  FAILED: {result.stderr.strip()}")
        return "failed"

    filepath = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "unknown"
    print(f"  Saved: {Path(filepath).name}")
    return "downloaded"


def main():
    check_ytdlp()
    check_ffmpeg()

    if not URLS_FILE.exists():
        print(f"ERROR: {URLS_FILE} not found. Create it with one TikTok URL per line.")
        sys.exit(1)

    lines = URLS_FILE.read_text().splitlines()
    urls = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]

    if not urls:
        print("No URLs found in input/urls.txt.")
        return

    print(f"Found {len(urls)} URL(s) to process.\n")
    downloaded_log = load_downloaded_log()

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    for url in urls:
        status = download_url(url, downloaded_log)
        counts[status] += 1
        if status == "downloaded":
            downloaded_log.add(url)

    save_downloaded_log(downloaded_log)

    print(f"\nDone. {counts['downloaded']} downloaded, {counts['skipped']} skipped, {counts['failed']} failed.")


if __name__ == "__main__":
    main()
