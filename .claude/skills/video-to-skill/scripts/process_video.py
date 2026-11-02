#!/usr/bin/env python3
"""Download a video, grab key frames, and transcribe its audio.

Usage: process_video.py <url-or-file> <out_dir> [--every SECONDS] [--max-frames N] [--model SIZE]

Writes into out_dir:
  video.*          the downloaded video
  frames/          JPEG frames named by timestamp (frame_0001_t00m12s.jpg)
  transcript.txt   timestamped transcript
  transcript.srt   subtitles
  meta.json        title, uploader, duration, url, frame list
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path


def need(pkg, module=None):
    try:
        __import__(module or pkg)
    except ImportError:
        print(f"Installing {pkg}...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


def ts(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def srt_ts(sec):
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def download(src, out):
    if Path(src).exists():
        dst = out / ("video" + Path(src).suffix)
        shutil.copy(src, dst)
        return dst, {"title": Path(src).stem, "url": src}
    need("yt-dlp", "yt_dlp")
    import yt_dlp
    opts = {
        "outtmpl": str(out / "video.%(ext)s"),
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "quiet": True, "no_warnings": True, "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(src, download=True)
    except Exception as e:
        sys.exit(f"Download failed: {str(e).splitlines()[0]}\n"
                 "Check the link is public, or download the file yourself and pass its path.")
    files = [p for p in out.glob("video.*") if p.suffix not in (".part", ".ytdl")]
    if not files:
        sys.exit("Download failed: no video file produced")
    meta = {k: info.get(k) for k in ("title", "uploader", "duration", "description", "webpage_url")}
    meta["url"] = src
    return files[0], meta


def duration(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def grab_frames(video, out, every, max_frames, dur):
    fdir = out / "frames"
    fdir.mkdir(exist_ok=True)
    if dur and max_frames and dur / every > max_frames:
        every = dur / max_frames  # spread frames evenly across long videos
    frames, t, i = [], 0.0, 1
    while (not dur or t < dur) and i <= max_frames:
        name = f"frame_{i:04d}_t{int(t)//60:02d}m{int(t)%60:02d}s.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "3",
                        str(fdir / name)], check=False)
        if (fdir / name).exists():
            frames.append({"file": f"frames/{name}", "time": ts(t)})
        elif not dur:
            break
        t += every
        i += 1
    return frames


def transcribe(video, out, model_size):
    audio = out / "audio.wav"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1",
                        "-ar", "16000", str(audio)])
    if r.returncode != 0 or not audio.exists():
        (out / "transcript.txt").write_text("(no audio track)\n")
        return ""
    need("faster-whisper", "faster_whisper")
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(model_size, device="auto", compute_type="int8")
        segs, info = model.transcribe(str(audio), vad_filter=True)
        txt, srt = [], []
        for n, s in enumerate(segs, 1):
            txt.append(f"[{ts(s.start)}] {s.text.strip()}")
            srt.append(f"{n}\n{srt_ts(s.start)} --> {srt_ts(s.end)}\n{s.text.strip()}\n")
    except Exception as e:
        msg = f"Transcription failed: {str(e).splitlines()[0] if str(e) else type(e).__name__}"
        print(msg + " (frames were still saved)", file=sys.stderr)
        (out / "transcript.txt").write_text(f"({msg})\n")
        audio.unlink(missing_ok=True)
        return None
    (out / "transcript.txt").write_text("\n".join(txt) + "\n")
    (out / "transcript.srt").write_text("\n".join(srt))
    audio.unlink()
    return info.language


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--every", type=float, default=10, help="seconds between frames")
    ap.add_argument("--max-frames", type=int, default=40)
    ap.add_argument("--model", default="base", help="whisper size: tiny/base/small/medium/large-v3")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    print("Downloading...", file=sys.stderr)
    video, meta = download(a.src, out)
    dur = duration(video)
    meta["duration"] = meta.get("duration") or dur
    print("Grabbing frames...", file=sys.stderr)
    meta["frames"] = grab_frames(video, out, a.every, a.max_frames, dur)
    print("Transcribing...", file=sys.stderr)
    meta["language"] = transcribe(video, out, a.model)
    (out / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({"out_dir": str(out), "video": str(video), "title": meta.get("title"),
                      "duration": meta["duration"], "frames": len(meta["frames"]),
                      "language": meta["language"]}, indent=2))


if __name__ == "__main__":
    main()
