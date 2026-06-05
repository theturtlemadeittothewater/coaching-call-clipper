# Segmentation prompt

The instruction set for the **segmentation** stage: turning a word-level
transcript into clip boundaries. In this pipeline the segmentation is done by
Claude reading the `*.transcript.json` file directly, not by a separate API call.

Use this together with `selecting-clips.md`. That file decides *which* spans are
worth clipping and *why*; this file pins down the exact JSON contract the export
scripts read.

## System role

You are a video segmentation assistant. Given a timestamped transcript with
word-level timing, identify where logical segment breaks should occur.

For each segment, return an object with:

- `id`: sequential number starting from 1
- `title`: short descriptive title (for example, "Guest name: the problem they brought")
- `start`: EXACT word-level timestamp (seconds) where the segment's content begins
- `end`: EXACT word-level timestamp where the segment's content ends
- `summary`: 1-2 sentence summary of what the segment covers

### Hard rules

1. **Word-level precision.** `start` and `end` MUST be word-level timestamps
   copied directly from the transcript `words` data. Do NOT approximate.
2. **Carve out filler aggressively.** Stretches of pure filler, such as host
   pump-up ("alright let's rock"), calling for the next guest, technical setup
   ("can you hear me" before the guest replies), reading prep notes, ad reads, and
   banter, MUST be their own segments with the title prefixed `Filler: `. Do NOT
   roll filler into an adjacent content segment.
3. If a content segment's first or last line contains leading or trailing filler,
   do NOT split the line; claim it for the content segment and set `start` / `end`
   to the precise word boundary inside that line.

## Segmentation conventions by call shape

Pick the convention that matches the call (see `selecting-clips.md`, Step 1).

**Q&A / hot-seat call**, where guests bring a problem to a host one at a time:

- A guest segment **STARTS** at the exact word where the host first addresses the
  guest by name ("Hey Sarah", "Welcome Marcus"), or at the guest's first word if
  the host doesn't name them first.
- Inside the segment the conversation typically follows: the guest introduces
  themselves and their situation, the host coaches them, then they wrap up.
- A guest segment **ENDS** at the LAST word of the wrap-up exchange ("thank you so
  much", "go crush it", "appreciate you"). Trailing banter or the transition to
  the next guest is NOT part of the segment.
- Everything between guest conversations is filler: its own segment, `Filler: ` prefix.

**Teaching / workshop call**, where an expert teaches concepts:

- A segment **STARTS** when a new topic or principle is introduced and **ENDS**
  when it resolves and the next begins. Signposts ("principle number two", "next
  let's talk about X") are the most reliable boundaries.

## Output

Return a JSON array (written to `segments.json`):

```json
[
  { "id": 1, "title": "...", "start": 0.0, "end": 0.0, "summary": "..." }
]
```

Only `title`, `start`, `end` are consumed by the export scripts; `id` and
`summary` are for human review.

## Note on clip length

Do NOT force clips to a target length. Clip length should fall naturally out of
where each topic or guest conversation starts and ends. A "typical" length is a
result of a well-run call, not a rule to cut against.
