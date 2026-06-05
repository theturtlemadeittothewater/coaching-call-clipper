---
name: coaching-call-clipper
description: Turn a long call recording (coaching call, group Q&A, hot-seat, webinar, workshop) into standalone clips, one per problem solved or idea taught, ready to post to YouTube. Runs locally with faster-whisper transcription, Claude-native segment selection, and ffmpeg export. No API keys, nothing leaves the machine. Use when the user wants to clip a call or video, cut highlights from a recording, or batch-produce clips across many recordings.
---

# coaching-call-clipper

Turn a long recording into **standalone clips**, each a single complete idea or a
single problem solved, postable as-is. One clip = one complete thing, with a hook,
a body, and a payoff.

The pipeline has three stages and uses **no API keys**, so nothing leaves the
machine:

```
  call.mp4
     |
     v   1. transcribe   (local faster-whisper, GPU or CPU)
  call.transcript.json
     |
     v   2. select + segment   (you read the transcript and apply the rubric)
  segments.json
     |
     v   3. export   (ffmpeg: per-clip MP4s, optionally a DaVinci Resolve timeline)
  clips/  +  clips.zip
```

## When to use

- The user wants to cut clips or highlights from a call, coaching session,
  webinar, or workshop recording.
- The user wants to batch-produce clips from many recordings at once.

## When not to use

- Short-form vertical reels with captions and effects. This produces clean
  horizontal clips for a human to finish in an editor; it does not style or caption.
- Live editing of an existing edit. This selects spans and cuts source video.

## Prerequisites

Install these once on the user's machine:

- **Python 3.9+** on PATH.
- **ffmpeg** on PATH (`ffmpeg -version` must work). Install with
  `winget install Gyan.FFmpeg` or `choco install ffmpeg` (Windows),
  `brew install ffmpeg` (macOS), or `sudo apt install ffmpeg` (Debian/Ubuntu).
- **A GPU is optional.** An NVIDIA GPU makes transcription fast (minutes); without
  one it runs on CPU, which is slower but works. A Mac (Apple Silicon included)
  runs on CPU; use `--model turbo` in Step 1 to keep that practical.

## Step 0: Make sure the environment is ready

Do this first, on every run. This skill bundles its Python scripts in the
`scripts/` folder next to this file. Resolve that absolute path first; call it
`SKILL_DIR`.

The Python interpreter comes from a fixed, user-level virtual environment so it
survives plugin updates and works whether the skill was installed as a plugin or
copied by hand:

- **Windows:** `%USERPROFILE%\.coaching-call-clipper\.venv\Scripts\python.exe`
- **macOS / Linux:** `$HOME/.coaching-call-clipper/.venv/bin/python`

Call this path `VENV_PY`. Before doing anything else:

1. If `VENV_PY` does not exist, bootstrap it by running the bundled setup script
   (`SKILL_DIR/setup.ps1` on Windows, `SKILL_DIR/setup.sh` on macOS/Linux). It
   creates the venv, installs `requirements.txt`, and (on Windows/Linux with an
   NVIDIA GPU) installs the CUDA wheels. This is a one-time step; it can take a few
   minutes the first time while it downloads packages.
2. Confirm `ffmpeg -version` runs. If not, stop and tell the user to install
   ffmpeg (see Prerequisites) before continuing.

Run every Python command below with `VENV_PY`, not the system `python`.

## Step 1: Transcribe

```
<VENV_PY> "<SKILL_DIR>/scripts/transcribe.py" "<path-to-call.mp4>"
```

Writes `call.transcript.json` next to the input. The first run downloads the
chosen model once.

**Pick the model for the machine** with `--model <name>`:

- **NVIDIA GPU (Windows/Linux):** the default `large-v3` is fine; a long call
  takes minutes.
- **Mac, or any machine with no NVIDIA GPU:** transcription runs on CPU, so use
  `--model turbo`. It is far faster than `large-v3` on CPU and the quality is more
  than enough for choosing clip boundaries. `--model small` is faster still for a
  rough first pass.

Example on a Mac:

```
<VENV_PY> "<SKILL_DIR>/scripts/transcribe.py" "<path-to-call.mp4>" --model turbo
```

If the user already has a word-level transcript in the contract shape (see the
transcribe.py docstring), skip this stage. That is the fastest path on any machine
when a transcript already exists, for example one exported by a Mac transcription
app that includes word timestamps.

