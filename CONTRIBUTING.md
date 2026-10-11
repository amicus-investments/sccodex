# Contributing to SCCodex

Thanks for helping bring a little StarCraft to a coding session.

Bug reports should include your macOS version, `python3 --version`,
`codex --version`, the command that failed, and relevant output from
`./sccodex status`. Please omit prompts, chat logs, credentials, and unrelated
configuration. Feature suggestions and pull requests are welcome.

## Develop and verify

The runtime uses only the Python standard library. Install ffmpeg, then:

```sh
./sccodex fetch
python3 -m unittest discover -s tests -v
git diff --check
```

Tests use temporary configuration and state folders and mock audio playback;
they do not install a hook into your real Codex configuration. The install test
validates the fetched WAVs, so fetching first is required.

For a manual sound check that keeps your normal rotation intact:

```sh
SCCODEX_STATE_DIR="$(mktemp -d -t sccodex-review)" ./sccodex preview zealot
```

Keep changes focused. Explain the resulting behavior and how you verified it.
For changes to playback, installation, or state, cover meaningful failure cases
as well as the normal path. See [the implementation notes](docs/DEVELOPMENT.md).

## Useful next projects

- Terran and Zerg manifests with clear provenance and three slots per unit.
- Playback backends for Linux and Windows.
- Native Codex plugin packaging and marketplace distribution.
- Clearer first-run diagnostics when audio or hook trust is missing.

Maintain the existing behavior: three acknowledgements per unit, persistent
rotation, quiet hooks, prompt privacy, and preservation of unrelated hooks.
Keep the downloaded sound pack out of Git and do not add Blizzard assets under
the project's MIT license.

## Update the demo

The GIF and video are generated from the actual rotation logic and fetched WAVs.
The visuals are an illustration, not a recording of Codex's interface.
Media building needs Python 3.10+, ffmpeg, and one optional package:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-demo.txt
./sccodex fetch
.venv/bin/python scripts/build_demo.py
```

The builder does not run Codex, modify hooks or state, or play through speakers.
Review the GIF, video, captions, and browser preview after rebuilding.
Use the [local preview instructions](README.md#hear-it-in-your-browser).

## Publish the browser demo

The `docs/` directory is ready for standalone static hosting. Its generated
manifest points to the pinned upstream recordings, so hosting does not require
committing the full audio pack. No clips autoplay or preload from upstream.

For GitHub Pages, after the public launch, select **Settings → Pages → Deploy
from a branch → main → /docs → Save**. See the
[GitHub Pages instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
Check that the published URL works, then use it for the README's soundboard link.
The repository currently links to local preview instructions rather than an
unpublished site.
