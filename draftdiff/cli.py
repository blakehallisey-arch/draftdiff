"""The command line. Six verbs: init, add, show, list, stats, rules, import.

Why code and not a note: the capture has to be cheap or it does not happen. If
recording a pair costs more than piping two files, nobody records the pair, and
a voice-learning tool with no corpus is a blog post.

Exit codes: 0 fine, 1 error, 2 stop and look up (used when `rules` is asked to
speak on a corpus too thin to speak on).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import __version__
from . import mining, stats
from .diffing import edit_stats, render
from .store import (CONFIG_FILE, DEFAULT_CONFIG, STATE_DIR, Store, StoreError,
                    load_config)

OK, ERROR, LOOK = 0, 1, 2


def _read_source(path_arg, text_arg, label, stdin_used):
    """A file path, `-` for stdin, or inline text. Exactly one."""
    if path_arg and text_arg:
        raise StoreError("--%s and --%s-text are mutually exclusive" % (label, label))
    if text_arg is not None:
        return text_arg, stdin_used
    if path_arg is None:
        raise StoreError("--%s or --%s-text is required" % (label, label))
    if path_arg == "-":
        if stdin_used:
            raise StoreError(
                "stdin can only feed one side; pass the other as a file or "
                "with --%s-text" % label
            )
        return sys.stdin.read(), True
    p = Path(path_arg).expanduser()
    if not p.is_file():
        raise StoreError("no such file: %s" % p)
    return p.read_text(), stdin_used


def _use_color(flag):
    if flag == "always":
        return True
    if flag == "never":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _store(args):
    return Store(path=getattr(args, "store", None))


# ── verbs ────────────────────────────────────────────────────────────────
def cmd_init(args):
    store = _store(args)
    created = store.init()
    root = store.root
    cfg = root / CONFIG_FILE
    if not cfg.exists():
        cfg.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    print("%s %s" % ("created" if created else "already there:", store.path))
    print("config: %s" % cfg)
    print("Add .draftdiff/ to .gitignore — drafts carry real names and addresses.")
    return OK


def cmd_add(args):
    store = _store(args)
    used = False
    drafted, used = _read_source(args.drafted, args.drafted_text, "drafted", used)
    sent, used = _read_source(args.sent, args.sent_text, "sent", used)
    pair = store.add(
        drafted=drafted,
        sent=sent,
        channel=args.channel,
        subject=args.subject or "",
        tags=args.tag or [],
    )
    st = edit_stats(pair["drafted"], pair["sent"])
    print(
        "%s  %s  %d words drafted -> %d sent, %.0f%% of the draft moved"
        % (pair["id"], pair["channel"], st["drafted_words"], st["sent_words"],
           st["changed_pct"])
    )
    return OK


def cmd_list(args):
    store = _store(args)
    rows = store.pairs(channel=args.channel)
    if not rows:
        print("No pairs recorded yet.")
        return OK
    if args.json:
        print(json.dumps([{k: v for k, v in r.items() if k not in ("drafted", "sent")}
                          for r in rows], indent=2))
        return OK
    for r in rows:
        st = edit_stats(r["drafted"], r["sent"])
        print("%s  %-8s %-10s %3.0f%%  %s"
              % (r["id"], r["created"][:10], r["channel"], st["changed_pct"],
                 (r.get("subject") or "")[:48]))
    return OK


def cmd_show(args):
    store = _store(args)
    pair = store.get(args.id)
    if pair is None:
        print("no pair with id %r" % args.id, file=sys.stderr)
        return ERROR
    st = edit_stats(pair["drafted"], pair["sent"])
    if args.json:
        print(json.dumps({**pair, "stats": st}, indent=2))
        return OK
    print("%s  %s  %s" % (pair["id"], pair["created"], pair["channel"]))
    if pair.get("subject"):
        print("subject: %s" % pair["subject"])
    print(
        "%d words drafted -> %d sent  ·  %.0f%% of the drafted wording kept  ·  "
        "%.0f%% of the draft moved"
        % (st["drafted_words"], st["sent_words"], st["kept_pct"], st["changed_pct"])
    )
    print()
    print(render(pair["drafted"], pair["sent"], color=_use_color(args.color)))
    return OK


def cmd_stats(args):
    store = _store(args)
    rows = store.pairs(channel=args.channel)
    data = stats.report(rows)
    if args.json:
        print(json.dumps(data, indent=2))
        return OK
    for line in stats.format_report(data):
        print(line)
    return OK


def cmd_rules(args):
    store = _store(args)
    cfg = load_config(store.root)
    rows = store.pairs(channel=args.channel)
    min_pairs = args.min_pairs if args.min_pairs is not None else cfg["min_pairs"]
    mined = mining.mine(
        rows,
        min_occurrences=cfg["min_occurrences"],
        min_consistency=cfg["min_consistency"],
        max_ngram=cfg["max_ngram"],
        structure_drop=cfg["structure_drop"],
    )
    if args.json:
        print(json.dumps({**mined, "min_pairs": min_pairs}, indent=2))
    else:
        print(mining.format_rules(
            mined,
            min_pairs=min_pairs,
            channel=args.channel,
            min_occurrences=cfg["min_occurrences"],
            min_consistency=cfg["min_consistency"],
        ))
    # Exit 2, not 0: the block printed, and it is also telling you not to trust
    # it yet. A script piping this into a prompt should be able to notice.
    return LOOK if len(rows) < min_pairs else OK


PAIR_NAME = re.compile(r"^(?P<key>.+?)\.drafted\.(?:txt|md)$")


def cmd_import(args):
    store = _store(args)
    directory = Path(args.dir).expanduser()
    if not directory.is_dir():
        print("no such directory: %s" % directory, file=sys.stderr)
        return ERROR
    added = skipped = 0
    for drafted_path in sorted(directory.iterdir()):
        match = PAIR_NAME.match(drafted_path.name)
        if not match:
            continue
        key = match.group("key")
        sent_path = None
        for ext in ("txt", "md"):
            candidate = directory / ("%s.sent.%s" % (key, ext))
            if candidate.is_file():
                sent_path = candidate
                break
        if sent_path is None:
            print("  %s has no matching .sent file — skipped" % drafted_path.name)
            skipped += 1
            continue
        meta = {}
        meta_path = directory / ("%s.meta.json" % key)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text())
            except json.JSONDecodeError as exc:
                print("  %s is not valid JSON (%s) — importing without it"
                      % (meta_path.name, exc))
        pair = store.add(
            drafted=drafted_path.read_text(),
            sent=sent_path.read_text(),
            channel=meta.get("channel") or args.channel,
            subject=meta.get("subject", ""),
            tags=meta.get("tags") or [],
            created=meta.get("created"),
        )
        added += 1
        print("  %s  %s" % (pair["id"], key))
    print("imported %d pair(s), skipped %d" % (added, skipped))
    return OK


# ── wiring ───────────────────────────────────────────────────────────────
def build_parser():
    ap = argparse.ArgumentParser(
        prog="draftdiff",
        description="Learn a writing voice from the edits made before hitting send.",
    )
    ap.add_argument("--version", action="version", version="draftdiff %s" % __version__)
    ap.add_argument("--store", metavar="PATH",
                    help="pairs.json to use (default: nearest %s/pairs.json)" % STATE_DIR)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create %s/ and a config file" % STATE_DIR)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="record one drafted/sent pair")
    p.add_argument("--drafted", metavar="FILE", help="file, or - for stdin")
    p.add_argument("--sent", metavar="FILE", help="file, or - for stdin")
    p.add_argument("--drafted-text", metavar="TEXT", help="the draft inline")
    p.add_argument("--sent-text", metavar="TEXT", help="what went out, inline")
    p.add_argument("--channel", default="email",
                   help="free text: email, pr, commit, slack, doc (default: email)")
    p.add_argument("--subject", default="", help="whatever you want to find it by later")
    p.add_argument("--tag", action="append", metavar="TAG", help="repeatable")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="every pair, one line each")
    p.add_argument("--channel")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="the word-level diff for one pair")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats", help="how much editing, and is it shrinking")
    p.add_argument("--channel")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("rules", help="the paste-ready style block")
    p.add_argument("--channel")
    p.add_argument("--json", action="store_true")
    p.add_argument("--min-pairs", type=int, default=None,
                   help="below this the block warns about itself and exits 2")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("import", help="bulk import NNN.drafted.txt / NNN.sent.txt")
    p.add_argument("--dir", required=True)
    p.add_argument("--channel", default="email")
    p.set_defaults(func=cmd_import)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return OK
    try:
        return args.func(args)
    except StoreError as exc:
        print("draftdiff: %s" % exc, file=sys.stderr)
        return ERROR
    except BrokenPipeError:
        return OK


if __name__ == "__main__":
    sys.exit(main())
