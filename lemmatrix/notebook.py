# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The notebook: one session a day, kept next to the database as <database>.notebook.

A session holds who was there (researchers, participants), where (locations), free
notes, open questions and to dos, and a record of the comments written that day. It is plain
Python, no Qt; the dialogue lives in ui/notebook_dialog.py.

Questions and To Dos (Josh, 21 October) are one kind of thing with two lists: the same fields,
dates, links and Resolve; Push to question and Push to To Do make them, and Convert moves one
from a list to the other, keeping its dates, link and status.

Comments (agreed 17 October 2026). Only the comment fields count. Every comment field
keeps the date it was last changed (Entry.changed / Token.changed), and a session
records the comments dated that day, with a link to their lemma or token:
- a comment changed again on the same day is written over in that day's record;
- a comment changed on a later day stays as it was in the old record, and the new
  version goes into the later day's;
- a lemma or token deleted on the day its comment was recorded leaves that day's
  record; deleted on a later day, it stays in the old record, whose link then says
  "Lemma no longer exists" / "Token no longer exists".
The tokens recorded that day aren't stored: they are found from the tokens' dates.

Comments on a text's lines (19 October) live in the TextGrid, which keeps no dates, so they
are recorded when they are written: in the day being worked on, linked to the text and line
(token_id "line:<start>"); written over that day if changed again the same day, and kept as
they were in earlier days. Adding a text records the comments already in its TextGrid in the
day the text was recorded.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .model import Database, Entry, Token, new_id, nfc, today, write_atomically, xml_safe
from . import hypotheses as _hy

FORMAT_VERSION = "4"                  # 2: <todo> beside <question>; 3: <hypotheses>, ids on questions (21 October);
                                      # 4: <snapshot> in the day (24 October)
SUFFIX = ".notebook"

QUESTION, TODO = "question", "todo"   # a notebook item's kind: its list, its element in the file
KINDS = (QUESTION, TODO)
# how each kind is named: (Title, Titles, a lowercase one, lowercase plural); "To Do", as Josh writes it
NAMES = {QUESTION: ("Question", "Questions", "question", "questions"),
         TODO: ("To Do", "To Dos", "To Do", "To Dos")}   # capitalised in sentences too


def other(kind: str) -> str:
    return TODO if kind == QUESTION else QUESTION


def name(kind: str, plural: bool = False, title: bool = True) -> str:
    """"Question", "To Dos", "to do"…"""
    return NAMES[kind][(0 if title else 2) + (1 if plural else 0)]


class NotebookError(Exception):
    pass


@dataclass
class Question:
    text: str
    created: str = ""                 # date asked
    edited: str = ""                  # date last edited
    resolved: str = ""                # date resolved; empty while open
    entry_id: str = ""                # pushed from a token's comment: a link to it (else no link)
    token_id: str = ""
    ref: str = ""                     # the lemma's reference then (the link falls back on it)
    about: str = ""                   # how the link reads: "D011 sheep · SG"
    kind: str = QUESTION              # QUESTION or TODO (a To Do is a Question in the other list)
    id: str = ""                      # given when first linked to a hypothesis (format 3), kept after
    pinned: bool = False              # kept at the top of its list (Josh, 22 October); resolving unpins

    def set_resolved(self, day: str):
        """Resolve it (a date) or open it again (""); resolving takes the pin off."""
        self.resolved = day
        if day:
            self.pinned = False

    @property
    def is_todo(self) -> bool:
        return self.kind == TODO

    @property
    def link(self) -> "NoteComment | None":
        """The token (or lemma) the question is about, as a link the notebook can follow."""
        if not self.entry_id and not self.ref:
            return None
        return NoteComment(self.text, self.entry_id, self.token_id, self.ref, self.about)

    @property
    def is_open(self) -> bool:
        return not self.resolved

    @property
    def status(self) -> str:
        return "Open" if self.is_open else "Resolved"

    @property
    def dated(self) -> str:
        """The created/edited date shown in lists: the later of the two."""
        return self.edited or self.created


LINE_PREFIX = "line:"


