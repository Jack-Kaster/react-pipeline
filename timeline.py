#!/usr/bin/env python3
"""Module 6 — DaVinci Resolve FCPXML Timeline Generator."""

import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
TIKTOKS_OUT = BASE / "output" / "tiktoks"
TRANSCRIPTS_OUT = BASE / "output" / "transcripts"
TIMELINE_OUT = BASE / "output" / "timeline"
HANDOFF_OUT = BASE / "output" / "editor_handoff"
TRIAGE_JSON = BASE / "triage_data" / "triage.json"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def load_config():
    return json.loads(CONFIG_FILE.read_text())


def load_triage():
    if TRIAGE_JSON.exists():
        return json.loads(TRIAGE_JSON.read_text())
    return {}


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
    return 30.0


def parse_timestamp(ts_str):
    """Parse 'react at M:SS' or 'M:SS' -> seconds float."""
    match = re.search(r"(\d+):(\d{2})", ts_str or "")
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    return 0


def frames(seconds, fps):
    return int(round(seconds * fps))


def rational(seconds, fps):
    """Return FCPXML rational time string like '900/30s'."""
    f = frames(seconds, fps)
    return f"{f}/{fps}s"


def pretty_xml(element):
    raw = ET.tostring(element, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ")


def build_fcpxml(clips_data, cfg, for_editor=False):
    fps = cfg["timeline"]["framerate"]
    gap_secs = cfg["timeline"]["default_reaction_gap_seconds"]
    triage = load_triage()

    # Root
    root = ET.Element("fcpxml", version="1.9")
    resources = ET.SubElement(root, "resources")

    # Format resource
    fmt = ET.SubElement(resources, "format",
        id="r1",
        name=f"FFVideoFormat{cfg['canvas']['height']}p{fps}",
        frameDuration=f"1/{fps}s",
        width=str(cfg["canvas"]["width"]),
        height=str(cfg["canvas"]["height"])
    )

    # Asset resources
    asset_ids = {}
    for idx, clip_path in enumerate(clips_data, start=2):
        asset_id = f"r{idx}"
        asset_ids[clip_path] = asset_id
        duration_secs = get_video_duration(clip_path)
        ET.SubElement(resources, "asset",
            id=asset_id,
            name=clip_path.stem,
            uid=f"uid_{idx}",
            start="0s",
            duration=rational(duration_secs, fps),
            hasVideo="1",
            hasAudio="1",
            **{"src": clip_path.resolve().as_uri()}
        )

    # Library > Event > Project
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="React Pipeline")
    project = ET.SubElement(event, "project", name="Editor Timeline" if for_editor else "Creator Timeline")
    sequence = ET.SubElement(project, "sequence",
        format="r1",
        duration="0s",  # will be updated
        tcStart="0s",
        tcFormat="NDF"
    )
    spine = ET.SubElement(sequence, "spine")

    cursor = 0.0  # current timeline position in seconds

    for clip_path in clips_data:
        duration_secs = get_video_duration(clip_path)
        asset_id = asset_ids[clip_path]
        fname = clip_path.name
        triage_info = triage.get(fname, triage.get(clip_path.name.replace(".mov", ".mp4"), {}))
        notes = triage_info.get("notes", "")
        color = cfg["timeline"]["color_label"]

        # Reaction gap BEFORE each TikTok
        gap = ET.SubElement(spine, "gap",
            name=f"REACTION — {clip_path.stem}" if for_editor else f"Reaction: {clip_path.stem}",
            offset=rational(cursor, fps),
            duration=rational(gap_secs, fps),
            start="0s"
        )
        if for_editor:
            ET.SubElement(gap, "note").text = "EDIT HERE — REACTION FOOTAGE"

        cursor += gap_secs

        # Parse start offset from triage notes
        start_offset = 0
        if notes and "react at" in notes.lower():
            start_offset = parse_timestamp(notes)
        effective_duration = max(0, duration_secs - start_offset)

        # TikTok clip
        clip_start_rational = rational(start_offset, fps)
        clip_elem = ET.SubElement(spine, "clip",
            name=clip_path.stem,
            offset=rational(cursor, fps),
            duration=rational(effective_duration, fps),
            start=clip_start_rational,
            format="r1",
            colorSpace="Rec. 709",
            **{"tcFormat": "NDF"}
        )
        clip_elem.set("note", "DO NOT EDIT — TIKTOK SEGMENT" if for_editor else "")
        clip_elem.set("audioRole", "dialogue")

        # Color label
        ET.SubElement(clip_elem, "keyword", value=color)

        # Asset ref inside clip
        ET.SubElement(clip_elem, "asset-clip",
            ref=asset_id,
            offset=clip_start_rational,
            name=clip_path.stem,
            duration=rational(effective_duration, fps),
            start=clip_start_rational,
            format="r1",
            audioRole="dialogue"
        )

        # Triage notes as marker
        if notes and cfg["editor"].get("notes_in_markers") and for_editor:
            marker = ET.SubElement(clip_elem, "marker",
                start=clip_start_rational,
                duration=rational(1, fps),
                value=notes[:100]
            )

        # Transcript first-line as chapter marker
        txt_file = TRANSCRIPTS_OUT / (clip_path.stem + ".txt")
        if txt_file.exists() and cfg["editor"].get("include_transcripts"):
            first_line = txt_file.read_text().strip().split(".")[0][:80]
            ET.SubElement(clip_elem, "chapter-marker",
                start=clip_start_rational,
                duration=rational(1, fps),
                value=first_line
            )

        cursor += effective_duration

    sequence.set("duration", rational(cursor, fps))
    return pretty_xml(root)


