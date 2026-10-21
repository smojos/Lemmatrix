# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
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

The workspace (<database>.workspace, workspace.py; idea 36) belongs to the document as well, but
never counts as unsaved: it is written a moment after anything in it changes (saved matrices,
rerecord flags, the spelling list, the view, filters, the session…), and again on saving, when
a copy of the one before goes to Backups.

Texts' lines are edited in their TextGrids (lines.py): a TextGrid being edited is held in a
Buffer here, its edits are undo steps like any other, and it is written when the database is
saved; not saving leaves the file as it was.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QTimer, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .. import lines as lmod, notebook as nbmod, predict, storage
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
        items = self.doc.db.list_for(self.entry)  # the entries, or the utterances
        if snap_to is None:                     # remove
            if self.entry in items:
                items.remove(self.entry)
        elif snap_from is None:                 # insert
            _restore(self.entry, snap_to)
            items.insert(min(self.index, len(items)), self.entry)
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


class BulkCommand(QUndoCommand):
    """Many entries changed at once (a bulk edit), with their recordings renamed: one undo step.

    Renames are done in the plan's order (a recording moves out of a name before another
    moves in) and undone in reverse.
    """

    def __init__(self, doc: "Document", label: str, changes, renames=()):
        super().__init__(label)
        self.doc = doc
        self.changes = list(changes)          # (entry, before snapshot, after snapshot)
        self.renames = list(renames)
        self._skip = True                     # already applied once

    def redo(self):
        if self._skip:
            self._skip = False
            return
        for old, new in self.renames:
            self.doc.move_file(old, new)
        for entry, _, after in self.changes:
            _restore(entry, after)
        self.doc.changed.emit()

    def undo(self):
        for old, new in reversed(self.renames):
            self.doc.move_file(new, old)
        for entry, before, _ in self.changes:
            _restore(entry, before)
        self.doc.changed.emit()


class AddManyCommand(QUndoCommand):
    """Several entries or utterances added at once (an import): one undo step.

    renames: (where a recording goes on undo, where it is now): each imported recording
    was copied in, so undoing moves it aside (into the held folder) and redoing brings it back.
    """

    def __init__(self, doc: "Document", label: str, items, renames=()):
        super().__init__(label)
        self.doc = doc
        self.items = list(items)
        self.snaps = [i.copy() for i in self.items]
        self.renames = list(renames)
        self._skip = True

    def redo(self):
        if self._skip:
            self._skip = False
            return
        for old, new in self.renames:
            self.doc.move_file(old, new)
        for item, snap in zip(self.items, self.snaps):
            _restore(item, snap)
            items = self.doc.db.list_for(item)
            if item not in items:
                items.append(item)
        self.doc.changed.emit()

    def undo(self):
        for old, new in reversed(self.renames):
            self.doc.move_file(new, old)
        for item in self.items:
            items = self.doc.db.list_for(item)
            if item in items:
                items.remove(item)
        self.doc.changed.emit()


class LineEditCommand(QUndoCommand):
    """A change to a text's line: its TextGrid's tiers (in the Buffer), the utterances clipped
    from the line, and the notebook's record of the line's comment. Applied once already."""

    def __init__(self, doc: "Document", label: str, text_id: str, edits, generation: int,
                 utterances=(), notebook=None):
        super().__init__(label)
        self.doc, self.text_id, self.edits, self.generation = doc, text_id, list(edits), generation
        self.utterances = list(utterances)     # (utterance, before, after)
        self.notebook = notebook               # (session, comments before, comments after) or None
        self._skip = True

    def _apply(self, undo: bool):
        buf = self.doc.text_buffers.get(self.text_id)
        if buf is not None and buf.generation == self.generation:   # not since read again from disk
            buf.apply(self.edits, undo=undo)
        for u, before, after in self.utterances:
            _restore(u, before if undo else after)
        if self.notebook is not None:
            session, before, after = self.notebook
            session.comments = list(before if undo else after)
            self.doc.notebook.dirty = True
        self.doc.linesChanged.emit(self.text_id)
        self.doc.changed.emit()

    def redo(self):
        if self._skip:
            self._skip = False
            return
        self._apply(False)

    def undo(self):
        self._apply(True)