@dataclass
class NoteComment:
    """A comment as it was recorded, with a link to where it was written."""
    text: str
    entry_id: str
    token_id: str = ""                # empty for a lemma's comment
    ref: str = ""                     # the lemma's reference then (the link falls back on it)
    about: str = ""                   # "C001a father", "C001a father · PL + f1": how the link reads
    field: str = "Comment"

    @property
    def is_token(self) -> bool:
        return bool(self.token_id) and not self.is_line

    @property
    def is_line(self) -> bool:
        """A comment on a text's line (token_id "line:<start>")."""
        return self.token_id.startswith(LINE_PREFIX)

    @property
    def line_start(self) -> float | None:
        try:
            return float(self.token_id[len(LINE_PREFIX):]) if self.is_line else None
        except ValueError:
            return None

    def key(self) -> tuple:
        return (self.entry_id, self.token_id, self.field)


@dataclass
class Snapshot:
    """A snapshot (Josh, 24 October): the main window's complete setup when the camera was clicked,
    an item of the day like a question, in the Snapshots list (View → Snapshots, the notebook's
    Snapshots tab). There is no resolving: a snapshot is renamed, pinned, linked or deleted. A
    hypothesis that cites one keeps its own copy of the setup, so deleting it from the list never
    breaks the evidence."""
    id: str
    name: str
    view: dict
    taken: str = ""                   # the day taken (the session's day)
    time: str = ""                    # HH:MM, so the day's snapshots read in order
    about: str = ""                   # how the setup read when taken ("Lemma/Tag · Basic Imperatives · …")
    pinned: bool = False              # kept at the top of the list, as questions and To Dos


@dataclass
class Session:
    date: str                                            # YYYY-MM-DD
    researchers: list[str] = field(default_factory=list)  # codes
    participants: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)    # location keys (code, or name)
    notes: str = ""
    comments: list[NoteComment] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    todos: list[Question] = field(default_factory=list)  # To Dos: Questions of kind TODO
    texts: list[str] = field(default_factory=list)       # ids of the texts worked on that day (their lines)
    hypotheses: list[str] = field(default_factory=list)  # ids of the hypotheses worked on that day (Cogitate)
    snapshots: list[Snapshot] = field(default_factory=list)   # the snapshots taken that day (24 October)


def items(s: Session, kind: str) -> list[Question]:
    """A day's questions or to dos (the list itself)."""
    return s.todos if kind == TODO else s.questions


def convert(s: Session, q: Question) -> Question:
    """Convert to To Do / Convert to question: the item moves to the end of the day's other list,
    keeping its text, dates, link and status. Returns it."""
    lst = items(s, q.kind)
    i = next(i for i, x in enumerate(lst) if x is q)
    del lst[i]
    q.kind = other(q.kind)
    items(s, q.kind).append(q)
    return q


@dataclass
class Notebook:
    sessions: list[Session] = field(default_factory=list)
    hypotheses: list = field(default_factory=list)       # Cogitate (hypotheses.py), at the end of the file
    confidence: list = field(default_factory=lambda: _hy.default_confidence())   # its levels (Edit → Lists)
    next_number: int = 1                                 # the next hypothesis number (never reused)
    path: str = ""
    dirty: bool = False
    repaired: bool = False            # had characters XML can't hold, taken out on reading
    upgraded: bool = False            # older snapshots put into the list on reading (format 4)

    def session(self, date: str) -> Session | None:
        return next((s for s in self.sessions if s.date == date), None)

    def add_session(self, date: str) -> Session:
        """A new session for a day (not a future one); the day's session if there is one."""
        if (s := self.session(date)) is not None:
            return s
        if date > today():
            raise NotebookError("The notebook can't have notes for a day that hasn't come yet.")
        s = Session(date)
        self.sessions.append(s)
        self.sort()
        self.dirty = True
        return s

    def remove(self, session: Session):
        self.sessions.remove(session)
        self.dirty = True

    def sort(self):
        self.sessions.sort(key=lambda s: s.date)

    def newest_first(self) -> list[Session]:
        return sorted(self.sessions, key=lambda s: s.date, reverse=True)

    def all_questions(self) -> list[tuple[Session, Question]]:
        return self.all_items(QUESTION)

    def all_items(self, kind: str) -> list[tuple[Session, Question]]:
        """Every question (or To Do), newest day first, the pinned ones above the rest."""
        every = [(s, q) for s in self.newest_first() for q in items(s, kind)]
        return [x for x in every if x[1].pinned] + [x for x in every if not x[1].pinned]

    def all_snapshots(self) -> list[tuple[Session, Snapshot]]:
        """Every snapshot, the newest first (day, then time), the pinned ones above the rest."""
        every = [(s, x) for s in self.sessions for x in s.snapshots]
        order = {id(x): i for i, (_, x) in enumerate(every)}      # taken later in the same minute: first
        every.sort(key=lambda p: (p[0].date, p[1].time, order[id(p[1])]), reverse=True)
        return [x for x in every if x[1].pinned] + [x for x in every if not x[1].pinned]

    def snapshot(self, ident: str) -> tuple[Session, Snapshot] | None:
        for s in self.sessions:
            for x in s.snapshots:
                if x.id == ident:
                    return s, x
        return None

    def people(self) -> tuple[list[str], list[str]]:
        """Every researcher and participant code that appears, in order of first appearance."""
        r, p = [], []
        for s in self.sessions:
            r += [c for c in s.researchers if c not in r]
            p += [c for c in s.participants if c not in p]
        return r, p

    def rename(self, researchers: dict[str, str] = None, participants: dict[str, str] = None,
               locations: dict[str, str] = None):
        """Follow codes renamed in Edit → Lists."""
        for s in self.sessions:
            for attr, ren in (("researchers", researchers), ("participants", participants),
                              ("locations", locations)):
                if ren:
                    old = getattr(s, attr)
                    new = list(dict.fromkeys(ren.get(c, c) for c in old))
                    if new != old:
                        setattr(s, attr, new)
                        self.dirty = True


