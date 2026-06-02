#!/usr/bin/env python3
"""Module 5 — Auto-Transcription using faster-whisper (fallback: openai-whisper)."""

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
TIKTOKS_IN = BASE / "input" / "tiktoks"
TRANSCRIPTS_OUT = BASE / "output" / "transcripts"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ffmpeg not found. Install it with:\n  brew install ffmpeg")
        sys.exit(1)


def load_config():
    return json.loads(CONFIG_FILE.read_text())


def try_import_faster_whisper():
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except ImportError:
        return None


def try_import_openai_whisper():
    try:
        import whisper
        return whisper
    except ImportError:
        return None


def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_srt_time(seg["start"])
        end = format_srt_time(seg["end"])
        lines.append(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n")
    return "\n".join(lines)


def segments_to_txt(segments):
    return " ".join(seg["text"].strip() for seg in segments)


def transcribe_with_faster_whisper(clip, model_name, language):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(str(clip), language=language)
    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_iter]
    return segments


def transcribe_with_openai_whisper(clip, model_name, language):
    import whisper
    model = whisper.load_model(model_name)
    result = model.transcribe(str(clip), language=language)
    segments = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in result["segments"]]
    return segments


def main():
    check_ffmpeg()
    cfg = load_config()
    model_name = cfg["transcription"]["model"]
    language = cfg["transcription"]["language"]

    TRANSCRIPTS_OUT.mkdir(parents=True, exist_ok=True)
    TIKTOKS_IN.mkdir(parents=True, exist_ok=True)

    WhisperModel = try_import_faster_whisper()
    openai_whisper = None
    if WhisperModel is None:
        openai_whisper = try_import_openai_whisper()

    if WhisperModel is None and openai_whisper is None:
        print("ERROR: No transcription library found.")
        print("Install faster-whisper (preferred):")
        print("  pip install faster-whisper")
        print("Or install openai-whisper (fallback):")
        print("  pip install openai-whisper")
        sys.exit(1)

    backend = "faster-whisper" if WhisperModel else "openai-whisper"
    print(f"Using backend: {backend}, model: {model_name}, language: {language}\n")

    clips = [f for f in sorted(TIKTOKS_IN.iterdir()) if f.suffix.lower() in VIDEO_EXTENSIONS]
    if not clips:
        print("No clips found in input/tiktoks/.")
        return

    print(f"Transcribing {len(clips)} clip(s)...")
    for i, clip in enumerate(clips, 1):
        print(f"  [{i}/{len(clips)}] {clip.name}...")
        try:
            if WhisperModel:
                segments = transcribe_with_faster_whisper(clip, model_name, language)
            else:
                segments = transcribe_with_openai_whisper(clip, model_name, language)

            srt_file = TRANSCRIPTS_OUT / (clip.stem + ".srt")
            txt_file = TRANSCRIPTS_OUT / (clip.stem + ".txt")

            srt_file.write_text(segments_to_srt(segments))
            txt_file.write_text(segments_to_txt(segments))
            print(f"    Saved: {srt_file.name}, {txt_file.name}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\nDone. Transcripts saved to {TRANSCRIPTS_OUT}/")


if __name__ == "__main__":
    main()
