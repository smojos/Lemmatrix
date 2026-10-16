"""The open database plus undo/redo.

Every change to an entry (and its tokens) goes through Document, which keeps a
before/after copy of the entry on Qt's undo stack. Sound files on disk are not
part of undo: re-recording or deleting a recording can't be undone here
(deleted recordings go to the Recycle Bin instead).
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .. import storage
from ..model import Database, Entry


def _restore(target: Entry, snapshot: Entry):
    fresh = copy.deepcopy(snapshot)
    target.__dict__.update(fresh.__dict__)


class EntryCommand(QUndoCommand):
    def __init__(self, doc: "Document", label: str, entry: Entry | None,
                 before: Entry | None, after: Entry | None, index: int, applied: bool = True):
        super().__init__(label)
        self.doc, self.entry, self.before, self.after, self.index = doc, entry, before, after, index
        self._skip = applied          # the change has already been made once

    def _apply(self, snap_from: Entry | None, snap_to: Entry | None):
        db = self.doc.db
        if snap_to is None:                     # remove
            if self.entry in db.entries:
                db.entries.remove(self.entry)
        elif snap_from is None:                 # insert
            _restore(self.entry, snap_to)
            db.entries.insert(min(self.index, len(db.entries)), self.entry)
        else:                                   # replace in place
            _restore(self.entry, snap_to)
        self.doc.changed.emit()

    def redo(self):
        if self._skip:
            self._skip = False
            return
        self._apply(self.before, self.after)

    def undo(self):
        self._apply(self.after, self.before)


class Document(QObject):
    changed = Signal()            # entries or tokens changed
    settingsChanged = Signal()    # metadata or settings changed
    dirtyChanged = Signal(bool)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.undo = QUndoStack(self)
        self._settings_dirty = False
        self.undo.cleanChanged.connect(lambda clean: self.dirtyChanged.emit(self.dirty))

    @property
    def dirty(self) -> bool:
        return self._settings_dirty or not self.undo.isClean()

    # ---- entry changes -------------------------------------------------
    def edit_entry(self, entry: Entry, change, label: str = "Edit"):
        """Run change(entry) and record it for undo."""
        before = entry.copy()
        change(entry)
        after = entry.copy()
        if before == after:
            return
        idx = self.db.entries.index(entry) if entry in self.db.entries else len(self.db.entries)
        self.undo.push(EntryCommand(self, label, entry, before, after, idx))
        self.changed.emit()

    def add_entry(self, entry: Entry, index: int | None = None):
        idx = len(self.db.entries) if index is None else index
        self.db.entries.insert(idx, entry)
        self.undo.push(EntryCommand(self, f"Add {entry.ref}", entry, None, entry.copy(), idx))
        self.changed.emit()

    def delete_entry(self, entry: Entry):
        idx = self.db.entries.index(entry)
        before = entry.copy()
        self.db.entries.remove(entry)
        self.undo.push(EntryCommand(self, f"Delete {entry.ref}", entry, before, None, idx))
        self.changed.emit()

    # ---- settings ------------------------------------------------------
    def settings_changed(self):
        self._settings_dirty = True
        self.dirtyChanged.emit(True)
        self.settingsChanged.emit()
        self.changed.emit()

    # ---- saving --------------------------------------------------------
    def save(self, path: str | None = None):
        storage.save(self.db, path)
        self._settings_dirty = False
        self.undo.setClean()
        self.dirtyChanged.emit(False)
