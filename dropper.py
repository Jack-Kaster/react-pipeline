#!/usr/bin/env python3
"""Drag-and-drop TikTok CSV downloader."""

import csv
import re
import subprocess
import threading
from pathlib import Path

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    import tkinter as tk
except ImportError:
    import tkinter as tk
    tk.Tk().withdraw()
    tk.messagebox.showerror("Missing dependency", "Run: pip install tkinterdnd2")
    raise SystemExit

OUTPUT_DIR = Path.home() / "Downloads" / "tiktoks"


def extract_urls(csv_path):
    urls = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("url", "").strip()
            if url.startswith("https://www.tiktok.com"):
                urls.append(url)
    return urls


def handle_from_url(url):
    m = re.search(r"/@([^/]+)/video/", url)
    return m.group(1) if m else "unknown"


def download_all(urls, log):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(urls)
    failed = 0

    for i, url in enumerate(urls, 1):
        handle = handle_from_url(url)
        log(f"[{i}/{total}] {handle}")
        out = str(OUTPUT_DIR / handle / f"{handle}.%(ext)s")
        result = subprocess.run([
            "yt-dlp",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--output", out,
            "--cookies-from-browser", "chrome",
            "--restrict-filenames",
            "--no-overwrites",
            "--no-playlist",
            "--quiet",
            url,
        ], capture_output=True, text=True)

        if result.returncode != 0:
            log(f"  ✗ failed")
            failed += 1
        else:
            log(f"  ✓ done")

    log(f"\n{'─'*30}")
    log(f"Finished. {total - failed}/{total} downloaded.")
    log(f"Files in: {OUTPUT_DIR}")


class App:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("TikTok Downloader")
        self.root.geometry("420x380")
        self.root.resizable(False, False)
        self.root.configure(bg="#ffffff")

        self.drop_zone = tk.Label(
            self.root,
            text="Drop CSV here",
            font=("Helvetica Neue", 22, "bold"),
            bg="#f5f5f5",
            fg="#999999",
            relief="flat",
            cursor="hand2",
        )
        self.drop_zone.pack(fill=tk.X, padx=20, pady=(20, 10), ipady=30)
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        self.log_box = tk.Text(
            self.root,
            height=12,
            font=("Menlo", 11),
            bg="#1a1a1a",
            fg="#cccccc",
            relief="flat",
            state=tk.DISABLED,
            padx=10,
            pady=8,
        )
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        self.root.mainloop()

    def on_drop(self, event):
        path = event.data.strip().strip("{}")
        if not path.lower().endswith(".csv"):
            self.log("Drop a .csv file.")
            return
        urls = extract_urls(path)
        if not urls:
            self.log("No TikTok URLs found in that file.")
            return
        self.drop_zone.config(text=f"Downloading {len(urls)} videos…", fg="#333333")
        threading.Thread(
            target=download_all, args=(urls, self.log), daemon=True
        ).start()

    def log(self, msg):
        self.root.after(0, self._write, msg)

    def _write(self, msg):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)


if __name__ == "__main__":
    App()
