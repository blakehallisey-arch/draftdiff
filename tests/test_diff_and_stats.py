"""The diff has one job a line diff cannot do, and the trend has one number
that has to be right in both directions."""
from __future__ import annotations

import unittest

from support import TempStore  # noqa: E402

from draftdiff import stats  # noqa: E402
from draftdiff.diffing import edit_stats, render  # noqa: E402

PARA = (
    "The billing migration slipped by two weeks because the vendor has not "
    "given us a date. We are holding the release until they do, and I will "
    "have something firmer by Friday."
)


def rewrap(text, width):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    out.append(line)
    return "\n".join(out)


class RewrapIsNotAnEdit(unittest.TestCase):
    def test_the_same_paragraph_at_a_different_width_shows_no_change(self):
        a, b = rewrap(PARA, 40), rewrap(PARA, 72)
        out = render(a, b, color=False)
        self.assertNotIn("[-", out)
        self.assertNotIn("{+", out)

    def test_and_scores_as_untouched(self):
        st = edit_stats(rewrap(PARA, 40), rewrap(PARA, 72))
        self.assertEqual(st["changed_pct"], 0.0)
        self.assertEqual(st["kept_pct"], 100.0)

    def test_one_word_changed_in_a_rewrapped_paragraph_is_the_only_thing_shown(self):
        a = rewrap(PARA, 40)
        b = rewrap(PARA.replace("two weeks", "three weeks"), 72)
        out = render(a, b, color=False)
        self.assertIn("[-two-]", out)
        self.assertIn("{+three+}", out)
        # Everything else survived: one deletion, one insertion, no more.
        self.assertEqual(out.count("[-"), 1)
        self.assertEqual(out.count("{+"), 1)


class Colour(unittest.TestCase):
    def test_plain_when_not_a_tty(self):
        out = render("one two three", "one four three", color=False)
        self.assertNotIn("\033", out)

    def test_ansi_when_asked_for(self):
        out = render("one two three", "one four three", color=True)
        self.assertIn("\033[31m", out)
        self.assertIn("\033[32m", out)


def synthetic(n_heavy, n_light):
    """Heavy pairs replace every word; light pairs change one."""
    pairs = []
    for i in range(n_heavy):
        pairs.append({"drafted": " ".join("alpha%d" % j for j in range(10)),
                      "sent": " ".join("omega%d" % j for j in range(10)),
                      "channel": "email"})
    for i in range(n_light):
        words = ["alpha%d" % j for j in range(10)]
        sent = list(words)
        sent[0] = "delta"
        pairs.append({"drafted": " ".join(words), "sent": " ".join(sent),
                      "channel": "email"})
    return pairs


class Trend(unittest.TestCase):
    def test_needs_ten_pairs_before_it_speaks(self):
        result = stats.summarize(synthetic(5, 4))
        self.assertFalse(result["trend"]["enough"])
        self.assertIn("9 of 10", result["trend"]["text"])

    def test_the_arithmetic_on_a_known_series(self):
        # First five: 10 words out, 10 words in, over a 10-word draft = 200%.
        # Last five: one word out, one in = 20%. (200-20)/200 = 90% less.
        result = stats.summarize(synthetic(5, 5))
        trend = result["trend"]
        self.assertTrue(trend["enough"])
        self.assertEqual(trend["earlier_median_edit_pct"], 200.0)
        self.assertEqual(trend["recent_median_edit_pct"], 20.0)
        self.assertEqual(trend["change_pct"], 90.0)
        self.assertIn("90% less editing", trend["text"])

    def test_it_reports_getting_worse_too(self):
        pairs = synthetic(0, 5) + synthetic(5, 0)
        trend = stats.summarize(pairs)["trend"]
        self.assertEqual(trend["direction"], "more")
        self.assertIn("more editing", trend["text"])

    def test_channels_are_reported_separately(self):
        store = TempStore()
        try:
            for _ in range(3):
                store.add("one two three", "one two", channel="email")
            store.add("four five six", "four five", channel="pr")
            data = stats.report(store.pairs())
        finally:
            store.close()
        self.assertEqual(data["overall"]["pairs"], 4)
        self.assertEqual(data["channels"]["email"]["pairs"], 3)
        self.assertEqual(data["channels"]["pr"]["pairs"], 1)


if __name__ == "__main__":
    unittest.main()