def path_for(db_path: str | os.PathLike) -> Path:
    """LXX-VXX.xml -> LXX-VXX.notebook, in the same folder."""
    return Path(db_path).with_suffix(SUFFIX)


# --------------------------------------------------------------------------
# Comments and recordings of a day
# --------------------------------------------------------------------------

def describe(db: Database, e: Entry, t: Token | None = None) -> str:
    """How a link reads (its preview in Cogitate, the notebook and the lists; Josh, 25 October):
    {reference} {form} {meaning} · {tags}. The form is the token's Phonemic, else its Phonetic
    (a lemma's: its Lemma field, else its citation token's); the meaning the token's translation,
    else the lemma's gloss, in quotes. "C001f mʊ̀ɔ̀ ‘mother’ · citation", "D009 jɔ̀dʌ́ʌm ‘your (sg)
    goat’ · 2SG.POSS", "U003 tʌ́dɔ̄tʌ̄ŋ … ‘We will eat lion meat today.’"; a lemma: "D009 dʌ́ʌm ‘goat’"."""
    from .model import is_utterance, meaning, token_form
    s = db.settings
    if is_utterance(e):
        t = t if t is not None else (e.tokens[0] if e.tokens else None)
        tr = s.token_field("translation")
        mean = t.get(tr.name, s.primary_gloss) if (t is not None and tr is not None) else ""
        form = token_form(db, t) or e.label
        return " ".join(x for x in (e.ref, form, meaning(mean)) if x)
    if t is None:
        cit = next((x for x in e.tokens if x.is_citation), None)
        form = db.lemma(e) or token_form(db, cit)
        return " ".join(x for x in (e.ref, form, meaning(db.gloss(e))) if x)
    tr = s.token_field("translation")
    mean = (t.get(tr.name, s.primary_gloss) if tr is not None else "") or db.gloss(e)
    base = " ".join(x for x in (e.ref, token_form(db, t), meaning(mean)) if x)
    from .matrix import chips, default_names
    names = [x for x in t.tags if x not in default_names(db)]
    label = " + ".join(chips(db, names)) or "citation"
    return f"{base} · {label}"


def about_now(db: Database, q) -> str:
    """What a question or to do is about, as its link reads now (the lemma or token may have
    changed since it was pushed); what was written then when it can't be found."""
    if not getattr(q, "entry_id", ""):
        return q.about
    e = db.item_by_id(q.entry_id)
    if e is None:
        return q.about
    t = next((x for x in e.tokens if x.id == q.token_id), None) if q.token_id else None
    if q.token_id and t is None:
        return q.about
    return describe(db, e, t)