def _hyp_state(nb) -> tuple:
    """What a hypothesis change can alter, besides the lines in the notes (the Journal's)."""
    return (copy.deepcopy(nb.hypotheses), nb.next_number, {s.date: list(s.hypotheses) for s in nb.sessions})


class HypothesisCommand(QUndoCommand):
    """A change in Cogitate (hypotheses.py): the hypotheses before and after, and the lines the
    change wrote into the days' notes (taken out again on undo, nothing else in the notes touched).
    Applied once already."""

    def __init__(self, doc: "Document", label: str, before: tuple, after: tuple, journal):
        super().__init__(label)
        self.doc, self.before, self.after, self.journal = doc, before, after, journal
        self._skip = True

    def _set(self, state):
        nb = self.doc.notebook
        hyps, number, days = state
        nb.hypotheses = copy.deepcopy(hyps)
        nb.next_number = number
        for s in nb.sessions:
            s.hypotheses = list(days.get(s.date, []))

    def redo(self):
        if self._skip:
            self._skip = False
            return
        self.journal.redo_lines()
        self._set(self.after)
        self.doc.notebook.dirty = True
        self.doc.hypothesesChanged.emit()

    def undo(self):
        self._set(self.before)
        self.journal.undo_lines()
        self.doc.notebook.dirty = True
        self.doc.hypothesesChanged.emit()


