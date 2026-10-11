# Demo media

- `demo.gif`: silent, looping illustration of four prompt submissions.
- `demo.mp4`: the same illustration with the actual Zealot 1–3 and Dragoon 1 audio.
- `demo-poster.png`: still image for the video preview.
- `demo.vtt`: English captions for the four acknowledgements.
- `timeline.json`: audio timing for the preview's replay buttons.

The video uses H.264 and AAC for browser compatibility. Its graphics illustrate
the interaction; SCCodex does not add these panels to the real Codex UI.
The browser soundboard prefers separately fetched local WAVs. On standalone
hosting it streams the original clips from the pinned mirror on demand.

Run `scripts/build_demo.py` to regenerate these files. Dependencies and commands
are in [CONTRIBUTING.md](../../CONTRIBUTING.md#update-the-demo).
Blizzard audio in the video is excluded from the MIT license; see
[NOTICE.md](../../NOTICE.md).