def dated_comments(db: Database, date: str) -> list[NoteComment]:
    """The comments last changed on a day (not empty ones), lemmas in database order."""
    efields, tfields = db.comment_fields()
    out = []
    for e in db.items():                              # lemmas first, then utterances
        for name in efields:
            if e.changed.get(name) == date and e.get(name):
                out.append(NoteComment(e.get(name), e.id, "", e.ref, describe(db, e), name))
        for t in e.tokens:
            for name in tfields:
                if t.changed.get(name) == date and t.get(name):
                    out.append(NoteComment(t.get(name), e.id, t.id, e.ref, describe(db, e, t), name))
    return out


def find(db: Database, c: NoteComment) -> tuple[Entry, int | None] | None:
    """Where a recorded comment was written: (entry, token index or None), or None if it's gone."""
    e = db.item_by_id(c.entry_id) or (db.entry_by_ref(c.ref) or db.utterance_by_ref(c.ref) if c.ref else None)
    if e is None:
        return None
    if not c.token_id:
        return e, None
    for i, t in enumerate(e.tokens):
        if t.id == c.token_id:
            return e, i
    return None


def missing_text(c: NoteComment) -> str:
    if c.is_line:
        return "Text no longer exists"
    return "Token no longer exists" if c.is_token else "Lemma no longer exists"


def line_comment(db: Database, text, start: float, field: str, value: str, clock: str = "") -> NoteComment:
    from .model import nfc as _nfc
    title = db.text_title(text)
    about = f"{text.ref} {title}".strip() + (f" · {clock}" if clock else "")
    return NoteComment(_nfc(value), text.id, f"{LINE_PREFIX}{start:.4f}", text.ref, about, field)


def record_line_comment(nb: Notebook, db: Database, date: str, c: NoteComment,
                        researchers=(), participants=(), locations=()):
    """Record (or, emptied, remove) a line's comment in a day's session; the day gets a session
    if it has none (with these people and places). Returns (session, comments before, after)."""
    s = nb.session(date)
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    before = list(s.comments)
    out = [x for x in s.comments if x.key() != c.key()]
    if c.text:
        at = next((i for i, x in enumerate(s.comments) if x.key() == c.key()), len(out))
        out.insert(min(at, len(out)), c)
    s.comments = out
    nb.dirty = True
    return s, before, list(out)


def note_text_worked_on(nb: Notebook, db: Database, date: str, text, researchers=(), participants=(),
                        locations=()) -> bool:
    """A text whose lines were worked on (edited, clipped, pushed) on a day: it is listed in that
    day's Texts tab (Josh, 21 October: the day it is worked on, not the day it was added). The day
    gets a session if it has none. Returns True if the text wasn't listed for that day yet."""
    s = nb.session(date)
    if s is not None and text.id in s.texts:
        return False
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    s.texts.append(text.id)
    nb.dirty = True
    return True


def refresh_comments(db: Database, session: Session) -> bool:
    """Bring a session's record of comments up to date with the database. Returns True if it changed.

    For the comments still dated this day, the record shows their current text (an
    emptied one leaves, and so does an undone one). Ones changed since on a later day
    keep the text they had.
    Ones whose lemma or token is gone leave the record: it was deleted on this day,
    the day being worked on.
    """
    fresh = {c.key(): c for c in dated_comments(db, session.date)}
    out = []
    for c in session.comments:
        if c.is_line:                                 # a text line's comment: recorded when written
            out.append(c)
            continue
        if c.key() in fresh:
            out.append(fresh.pop(c.key()))
            continue
        where = find(db, c)
        if where is None:
            continue                                  # deleted on this day
        e, i = where
        obj = e if i is None else e.tokens[i]
        if obj.changed.get(c.field, "") > session.date:
            out.append(c)                             # changed since, on a later day: kept as it was
        # otherwise it was emptied on this day, or the change was undone
    out += fresh.values()
    if out != session.comments:
        session.comments = out
        return True
    return False


def empty_days(nb, db: Database, before: str) -> list[Session]:
    """Days before `before` with only people and places in them (Josh, 23 October: Write to notebook
    pressed, then nothing done that day): no notes, comments, questions, To Dos, texts or
    hypotheses, no snapshots, and no recordings or texts dated that day."""
    out = []
    for s in nb.sessions:
        if s.date >= before or s.notes.strip() or s.comments or s.questions or s.todos or s.texts \
                or s.hypotheses or s.snapshots:
            continue
        if recordings(db, s.date) or any(t.date == s.date for t in db.texts):
            continue
        out.append(s)
    return out


