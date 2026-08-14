# draftdiff

Learns your writing voice from the edits you make before you hit send, and
writes the style rules back out as a block you paste into your agent's prompt.

## The problem

An assistant drafted an email. It opened "I hope this email finds you well. I
wanted to reach out regarding the pricing proposal," and ran a hundred and
seventy-five words. Before sending, the human deleted the opener, deleted the
hedges, cut it to seventy-five words, and replaced the closing paragraph with
"Can you do 30 minutes Thursday or Friday." Then they sent it.

The next day the assistant drafted another email. It opened "I hope this email
finds you well."

That edit was the best writing sample anybody had. It is the exact delta between
what a machine wrote and what a person was willing to put their name on, and it
was made in a compose window that nothing reads. Every correction in that loop
gets made once and learned zero times. draftdiff is the piece that catches the
two versions and counts what changed across all of them.

## Install

```
git clone https://github.com/blakehallisey-arch/draftdiff && cd draftdiff
./install.sh          # or just run: python3 -m draftdiff --help
```

Python 3.9 or newer. No dependencies.

## What it looks like

Recording a pair, then reading the diff back:

```
$ draftdiff add --drafted drafts/pricing.txt --sent sent/pricing.txt --channel email
55842376  email  120 words drafted -> 57 sent, 78% of the draft moved

$ draftdiff show 5584
55842376  2026-06-09T08:05:00  email
subject: Re: Senior Product Manager role
120 words drafted -> 57 sent  ·  35% of the drafted wording kept  ·  78% of the draft moved

Hi Priya,

{+Yes,+} I [-hope this finds you well. Thank you so much for reaching out about-] {+am
interested in+} the Senior Product Manager [-role — I was really excited to see it land
in my inbox!-] {+role.+}

[-I would definitely be interested in learning more. I think my background lines up
quite well with what you described;-] {+The fit is the platform side.+} I have spent
[-the last-] four years on [-platform and-] infrastructure products, most recently
owning the API [-surface-] that about 3,000 developers build on.

I am [-generally-] free most afternoons this week and next. [-Please let me know what
works-] {+Send a link+} and I will [-make it happen, or feel free to send over a link to
your calendar at your earliest convenience.-] {+book something.+}

[-Looking forward to speaking!-]

Best, Dana
```

The trend, which is the only number that says whether this is working:

```
$ draftdiff stats
DRAFTDIFF — 12 pair(s)

overall
  pairs                12
  median edit          76% of the draft moved
  median kept          39% of the drafted wording survived
  median length        125 words drafted -> 58 sent
  trend                your last 5 drafts needed 51% less editing than the 5 before

email
  pairs                9
  median edit          76% of the draft moved
  median kept          37% of the drafted wording survived
  median length        120 words drafted -> 58 sent
  trend                not enough pairs to call a trend yet (9 of 10)
```

And the command the whole tool exists for. This is the real output over the
twelve pairs in `examples/`, unedited:

```
$ draftdiff rules

## How this person edits your drafts

Derived from 12 drafted/sent pair(s) in all channels. Follow these when writing for them.

### Length
- Write about 55% of your first instinct. Their median draft ran 125 words and the version that went out ran 58.

### Never write these

Each one appeared in a draft and was gone from the version that actually went out.

- "i think" — cut 9 of the 9 time(s) it was written (100%)
- "please" — cut 7 of the 7 time(s) it was written (100%)
- "really" — cut 7 of the 7 time(s) it was written (100%)
- "know" — cut 6 of the 6 time(s) it was written (100%)
- "i wanted to reach out" — cut 5 of the 5 time(s) it was written (100%)
- "have any questions" — cut 4 of the 4 time(s) it was written (100%)
- "i hope" — cut 4 of the 4 time(s) it was written (100%)
- "please don't hesitate to reach out" — cut 3 of the 3 time(s) it was written (100%)
- "at your earliest convenience" — cut 3 of the 3 time(s) it was written (100%)
- "i will circle back" — cut 3 of the 3 time(s) it was written (100%)
- "please let me know" — cut 3 of the 3 time(s) it was written (100%)
- "finds you well" — cut 3 of the 3 time(s) it was written (100%)
- "really excited" — cut 3 of the 3 time(s) it was written (100%)
- "just" — cut 3 of the 3 time(s) it was written (100%)
- "leverage" — cut 3 of the 3 time(s) it was written (100%)
- "roughly" — cut 3 of the 3 time(s) it was written (100%)

### They put these in themselves

Words that were not in the draft and were in the send.

- "can you" — added 4 of the 4 time(s) it appears (100%)

### The first sentence

- Survived unchanged 2 of 12 times (17%).
- Your opener is the single most rewritten part of the message. What they replaced it with:

  - you wrote: "Hi Marcus, I hope this email finds you well!"
    they sent: "Hi Marcus, Two things in the pricing proposal do not work for us."
  - you wrote: "Hi team, I wanted to reach out with a quick update on where we landed for Q3."
    they sent: "Hi team, Q3 update."
  - you wrote: "Hi Priya, I hope this finds you well."
    they sent: "Hi Priya, Yes, I am interested in the Senior Product Manager role."
  - you wrote: "## Summary"
    they sent: "Three call sites wrote `sessions.json` directly, so a partial write from any one of them left a file the other two could not parse."
  - you wrote: "Hi Alex, I hope you are having a good week."
    they sent: "Hi Alex, Support tickets have gone from 40 a day to 120 since the release on the 3rd."
  - you wrote: "Hi Renee, I hope this email finds you well."
    they sent: "Hi Renee, Following up on the renewal."

### The last sentence

- Survived unchanged 8 of 12 times (67%).

### Structure

- No bullet list items. You wrote 12 across 3 message(s); none survived.
- No markdown headings. You wrote 9 across 3 message(s); none survived.
- No exclamation marks. You wrote 6 across 5 message(s); none survived.
- No semicolons. You wrote 5 across 5 message(s); none survived.

---

Derived from 12 pair(s). A phrase becomes a rule at 3 occurrences and 60% consistency.
```

