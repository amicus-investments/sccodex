# How SCCodex works

## Prompt to acknowledgement

The Codex `UserPromptSubmit` hook receives an event on stdin. SCCodex reads only
the event identity and launches a detached, silent playback worker. Prompt text
is not stored or forwarded to that worker. No Codex model call is made by the
sound hook.

The worker locks the shared state, chooses a clip from `assets/protoss.json`,
plays it with macOS `afplay`, and advances the counter after successful
playback. A unit gets three slots. The selection wraps after 42 prompts.
The lock serializes sounds from concurrent sessions. Duplicate session/turn IDs
are ignored when the event includes a turn ID; recent identities are bounded.

Muted prompts, volume 0, and failed playback do not advance the counter. Audio
errors are saved for `status`; hook failures do not reject a prompt. An optional
`Stop` hook is available with `setup --event finish`.

## Files and installation

| Location | Purpose |
| --- | --- |
| `src/sccodex.py` | CLI, hook handler, installer, state, and player |
| `assets/protoss.json` | Unit order, source paths, pinned commit, checksums |
| `assets/audio/` | Downloaded WAVs; excluded from Git |
| `scripts/fetch_sounds.py` | Verified download and PCM conversion |
| `scripts/build_demo.py` | Optional GIF/video builder |
| `scripts/preview.py` | Local preview server with byte-range media requests |
| `docs/index.html` | Local video and soundboard preview |
| `docs/protoss.json` | Generated manifest copy for standalone hosting |
| `tests/test_sccodex.py` | Rotation, concurrency, hook, and installation tests |

Setup validates the audio before editing hook configuration, then copies the
runtime, manifest, and WAVs to `~/.codex/sccodex/`. It adds one command handler to
`~/.codex/hooks.json`, preserves existing handlers and metadata, and creates
`hooks.json.sccodex-backup` before an edit. `config.toml` and existing notification
commands are untouched. Uninstall removes only SCCodex's handler.

The hook uses absolute, shell-quoted paths, so spaces in paths and different
working directories work. `CODEX_HOME` selects a custom Codex configuration
folder. After modifying source code or fetching replacement audio, rerun setup
to update the installed copy and review trust in Codex.

State lives in `~/Library/Application Support/SCCodex/state.json`: rotation,
volume, mute, recent event identities, last playback, and any audio error.
`SCCODEX_STATE_DIR` selects a separate folder for testing. `reset` recovers corrupt
state and retains a backup of the broken file.

## Audio provenance

The fetcher downloads originals from the pinned upstream commit in the manifest
and verifies each file against its Git blob checksum before conversion. ffmpeg
converts them to 16-bit mono PCM WAV at 22050 Hz. Duplicate files are fetched
once; cached valid WAVs are reused. Playback has no network dependency.

The audio remains Blizzard Entertainment's content. See [NOTICE.md](../NOTICE.md).
The runtime has no Python package dependencies; Pillow is used only for building
the documentation media.