def recordings(db: Database, date: str) -> list[tuple[Entry, int]]:
    """Tokens (and utterances) with a recording collected on a day: (entry or utterance, token index)."""
    return [(e, i) for e in db.items() for i, t in enumerate(e.tokens) if t.collected == date and t.file]


def speakers(db: Database, date: str) -> list[str]:
    """Who spoke the tokens collected on a day, most tokens first."""
    count: dict[str, int] = {}
    for e in db.items():
        for t in e.tokens:
            if t.collected == date and t.speaker:
                count[t.speaker] = count.get(t.speaker, 0) + 1
    return sorted(count, key=lambda c: -count[c])


def write_session(nb: Notebook, db: Database, date: str, researchers, participants, locations) -> Session:
    """Write to notebook: the day's session gets these people and places and its comments.

    The notes, questions and to dos are never touched.
    """
    s = nb.add_session(date)
    for attr, value in (("researchers", researchers), ("participants", participants),
                        ("locations", locations)):
        value = list(dict.fromkeys(value))
        if getattr(s, attr) != value:
            setattr(s, attr, value)
            nb.dirty = True
    if refresh_comments(db, s):
        nb.dirty = True
    return s


def push_question(nb: Notebook, db: Database, date: str, text: str, e: Entry | None, t: Token | None,
                  researchers=(), participants=(), locations=(), kind: str = QUESTION) -> Question:
    """Push to question (or, with kind TODO, Push to To Do): an open item on a day, linked to a
    token (or lemma); with no entry, an item of its own (the + in View → Questions and View → To
    Do; Josh, 25 October).

    A day without notes yet gets them, with these people and places."""
    s = nb.session(date)
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    if e is None:
        q = Question(text, today(), kind=kind)
    else:
        q = Question(text, today(), entry_id=e.id, token_id=t.id if t is not None else "", ref=e.ref,
                     about=describe(db, e, t), kind=kind)
    items(s, kind).append(q)
    nb.dirty = True
    return q


# --------------------------------------------------------------------------
# History sections in the notes (Josh, 22 October)
# --------------------------------------------------------------------------
# The lines ɛλicit and Cogitate write go under a heading of their own at the end of the day's notes,
# ɛλicit's first: a blank line between the sections and between them and the notes typed there; a
# day with no notes yet starts with two blank lines, so typing on the top line still leaves a gap.
# Whether they are written is switched per database (the workspace; Settings → General and the
# notebook window): switching off never touches what is already written, and nothing is written
# afterwards for the days missed.

ELICIT_HISTORY, COGITATE_HISTORY, SNAPSHOT_HISTORY = "elicit", "cogitate", "snapshot"
HISTORY_ORDER = (ELICIT_HISTORY, COGITATE_HISTORY, SNAPSHOT_HISTORY)   # Snapshots' last (24 October)
HISTORY_HEADINGS = {ELICIT_HISTORY: "=====ELICIT HISTORY=====", COGITATE_HISTORY: "=====COGITATE HISTORY=====",
                    SNAPSHOT_HISTORY: "=====SNAPSHOT HISTORY====="}
HISTORY_SETTINGS = {ELICIT_HISTORY: "notebook/elicit_history", COGITATE_HISTORY: "notebook/cogitate_history",
                    SNAPSHOT_HISTORY: "notebook/snapshot_history"}


def _is_heading(row: str) -> bool:
    return row.strip() in HISTORY_HEADINGS.values()


def _section(rows: list[str], section: str) -> tuple[int, int] | None:
    """(heading row, the row after the section's last line), or None: a section runs from its
    heading to the next blank line or heading."""
    head = HISTORY_HEADINGS[section]
    h = next((i for i, r in enumerate(rows) if r.strip() == head), None)
    if h is None:
        return None
    e = h + 1
    while e < len(rows) and rows[e].strip() and not _is_heading(rows[e]):
        e += 1
    return h, e


