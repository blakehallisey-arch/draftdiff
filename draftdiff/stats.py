"""The trend — is the gap between what the agent writes and what you send
getting smaller?

Why code and not a note: the whole claim of this tool is that feeding the rules
back into the prompt shrinks the next diff. That claim is falsifiable, and this
is the file that falsifies it. It compares the median edit on the last five
pairs against the median on the five before, and says the number plainly in
both directions. If the edits are getting bigger it says that too.
"""
from __future__ import annotations

from . import textutil as T
from .diffing import edit_stats

WINDOW = 5


def summarize(pairs):
    """Overall numbers for one list of pairs, already in chronological order."""
    rows = [edit_stats(p["drafted"], p["sent"]) for p in pairs]
    out = {
        "pairs": len(pairs),
        "median_edit_pct": T.median([r["changed_pct"] for r in rows]),
        "median_kept_pct": T.median([r["kept_pct"] for r in rows]),
        "median_drafted_words": T.median([r["drafted_words"] for r in rows]),
        "median_sent_words": T.median([r["sent_words"] for r in rows]),
        "trend": trend(rows),
    }
    return out


def trend(rows):
    """Last WINDOW vs the WINDOW before it.

    Needs 2*WINDOW pairs. Comparing a window of five against a window of two
    would produce a headline number off two messages, which is exactly the kind
    of confident noise this tool is supposed to refuse.
    """
    need = WINDOW * 2
    if len(rows) < need:
        return {
            "enough": False,
            "have": len(rows),
            "need": need,
            "text": "not enough pairs to call a trend yet (%d of %d)" % (len(rows), need),
        }
    recent = T.median([r["changed_pct"] for r in rows[-WINDOW:]])
    earlier = T.median([r["changed_pct"] for r in rows[-need:-WINDOW]])
    if earlier == 0:
        change = 0.0
    else:
        change = (earlier - recent) / earlier * 100.0
    direction = "less" if change > 0 else "more"
    if abs(change) < 1:
        text = "your last %d drafts needed about the same editing as the %d before" % (
            WINDOW, WINDOW)
    else:
        text = "your last %d drafts needed %.0f%% %s editing than the %d before" % (
            WINDOW, abs(change), direction, WINDOW)
    return {
        "enough": True,
        "recent_median_edit_pct": recent,
        "earlier_median_edit_pct": earlier,
        "change_pct": round(change, 1),
        "direction": direction,
        "text": text,
    }


def report(pairs):
    """Overall plus a block per channel."""
    by_channel = {}
    for p in pairs:
        by_channel.setdefault(p.get("channel") or "email", []).append(p)
    return {
        "overall": summarize(pairs),
        "channels": {name: summarize(rows) for name, rows in sorted(by_channel.items())},
    }


def format_report(data):
    lines = []
    overall = data["overall"]
    if not overall["pairs"]:
        return ["No pairs recorded yet. `draftdiff add` one and this fills in."]
    lines.append("DRAFTDIFF — %d pair(s)" % overall["pairs"])
    lines.append("")
    lines.append(_block("overall", overall))
    if len(data["channels"]) > 1:
        for name, block in data["channels"].items():
            lines.append("")
            lines.append(_block(name, block))
    return lines


def _block(name, s):
    out = [
        "%s" % name,
        "  pairs                %d" % s["pairs"],
        "  median edit          %.0f%% of the draft moved" % s["median_edit_pct"],
        "  median kept          %.0f%% of the drafted wording survived" % s["median_kept_pct"],
        "  median length        %d words drafted -> %d sent" % (
            s["median_drafted_words"], s["median_sent_words"]),
        "  trend                %s" % s["trend"]["text"],
    ]
    return "\n".join(out)
