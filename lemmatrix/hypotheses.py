# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Cogitate: hypotheses, kept at the end of the notebook (IDEAS.md idea 35, designed with Josh on
21 October 2026). Plain Python, no Qt; the window is ui/cogitate.py.

A hypothesis has a number (H1, H2…: never reused, like references), a summary (usually a
one-sentence claim), a careful formulation, a confidence (from an editable list: initial,
developing, proven, dubious by default) and its links. Things are linked to a hypothesis as
Evidence, Counterevidence or Relevant (Josh's word for "kept with it, no direction"), each with an
optional note and the date linked. The links are stored with the hypothesis, never on the item, and
point at ids, so they survive reference and tag changes:

- a token or an utterance (its entry's and token's ids);
- a text's line (the text's id and the line's start time, as bookmarks are: a boundary moved in
  Praat finds the nearest line);
- a snapshot: an item of the Snapshots list (notebook.Snapshot, by its id, 24 October), with the
  complete setup of the main window also copied into the link, so deleting the snapshot from the
  list never breaks the evidence: the link still restores that view;
- a question or a To Do (its id; it may have been converted since), a comment (the notebook's
  record of it, that day's version, copied, so later edits don't change what was cited), and
  another hypothesis;
- a whiteboard drawing (22 October, idea 45): its file in the main folder's Whiteboard folder, by
  its place relative to the main folder; a moved or deleted drawing is a broken link.

A hypothesis joins a day's session when it is made or edited that day (linking and unlinking count),
and the day's notes get a line for what happened (Josh: "automatically into the notebook entry's
general text"): one per change for made, confidence changed, linked, unlinked and deleted; summary
and formulation edits once per hypothesis per day, with the new summary.

Every change goes through a Journal, which remembers the lines written into the notes, so undoing
it takes them out again without touching anything else written there (ui/document.py's
HypothesisCommand keeps the before and after of the hypotheses themselves).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .model import Database, is_utterance, new_id, nfc, today

DEFAULT_CONFIDENCE = ["initial", "developing", "proven", "dubious"]

EVIDENCE, COUNTER, RELEVANT = "evidence", "counterevidence", "relevant"
MARKS = (EVIDENCE, COUNTER, RELEVANT)
MARK_NAMES = {EVIDENCE: "Evidence", COUNTER: "Counterevidence", RELEVANT: "Relevant"}

TOKEN, UTTERANCE, LINE, SNAPSHOT, QUESTION, COMMENT, HYPOTHESIS, DRAWING = (
    "token", "utterance", "line", "snapshot", "question", "comment", "hypothesis", "drawing")
KINDS = (TOKEN, UTTERANCE, LINE, SNAPSHOT, QUESTION, COMMENT, HYPOTHESIS, DRAWING)
KIND_NAMES = {TOKEN: "Token", UTTERANCE: "Utterance", LINE: "Text line", SNAPSHOT: "Snapshot",
              QUESTION: "Question", COMMENT: "Comment", HYPOTHESIS: "Hypothesis", DRAWING: "Drawing"}
KIND_PLURALS = {TOKEN: "Tokens", UTTERANCE: "Utterances", LINE: "Text lines", SNAPSHOT: "Snapshots",
                QUESTION: "Questions and To Dos", COMMENT: "Comments", HYPOTHESIS: "Hypotheses",
                DRAWING: "Drawings"}


@dataclass
class Link:
    kind: str
    mark: str = RELEVANT
    note: str = ""
    linked: str = ""                  # the date it was linked
    entry: str = ""                   # the lemma's or utterance's id; a text's id (a line); a comment's entry
    token: str = ""                   # the token's id; a comment's token (or "line:<start>")
    target: str = ""                  # a question's or a hypothesis's id; a drawing's file (Whiteboard/…)
    start: float | None = None        # a text's line: its start time
    about: str = ""                   # how it read when linked ("D001 goat · PL"), the fallback label
    text: str = ""                    # a copy: the line's text, the question's, the comment as it was
    date: str = ""                    # a comment's or question's day
    field: str = ""                   # a comment's field
    view: dict | None = None          # a snapshot's setup

    def same_item(self, other: "Link") -> bool:
        """The same thing linked (a snapshot of the list by its id; an older one never is)."""
        if self.kind != other.kind:
            return False
        if self.kind == SNAPSHOT:
            return bool(self.target) and self.target == other.target
        if self.kind == LINE:
            return self.entry == other.entry and self.start is not None and other.start is not None \
                and abs(self.start - other.start) < 0.005
        if self.kind == COMMENT:
            return (self.date, self.entry, self.token, self.field) == (other.date, other.entry, other.token, other.field)
        return (self.entry, self.token, self.target) == (other.entry, other.token, other.target)