def history_add(notes: str, section: str, line: str, replace_prefixes: tuple[str, ...] = ()) -> tuple[str, str]:
    """Notes with a line written into a history section (made if need be); with replace_prefixes,
    a line of the section starting with one of them is replaced instead (an edit's line, once a
    day). Returns (the new notes, the line replaced or "")."""
    rows = notes.split("\n") if notes else []
    found = _section(rows, section)
    if found is not None:
        h, e = found
        if replace_prefixes:
            for i in range(e - 1, h, -1):
                if any(rows[i].startswith(p) for p in replace_prefixes):
                    old, rows[i] = rows[i], line
                    return "\n".join(rows), old
        rows.insert(e, line)
        return "\n".join(rows), ""
    later = [_section(rows, x) for x in HISTORY_ORDER[HISTORY_ORDER.index(section) + 1:]]
    later = [f[0] for f in later if f is not None]
    if later:                                      # ɛλicit's goes before Cogitate's
        at = min(later)
        rows[at:at] = [HISTORY_HEADINGS[section], line, ""]
        return "\n".join(rows), ""
    while rows and not rows[-1].strip():
        rows.pop()
    rows += (["", HISTORY_HEADINGS[section], line] if rows else ["", "", HISTORY_HEADINGS[section], line])
    return "\n".join(rows), ""


def history_remove(notes: str, section: str, line: str, old: str = "") -> str:
    """Undo a history_add: the line taken out (or the line it replaced put back); a section left
    with no lines goes, with the blank line it brought."""
    rows = notes.split("\n") if notes else []
    found = _section(rows, section)
    if found is None:
        return notes
    h, e = found
    for i in range(e - 1, h, -1):
        if rows[i] == line:
            if old:
                rows[i] = old
                return "\n".join(rows)
            del rows[i]
            e -= 1
            break
    else:
        return notes
    if e == h + 1:                                 # nothing left under the heading
        del rows[h]
        if h < len(rows) and not rows[h].strip():
            del rows[h]
        elif h > 0 and not rows[h - 1].strip():
            del rows[h - 1]
    if not any(r.strip() for r in rows):
        return ""
    return "\n".join(rows)


def add_history_line(nb: Notebook, date: str, section: str, line: str) -> Session:
    """A line in a day's history section (ɛλicit's); the day gets a session if it has none."""
    s = nb.add_session(date)
    s.notes, _ = history_add(s.notes, section, line)
    nb.dirty = True
    return s


def push_line_question(nb: Notebook, db: Database, date: str, question: str, text, start: float,
                       clock: str = "", researchers=(), participants=(), locations=(),
                       kind: str = QUESTION) -> Question:
    """Push to question (or To Do) from a text's line (its Comment): an open item linked to the line."""
    s = nb.session(date)
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    link = line_comment(db, text, start, "", question, clock)
    q = Question(link.text, today(), entry_id=link.entry_id, token_id=link.token_id, ref=link.ref,
                 about=link.about, kind=kind)
    items(s, kind).append(q)
    nb.dirty = True
    return q


# --------------------------------------------------------------------------
# Snapshots (Josh, 24 October)
# --------------------------------------------------------------------------

HISTORY_LABELS = {ELICIT_HISTORY: "Write ELICIT HISTORY", COGITATE_HISTORY: "Write COGITATE HISTORY",
                  SNAPSHOT_HISTORY: "Write SNAPSHOT HISTORY"}
HISTORY_WHAT = {ELICIT_HISTORY: "ɛλicit request made or received", COGITATE_HISTORY: "change to a hypothesis",
                SNAPSHOT_HISTORY: "snapshot taken"}


def snapshot_line(snap: Snapshot) -> str:
    """The line a snapshot taken writes under =====SNAPSHOT HISTORY=====."""
    return f"Snapshot taken{(' ' + snap.time) if snap.time else ''}: {snap.name}"


def snapshot_state(nb: Notebook) -> list:
    """Every day's snapshots, copied (an undo step's before and after), kept with the day itself
    rather than its date: a day's date can change (or the day be deleted) outside the undo steps,
    and undoing by date then wiped that day's snapshots (the audit, 25 October)."""
    return [(s, copy.deepcopy(s.snapshots)) for s in nb.sessions if s.snapshots]


def day_state(state: list, s, sessions) -> list:
    """A day's part of an undo state kept by day ([(session, value)]): the day itself, else (a day
    undo took out and redo made again) the one of that date no longer in the notebook."""
    hit = next((v for day, v in state if day is s), None)
    if hit is None:
        live = {id(x) for x in sessions}
        hit = next((v for day, v in state if id(day) not in live and day.date == s.date), [])
    return hit


def set_snapshot_state(nb: Notebook, state: list):
    for s in nb.sessions:
        s.snapshots = copy.deepcopy(day_state(state, s, nb.sessions))
    nb.dirty = True


