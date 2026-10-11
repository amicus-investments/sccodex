from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sccodex as sc


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sccodex-test-")
        self.directory = Path(self.temporary.name)
        self.units = sc.load_units()
        self.played = []

    def tearDown(self):
        self.temporary.cleanup()

    def player(self, path, volume):
        self.played.append((path, volume))

    def play(self, **kwargs):
        return sc.play_next(self.units, self.directory, player=self.player, **kwargs)

    def test_three_slots_per_unit_and_full_wrap(self):
        results = [self.play() for _ in range(43)]
        expected = [unit["name"] for unit in self.units for _ in range(3)]
        self.assertEqual([result["unit"] for result in results], expected + ["Zealot"])
        self.assertEqual([result["slot"] for result in results], [1, 2, 3] * 14 + [1])

    def test_position_persists_between_calls_and_volume_is_used(self):
        for _ in range(4):
            self.play()
        fresh = sc.read_state(self.directory)
        self.assertEqual(fresh["next_index"], 4)
        self.assertEqual(self.play()["unit"], "Dragoon")
        self.assertEqual(self.played[-1][1], 0.65)

    def test_duplicate_turn_does_not_play_twice(self):
        self.play(event_key="session-a/turn-1")
        self.assertIsNone(self.play(event_key="session-a/turn-1"))
        self.play(event_key="session-b/turn-1")
        self.assertEqual(len(self.played), 2)
        self.assertEqual(sc.read_state(self.directory)["next_index"], 2)

    def test_muting_and_zero_volume_pause_rotation(self):
        for setting in [{"muted": True}, {"volume": 0}]:
            sc.atomic_json(self.directory / "state.json", {**sc.default_state(), **setting})
            self.assertIsNone(self.play())
            self.assertEqual(sc.read_state(self.directory)["next_index"], 0)
        self.assertEqual(self.played, [])

    def test_failed_audio_is_recorded_without_skipping_clip(self):
        def failing_player(path, volume):
            raise sc.SoundError("device unavailable")
        with self.assertRaises(sc.SoundError):
            sc.play_next(self.units, self.directory, player=failing_player)
        state = sc.read_state(self.directory)
        self.assertEqual(state["next_index"], 0)
        self.assertEqual(state["last_error"], "device unavailable")
        self.assertEqual(self.play()["slot"], 1)
        self.assertNotIn("last_error", sc.read_state(self.directory))

    def test_concurrent_events_serialize_playback_and_do_not_lose_progress(self):
        active = 0
        maximum = 0
        def concurrent_player(path, volume):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            time.sleep(0.003)
            active -= 1
        def work(index):
            return sc.play_next(self.units, self.directory,
                                event_key=str(index), player=concurrent_player)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(work, range(24)))
        self.assertEqual(len(results), 24)
        self.assertEqual(sc.read_state(self.directory)["next_index"], 24)
        self.assertEqual(maximum, 1)

    def test_asset_paths_cannot_escape_manifest_directory(self):
        with self.assertRaises(sc.SoundError):
            sc.asset_path({"file": "../../outside.wav"})

    def test_reset_recovers_corrupt_state_and_keeps_backup(self):
        broken = self.directory / "state.json"
        broken.write_text("{unfinished")
        with patch.dict(os.environ, {"SCCODEX_STATE_DIR": str(self.directory)}), redirect_stdout(io.StringIO()):
            self.assertEqual(sc.main(["reset"]), 0)
        self.assertEqual(sc.read_state(self.directory)["next_index"], 0)
        self.assertEqual((self.directory / "state.json.broken-backup").read_text(), "{unfinished")


class HookTests(unittest.TestCase):
    def test_hook_is_quiet_detached_and_never_forwards_prompt_text(self):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                   "turn_id": "t1", "prompt": "private prompt text"}
        output = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                patch.object(sc.subprocess, "Popen") as spawn, redirect_stdout(output):
            sc.run_hook()
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertNotIn("private prompt text", str(spawn.call_args))
        self.assertIn("_play-next", spawn.call_args.args[0])

    def test_malformed_unrelated_and_continuation_events_are_ignored(self):
        for payload in ["not json", "[]", '{"hook_event_name": []}',
                        '{"hook_event_name": "PreToolUse"}',
                        '{"hook_event_name": "Stop", "stop_hook_active": true}']:
            with self.subTest(payload=payload), patch.object(sys, "stdin", io.StringIO(payload)), \
                    patch.object(sc.subprocess, "Popen") as spawn:
                sc.run_hook()
                spawn.assert_not_called()

    def test_install_idempotent_preserves_other_hooks_and_uninstalls_selectively(self):
        with tempfile.TemporaryDirectory(prefix="sccodex-home-") as temporary:
            home = Path(temporary)
            original = {"description": "My hooks", "hooks": {
                "UserPromptSubmit": [{"matcher": "", "hooks": [
                    {"type": "command", "command": "printf existing"}
                ]}],
                "Stop": [{"hooks": [{"type": "command", "command": "printf finish"}]}],
                "SessionStart": [{"hooks": []}],
            }}
            sc.atomic_json(home / "hooks.json", original)
            with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                sc.install("submit")
                first = json.loads((home / "hooks.json").read_text())
                sc.install("submit")
                self.assertEqual(json.loads((home / "hooks.json").read_text()), first)
                self.assertEqual(first["hooks"]["Stop"], original["hooks"]["Stop"])
                self.assertEqual(first["hooks"]["SessionStart"], original["hooks"]["SessionStart"])
                self.assertEqual(len(first["hooks"]["UserPromptSubmit"]), 2)
                command = first["hooks"]["UserPromptSubmit"][1]["hooks"][0]["command"]
                script = Path(shlex.split(command)[1])
                self.assertTrue(script.exists())
                self.assertTrue((home / "sccodex/assets/protoss.json").exists())
                self.assertEqual(json.loads((home / "hooks.json.sccodex-backup").read_text()), original)
                sc.install("finish")
                changed = json.loads((home / "hooks.json").read_text())
                self.assertEqual(changed["hooks"]["UserPromptSubmit"], original["hooks"]["UserPromptSubmit"])
                self.assertEqual(len(changed["hooks"]["Stop"]), 2)
                sc.uninstall()
                self.assertEqual(json.loads((home / "hooks.json").read_text()), original)

    def test_existing_codex_arguments_are_forwarded(self):
        arguments = ["exec", "--model", "example", "hello"]
        with patch.object(sc, "launch", return_value=0) as launch:
            self.assertEqual(sc.main(arguments), 0)
        launch.assert_called_once_with(arguments)


if __name__ == "__main__":
    unittest.main()
