"""The miner — turns a pile of edits into a block you paste into a prompt.

Why code and not a note: a human reading twelve diffs will notice two or three
habits and forget the rest. The habits worth writing down are the ones that
repeat, and repetition across a dozen documents is a counting problem, not a
judgment problem. So the counting happens here and the judgment stays with
whoever reads the block.

Every rule in the output has to clear the same two bars, both configurable:

  1. It happened at least `min_occurrences` times. Three, by default. Cutting a
     phrase once means you did not like it in that message.
  2. It happened in at least `min_consistency` of the drafts that contained it.
     60%, by default. A phrase you cut four times and kept six times is not a
     rule, it is a coin flip, and putting it in a prompt makes the next draft
     worse.

What it cannot see: why. It is descriptive. If you have spent a month cutting
every number out of your drafts because you were nervous about them, this will
cheerfully tell your agent to stop writing numbers.
"""
from __future__ import annotations

import re

from . import textutil as T

# Words that carry no voice on their own. A heavy editor deletes half the draft,
# so "for" and "with" and "to the" clear any consistency bar you set — not
# because they are disliked but because everything was cut. A rule saying "never
# write 'for'" is the fastest way to make this output unreadable, so a phrase
# made ENTIRELY of these is dropped. A phrase that merely contains them is fine:
# "i wanted to reach out" is mostly function words and is exactly the habit.
FUNCTION_WORDS = frozenset("""
a about an and any are as at back be been before being both but by can could did
do does down for from had has have he her here him his how i if in into is it
its me more most my no nor not now of off on once one only or other others our
ours out over own she should so some such than that the their them then there
these they this those through to too under until up us was we were what when
where which while who whom why will with would you your yours am
""".split())

# Chaining bounds. A rule longer than this is a paragraph, not a habit, and
# nobody pastes a paragraph-long "never write" line into a prompt.
MAX_CHAIN_WORDS = 12
MIN_CHAIN = 2

# Structural habits. Each is (label, singular-noun, counter). They are counted
# on the RAW text, not the normalized text, because normalizing is what erases
# line structure in the first place.
STRUCTURE = [
    ("bullet list items", "bullet",
     lambda t: len([l for l in t.splitlines() if re.match(r"^\s*[-*•+]\s+", l)])),
    ("numbered list items", "numbered item",
     lambda t: len([l for l in t.splitlines() if re.match(r"^\s*\d+[.)]\s+", l)])),
    ("markdown headings", "heading",
     lambda t: len([l for l in t.splitlines() if re.match(r"^\s*#{1,6}\s+", l)])),
    ("em dashes", "em dash", lambda t: t.count("—") + len(re.findall(r"\s--\s", t))),
    ("exclamation marks", "exclamation mark", lambda t: t.count("!")),
    ("semicolons", "semicolon", lambda t: t.count(";")),
    ("questions", "question mark", lambda t: t.count("?")),
    ("parentheticals", "parenthetical", lambda t: t.count("(")),
    ("paragraphs", "paragraph", lambda t: len(T.paragraphs(t))),
]


def mine(pairs, min_occurrences=3, min_consistency=0.6, max_ngram=3, structure_drop=0.25):
    """Everything the corpus supports, as data. Formatting happens elsewhere."""
    prepared = []
    for p in pairs:
        d_norm = T.normalize(p["drafted"])
        s_norm = T.normalize(p["sent"])
        prepared.append({
            "raw_drafted": p["drafted"],
            "raw_sent": p["sent"],
            "d_words": T.words(d_norm),
            "s_words": T.words(s_norm),
            "d_grams": T.ngram_set(T.words(d_norm), max_ngram),
            "s_grams": T.ngram_set(T.words(s_norm), max_ngram),
            "d_sents": T.sentences(d_norm),
            "s_sents": T.sentences(s_norm),
        })

    return {
        "pairs": len(pairs),
        "killed": _phrases(prepared, "d_words", "s_words",
                           min_occurrences, min_consistency, max_ngram,
                           drop_all_function=True),
        # The function-word filter is asymmetric on purpose. Deleting is
        # wholesale — cut a paragraph and every "with" in it goes too — so the
        # killed side needs the filter. Inserting is deliberate and sparse: if
        # somebody wrote "can you" into four sends that did not have it, that is
        # the habit, not an artifact.
        "added": _phrases(prepared, "s_words", "d_words",
                          min_occurrences, min_consistency, max_ngram,
                          drop_all_function=False),
        "length": _length(prepared),
        "openers": _edges(prepared, first=True),
        "closers": _edges(prepared, first=False),
        "structure": _structure(prepared, min_occurrences, min_consistency, structure_drop),
    }