def take_snapshot(nb: Notebook, date: str, view: dict, about: str, clock: str = "") -> tuple[Session, Snapshot]:
    """A new snapshot in the day's list, named as the setup reads (renamed later if wanted)."""
    s = nb.add_session(date)
    snap = Snapshot(new_id(), about or "Snapshot", copy.deepcopy(view), date, clock, about)
    s.snapshots.append(snap)
    nb.dirty = True
    return s, snap


def delete_snapshot(nb: Notebook, snap: Snapshot) -> bool:
    """Out of the list (and its day); hypotheses citing it keep their copy of the setup."""
    for s in nb.sessions:
        if snap in s.snapshots:
            s.snapshots.remove(snap)
            nb.dirty = True
            return True
    return False


def _list_old_snapshots(nb: Notebook) -> int:
    """Notebooks before format 4 kept a snapshot only inside its hypothesis link: each becomes an
    item of the day it was linked (named as it read), and the link points at it. Returns how many."""
    n = 0
    for h in nb.hypotheses:
        for ln in h.links:
            if ln.kind != _hy.SNAPSHOT or ln.target or ln.view is None:
                continue
            day = ln.date or ln.linked or h.made or today()
            day = min(day, today())
            s = nb.session(day) or nb.add_session(day)
            snap = Snapshot(new_id(), ln.about or "Snapshot", copy.deepcopy(ln.view), day, "", ln.about)
            s.snapshots.append(snap)
            ln.target = snap.id
            n += 1
    return n


def matches(s: Session, db: Database | None, text: str, nb: "Notebook | None" = None) -> bool:
    """Search: the date, notes, people, places, comments, questions and to dos, and (given the
    notebook) the hypotheses worked on that day."""
    text = text.strip().lower()
    if not text:
        return True
    md = db.metadata if db else None
    parts = [s.date, s.notes, *s.researchers, *s.participants]
    for code in s.researchers + s.participants:
        p = md and (md.researcher(code) or md.participant(code))
        if p:
            parts.append(p.name)
    for key in s.locations:
        parts.append(md.location_path(key) if md else key)
    parts += [c.text for c in s.comments] + [c.about for c in s.comments]
    parts += [q.text for q in s.questions + s.todos]
    parts += [x.name for x in s.snapshots] + [x.about for x in s.snapshots]
    if any(text in (x or "").lower() for x in parts):
        return True
    if nb is not None and s.hypotheses:          # the hypotheses worked on that day (Cogitate)
        return any(_hy.matches(h, text) for h in nb.hypotheses if h.id in s.hypotheses)
    return False


def summary(s: Session) -> str:
    """A line to recognise a day by: its first line of notes that isn't a heading."""
    for line in s.notes.splitlines():
        line = line.strip(" -•\t")
        if line and not line.startswith("="):
            return line
    return ""


def long_date(date: str) -> str:
    """2026-10-17 -> 2026-OCT-17, as on the notebook's page."""
    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        return date
    return f"{d.year}-{d.strftime('%b').upper()}-{d.day:02d}"


def weekday(date: str) -> str:
    try:
        return _dt.date.fromisoformat(date).strftime("%A")
    except ValueError:
        return ""


# --------------------------------------------------------------------------
# File
# --------------------------------------------------------------------------

def _text(el) -> str:
    return nfc(el.text or "") if el is not None else ""


def _codes(text: str | None) -> list[str]:
    return [nfc(c.strip()) for c in (text or "").split(",") if c.strip()]