def get_clips():
    clips = [f for f in sorted(TIKTOKS_OUT.iterdir()) if f.suffix.lower() in VIDEO_EXTENSIONS]
    return clips


def build_brief(clips):
    total_duration = sum(get_video_duration(c) for c in clips)
    cfg = load_config()
    gap = cfg["timeline"]["default_reaction_gap_seconds"]
    estimated_total = total_duration + len(clips) * gap

    def fmt(secs):
        m, s = int(secs // 60), int(secs % 60)
        return f"{m}m {s}s"

    return f"""EDITOR BRIEF
============

TikTok segments: {len(clips)}
Total TikTok runtime: {fmt(total_duration)}
Estimated final video length: {fmt(estimated_total)} (includes {gap}s reaction gaps)

INSTRUCTIONS
------------
TikTok segments are pre-placed and locked on V2.
Edit ONLY the reaction footage gaps on V1.
Do not adjust TikTok clip timing or positioning.

Each reaction gap is labeled with the TikTok clip it precedes.
Triage notes (if any) are added as markers on each clip.

Import editor_timeline.fcpxml into DaVinci Resolve:
  File > Import > Timeline > Select .fcpxml file
"""


def main():
    import sys
    cfg = load_config()
    TIMELINE_OUT.mkdir(parents=True, exist_ok=True)
    HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    clips = get_clips()
    if not clips:
        print("No processed TikTok clips found in output/tiktoks/. Run process.py first.")
        sys.exit(0)

    print(f"Generating timelines for {len(clips)} clip(s)...")

    # Creator timeline
    creator_xml = build_fcpxml(clips, cfg, for_editor=False)
    creator_file = TIMELINE_OUT / "creator_timeline.fcpxml"
    creator_file.write_text(creator_xml)
    print(f"  Saved: {creator_file}")

    # Editor timeline
    editor_xml = build_fcpxml(clips, cfg, for_editor=True)
    editor_file = TIMELINE_OUT / "editor_timeline.fcpxml"
    editor_file.write_text(editor_xml)
    print(f"  Saved: {editor_file}")

    # Editor handoff package
    print("\nBuilding editor handoff package...")
    handoff_clips = HANDOFF_OUT / "tiktok_clips"
    handoff_transcripts = HANDOFF_OUT / "transcripts"
    handoff_clips.mkdir(parents=True, exist_ok=True)

    shutil.copy2(editor_file, HANDOFF_OUT / "editor_timeline.fcpxml")

    for clip in clips:
        shutil.copy2(clip, handoff_clips / clip.name)

    if TRANSCRIPTS_OUT.exists() and cfg["editor"].get("include_transcripts"):
        handoff_transcripts.mkdir(parents=True, exist_ok=True)
        for txt in TRANSCRIPTS_OUT.glob("*.txt"):
            shutil.copy2(txt, handoff_transcripts / txt.name)

    brief_file = HANDOFF_OUT / "BRIEF.txt"
    brief_file.write_text(build_brief(clips))
    print(f"  Handoff package: {HANDOFF_OUT}/")

    print("\nDone. Import FCPXML into DaVinci Resolve: File > Import > Timeline")


if __name__ == "__main__":
    main()
