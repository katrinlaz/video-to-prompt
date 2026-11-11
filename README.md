# video-to-prompt

A skill for Claude Code and Codex. Send your AI a video you like and it helps you find the words to describe it, so you can tell a video, image or music model what you want.

Ask it things like:

- "/video-to-prompt https://youtube.com/... from 0:10 to 0:20, I like the atmosphere"
- "how does the snow fall here?"
- "how do I recreate this scene?"
- "check my video against these reference images"

It cuts the video into timestamped frames, finds the cuts, reads the captions and measures the beat and loudness. Then it describes what creates the look you like and gives you a line you can paste into your prompt.

## What you need

- **python3** with **numpy**
- **ffmpeg**
- **yt-dlp** (for YouTube and other links)

On a Mac with Homebrew:

```
brew install ffmpeg yt-dlp
python3 -m pip install --user numpy
```

No ffmpeg? `python3 -m pip install --user imageio-ffmpeg` works too.

Or just ask your AI: "install what the video-to-prompt skill needs".

## Install

Clone it into your skills folder:

```
# Claude Code
git clone https://github.com/katrinlaz/video-to-prompt ~/.claude/skills/video-to-prompt

# Codex
git clone https://github.com/katrinlaz/video-to-prompt ~/.codex/skills/video-to-prompt
```

No git? Click **Code → Download ZIP**, unzip, rename the folder to `video-to-prompt` and put it there.

Start a new session. Type `/video-to-prompt` or just send a video link and say what you like.

## What it can't do

- **It doesn't hear the music.** It measures the beat and how loud it gets, and names the track from the title. You tell it how the music feels, and it turns that into a music prompt.
- Frames are pictures, not motion. For motion it looks at more frames per second on a short piece.
- Soft transitions (dissolves) aren't detected automatically.
- Private or login-only videos may not download.

The script processes the video locally and makes no AI API calls. The frames are then read by the AI you use (Claude or Codex).

## Running the script yourself

```
python3 watch.py "<url-or-file>" [--start S] [--end S] [--fps N] [--out DIR]
python3 watch.py "<url-or-file>" --still T [T ...]
```

`--still` saves full-size frames for zooming into texture.

Made by Kate Lazarevich ([Wonderland on Tokens](https://wonderlandontokens.substack.com)). Inspired by the `/watch` idea in [claude-video](https://github.com/bradautomates/claude-video); the code here is written from scratch.

MIT License.
