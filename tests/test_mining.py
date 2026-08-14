"""The bars a rule has to clear. These are the tests that matter: a miner that
invents a rule off one deletion poisons the prompt it gets pasted into."""
from __future__ import annotations

import unittest

from support import TempStore  # noqa: E402

from draftdiff import mining  # noqa: E402

BODY = (
    "Hi Marcus, the quarterly numbers landed this morning and the migration "
    "window is still open. The team wants a decision on the vendor before the "
    "release goes out on Tuesday."
)


def pair(drafted, sent):
    return {"drafted": drafted, "sent": sent}


def phrases(rows):
    return [r["phrase"] for r in rows]


class MinerCase(unittest.TestCase):
    """The miner chains overlapping fragments into the longest phrase it can
    support, so a synthetic corpus where a phrase always sits next to the same
    words reports the longer phrase. Assert on the habit, not on the exact
    string the chainer settled on."""

    def assertCut(self, mined, phrase):
        hits = [r for r in mined["killed"] if phrase in r["phrase"]]
        self.assertTrue(hits, "%r is in no rule: %s" % (phrase, phrases(mined["killed"])))
        return hits[0]

    def assertNotCut(self, mined, phrase):
        hits = [r for r in mined["killed"] if phrase in r["phrase"]]
        self.assertFalse(hits, "%r became a rule: %s" % (phrase, phrases(mined["killed"])))


class NoEdits(unittest.TestCase):
    def test_identical_pairs_produce_no_rules(self):
        pairs = [pair(BODY, BODY) for _ in range(8)]
        mined = mining.mine(pairs)
        self.assertEqual(mined["killed"], [])
        self.assertEqual(mined["added"], [])
        self.assertEqual(mined["structure"], [])
        self.assertEqual(mined["openers"]["survived"], 8)
        self.assertEqual(mined["closers"]["survived"], 8)

    def test_block_says_so_rather_than_inventing_something(self):
        pairs = [pair(BODY, BODY) for _ in range(12)]
        text = mining.format_rules(mining.mine(pairs), min_pairs=10)
        self.assertIn("No phrase or structure habit repeated", text)

    def test_a_rewrapped_send_is_not_an_edit(self):
        wrapped = "Hi Marcus, the quarterly numbers landed this\nmorning and the\nmigration window is still open."
        flat = "Hi Marcus, the quarterly numbers landed this morning and the migration window is still open."
        mined = mining.mine([pair(flat, wrapped) for _ in range(6)])
        self.assertEqual(mined["killed"], [])
        self.assertEqual(mined["added"], [])


class Occurrences(MinerCase):
    def test_one_deletion_is_not_a_rule(self):
        pairs = [pair("kindly advise. " + BODY, BODY)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY) for _ in range(4)]
        mined = mining.mine(pairs)
        self.assertNotCut(mined, "kindly advise")

    def test_two_deletions_are_not_a_rule_either(self):
        pairs = [pair("kindly advise. " + BODY, BODY) for _ in range(2)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY) for _ in range(3)]
        self.assertNotCut(mining.mine(pairs), "kindly advise")

    def test_four_deletions_in_four_of_five_drafts_is_a_rule(self):
        pairs = [pair("kindly advise. " + BODY, BODY) for _ in range(4)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY)]
        mined = mining.mine(pairs)
        row = self.assertCut(mined, "kindly advise")
        self.assertEqual((row["hits"], row["seen"]), (4, 5))
        self.assertEqual(row["consistency"], 0.8)


class Consistency(MinerCase):
    """The 60% bar, held from both sides."""

    def test_fifty_percent_is_not_a_rule(self):
        # Written six times, cut three. That is a coin flip, not a habit.
        pairs = [pair("kindly advise. " + BODY, BODY) for _ in range(3)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY) for _ in range(3)]
        self.assertNotCut(mining.mine(pairs), "kindly advise")

    def test_exactly_sixty_percent_is_a_rule(self):
        # Written five times, cut three.
        pairs = [pair("kindly advise. " + BODY, BODY) for _ in range(3)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY) for _ in range(2)]
        self.assertCut(mining.mine(pairs), "kindly advise")

    def test_the_bar_is_configurable_upward(self):
        pairs = [pair("kindly advise. " + BODY, BODY) for _ in range(3)]
        pairs += [pair("kindly advise. " + BODY, "kindly advise. " + BODY) for _ in range(2)]
        mined = mining.mine(pairs, min_consistency=0.9)
        self.assertNotCut(mined, "kindly advise")


class Additions(unittest.TestCase):
    def test_a_phrase_written_in_every_time_shows_up(self):
        pairs = [pair(BODY, BODY + " Can you confirm by Friday.") for _ in range(5)]
        added = phrases(mining.mine(pairs)["added"])
        self.assertTrue(any("confirm" in p for p in added), added)


class Structure(unittest.TestCase):
    BULLETS = "Three things:\n\n- one\n- two\n- three\n"
    PROSE = "Three things: one, two, three.\n"

    def test_bullets_removed_every_time_becomes_a_rule(self):
        pairs = [pair(self.BULLETS, self.PROSE) for _ in range(4)]
        labels = [r["label"] for r in mining.mine(pairs)["structure"]]
        self.assertIn("bullet list items", labels)

    def test_bullets_removed_once_does_not(self):
        pairs = [pair(self.BULLETS, self.PROSE)]
        pairs += [pair(self.BULLETS, self.BULLETS) for _ in range(4)]
        labels = [r["label"] for r in mining.mine(pairs)["structure"]]
        self.assertNotIn("bullet list items", labels)


class Openers(unittest.TestCase):
    def test_a_rewritten_opener_is_counted_and_quoted(self):
        pairs = [pair("I hope you are well. " + BODY, "Quick one. " + BODY)
                 for _ in range(4)]
        edge = mining.mine(pairs)["openers"]
        self.assertEqual(edge["survived"], 0)
        self.assertEqual(edge["total"], 4)
        self.assertEqual(edge["changes"][0]["now"], "Quick one.")


class Footer(unittest.TestCase):
    def test_a_thin_corpus_warns_about_itself(self):
        pairs = [pair(BODY, BODY) for _ in range(4)]
        text = mining.format_rules(mining.mine(pairs), min_pairs=10)
        self.assertIn("WARNING", text)

    def test_a_full_corpus_does_not(self):
        pairs = [pair(BODY, BODY) for _ in range(12)]
        text = mining.format_rules(mining.mine(pairs), min_pairs=10)
        self.assertNotIn("WARNING", text)

    def test_no_emojis_anywhere_in_the_block(self):
        store = TempStore()
        try:
            for _ in range(3):
                store.add("kindly advise. " + BODY, BODY)
            text = mining.format_rules(mining.mine(store.pairs()), min_pairs=10)
        finally:
            store.close()
        self.assertTrue(all(ord(ch) < 0x2600 for ch in text))


if __name__ == "__main__":
    unittest.main()