# ── phrases ──────────────────────────────────────────────────────────────
def _contains(tokens, gram):
    n = len(gram)
    return any(tuple(tokens[i:i + n]) == gram for i in range(len(tokens) - n + 1))


def _extra_words(short, long_):
    """Tokens `long_` adds around `short`. Only correct when short is inside
    long_, which is the only place it is called."""
    n = len(short)
    for i in range(len(long_) - n + 1):
        if long_[i:i + n] == short:
            return list(long_[:i]) + list(long_[i + n:])
    return list(long_)


def _tally(prepared, source_key, other_key, gram):
    """(times it was written, times it did not survive)."""
    seen = hits = 0
    for doc in prepared:
        if _contains(doc[source_key], gram):
            seen += 1
            if not _contains(doc[other_key], gram):
                hits += 1
    return seen, hits


def _phrases(prepared, source_key, other_key, min_occurrences, min_consistency,
             max_ngram, drop_all_function=True):
    """Phrases present on the source side and absent from the other side.

    Absence, not a smaller count: if a phrase appears twice in the draft and
    once in the send, the human kept it. Counting the drop would report a
    deletion the writer plainly did not commit to.

    Three filters sit on top of the two the README advertises, and each one is
    here because the first version of this file printed the rule it removes:

      · a phrase made entirely of function words is dropped (see FUNCTION_WORDS)
      · a phrase must beat the corpus BASELINE deletion rate by a margin. When a
        human cuts 60% of every draft, a 60% deletion rate is what nothing
        special looks like, and "never write 'roughly'" earned its place only
        by being cut more often than the average word was
      · overlapping fragments are chained back into the phrase they came from,
        so three rules about "wanted", "to reach" and "reach out" become one
        rule about "i wanted to reach out"
    """
    containing = {}
    gone = {}
    for doc in prepared:
        other = T.ngram_set(doc[other_key], max_ngram)
        for gram in T.ngram_set(doc[source_key], max_ngram):
            containing[gram] = containing.get(gram, 0) + 1
            if gram not in other:
                gone[gram] = gone.get(gram, 0) + 1

    # Baseline per phrase length. Long phrases survive less often than single
    # words by nature, so each length gets its own bar.
    baseline = {}
    for n in range(1, max_ngram + 1):
        seen_n = sum(v for g, v in containing.items() if len(g) == n)
        gone_n = sum(v for g, v in gone.items() if len(g) == n)
        baseline[n] = (gone_n / seen_n) if seen_n else 0.0

    def bar(n):
        # A phrase longer than max_ngram has no baseline of its own; fall back
        # to the longest one measured rather than to zero.
        ref = baseline.get(n, baseline.get(max_ngram, 0.0))
        # Capped below 1.0 on purpose. In a corpus where the human rewrites
        # nearly everything, the raw baseline for a three-word phrase can reach
        # 0.9, the bar lands above 1.0, and NO long phrase can ever qualify —
        # which silently deleted the best rules in the report.
        return min(0.95, max(min_consistency, ref + 0.20))

    def admissible(gram, seen, hits):
        if hits < min_occurrences:
            return False
        if hits / seen < bar(len(gram)):
            return False
        if all(w in FUNCTION_WORDS for w in gram) and (drop_all_function or len(gram) == 1):
            return False
        if len(gram) == 1 and (len(gram[0]) < 2 or gram[0].isdigit()):
            # A rule saying "never write 3" is worse than no rule.
            return False
        return True

    qualifying = {}
    for gram, hits in gone.items():
        seen = containing[gram]
        if admissible(gram, seen, hits):
            qualifying[gram] = {"seen": seen, "hits": hits}

    qualifying = _chain(prepared, source_key, other_key, qualifying, admissible)

    # Fragments, in both directions.
    #
    # Down: "please don't hesitate to" and "please don't hesitate to reach out"
    # are one habit. If the longer phrase accounts for all but one of the
    # shorter one's kills, print the longer — it is the thing the person
    # actually stopped writing.
    #
    # Up: "really" was cut 7 times, "i am really" 4 times. The longer phrase
    # adds two function words and no information, so it goes. "really excited"
    # stays, because "excited" is a word somebody chose.
    # Pass one, upward: "really" was cut 7 times and "i am really" 4 times. The
    # longer phrase adds two function words and no information, so it goes.
    # "really excited" survives, because "excited" is a word somebody chose.
    # This pass only ever drops the LONGER phrase, so it cannot cycle.
    trimmed = {}
    for gram, row in qualifying.items():
        beaten = any(
            len(other) < len(gram)
            and T.is_contiguous_sub(other, gram)
            and orow["hits"] > row["hits"]
            and all(w in FUNCTION_WORDS for w in _extra_words(other, gram))
            for other, orow in qualifying.items()
        )
        if not beaten:
            trimmed[gram] = row

    # Pass two, downward: greedy, longest first, comparing only against what has
    # already been kept. Comparing every pair at once let "know" and "let me
    # know if you" each disqualify the other and the habit vanished entirely.
    # A longer phrase swallows a shorter one when it accounts for most of its
    # kills — most, not all, so a single strong word like "please" survives a
    # longer phrase that only explains three of its seven deletions.
    keep = {}
    for gram in sorted(trimmed, key=lambda g: (-len(g), -trimmed[g]["hits"], g)):
        row = trimmed[gram]
        threshold = max(0.6 * row["hits"], row["hits"] - 2)
        covered = any(
            (T.is_contiguous_sub(gram, other) and orow["hits"] >= threshold)
            # ...or it is the tail of a phrase already kept. "can you" and
            # "you do" are one habit seen through a two-word window; without
            # this the report prints the seam as if it were a second rule.
            or (len(gram) > 1 and orow["hits"] >= row["hits"]
                and (gram[:-1] == other[-len(gram) + 1:]
                     or gram[1:] == other[:len(gram) - 1]))
            for other, orow in keep.items()
        )
        if not covered:
            keep[gram] = row

    rows = [
        {
            "phrase": T.phrase(gram),
            "words": len(gram),
            "hits": row["hits"],
            "seen": row["seen"],
            "consistency": round(row["hits"] / row["seen"], 3),
        }
        for gram, row in keep.items()
    ]
    rows.sort(key=lambda r: (-r["hits"], -r["consistency"], -r["words"], r["phrase"]))
    return rows


