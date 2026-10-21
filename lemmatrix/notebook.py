# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The notebook: one session a day, kept next to the database as <database>.notebook.

A session holds who was there (researchers, participants), where (locations), free
notes, open questions, and a record of the comments written that day. It is plain
Python, no Qt; the dialogue lives in ui/notebook_dialog.py.

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

import datetime as _dt
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .model import Database, Entry, Token, nfc, today, write_atomically, xml_safe

FORMAT_VERSION = "1"
SUFFIX = ".notebook"


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
class Session:
    date: str                                            # YYYY-MM-DD
    researchers: list[str] = field(default_factory=list)  # codes
    participants: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)    # location keys (code, or name)
    notes: str = ""
    comments: list[NoteComment] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)


@dataclass
class Notebook:
    sessions: list[Session] = field(default_factory=list)
    path: str = ""
    dirty: bool = False
    repaired: bool = False            # had characters XML can't hold, taken out on reading

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
        return [(s, q) for s in self.newest_first() for q in s.questions]

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
    """How a link reads: "C001a father", or "C001a father · PL + f1" for a token; an utterance's
    is its reference and label: "W001 hare ran (utterance)"."""
    from .model import is_utterance
    if is_utterance(e):
        return " ".join(x for x in (e.ref, e.label) if x) + " (utterance)"
    base = " ".join(x for x in (e.ref, db.gloss(e)) if x)
    if t is None:
        return base
    from .matrix import chips, default_names
    names = [x for x in t.tags if x not in default_names(db)]
    label = " + ".join(chips(db, names)) or "citation"
    return f"{base} · {label}"


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

    The notes and questions are never touched.
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


def push_question(nb: Notebook, db: Database, date: str, text: str, e: Entry, t: Token | None,
                  researchers=(), participants=(), locations=()) -> Question:
    """Push to question: an open question on a day, linked to a token (or lemma).

    A day without notes yet gets them, with these people and places."""
    s = nb.session(date)
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    q = Question(text, today(), entry_id=e.id, token_id=t.id if t is not None else "", ref=e.ref,
                 about=describe(db, e, t))
    s.questions.append(q)
    nb.dirty = True
    return q


def add_note_line(nb: Notebook, date: str, line: str) -> Session:
    """A line at the end of a day's notes (after whatever is written); the day gets a session if it
    has none (no people or places: those are the panel's to give)."""
    s = nb.add_session(date)
    s.notes = (s.notes.rstrip("\n") + "\n" if s.notes.strip() else "") + line
    nb.dirty = True
    return s


def push_line_question(nb: Notebook, db: Database, date: str, question: str, text, start: float,
                       clock: str = "", researchers=(), participants=(), locations=()) -> Question:
    """Push to question from a text's line (its Comment): an open question linked to the line."""
    s = nb.session(date)
    if s is None:
        s = write_session(nb, db, date, researchers, participants, locations)
    link = line_comment(db, text, start, "", question, clock)
    q = Question(link.text, today(), entry_id=link.entry_id, token_id=link.token_id, ref=link.ref,
                 about=link.about)
    s.questions.append(q)
    nb.dirty = True
    return q


def matches(s: Session, db: Database | None, text: str) -> bool:
    """Search: the date, notes, people, places, comments and questions."""
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
    parts += [q.text for q in s.questions]
    return any(text in (x or "").lower() for x in parts)


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
        for q in el.findall("question"):
            s.questions.append(Question(_text(q), q.get("created", ""), q.get("edited", ""),
                                        q.get("resolved", ""), q.get("entry", ""), q.get("token", ""),
                                        nfc(q.get("ref", "")), nfc(q.get("about", ""))))
        nb.sessions.append(s)
    nb.sort()
    nb.dirty = nb.repaired                # so saving writes the repaired file
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
        for q in s.questions:
            qa = {"created": q.created}
            if q.edited:
                qa["edited"] = q.edited
            if q.resolved:
                qa["resolved"] = q.resolved
            for key, val in (("entry", q.entry_id), ("token", q.token_id), ("ref", q.ref), ("about", q.about)):
                if val:
                    qa[key] = val
            ET.SubElement(el, "question", qa).text = q.text
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
