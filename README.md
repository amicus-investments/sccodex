# SCCodex

Classic StarCraft Protoss acknowledgements on **every prompt submitted to Codex**.
One sound plays per prompt. A unit gets three consecutive prompts, then the next
unit takes over. After 42 prompts, the cycle returns to Zealot.

This uses Codex's official `UserPromptSubmit` lifecycle hook and your installed
Codex CLI or desktop app. Your Codex account, model settings, and other hooks stay
in place. Python 3.9+ and macOS are required. No Python packages or API key are
needed. `ffmpeg` is needed only to prepare the audio files.

## Start

From this folder:

```sh
./sccodex fetch            # Fetch and verify source audio; convert to PCM WAV
./sccodex preview zealot   # Hear the three Zealot acknowledgements
./sccodex setup            # Install for your Codex CLI and desktop app
./sccodex                 # Launch your existing Codex CLI
```

Codex requires new hooks to be trusted once. Open **`/hooks`** in Codex, review
the command ending in `sccodex/src/sccodex.py hook`, and trust it. Start a new
session if an already open desktop thread hasn't picked up the hook.
See the [official hook documentation](https://learn.chatgpt.com/docs/hooks).

Normal Codex arguments pass through, including `./sccodex resume`,
`./sccodex exec "your prompt"`, `./sccodex --model ...`, and `./sccodex --version`.
After setup, running ordinary `codex` also plays the acknowledgements.

## Controls

```sh
./sccodex status                # Show next unit, slot, volume, and playback errors
./sccodex list                  # Show unit order
./sccodex preview dark-templar  # Preview without moving the prompt rotation
./sccodex play                  # Play one sound and advance the rotation
./sccodex volume 50             # Volume from 0–100; default 65
./sccodex mute                  # Pause sounds and rotation
./sccodex unmute                # Resume
./sccodex reset                 # Return to Zealot 1/3
./sccodex uninstall             # Remove this hook; preserve all other hooks
```

Preview is an explicit sound check and plays even when the prompt hook is muted.
Volume 0 silences both previews and prompts; prompts at volume 0 pause the rotation.

The order is Zealot → Dragoon → High Templar → Dark Templar → Archon →
Dark Archon → Probe → Shuttle → Reaver → Observer → Scout → Corsair → Carrier →
Arbiter. Each gets three plays. The Observer set has two order acknowledgement
clips, so its third slot repeats its first. There are 41 audio files and 42 slots.

## How it works

- `assets/protoss.json` defines the unit order and three sound slots per unit.
- Audio downloads come from a pinned commit of
  [hometlt's StarCraft assets mirror](https://github.com/hometlt/starcraft-all-races-assets/tree/362949791055e0fc010ab7fe873792b362cba2d9/BroodWar.SC2Mod/Assets/Sounds).
  Each original file is verified against its Git blob checksum before conversion.
  StarCraft audio belongs to Blizzard Entertainment. Downloaded audio is excluded
  from Git; this repository contains the code and asset manifest.
- Setup copies the runtime and WAVs to `~/.codex/sccodex/` and adds one handler to
  `~/.codex/hooks.json`. Existing hooks are preserved, with a backup before edits.
  It never changes `config.toml` or the existing notification command.
- Playback runs in a detached worker using macOS `afplay`. Submitting a prompt
  doesn't wait for the sound to finish. A file lock serializes sounds from
  concurrent sessions and keeps the shared counter consistent.
- The position, volume, and mute setting persist in
  `~/Library/Application Support/SCCodex/state.json`. Duplicate session/turn IDs
  play only once. Muted prompts and failed playback do not advance the counter.
  The hook never stores or forwards your prompt text. Playback errors never
  reject a prompt.

`CODEX_HOME` selects a custom Codex configuration folder, if already configured.
`SCCODEX_STATE_DIR` selects a separate state folder, useful for testing. The
installed hook contains absolute, shell-quoted paths so spaces in folder names
and running Codex from another working directory both work.

## Verify

Fetch the audio, then run:

```sh
python3 -m unittest discover -s tests -v
./sccodex preview zealot
```

The tests cover three plays per unit, a full cycle, saved progress, duplicate
events, concurrent playback, muting, failed audio, corrupt-state recovery, quiet
hook execution, argument forwarding, and safe installation/removal.