def _chain(prepared, source_key, other_key, qualifying, admissible):
    """Glue overlapping grams back into the phrase they were cut out of.

    'i wanted to' + 'wanted to reach' + 'to reach out' are three views of one
    habit. If the joined phrase still clears the bar on its own count, it
    replaces all three. Capped at 12 words so a whole boilerplate paragraph
    cannot become a single unreadable rule.
    """
    grams = dict(qualifying)
    # Index by leading tokens so finding "what starts where this one ends" is a
    # dictionary lookup. The first version compared every gram against every
    # other gram on every pass and took minutes on a corpus of twelve emails.
    by_prefix = {}
    for gram in grams:
        by_prefix.setdefault(gram[:-1], []).append(gram)

    frontier = [g for g in grams if len(g) >= MIN_CHAIN]
    for _ in range(MAX_CHAIN_WORDS):
        grown = []
        for a in frontier:
            if len(a) >= MAX_CHAIN_WORDS:
                continue
            for b in by_prefix.get(a[1:], ()):
                joined = a + b[len(a) - 1:]
                if joined in grams or len(joined) > MAX_CHAIN_WORDS:
                    continue
                seen, hits = _tally(prepared, source_key, other_key, joined)
                if seen and admissible(joined, seen, hits):
                    # The parts stay in the dict; the fragment passes below drop
                    # the ones this phrase explains and keep any that carry
                    # evidence of their own.
                    grams[joined] = {"seen": seen, "hits": hits}
                    by_prefix.setdefault(joined[:-1], []).append(joined)
                    grown.append(joined)
        if not grown:
            break
        frontier = grown
    return grams


