#!/usr/bin/env python3
"""Batch-export clips across many calls in one run.

Point this at a directory whose subfolders are one-per-call. Each call subfolder
must contain a source video and a segments.json. For each call it runs the MP4
export (or FCPXML with --fcpxml) and unzips the result into a clips/ folder.
Already-exported calls are skipped, so the run is safe to repeat.

Expected layout:

    <calls_dir>/
        first-call/
            source.mp4          (or any single video file)
            segments.json
        second-call/
            source.mov
            segments.json
        ...

segments.json shape (the same the export scripts read):
    [ { "title": "...", "start": 92.4, "end": 701.8 }, ... ]

Usage:
    batch_export.py <calls_dir> [--pad SECONDS] [--fcpxml] [--outro PATH]

    --pad SECONDS   Widen every clip by SECONDS on each side (clamped to the
                    video bounds) so you can hand-trim the exact in/out point
                    later. Default 0 (cut tight to the segments.json boundaries).
    --fcpxml        Also write a clips.fcpxml timeline per call (DaVinci Resolve
                    / Final Cut) in addition to the MP4s.
    --outro PATH    Optional CTA/outro clip appended to every MP4 (passed through
                    to export_mp4.py).
"""

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
EXPORT_MP4 = str(SCRIPTS_DIR / "export_mp4.py")
EXPORT_FCPXML = str(SCRIPTS_DIR / "export_fcpxml.py")
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


def find_source(call_dir: Path):
    """A file literally named source.* wins; otherwise the only video file."""
    named = [p for p in call_dir.glob("source.*") if p.suffix.lower() in VIDEO_EXTS]
    if named:
        return named[0]
    videos = [p for p in call_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS]
    return videos[0] if len(videos) == 1 else None


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def load_segments(call_dir: Path, pad: int, duration: float):
    raw = json.loads((call_dir / "segments.json").read_text(encoding="utf-8"))
    segs = []
    for seg in raw:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        if end <= start:
            continue
        if pad:
            start = max(0.0, start - pad)
            end = (min(duration, end + pad) if duration else end + pad)
        segs.append({"title": seg.get("title", ""), "start": start, "end": end})
    return segs


def already_done(call_dir: Path) -> bool:
    clips = call_dir / "clips"
    return clips.is_dir() and any(clips.iterdir())


def export_call(call_dir: Path, pad: int, fcpxml: bool, outro):
    source = find_source(call_dir)
    if not source:
        return "skip-no-source", 0
    seg_path = call_dir / "segments.json"
    if not seg_path.exists():
        return "skip-no-segments", 0
    if already_done(call_dir):
        return "skip-already-done", 0

    duration = probe_duration(source)
    segs = load_segments(call_dir, pad, duration)
    if not segs:
        return "skip-empty-segments", 0

    seg_str = json.dumps(segs)

    out_zip = call_dir / "clips.zip"
    cmd = [sys.executable, EXPORT_MP4, str(source), seg_str, str(out_zip)]
    if outro:
        cmd.append(str(outro))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  FAILED mp4: {r.stderr.strip()[-400:]}", flush=True)
        return "export-failed", 0

    clips_dir = call_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(out_zip) as z:
        z.extractall(clips_dir)

    if fcpxml:
        out_xml = call_dir / "clips.fcpxml"
        rx = subprocess.run(
            [sys.executable, EXPORT_FCPXML, str(source), seg_str, str(out_xml)],
            capture_output=True, text=True,
        )
        if rx.returncode != 0:
            print(f"  WARN fcpxml: {rx.stderr.strip()[-300:]}", flush=True)

    return "ok", len(segs)


def main():
    ap = argparse.ArgumentParser(description="Batch-export clips across many call subfolders.")
    ap.add_argument("calls_dir", help="Directory whose subfolders are one-per-call.")
    ap.add_argument("--pad", type=int, default=0, help="Seconds of padding on each side of every clip.")
    ap.add_argument("--fcpxml", action="store_true", help="Also write a clips.fcpxml timeline per call.")
    ap.add_argument("--outro", default=None, help="Optional CTA/outro clip appended to every MP4.")
    args = ap.parse_args()

    calls_root = Path(args.calls_dir).resolve()
    if not calls_root.is_dir():
        print(f"Not a directory: {calls_root}", file=sys.stderr)
        sys.exit(1)
    if args.outro and not Path(args.outro).exists():
        print(f"Outro clip not found: {args.outro}", file=sys.stderr)
        sys.exit(1)

    call_dirs = sorted(p for p in calls_root.iterdir() if p.is_dir())
    summary = []
    for call_dir in call_dirs:
        print(f"=== {call_dir.name} ===", flush=True)
        status, count = export_call(call_dir, args.pad, args.fcpxml, args.outro)
        print(f"  {status}: {count} clips", flush=True)
        summary.append((call_dir.name, status, count))

    total = sum(c for _, st, c in summary if st == "ok")
    ok_calls = sum(1 for _, st, _ in summary if st == "ok")
    print("\n=== SUMMARY ===")
    for name, st, c in summary:
        print(f"{name:30s} {st:18s} {c}")
    print(f"\nTotal clips cut: {total} across {ok_calls} calls")


if __name__ == "__main__":
    main()
