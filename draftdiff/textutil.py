"""Text shaping shared by the diff, the stats and the miner.

Why this is code and not a note: everything downstream compares two blocks of
prose that were written in different places. A draft goes into an editor
unwrapped and comes back out of a sent message hard-wrapped at some column
nobody chose. Compared line for line an untouched send reads as a total
rewrite, because every sentence boundary lands somewhere else. So the very
first thing that happens to any text here is that paragraphs get rejoined to
one line. Get that wrong and every number in this tool is wrong.
"""
from __future__ import annotations

import re

# A line that opens a list item or a heading is its own block, not a
# continuation of the sentence above it. Rejoining those into the previous
# paragraph would hide exactly the structure the miner is looking for.
BLOCK_START = re.compile(r"^\s*(?:[-*•+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s+)")

WORD_RE = re.compile(r"[a-z0-9']+")
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+")


def paragraphs(text):
    """Split into blocks, rejoining wrapped lines inside each one."""
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace(" ", " ")
    out = []
    current = []

    def flush():
        if current:
            out.append(" ".join(current))
            current.clear()

    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            flush()
            continue
        if BLOCK_START.match(raw):
            # A bullet or heading ends the paragraph above it and stands alone,
            # so the prose line after a list does not get glued to the last item.
            flush()
            out.append(line)
            continue
        current.append(line)
    flush()
    return [p for p in out if p]


def normalize(text):
    """One paragraph per line, no stray whitespace. The comparison surface."""
    return "\n".join(paragraphs(text)).strip()


def words(text):
    """Lowercased word tokens. Punctuation is dropped on purpose: the miner
    should treat 'reach out,' and 'reach out' as the same phrase."""
    return WORD_RE.findall((text or "").lower())


def sentences(text):
    """Sentences, in order, across every paragraph."""
    out = []
    for para in paragraphs(text):
        for part in SENT_SPLIT.split(para):
            part = part.strip()
            if part:
                out.append(part)
    return out


def ngrams(tokens, n):
    """Every contiguous n-token run, as tuples."""
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def ngram_set(tokens, max_n):
    """Every 1..max_n gram present, deduped. Membership is what the miner asks
    about ('did this phrase survive'), not how many times it occurred."""
    out = set()
    for n in range(1, max_n + 1):
        out.update(ngrams(tokens, n))
    return out


def phrase(gram):
    return " ".join(gram)


def is_contiguous_sub(short, long_):
    """Is `short` a contiguous run inside `long_`?"""
    n = len(short)
    if n >= len(long_):
        return False
    return any(long_[i:i + n] == short for i in range(len(long_) - n + 1))


def median(values):
    vals = sorted(values)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0
