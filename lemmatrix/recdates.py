"""Tools → Fill in recording dates from the sound files: the token's date from its recording."""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass

from . import audio, storage
from .model import Database, Entry, is_utterance

FILE_DATE = "the date the file was last changed"


@dataclass
class Change:
    entry: Entry
    index: int
    old: str
    new: str
    source: str


def plan(db: Database, overwrite: bool = False, file_dates: bool = False,
         skip: set[str] = frozenset()) -> tuple[list[Change], dict[str, int]]:
    """The dates to fill in, and counts of what was left alone.

    overwrite: also change a date that differs from the recording's; file_dates: when the
    recording has no date in it, use the date the file was last changed; skip: file names not
    to read (online-only ones, which reading would download)."""
    out, counts = [], {"no date in the file": 0, "not in the sound folder": 0, "online only": 0,
                       "already the same": 0, "kept (has a date)": 0}
    for e in db.items():                          # lemmas' tokens and utterances
        folder = storage.folder_for(db, e)
        for i, t in enumerate(e.tokens):
            if not t.file:
                continue
            if t.collected and not overwrite:
                counts["kept (has a date)"] += 1
                continue
            path = folder / t.file
            # skip names the tokens' folder's online-only files; the utterances' are checked here
            if (t.file in skip and not is_utterance(e)) or (is_utterance(e) and storage.is_cloud_only(path)):
                counts["online only"] += 1
                continue
            if not path.exists():
                counts["not in the sound folder"] += 1
                continue
            date, source = audio.recorded_date(path)
            if not date and file_dates:
                try:
                    date = _dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
                    source = FILE_DATE
                except OSError:
                    date = ""
            if not date:
                counts["no date in the file"] += 1
                continue
            if date == t.collected:
                counts["already the same"] += 1
                continue
            out.append(Change(e, i, t.collected, date, source))
    return out, {k: v for k, v in counts.items() if v}


def apply(doc, changes: list[Change]) -> None:
    """All the dates in one undo step."""
    copies: dict[int, Entry] = {}
    order: dict[int, Entry] = {}
    for c in changes:
        after = copies.setdefault(id(c.entry), c.entry.copy())
        order[id(c.entry)] = c.entry
        after.tokens[c.index].collected = c.new
    doc.apply_changes("Fill in recording dates", [(e, copies[k]) for k, e in order.items()], stamp=False)

