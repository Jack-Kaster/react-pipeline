#!/usr/bin/env python3
"""Download all TikTok URLs from a CSV file."""

import csv
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

OUTPUT_DIR = Path.home() / "Downloads" / "tiktoks"


def handle_from_url(url):
    m = re.search(r"/@([^/]+)/video/", url)
    return m.group(1) if m else "unknown"


def next_available_path(output_dir, handle):
    path = output_dir / f"{handle}.mp4"
    if not path.exists():
        return path
    i = 2
    while True:
        path = output_dir / f"{handle}-{i}.mp4"
        if not path.exists():
            return path
        i += 1


def main():
    if len(sys.argv) < 2:
        root = tk.Tk()
        root.withdraw()
        chosen = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "*.csv")])
        root.destroy()
        if not chosen:
            print("No file selected.")
            sys.exit(1)
        csv_path = Path(chosen)
    else:
        csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    urls = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("url", "").strip()
            if url.startswith("https://www.tiktok.com"):
                urls.append(url)

    if not urls:
        print("No TikTok URLs found in that file.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(urls)} videos to {OUTPUT_DIR}\n")

    failed = 0
    for i, url in enumerate(urls, 1):
        handle = handle_from_url(url)
        dest = next_available_path(OUTPUT_DIR, handle)
        print(f"[{i}/{len(urls)}] {dest.name}...")
        out = str(dest.with_suffix("")) + ".%(ext)s"
        result = subprocess.run([
            "yt-dlp",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--output", out,
            "--cookies-from-browser", "chrome",
            "--restrict-filenames",
            "--no-playlist",
            "--quiet",
            url,
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  FAILED")
            failed += 1
        else:
            print(f"  done")

    print(f"\nFinished. {len(urls) - failed}/{len(urls)} downloaded.")


if __name__ == "__main__":
    main()