@dataclass
class Hypothesis:
    id: str
    number: int
    summary: str = ""
    formulation: str = ""
    confidence: str = ""
    made: str = ""                    # the day made (the session's day)
    edited: str = ""                  # the day last edited (links included)
    links: list[Link] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"H{self.number}"

    def title(self, n: int = 60) -> str:
        """"H3 Tone spreads rightward" (shortened)."""
        s = " ".join(self.summary.split())
        if len(s) > n:
            s = s[:n - 1].rstrip() + "…"
        return f"{self.label} {s}".rstrip()

    def count(self, mark: str) -> int:
        return sum(1 for ln in self.links if ln.mark == mark)


# --------------------------------------------------------------------------
# The notes: lines written for what happened, and the journal that remembers them
# --------------------------------------------------------------------------

class Journal:
    """The notebook changes of one hypothesis change (one undo step): lines written into days'
    notes, and the days that list a hypothesis or were made for it."""

    def __init__(self, nb, history: bool = True):
        self.nb = nb
        self.history = history                         # write the lines (COGITATE HISTORY), or not
        self.lines: list[tuple[str, str, str]] = []   # (date, line replaced or "", line written)
        self.made_days: list[str] = []                 # sessions made by this change

    def _session(self, date: str):
        s = self.nb.session(date)
        if s is None:
            s = self.nb.add_session(date)
            self.made_days.append(date)
        return s

    def touch(self, date: str, h: Hypothesis):
        """The hypothesis was worked on that day: the day lists it (the notebook's Hypotheses tab)."""
        s = self._session(date)
        if h.id not in s.hypotheses:
            s.hypotheses.append(h.id)
        self.nb.dirty = True

    def write(self, date: str, line: str, replace_prefixes: tuple[str, ...] = ()):
        """A line in the day's =====COGITATE HISTORY===== section of the notes; or, when a line of it
        starts with one of the prefixes, that line is replaced (an edit's line, once a day). Nothing
        is written while the history is switched off."""
        from .notebook import COGITATE_HISTORY, history_add
        if not self.history:
            return
        s = self._session(date)
        s.notes, old = history_add(s.notes, COGITATE_HISTORY, line, replace_prefixes)
        self.lines.append((date, old, line))
        self.nb.dirty = True

    # ---- undo and redo (by the document's command) -----------------------------------
    def undo_lines(self):
        from .notebook import COGITATE_HISTORY, history_remove
        for date, old, new in reversed(self.lines):
            s = self.nb.session(date)
            if s is not None:
                s.notes = history_remove(s.notes, COGITATE_HISTORY, new, old)
        for date in self.made_days:              # a day made for this, empty again: gone again
            s = self.nb.session(date)
            if s is not None and _empty(s):
                self.nb.sessions.remove(s)

    def redo_lines(self):
        from .notebook import COGITATE_HISTORY, history_add
        for date, old, new in self.lines:
            s = self.nb.add_session(date)
            s.notes, _ = history_add(s.notes, COGITATE_HISTORY, new, (old,) if old else ())


def _empty(s) -> bool:
    return not (s.notes.strip() or s.comments or s.questions or s.todos or s.texts or s.hypotheses
                or getattr(s, "snapshots", None) or s.researchers or s.participants or s.locations)


def _short(text: str, n: int = 60) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _mark_words(mark: str) -> str:
    return "linked as relevant" if mark == RELEVANT else f"{mark} linked"


# --------------------------------------------------------------------------
# Making and changing hypotheses
# --------------------------------------------------------------------------

def by_id(nb, ident: str) -> Hypothesis | None:
    return next((h for h in nb.hypotheses if h.id == ident), None)


def by_number(nb, n: int) -> Hypothesis | None:
    return next((h for h in nb.hypotheses if h.number == n), None)


def confidence_list(nb) -> list[str]:
    """The confidence levels, in order (the list may be nested in Edit → Lists: flattened here)."""
    out = []
    for top in nb.confidence:
        for it in top.walk():
            if it.name not in out:
                out.append(it.name)
    return out


