"""The command line and the file under it. An empty store must not crash a
single command — a tool that explodes before you have fed it anything never
gets fed anything."""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import TempStore  # noqa: E402

from draftdiff import cli  # noqa: E402
from draftdiff.store import Store, StoreError, load_config  # noqa: E402


class Capture:
    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc):
        self.out = sys.stdout.getvalue()
        self.err = sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


class CliBase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="draftdiff-cli-"))
        self.store_path = str(self.dir / ".draftdiff" / "pairs.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_cli(self, *args):
        with Capture() as cap:
            code = cli.main(["--store", self.store_path] + list(args))
        return code, cap.out, cap.err


class EmptyStore(CliBase):
    def test_no_command_crashes_on_an_empty_store(self):
        for args in (["list"], ["stats"], ["rules"], ["stats", "--json"],
                     ["rules", "--json"], ["list", "--json"]):
            code, out, err = self.run_cli(*args)
            self.assertIn(code, (0, 2), "%s exited %d: %s" % (args, code, err))
            self.assertEqual(err, "")
            self.assertTrue(out.strip())

    def test_show_on_a_missing_id_is_an_error_not_a_traceback(self):
        code, out, err = self.run_cli("show", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no pair", err)

    def test_stats_on_an_empty_store_says_so(self):
        code, out, _ = self.run_cli("stats")
        self.assertEqual(code, 0)
        self.assertIn("No pairs recorded yet", out)


class Adding(CliBase):
    def test_inline_text(self):
        code, out, _ = self.run_cli(
            "add", "--drafted-text", "I just wanted to reach out about Friday.",
            "--sent-text", "About Friday.", "--channel", "email")
        self.assertEqual(code, 0)
        self.assertIn("words drafted", out)
        self.assertEqual(len(Store(path=self.store_path).pairs()), 1)

    def test_stdin_feeds_one_side(self):
        drafted = self.dir / "d.txt"
        drafted.write_text("I just wanted to reach out about Friday.")
        real = sys.stdin
        sys.stdin = io.StringIO("About Friday.")
        try:
            code, out, _ = self.run_cli("add", "--drafted", str(drafted), "--sent", "-")
        finally:
            sys.stdin = real
        self.assertEqual(code, 0)
        pairs = Store(path=self.store_path).pairs()
        self.assertEqual(pairs[0]["sent"], "About Friday.")

    def test_stdin_cannot_feed_both_sides(self):
        code, _, err = self.run_cli("add", "--drafted", "-", "--sent", "-")
        self.assertEqual(code, 1)
        self.assertIn("stdin can only feed one side", err)

    def test_a_missing_file_is_a_clean_error(self):
        code, _, err = self.run_cli("add", "--drafted", "/nope/nope.txt",
                                    "--sent-text", "x")
        self.assertEqual(code, 1)
        self.assertIn("no such file", err)

    def test_an_empty_side_is_refused(self):
        code, _, err = self.run_cli("add", "--drafted-text", "hello", "--sent-text", "  ")
        self.assertEqual(code, 1)
        self.assertIn("empty sent side", err)


class ShowAndRules(CliBase):
    def seed(self, n=12):
        for i in range(n):
            self.run_cli("add",
                         "--drafted-text", "I just wanted to reach out about item %d." % i,
                         "--sent-text", "About item %d." % i)

    def test_show_takes_an_id_prefix(self):
        self.seed(1)
        pair_id = Store(path=self.store_path).pairs()[0]["id"]
        code, out, _ = self.run_cli("show", pair_id[:4])
        self.assertEqual(code, 0)
        self.assertIn("[-", out)

    def test_rules_exits_two_when_the_corpus_is_thin(self):
        self.seed(4)
        code, out, _ = self.run_cli("rules")
        self.assertEqual(code, 2)
        self.assertIn("WARNING", out)

    def test_rules_exits_zero_once_there_are_enough(self):
        self.seed(12)
        code, out, _ = self.run_cli("rules")
        self.assertEqual(code, 0)
        self.assertIn("i just wanted to reach out", out)

    def test_min_pairs_override(self):
        self.seed(4)
        code, _, _ = self.run_cli("rules", "--min-pairs", "3")
        self.assertEqual(code, 0)

    def test_rules_json_is_json(self):
        self.seed(12)
        code, out, _ = self.run_cli("rules", "--json")
        data = json.loads(out)
        self.assertEqual(data["pairs"], 12)
        self.assertTrue(data["killed"])


class Importing(CliBase):
    def test_a_directory_of_pairs(self):
        src = self.dir / "corpus"
        src.mkdir()
        for i in range(3):
            (src / ("%02d.drafted.txt" % i)).write_text("I just wanted to reach out.")
            (src / ("%02d.sent.txt" % i)).write_text("Quick one.")
        (src / "00.meta.json").write_text(json.dumps(
            {"channel": "slack", "subject": "hello", "created": "2026-01-01T00:00:00"}))
        code, out, _ = self.run_cli("import", "--dir", str(src))
        self.assertEqual(code, 0)
        self.assertIn("imported 3 pair(s), skipped 0", out)
        pairs = Store(path=self.store_path).pairs()
        self.assertEqual(pairs[0]["channel"], "slack")
        self.assertEqual(pairs[0]["subject"], "hello")

    def test_a_drafted_file_with_no_sent_file_is_skipped_loudly(self):
        src = self.dir / "corpus"
        src.mkdir()
        (src / "01.drafted.txt").write_text("one")
        code, out, _ = self.run_cli("import", "--dir", str(src))
        self.assertEqual(code, 0)
        self.assertIn("skipped 1", out)

    def test_a_missing_directory_is_an_error(self):
        code, _, err = self.run_cli("import", "--dir", str(self.dir / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("no such directory", err)


class StoreFile(unittest.TestCase):
    def test_a_corrupt_store_is_refused_not_overwritten(self):
        temp = TempStore()
        try:
            temp.add("one two three", "one two")
            temp.store.path.write_text("{ this is not json")
            with self.assertRaises(StoreError):
                temp.store.load()
            # And the file is still on disk, untouched.
            self.assertIn("not json", temp.store.path.read_text())
        finally:
            temp.close()

    def test_a_previous_version_is_kept_as_bak(self):
        temp = TempStore()
        try:
            temp.add("one two three", "one two")
            temp.add("four five six", "four five")
            bak = temp.store.path.with_suffix(temp.store.path.suffix + ".bak")
            self.assertTrue(bak.exists())
            self.assertEqual(len(json.loads(bak.read_text())["pairs"]), 1)
        finally:
            temp.close()

    def test_an_ambiguous_id_prefix_is_an_error(self):
        temp = TempStore()
        try:
            data = temp.store.load()
            temp.add("one two three", "one two")
            temp.add("four five six", "four five")
            data = temp.store.load()
            data["pairs"][0]["id"] = "aaaa1111"
            data["pairs"][1]["id"] = "aaaa2222"
            temp.store._write(data)
            with self.assertRaises(StoreError):
                temp.store.get("aaaa")
            self.assertIsNotNone(temp.store.get("aaaa1111"))
        finally:
            temp.close()

    def test_config_defaults_and_overrides(self):
        temp = TempStore()
        try:
            cfg = load_config(temp.dir)
            self.assertEqual(cfg["min_occurrences"], 3)
            (temp.dir / "draftdiff.json").write_text('{"min_occurrences": 5}')
            self.assertEqual(load_config(temp.dir)["min_occurrences"], 5)
            (temp.dir / "draftdiff.json").write_text('{"nonsense": 1}')
            with self.assertRaises(StoreError):
                load_config(temp.dir)
        finally:
            temp.close()


if __name__ == "__main__":
    unittest.main()
