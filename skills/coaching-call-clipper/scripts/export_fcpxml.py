#!/usr/bin/env python3
"""Export segments as a single-track FCPXML for DaVinci Resolve / Final Cut.

Args: <video_path> <segments_json> <output_path>

segments_json: [{"title": str, "start": float, "end": float}, ...]
Passed as a STRING argument (not a file path).
"""

import json
import os
import subprocess
import sys
import urllib.parse
import xml.sax.saxutils as saxutils
from fractions import Fraction
from pathlib import Path
from typing import Optional, Tuple


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout.strip()


def tc_to_fraction(tc_string: Optional[str], frame_duration: Fraction) -> Fraction:
    """Convert HH:MM:SS:FF (or HH:MM:SS;FF for drop-frame) to seconds as a Fraction."""
    if not tc_string:
        return Fraction(0)
    drop_frame = ";" in tc_string
    parts = tc_string.replace(";", ":").split(":")
    if len(parts) != 4:
        return Fraction(0)
    try:
        h, m, s, f = (int(x) for x in parts)
    except ValueError:
        return Fraction(0)

    fps_actual = Fraction(1) / frame_duration
    fps_nominal = round(float(fps_actual))
    if fps_nominal <= 0:
        fps_nominal = 30

    if drop_frame and fps_nominal in (30, 60):
        # Standard SMPTE drop-frame: drop 2 frames every minute except every 10th
        drop_per_min = 2 if fps_nominal == 30 else 4
        total_minutes = h * 60 + m
        total_frames = (
            (h * 3600 + m * 60 + s) * fps_nominal
            + f
            - drop_per_min * (total_minutes - total_minutes // 10)
        )
    else:
        total_frames = (h * 3600 + m * 60 + s) * fps_nominal + f

    return Fraction(total_frames) * frame_duration


def probe_video(video_path: str) -> Tuple[Fraction, float, int, int, int, int, Fraction, bool]:
    """Returns (frame_duration, video_duration_s, width, height, audio_rate, audio_channels,
                asset_tc_offset, drop_frame)."""
    output = run_command([
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration:format_tags=timecode:"
        "stream=codec_type,r_frame_rate,width,height,sample_rate,channels:"
        "stream_tags=timecode",
        "-of", "json",
        video_path,
    ])
    data = json.loads(output)
    duration = float(data.get("format", {}).get("duration", 0) or 0)

    fps = None
    width, height = 1920, 1080
    audio_rate, audio_channels = 48000, 1
    timecode_str: Optional[str] = (data.get("format", {}).get("tags") or {}).get("timecode")

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and fps is None:
            r = stream.get("r_frame_rate") or "30/1"
            num, den = r.split("/")
            num_i, den_i = int(num), int(den)
            if num_i > 0 and den_i > 0:
                fps = Fraction(num_i, den_i)
            width = int(stream.get("width") or width)
            height = int(stream.get("height") or height)
            stream_tc = (stream.get("tags") or {}).get("timecode")
            if stream_tc and not timecode_str:
                timecode_str = stream_tc
        elif stream.get("codec_type") == "audio":
            audio_rate = int(stream.get("sample_rate") or audio_rate)
            audio_channels = int(stream.get("channels") or audio_channels)
        elif stream.get("codec_type") == "data":
            stream_tc = (stream.get("tags") or {}).get("timecode")
            if stream_tc and not timecode_str:
                timecode_str = stream_tc

    if fps is None or fps == 0:
        fps = Fraction(30, 1)

    frame_duration = Fraction(1) / fps
    asset_tc_offset = tc_to_fraction(timecode_str, frame_duration)
    drop_frame = bool(timecode_str and ";" in timecode_str)
    return frame_duration, duration, width, height, audio_rate, audio_channels, asset_tc_offset, drop_frame


def snap_to_frame(seconds: float, frame_duration: Fraction) -> Fraction:
    """Snap a float seconds value to the nearest frame boundary, return as exact Fraction."""
    if seconds <= 0:
        return Fraction(0)
    frames = round(seconds / float(frame_duration))
    return Fraction(frames) * frame_duration


def time_str(f: Fraction) -> str:
    if f == 0:
        return "0s"
    if f.denominator == 1:
        return f"{f.numerator}s"
    return f"{f.numerator}/{f.denominator}s"


def file_url(path: str) -> str:
    return "file://" + urllib.parse.quote(os.path.abspath(path), safe="/")


def fps_label(frame_duration: Fraction) -> str:
    fps = float(Fraction(1) / frame_duration)
    rounded = round(fps, 2)
    return str(int(rounded)) if rounded.is_integer() else str(rounded)


def build_fcpxml(
    video_path: str,
    segments: list,
    frame_duration: Fraction,
    video_duration_s: float,
    width: int,
    height: int,
    audio_rate: int,
    audio_channels: int,
    asset_tc: Fraction,
    drop_frame: bool,
) -> str:
    name = Path(video_path).stem
    src = file_url(video_path)
    fd_str = time_str(frame_duration)
    asset_start_str = time_str(asset_tc)
    asset_dur_str = time_str(snap_to_frame(video_duration_s, frame_duration))
    tc_format = "DF" if drop_frame else "NDF"

    clip_lines = []
    timeline_offset = Fraction(0)
    for i, seg in enumerate(segments):
        start_f = snap_to_frame(float(seg.get("start", 0)), frame_duration)
        end_f = snap_to_frame(float(seg.get("end", 0)), frame_duration)
        dur_f = end_f - start_f
        if dur_f <= 0:
            dur_f = frame_duration

        title = saxutils.escape(str(seg.get("title") or f"Segment {i + 1}"))

        # Both offset (timeline position) and start (source position) are absolute
        # timecodes in the asset's TC space, so they must include the asset's TC base
        # offset or Resolve reports "Media Offline" (it can't find a frame at that TC).
        clip_offset = asset_tc + timeline_offset
        clip_start = asset_tc + start_f

        clip_lines.append(
            '          <asset-clip ref="r2" '
            f'offset="{time_str(clip_offset)}" '
            f'name="{title}" '
            f'start="{time_str(clip_start)}" '
            f'duration="{time_str(dur_f)}"/>'
        )
        timeline_offset += dur_f

    sequence_dur_str = time_str(timeline_offset)
    sequence_tc_start_str = time_str(asset_tc)
    label = fps_label(frame_duration)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE fcpxml>\n'
        '<fcpxml version="1.10">\n'
        '  <resources>\n'
        f'    <format id="r1" name="FFVideoFormat{height}p{label}" '
        f'frameDuration="{fd_str}" width="{width}" height="{height}" '
        'colorSpace="1-1-1 (Rec. 709)"/>\n'
        f'    <asset id="r2" name="{saxutils.escape(name)}" src="{src}" '
        f'start="{asset_start_str}" duration="{asset_dur_str}" '
        f'hasVideo="1" hasAudio="1" '
        f'format="r1" audioSources="1" audioChannels="{audio_channels}" '
        f'audioRate="{audio_rate}"/>\n'
        '  </resources>\n'
        '  <library>\n'
        f'    <event name="Segments">\n'
        f'      <project name="{saxutils.escape(name)}_segmented">\n'
        f'        <sequence format="r1" duration="{sequence_dur_str}" '
        f'tcStart="{sequence_tc_start_str}" tcFormat="{tc_format}" '
        'audioLayout="stereo" audioRate="48k">\n'
        '          <spine>\n'
        + "\n".join(clip_lines) + "\n"
        '          </spine>\n'
        '        </sequence>\n'
        '      </project>\n'
        '    </event>\n'
        '  </library>\n'
        '</fcpxml>\n'
    )


def main():
    if len(sys.argv) != 4:
        print(
            json.dumps({"error": "Usage: export_fcpxml.py <video_path> <segments_json> <output_path>"}),
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    video_path = sys.argv[1]
    segments_json = sys.argv[2]
    output_path = sys.argv[3]

    if not os.path.exists(video_path):
        print(json.dumps({"error": f"Video not found: {video_path}"}), file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        segments = json.loads(segments_json)
        if not isinstance(segments, list) or not segments:
            raise ValueError("segments must be a non-empty list")

        fd, dur, w, h, ar, ac, tc, df = probe_video(video_path)
        xml_text = build_fcpxml(video_path, segments, fd, dur, w, h, ar, ac, tc, df)
        Path(output_path).write_text(xml_text, encoding="utf-8")
        print(output_path)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
