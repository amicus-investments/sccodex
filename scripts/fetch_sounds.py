#!/usr/bin/env python3
"""Fetch pinned StarCraft assets and make short PCM WAV files for macOS afplay."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from sccodex import SoundError, asset_path, load_units, validate_wav  # noqa: E402


def fetch(clip: dict, source: dict, converter: str) -> tuple[str, str]:
    output = asset_path(clip)
    if output.exists():
        try:
            validate_wav(output)
            return str(output.relative_to(ROOT)), "cached"
        except SoundError:
            pass
    url = source["raw_base"] + urllib.parse.quote(clip["source"], safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "sccodex/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise SoundError(f"Unexpectedly large audio file: {clip['source']}")
    # Verify against the pinned repository's Git blob identity.
    git_hash = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if git_hash != clip["git_blob_sha"]:
        raise SoundError(f"Audio checksum mismatch: {clip['source']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sccodex-audio-") as temporary:
        input_file = Path(temporary) / Path(clip["source"]).name
        wav_file = Path(temporary) / "converted.wav"
        input_file.write_bytes(raw)
        subprocess.run([
            converter, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(input_file), "-map_metadata", "-1", "-ac", "1", "-ar", "22050",
            "-c:a", "pcm_s16le", str(wav_file),
        ], check=True, timeout=30)
        validate_wav(wav_file)
        # Copy via a sibling temporary file to avoid exposing a partial WAV.
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".download-", delete=False) as stream:
            staged = Path(stream.name)
            stream.write(wav_file.read_bytes())
        try:
            staged.replace(output)
        finally:
            staged.unlink(missing_ok=True)
    return str(output.relative_to(ROOT)), "downloaded"


def main() -> int:
    converter = shutil.which("ffmpeg")
    if not converter:
        print("Install ffmpeg to convert the OGG source clips (brew install ffmpeg).", file=sys.stderr)
        return 1
    manifest = json.loads((ROOT / "assets" / "protoss.json").read_text())
    units = load_units()
    unique = {clip["file"]: clip for unit in units for clip in unit["clips"]}
    failures = []
    def work(clip):
        try:
            return fetch(clip, manifest["source"], converter)
        except Exception as error:
            failures.append((clip["source"], str(error)))
            return clip["file"], "FAILED"
    with ThreadPoolExecutor(max_workers=4) as executor:
        for name, status in executor.map(work, unique.values()):
            print(f"{status:10} {name}", flush=True)
    for name, error in failures:
        print(f"{name}: {error}", file=sys.stderr)
    if failures:
        return 1
    print(f"Ready: {len(unique)} audio files, {len(units)} units, {len(units) * 3} acknowledgement slots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
