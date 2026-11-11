#!/usr/bin/env python3
"""
watch.py: turn a video (URL or local file) into evidence a model can watch.

Usage:
  python3 watch.py <url-or-file> [--out DIR] [--fps N] [--max-frames N] [--start S] [--end S]
  python3 watch.py <url-or-file> --still T [T ...]     full-size frames only, for zooming into texture

Writes to DIR (default: $TMPDIR/watch/<slug>):
  video.mp4        the video (downloaded, or a link to the local file)
  sheet_NN.jpg     contact sheets, 12 timestamped frames each (4 x 3)
  frames/          the single frames (640 px), named by full-video second (e.g. 003.50.jpg)
  stills/          full-size frames from --still
  audio.json       the full loudness curve and every 4 dB jump
  report.md        metadata, scene cuts, sheet list, captions, audio summary

Audio:
  Measured locally: loudness over time, steady beat or not, silence. Nothing leaves your machine
  except the video download.

Needs: python3, numpy, yt-dlp (for URLs), ffmpeg (system, or pip imageio-ffmpeg).
Works the same from Claude Code and Codex.
Inspired by the /watch idea in bradautomates/claude-video (github.com/bradautomates/claude-video); written from scratch.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

SHEET_COLS, SHEET_ROWS = 4, 3


def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("No ffmpeg. Install it (brew install ffmpeg) or: python3 -m pip install --user imageio-ffmpeg")


FF = None


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def is_url(s):
    return bool(re.match(r"https?://", s))


def slugify(s):
    base = s if is_url(s) else os.path.splitext(os.path.basename(s.rstrip("/")))[0]
    base = re.sub(r"https?://(www\.)?", "", base)
    return re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")[:60] or "video"


# ---------- fetch ----------

def fetch(src, out, start=None, end=None):
    meta = {"source": src}
    video = os.path.join(out, "video.mp4")
    if is_url(src):
        if not shutil.which("yt-dlp"):
            sys.exit("yt-dlp not found. Install: python3 -m pip install --user yt-dlp (or brew install yt-dlp)")
        cmd = ["yt-dlp", "--ffmpeg-location", FF, "--no-playlist",
               "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
               "--merge-output-format", "mp4",
               "--write-subs", "--write-auto-subs", "--sub-langs", "en,en-orig,en-US,en-GB", "--ignore-errors", "--sub-format", "vtt",
               "--write-info-json", "-o", os.path.join(out, "video.%(ext)s")]
        if start is not None or end is not None:
            # a window is cut locally after download; 720p keeps long videos quick
            cmd[cmd.index("-f") + 1] = cmd[cmd.index("-f") + 1].replace("1080", "720")
        cmd.append(src)
        r = run(cmd)
        if not os.path.exists(video) or "Video:" not in run([FF, "-i", video]).stderr:
            sys.exit("Download failed (no video stream):\n" + (r.stderr or r.stdout)[-1500:])
        info = os.path.join(out, "video.info.json")
        if os.path.exists(info):
            d = json.load(open(info))
            for k in ("title", "uploader", "upload_date", "duration", "webpage_url", "description"):
                if d.get(k):
                    meta[k] = d[k]
            os.remove(info)
    else:
        src = os.path.abspath(os.path.expanduser(src))
        if not os.path.exists(src):
            sys.exit(f"No such file: {src}")
        if os.path.lexists(video):
            os.remove(video)
        os.symlink(src, video)
        meta["title"] = os.path.basename(src)
    return video, meta


def probe(video):
    r = run([FF, "-i", video])
    txt = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    v = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", txt)
    f = re.search(r"([\d.]+) fps", txt)
    return {"duration": round(dur, 2),
            "width": int(v.group(1)) if v else None, "height": int(v.group(2)) if v else None,
            "fps": float(f.group(1)) if f else None,
            "has_audio": "Audio:" in txt}


# ---------- frames ----------

def auto_fps(dur, max_frames):
    if dur <= 15:
        fps = 4
    elif dur <= 60:
        fps = 2
    else:
        fps = max_frames / dur
    fps = min(fps, max_frames / max(dur, 0.1))
    return max(fps, 0.02)


def scene_cuts(video, threshold=0.3):
    r = run([FF, "-i", video, "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"])
    return [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def extract_frames(video, out, fps, offset=0):
    """Frames from the (already windowed) video, named by full-video time: offset + i / fps."""
    fdir = os.path.join(out, "frames")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    cmd = [FF, "-loglevel", "error", "-i", video,
           "-vf", f"fps={fps},scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)'", "-q:v", "3",
           os.path.join(fdir, "f_%05d.jpg")]
    r = run(cmd)
    if r.returncode != 0:
        sys.exit("Frame extraction failed: " + r.stderr[-800:])
    files = sorted(os.listdir(fdir))
    named = []
    for i, f in enumerate(files):
        t = offset + i / fps
        new = f"{t:06.2f}.jpg"
        os.rename(os.path.join(fdir, f), os.path.join(fdir, new))
        named.append((t, os.path.join(fdir, new)))
    return named


def make_sheets(frames, out):
    for f in os.listdir(out):
        if f.startswith("sheet_"):
            os.remove(os.path.join(out, f))
    per = SHEET_COLS * SHEET_ROWS
    sheets = []
    for n in range(0, len(frames), per):
        chunk = frames[n:n + per]
        label = os.path.join(out, f"sheet_{len(sheets) + 1:02d}.jpg")
        # label each tile with its timestamp, then tile
        inputs, filters = [], []
        for i, (t, p) in enumerate(chunk):
            inputs += ["-i", p]
            mm, ss = divmod(t, 60)
            txt = f"{int(mm)}\\:{ss:05.2f}"
            filters.append(f"[{i}:v]scale='if(gt(iw,ih),480,-2)':'if(gt(iw,ih),-2,560)',drawtext=text='{txt}':x=8:y=8:fontsize=22:"
                           f"fontcolor=white:box=1:boxcolor=black@0.65[t{i}]")
        tiles = "".join(f"[t{i}]" for i in range(len(chunk)))
        cols = min(SHEET_COLS, len(chunk))
        layout = "|".join(f"{'+'.join(['w0'] * (i % cols)) or '0'}_{'+'.join(['h0'] * (i // cols)) or '0'}"
                          for i in range(len(chunk)))
        fc = ";".join(filters) + f";{tiles}xstack=inputs={len(chunk)}:layout={layout}:fill=black[o]" \
            if len(chunk) > 1 else filters[0].replace(f"[t0]", "[o]")
        r = run([FF, "-loglevel", "error", "-y"] + inputs + ["-filter_complex", fc, "-map", "[o]",
                                                             "-frames:v", "1", "-q:v", "3", label])
        if r.returncode != 0:
            sys.exit("Sheet build failed: " + r.stderr[-800:])
        sheets.append((chunk[0][0], chunk[-1][0], label))
    return sheets


# ---------- captions ----------

def read_captions(out, start=None, end=None):
    vtts = sorted(f for f in os.listdir(out) if f.endswith(".vtt"))
    if not vtts:
        return None
    lines, last = [], None
    cur, keep = None, True
    for ln in open(os.path.join(out, vtts[0]), encoding="utf-8", errors="replace"):
        m = re.match(r"(\d\d):(\d\d):(\d\d)[.,]\d+\s*-->", ln)
        if m:
            sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            cur = f"{sec // 60}:{sec % 60:02d}"
            keep = (start is None or sec >= start - 1) and (end is None or sec <= end)
            continue
        t = re.sub(r"<[^>]+>", "", ln).strip()
        if not t or t.startswith(("WEBVTT", "Kind:", "Language:")) or t == last or not keep:
            continue
        lines.append(f"[{cur}] {t}")
        last = t
    return "\n".join(lines) if lines else None


# ---------- audio ----------

def audio_facts(video, offset=0):
    import numpy as np
    sr = 22050
    r = subprocess.run([FF, "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.int16).astype(float) / 32768
    if len(x) < sr // 2:
        return None
    w = sr // 2
    curve = []
    for i in range(0, len(x) - w + 1, w):
        rms = np.sqrt(np.mean(x[i:i + w] ** 2))
        curve.append((round(offset + i / sr, 1), round(20 * np.log10(rms + 1e-9), 1)))
    db = np.array([c[1] for c in curve])
    silent = float(np.mean(db < -50))
    # onset envelope (spectral flux) for a steady-beat check
    hop, n = 512, 1024
    frames = [x[i:i + n] * np.hanning(n) for i in range(0, len(x) - n, hop)]
    beat = None
    if len(frames) > 64:
        spec = np.abs(np.fft.rfft(np.array(frames), axis=1))
        flux = np.maximum(0, np.diff(spec, axis=0)).sum(axis=1)
        flux = (flux - flux.mean()) / (flux.std() + 1e-9)
        ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
        ac /= ac[0] + 1e-9
        fr = sr / hop
        lo, hi = int(fr * 60 / 180), int(fr * 60 / 60)  # 60 to 180 BPM
        if hi < len(ac):
            k = lo + int(np.argmax(ac[lo:hi]))
            strength = float(ac[k])
            beat = {"bpm": round(60 * fr / k), "strength": round(strength, 2),
                    "steady": strength > 0.5, "short": len(x) / sr < 20}
    # notable changes: jumps of 4 dB or more between neighbouring half-seconds
    jumps = [(curve[i][0], round(db[i] - db[i - 1], 1)) for i in range(1, len(db)) if abs(db[i] - db[i - 1]) >= 4]
    return {"curve": curve, "silent_share": round(silent, 2), "beat": beat, "jumps": jumps,
            "mean_db": round(float(db.mean()), 1), "peak_db": round(float(db.max()), 1)}


# ---------- report ----------

def fmt_t(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}"


def main():
    global FF
    ap = argparse.ArgumentParser(description="Turn a video into timestamped frames and audio facts.")
    ap.add_argument("src")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--max-frames", type=int, default=72)
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--still", type=float, nargs="+", metavar="T",
                    help="only save full-size frames at these full-video times, then stop")
    a = ap.parse_args()
    FF = ffmpeg_bin()

    out = a.out or os.path.join(tempfile.gettempdir(), "watch", slugify(a.src))
    os.makedirs(out, exist_ok=True)
    video, meta = fetch(a.src, out, None, None) if a.still else fetch(a.src, out, a.start, a.end)
    if a.still:
        sdir = os.path.join(out, "stills")
        os.makedirs(sdir, exist_ok=True)
        for t in a.still:
            path = os.path.join(sdir, f"{t:06.2f}.jpg")
            r = run([FF, "-loglevel", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-q:v", "2", path])
            print(path if r.returncode == 0 and os.path.exists(path) else f"failed at {t} s: {r.stderr[-300:]}")
        return
    offset = a.start or 0
    windowed = a.start is not None or a.end is not None
    if windowed:
        # cut the window from the local file so every step below sees only that part
        clip = os.path.join(out, "window.mp4")
        cmd = [FF, "-loglevel", "error", "-y", "-ss", str(offset), "-i", video]
        if a.end is not None:
            cmd += ["-t", str(a.end - offset)]
        r = run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", clip])
        if r.returncode != 0:
            sys.exit("Window cut failed: " + r.stderr[-800:])
        video = clip
    p = probe(video)
    dur = p["duration"]
    fps = a.fps or auto_fps(dur, a.max_frames)
    cuts = [round(c + offset, 2) for c in scene_cuts(video)] if dur <= 1800 else []
    frames = extract_frames(video, out, fps, offset)
    sheets = make_sheets(frames, out)
    caps = read_captions(out, offset if windowed else None, a.end)
    facts = audio_facts(video, offset) if p["has_audio"] else None
    if facts:
        json.dump({"loudness_every_0.5s": facts["curve"], "jumps_4db": facts["jumps"]},
                  open(os.path.join(out, "audio.json"), "w"))

    L = [f"# Watch report: {meta.get('title', a.src)}", ""]
    L.append(f"- Source: {meta.get('webpage_url', a.src)}")
    if meta.get("uploader"):
        L.append(f"- Uploader: {meta['uploader']}" + (f" · {meta['upload_date']}" if meta.get("upload_date") else ""))
    L.append((f"- Full video: {meta['duration']} s · " if meta.get("duration") else "- ") + f"Watched: {dur} s · {p['width']}x{p['height']} · {p['fps']} fps · "
             f"{'portrait' if (p['height'] or 0) > (p['width'] or 0) else 'landscape'}")
    L.append(f"- Frames: {len(frames)} at {fps:.2f} fps" + (f", window {a.start}–{a.end} s of the full video; all times are full-video times" if windowed else ""))
    L.append(f"- Scene cuts (hard cuts only; dissolves are not detected, check the sheets): "
             f"{', '.join(fmt_t(c) for c in cuts) if cuts else 'none detected'}")
    L.append(f"- Output folder: {out}")
    if meta.get("description"):
        L += ["", "## Uploader's description", "", meta["description"][:600]]
    L += ["", "## Contact sheets (read in order)", ""]
    for s, e, path in sheets:
        L.append(f"- {path}  ({fmt_t(s)} to {fmt_t(e)})")
    L += ["", "## Captions", "", caps if caps else "None."]
    L += ["", "## Audio, measured (ground truth)", ""]
    if not p["has_audio"]:
        L.append("No audio track.")
    elif facts:
        b = facts["beat"]
        L.append(f"- Level: mean {facts['mean_db']} dB, peak {facts['peak_db']} dB; near-silent share {facts['silent_share']}")
        if b:
            L.append(f"- Beat: {'steady, about ' + str(b['bpm']) + ' BPM' if b['steady'] else 'no steady beat'} "
                     f"(autocorrelation {b['strength']}" + ("; low confidence, clip under 20 s" if b["short"] else "")
                     + ("; may count fast notes, the felt pulse can be half" if b["steady"] and b["bpm"] > 120 else "") + ")")
        # loudness in about 12 steps, so a build or a drop is visible at a glance
        curve = facts["curve"]
        step = max(1, -(-len(curve) // 12))
        L.append("- Loudness over time: " + " · ".join(f"{fmt_t(t)} {d}" for t, d in curve[::step]))
        big = sorted(facts["jumps"], key=lambda j: -abs(j[1]))[:5]
        L.append("- Biggest jumps: " + (", ".join(f"{fmt_t(t)} ({d:+} dB)" for t, d in sorted(big)) or "none"))
        L.append(f"- Full curve: {os.path.join(out, 'audio.json')}")
    open(os.path.join(out, "report.md"), "w").write("\n".join(L) + "\n")
    print(os.path.join(out, "report.md"))


if __name__ == "__main__":
    main()