def make(nb, j: Journal, date: str, summary: str = "", formulation: str = "", confidence: str = "",
         links=(), db: Database | None = None) -> Hypothesis:
    """Make a new hypothesis (the next number; numbers are never reused)."""
    levels = confidence_list(nb)
    number = max([nb.next_number] + [h.number + 1 for h in nb.hypotheses])
    nb.next_number = number + 1
    h = Hypothesis(new_id(), number, nfc(summary.strip()), nfc(formulation.strip()),
                   confidence or (levels[0] if levels else ""), date, date)
    nb.hypotheses.append(h)
    j.touch(date, h)
    j.write(date, f"{h.label} made" + (f": {_short(h.summary)}" if h.summary else ""))
    for ln in links:
        add_link(nb, j, date, h, ln, db, log=True)
    return h


def edit(nb, j: Journal, date: str, h: Hypothesis, summary: str | None = None, formulation: str | None = None,
         confidence: str | None = None) -> bool:
    """Change the summary, formulation or confidence. Returns True if anything changed."""
    changed = False
    text_changed = False
    if summary is not None and nfc(summary.strip()) != h.summary:
        h.summary = nfc(summary.strip())
        changed = text_changed = True
    if formulation is not None and nfc(formulation.strip()) != h.formulation:
        h.formulation = nfc(formulation.strip())
        changed = text_changed = True
    if confidence is not None and confidence != h.confidence:
        old = h.confidence
        h.confidence = confidence
        changed = True
        j.write(date, f"{h.title()}: confidence {old or '(none)'} → {confidence or '(none)'}")
    if not changed:
        return False
    h.edited = date
    j.touch(date, h)
    if text_changed:                              # once a day, with the new summary
        if h.made == date:
            j.write(date, f"{h.label} made" + (f": {_short(h.summary)}" if h.summary else ""),
                    (f"{h.label} made: ", f"{h.label} made"))
        else:
            j.write(date, f"{h.label} edited: {_short(h.summary)}", (f"{h.label} edited: ",))
    return True


def delete(nb, j: Journal, date: str, h: Hypothesis):
    """Delete a hypothesis (its number isn't given out again). Links to it from other hypotheses
    stay, marked as no longer existing."""
    nb.hypotheses.remove(h)
    nb.next_number = max(nb.next_number, h.number + 1)
    j.write(date, f"{h.label} deleted: {_short(h.summary)}")
    nb.dirty = True


def add_link(nb, j: Journal, date: str, h: Hypothesis, link: Link, db: Database | None = None,
             log: bool = True) -> Link:
    """Link something to a hypothesis. The same item linked again changes the existing link's mark
    and note instead of adding a second one. Returns the link."""
    link.linked = link.linked or date
    have = next((x for x in h.links if x.same_item(link)), None)
    if have is not None:
        if (have.mark, have.note) == (link.mark, link.note or have.note):
            return have
        have.mark = link.mark
        if link.note:
            have.note = link.note
        link = have
        words = f"now {link.mark}"
    else:
        h.links.append(link)
        words = _mark_words(link.mark)
    h.edited = date
    j.touch(date, h)
    if log:
        what = label(db, nb, link) if db is not None else (link.about or KIND_NAMES[link.kind])
        j.write(date, f"{h.title()}: {words}, {_short(what, 50)}")
    return link


def unlink(nb, j: Journal, date: str, h: Hypothesis, link: Link, db: Database | None = None):
    h.links = [x for x in h.links if x is not link]
    h.edited = date
    j.touch(date, h)
    what = label(db, nb, link) if db is not None else (link.about or KIND_NAMES[link.kind])
    j.write(date, f"{h.title()}: unlinked, {_short(what, 50)}")


def set_link(nb, j: Journal, date: str, h: Hypothesis, link: Link, mark: str | None = None,
             note: str | None = None, db: Database | None = None) -> bool:
    """Change a link's mark (logged) or note (not logged: it is the link's own text)."""
    changed = False
    if note is not None and nfc(note.strip()) != link.note:
        link.note = nfc(note.strip())
        changed = True
    if mark is not None and mark != link.mark:
        link.mark = mark
        changed = True
        what = label(db, nb, link) if db is not None else (link.about or KIND_NAMES[link.kind])
        j.write(date, f"{h.title()}: now {mark}, {_short(what, 50)}")
    if changed:
        h.edited = date
        j.touch(date, h)
    return changed