class Document(QObject):
    changed = Signal()            # entries or tokens changed
    hypothesesChanged = Signal()  # Cogitate: a hypothesis made, edited, linked… (or undone)
    linesChanged = Signal(str)    # a text's lines changed (its id)
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
        self.predictor = predict.Predictor()    # suggested translations, learned from this database
        self.text_buffers: dict[str, lmod.Buffer] = {}   # text id -> its TextGrid being edited
        self.undo.cleanChanged.connect(self._clean_changed)
        from .. import workspace as wsmod
        self.workspace = wsmod.Workspace()      # the working state, beside the database (idea 36)
        self._ws_written = None                 # (path, text) as last written, so nothing is written twice
        self._ws_timer = QTimer(self)
        self._ws_timer.setSingleShot(True)
        self._ws_timer.setInterval(400)         # a moment after the last change
        self._ws_timer.timeout.connect(self.write_workspace)
        self.changed.connect(self._ws_timer.start)   # e.g. a rerecord flag set in an edit

    # ---- texts' lines (edited in their TextGrids) -------------------------
    def buffer(self, text, reload_if_saved_elsewhere: bool = True):
        """The text's TextGrid held for editing (read when first needed; read again if Praat
        saved it and there are no edits here waiting). None without a TextGrid."""
        if not text.textgrid or not self.db.path:
            return None
        path = storage.text_folder(self.db) / text.textgrid
        if not path.exists():
            return None
        buf = self.text_buffers.get(text.id)
        if buf is None or buf.path != path:
            buf = self.text_buffers[text.id] = lmod.Buffer(path)
        elif reload_if_saved_elsewhere and not buf.changed and buf.disk_changed():
            buf.reload()
        return buf

    def edited_buffers(self) -> list:
        return [(self.db.text_by_id(tid), b) for tid, b in self.text_buffers.items() if b.changed]

    def push_line_edit(self, label: str, text, buf, edits, utterances=(), notebook=None):
        """Record a line edit already made (buffer, utterances and notebook) for undo."""
        self.undo.push(LineEditCommand(self, label, text.id, edits, buf.generation, utterances, notebook))
        self.linesChanged.emit(text.id)
        self.changed.emit()

    def _clean_changed(self, clean: bool):
        try:
            self.dirtyChanged.emit(self.dirty)
        except RuntimeError:          # the window is closing and Qt has already deleted us
            pass

    @property
    def dirty(self) -> bool:
        return self._settings_dirty or not self.undo.isClean() or self.notebook.dirty

    def change_hypotheses(self, label: str, change):
        """Run change(journal) on the notebook's hypotheses (hypotheses.py) as one undo step; the
        day being worked on is work_date(). Returns what change returns. Nothing changed (it
        returned None or False and wrote nothing): no undo step."""
        from .. import hypotheses as hy
        nb = self.notebook
        before = _hyp_state(nb)
        j = hy.Journal(nb)
        result = change(j)
        after = _hyp_state(nb)
        if not j.lines and not j.made_days and before[0] == after[0] and before[2] == after[2]:
            return result
        self.undo.push(HypothesisCommand(self, label, before, after, j))
        nb.dirty = True
        self.dirtyChanged.emit(True)
        self.hypothesesChanged.emit()
        return result

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
        items = self.db.list_for(entry)
        idx = items.index(entry) if entry in items else len(items)
        self.undo.push(EntryCommand(self, label, entry, before, after, idx, renames=renames))
        self.changed.emit()

    def apply_changes(self, label: str, pairs, renames=(), stamp: bool = True) -> list[str]:
        """Change many entries at once as one undo step (bulk edit, word class changes).

        pairs: (entry, the changed copy); renames: (old, new) paths in the order to rename them.
        The recordings are renamed first; if one can't be, those already renamed go back and
        nothing changes. stamp: date the changed comment fields with the session's date.
        Returns the problems (empty when it worked).
        """
        done = []
        for old, new in renames:
            old, new = Path(old), Path(new)
            problem = ""
            if not old.exists():
                problem = f"{old.name} isn't in the sound folder"
            elif new.exists() and not storage.same_file(old, new):
                problem = f"{new.name} already exists"
            else:
                try:
                    old.rename(new)
                except OSError as exc:
                    problem = f"{old.name}: {exc}"
            if problem:
                for o, n in reversed(done):
                    try:
                        n.rename(o)
                    except OSError:
                        pass
                return [problem]
            done.append((old, new))
        changes = []
        for entry, after in pairs:
            before = entry.copy()
            _restore(entry, after)
            if stamp:
                self.db.stamp_comments(before, entry, self.work_date())
            changes.append((entry, before, entry.copy()))
        for old, new in done:
            self._note_rename(old, new)
        if changes or done:
            self.undo.push(BulkCommand(self, label, changes, done))
            self.changed.emit()
        return []

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

    # ---- recordings of deleted tokens -----------------------------------
    def hold_recording(self, path: Path) -> Path:
        """Where a deleted token's recording goes for now (a name of its own in the held folder)."""
        folder = storage.held_folder(self.db)
        folder.mkdir(parents=True, exist_ok=True)
        target, n = folder / path.name, 2
        while target.exists():
            target, n = folder / f"{path.stem} ({n}){path.suffix}", n + 1
        return target

    def bring_back_held(self):
        """On opening: a held recording that a token of the database still uses goes back (the
        deletion wasn't saved, e.g. after a crash)."""
        if not self.db.path:
            return
        home = {t.file: storage.folder_for(self.db, e) for e, t in self.db.all_tokens() if t.file}
        for held in storage.held_folders(self.db):
            if not held.is_dir():
                continue
            for f in held.iterdir():
                folder = home.get(f.name)
                if f.is_file() and folder is not None and folder.is_dir() and not (folder / f.name).exists():
                    try:
                        f.rename(folder / f.name)
                    except OSError:
                        pass

    def empty_held(self):
        """On closing the database: the deleted tokens' recordings go to the Recycle Bin."""
        if not self.db.path:
            return
        for held in storage.held_folders(self.db):
            if not held.is_dir():
                continue
            for f in held.iterdir():
                if f.is_file():
                    QFile.moveToTrash(str(f))
            try:
                held.rmdir()                      # only if it's empty now
            except OSError:
                pass

    def add_entry(self, entry: Entry, index: int | None = None, renames=()):
        """Add an entry (or an utterance, to the utterances) as one undo step."""
        items = self.db.list_for(entry)
        idx = len(items) if index is None else index
        self.db.stamp_comments(None, entry, self.work_date())
        for old, new in renames:
            self._note_rename(Path(old), Path(new))
        items.insert(idx, entry)
        self.undo.push(EntryCommand(self, f"Add {entry.ref}", entry, None, entry.copy(), idx,
                                    renames=renames))
        self.changed.emit()

    def add_many(self, label: str, items, renames=()):
        """Add several entries or utterances as one undo step (an import). renames: (where each
        copied-in recording goes on undo, where it is now)."""
        if not items:
            return
        date = self.work_date()
        for item in items:
            self.db.stamp_comments(None, item, date)
            self.db.list_for(item).append(item)
        for old, new in renames:
            self._note_rename(Path(old), Path(new))
        self.undo.push(AddManyCommand(self, label, items, renames))
        self.changed.emit()

    def delete_entry(self, entry: Entry, renames=()):
        """Delete an entry (or an utterance); renames: recordings moved aside with it (held)."""
        items = self.db.list_for(entry)
        idx = items.index(entry)
        before = entry.copy()
        items.remove(entry)
        for old, new in renames:
            self._note_rename(Path(old), Path(new))
        self.undo.push(EntryCommand(self, f"Delete {entry.ref}", entry, before, None, idx,
                                    renames=renames))
        self.changed.emit()

    # ---- settings ------------------------------------------------------
    def settings_changed(self):
        self._settings_dirty = True
        self.dirtyChanged.emit(True)
        self.settingsChanged.emit()
        self.changed.emit()

    # ---- the workspace (idea 36) ---------------------------------------------
    @property
    def ws(self):
        return self.workspace

    def ws_set(self, name: str, value):
        """Set one of the workspace's values; it is written a moment later."""
        self.workspace.set(name, value)
        if self.workspace.dirty:
            self._ws_timer.start()

    def workspace_changed(self):
        """Something of the workspace's kept in the database's objects changed (a saved matrix,
        the spelling list…): written a moment later; the database stays as saved or unsaved as it was."""
        self.workspace.touch()
        self._ws_timer.start()
        self.settingsChanged.emit()
        self.changed.emit()

    def write_workspace(self) -> bool:
        """Write the workspace beside the database, if it has changed since it was last written."""
        from .. import workspace as wsmod
        self._ws_timer.stop()
        ws = self.workspace
        if not self.db.path or ws.unreadable:
            return False
        path = str(wsmod.path_for(self.db.path))
        text = wsmod.to_string(ws, self.db)
        if self._ws_written == (path, text) and Path(path).exists():
            ws.dirty = False
            return False
        try:
            wsmod.save(ws, self.db, path)
        except OSError:
            return False                        # tried again with the next change, or on saving
        self._ws_written = (path, text)
        return True

    def set_workspace(self, ws, written: bool):
        """The workspace that goes with the database just opened (written: as it is on disk)."""
        from .. import workspace as wsmod
        self._ws_timer.stop()
        self.workspace = ws
        self._ws_written = ((str(wsmod.path_for(self.db.path)), wsmod.to_string(ws, self.db))
                            if written and self.db.path else None)

    # ---- saving --------------------------------------------------------
    def save(self, path: str | None = None):
        from .. import workspace as wsmod
        for text, buf in self.edited_buffers():  # texts' TextGrids first (each backed up)
            buf.write(self.db)
        storage.save(self.db, path)
        self.renamed.clear()                    # the saved database now has the new names
        self._settings_dirty = False
        self.undo.setClean()
        self.save_notebook()
        if not self.workspace.unreadable:       # a copy of the workspace into Backups, then the new one
            wsmod.backup(self.db)
            self._ws_written = None
            self.write_workspace()
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

    def save_notebook(self):
        """Write the notebook next to the database, if it has anything in it."""
        nb = self.notebook
        if not self.db.path or self.notebook_unreadable:
            return                              # never write over a notebook that couldn't be read
        path = nbmod.path_for(self.db.path)
        if not nb.sessions and not path.exists():
            nb.dirty = False
            return
        if nb.dirty or Path(nb.path or "") != path or not path.exists():
            storage.make_backup(path)
            nbmod.save(nb, path, Path(self.db.path).name)
