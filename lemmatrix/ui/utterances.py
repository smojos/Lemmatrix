# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""View → Texts and utterances: a window of its own, like Bulk edit and the notebook.

Utterances (idea 7, stage 2) are one-off sentences and phrases with no lemma: one reference,
one token (one transcription, one recording). Their reference's letter is their category
(U Unorganised, and W, X, Y, Z of the user's own). The Utterances tab is a grid like All data;
the utterance dialogue is the token dialogue with a header of its own (reference, category,
file label), the tag groups for utterances first, and a Lemmas box for links by hand.

Utterances are made by recording on the spot (Add), or from soundfiles: Import…, or WAVs
dragged onto the grid. Imported recordings are copied into Soundfiles/Utterances under the
utterance's name; the originals are left as they are. The Texts tab comes with stage 3.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from PySide6.QtCore import QDir, QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QCompleter, QDialog, QSplitter, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget, QFileDialog)

from .. import spelling, audio, layout, matrix as mx, pitch as pitchmod, pull, storage
from ..model import FORBIDDEN_CHARS, UTTERANCES, Token, Utterance, nfc
from . import theme
from .filter_dialogs import ConfigureColumnsDialog
from .icons import icon, ink_icon
from .spellui import SpellDelegate
from .table import ChipsDelegate, Column, DrawingDelegate, FilterTable, ListEditDelegate
from .token_dialog import Slot, TokenDialog
from .widgets import FlowLayout, ipa_font, meaning

TEXTS, UTTERANCES_TAB = 0, 1      # the tabs


def clean_label(text: str, limit: int = 60) -> str:
    """A file label from a file name: no characters Windows forbids, underscores as spaces."""
    text = "".join(" " if ch in FORBIDDEN_CHARS or ch == "_" else ch for ch in text or "")
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return nfc(text[:limit].strip())


def category_title(db, ref: str) -> str:
    c = db.settings.category(ref)
    return c.name if c else ""


# --------------------------------------------------------------------------
# The grid: WAVs can be dropped on it
# --------------------------------------------------------------------------

class UtteranceTable(FilterTable):
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(self.DragDropMode.DropOnly)

    @staticmethod
    def _wavs(event) -> list[str]:
        md = event.mimeData()
        if not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(".wav")]

    def dragEnterEvent(self, event):
        if self._wavs(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._wavs(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._wavs(event)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

class TextsUtterancesWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.setWindowTitle("Texts and utterances")
        from .winstate import fit_to_screen
        fit_to_screen(self, 1300, 760)           # the default: as big as fits (a saved size wins)
        self.sound_files: set[str] = set()
        self.cloud_files: set[str] = set()
        self.checks: dict = {}                    # utterance id -> pull.Check, for clipped ones

        # Laid out like the main window's Matrix pane (Josh, 18 October), so nothing has to be
        # looked for anew: the title with the tabs on its right, the grid, the options row under
        # it, and the buttons, search and count in the options panel at the bottom.
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        split = self.split = QSplitter(Qt.Vertical)
        lay.addWidget(split)

        box = QWidget()
        bxl = QVBoxLayout(box)
        bxl.setContentsMargins(0, 0, 0, 0)
        bxl.setSpacing(2)
        head = QWidget()
        top = QHBoxLayout(head)
        top.setContentsMargins(0, 0, 0, 0)
        self.title = main._heading("Texts and utterances")
        top.addWidget(self.title)
        top.addStretch(1)
        self.tabs = QTabBar()
        self.tabs.addTab("Texts")
        self.tabs.addTab("Utterances")
        self.tabs.setExpanding(False)
        top.addWidget(self.tabs, 0, Qt.AlignBottom)
        head.setFixedHeight(max(self.tabs.sizeHint().height(), self.title.sizeHint().height()))
        bxl.addWidget(head)

        self.pages = QStackedWidget()
        from .texts import TextsPanel
        self.texts = TextsPanel(self)             # the texts above, the chosen text's lines below
        self.pages.addWidget(self.texts.page)
        t = self.table = UtteranceTable(self)
        self.pages.addWidget(t)
        bxl.addWidget(self.pages, 1)

        self.autoplay = QCheckBox("Auto-play token soundfile")      # the same option as the main window's
        self.autoplay.setToolTip("Play an utterance's recording when you click it, and when the "
                                 "utterance dialogue opens on it")
        self.autoplay.setChecked(main.autoplay.isChecked())
        self.autoplay.toggled.connect(self._autoplay_toggled)
        main.autoplay.toggled.connect(self._main_autoplay)
        opts = QHBoxLayout()
        opts.setContentsMargins(4, 0, 0, 0)
        opts.addWidget(self.autoplay)
        opts.addStretch(1)
        bxl.addLayout(opts)
        normal = QFont(box.font())
        normal.setBold(False)
        for w in (self.tabs, self.pages, self.autoplay):
            w.setFont(normal)
        split.addWidget(box)

        self.options = QStackedWidget()
        self.options.addWidget(self.texts.bar)
        self.options.addWidget(self._utterances_bar())
        split.addWidget(self.options)
        split.setSizes([600, 150])
        split.setCollapsible(0, False)

        t.space_plays = True
        t.rowActivated.connect(lambda row: self.edit(row))
        t.deleteRequested.connect(self.delete)
        t.playRequested.connect(self.play)
        t.contextRequested.connect(self._menu)
        t.filesDropped.connect(self.import_files)
        t.filtersChanged.connect(self._update_count)
        t.clicked.connect(lambda *_: self.autoplay.isChecked() and self.play())
        t.model_.edited.connect(self._edited)
        self.search.textChanged.connect(lambda text: t.proxy.set_search(text))
        from PySide6.QtGui import QShortcut
        QShortcut(QKeySequence("Ctrl+Space"), self, self._play_key)       # an utterance, or a text's line
        QShortcut(QKeySequence("Ctrl+Shift+Space"), self, self.play_pitch)    # as in All data

        for a in (self.doc.undo.createUndoAction(self, "Undo"), self.doc.undo.createRedoAction(self, "Redo")):
            self.addAction(a)
        self.actions()[0].setShortcut(QKeySequence.Undo)
        self.actions()[1].setShortcut(QKeySequence.Redo)

        self.tabs.currentChanged.connect(self._tab_changed)
        self.doc.changed.connect(self.refresh)
        self.doc.settingsChanged.connect(self._settings_changed)
        self._setup_columns()
        self.refresh()
        self.tabs.setCurrentIndex(TEXTS)           # it always opens on Texts (Josh, 18 October)
        self._tab_changed(TEXTS)
        self._restyle()
        from . import winstate
        winstate.keep(self, self.main.prefs, "window/utterances")   # size, place and splitters, as adjusted

    @property
    def db(self):
        return self.doc.db

    # ---- building ----------------------------------------------------
    def _utterances_bar(self) -> QWidget:
        """The options panel under the grid, like All data's: the buttons, the quick search, the count."""
        from .main_window import tool             # the same buttons as the main window's
        bar, bl = self.main._bar()
        self.main._row(bl, tool("Add", "add", self.add, "Add an utterance (pick its category, then record it)"),
                       tool("Import…", None, self.import_dialog,
                            "Import WAV files as utterances (they can also be dragged onto the grid). They "
                            "are copied into Soundfiles\\Utterances; the originals stay as they are."),
                       tool("Delete", "delete", self.delete, "Delete the selected utterance (Delete)"),
                       tool("Edit", "edit", self.edit, "Edit the selected utterance (Enter)"),
                       tool("Play", "play", self.play, "Play the selected utterance (Ctrl+Space)"),
                       tool("Configure columns", "gear-columns", self.configure_columns),
                       tool("Clear all filters", "reset-filters", self.clear_filters))
        self.search = QLineEdit()
        self.search.setPlaceholderText("quick search of the visible columns")
        self.search.setClearButtonEnabled(True)
        bl.addWidget(self.search)
        self.count = QLabel()
        bl.addWidget(self.count)
        self.hint = QLabel("Drop WAV files on the grid to add them as utterances.")
        bl.addWidget(self.hint)
        bl.addStretch(1)
        return bar

    def _main_autoplay(self, on: bool):
        if self.autoplay.isChecked() != bool(on):
            self.autoplay.setChecked(bool(on))

    def _autoplay_toggled(self, on: bool):
        if self.main.autoplay.isChecked() != bool(on):     # one option, in both windows
            self.main.autoplay.setChecked(bool(on))

    # ---- columns -----------------------------------------------------
    def _columns(self) -> list[Column]:
        db = self.db
        s = db.settings
        edit = lambda row, text: None
        cats = lambda: [mx_item(c) for c in s.categories(UTTERANCES)]

        def lemmas_text(u):
            return ", ".join(f"{e.ref} {db.lemma(e)}".strip() for e in db.linked_lemmas(u))

        cols = [
            Column("ref", "Reference", lambda u: u.ref,
                   color=lambda u: theme.colour("error") if self._flagged(u) else None,
                   tooltip=lambda u: pull.describe(self.checks[u.id]) + "\nRight-click → Pull from source"
                   if self._flagged(u) else None),
            Column("category", "Category", lambda u: category_title(db, u.ref), closed=True, tree=cats),
            Column("label", "File label", lambda u: u.label, edit=edit,
                   tooltip=lambda u: "Part of the recording's file name; changing it renames the recording"),
            Column("tags", "Tags", lambda u: list(u.token.tags), closed=True, multi=True, kind="chips",
                   tree=lambda: [mx_group(g) for g in s.tags.groups],
                   tooltip=lambda u: db.settings.tags.tag_tip(u.token.tags, "") or None),
            Column("drawing", "Pitch drawing", lambda u: u.token.get("Pitch"), kind="drawing",
                   tooltip=lambda u: f"Pitch: {p}" if (p := u.token.get("Pitch")) else None),
        ]
        for f in s.token_fields:
            cols.append(Column(
                "f:" + f.name, f.title,
                lambda u, n=f.name, ml=f.multilingual: u.token.get(n, s.primary_gloss if ml else None),
                closed=f.closed, tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                ipa=f.role in ("phonetic", "phonemic"), edit=edit))
            if f.multilingual:                 # second languages: in Configure columns, not shown by default
                for lang in [x for x in s.gloss_languages if x != s.primary_gloss]:
                    cols.append(Column(f"f:{f.name}:{lang}", f"{f.title} ({lang})",
                                       lambda u, n=f.name, l=lang: u.token.get(n, l), edit=edit))
        folder = storage.utterance_folder(db)
        cols += [
            Column("lemmas", "Lemmas", lemmas_text, ipa=True,
                   tooltip=lambda u: "Linked by hand in the utterance dialogue" if u.lemmas else None),
            Column("speaker", "Speaker", lambda u: u.token.speaker),
            Column("date", "Date", lambda u: u.token.collected),
            Column("file", "Soundfile", lambda u: u.token.file if u.token.file in self.sound_files else "",
                   blank_labels=("Missing", "Present"), flag=lambda u: u.token.rerecord, flag_label="Rerecord",
                   display=lambda u: u.token.file or db.expected_filename(u, u.token),
                   color=lambda u: theme.colour("dim") if not u.token.file else
                   (theme.colour("error") if (u.token.file not in self.sound_files or
                                              u.token.file != db.expected_filename(u, u.token)) else None),
                   tooltip=lambda u: ("Not recorded yet" if not u.token.file else
                                      f"{u.token.file} isn't in Soundfiles\\Utterances"
                                      if u.token.file not in self.sound_files else
                                      f"Recorded as {u.token.file}\nExpected: {db.expected_filename(u, u.token)}"
                                      f"\n{QDir.toNativeSeparators(str(folder / u.token.file))}")),
            Column("source", "Source", self._source_value, display=self._source_display,
                   flag=self._flagged, flag_label="Changed in the TextGrid",
                   color=lambda u: theme.colour("error") if self._flagged(u) else None,
                   tooltip=self._source_tooltip),
        ]
        return cols

    # ---- clipped utterances (Pull) ---------------------------------------
    def _flagged(self, u) -> bool:
        c = self.checks.get(u.id)
        return c is not None and c.flagged

    def _source_value(self, u) -> str:
        c = self.checks.get(u.id)
        if c is None:
            return ""
        from .pull_dialog import status_label
        return f"{c.text.ref if c.text else '(deleted text)'} – {status_label(c)}"

    def _source_display(self, u) -> str:
        c = self.checks.get(u.id)
        if c is None:
            return ""
        from .pull_dialog import status_label, times
        where = f"{c.text.ref} {times(u.source.start, u.source.end)}" if c.text else "(deleted text)"
        label = status_label(c)
        return where if label == "the same" else f"{where} – {label}"

    def _source_tooltip(self, u):
        c = self.checks.get(u.id)
        if c is None:
            return None
        parts = [pull.describe(c)] if c.flagged or not c.edited else []
        if c.edited:
            parts.append(pull.describe_edits(c))
        return "\n".join(parts)

    def recheck(self) -> bool:
        """Check the clipped utterances against their TextGrids again; True if anything changed."""
        before = {k: (c.status, c.moved, c.edited) for k, c in self.checks.items()}
        self.checks = pull.check_all(self.db, self.doc.text_buffers)
        return before != {k: (c.status, c.moved, c.edited) for k, c in self.checks.items()}

    def selected(self) -> list:
        """The selected utterances (or the current one)."""
        rows = sorted({self.table.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        out = [self.table.model_.rows[r] for r in rows]
        if not out and self.table.current_row() is not None:
            out = [self.table.current_row()]
        return out

    def pull_selected(self):
        from .pull_dialog import pull_utterances
        self.recheck()
        checks = [self.checks[u.id] for u in self.selected() if u.id in self.checks]
        if pull_utterances(self.main, self, checks):
            self.refresh()

    def push_selected(self):
        from .pull_dialog import push_utterances
        self.recheck()
        checks = [self.checks[u.id] for u in self.selected() if u.id in self.checks]
        if push_utterances(self.main, self, checks):
            self.refresh()

    def unlink_selected(self):
        from .pull_dialog import unlink_utterances
        self.recheck()
        checks = [self.checks[u.id] for u in self.selected() if u.id in self.checks]
        if unlink_utterances(self.main, self, checks):
            self.refresh()

    def changeEvent(self, event):
        """Back from Praat: the TextGrids may have changed."""
        super().changeEvent(event)
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.ActivationChange and self.isActiveWindow() and self.db.utterances:
            if self.recheck():
                self.table.set_rows(list(self.db.utterances))
            if self.tabs.currentIndex() == TEXTS and hasattr(self, "texts"):
                self.texts.lines_changed()

    def _default_keys(self) -> list[str]:
        keys = ["ref", "label", "tags", "drawing"]
        keys += ["f:" + f.name for f in self.db.settings.token_fields]
        return keys + ["lemmas", "speaker", "date", "file", "source"]

    def _setup_columns(self):
        db = self.db
        cols = self._columns()
        saved = self.main.prefs.get_list("columns/utterances")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_keys()
        self.table.set_columns(cols, keys)
        self.table.set_delegate("tags", ChipsDelegate(
            lambda u: mx.chips(db, u.token.tags) if u is not None else [], self.table, empty=""))
        self.table.set_delegate("drawing", DrawingDelegate(
            lambda: (db.settings.pitch_low, db.settings.pitch_high), self.table))
        for c in self.table.model_.columns:
            if c.closed and c.edit and c.tree and not c.multi:
                self.table.set_delegate(c.key, ListEditDelegate(
                    lambda c=c: [i.name for top in c.tree() for i in top.walk()], self.table))
        tr = db.settings.token_field("translation")
        if tr is not None and db.settings.primary_gloss == spelling.LANG:   # underlines, as in All data
            self.table.set_delegate("f:" + tr.name, SpellDelegate(self.main.speller, self.table))

    def configure_columns(self):
        cols = self._columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.table.visible_keys())
        if dlg.exec():
            self.main.prefs.set_list("columns/utterances", dlg.chosen())
            self._setup_columns()
            self.refresh()

    def clear_filters(self):
        self.table.clear_filters()
        self.search.clear()

    # ---- refreshing ---------------------------------------------------
    def refresh(self):
        try:
            self.sound_files, self.cloud_files = storage.scan_sound_folder(storage.utterance_folder(self.db))
        except Exception:
            self.sound_files, self.cloud_files = set(), set()
        self.checks = pull.check_all(self.db, self.doc.text_buffers)
        self.table.set_rows(list(self.db.utterances))
        self._update_count()
        if hasattr(self, "texts"):
            self.texts.refresh()

    def _settings_changed(self):
        self._setup_columns()
        self.texts.settings_changed()
        self.refresh()

    def _update_count(self):
        n, shown = len(self.db.utterances), self.table.proxy.rowCount()
        self.count.setText(f"{shown} of {n} utterance{'s' if n != 1 else ''} shown")   # as All data's

    def _tab_changed(self, i):
        self.pages.setCurrentIndex(i)
        self.options.setCurrentIndex(i)

    def _play_key(self):
        if self.tabs.currentIndex() == TEXTS:
            self.texts.play_line()
        else:
            self.play()

    def select_text(self, text):
        """Show a text (from the notebook)."""
        self.tabs.setCurrentIndex(TEXTS)
        self.texts.select(text)

    def select(self, u: Utterance):
        """Show an utterance (from a notebook link)."""
        self.tabs.setCurrentIndex(UTTERANCES_TAB)
        if u not in self.table.visible_rows():
            self.clear_filters()
        self.table.select_row(u)

    # ---- categories ----------------------------------------------------
    def _ask_category(self, title: str, current: str = "") -> str:
        """An utterance category's letter, or "" if cancelled."""
        cats = self.db.settings.categories(UTTERANCES)
        if not cats:
            QMessageBox.information(self, title, "There are no utterance categories. Add one in Edit → "
                                    "Lists → Reference categories.")
            return ""
        labels = [f"{c.letter}  {c.name}" for c in cats]
        start = next((i for i, c in enumerate(cats) if c.letter == current), 0)
        text, ok = QInputDialog.getItem(self, title, "Category:", labels, start, False)
        if not ok:
            return ""
        return cats[labels.index(text)].letter

    # ---- adding --------------------------------------------------------
    def add(self):
        letter = self._ask_category("Add utterance")
        if not letter:
            return
        ref = self.db.suggest_utterance_reference(letter)
        u = self.db.new_utterance(ref, "", self.main.session_speaker(), self.main.session_date())
        slots = self._slots()
        slots.append(Slot(u, None, explicit=True))
        self._open(slots, len(slots) - 1)

    def import_dialog(self):
        start = str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(self, "Import recordings as utterances", start,
                                                "WAV recordings (*.wav *.WAV)")
        if paths:
            self.import_files(paths)

    def import_files(self, paths) -> list[Utterance]:
        """WAV files become utterances (one undo step). Each is copied into Soundfiles/Utterances
        under its utterance's name, with the file's name as its label; the original stays."""
        wavs = [Path(p) for p in paths if Path(p).suffix.lower() == ".wav" and Path(p).is_file()]
        if not wavs:
            QMessageBox.information(self, "Import", "Only WAV recordings can be imported.")
            return []
        if not self.db.path:
            QMessageBox.information(self, "Import", "Save the database first: the recordings go in the "
                                    "Soundfiles folder next to it.")
            return []
        letter = self._ask_category(f"Import {len(wavs)} recording{'s' if len(wavs) != 1 else ''}")
        if not letter:
            return []
        folder = storage.utterance_folder(self.db)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Import", f"Couldn't make {folder}: {exc}")
            return []
        digits = self.db.settings.ref_digits
        number = int(self.db.suggest_utterance_reference(letter)[len(letter):])
        speaker, date = self.main.session_speaker(), self.main.session_date()
        items, renames, problems = [], [], []
        for w in wavs:
            lines = self._grid_lines(w)           # a TextGrid beside it fills in the fields
            choice = self._ask_lines(w, lines) if len(lines) > 1 else ("one", 0) if lines else ("none", None)
            if choice is None:
                continue
            if choice[0] == "text":               # several lines: added as a text instead
                t = self._as_text(w, problems)
                if t is not None:
                    items.append(t[0])
                    renames += t[1]
                continue
            ref = f"{letter}{number:0{digits}d}"
            u = self.db.new_utterance(ref, clean_label(w.stem), speaker, date)
            if choice[0] in ("one", "join"):
                picked = [lines[choice[1]]] if choice[0] == "one" else lines
                self._fill_from_lines(u, picked)
            name = self.db.expected_filename(u, u.token)
            dst = folder / name
            here = storage.in_folder(w, folder)   # already in Soundfiles/Utterances: renamed, not copied
            if dst.exists() and not (here and storage.same_file(w, dst)):
                problems.append(f"{w.name}: {name} is already in Soundfiles\\Utterances")
                continue
            try:
                if not here:
                    shutil.copy2(w, dst)
                elif w.name != name:
                    w.rename(dst)
            except OSError as exc:
                problems.append(f"{w.name}: {exc}")
                continue
            number += 1
            u.token.file = name
            if not here:
                renames.append((self.doc.hold_recording(dst), dst))   # undo moves the copy aside
            elif w.name != name:
                renames.append((w, dst))          # undo gives it its old name back
            items.append(u)
        if items:
            n = len(items)
            self.doc.add_many(f"Import {n} recording{'s' if n != 1 else ''}", items, renames)
            self.table.select_row(items[0])
            items = [u for u in items if isinstance(u, Utterance)]
            if not items:
                return []
        if problems:
            QMessageBox.warning(self, "Import", "Not imported:\n\n" + "\n".join(problems[:30]))
        elif items:
            self.main.statusBar().showMessage(
                f"Imported {len(items)} recording(s) as {items[0].ref}"
                + (f"–{items[-1].ref}" if len(items) > 1 else "") + ".", 8000)
        return items

    # ---- a TextGrid beside an imported recording -------------------------
    @staticmethod
    def _grid_beside(wav: Path) -> Path | None:
        for ext in (".TextGrid", ".textgrid", ".TEXTGRID"):
            if wav.with_suffix(ext).exists():
                return wav.with_suffix(ext)
        return None

    def _grid_lines(self, wav: Path) -> list:
        from .. import textgrid as tgmod
        grid = self._grid_beside(wav)
        if grid is None:
            return []
        try:
            return tgmod.read_lines(grid, self.db.settings.tier_mapping, self.main.session_speaker())
        except tgmod.TextGridError:
            return []

    def _ask_lines(self, wav: Path, lines) -> tuple | None:
        """A TextGrid with several lines beside a recording: join them, pick one, or add the
        recording as a text instead. None: skip the file."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Import")
        box.setText(f"{wav.name} has a TextGrid with {len(lines)} lines. An utterance is one line.")
        box.setInformativeText("Join the lines into one utterance, pick one of them, or add the recording "
                               "as a text (its lines can then be clipped as utterances one by one)?")
        join = box.addButton("Join the lines", QMessageBox.AcceptRole)
        pick = box.addButton("Pick one…", QMessageBox.ActionRole)
        text = box.addButton("Add as a text", QMessageBox.ActionRole)
        box.addButton("Skip this file", QMessageBox.RejectRole)
        box.exec()
        hit = box.clickedButton()
        if hit is join:
            return ("join", None)
        if hit is text:
            return ("text", None)
        if hit is pick:
            from .texts import clock
            labels = [f"{clock(l.start)}  {' · '.join(v for v in l.values.values())}"[:120] for l in lines]
            choice, ok = QInputDialog.getItem(self, "Import", "Which line?", labels, 0, False)
            return ("one", labels.index(choice)) if ok else None
        return None

    def _fill_from_lines(self, u: Utterance, lines):
        s = self.db.settings
        values: dict[str, str] = {}
        for ln in lines:
            for key, text in ln.values.items():
                values[key] = (values[key] + " " + text) if values.get(key) else text
        for key, text in values.items():
            name, _, lang = key.partition(":")
            f = s.token_field(name)
            if f is not None:
                u.token.set(name, text, (lang or s.primary_gloss) if f.multilingual else None, f.multilingual)
        if lines and lines[0].speaker:
            u.token.speaker = lines[0].speaker

    def _as_text(self, wav: Path, problems) -> tuple | None:
        """The recording (and its TextGrid) added as a text: (text, renames) or None."""
        from ..model import TEXTS, Text
        cats = self.db.settings.categories(TEXTS)
        if not cats:
            problems.append(f"{wav.name}: there is no text category to add it to")
            return None
        t = Text(ref=self.db.suggest_utterance_reference(cats[0].letter), file_label=clean_label(wav.stem),
                 date=self.main.session_date(), participants=list(self.main.session_keys().get("participants", [])))
        f = self.db.settings.text_field("title")
        if f is not None:
            t.set(f.name, wav.stem.replace("_", " "))
        renames = self.texts._copy_in(t, wav, self._grid_beside(wav))
        if renames is None:
            problems.append(f"{wav.name}: not added as a text")
            return None
        return t, renames

    # ---- editing -------------------------------------------------------
    def _slots(self) -> list[Slot]:
        return [Slot(u, 0) for u in self.table.visible_rows()]

    def _open(self, slots, index):
        if not slots:
            return
        self.main.dialog_autoplay = self.main.autoplay.isChecked()
        UtteranceDialog(self.main, slots, index, self).exec()
        self.refresh()

    def edit(self, row=None):
        u = row if isinstance(row, Utterance) else self.table.current_row()
        if u is None:
            return
        slots = self._slots()
        idx = next((k for k, s in enumerate(slots) if s.entry is u), None)
        if idx is None:
            slots, idx = [Slot(u, 0)], 0
        self._open(slots, idx)

    def _edited(self, u, key, text):
        """An in-place edit: a token field, or the file label (which renames the recording)."""
        s = self.db.settings
        text = text.strip()
        if key == "label":
            text = clean_label(text, 200)
            self.set_label(u, text)
            return
        name, _, lang = key[2:].partition(":")      # f:Translation, or f:Translation:ar
        f = s.token_field(name)
        if f is None:
            return
        if f.role == "pitch":
            text = pitchmod.normalise(text)
        if f.closed and text and text not in f.all_values():
            f.add_value(text)
            self.doc.settings_changed()

        def change(x):
            x.token.set(name, text, (lang or s.primary_gloss) if f.multilingual else None, f.multilingual)
        self.doc.edit_entry(u, change, f"Edit {f.title}" + (f" ({lang})" if lang else ""))

    def _renamed(self, u: Utterance, after: Utterance) -> list:
        """Rename the recording to after's expected name (if automatic). Returns the renames."""
        t = u.token
        if not (t.file and self.db.settings.auto_update_names):
            return []
        folder = storage.utterance_folder(self.db)
        new = self.db.expected_filename(after, after.token)
        src, dst = folder / t.file, folder / new
        if new == t.file or not src.exists():
            return []
        if dst.exists() and not storage.same_file(src, dst):
            QMessageBox.warning(self, "File name", f"Can't rename {t.file}: {new} already exists.")
            return []
        try:
            src.rename(dst)
        except OSError as exc:
            QMessageBox.warning(self, "File name", f"Couldn't rename {t.file}: {exc}")
            return []
        after.token.file = new
        return [(src, dst)]

    def set_label(self, u: Utterance, label: str):
        if label == u.label:
            return
        after = u.copy()
        after.file_gloss = label
        renames = self._renamed(u, after)

        def change(x, label=label, file=after.token.file):
            x.file_gloss = label
            x.token.file = file
        self.doc.edit_entry(u, change, f"Rename {u.ref}", renames=renames)

    def move_category(self, u: Utterance | None = None):
        """Another category: a new reference, so the recording is renamed (asked first)."""
        u = u or self.table.current_row()
        if u is None:
            return
        old = self.db.settings.category(u.ref)
        letter = self._ask_category(f"Move {u.ref} to another category", old.letter if old else "")
        if not letter or (old and letter == old.letter):
            return
        ref = self.db.suggest_utterance_reference(letter)
        what = f" and its recording renamed to match" if u.token.file else ""
        if QMessageBox.question(self, "Move utterance", f"Move {u.ref} to {category_title(self.db, ref)}? "
                                f"Its reference becomes {ref}{what}.") != QMessageBox.Yes:
            return
        after = u.copy()
        after.ref = ref
        renames = self._renamed(u, after)

        def change(x, ref=ref, file=after.token.file):
            x.ref = ref
            x.token.file = file
        self.doc.edit_entry(u, change, f"Move {u.ref} to {ref}", renames=renames)
        self.table.select_row(u)

    def delete(self):
        u = self.table.current_row()
        if u is None:
            return
        t = u.token
        prefs = self.main.prefs
        folder = storage.utterance_folder(self.db)
        with_file = bool(t.file) and prefs.delete_recordings_with_tokens and (folder / t.file).exists()
        msg = f"Delete the utterance {u.ref}" + (f" “{u.label}”" if u.label else "") + "?"
        if with_file:
            msg += (f"\nIts recording ({t.file}) goes to the Recycle Bin when the database is closed; "
                    "until then, undo brings it back.")
        if QMessageBox.question(self, "Delete utterance", msg) != QMessageBox.Yes:
            return
        renames = []
        if with_file:
            self.main.player.stop()
            path = folder / t.file
            held = self.doc.hold_recording(path)
            try:
                path.rename(held)
                renames.append((path, held))
            except OSError as exc:
                QMessageBox.warning(self, "Delete utterance", f"Couldn't move {t.file} aside: {exc}. The "
                                    "utterance is deleted; its recording stays in Soundfiles\\Utterances.")
        self.doc.delete_entry(u, renames=renames)

    def _pitch(self, u) -> str:
        f = self.db.settings.token_field("pitch")
        return u.token.get(f.name) if (u is not None and f is not None) else ""

    def play_pitch(self):
        """Play the selected utterance's pitch in the voice chosen in Settings → Pitch."""
        u = self.table.current_row()
        if u is None:
            return
        self.main.play_pitch(self._pitch(u))

    def play(self):
        u = self.table.current_row()
        if u is None or not u.token.file:
            return
        try:
            self.main.player.play([storage.utterance_folder(self.db) / u.token.file])
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play", str(exc))

    def _menu(self, row, pos):
        if row is not None:
            self.table.select_row(row)
        m = QMenu(self)
        items = [("Add", "add", self.add, True), ("Import…", None, self.import_dialog, True),
                 ("Edit", "edit", self.edit, row is not None),
                 ("Play", "play", self.play, row is not None and bool(row.token.file)),
                 ("Play pitch", "play-pitch", self.play_pitch, bool(self._pitch(row))),
                 ("Move to another category…", None, self.move_category, row is not None),
                 ("Delete", "delete", self.delete, row is not None)]
        if row is not None and row.source is not None:
            c = self.checks.get(row.id)
            items[-1:-1] = [("Pull from source…", None, self.pull_selected, c is not None and c.pullable),
                            ("Push to source…", None, self.push_selected, c is not None and c.pushable),
                            ("Unlink from the text…", None, self.unlink_selected, True)]
        if row is not None and hasattr(self.main, "elicit_menu_item"):   # ɛλicit, before Delete
            items[-1:-1] = [self.main.elicit_menu_item(row.token)]
        for text, name, fn, on in items:
            if name is not None and not isinstance(name, str):              # an icon already drawn
                a = m.addAction(name, text)
            else:
                a = m.addAction(icon(name, 16), text) if name else m.addAction(text)
            a.setEnabled(on)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    # ---- style and closing --------------------------------------------
    def _restyle(self):
        a = theme.accent()
        self.title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        self.tabs.setStyleSheet("QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
                                f"QTabBar::tab:selected {{ background: {a.name()}; "
                                f"color: {theme.text_on(a).name()}; }}")
        for lbl in (self.count, self.hint, self.texts.count, self.texts.text_count):
            lbl.setStyleSheet(f"color: {theme.muted()};")
        for t in (self.table, self.texts.table, self.texts.lines):
            theme.as_data(t)
        self.texts.restyle_icons()

    def done(self, result):
        super().done(result)

    def closeEvent(self, event):
        try:
            self.doc.changed.disconnect(self.refresh)
            self.doc.settingsChanged.disconnect(self._settings_changed)
            self.main.autoplay.toggled.disconnect(self._main_autoplay)
        except (RuntimeError, TypeError):
            pass
        if getattr(self.main, "utterances_window", None) is self:
            self.main.utterances_window = None
        super().closeEvent(event)


def mx_item(c):
    from ..model import ListItem
    return ListItem(c.name)


def mx_group(g):
    from ..model import ListItem
    return ListItem(g.name, [ListItem(t.name) for t in g.tags] + [mx_group(x) for x in g.groups])


# --------------------------------------------------------------------------
# The utterance dialogue
# --------------------------------------------------------------------------

class UtteranceDialog(TokenDialog):
    """The token dialogue for an utterance: a header with its reference, category and file label;
    the token fields and recording as for tokens; the utterance-only tag groups and the groups
    with no "usual for" hint first; a Lemmas box; Back and Next through the Utterances grid."""
    MULTI_TOKENS = False      # one utterance at a time

    def __init__(self, main, slots: list[Slot], index: int, parent=None):
        self.lemma_ids: list[str] = []
        super().__init__(main, slots, index, parent)
        self.setWindowTitle("Utterance")

    # ---- building --------------------------------------------------------
    def _build(self):
        super()._build()
        outer = self.layout()
        outer.removeWidget(self.header)
        head = QHBoxLayout()
        head.addWidget(self.header)
        from .dialogs import NoForbidden
        self.label_edit = NoForbidden()
        self.label_edit.setFont(ipa_font(14))
        self.label_edit.setPlaceholderText("file label, e.g. hare ran")
        self.label_edit.setToolTip("A short label for the recording's file name. Changing it renames the "
                                   "recording when you leave the utterance.")
        self.label_edit.textChanged.connect(self._fields_changed)
        head.addWidget(self.label_edit, 1)
        outer.insertLayout(0, head)

        box = QGroupBox("Lemmas")
        bl = QVBoxLayout(box)
        self.lemma_holder = QWidget()
        self.lemma_flow = FlowLayout(self.lemma_holder, spacing=6)
        bl.addWidget(self.lemma_holder)
        self.lemma_find = QLineEdit()
        self.lemma_find.setFont(ipa_font(self.main.prefs.ipa_size + 1))
        self.lemma_find.setPlaceholderText("type a reference, form or gloss to link a lemma")
        self.lemma_find.setToolTip("Links this utterance to lemmas, by hand. Pick from the list that "
                                   "appears; click a lemma's chip to remove the link.")
        self._choices: dict[str, str] = {}
        self.completer = QCompleter(self)
        self.completer.setModel(QStringListModel(self.completer))
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setMaxVisibleItems(12)
        self.lemma_find.setCompleter(self.completer)
        self.completer.activated.connect(self._lemma_chosen)
        self.lemma_find.returnPressed.connect(lambda: self._lemma_chosen(self.lemma_find.text()))
        bl.addWidget(self.lemma_find)
        outer.insertWidget(2, box)
        self.source_box = QGroupBox("Source")     # for an utterance clipped from a text's line
        sl = QHBoxLayout(self.source_box)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        sl.addWidget(self.source_label, 1)
        self.context_btn = QPushButton("Play in context")
        self.context_btn.setToolTip("Play the line in the text's recording, with a few seconds either side")
        self.context_btn.clicked.connect(lambda *_: self._play_context())
        sl.addWidget(self.context_btn)
        self.show_text_btn = QPushButton("Show the text")
        self.show_text_btn.setToolTip("Show the text and its lines in the Texts tab")
        self.show_text_btn.clicked.connect(lambda *_: self._show_text())
        sl.addWidget(self.show_text_btn)
        self.pull_btn = QPushButton("Pull from source…")
        self.pull_btn.setToolTip("Take the line as it is in the TextGrid now")
        self.pull_btn.clicked.connect(lambda *_: self._pull())
        sl.addWidget(self.pull_btn)
        self.source_push_btn = QPushButton("Push to source…")   # (push_btn is Push to question)
        self.source_push_btn.setToolTip("Write the fields edited here into the text's TextGrid")
        self.source_push_btn.clicked.connect(lambda *_: self._push())
        sl.addWidget(self.source_push_btn)
        outer.insertWidget(3, self.source_box)
        for ed in (self.label_edit, self.lemma_find):     # Ctrl+Space plays, never types a space
            ed.installEventFilter(self)
        self.show_all_btn.setToolTip("Shown first: the tag groups for utterances only, the groups with "
                                     "no “usual for” hint, and any group the utterance has a tag in")

    def _fill_choices(self):
        db = self.db
        self._choices = {}
        for e in db.entries:
            text = " ".join(x for x in (e.ref, db.lemma(e), meaning(db.gloss(e))) if x)
            self._choices[text] = e.id
        self.completer.model().setStringList(list(self._choices))

    def key_fields(self) -> list:
        return [*super().key_fields(), self.label_edit, self.lemma_find]

    # ---- what differs from a token ------------------------------------------
    def _new_token(self, sl: Slot) -> Token:
        return Token(speaker=self.main.session_speaker(), collected=self.main.session_date())

    def _show_header(self, u):
        cat = category_title(self.db, u.ref)
        self.header.setText(f"{u.ref}  ·  {cat}  ·" if cat else f"{u.ref}  ·")

    def _position_text(self) -> str:
        u = self.slot.entry
        state = "new utterance" if u not in self.db.utterances else "utterance"
        return f"{self.pos + 1} / {len(self.slots)}  ·  {state}"

    def _tag_args(self) -> dict:
        return {"classes": None, "utterance": True}

    def _folder(self) -> Path:
        return storage.utterance_folder(self.db)

    def _update_unusual(self):
        self.unusual_note.hide()                  # utterances have no word class

    def _update_suggestion(self):
        self.suggestion = None                    # suggestions are learned from lemmas' glosses
        if self.translation is not None:
            from .table import show_suggestion
            show_suggestion(self.translation, "")
            self.translation.setToolTip("")

    def _probe(self) -> Utterance:
        u = self.slot.entry.copy()
        u.file_gloss = nfc(self.label_edit.text().strip()) if hasattr(self, "label_edit") else u.file_gloss
        u.tokens = [self.token if self.token is not None else Token()]
        return u

    def _expected(self) -> str:
        p = self._probe()
        return self.db.expected_filename(p, p.token)

    def _clashes(self, tags=None) -> list:
        """Other utterances whose recording has, or would have, this one's file name."""
        name = self._expected().lower()
        me = self.slot.entry
        return [(u, u.token) for u in self.db.utterances if u is not me and
                ((u.token.file and u.token.file.lower() == name) or
                 self.db.expected_filename(u, u.token).lower() == name)]

    def _offer_example(self, recording: bool) -> bool:
        other = self._clashes()[0][0]
        QMessageBox.warning(self, "Same recording name", f"{other.ref} already has the file name "
                            f"{self._expected()}. Change this utterance's file label first.")
        return False

    # ---- loading and saving --------------------------------------------
    def _load(self):
        u = self.slot.entry
        self.lemma_ids = list(u.lemmas)
        if hasattr(self, "label_edit"):
            self.label_edit.blockSignals(True)
            self.label_edit.setText(u.label)
            self.label_edit.blockSignals(False)
        super()._load()
        self._fill_choices()
        self._show_lemmas()
        self._show_source()
        self._refresh_name()

    def _source_text(self):
        u = self.slot.entry
        return self.db.text_by_id(u.source.text) if u.source is not None else None

    def _show_source(self):
        u = self.slot.entry
        self.source_box.setVisible(u.source is not None)
        if u.source is None:
            return
        from .texts import clock
        t = self._source_text()
        when = f"{clock(u.source.start)}–{clock(u.source.end)}"
        if t is None:
            self.source_label.setText(f"Clipped from a text that no longer exists ({when}).")
        else:
            self.source_label.setText(f"Clipped from {t.ref} {self.db.text_title(t)}, {when}")
        c = pull.check(self.db, u, self.main.doc.text_buffers)
        if c is not None and c.flagged:
            self.source_label.setText(self.source_label.text().replace("<", "&lt;") +
                                      f"<br><span style='color:{theme.colour('error').name()}'>"
                                      f"{pull.describe(c)}</span>")
        if c is not None and c.edited:
            self.source_label.setText(self.source_label.text() + "<br>" + pull.describe_edits(c))
        self.pull_btn.setVisible(c is not None and c.pullable)
        self.source_push_btn.setVisible(c is not None and c.pushable)
        self.context_btn.setEnabled(t is not None and bool(t.file))
        self.show_text_btn.setEnabled(t is not None)

    def _play_context(self):
        from .texts import CONTEXT
        t = self._source_text()
        if t is None or not t.file:
            return
        wav = storage.text_folder(self.db) / t.file
        src = self.slot.entry.source
        try:
            samples, rate = audio.read_segment(wav, src.start - CONTEXT, src.end + CONTEXT)
            self.main.player.play_samples(samples, rate)
        except Exception as exc:
            QMessageBox.warning(self, "Play", f"Couldn't play {wav.name}: {exc}")

    def _pull(self):
        from .pull_dialog import pull_utterances
        if not self._commit():                    # what's typed here is kept first
            return
        c = pull.check(self.db, self.slot.entry, self.main.doc.text_buffers)
        if c is not None and pull_utterances(self.main, self, [c]):
            self._load()
            win = self.parent()
            if hasattr(win, "refresh"):
                win.refresh()

    def _push(self):
        from .pull_dialog import push_utterances
        if not self._commit():                    # what's typed here is what gets pushed
            return
        c = pull.check(self.db, self.slot.entry, self.main.doc.text_buffers)
        if c is not None and push_utterances(self.main, self, [c]):
            self._load()
            win = self.parent()
            if hasattr(win, "refresh"):
                win.refresh()

    def _show_text(self):
        t = self._source_text()
        win = self.parent()
        if t is not None and hasattr(win, "select_text"):
            win.select_text(t)
            win.texts.lines.clearSelection()
            src = self.slot.entry.source
            hit = next((l for l in win.texts.lines.rows
                        if abs(l.start - src.start) < 0.01 and abs(l.end - src.end) < 0.01), None)
            if hit is not None:
                win.texts.lines.select_row(hit)

    def _show_lemmas(self):
        while self.lemma_flow.count():
            item = self.lemma_flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        db = self.db
        for ident in self.lemma_ids:
            e = db.entry_by_id(ident)
            text = f"{e.ref} {db.lemma(e)}".strip() if e else "(lemma deleted)"
            b = QToolButton()
            b.setText(text + "  ✕")
            b.setFont(ipa_font(self.main.prefs.ipa_size))
            b.setToolTip((f"{e.ref} {db.lemma(e)} {meaning(db.gloss(e))}\n" if e else "") + "Click to remove the link")
            b.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 10px; padding: 2px 8px; }"
                            % theme.colour("pitch").name())
            b.clicked.connect(lambda *_, i=ident: self._remove_lemma(i))
            self.lemma_flow.addWidget(b)
        self.lemma_holder.setVisible(bool(self.lemma_ids))

    def _lemma_chosen(self, text: str):
        ident = self._choices.get(text)
        if ident is None:
            hits = [i for t, i in self._choices.items() if text and text.lower() in t.lower()]
            ident = hits[0] if len(hits) == 1 else None
        if ident is None:
            return
        if ident not in self.lemma_ids:
            self.lemma_ids.append(ident)
            self._show_lemmas()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.lemma_find.clear)

    def _remove_lemma(self, ident: str):
        if ident in self.lemma_ids:
            self.lemma_ids.remove(ident)
            self._show_lemmas()

    def _commit(self, keep_empty: bool = False, check_clash: bool = True, extras: bool = False) -> bool:
        """Save the working utterance (token, file label and lemma links) with undo."""
        self._collect()
        u = self.slot.entry
        t = self.token
        label = nfc(self.label_edit.text().strip())
        lemmas = list(self.lemma_ids)
        new = u not in self.db.utterances
        if new and not (t.has_content() or keep_empty or self.slot.explicit or label or lemmas):
            return True                           # nothing typed: nothing added
        problems = self.db.settings.tags.conflicts([x for x in t.tags if x not in self.unknown_tags])
        if problems:
            QMessageBox.warning(self, "Tags", "\n".join(problems))
            return False
        if self.db.settings.auto_update_names and t.file and t.file != self._expected():
            self._rename_file()
        renames, self._renames = self._renames, []
        token = t.copy()

        def change(x, token=token, label=label, lemmas=lemmas):
            x.tokens = [token]
            x.file_gloss = label
            x.lemmas = list(lemmas)
        if new:
            change(u)
            self.doc.add_entry(u, renames=renames)
            self.slot.index = 0
        elif self.original != t or u.file_gloss != label or u.lemmas != lemmas or renames:
            self.doc.edit_entry(u, change, f"Edit {u.ref}", renames=renames)
        self.original = u.tokens[0]
        self.token = self.original.copy()
        self.position.setText(self._position_text())
        return True
