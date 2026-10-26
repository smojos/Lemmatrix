# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Two tokens of a lemma that a change to the tag structure would give one soundfile name.

Making a tag its group's default takes its file-name code away (a default adds nothing to file
names), so a token tagged with it and nothing else but defaults gets the citation token's name:
make Frame 1 the default and A009's "Singular · Nominative · isolation · Frame 1" is named
LXX-VXX_A009_head.wav, like A009's tagless citation token (Josh, 26 October: found while asking
whether it had been solved; it hadn't). A shared code does the same.

On OK in the tag structure the clashes are listed, with a choice (Josh: "give the option of 2 or
3 or cancel"): give each the next Example tag (x1…), as the token dialogue does for a clash; or
choose for each, Example tag or **merge** the two tokens into one; or Cancel. Merging keeps the
token with fewer tags (the citation token, say) and fills its empty fields from the other; it is
offered only when no field has two different values. With two recordings, the merge keeps the one
chosen (as *Overwrite the token* asks); the other waits in Soundfiles/_Deleted recordings and goes
to the Recycle Bin when the database is closed.
No Qt here."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Database, Entry, Token

EXAMPLE, MERGE, MERGE_THEIRS = "example", "merge", "merge-theirs"   # MERGE keeps `keep`'s recording


@dataclass
class Clash:
    entry: Entry
    keep: Token          # stays as it is (the one with fewer tags: the citation token, often)
    other: Token         # gets an Example tag, or is merged into `keep`
    name: str            # the soundfile name both would get

    @property
    def merge_problem(self) -> str:
        return merge_problem(self.keep, self.other)

    @property
    def two_recordings(self) -> bool:
        return bool(self.keep.file and self.other.file and self.keep.file != self.other.file)


def _fields(t: Token) -> dict[str, str]:
    out = {f"v:{k}": v for k, v in t.values.items() if v.strip()}
    out.update({f"m:{k}:{lang}": v for k, d in t.multi.items() for lang, v in d.items() if v.strip()})
    return out


def _label(key: str) -> str:
    parts = key.split(":")
    return parts[1] + (f" ({parts[2]})" if len(parts) > 2 and parts[2] not in ("", "en") else "")


def merge_problem(keep: Token, other: Token) -> str:
    """Why the two can't become one without losing something ("" if they can). Two recordings
    don't stop it: the merge keeps the one chosen."""
    a, b = _fields(keep), _fields(other)
    both = sorted(_label(k) for k in a.keys() & b.keys() if a[k].strip() != b[k].strip())
    if both:
        return "both have " + ", ".join(dict.fromkeys(both))
    for attr, what in (("speaker", "a speaker"), ("collected", "a date")):
        x, y = getattr(keep, attr), getattr(other, attr)
        if x and y and x != y:
            return f"both have {what}, different"
    return ""


def find(db: Database, new_tags, renames: dict | None = None, deleted: set | None = None) -> list[Clash]:
    """The pairs of tokens that the tag structure `new_tags` (with tags renamed and deleted as the
    editor says) would give the same soundfile name, and that don't share one now."""
    renames, deleted = renames or {}, set(deleted or ())
    s = db.settings
    old_tags = s.tags
    before = {}
    for e in db.entries:
        for t in e.tokens:
            before[id(t)] = db.expected_filename(e, t).lower()
    saved = [(t, t.tags) for e in db.entries for t in e.tokens]
    out: list[Clash] = []
    try:
        s.tags = new_tags
        for t, tags in saved:
            t.tags = [renames.get(x, x) for x in tags if x not in deleted]
        for e in db.entries:
            groups: dict[str, list[Token]] = {}
            for t in e.tokens:
                groups.setdefault(db.expected_filename(e, t).lower(), []).append(t)
            for name, toks in groups.items():
                if len(toks) < 2 or len({before[id(t)] for t in toks}) == 1:
                    continue                      # one token, or they shared a name already
                toks = sorted(toks, key=lambda t: (len(t.tags), e.tokens.index(t)))
                keep = toks[0]
                for t in toks[1:]:
                    out.append(Clash(e, keep, t, db.expected_filename(e, t)))
    finally:
        s.tags = old_tags
        for t, tags in saved:
            t.tags = tags
    return out


def apply(db: Database, clashes: list[Clash], choice: dict[int, str]) -> tuple[int, int]:
    """After the new structure is in use: each clash's `other` gets the next Example tag, or is
    merged into `keep` (choice[i] for clash i; Example by default). Returns (tagged, merged)."""
    from . import move
    tagged = merged = 0
    planned: dict[int, list[Token]] = {}
    for i, c in enumerate(clashes):
        how = choice.get(i, EXAMPLE)
        if how in (MERGE, MERGE_THEIRS) and not c.merge_problem and c.other in c.entry.tokens:
            if c.two_recordings:                  # one recording kept, the other held
                drop = c.other if how == MERGE else c.keep
                kept = c.keep.file if how == MERGE else c.other.file
                _hold(db, c.entry, drop.file)
                c.keep.file = c.other.file = kept
            _merge(c.keep, c.other)
            c.entry.tokens.remove(c.other)
            merged += 1
            continue
        tag = move.free_example(db, c.entry, c.other, planned.setdefault(id(c.entry), []))
        move._ensure_example(db, tag)
        group = move.examples_group(db)
        mine = {x.name for x in group.tags} if group else set()
        c.other.tags = db.settings.tags.sort([x for x in c.other.tags if x not in mine] + [tag])
        planned[id(c.entry)].append(c.other)
        tagged += 1
    return tagged, merged


def _hold(db: Database, entry: Entry, name: str):
    """The recording not kept: into Soundfiles/_Deleted recordings (the Recycle Bin on closing)."""
    from . import storage
    if not name or not db.path:
        return
    src = storage.folder_for(db, entry) / name
    if not src.exists():
        return
    folder = storage.held_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    target, n = folder / src.name, 2
    while target.exists():
        target, n = folder / f"{src.stem} ({n}){src.suffix}", n + 1
    src.rename(target)


def _merge(keep: Token, other: Token):
    """`keep` takes what it doesn't have of `other`: fields, the recording, speaker, date."""
    for k, v in other.values.items():
        if v.strip() and not keep.values.get(k, "").strip():
            keep.values[k] = v
    for k, d in other.multi.items():
        mine = keep.multi.setdefault(k, {})
        for lang, v in d.items():
            if v.strip() and not mine.get(lang, "").strip():
                mine[lang] = v
    for k, v in other.changed.items():
        keep.changed.setdefault(k, v)
    if not keep.file and other.file:
        keep.file = other.file
    if not keep.speaker:
        keep.speaker = other.speaker
    if not keep.collected:
        keep.collected = other.collected
    keep.rerecord = keep.rerecord or other.rerecord
