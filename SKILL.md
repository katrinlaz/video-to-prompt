---
name: video-to-prompt
description: Watch a video (YouTube or any yt-dlp link, or a local file) and help the user tell an AI video or music model what they want. Three modes: what they like in a clip (feeling, look, motion, effects), how to recreate it, or checking their own AI video against its references. Returns short shot-by-shot descriptions with paste-ready brief lines, then refines them from what the user says they liked. Use when the user sends a video and asks what is happening, how to describe a look, how something moves, how to recreate a scene, or to check their video. Triggers: "/video-to-prompt", "watch this video", "describe this video", "how do I explain this", "how to recreate this", "what is the camera doing here".
---

Help the user explain to an AI what they want, using a video they like. The output is words they can paste into a prompt for a video, image or music model.

## 1. Know the goal

The user usually names a time range and what they like. Pick the mode from their words:

- **What I like**: "the atmosphere", "the light", "how the snow falls", "this effect". Describe that, nothing else.
- **Recreate**: "how to recreate", "how did they make it". Give structure, a shared style line and a shot recipe.
- **Check my video**: their own AI video against reference images. Report continuity.

Nothing named → ask one line: what do you like here, or do you want to recreate it?

## 2. Run the script

`watch.py` sits in the same folder as this file. Run it with python3 (on Windows: `py` or `python`):

```
python3 <this skill's folder>/watch.py "<url-or-file>" [--start S --end S] [--fps N] [--out DIR]
```

- It prints the path of `report.md`. Read the report first.
- Always pass the user's time range. No range on a video over 2 minutes → ask for one, or watch the first minute.
- A missing tool stops the script with an install line. Show it to the user and stop.

## 3. Look the way the question needs

- **Colour, light, atmosphere** → the contact sheets are enough.
- **Motion** (how something falls, moves, dances, how the camera moves) → rerun the shot's window with `--fps 12`. Never guess motion between frames.
- **Texture or effects** (a grid, grain, a glitch) → `--still T` saves a full-size frame at time T; crop and zoom it. The sheet frames are 640 px and hide texture.
- **Cuts**: the report finds hard cuts only. Check the sheets for dissolves.
- More than 6 sheets → if you can run a subagent, let it read the sheets and return the shot list with timestamps. Otherwise read them in order.

## 4. Report: short

One short block per shot or per quality, then a brief. Under about 15 lines.

- **What I like** → what creates it (colours, light, camera, motion), in visible details first, a feeling word only after the details that earn it. Then one paste-ready brief in italics.
- **Recreate** → the structure (shots in order, with timestamps and cut rhythm), one style line shared by every shot, a recipe line per shot type, the edit rule.
- **Several readings possible** (two kinds of snow, three different effects) → name each one with its timestamp and ask which they meant.
- Name the camera move in plain words; add the film term in brackets.

Then ask what they liked. They answer in their own words. Translate them into prompt language (colour scheme, light, depth of field, camera, motion, music) and give the refined brief.

**Music.** You cannot hear the audio. Name the track from the title or captions. Report the measured facts: steady beat or not, loudness building or falling. A BPM over 120 may count fast notes; say the felt pulse can be half. Ask the user how the music feels to them, then turn that into a music prompt: genre, lead instrument, tempo, how it builds, mood.

**Check my video** → report **Continuity** instead. Compare each shot against the supplied reference images for props, clothes, appearance, and the start and end positions of hands and objects. Flag anything that changes across a cut.

## Limits

- Frames show images, not motion. Sampling is 4 fps up to 15 s, 2 fps up to 60 s, then a budget of 72 frames.
- No audio description: only measured loudness and beat. The beat check is weak on clips under 20 s.
- Dissolves are not detected.
- Private or login-only videos may fail to download. The script reports the error; tell the user and stop.
- Output lives in the system temp folder (`watch/<name>/`) unless `--out` is given.
