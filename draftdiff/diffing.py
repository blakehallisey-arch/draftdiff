"""The diff — word level, because these are paragraphs and not source files.

Why code and not a note: a line diff is useless here. The drafted text and the
sent text are the same prose wrapped differently, so `difflib.unified_diff`
reports the whole paragraph as replaced and the one word that actually changed
is invisible. This module aligns paragraphs first, then diffs word by word
inside the ones that moved, which is the only view that shows what the human
actually did.
"""
from __future__ import annotations

import difflib

from . import textutil as T

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
DIM = "\033[2m"


def _tokens(paragraph):
    """Whitespace-split. Punctuation stays glued to its word so the rendered
    diff reads like prose rather than like a lexer dump."""
    return paragraph.split()


def word_ops(before, after):
    """[(tag, before_words, after_words)] for two paragraphs."""
    a, b = _tokens(before), _tokens(after)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        ops.append((tag, a[i1:i2], b[j1:j2]))
    return ops


def paragraph_ops(drafted, sent):
    """[(tag, drafted_paras, sent_paras)] — the outer alignment."""
    a, b = T.paragraphs(drafted), T.paragraphs(sent)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        ops.append((tag, a[i1:i2], b[j1:j2]))
    return ops


def render(drafted, sent, color=False, width=88):
    """The human view. Deletions marked [- -], insertions {+ +}."""
    def mark(kind, text):
        if kind == "del":
            return (RED + "[-" + text + "-]" + RESET) if color else "[-" + text + "-]"
        return (GREEN + "{+" + text + "+}" + RESET) if color else "{+" + text + "+}"

    chunks = []
    for tag, before, after in paragraph_ops(drafted, sent):
        if tag == "equal":
            chunks.extend(before)
        elif tag == "delete":
            chunks.extend(mark("del", p) for p in before)
        elif tag == "insert":
            chunks.extend(mark("add", p) for p in after)
        else:
            # Pair them up and diff inside. Any tail on either side is a whole
            # paragraph added or dropped.
            for i in range(max(len(before), len(after))):
                if i < len(before) and i < len(after):
                    chunks.append(_render_paragraph(before[i], after[i], mark))
                elif i < len(before):
                    chunks.append(mark("del", before[i]))
                else:
                    chunks.append(mark("add", after[i]))
    body = "\n\n".join(_wrap(c, width) for c in chunks)
    return body


def _render_paragraph(before, after, mark):
    out = []
    for tag, a, b in word_ops(before, after):
        if tag == "equal":
            out.extend(a)
        elif tag == "delete":
            out.append(mark("del", " ".join(a)))
        elif tag == "insert":
            out.append(mark("add", " ".join(b)))
        else:
            out.append(mark("del", " ".join(a)))
            out.append(mark("add", " ".join(b)))
    return " ".join(out)


def _wrap(text, width):
    if width <= 0:
        return text
    out, line = [], ""
    for word in text.split(" "):
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return "\n".join(out)


def edit_stats(drafted, sent):
    """How much of the draft the human moved, as a share of the draft.

    `changed_pct` counts words deleted plus words inserted, over the drafted
    word count. It can exceed 100 — rewriting 40 words into 90 new ones is more
    than a complete edit, and pretending otherwise would flatten the trend.
    """
    d = T.words(T.normalize(drafted))
    s = T.words(T.normalize(sent))
    sm = difflib.SequenceMatcher(None, d, s, autojunk=False)
    matched = sum(block.size for block in sm.get_matching_blocks())
    removed = len(d) - matched
    added = len(s) - matched
    return {
        "drafted_words": len(d),
        "sent_words": len(s),
        "kept_words": matched,
        "removed_words": removed,
        "added_words": added,
        "changed_pct": round(100.0 * (removed + added) / len(d), 1) if d else 0.0,
        "kept_pct": round(100.0 * matched / len(d), 1) if d else 0.0,
        "length_ratio": round(len(s) / len(d), 3) if d else 0.0,
    }