def rename_confidence(nb, renames: dict[str, str]):
    """Follow confidence levels renamed in Edit → Lists."""
    for h in nb.hypotheses:
        if h.confidence in renames:
            h.confidence = renames[h.confidence]
            nb.dirty = True


# --------------------------------------------------------------------------
# Links: making them, finding what they point at, how they read
# --------------------------------------------------------------------------

def token_link(db: Database, e, t, mark: str = RELEVANT, note: str = "") -> Link:
    """A link to a token, or (an utterance's only token) to the utterance."""
    from .notebook import describe
    if is_utterance(e):
        return Link(UTTERANCE, mark, note, entry=e.id, token=t.id if t is not None else "",
                    about=describe(db, e))
    return Link(TOKEN, mark, note, entry=e.id, token=t.id, about=describe(db, e, t))


def line_link(db: Database, text, start: float, line_text: str = "", clock: str = "",
              mark: str = RELEVANT, note: str = "") -> Link:
    about = f"{text.ref} {db.text_title(text)}".strip() + (f" · {clock}" if clock else "")
    return Link(LINE, mark, note, entry=text.id, start=round(float(start), 4), about=about,
                text=nfc(line_text or ""))


def snapshot_link(view: dict, about: str, mark: str = RELEVANT, note: str = "", target: str = "",
                  date: str = "") -> Link:
    """A snapshot: its id in the list (target) and its own copy of the setup."""
    return Link(SNAPSHOT, mark, note, target=target, about=about, view=copy.deepcopy(view), date=date or today())


def snapshot_listed(nb, link: Link):
    """The list's snapshot a link points at, or None (deleted from the list, or an older link)."""
    if link.kind != SNAPSHOT or not link.target or nb is None or not hasattr(nb, "snapshot"):
        return None
    hit = nb.snapshot(link.target)
    return hit[1] if hit is not None else None


SNAPSHOT_DELETED = "Snapshot deleted from the list"


def question_link(session, q, mark: str = RELEVANT, note: str = "") -> Link:
    if not q.id:
        q.id = new_id()
    return Link(QUESTION, mark, note, target=q.id, text=q.text, date=session.date,
                about=f"{'To Do' if q.is_todo else 'Question'} of {session.date}")


def comment_link(session, c, mark: str = RELEVANT, note: str = "") -> Link:
    return Link(COMMENT, mark, note, entry=c.entry_id, token=c.token_id, about=c.about or c.ref, text=c.text,
                date=session.date, field=c.field)


def hypothesis_link(h: Hypothesis, mark: str = RELEVANT, note: str = "") -> Link:
    return Link(HYPOTHESIS, mark, note, target=h.id, about=h.title())


def drawing_link(rel_path: str, mark: str = RELEVANT, note: str = "") -> Link:
    """A whiteboard drawing, by its place relative to the main folder (Whiteboard/….png)."""
    from pathlib import PurePosixPath
    return Link(DRAWING, mark, note, target=rel_path, about=PurePosixPath(rel_path).name, date=today())


def find_question(nb, ident: str):
    for s in nb.sessions:
        for q in s.questions + s.todos:
            if q.id == ident:
                return s, q
    return None


def find(db: Database, nb, link: Link):
    """What a link points at now, or None if it is gone:
    token: (entry, index); utterance: the utterance; line: the text; question: (session, question);
    comment: what its comment was written on ((entry, index or None), or the text); hypothesis: it;
    snapshot: its setup; drawing: its file (a Path)."""
    k = link.kind
    if k == SNAPSHOT:
        return link.view
    if k == DRAWING:
        from . import whiteboard
        return whiteboard.resolve(db.path if db is not None else "", link.target)
    if k == HYPOTHESIS:
        return by_id(nb, link.target)
    if k == QUESTION:
        return find_question(nb, link.target)
    if db is None:
        return None
    if k == LINE:
        return db.text_by_id(link.entry)
    if k == UTTERANCE:
        u = db.item_by_id(link.entry)
        return u if u is not None and is_utterance(u) and u in db.utterances else None
    if k == TOKEN:
        e = db.item_by_id(link.entry)
        if e is None or is_utterance(e):
            return None
        for i, t in enumerate(e.tokens):
            if t.id == link.token:
                return e, i
        return None
    if k == COMMENT:
        from .notebook import LINE_PREFIX, NoteComment, find as nb_find
        if link.token.startswith(LINE_PREFIX):
            return db.text_by_id(link.entry)
        return nb_find(db, NoteComment(link.text, link.entry, link.token, "", link.about, link.field))
    return None


