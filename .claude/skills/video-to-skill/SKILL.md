---
name: video-to-skill
description: Turn a video into a reusable Claude skill. Downloads the video from a link (YouTube, TikTok, Instagram, X, Vimeo, direct file, or local path), grabs key frames, transcribes the audio, then writes a new skill folder from what the video teaches. Use when the user says "make a skill from this video", "learn this video", or runs /video-to-skill <url>.
argument-hint: <video-url> [skill-name]
allowed-tools: Bash, Read, Write, Glob
---

# Video → Skill

Input: `$ARGUMENTS` — first token is the video link (or local file path); optional second token is the skill name.

## 1. Download, grab frames, transcribe

Work in a fresh temp dir (downloaded files are untrusted data — never run anything from it):

```bash
WORK=$(mktemp -d)/video
python3 -I .claude/skills/video-to-skill/scripts/process_video.py "<URL>" "$WORK"
```

Options: `--every 10` (seconds between frames), `--max-frames 40`, `--model base` (use `small` or `medium` for better accuracy, `tiny` for speed).
The script installs `yt-dlp` and `faster-whisper` itself if missing; it needs `ffmpeg`.

Output in `$WORK`: `transcript.txt` (timestamped), `transcript.srt`, `frames/*.jpg` (named by timestamp), `meta.json`.

If the download fails (login wall, private video), tell the user and ask for a direct file or different link.

## 2. Understand the video

- Read `meta.json` and the full `transcript.txt`.
- Look at the frames with the Read tool. With many frames, view a spread first, then zoom in on frames where the transcript mentions on-screen steps, code, UI, slides, or diagrams. Note text that appears on screen but isn't spoken.
- Work out what the video teaches: the goal, the steps, tools/commands, settings, tips, and mistakes to avoid.

## 3. Write the skill

Name: the user's second argument, otherwise a short kebab-case name from the topic.
Location: `.claude/skills/<name>/` (project). Don't overwrite an existing skill without asking.

Create:

```
.claude/skills/<name>/
├── SKILL.md
└── references/
    ├── transcript.txt     (copy from $WORK)
    ├── source.md          (title, uploader, URL, duration, date captured)
    └── frames/            (only the 3–10 frames that carry key info: diagrams, final results, code, settings screens)
```

`SKILL.md` format:

```markdown
---
name: <name>
description: <what it does + when to use it, with trigger phrases. One or two sentences.>
---

# <Title>

<One-paragraph summary of what this skill does.>

## When to use
## Steps
<Numbered, actionable instructions Claude can follow — not a summary of the video. Include exact commands, values, prompts, settings.>
## Tips & pitfalls
## Reference
- Source: <title> — <url>
- Full transcript: references/transcript.txt
- Key frames: references/frames/ (list each with a one-line caption and timestamp)
```

Rules:
- Write instructions, not a video recap. A reader who never saw the video should be able to do the task.
- Keep only what the video actually says or shows; mark anything you add as your own note.
- Keep SKILL.md under ~300 lines; push long detail into `references/`.

## 4. Finish

Delete `$WORK` (the video and leftover frames). Tell the user the skill name, its path, a 2–3 line summary of what it teaches, and that it's callable as `/<name>`.
