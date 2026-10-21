# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The workspace file: a database's working state, beside it (IDEAS.md idea 36, 21 October 2026).

Lemmatrix's goal is human readable, machine processable, ethically collected and shared
linguistic data. The database keeps only what describes the data or is needed to read it; what
you are working on goes here, in `<database>.workspace`: the saved matrices, the tokens flagged
to be recorded again, the spellcheck's own words, the Current Session, the last view, the
columns, filters and searches, and the rest. How things look (theme, widths, window sizes) stays
on each computer.

The file is XML, like the notebook. It is written as soon as something changes (the window
does that a moment after), never marks the database unsaved, goes into Full backup and Backups,
and is left out of the anonymous backup (it holds participant codes and no data).

Three parts of it live in the database's objects while it is open, so the rest of the program
works with them as before: `settings.matrices`, `settings.play_cell_on_click`,
`settings.pitch_style`, `settings.spelling_words` and each token's `rerecord` flag. Everything
else is a named value (`get`, `set`), a string, number, list or dict, written as JSON text.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .model import Database, nfc, write_atomically, xml_safe

FORMAT = "1"
SUFFIX = ".workspace"


class WorkspaceError(Exception):
    pass


def path_for(db_path: str | os.PathLike) -> Path:
    """The workspace beside a database: Lex.xml → Lex.workspace."""
    return Path(db_path).with_suffix(SUFFIX)


@dataclass
class Workspace:
    path: str = ""
    values: dict = field(default_factory=dict)    # name -> a JSON-able value
    dirty: bool = False                           # changed since it was last written
    unreadable: bool = False                      # then it is never written over

    # ---- named values ---------------------------------------------------------
    def get(self, name: str, default=None):
        return self.values.get(name, default)

    def set(self, name: str, value):
        """Set a value (None removes it); marks the workspace changed if it is."""
        if value is None:
            if name in self.values:
                del self.values[name]
                self.dirty = True
            return
        if self.values.get(name) != value:
            self.values[name] = value
            self.dirty = True

    # the shapes the per-computer preferences had, so callers read the same way
    def get_list(self, name: str) -> list[str]:
        v = self.values.get(name)
        return [str(x) for x in v] if isinstance(v, list) else []

    def set_list(self, name: str, items: list[str]):
        self.set(name, list(items))

    def get_bool(self, name: str, default: bool = False) -> bool:
        v = self.values.get(name)
        return bool(v) if isinstance(v, bool) else default

    def get_dict(self, name: str) -> dict:
        v = self.values.get(name)
        return dict(v) if isinstance(v, dict) else {}

    def touch(self):
        """Something kept in the database's objects (matrices, rerecord flags…) changed."""
        self.dirty = True


# ---- reading and writing ------------------------------------------------------------

def _rerecorded(db: Database) -> list[tuple[str, str]]:
    """(token id, a readable label) for every token flagged to be recorded again."""
    out = []
    for e in list(db.entries) + list(db.utterances):
        for t in e.tokens:
            if t.rerecord and t.id:
                tags = ", ".join(t.tags)
                out.append((t.id, e.ref + (f" ({tags})" if tags else "")))
    return out


def to_string(ws: Workspace, db: Database) -> str:
    from .storage import save_matrices
    s = db.settings
    root = ET.Element("workspace", format=FORMAT)
    if db.metadata.name or db.path:
        root.set("database", Path(db.path).name if db.path else db.metadata.name)
    ET.SubElement(root, "settings", {"play-cell-on-click": "yes" if s.play_cell_on_click else "no",
                                     "pitch-style": s.pitch_style})
    if s.matrices:
        save_matrices(ET.SubElement(root, "matrices"), s.matrices, s.tags)
    flagged = _rerecorded(db)
    if flagged:
        rr = ET.SubElement(root, "rerecord")             # tokens flagged to be recorded again
        for tid, label in flagged:
            ET.SubElement(rr, "token", id=tid).text = label
    if s.spelling_words:                                  # the spellcheck's own words
        sp = ET.SubElement(root, "spelling")
        for w in sorted(dict.fromkeys(s.spelling_words), key=str.lower):
            ET.SubElement(sp, "word").text = w
    if ws.values:
        st = ET.SubElement(root, "state")
        for name in sorted(ws.values):
            ET.SubElement(st, "value", name=name).text = json.dumps(ws.values[name], ensure_ascii=False,
                                                                    sort_keys=True)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def from_string(text: str, db: Database, path: str = "") -> Workspace:
    """A workspace from its text, put into the database's objects. WorkspaceError if unreadable."""
    from .storage import _load_matrices
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise WorkspaceError(f"The workspace {Path(path).name or ''} isn't readable XML: {exc}") from exc
    if root.tag != "workspace":
        raise WorkspaceError(f"{Path(path).name} isn't a Lemmatrix workspace.")
    s = db.settings
    ws = Workspace(path=path)
    if (x := root.find("settings")) is not None:
        s.play_cell_on_click = x.get("play-cell-on-click") == "yes"
        s.pitch_style = x.get("pitch-style", s.pitch_style) or "contours"
    s.matrices = _load_matrices(root.find("matrices"))
    flagged = {x.get("id") for x in root.iter("token") if x.get("id")}
    for e in list(db.entries) + list(db.utterances):
        for t in e.tokens:
            t.rerecord = t.id in flagged
    if (x := root.find("spelling")) is not None:
        s.spelling_words = [w for w in (nfc(w.text or "").strip() for w in x.findall("word")) if w]
    else:
        s.spelling_words = []
    if (x := root.find("state")) is not None:
        for v in x.findall("value"):
            try:
                ws.values[v.get("name", "")] = json.loads(v.text or "null")
            except ValueError:
                pass                                       # one unreadable value is just forgotten
    ws.values.pop("", None)
    return ws


def load(path: str | os.PathLike, db: Database) -> Workspace:
    path = str(path)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkspaceError(f"Couldn't read {Path(path).name}: {exc}") from exc
    return from_string(text, db, path)


def save(ws: Workspace, db: Database, path: str | os.PathLike | None = None):
    """Write the workspace atomically (never over one that couldn't be read)."""
    path = str(path or ws.path or (path_for(db.path) if db.path else ""))
    if not path:
        raise ValueError("No file name given")
    if ws.unreadable and Path(path).exists():
        return
    tmp = write_atomically(path, xml_safe(to_string(ws, db), line_break="\n"))
    os.replace(tmp, path)
    ws.path = path
    ws.dirty = False


def save_blank(path: str | os.PathLike):
    """A workspace with nothing in it but the defaults (the anonymous backup's: none of the
    working state goes with the data)."""
    root = ET.Element("workspace", format=FORMAT)
    ET.SubElement(root, "settings", {"play-cell-on-click": "no", "pitch-style": "contours"})
    ET.indent(root, space="  ")
    text = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    os.replace(write_atomically(str(path), text), str(path))


def backup(db: Database):
    """A copy of the workspace into Backups (on each save of the database), kept like the database's."""
    from .storage import make_backup
    p = path_for(db.path) if db.path else None
    if p is not None and p.exists():
        make_backup(p)