def gone_text(link: Link) -> str:
    from .notebook import LINE_PREFIX
    k = link.kind
    if k == COMMENT:
        if link.token.startswith(LINE_PREFIX):
            return "Text no longer exists"
        return "Token no longer exists" if link.token else "Lemma no longer exists"
    return {TOKEN: "Token no longer exists", UTTERANCE: "Utterance no longer exists",
            LINE: "Text no longer exists", QUESTION: "Question no longer exists",
            HYPOTHESIS: "Hypothesis no longer exists",
            DRAWING: "Drawing no longer in the Whiteboard folder"}.get(k, "No longer exists")


def label(db: Database | None, nb, link: Link) -> str:
    """How a link's item reads now: "D001 dʌ́ʌmã ‘goats’ · PL", "U004 … ‘The hare ran.’",
    "T001 Hyena and Hare · 0:12.30", the question's text, "H3 Tone spreads rightward"…"""
    from .notebook import describe
    k = link.kind
    try:
        hit = find(db, nb, link)
    except Exception:                             # a link the database can't place: its own words
        hit = None
    if k == TOKEN and hit is not None:
        e, i = hit
        return describe(db, e, e.tokens[i])
    if k == UTTERANCE and hit is not None:
        return describe(db, hit)
    if k == LINE:
        return (link.about or "Text line") + (f"  {_short(link.text, 50)}" if link.text else "")
    if k == QUESTION:
        if hit is not None:
            s, q = hit
            return f"{'To Do' if q.is_todo else 'Q'}: {q.text}"        # Q: … (Josh, 25 October)
        return f"Q: {link.text}" if link.text else "Question"
    if k == COMMENT:
        return f"Comment on {link.about}: {link.text}" if link.about else f"Comment: {link.text}"
    if k == HYPOTHESIS:
        return hit.title() if hit is not None else (link.about or "Hypothesis")
    if k == SNAPSHOT:
        snap = snapshot_listed(nb, link)
        if snap is not None:                       # renamed in the list: the link follows the name
            return snap.name
        name = link.about or "Snapshot"
        return f"{name} ({SNAPSHOT_DELETED.lower()})" if link.target else name
    if k == DRAWING:
        return f"Drawing: {link.about or link.target}"
    return link.about or KIND_NAMES.get(k, k)


def is_gone(db: Database | None, nb, link: Link) -> bool:
    if link.kind == SNAPSHOT:
        return False
    try:
        return find(db, nb, link) is None
    except Exception:
        return True


def cited_by(nb, h: Hypothesis) -> list[tuple[Hypothesis, Link]]:
    """The hypotheses that link to this one, with their link (worked out, nothing stored twice)."""
    return [(o, ln) for o in nb.hypotheses if o is not h for ln in o.links
            if ln.kind == HYPOTHESIS and ln.target == h.id]


def linked_to_item(nb, kind: str, entry: str = "", token: str = "") -> list[tuple[Hypothesis, Link]]:
    """The hypotheses a token or utterance is in (the dialogues' "In hypotheses" line)."""
    out = []
    for h in nb.hypotheses:
        for ln in h.links:
            if ln.kind != kind:
                continue
            if kind == UTTERANCE and ln.entry == entry:
                out.append((h, ln))
            elif kind == TOKEN and ln.entry == entry and ln.token == token:
                out.append((h, ln))
    return out


def matches(h: Hypothesis, text: str, db: Database | None = None, nb=None) -> bool:
    """The search (List's quick search, the notebook's search): number, summary, formulation,
    confidence and the links' notes and words."""
    from . import search
    return search.matches(text, search_parts(h))      # one search for every bar (idea 86)


def search_parts(h: Hypothesis) -> list[str]:
    """What a search looks through in a hypothesis."""
    parts = [h.label, h.summary, h.formulation, h.confidence]
    for ln in h.links:
        parts += [ln.note, ln.about, ln.text]
    return parts


# --------------------------------------------------------------------------
# The file: <hypotheses> at the end of the notebook (format 3)
# --------------------------------------------------------------------------

