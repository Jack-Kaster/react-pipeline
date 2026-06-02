#!/usr/bin/env python3
"""Module 3 — Compositing Script (TikTok + Comment screenshots)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
TIKTOKS_IN = BASE / "input" / "tiktoks"
COMMENTS_IN = BASE / "input" / "comments"
TIKTOKS_OUT = BASE / "output" / "tiktoks"
COMMENTS_OUT = BASE / "output" / "comments"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found. Install it with:\n  brew install ffmpeg")
        sys.exit(1)


def load_config():
    return json.loads(CONFIG_FILE.read_text())


def prores_args():
    return ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]


def rounded_corner_filter(w, h, r):
    """
    FFmpeg geq filter that draws an antialiased rounded-rectangle alpha mask.
    Each corner uses a distance formula; pixels inside the rounded rect are opaque.
    """
    r = min(r, w // 2, h // 2)
    # Per-corner distance expressions. We clamp each coordinate to the corner region.
    tl = f"max(0,{r}-X)*max(0,{r}-Y)"
    tr = f"max(0,X-({w}-{r}-1))*max(0,{r}-Y)"
    bl = f"max(0,{r}-X)*max(0,Y-({h}-{r}-1))"
    br = f"max(0,X-({w}-{r}-1))*max(0,Y-({h}-{r}-1))"
    # alpha = 255 * (inside rounded rect). We use lum() hack via geq for alpha channel.
    alpha_expr = (
        f"if(lte(hypot({tl}),{r})*lte(X,{r})*lte(Y,{r}),255,"
        f"if(lte(hypot({tr}),{r})*gte(X,{w}-{r}-1)*lte(Y,{r}),255,"
        f"if(lte(hypot({bl}),{r})*lte(X,{r})*gte(Y,{h}-{r}-1),255,"
        f"if(lte(hypot({br}),{r})*gte(X,{w}-{r}-1)*gte(Y,{h}-{r}-1),255,"
        f"if(between(X,{r},{w}-{r}-1)+between(Y,{r},{h}-{r}-1),255,0)))))"
    )
    return alpha_expr


def process_tiktoks(cfg):
    TIKTOKS_OUT.mkdir(parents=True, exist_ok=True)
    canvas_w = cfg["canvas"]["width"]
    canvas_h = cfg["canvas"]["height"]
    frame = cfg["tiktok_frame"]
    fx, fy, fw, fh, cr = frame["x"], frame["y"], frame["width"], frame["height"], frame["corner_radius"]

    clips = [f for f in sorted(TIKTOKS_IN.iterdir()) if f.suffix.lower() in VIDEO_EXTENSIONS]
    if not clips:
        print("No MP4 files found in input/tiktoks/.")
        return

    print(f"Processing {len(clips)} TikTok clip(s)...")
    for clip in clips:
        out_file = TIKTOKS_OUT / (clip.stem + ".mov")
        print(f"  {clip.name} -> {out_file.name}")

        # Scale to fit within fw x fh, maintaining aspect ratio
        scale_filter = f"scale={fw}:{fh}:force_original_aspect_ratio=decrease,pad={fw}:{fh}:(ow-iw)/2:(oh-ih)/2:color=black@0"

        # Rounded corner alpha mask using geq
        alpha_expr = rounded_corner_filter(fw, fh, cr)
        # Apply alpha mask: use geq to generate alpha, then alphamerge
        round_filter = (
            f"[scaled]split[vid][mask];"
            f"[mask]geq=lum='255':a='{alpha_expr}',alphaextract[msk];"
            f"[vid][msk]alphamerge[rounded]"
        )

        # Compose onto transparent canvas at fx, fy
        compose_filter = (
            f"[0:v]{scale_filter}[scaled];"
            f"{round_filter};"
            f"color=c=black@0:s={canvas_w}x{canvas_h}[canvas];"
            f"[canvas][rounded]overlay={fx}:{fy}[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(clip),
            "-filter_complex", compose_filter,
            "-map", "[out]",
            "-map", "0:a?",
            "-c:a", "copy",
        ] + prores_args() + [str(out_file)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr[-500:]}")
        else:
            print(f"  Done.")


def process_comments(cfg):
    COMMENTS_OUT.mkdir(parents=True, exist_ok=True)
    canvas_w = cfg["canvas"]["width"]
    canvas_h = cfg["canvas"]["height"]
    frame = cfg["comment_frame"]
    cx, cy = frame["x_center"], frame["y_center"]
    max_w, max_h = frame["max_width"], frame["max_height"]
    cr = frame["corner_radius"]
    hold = frame["hold_duration_seconds"]

    images = [f for f in sorted(COMMENTS_IN.iterdir()) if f.suffix.lower() in IMAGE_EXTENSIONS]
    if not images:
        print("No image files found in input/comments/.")
        return

    print(f"Processing {len(images)} comment image(s)...")
    for img in images:
        out_file = COMMENTS_OUT / (img.stem + ".mov")
        print(f"  {img.name} -> {out_file.name}")

        # Scale: fit within max_w x max_h
        scale_filter = f"scale={max_w}:{max_h}:force_original_aspect_ratio=decrease"

        alpha_expr_placeholder = "ALPHA_PLACEHOLDER"

        # We need actual scaled dims to compute position — use ffprobe first
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(img)],
            capture_output=True, text=True
        )
        probe_data = json.loads(probe.stdout)
        src_w, src_h = 0, 0
        for s in probe_data.get("streams", []):
            if s.get("codec_type") == "video":
                src_w, src_h = int(s["width"]), int(s["height"])
                break

        if src_w == 0 or src_h == 0:
            print(f"  SKIP: could not read dimensions for {img.name}")
            continue

        # Compute scaled dimensions
        scale = min(max_w / src_w, max_h / src_h)
        scaled_w = int(src_w * scale)
        scaled_h = int(src_h * scale)

        # Dynamic centering
        pos_x = cx - scaled_w // 2
        pos_y = cy - scaled_h // 2

        alpha_expr = rounded_corner_filter(scaled_w, scaled_h, cr)

        filter_complex = (
            f"[0:v]scale={scaled_w}:{scaled_h}[scaled];"
            f"[scaled]split[vid][mask];"
            f"[mask]geq=lum='255':a='{alpha_expr}',alphaextract[msk];"
            f"[vid][msk]alphamerge[rounded];"
            f"color=c=black@0:s={canvas_w}x{canvas_h}:d={hold}[canvas];"
            f"[canvas][rounded]overlay={pos_x}:{pos_y}:shortest=1[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(hold),
            "-i", str(img),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-r", "30",
        ] + prores_args() + [str(out_file)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr[-500:]}")
        else:
            print(f"  Done.")


def main():
    parser = argparse.ArgumentParser(description="Compositing script for TikToks and comment screenshots.")
    parser.add_argument("--mode", choices=["tiktoks", "comments", "all"], default="all")
    args = parser.parse_args()

    check_ffmpeg()
    cfg = load_config()

    if args.mode in ("tiktoks", "all"):
        process_tiktoks(cfg)
    if args.mode in ("comments", "all"):
        process_comments(cfg)


if __name__ == "__main__":
    main()