## Step 2: Select and segment

Read `references/selecting-clips.md` and `references/segmentation-prompt.md` in
this skill folder, then read the transcript and decide the clips.

`references/selecting-clips.md` is the craft: what counts as a standalone clip,
how to read the call's shape (Q&A, teaching, or mixed), how to triage for worth,
and how to set exact boundaries. Apply it carefully; selection is where the
quality of the output is won or lost.

Write `segments.json` next to the call:

```json
[
  { "id": 1, "title": "Guest name: the problem they brought", "start": 92.4, "end": 701.8 }
]
```

Only `title`, `start`, `end` are read by the export scripts. Keep titles free of
characters the filesystem dislikes (`/ \ : * ? " < > |`); the exporter replaces
anything unusual with `_`, but clean titles read better as filenames.

Show the proposed clips to the user before exporting unless they have told you to
just run it. Boundaries are cheap to adjust on paper and expensive to re-cut.

## Step 3: Export

The export scripts take the segments JSON as a **string argument**, not a file
path. Drop any `Filler:` segments from the list before exporting; keep only the
content clips.

Per-clip MP4s, bundled into a zip:

```
<VENV_PY> "<SKILL_DIR>/scripts/export_mp4.py" "<call.mp4>" "<segments-json-string>" "<out-dir>/clips.zip"
```

Optionally also a DaVinci Resolve / Final Cut timeline:

```
<VENV_PY> "<SKILL_DIR>/scripts/export_fcpxml.py" "<call.mp4>" "<segments-json-string>" "<out-dir>/clips.fcpxml"
```

After exporting MP4s, unzip `clips.zip` into a `clips/` folder. Editors link to
loose files on disk, never to clips inside a zip; the zip is for transport and
archive only.

## Batch mode

To process many calls at once, put each call in its own subfolder with a source
video and a `segments.json`, then:

```
<VENV_PY> "<SKILL_DIR>/scripts/batch_export.py" "<calls-dir>" --pad 180
```

It exports each subfolder, unzips into `clips/`, and skips calls already done, so
it is safe to re-run. See the script's docstring for the expected layout and all
flags (`--pad`, `--fcpxml`, `--outro`).

## Output conventions

Give each processed call its own folder (kebab-case, for example
`calls/aug1-mastermind/`) and keep all of that call's artifacts in it:

| File | What |
|------|------|
| `source.mp4` | the call recording |
| `call.transcript.json` | word-level transcript from `transcribe.py` |
| `segments.json` | the clip definitions fed to the export scripts |
| `clips/` | the rendered per-clip MP4s as loose files (the editable form) |
| `clips.zip` | zipped copy of `clips/` (transport and archive only) |
| `clips.fcpxml` | optional editing timeline |

## Operating guidance

These are sensible defaults; the user can override any of them.

- **The goal is a high-value demonstration.** Marketing clips work when the viewer
  thinks "this person clearly knows how to solve my problem." Prefer spans where
  the expert delivers a concrete, specific solution. If the user's intent is to
  position themselves as the authority (the common case), lean toward spans where
  they lead the value, not spans where they are the one being coached.
- **Length follows content, never a target.** A tight 3-minute principle and a
  30-minute teaching block are both correct clips if that is where the idea begins
  and ends. Do not cut a flowing piece short to fit a window, and do not pad a weak
  one to reach one.
- **Volume over dedup, by default.** Most viewers have never seen this person
  before, so the same lesson taught two different ways is two useful clips, not a
  duplicate. Do not suppress a strong clip for thematic overlap unless the user
  asks you to dedupe.
- **Padding for hand-trimming.** When the user plans to finish clips in an editor,
  widen each clip by a couple of minutes on each side (`--pad` in batch mode, or
  pad the boundaries when writing `segments.json`) so they can find the exact in
  and out point themselves. When the clips are meant to post as-is, cut tight.
- **Privacy is the user's judgment call, not an automated filter.** Flag spans
  that touch a participant's sensitive personal situation, make a named client look
  bad, fall under a confidentiality agreement, or expose a specific business's
  private numbers, then let the user decide. Do not invent a blanket rule that
  auto-rejects them.

## References

- `references/selecting-clips.md`: the selection rubric (read before segmenting).
- `references/segmentation-prompt.md`: the exact `segments.json` contract and the
  per-call-shape conventions.
