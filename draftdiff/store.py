"""The pair store — every drafted/sent couple, on disk, as JSON.

Why code and not a note: the drafted side is the perishable half. The moment a
message is sent, most tools overwrite or discard the version the agent wrote,
and nothing anywhere can re-derive it. So the store's one real job is to never
lose a `drafted` body it has already accepted. Writes are atomic and the
previous file is kept as `.bak`, because a half-written pairs.json read by the
next run is indistinguishable from an empty one.

State lives in `.draftdiff/pairs.json`, found by walking up from the working
directory the same way git finds `.git`. Nothing is ever written outside it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import uuid
from pathlib import Path

STATE_DIR = ".draftdiff"
PAIRS_FILE = "pairs.json"
CONFIG_FILE = "draftdiff.json"

DEFAULT_CONFIG = {
    # A phrase must be cut this many times before it is a rule at all.
    "min_occurrences": 3,
    # ...and in at least this share of the drafts that contained it. One
    # deletion is a mood; six out of seven is a habit.
    "min_consistency": 0.6,
    # Longest phrase the miner will consider, in words.
    "max_ngram": 3,
    # Below this many pairs the rules block prints a warning about itself.
    "min_pairs": 10,
    # A structural habit (bullets, headers, em-dashes) counts only when the
    # total drops by at least this much across the corpus.
    "structure_drop": 0.25,
}


class StoreError(Exception):
    """A store that exists but cannot be read. Deliberately different from a
    store that is absent — conflating the two is how a truncated file gets
    read as 'nothing here yet' and then overwritten with an empty one."""


def find_root(start=None):
    """Nearest ancestor directory holding a .draftdiff/, else the start dir."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / STATE_DIR).is_dir():
            return candidate
    return here


def load_config(root):
    """Repo-root draftdiff.json merged over the defaults. JSON, not TOML, so
    there is no parser dependency on Python 3.9 (tomllib landed in 3.11)."""
    cfg = dict(DEFAULT_CONFIG)
    path = Path(root) / CONFIG_FILE
    if path.exists():
        try:
            user = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"{path} exists but could not be read: {exc}") from exc
        if not isinstance(user, dict):
            raise StoreError(f"{path} must contain a JSON object")
        unknown = sorted(set(user) - set(DEFAULT_CONFIG))
        if unknown:
            raise StoreError(f"{path} has unknown key(s): {', '.join(unknown)}")
        cfg.update(user)
    return cfg


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path=None, root=None):
        if path:
            self.path = Path(path).expanduser().resolve()
            self.root = self.path.parent.parent
        else:
            self.root = Path(find_root(root))
            self.path = self.root / STATE_DIR / PAIRS_FILE

    # ── reading ──────────────────────────────────────────────────────────
    def exists(self):
        return self.path.exists()

    def load(self):
        if not self.path.exists():
            return {"version": 1, "pairs": []}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"{self.path} exists but could not be read: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
            raise StoreError(f"{self.path} is the wrong shape — refusing to overwrite it")
        return data

    def pairs(self, channel=None):
        rows = self.load()["pairs"]
        rows.sort(key=lambda p: (p.get("created") or "", p.get("id") or ""))
        if channel:
            rows = [p for p in rows if p.get("channel") == channel]
        return rows

    def channels(self):
        seen = []
        for p in self.pairs():
            if p.get("channel") and p["channel"] not in seen:
                seen.append(p["channel"])
        return seen

    def get(self, pair_id):
        """Exact id, else unique prefix. An ambiguous prefix is an error, not a
        guess — showing the wrong pair silently is worse than saying no."""
        rows = self.pairs()
        for p in rows:
            if p["id"] == pair_id:
                return p
        hits = [p for p in rows if p["id"].startswith(pair_id)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise StoreError(
                "id %r matches %d pairs: %s"
                % (pair_id, len(hits), ", ".join(h["id"] for h in hits))
            )
        return None

    # ── writing ──────────────────────────────────────────────────────────
    def init(self):
        (self.root / STATE_DIR).mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": 1, "pairs": []})
            return True
        return False

    def add(self, drafted, sent, channel="email", subject="", tags=None, created=None):
        if not (drafted or "").strip():
            raise StoreError("refusing to record a pair with an empty drafted side")
        if not (sent or "").strip():
            raise StoreError(
                "refusing to record a pair with an empty sent side — if the draft "
                "was thrown away entirely, that is a decision, not an edit"
            )
        data = self.load()
        pair = {
            "id": uuid.uuid4().hex[:8],
            "created": created or now(),
            "channel": channel or "email",
            "subject": subject or "",
            "drafted": drafted,
            "sent": sent,
            "tags": list(tags or []),
        }
        data["pairs"].append(pair)
        self._write(data)
        return pair

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)
