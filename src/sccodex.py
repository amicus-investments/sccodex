#!/usr/bin/env python3
"""Classic Protoss acknowledgements for Codex, using only the Python stdlib."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Callable
import wave


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "assets" / "protoss.json"
EVENTS = {"submit": "UserPromptSubmit", "finish": "Stop"}
EVENT_NAMES = set(EVENTS.values())


class SoundError(Exception):
    pass


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()


def state_dir() -> Path:
    return Path(os.environ.get(
        "SCCODEX_STATE_DIR", str(Path.home() / "Library" / "Application Support" / "SCCodex")
    )).expanduser().resolve()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default.copy()
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return data
    except (ValueError, OSError) as error:
        raise SoundError(f"Cannot read {path}: {error}") from error


def load_units(manifest: Path = MANIFEST) -> list[dict]:
    data = read_json(manifest, {})
    units = data.get("units")
    if not isinstance(units, list) or not units:
        raise SoundError(f"No units found in {manifest}")
    ids = set()
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("id"), str):
            raise SoundError("Invalid unit in sound manifest")
        if unit["id"] in ids:
            raise SoundError(f"Duplicate unit: {unit['id']}")
        ids.add(unit["id"])
        clips = unit.get("clips")
        if not isinstance(clips, list) or len(clips) != 3:
            raise SoundError(f"{unit['id']} must have exactly three acknowledgement slots")
        for clip in clips:
            if not isinstance(clip, dict) or not isinstance(clip.get("file"), str):
                raise SoundError(f"Invalid clip for {unit['id']}")
            asset_path(clip, manifest.parent)
    return units


def asset_path(clip: dict, assets: Path = MANIFEST.parent) -> Path:
    path = (assets / clip["file"]).resolve()
    if not path.is_relative_to(assets.resolve()):
        raise SoundError("Sound path must stay inside the assets directory")
    return path


def selection(units: list[dict], index: int) -> tuple[dict, dict, int]:
    unit_index, clip_index = divmod(index % (len(units) * 3), 3)
    unit = units[unit_index]
    return unit, unit["clips"][clip_index], clip_index


def default_state() -> dict:
    return {"next_index": 0, "volume": 0.65, "muted": False, "recent_events": []}


def read_state(directory: Path) -> dict:
    state = {**default_state(), **read_json(directory / "state.json", {})}
    index = state["next_index"]
    volume = state["volume"]
    if type(index) is not int or index < 0:
        raise SoundError("Invalid rotation state. Run sccodex reset.")
    if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise SoundError("Invalid volume state. Run sccodex reset.")
    if type(state["muted"]) is not bool or not isinstance(state["recent_events"], list):
        raise SoundError("Invalid sound settings. Run sccodex reset.")
    return state


@contextmanager
def locked(directory: Path):
    """A separate lock survives atomic state replacement and serializes audio."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "state.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def validate_wav(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
            if audio.getnframes() == 0 or duration > 15 or audio.getcomptype() != "NONE":
                raise SoundError(f"Invalid acknowledgement WAV: {path}")
            return duration
    except (OSError, wave.Error, EOFError) as error:
        raise SoundError(f"Missing or invalid audio: {path}. Run sccodex fetch.") from error


def native_player(path: Path, volume: float) -> None:
    if sys.platform != "darwin":
        raise SoundError("This version uses macOS afplay.")
    validate_wav(path)
    try:
        result = subprocess.run(
            ["/usr/bin/afplay", "-v", str(volume), str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=16, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SoundError(f"Audio playback failed: {error}") from error
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise SoundError(f"afplay failed: {detail or result.returncode}")


def play_next(
    units: list[dict], directory: Path, assets: Path = MANIFEST.parent,
    event_key: str = "", player: Callable = native_player,
) -> dict | None:
    with locked(directory):
        state = read_state(directory)
        if state["muted"] or state["volume"] == 0:
            return None
        if event_key and event_key in state["recent_events"]:
            return None
        unit, clip, clip_index = selection(units, state["next_index"])
        path = asset_path(clip, assets)
        try:
            player(path, state["volume"])
        except SoundError as error:
            state["last_error"] = str(error)
            atomic_json(directory / "state.json", state)
            raise
        state["next_index"] += 1
        if event_key:
            state["recent_events"] = (state["recent_events"] + [event_key])[-128:]
        state["last_played"] = {
            "unit": unit["name"], "slot": clip_index + 1, "file": clip["file"],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        state.pop("last_error", None)
        atomic_json(directory / "state.json", state)
        return state["last_played"]


def run_hook() -> None:
    """Only read event identity; never log or forward the user's prompt."""
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return
        event_name = event.get("hook_event_name")
        if not isinstance(event_name, str) or event_name not in EVENT_NAMES:
            return
        if event.get("hook_event_name") == "Stop" and event.get("stop_hook_active"):
            return
        turn = event.get("turn_id")
        key = json.dumps([event.get("hook_event_name"), event.get("session_id"), turn]) if turn else ""
        # Detach playback so neither the audio duration nor the playback lock
        # delays a submitted prompt. The worker is silent and never calls Codex.
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_play-next", "--event-key", key],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
    except (ValueError, OSError):
        return


def is_our_hook(handler: dict) -> bool:
    if handler.get("type") != "command":
        return False
    try:
        parts = shlex.split(handler.get("command", ""))
    except ValueError:
        return False
    return (len(parts) == 3 and parts[2] == "hook"
            and Path(parts[1]).resolve() == (codex_home() / "sccodex/src/sccodex.py").resolve())


def without_our_hooks(data: dict) -> dict:
    """Remove only our handlers, preserving other handlers and their metadata."""
    data = json.loads(json.dumps(data))
    events = data.setdefault("hooks", {})
    if not isinstance(events, dict):
        raise SoundError("Existing hooks must be a JSON object")
    for event_name in list(events):
        groups = []
        for group in events[event_name]:
            original = group.get("hooks", [])
            handlers = [handler for handler in original if not is_our_hook(handler)]
            if len(handlers) == len(original):
                groups.append(group)
                continue
            if handlers:
                groups.append({**group, "hooks": handlers})
        if groups:
            events[event_name] = groups
        else:
            del events[event_name]
    return data


def install(event: str) -> Path:
    units = load_units()
    # Finish validating all assets before changing the user's hook configuration.
    paths = {asset_path(clip) for unit in units for clip in unit["clips"]}
    for path in paths:
        validate_wav(path)
    home = codex_home()
    destination = home / "sccodex"
    with locked(home / "sccodex-install"):
        hook_file = home / "hooks.json"
        old = read_json(hook_file, {})
        updated = without_our_hooks(old)
        for relative in [Path("src/sccodex.py"), Path("assets/protoss.json")]:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if (ROOT / relative).resolve() != target.resolve():
                shutil.copy2(ROOT / relative, target)
        for path in paths:
            target = destination / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.resolve() != target.resolve():
                shutil.copy2(path, target)
        command = shlex.join([sys.executable, str(destination / "src" / "sccodex.py"), "hook"])
        updated["hooks"].setdefault(EVENTS[event], []).append({"hooks": [{
            "type": "command", "command": command, "timeout": 3,
        }]})
        if updated != old:
            if hook_file.exists():
                shutil.copy2(hook_file, hook_file.with_name("hooks.json.sccodex-backup"))
            atomic_json(hook_file, updated)
    return hook_file


def uninstall() -> None:
    home = codex_home()
    with locked(home / "sccodex-install"):
        path = home / "hooks.json"
        if not path.exists():
            return
        old = read_json(path, {})
        updated = without_our_hooks(old)
        if old != updated:
            atomic_json(path, updated)


def launch(arguments: list[str]) -> int:
    binary = shutil.which("codex")
    if not binary:
        raise SoundError("Codex CLI is not installed or is not on PATH.")
    os.execv(binary, [binary, *arguments])
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    commands = {"setup", "uninstall", "fetch", "play", "preview", "list", "status",
                "reset", "mute", "unmute", "volume", "hook", "_play-next"}
    if not arguments or arguments[0] not in commands | {"-h", "--help"}:
        return launch(arguments)
    if arguments[0] == "hook":
        run_hook()
        return 0
    if arguments[0] == "_play-next":
        worker = argparse.ArgumentParser()
        worker.add_argument("command")
        worker.add_argument("--event-key", default="")
        args = worker.parse_args(arguments)
        play_next(load_units(), state_dir(), event_key=args.event_key)
        return 0
    parser = argparse.ArgumentParser(
        prog="sccodex",
        description="Codex with classic Protoss acknowledgements. Other arguments pass through to codex."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Install the Codex sound hook (preserves existing hooks)")
    setup.add_argument("--event", choices=EVENTS, default="submit")
    sub.add_parser("uninstall", help="Remove only the SCCodex hook")
    sub.add_parser("fetch", help="Download and convert the original audio files")
    sub.add_parser("play", help="Play the next acknowledgement and advance the rotation")
    preview = sub.add_parser("preview", help="Preview three slots without advancing the rotation")
    preview.add_argument("unit", nargs="?", default="zealot")
    sub.add_parser("list", help="List the unit rotation")
    sub.add_parser("status", help="Show the next acknowledgement, volume and mute setting")
    sub.add_parser("reset", help="Restart at Zealot; keep valid volume and mute settings")
    sub.add_parser("mute", help="Mute sounds and pause the rotation")
    sub.add_parser("unmute", help="Resume sounds")
    volume_parser = sub.add_parser("volume", help="Set playback volume from 0 to 100 percent")
    volume_parser.add_argument("percent", type=int, choices=range(101), metavar="0..100")
    args = parser.parse_args(arguments)
    if args.command == "fetch":
        fetch_script = ROOT / "scripts" / "fetch_sounds.py"
        if not fetch_script.exists():
            raise SoundError("Run fetch from the SCCodex source folder.")
        return subprocess.call([sys.executable, str(fetch_script)])
    if args.command == "setup":
        path = install(args.event)
        print(f"Installed {EVENTS[args.event]} sound hook in {path}")
        print("In Codex, open /hooks and trust the SCCodex sound command once.")
        return 0
    if args.command == "uninstall":
        uninstall()
        print("Removed the SCCodex hook. Other hooks, sounds and settings are preserved.")
        return 0
    units = load_units()
    directory = state_dir()
    if args.command == "play":
        played = play_next(units, directory)
        print(f"{played['unit']} {played['slot']}/3" if played else "Muted; rotation paused.")
    elif args.command == "preview":
        unit = next((unit for unit in units if unit["id"] == args.unit), None)
        if unit is None:
            raise SoundError(f"Unknown unit: {args.unit}. Run sccodex list.")
        state = read_state(directory)
        for index, clip in enumerate(unit["clips"]):
            print(f"{unit['name']} {index + 1}/3", flush=True)
            native_player(asset_path(clip), state["volume"])
    elif args.command == "list":
        for unit in units:
            print(f"{unit['id']:14} {unit['name']} (3 plays)")
    elif args.command == "status":
        state = read_state(directory)
        unit, clip, index = selection(units, state["next_index"])
        print(f"Next: {unit['name']} {index + 1}/3 ({clip['file']})")
        print(f"Volume: {round(state['volume'] * 100)}% | Muted: {'yes' if state['muted'] else 'no'}")
        print(f"Cycle: {len(units)} units, {len(units) * 3} prompts")
        if state.get("last_error"):
            print(f"Last audio error: {state['last_error']}")
    else:
        with locked(directory):
            if args.command == "reset":
                try:
                    state = read_state(directory)
                except SoundError:
                    old_path = directory / "state.json"
                    if old_path.exists():
                        shutil.copy2(old_path, directory / "state.json.broken-backup")
                    state = default_state()
                state["next_index"] = 0
                state["recent_events"] = []
                state.pop("last_error", None)
                state.pop("last_played", None)
            else:
                state = read_state(directory)
                if args.command == "volume":
                    state["volume"] = args.percent / 100
                else:
                    state["muted"] = args.command == "mute"
            atomic_json(directory / "state.json", state)
        print({"reset": "Rotation reset to Zealot 1/3.", "mute": "Sounds muted; rotation paused.",
               "unmute": "Sounds unmuted.", "volume": f"Volume set to {round(state['volume'] * 100)}%."}[args.command])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SoundError as error:
        if len(sys.argv) < 2 or sys.argv[1] not in {"hook", "_play-next"}:
            print(f"sccodex: {error}", file=sys.stderr)
            sys.exit(1)
        # Sound failures must never reject a prompt or continue an agent turn.
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
