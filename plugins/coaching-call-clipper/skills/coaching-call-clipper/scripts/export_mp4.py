#!/usr/bin/env python3
"""Render each kept segment of the main video as its own MP4 (segment + optional
CTA outro), then bundle them into a single ZIP.

Args: <main_video> <segments_json> <output_zip> [outro_path]

segments_json: [{"title": str, "start": float, "end": float}, ...]
Passed as a STRING argument (not a file path).

The outro (if provided) is normalized to the main video's resolution, frame rate,
sample rate and channel layout so the concat filter can splice it without complaint.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-15:]
        raise RuntimeError("\n".join(tail) or "ffmpeg failed")
    return result.stdout.strip()


def probe(path):
    output = run_command([
        "ffprobe", "-v", "error",
        "-show_entries",
        "stream=codec_type,r_frame_rate,width,height,sample_rate,channels",
        "-of", "json",
        path,
    ])
    data = json.loads(output)
    w, h = 1920, 1080
    fps_num, fps_den = 30, 1
    sample_rate, channels = 48000, 2
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            w = int(stream.get("width") or w)
            h = int(stream.get("height") or h)
            r = stream.get("r_frame_rate") or "30/1"
            num, den = r.split("/")
            num_i, den_i = int(num), int(den)
            if num_i > 0 and den_i > 0:
                fps_num, fps_den = num_i, den_i
        elif stream.get("codec_type") == "audio":
            sample_rate = int(stream.get("sample_rate") or sample_rate)
            channels = int(stream.get("channels") or channels)
    return w, h, fps_num, fps_den, sample_rate, channels


def safe_name(s: str) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", "_", s).strip().strip(".")
    return cleaned or "segment"


def render_one(main_video, outro_path, start, end, v_norm, a_norm, output_path):
    if outro_path:
        filter_graph = (
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,{v_norm}[v0];"
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{a_norm}[a0];"
            f"[1:v]setpts=PTS-STARTPTS,{v_norm}[v1];"
            f"[1:a]asetpts=PTS-STARTPTS,{a_norm}[a1];"
            f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]"
        )
        inputs = ["-i", main_video, "-i", outro_path]
    else:
        filter_graph = (
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,{v_norm}[outv];"
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{a_norm}[outa]"
        )
        inputs = ["-i", main_video]

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]
    run_command(cmd)


def main():
    if len(sys.argv) not in (4, 5):
        print(
            json.dumps({"error": "Usage: export_mp4.py <main> <segments_json> <output_zip> [outro]"}),
            file=sys.stderr, flush=True,
        )
        sys.exit(1)

    main_video = sys.argv[1]
    segments_json = sys.argv[2]
    output_zip = sys.argv[3]
    outro_path = sys.argv[4] if len(sys.argv) == 5 else None

    if not os.path.exists(main_video):
        print(json.dumps({"error": f"Main video not found: {main_video}"}), file=sys.stderr, flush=True)
        sys.exit(1)
    if outro_path and not os.path.exists(outro_path):
        print(json.dumps({"error": f"Outro clip not found: {outro_path}"}), file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        segments = json.loads(segments_json)
        if not isinstance(segments, list) or not segments:
            raise ValueError("segments must be a non-empty list")

        w, h, fps_num, fps_den, sr, ch = probe(main_video)
        ch_layout = "mono" if ch == 1 else "stereo"
        v_norm = (
            f"scale={w}:{h}:flags=bicubic,setsar=1,"
            f"fps={fps_num}/{fps_den},format=yuv420p"
        )
        a_norm = f"aresample={sr},aformat=channel_layouts={ch_layout}"

        produced = []
        with tempfile.TemporaryDirectory(prefix="clipper-mp4-") as work_dir:
            pad = max(2, len(str(len(segments))))
            for i, seg in enumerate(segments):
                start = float(seg.get("start", 0))
                end = float(seg.get("end", 0))
                if end <= start:
                    continue
                title = safe_name(str(seg.get("title") or f"segment_{i + 1}"))
                arcname = f"{str(i + 1).zfill(pad)} - {title}.mp4"
                temp_path = os.path.join(work_dir, arcname)
                render_one(main_video, outro_path, start, end, v_norm, a_norm, temp_path)
                produced.append((arcname, temp_path))

            if not produced:
                raise ValueError("No valid segments (all empty or zero length)")

            with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_STORED) as zf:
                for arcname, src in produced:
                    zf.write(src, arcname=arcname)

        print(output_zip)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