# ── length ───────────────────────────────────────────────────────────────
def _length(prepared):
    ratios = [len(d["s_words"]) / len(d["d_words"]) for d in prepared if d["d_words"]]
    return {
        "median_ratio": round(T.median(ratios), 3) if ratios else None,
        "median_drafted_words": T.median([len(d["d_words"]) for d in prepared]),
        "median_sent_words": T.median([len(d["s_words"]) for d in prepared]),
        "shorter_pairs": sum(1 for r in ratios if r < 0.95),
        "longer_pairs": sum(1 for r in ratios if r > 1.05),
        "pairs": len(ratios),
    }


# ── openers and closers ──────────────────────────────────────────────────
def _key(sentence):
    return " ".join(T.words(sentence))


def _edges(prepared, first=True):
    """The first (or last) sentence is where voice lives, so it gets counted on
    its own rather than being averaged into the body."""
    idx = 0 if first else -1
    survived = 0
    total = 0
    changes = []
    for doc in prepared:
        if not doc["d_sents"] or not doc["s_sents"]:
            continue
        total += 1
        was, now = doc["d_sents"][idx], doc["s_sents"][idx]
        if _key(was) == _key(now):
            survived += 1
        else:
            changes.append({"was": was, "now": now})
    return {
        "total": total,
        "survived": survived,
        "survival_pct": round(100.0 * survived / total, 1) if total else 0.0,
        "changes": changes,
    }


# ── structure ────────────────────────────────────────────────────────────
def _structure(prepared, min_occurrences, min_consistency, structure_drop):
    out = []
    for label, noun, count in STRUCTURE:
        d_total = s_total = 0
        present = dropped = raised = 0
        for doc in prepared:
            dn, sn = count(doc["raw_drafted"]), count(doc["raw_sent"])
            d_total += dn
            s_total += sn
            if dn:
                present += 1
                if sn < dn:
                    dropped += 1
                elif sn > dn:
                    raised += 1
        if present < min_occurrences or not d_total:
            continue
        consistency = dropped / present
        drop = (d_total - s_total) / d_total
        if consistency < min_consistency or drop < structure_drop:
            continue
        out.append({
            "label": label,
            "noun": noun,
            "drafted_total": d_total,
            "sent_total": s_total,
            "drop_pct": round(100.0 * drop, 1),
            "pairs_present": present,
            "pairs_dropped": dropped,
            "pairs_raised": raised,
            "consistency": round(consistency, 3),
        })
    out.sort(key=lambda r: -r["drop_pct"])
    return out


