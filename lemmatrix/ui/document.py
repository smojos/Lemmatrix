"""The open database plus undo/redo.

Every change to an entry (and its tokens) goes through Document, which keeps a
before/after copy of the entry on Qt's undo stack.

Renaming recordings changes the disk straight away, so the database and the
sound folder could disagree after an undo, or after closing without saving.
To prevent that, renames travel with their undo step (undo renames the files
back), and Document remembers every rename since the last save, so discarding
the changes can put the files' names back too. Re-recording or deleting a
recording isn't undone (deleted recordings go to the Recycle Bin).

The notebook (<database>.notebook) belongs to the document too: it is saved with
the database, and its unsaved changes count as unsaved changes. Every change to
a comment field is dated with the session's date (work_date), which is what the
notebook's record of comments goes by.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .. import notebook as nbmod, storage
from ..model import Database, Entry, today


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
        self.notebook = nbmod.Notebook()
        self.notebook_unreadable = False        # then it is never written over
        self.work_date = today                  # the session's date (set by the main window)
        self.undo.cleanChanged.connect(self._clean_changed)

    def _clean_changed(self, clean: bool):
        try:
            self.dirtyChanged.emit(self.dirty)
        except RuntimeError:          # the window is closing and Qt has already deleted us
            pass

    @property
    def dirty(self) -> bool:
        return self._settings_dirty or not self.undo.isClean() or self.notebook.dirty

    def notebook_changed(self):
        """The notebook was edited: mark it unsaved."""
        self.notebook.dirty = True
        self.dirtyChanged.emit(True)

    # ---- entry changes -------------------------------------------------
    def edit_entry(self, entry: Entry, change, label: str = "Edit", renames=()):
        """Run change(entry) and record it for undo.

        renames: (old, new) paths of recordings the caller has just renamed as part of
        this change; undoing the change renames them back.
        """
        before = entry.copy()
        change(entry)
        self.db.stamp_comments(before, entry, self.work_date())
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
        self.db.stamp_comments(None, entry, self.work_date())
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
        self.save_notebook(backup_dir)
        self.dirtyChanged.emit(False)

    # ---- the notebook --------------------------------------------------
    def load_notebook(self) -> str:
        """Read the database's notebook (none yet is fine). Returns a problem to report, or ""."""
        self.notebook = nbmod.Notebook()
        if not self.db.path:
            return ""
        path = nbmod.path_for(self.db.path)
        try:
            self.notebook = nbmod.load(path)
        except (nbmod.NotebookError, OSError) as exc:
            self.notebook = nbmod.Notebook(path=str(path))
            self.notebook_unreadable = True
            return str(exc)
        self.notebook_unreadable = False
        return ""

    def save_notebook(self, backup_dir: str | None = None):
        """Write the notebook next to the database, if it has anything in it."""
        nb = self.notebook
        if not self.db.path or self.notebook_unreadable:
            return                              # never write over a notebook that couldn't be read
        path = nbmod.path_for(self.db.path)
        if not nb.sessions and not path.exists():
            nb.dirty = False
            return
        if nb.dirty or Path(nb.path or "") != path or not path.exists():
            storage.make_backup(path, folder=backup_dir or None)
            nbmod.save(nb, path, Path(self.db.path).name)