The whole file is in `examples/rules-output.md`. Paste it into the system prompt
of whatever writes your drafts, and the next diff should be smaller. `stats`
tells you whether it was.

## How it works

You give it two blocks of text. It stores them and does arithmetic.

**Normalizing.** Before anything is compared, every paragraph is rejoined to one
line. This matters more than it sounds. A draft goes into a compose window
unwrapped and comes back out of the sent folder hard-wrapped at some column
nobody chose, so a line diff reports an untouched message as a total rewrite.
Everything downstream would then be measuring the mail client.

**The diff.** Paragraphs are aligned first, then the ones that moved are diffed
word by word. That is why a rewrapped paragraph with one changed word shows one
deletion and one insertion instead of eight changed lines.

**The mining.** For every phrase of one to three words, it counts how many
drafts contained it and in how many of those it was gone from the sent version.
A phrase becomes a rule only when both bars are cleared: at least
`min_occurrences` deletions, and at least `min_consistency` of the drafts that
contained it. Three more filters sit on top, and each one is there because the
first version printed the rule it now removes:

- A phrase made entirely of function words is dropped. When somebody cuts half
  of every draft, "for" and "with" and "to the" clear any bar you set. That is
  not a preference, that is deletion being wholesale.
- A phrase has to beat the corpus baseline. If 60% of every draft dies, a 60%
  deletion rate is what nothing special looks like. `roughly` earned its line by
  being cut more often than the average word was.
- Overlapping fragments are chained back into the phrase they came out of, so
  "wanted to", "to reach" and "reach out" become one rule about "i wanted to
  reach out" instead of three about nothing.

**What it cannot see.** Why. It has no idea that you cut "excited" because the
recipient had just been laid off. It sees text in, text out, and counts. It also
cannot see anything you did not give it — there is no mailbox integration, so a
message you never recorded does not exist as far as this is concerned.

**Where state lives.** `.draftdiff/pairs.json`, in the nearest ancestor
directory that has a `.draftdiff/`, the way git finds `.git`. Writes are atomic
and the previous file is kept alongside as `pairs.json.bak`, because the drafted
side is the perishable half — once a message is sent, nothing can re-derive what
the machine originally wrote. Nothing is written anywhere else. Add
`.draftdiff/` to your `.gitignore`; drafts carry real names and real addresses.

## Configuration

One file, `draftdiff.json`, at the root of the directory holding `.draftdiff/`.
Every key is optional. Unknown keys are an error, not a shrug.

| key | default | what it does |
|---|---|---|
| `min_occurrences` | `3` | how many times a phrase must be cut before it is a rule at all |
| `min_consistency` | `0.6` | and in what share of the drafts that contained it |
| `max_ngram` | `3` | longest phrase mined directly; longer rules are built by chaining |
| `min_pairs` | `10` | below this, `rules` warns about itself and exits 2 |
| `structure_drop` | `0.25` | how far a structural habit (bullets, headings, em dashes) must fall corpus-wide before it is reported |

Commands: `init`, `add`, `list`, `show`, `stats`, `rules`, `import`. Every one
takes `--help`; `list`, `show`, `stats` and `rules` take `--json`. `add` reads a
file, or `-` for stdin, or `--drafted-text` / `--sent-text` inline. `import
--dir <path>` backfills a directory of `NNN.drafted.txt` / `NNN.sent.txt` pairs,
with an optional `NNN.meta.json` carrying `channel`, `subject` and `created`.

Exit codes: 0 fine, 1 error, 2 stop and look up. `rules` returns 2 when it is
speaking on fewer pairs than `min_pairs`, so a script that pipes it into a
prompt can notice.

## What this is not

- **It does not send anything, read your mailbox, or connect to any service.**
  There is no network code in this repo. You hand it two blocks of text. If you
  want it wired to a mail client, that glue is yours to write and it stays
  yours.
- **It is not a fine-tuning pipeline.** The output is English you paste into a
  prompt. Nothing is trained, nothing is uploaded, no model weights are
  involved.
- **It is descriptive, not prescriptive.** It reports the habit, not the good
  habit. Spend a month nervously deleting every number from your drafts and it
  will cheerfully instruct your agent to stop writing numbers. Read the block
  before you paste it.
- **Under about ten pairs the rules are noise.** One long message can invent a
  habit that is not there. The block says so in its own footer and the command
  exits 2, but it will still print, because a tool that refuses to show you your
  own data is worse.
- **It only sees text.** Not tone in the room, not the relationship, not the
  fact that the person you were writing to had already said no twice.

## Part of a family

Six small tools for the case where an AI coding agent does the work and a human
is not watching every step.

| repo | one line |
|---|---|
| [curfew](https://github.com/blakehallisey-arch/curfew) | write-time policy for an unattended agent — deny by rule, not by prompt |
| [breaker](https://github.com/blakehallisey-arch/breaker) | stops a session that is spinning, spreading, or inventing work |
| [shipgate](https://github.com/blakehallisey-arch/shipgate) | will not let a merge through until the checks it actually needs have run |
| [nightwatch](https://github.com/blakehallisey-arch/nightwatch) | the run rail — a queue, a budget lid, a window, and an honest log |
| draftdiff | learns your voice from the edits you make before you hit send |
| [ledger](https://github.com/blakehallisey-arch/ledger) | gives stateless agents a memory of what you did with their advice |
