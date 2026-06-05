# coaching-call-clipper

A Claude Code skill that turns a long call recording (a coaching call, group Q&A,
hot-seat, webinar, or workshop) into standalone clips. One clip = one complete
thing: a single problem solved or a single idea taught, start to finish, ready to
post to YouTube.

It runs three stages locally and uses **no API keys**, so nothing leaves your
machine:

1. **Transcribe** the recording with faster-whisper (GPU when you have one, CPU
   otherwise).
2. **Select and segment** the transcript. Claude reads the call and decides which
   spans are real clips and where each one starts and ends, using the rubric in
   [`selecting-clips.md`](plugins/coaching-call-clipper/skills/coaching-call-clipper/references/selecting-clips.md).
3. **Export** each clip as its own MP4 with ffmpeg, plus an optional DaVinci
   Resolve / Final Cut timeline.

## Requirements

You install these once on your own machine:

- **Python 3.9 or newer** on your PATH.
- **ffmpeg** on your PATH (`ffmpeg -version` should print a version).
  - Windows: `winget install Gyan.FFmpeg` or `choco install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Debian / Ubuntu: `sudo apt install ffmpeg`
- An NVIDIA GPU is optional. With one, transcription takes minutes; without one it
  falls back to CPU, which works but is slower. macOS runs on CPU.

## Install as a Claude Code plugin

This is the simplest path. In Claude Code, run these two commands:

```
/plugin marketplace add theturtlemadeittothewater/coaching-call-clipper
/plugin install coaching-call-clipper@coaching-call-clipper
```

That registers this repo as a plugin marketplace and installs the skill. The repo
is public, so no GitHub login is needed. After installing, the skill is available
as `/coaching-call-clipper:coaching-call-clipper`, or you can just describe what
you want and Claude will use it.

## Install by copying the skill folder

If you would rather not use the plugin system:

```
git clone https://github.com/theturtlemadeittothewater/coaching-call-clipper.git
```

Then copy the folder
`plugins/coaching-call-clipper/skills/coaching-call-clipper` into your Claude Code
skills directory:

- Personal (all projects): `~/.claude/skills/` (Windows: `%USERPROFILE%\.claude\skills\`)
- One project only: that project's `.claude/skills/`

## First run

The first time you use the skill it builds a small Python environment for itself at
`~/.coaching-call-clipper/.venv` and downloads the Whisper model once (about
1.5 GB). You can let the skill do this automatically, or build it ahead of time by
running the setup script in the skill folder:

```
# Windows (PowerShell)
plugins\coaching-call-clipper\skills\coaching-call-clipper\setup.ps1

# macOS / Linux
bash plugins/coaching-call-clipper/skills/coaching-call-clipper/setup.sh
```

The environment lives in your home folder, not inside the skill, so it survives
plugin updates.

## Use it

Point Claude at a recording and say what you want, for example:

> Turn this call into clips: C:\Users\me\Downloads\group-call.mp4

Claude will transcribe it, propose the clips with start/end times and a one-line
reason for each, and (once you approve) export them. You can also drive the three
stages yourself; see
[the skill's instructions](plugins/coaching-call-clipper/skills/coaching-call-clipper/SKILL.md).

### What you get

Each processed call gets its own folder holding:

| File | What it is |
|------|------------|
| `source.mp4` | the recording |
| `call.transcript.json` | the word-level transcript |
| `segments.json` | the clip definitions (title, start, end) |
| `clips/` | the rendered per-clip MP4s as loose files |
| `clips.zip` | a zipped copy of `clips/` for transport |
| `clips.fcpxml` | an optional editing timeline |

Video editors link to loose files on disk, not to clips inside a zip, so unzip
`clips.zip` into a `clips/` folder before importing into an editor.

## How clips get chosen

Selection is the part that decides whether the output is worth posting, so it gets
the most care. The full rubric is in
[`selecting-clips.md`](plugins/coaching-call-clipper/skills/coaching-call-clipper/references/selecting-clips.md).
The short version:

- **One clip = one complete thing**, with a hook, a body, and a payoff. A span that
  has no payoff is not a clip.
- **Value is the only test.** A clip is kept because it delivers something a viewer
  can use, never because it hit a length. A tight 3-minute principle and a 30-minute
  teaching block are both fine.
- **The call's shape decides the cut.** A Q&A call clips one segment per person's
  problem; a teaching call clips one segment per topic or principle.
- **Privacy is your call, not the tool's.** The skill flags spans that touch
  someone's sensitive situation, make a named client look bad, or fall under a
  confidentiality agreement, then leaves the decision to you.

## Batch many calls

To process several recordings in one run, give each call its own subfolder with a
source video and a `segments.json`, then run the batch exporter (the skill can do
this for you):

```
<venv-python> plugins/coaching-call-clipper/skills/coaching-call-clipper/scripts/batch_export.py <calls-dir> --pad 180
```

`--pad 180` widens each clip by three minutes on each side so you can hand-trim the
exact in and out points in your editor. Drop the flag to cut tight to the
boundaries. The run skips calls that are already exported, so it is safe to repeat.

## What's in this repo

```
coaching-call-clipper/
├── .claude-plugin/
│   └── marketplace.json       lets the repo install itself as a plugin
├── plugins/
│   └── coaching-call-clipper/
│       ├── .claude-plugin/
│       │   └── plugin.json     plugin manifest
│       └── skills/
│           └── coaching-call-clipper/
│               ├── SKILL.md            the workflow Claude follows
│               ├── references/
│               │   ├── selecting-clips.md       the clip-selection rubric
│               │   └── segmentation-prompt.md   the segments.json contract
│               ├── scripts/
│               │   ├── transcribe.py            stage 1: local transcription
│               │   ├── export_mp4.py            stage 3: per-clip MP4s
│               │   ├── export_fcpxml.py         stage 3: editing timeline
│               │   └── batch_export.py          run many calls at once
│               ├── requirements.txt
│               ├── setup.ps1          Windows environment setup
│               └── setup.sh           macOS / Linux environment setup
├── examples/
│   └── segments.example.json
├── README.md
└── LICENSE
```

## Attribution

The two export scripts (`export_mp4.py`, `export_fcpxml.py`) are adapted from the
open-source SEGMENTER reference project. The transcription stage was rewritten to
run locally with faster-whisper instead of a paid transcription API, and the
segmentation stage was moved into Claude rather than a separate API call, so the
whole pipeline runs with no API keys.

## License

MIT. See [LICENSE](LICENSE).