def load(path: str | os.PathLike) -> Notebook:
    """Read a notebook; a missing file is an empty notebook."""
    path = Path(path)
    nb = Notebook(path=str(path))
    if not path.exists():
        return nb
    try:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:                 # invisible characters a paste brought in: take them out
            root = ET.fromstring(xml_safe(path.read_text(encoding="utf-8", errors="replace"), "\n"))
            nb.repaired = True
    except ET.ParseError as exc:
        raise NotebookError(f"The notebook {path.name} isn't readable XML: {exc}") from exc
    if root.tag != "notebook":
        raise NotebookError(f"{path.name} isn't a Lemmatrix notebook.")
    for el in root.findall("session"):
        s = Session(el.get("date", ""))
        s.researchers = _codes(el.get("researchers"))
        s.participants = _codes(el.get("participants"))
        s.locations = [nfc(x.get("key", "")) for x in el.findall("location")]
        s.notes = _text(el.find("notes")).strip("\n")
        for c in el.findall("comment"):
            s.comments.append(NoteComment(_text(c), c.get("entry", ""), c.get("token", ""),
                                          nfc(c.get("ref", "")), nfc(c.get("about", "")),
                                          c.get("field", "Comment")))
        for kind in KINDS:
            for q in el.findall(kind):
                items(s, kind).append(Question(_text(q), q.get("created", ""), q.get("edited", ""),
                                               q.get("resolved", ""), q.get("entry", ""), q.get("token", ""),
                                               nfc(q.get("ref", "")), nfc(q.get("about", "")), kind,
                                               q.get("id", ""), q.get("pinned") == "yes"))
        s.texts = [x.get("id", "") for x in el.findall("text") if x.get("id")]
        s.hypotheses = [x.get("id", "") for x in el.findall("hypothesis") if x.get("id")]
        for x in el.findall("snapshot"):
            ve = x.find("view")
            try:
                view = json.loads(ve.text) if ve is not None and (ve.text or "").strip() else {}
            except ValueError:
                view = {}
            s.snapshots.append(Snapshot(x.get("id") or new_id(), nfc(x.get("name", "")) or "Snapshot", view,
                                        x.get("taken", s.date), x.get("time", ""), nfc(x.get("about", "")),
                                        x.get("pinned") == "yes"))
        nb.sessions.append(s)
    _hy.read_xml(nb, root)
    nb.sort()
    nb.upgraded = _list_old_snapshots(nb) > 0     # older snapshots into the list (format 4)
    nb.dirty = nb.repaired or nb.upgraded  # so saving writes the repaired (or upgraded) file
    return nb


def to_string(nb: Notebook, database_name: str = "") -> str:
    root = ET.Element("notebook", format=FORMAT_VERSION)
    if database_name:
        root.set("database", database_name)
    for s in sorted(nb.sessions, key=lambda s: s.date):
        a = {"date": s.date}
        if s.researchers:
            a["researchers"] = ", ".join(s.researchers)
        if s.participants:
            a["participants"] = ", ".join(s.participants)
        el = ET.SubElement(root, "session", a)
        for key in s.locations:
            ET.SubElement(el, "location", key=key)
        if s.notes:
            ET.SubElement(el, "notes").text = s.notes
        for c in s.comments:
            ca = {"entry": c.entry_id}
            if c.token_id:
                ca["token"] = c.token_id
            ca.update({"ref": c.ref, "about": c.about, "field": c.field})
            ET.SubElement(el, "comment", ca).text = c.text
        for q in s.questions + s.todos:
            qa = {"id": q.id} if q.id else {}
            qa["created"] = q.created
            if q.edited:
                qa["edited"] = q.edited
            if q.resolved:
                qa["resolved"] = q.resolved
            if q.pinned:
                qa["pinned"] = "yes"
            for key, val in (("entry", q.entry_id), ("token", q.token_id), ("ref", q.ref), ("about", q.about)):
                if val:
                    qa[key] = val
            ET.SubElement(el, q.kind, qa).text = q.text
        for tid in s.texts:                       # the texts worked on that day
            ET.SubElement(el, "text", id=tid)
        for hid in s.hypotheses:                  # the hypotheses worked on that day (Cogitate)
            ET.SubElement(el, "hypothesis", id=hid)
        for x in s.snapshots:                     # the snapshots taken that day (format 4)
            xa = {"id": x.id, "name": x.name, "taken": x.taken or s.date}
            if x.time:
                xa["time"] = x.time
            if x.about:
                xa["about"] = x.about
            if x.pinned:
                xa["pinned"] = "yes"
            se = ET.SubElement(el, "snapshot", xa)
            ET.SubElement(se, "view").text = json.dumps(x.view, ensure_ascii=False, sort_keys=True)
    _hy.write_xml(nb, root)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def save(nb: Notebook, path: str | os.PathLike | None = None, database_name: str = ""):
    """Write the notebook atomically (via a .saving file)."""
    path = str(path or nb.path)
    if not path:
        raise ValueError("No file name given")
    text = xml_safe(to_string(nb, database_name), line_break="\n")   # a paste from Word, say
    tmp = write_atomically(path, text)
    os.replace(tmp, path)
    nb.path = path
    nb.dirty = False