# ── the paste-ready block ────────────────────────────────────────────────
def format_rules(mined, min_pairs=10, channel=None, min_occurrences=3, min_consistency=0.6):
    n = mined["pairs"]
    where = "channel `%s`" % channel if channel else "all channels"
    lines = []
    lines.append("## How this person edits your drafts")
    lines.append("")
    lines.append(
        "Derived from %d drafted/sent pair(s) in %s. Follow these when writing "
        "for them." % (n, where)
    )
    lines.append("")

    if not n:
        lines.append("Nothing recorded yet, so there is nothing to say.")
        return "\n".join(lines)

    # Length
    ln = mined["length"]
    if ln["median_ratio"]:
        lines.append("### Length")
        pct = int(round(ln["median_ratio"] * 100))
        if pct < 98:
            lines.append(
                "- Write about %d%% of your first instinct. Their median draft ran "
                "%d words and the version that went out ran %d."
                % (pct, ln["median_drafted_words"], ln["median_sent_words"])
            )
        elif pct > 102:
            lines.append(
                "- Your drafts run short for them. They added length in %d of %d "
                "pairs; the sent median is %d words against %d drafted."
                % (ln["longer_pairs"], ln["pairs"], ln["median_sent_words"],
                   ln["median_drafted_words"])
            )
        else:
            lines.append(
                "- Length is right. Median %d words drafted, %d sent."
                % (ln["median_drafted_words"], ln["median_sent_words"])
            )
        lines.append("")

    # Killed
    if mined["killed"]:
        lines.append("### Never write these")
        lines.append("")
        lines.append(
            "Each one appeared in a draft and was gone from the version that "
            "actually went out."
        )
        lines.append("")
        for row in mined["killed"]:
            lines.append(
                '- "%s" — cut %d of the %d time(s) it was written (%d%%)'
                % (row["phrase"], row["hits"], row["seen"],
                   round(row["consistency"] * 100))
            )
        lines.append("")

    # Added
    if mined["added"]:
        lines.append("### They put these in themselves")
        lines.append("")
        lines.append("Words that were not in the draft and were in the send.")
        lines.append("")
        for row in mined["added"]:
            lines.append(
                '- "%s" — added %d of the %d time(s) it appears (%d%%)'
                % (row["phrase"], row["hits"], row["seen"],
                   round(row["consistency"] * 100))
            )
        lines.append("")

    # Openers / closers
    for key, title, advice in (
        ("openers", "### The first sentence", "opener"),
        ("closers", "### The last sentence", "closer"),
    ):
        edge = mined[key]
        if not edge["total"]:
            continue
        lines.append(title)
        lines.append("")
        lines.append(
            "- Survived unchanged %d of %d times (%.0f%%)."
            % (edge["survived"], edge["total"], edge["survival_pct"])
        )
        if edge["survival_pct"] < 50 and edge["changes"]:
            lines.append(
                "- Your %s is the single most rewritten part of the message. "
                "What they replaced it with:" % advice
            )
            lines.append("")
            for change in edge["changes"][:6]:
                lines.append('  - you wrote: "%s"' % _trim(change["was"]))
                lines.append('    they sent: "%s"' % _trim(change["now"]))
        lines.append("")

    # Structure
    if mined["structure"]:
        lines.append("### Structure")
        lines.append("")
        for row in mined["structure"]:
            if row["sent_total"] == 0:
                lines.append(
                    "- No %s. You wrote %d across %d message(s); none survived."
                    % (row["label"], row["drafted_total"], row["pairs_present"])
                )
            else:
                lines.append(
                    "- Fewer %s. %d drafted, %d sent (%d%% cut), and they cut them "
                    "in %d of the %d message(s) that had any."
                    % (row["label"], row["drafted_total"], row["sent_total"],
                       round(row["drop_pct"]), row["pairs_dropped"], row["pairs_present"])
                )
        lines.append("")

    body_rules = (
        len(mined["killed"]) + len(mined["added"]) + len(mined["structure"])
    )
    if not body_rules:
        lines.append(
            "No phrase or structure habit repeated often enough to be a rule "
            "(the bar is %d occurrences and %d%% consistency). That either means "
            "the drafts are already close, or there are not enough pairs yet."
            % (min_occurrences, int(min_consistency * 100))
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Derived from %d pair(s). A phrase becomes a rule at %d occurrences and "
        "%d%% consistency." % (n, min_occurrences, int(min_consistency * 100))
    )
    if n < min_pairs:
        lines.append("")
        lines.append(
            "WARNING: %d pairs is thin. Under about %d these rules are mostly "
            "noise — one long message can invent a habit that is not there. "
            "Record more before pasting this into a prompt." % (n, min_pairs)
        )
    return "\n".join(lines)


def _trim(text, limit=140):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
