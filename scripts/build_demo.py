#!/usr/bin/env python3
"""Build an illustrated prompt-flow GIF and a video with the real clip audio.

Does not run Codex, install hooks, play through speakers, or change user state.
Requires fetched WAVs, ffmpeg, and Pillow (Python 3.10+ for the pinned version).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sccodex as sc

OUT = ROOT / "docs" / "media"
BUILD = ROOT / ".build" / "demo"
WIDTH, HEIGHT, FPS = 960, 540, 12
STEP, AUDIO_OFFSET, DURATION = 4.0, 1.0, 17.0
PROMPTS = ["Fix the failing test.", "Explain this diff.",
           "Add dark mode.", "Review the refactor."]
QUOTES = ["Thus I serve!", "Honor guide me!", "For Adun!", "Confirmed."]
C = {"bg": "#0b101d", "panel": "#121b2d", "border": "#28354b",
     "text": "#f3f6fc", "muted": "#9aaac2", "gold": "#f1cf83",
     "cyan": "#86e1e7", "violet": "#b7a5ef"}


def font(size: int, bold: bool = False, mono: bool = False):
    if mono:
        candidates = ["/System/Library/Fonts/Monaco.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    elif bold:
        candidates = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    else:
        candidates = ["/System/Library/Fonts/Supplemental/Arial.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("Install Arial or DejaVu Sans/Mono to render the demo.")


F = {"small": font(13), "label": font(14, True), "body": font(19),
     "title": font(43, True), "unit": font(34, True), "mono": font(22, mono=True),
     "quote": font(23, True), "number": font(17, True)}


def render(t: float, events: list[dict]) -> Image.Image:
    index = min(int(t // STEP), 3)
    event = events[index]
    elapsed = t - index * STEP
    answering = AUDIO_OFFSET <= elapsed < AUDIO_OFFSET + event["duration"]
    image = Image.new("RGB", (WIDTH, HEIGHT), C["bg"])
    d = ImageDraw.Draw(image)
    d.text((38, 27), "SCCODEX  /  PROTOSS ACKNOWLEDGEMENTS", font=F["label"], fill=C["gold"])
    d.text((36, 59), "Your prompt. Their command.", font=F["title"], fill=C["text"])
    d.text((38, 115), "Three acknowledgements per unit. Then the next unit takes over.",
           font=F["body"], fill=C["muted"])

    d.rounded_rectangle((36, 167, 596, 391), radius=16, fill=C["panel"], outline=C["border"])
    d.text((59, 188), "CODEX  /  PROMPT-FLOW ILLUSTRATION", font=F["label"], fill=C["muted"])
    d.line((59, 221, 573, 221), fill=C["border"])
    text = PROMPTS[index][:int(min(1, elapsed / .75) * len(PROMPTS[index]))]
    d.text((59, 248), ">", font=F["mono"], fill=C["cyan"])
    d.text((91, 248), text, font=F["mono"], fill=C["text"])
    if elapsed < AUDIO_OFFSET:
        cursor_x = 91 + d.textlength(text, font=F["mono"])
        d.rectangle((cursor_x + 3, 250, cursor_x + 13, 274), fill=C["cyan"])
    submitted = elapsed >= AUDIO_OFFSET
    d.text((59, 333), f"PROMPT {index + 1:02d}  " + ("SUBMITTED" if submitted else "TYPING"),
           font=F["label"], fill=C["cyan"] if submitted else C["muted"])
    d.text((318, 333), "One prompt. One sound.", font=F["body"], fill=C["muted"])

    d.rounded_rectangle((616, 167, 924, 391), radius=16, fill=C["panel"], outline=C["border"])
    d.text((640, 189), "UNIT ACKNOWLEDGEMENT", font=F["label"], fill=C["gold"])
    d.text((640, 227), event["unit"], font=F["unit"], fill=C["text"])
    for slot in range(3):
        x = 642 + slot * 43
        active = slot + 1 == event["slot"]
        d.rounded_rectangle((x, 277, x + 31, 307), radius=6,
                            fill=C["gold"] if active else C["bg"], outline=C["gold"] if active else C["border"])
        d.text((x + 10, 282), str(slot + 1), font=F["number"], fill=C["bg"] if active else C["muted"])
    if submitted:
        d.text((640, 330), QUOTES[index], font=F["quote"], fill=C["gold"])
    else:
        d.text((640, 330), "Ready for your command", font=F["body"], fill=C["muted"])
    for bar in range(8):
        h = 5 + (10 + 8 * math.sin(t * 12 + bar * .9) if answering else 0)
        x = 838 + bar * 8
        d.rounded_rectangle((x, 292 - h / 2, x + 4, 292 + h / 2), radius=2,
                            fill=C["cyan"] if answering else C["border"])

    d.rounded_rectangle((36, 414, 924, 479), radius=12, fill=C["panel"], outline=C["border"])
    d.text((59, 436), "ZEALOT", font=F["label"], fill=C["gold"])
    for slot in range(3):
        x = 137 + slot * 61
        selected = index == slot
        d.rounded_rectangle((x, 430, x + 49, 462), radius=6,
                            fill=C["gold"] if selected else C["bg"], outline=C["gold"] if selected else C["border"])
        d.text((x + 12, 437), f"{slot + 1}/3", font=F["label"], fill=C["bg"] if selected else C["muted"])
    d.text((330, 432), "→", font=F["quote"], fill=C["muted"])
    d.text((383, 436), "DRAGOON", font=F["label"], fill=C["violet"])
    for slot in range(3):
        x = 482 + slot * 61
        selected = index == 3 and slot == 0
        d.rounded_rectangle((x, 430, x + 49, 462), radius=6,
                            fill=C["violet"] if selected else C["bg"], outline=C["violet"] if selected else C["border"])
        d.text((x + 12, 437), f"{slot + 1}/3", font=F["label"], fill=C["bg"] if selected else C["muted"])
    d.text((679, 436), "→   +12 UNITS   →   REPEAT", font=F["label"], fill=C["muted"])
    d.text((38, 503), "14 Protoss units · 42 prompts per cycle · macOS · Codex CLI + desktop",
           font=F["small"], fill=C["muted"])
    d.text((716, 503), "Audio: Blizzard Entertainment", font=F["small"], fill=C["muted"])
    return image


def vtt_time(t: float) -> str:
    milliseconds = round(t * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"00:{minutes:02d}:{seconds:02d}.{ms:03d}"


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to build the demo.")
    units = sc.load_units()
    events = []
    for index in range(4):
        unit, clip, slot = sc.selection(units, index)
        path = sc.asset_path(clip)
        events.append({"unit": unit["name"], "slot": slot + 1, "path": path,
                       "start": index * STEP + AUDIO_OFFSET, "duration": sc.validate_wav(path)})
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sc.MANIFEST, OUT.parent / "protoss.json")
    render(1.3, events).save(OUT / "demo-poster.png")

    # A silent PCM timeline with the original four clips placed at submission.
    rate = 22050
    timeline = bytearray(round(DURATION * rate) * 2)
    for event in events:
        with wave.open(str(event["path"]), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, rate):
                raise SystemExit("Run sccodex fetch to prepare mono 22050 Hz PCM WAVs.")
            data = audio.readframes(audio.getnframes())
        offset = round(event["start"] * rate) * 2
        timeline[offset:offset + len(data)] = data
    audio_path = BUILD / "timeline.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(timeline)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
               "-r", str(FPS), "-i", "pipe:0", "-i", str(audio_path),
               "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "96k",
               "-movflags", "+faststart", "-shortest", str(OUT / "demo.mp4")]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        for frame in range(round(DURATION * FPS)):
            encoder.stdin.write(render(frame / FPS, events).tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise SystemExit("Video encoding failed.")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(OUT / "demo.mp4"), "-filter_complex",
                    "fps=8,scale=800:-1:flags=lanczos,split[a][b];"
                    "[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none",
                    "-loop", "0", str(OUT / "demo.gif")], check=True)
    captions = ["WEBVTT", ""]
    for event, quote in zip(events, QUOTES):
        captions += [f"{vtt_time(event['start'])} --> {vtt_time(event['start'] + event['duration'])}",
                     f"{event['unit']}: {quote}", ""]
    (OUT / "demo.vtt").write_text("\n".join(captions))
    (OUT / "timeline.json").write_text(json.dumps([
        {"unit": event["unit"], "slot": event["slot"], "start": event["start"],
         "end": round(event["start"] + event["duration"], 3), "quote": quote}
        for event, quote in zip(events, QUOTES)
    ], indent=2) + "\n")
    for name in ("demo.gif", "demo.mp4", "demo-poster.png", "demo.vtt", "timeline.json"):
        print(f"{OUT.relative_to(ROOT) / name}: {(OUT / name).stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