def write_xml(nb, root):
    """Add <hypotheses> (the confidence list, then each hypothesis) at the end of the notebook."""
    import json
    import xml.etree.ElementTree as ET
    if not nb.hypotheses and _default_list(nb) and nb.next_number <= 1:
        return
    el = ET.SubElement(root, "hypotheses", next=str(nb.next_number))
    if not _default_list(nb):
        conf = ET.SubElement(el, "confidence")
        for top in nb.confidence:
            _write_item(conf, top)
    for h in sorted(nb.hypotheses, key=lambda h: h.number):
        a = {"id": h.id, "number": str(h.number)}
        if h.confidence:
            a["confidence"] = h.confidence
        if h.made:
            a["made"] = h.made
        if h.edited:
            a["edited"] = h.edited
        he = ET.SubElement(el, "hypothesis", a)
        if h.summary:
            ET.SubElement(he, "summary").text = h.summary
        if h.formulation:
            ET.SubElement(he, "formulation").text = h.formulation
        for ln in h.links:
            la = {"kind": ln.kind, "mark": ln.mark}
            for key, val in (("linked", ln.linked), ("entry", ln.entry), ("token", ln.token),
                             ("target", ln.target), ("date", ln.date), ("field", ln.field), ("about", ln.about)):
                if val:
                    la[key] = val
            if ln.start is not None:
                la["start"] = f"{ln.start:.4f}"
            le = ET.SubElement(he, "link", la)
            if ln.text:
                ET.SubElement(le, "text").text = ln.text
            if ln.note:
                ET.SubElement(le, "note").text = ln.note
            if ln.view is not None:               # a snapshot's setup, as the workspace keeps a view
                ET.SubElement(le, "view").text = json.dumps(ln.view, ensure_ascii=False, sort_keys=True)


def _write_item(parent, item):
    import xml.etree.ElementTree as ET
    el = ET.SubElement(parent, "item", name=item.name)
    for c in item.children:
        _write_item(el, c)


def _read_item(el):
    from .model import ListItem
    return ListItem(nfc(el.get("name", "")), [_read_item(c) for c in el.findall("item")])


def default_confidence():
    from .model import ListItem
    return [ListItem(n) for n in DEFAULT_CONFIDENCE]


def _default_list(nb) -> bool:
    return [(i.name, i.children) for i in nb.confidence] == [(n, []) for n in DEFAULT_CONFIDENCE]


def read_xml(nb, root):
    """Read <hypotheses> (a notebook without one has none, and the default confidence list)."""
    import json
    el = root.find("hypotheses")
    if el is None:
        return
    try:
        nb.next_number = max(1, int(el.get("next", "1")))
    except ValueError:
        nb.next_number = 1
    conf = el.find("confidence")
    if conf is not None:
        nb.confidence = [_read_item(x) for x in conf.findall("item")]
    for he in el.findall("hypothesis"):
        try:
            number = int(he.get("number", "0"))
        except ValueError:
            number = 0
        h = Hypothesis(he.get("id") or new_id(), number, _text(he.find("summary")), _text(he.find("formulation")),
                       nfc(he.get("confidence", "")), he.get("made", ""), he.get("edited", ""))
        for le in he.findall("link"):
            start = le.get("start")
            try:
                start = float(start) if start not in (None, "") else None
            except ValueError:
                start = None
            view = None
            ve = le.find("view")
            if ve is not None and (ve.text or "").strip():
                try:
                    view = json.loads(ve.text)
                except ValueError:
                    view = None
            kind = le.get("kind", RELEVANT)
            if kind not in KINDS:
                continue
            mark = le.get("mark", RELEVANT)
            h.links.append(Link(kind, mark if mark in MARKS else RELEVANT, _text(le.find("note")),
                                le.get("linked", ""), le.get("entry", ""), le.get("token", ""),
                                le.get("target", ""), start, nfc(le.get("about", "")), _text(le.find("text")),
                                le.get("date", ""), le.get("field", ""), view))
        nb.hypotheses.append(h)
    numbers = [h.number for h in nb.hypotheses]
    for h in nb.hypotheses:                        # a hand-edited file: every number its own
        if h.number <= 0 or numbers.count(h.number) > 1:
            h.number = max(numbers + [nb.next_number - 1]) + 1
            numbers.append(h.number)
    nb.next_number = max([nb.next_number] + [n + 1 for n in numbers])


def _text(el) -> str:
    return nfc(el.text or "").strip("\n") if el is not None else ""
