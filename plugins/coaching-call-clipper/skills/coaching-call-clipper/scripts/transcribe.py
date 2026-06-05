#!/usr/bin/env python3
"""Transcribe a video/audio file to a word-level-timestamped transcript JSON.

Runs locally with faster-whisper. No API keys, nothing leaves the machine.
Uses the GPU (CUDA) when available and falls back to CPU automatically. On a Mac
there is no NVIDIA GPU, so it runs on CPU (int8); pick a faster model with --model
(see below) to keep that practical.

Usage:
    transcribe.py <video_or_audio_path> [output_json_path] [--model NAME]

If output_json_path is omitted, writes <input_basename>.transcript.json next to
the input file.

--model picks the faster-whisper model (auto-downloaded from Hugging Face on
first use). Default "large-v3" (best quality). On CPU / Mac, "turbo" is much
faster with quality close enough for clip selection; "distil-large-v3", "medium",
"small", "base", and "tiny" trade more quality for more speed. The default can
also be set with the CLIPPER_WHISPER_MODEL environment variable.

Output JSON shape (the contract the export scripts read):
{
  "status": "done",
  "duration": float,
  "language": "en",
  "model": "faster-whisper:large-v3",
  "transcript": [
    { "start": float, "end": float, "text": str,
      "words": [ { "word": str, "start": float, "end": float, "confidence": float } ] }
  ]
}
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_MODEL = os.environ.get("CLIPPER_WHISPER_MODEL", "large-v3")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def log(msg: str) -> None:
    """Progress goes to stderr so stdout stays clean for the result path."""
    print(msg, file=sys.stderr, flush=True)


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout.strip()


def get_audio_offset(path: str) -> float:
    """Audio stream start_time, added to every timestamp so they line up with
    the original video's timeline (what export_mp4 / export_fcpxml trim against)."""
    try:
        output = run_command([
            "ffprobe", "-v", "error",
            "-show_entries", "stream=start_time,codec_type",
            "-of", "json", path,
        ])
        for stream in json.loads(output).get("streams", []):
            if stream.get("codec_type") == "audio":
                val = stream.get("start_time")
                if val and val != "N/A":
                    return float(val)
    except Exception:
        pass
    return 0.0


def extract_audio(video_path: str) -> str:
    """Pull mono 16kHz audio out of a video into a temp wav for transcription."""
    tmp = tempfile.mktemp(suffix=".wav", prefix="clipseg-audio-")
    result = subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1",
         "-avoid_negative_ts", "make_zero", tmp, "-y"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr.strip()}")
    return tmp


def register_cuda_dlls() -> None:
    """Windows: pip-installed nvidia CUDA libs (cublas, cudnn) aren't on the DLL
    search path. Register each nvidia/*/bin dir so ctranslate2 can load them.
    No-op on machines without those packages (for example CPU-only or macOS)."""
    if sys.platform != "win32":
        return
    nvidia_root = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
    if not os.path.isdir(nvidia_root):
        return
    for pkg in os.listdir(nvidia_root):
        bin_dir = os.path.join(nvidia_root, pkg, "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def load_model(model_size: str):
    """Try GPU first, fall back to CPU with a clear note. On Mac the GPU attempt
    fails and it lands on CPU (int8), which ctranslate2 supports on Apple Silicon."""
    register_cuda_dlls()
    from faster_whisper import WhisperModel

    try:
        log(f"Loading {model_size} on GPU (CUDA, float16)...")
        return WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception as exc:
        log(f"GPU not available ({exc}); using CPU (int8). On a Mac this is normal; "
            f"transcription is slower, so consider --model turbo.")
        return WhisperModel(model_size, device="cpu", compute_type="int8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe a video/audio file to a word-level-timestamped transcript JSON.",
    )
    parser.add_argument("input", help="Path to the video or audio file.")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output JSON path (default: <input>.transcript.json).")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="faster-whisper model: large-v3 (default), turbo (fast, good for CPU/Mac), "
                             "distil-large-v3, medium, small, base, tiny.")
    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        log(f"File not found: {input_path}")
        sys.exit(1)

    ext = os.path.splitext(input_path)[1].lower()
    if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
        log(f"Unsupported file type: {ext}")
        sys.exit(1)

    output_path = args.output or (os.path.splitext(input_path)[0] + ".transcript.json")

    offset = get_audio_offset(input_path)
    if offset:
        log(f"Audio stream offset: {offset:.3f}s (applied to all timestamps)")

    extracted = None
    try:
        if ext in VIDEO_EXTENSIONS:
            log("Extracting audio with ffmpeg...")
            extracted = extract_audio(input_path)
            audio_path = extracted
        else:
            audio_path = input_path

        model = load_model(args.model)
        log("Transcribing (word-level timestamps, VAD filter on)...")
        segments_gen, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,  # skip silence -> avoids Whisper hallucinating text
        )

        transcript = []
        last_end = 0.0
        for seg in segments_gen:
            words = []
            for w in (seg.words or []):
                words.append({
                    "word": w.word,
                    "start": round(w.start + offset, 3),
                    "end": round(w.end + offset, 3),
                    "confidence": round(w.probability, 3),
                })
            transcript.append({
                "start": round(seg.start + offset, 2),
                "end": round(seg.end + offset, 2),
                "text": seg.text.strip(),
                "words": words,
            })
            last_end = seg.end + offset
            if len(transcript) % 25 == 0:
                log(f"  ...{len(transcript)} segments ({last_end/60:.1f} min in)")

        duration = round((info.duration or last_end) + offset, 2)
        result = {
            "status": "done",
            "duration": duration,
            "language": info.language or "en",
            "model": f"faster-whisper:{args.model}",
            "transcript": transcript,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        log(f"Done: {len(transcript)} segments, {duration/60:.1f} min.")
        # stdout = just the result path, for easy scripting
        print(output_path)
    finally:
        if extracted and os.path.exists(extracted):
            os.unlink(extracted)


if __name__ == "__main__":
    main()
