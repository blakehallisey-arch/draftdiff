"""Shared scaffolding: a throwaway store in a temp directory."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftdiff.store import Store  # noqa: E402


class TempStore:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="draftdiff-test-"))
        self.store = Store(path=self.dir / ".draftdiff" / "pairs.json")
        self.store.init()

    def add(self, drafted, sent, channel="email", created=None):
        return self.store.add(drafted, sent, channel=channel, created=created)

    def pairs(self):
        return self.store.pairs()

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)
