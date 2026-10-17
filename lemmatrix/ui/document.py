"""The open database plus undo/redo.

Every change to an entry (and its tokens) goes through Document, which keeps a
before/after copy of the entry on Qt's undo stack.

Renaming recordings changes the disk straight away, so the database and the
sound folder could disagree after an undo, or after closing without saving.
To prevent that, renames travel with their undo step (undo renames the files
back), and Document remembers every rename since the last save, so discarding
the changes can put the files' names back too. Re-recording or deleting a
recording isn't undone (deleted recordings go to the Recycle Bin).
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .. import storage
from ..model import Database, Entry


def _restore(target: Entry, snapshot: Entry):
    fresh = copy.deepcopy(snapshot)
    target.__dict__.update(fresh.__dict__)


class EntryCommand(QUndoCommand):
    def __init__(self, doc: "Document", label: str, entry: Entry | None,
                 before: Entry | None, after: Entry | None, index: int, applied: bool = True,
                 renames=()):
        super().__init__(label)
        self.doc, self.entry, self.before, self.after, self.index = doc, entry, before, after, index
        self.renames = list(renames)  # (old path, new path) of recordings renamed with this change
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
        for old, new in self.renames:
            self.doc.move_file(old, new)
        self._apply(self.before, self.after)

    def undo(self):
        for old, new in reversed(self.renames):
            self.doc.move_file(new, old)
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
        self.renamed: dict[Path, Path] = {}     # recording's path now -> its path at the last save
        self.undo.cleanChanged.connect(self._clean_changed)

    def _clean_changed(self, clean: bool):
        try:
            self.dirtyChanged.emit(self.dirty)
        except RuntimeError:          # the window is closing and Qt has already deleted us
            pass

    @property
    def dirty(self) -> bool:
        return self._settings_dirty or not self.undo.isClean()

    # ---- entry changes -------------------------------------------------
    def edit_entry(self, entry: Entry, change, label: str = "Edit", renames=()):
        """Run change(entry) and record it for undo.

        renames: (old, new) paths of recordings the caller has just renamed as part of
        this change; undoing the change renames them back.
        """
        before = entry.copy()
        change(entry)
        after = entry.copy()
        for old, new in renames:
            self._note_rename(Path(old), Path(new))
        if before == after and not renames:
            return
        idx = self.db.entries.index(entry) if entry in self.db.entries else len(self.db.entries)
        self.undo.push(EntryCommand(self, label, entry, before, after, idx, renames=renames))
        self.changed.emit()

    # ---- recordings renamed since the last save ------------------------
    def _note_rename(self, old: Path, new: Path):
        original = self.renamed.pop(old, old)
        if original != new:
            self.renamed[new] = original

    def move_file(self, src, dst) -> bool:
        """Rename a recording (for undo and redo); remembered until the next save."""
        src, dst = Path(src), Path(dst)
        if not src.exists() or (dst.exists() and not storage.same_file(src, dst)):
            return False
        try:
            src.rename(dst)
        except OSError:
            return False
        self._note_rename(src, dst)
        return True

    def revert_renames(self) -> list[str]:
        """Give renamed recordings back the names the saved database expects.

        Used when the changes are discarded. Returns the files that couldn't be renamed.
        """
        problems = []
        moves = [(now, then) for now, then in self.renamed.items() if now != then]
        temps = []
        for now, then in moves:                  # via temporary names, in case names swapped
            tmp = now.with_name(now.name + ".lemmatrix-renaming")
            try:
                now.rename(tmp)
                temps.append((tmp, then, now))
            except OSError as exc:
                problems.append(f"{now.name}: {exc}")
        for tmp, then, now in temps:
            try:
                if then.exists():
                    raise OSError(f"{then.name} already exists")
                tmp.rename(then)
            except OSError as exc:
                tmp.rename(now)
                problems.append(f"{now.name}: {exc}")
        self.renamed.clear()
        return problems

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
    def save(self, path: str | None = None, backup_dir: str | None = None):
        storage.save(self.db, path, backup_dir=backup_dir or None)
        self.renamed.clear()                    # the saved database now has the new names
        self._settings_dirty = False
        self.undo.setClean()
        self.dirtyChanged.emit(False)
