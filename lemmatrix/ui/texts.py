# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The Texts tab of View → Texts and utterances (idea 7, stage 3), and the text dialogue.

A text (T) or song (S) is a catalogue record with a recording and its Praat TextGrid, both copied
into Soundfiles/Texts when the text is added. The lines stay in the TextGrid: the lower grid
reads them (with the tier mapping) when a text is chosen. A line can be played, opened in Praat
(the recording with its TextGrid) or clipped as an utterance: its stretch of the recording cut
into a file of its own in Soundfiles/Utterances, its text copied from the mapped tiers, and a
link back to the line kept for Pull (stage 4).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDir, QObject, QRegularExpression, QSize, Qt
from PySide6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from .. import audio, layout, lines as lmod, notebook as nbmod, storage, textgrid as tgmod
from ..model import SPEAKER_FIELD, TEXTS, ClipSource, ListItem, Text, TierMapping, TierRule, nfc, tier_base
from . import chiprow as chips, theme
from .filter_dialogs import ConfigureColumnsDialog
from .icons import icon, themed_icon
from .lines_view import ConfigureViewDialog, FieldSpec, LinesView
from .table import Column, FilterTable
from .widgets import ipa_font

CONTEXT = 2.0            # seconds of the text played either side of a line ("in context")


def clock(t: float) -> str:
    """1:05.30 for 65.3 seconds."""
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def field_choices(db, keep: tuple | None = None) -> list[tuple[str, str, str]]:
    """(label, field, lang) for what a tier can fill in: Ignore, then every token field (a
    multilingual one once per gloss language). With the pitch system hidden (idea 9) Pitch isn't
    offered for new rules, but a rule that already fills it keeps it (keep: its (field, lang))."""
    from .. import pitchview
    s = db.settings
    out = [("Ignore", "", ""), ("Speaker (code)", SPEAKER_FIELD, "")]
    for f in s.token_fields:
        if f.role == "pitch" and not pitchview.shown() and (keep is None or keep[0] != f.name):
            continue
        if f.multilingual:
            for lang in s.gloss_languages:
                out.append((f"{f.title} ({lang})", f.name, lang))
        else:
            out.append((f.title, f.name, ""))
    return out


# --------------------------------------------------------------------------
# The text dialogue
# --------------------------------------------------------------------------

class TextDialog(QDialog):
    """Add or edit a text: its record, its recording and TextGrid, and how its tiers are read."""

    def __init__(self, panel: "TextsPanel", text: Text | None = None):
        super().__init__(panel.win)
        self.panel, self.main, self.db = panel, panel.main, panel.db
        self.text = text
        s = self.db.settings
        self.setWindowTitle("Edit text" if text else "Add text")
        self.setSizeGripEnabled(True)
        self.resize(600, 720)                     # resizable; the size is remembered (done())
        self.new_wav: Path | None = None
        self.new_grid: Path | None = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)
        from .dialogs import NoForbidden
        self.category = QComboBox()
        for c in s.categories(TEXTS):
            self.category.addItem(c.label, c.letter)
        self.ref = NoForbidden(text.ref if text else "")
        if text:
            self.category.setEnabled(False)
            self.ref.setReadOnly(True)
            self.ref.setToolTip("References never change, because they're part of file names.")
        else:
            self.category.currentIndexChanged.connect(self._suggest)
        form.addRow("Category", self.category)
        form.addRow("Reference", self.ref)
        self.fields: dict[str, QWidget] = {}
        for f in s.text_fields:
            if f.closed:
                w = QComboBox()
                w.setEditable(True)
                w.addItem("")
                w.addItems(f.all_values())
                w.setCurrentText(text.get(f.name) if text else "")
                w.setToolTip("Pick from the list, or type a new value to add it to the list "
                             "(the lists are in Edit → Lists)")
            else:
                w = QLineEdit(text.get(f.name) if text else "")
                if f.role == "title":
                    w.textChanged.connect(self._title_changed)
            form.addRow(f.title, w)
            self.fields[f.name] = w
        self.label = NoForbidden(text.file_label if text else "")
        self.label.setPlaceholderText("copied from the title when the text is added")
        self.label.setToolTip("The title as it goes into the recording's and TextGrid's names. Changing "
                              "it renames both files.")
        if not text:
            self.label.setEnabled(False)
        form.addRow("Title in file names", self.label)
        self.date = QLineEdit(text.date if text else self.main.session_date())
        self.date.setPlaceholderText("YYYY-MM-DD")
        self.date.setValidator(QRegularExpressionValidator(QRegularExpression(r"(\d{4}-\d{2}-\d{2})?"),
                                                           self.date))
        form.addRow("Date", self.date)
        self.people = {}
        session = self.main.session_keys()
        for kind, title in ((chips.PARTICIPANTS, "Participants"), (chips.RESEARCHERS, "Researchers"),
                            (chips.LOCATIONS, "Locations")):
            row = chips.ChipRow(kind, lambda: self.db, compact=True)
            attr = {chips.PARTICIPANTS: "participants", chips.RESEARCHERS: "researchers",
                    chips.LOCATIONS: "locations"}[kind]
            row.set_keys(getattr(text, attr) if text else session[kind])
            form.addRow(title, row)
            self.people[attr] = row

        files = QWidget()
        fl = QFormLayout(files)
        fl.setContentsMargins(0, 8, 0, 0)
        self.wav_label = QLabel()
        self.wav_label.setWordWrap(True)
        b = QPushButton("Choose recording…")
        b.clicked.connect(lambda *_: self._choose_wav())
        row = QHBoxLayout()
        row.addWidget(self.wav_label, 1)
        row.addWidget(b)
        fl.addRow("Recording", row)
        self.grid_label = QLabel()
        self.grid_label.setWordWrap(True)
        b = QPushButton("Choose TextGrid…")
        b.clicked.connect(lambda *_: self._choose_grid())
        row = QHBoxLayout()
        row.addWidget(self.grid_label, 1)
        row.addWidget(b)
        fl.addRow("TextGrid", row)
        lay.addWidget(files)

        note = QLabel("<b>Tiers</b>: what each tier of the TextGrid fills in. The main tier's "
                      "intervals are the lines; the other tiers are matched to them by time. "
                      "A tier with no rule yet is learned for the next texts.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.tiers = QTableWidget(0, 4)
        self.tiers.setHorizontalHeaderLabels(["Tier", "Intervals", "Fills in", "Main"])
        self.tiers.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tiers.verticalHeader().setVisible(False)
        self.tiers.setSelectionMode(QAbstractItemView.NoSelection)
        lay.addWidget(self.tiers, 1)
        self.lines_note = QLabel()
        self.lines_note.setWordWrap(True)
        lay.addWidget(self.lines_note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        if not text:
            self._suggest()
        self._show_files()
        g = self.main.prefs.get_bytes("window/text")
        if g:
            self.restoreGeometry(g)

    def done(self, result):
        self.main.prefs.set_value("window/text", self.saveGeometry())
        super().done(result)

    # ---- the record ----------------------------------------------------
    def _suggest(self):
        letter = self.category.currentData()
        if letter:
            self.ref.setText(self.db.suggest_utterance_reference(letter))

    def _title_changed(self, text):
        if self.text is None:
            from .utterances import clean_label
            self.label.setText(clean_label(text))

    # ---- files ---------------------------------------------------------
    def _current_wav(self) -> Path | None:
        if self.new_wav:
            return self.new_wav
        if self.text and self.text.file:
            return storage.text_folder(self.db) / self.text.file
        return None

    def _current_grid(self) -> Path | None:
        if self.new_grid:
            return self.new_grid
        if self.text and self.text.textgrid:
            return storage.text_folder(self.db) / self.text.textgrid
        return None

    def _start_folder(self) -> str:
        """Where the file dialogues open: beside the recording chosen so far, otherwise
        Soundfiles/Texts."""
        wav = self._current_wav()
        if wav is not None and wav.parent.is_dir():
            return str(wav.parent)
        if self.db.path:
            return str(layout.existing_folder(storage.text_folder(self.db)))
        return str(Path.home())

    def _choose_wav(self):
        start = self._start_folder()
        path, _ = QFileDialog.getOpenFileName(self, "The text's recording", start, "WAV recordings (*.wav *.WAV)")
        if not path:
            return
        self.new_wav = Path(path)
        if self.new_grid is None:                 # a TextGrid of the same name beside it
            for ext in (".TextGrid", ".textgrid", ".TEXTGRID"):
                g = self.new_wav.with_suffix(ext)
                if g.exists():
                    self.new_grid = g
                    break
        title = self.fields.get(self._title_name())
        if isinstance(title, QLineEdit) and not title.text().strip():
            title.setText(self.new_wav.stem.replace("_", " "))
        self._show_files()

    def _choose_grid(self):
        start = self._start_folder()
        path, _ = QFileDialog.getOpenFileName(self, "The text's TextGrid", start, "Praat TextGrids (*.TextGrid)")
        if path:
            self.new_grid = Path(path)
            self._show_files()

    def _title_name(self) -> str:
        f = self.db.settings.text_field("title")
        return f.name if f else "Title"

    def _show_files(self):
        def show(label, path, new):
            if path is None:
                label.setText("<span style='color:%s'>none yet</span>" % theme.muted())
            else:                                 # the name only: the full path is in the tooltip
                label.setText(path.name.replace("<", "&lt;") + ("  <i>(copied in on OK)</i>" if new else ""))
                label.setToolTip(QDir.toNativeSeparators(str(path)))
        show(self.wav_label, self._current_wav(), bool(self.new_wav))
        show(self.grid_label, self._current_grid(), bool(self.new_grid))
        self._fill_tiers()

    # ---- tiers -----------------------------------------------------------
    def _mapping(self) -> TierMapping:
        return self.text.tiers if (self.text and self.text.tiers is not None) else self.db.settings.tier_mapping

    def _fill_tiers(self):
        self.tiers.setRowCount(0)
        grid = self._current_grid()
        if grid is None:
            self.lines_note.setText("No TextGrid yet: the text has no lines until one is chosen.")
            return
        try:
            infos = tgmod.tiers(grid)
        except tgmod.TextGridError as exc:
            self.lines_note.setText(f"<span style='color:{theme.colour('error').name()}'>{exc}</span>")
            return
        m = self._mapping()
        seen = set()
        for info in infos:
            base = tier_base(info.name)[0]
            if base.lower() in seen or info.kind != "intervals":
                continue
            seen.add(base.lower())
            r = self.tiers.rowCount()
            self.tiers.insertRow(r)
            it = QTableWidgetItem(base)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            rule = m.rule(base)
            if rule is None:
                it.setToolTip("No rule for this tier yet: what you choose is used for the next texts too")
                it.setForeground(theme.colour("warning"))
            self.tiers.setItem(r, 0, it)
            n = QTableWidgetItem(str(info.count))
            n.setFlags(n.flags() & ~Qt.ItemIsEditable)
            self.tiers.setItem(r, 1, n)
            combo = QComboBox()
            choices = field_choices(self.db, (rule.field, rule.lang) if rule is not None else None)
            for label, f, lang in choices:
                combo.addItem(label, (f, lang))
            if rule is not None:
                i = next((k for k, (_, f, lang) in enumerate(choices) if (f, lang) == (rule.field, rule.lang)), 0)
                combo.setCurrentIndex(i)
            combo.currentIndexChanged.connect(lambda *_: self._count_lines())
            self.tiers.setCellWidget(r, 2, combo)
            main = QCheckBox()
            main.setChecked(m.is_main(base))
            main.toggled.connect(lambda on, r=r: self._main_toggled(r, on))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(6, 0, 0, 0)
            hl.addWidget(main)
            self.tiers.setCellWidget(r, 3, holder)
        self.tiers.resizeColumnsToContents()
        self.tiers.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._count_lines()

    def _main_box(self, r) -> QCheckBox:
        return self.tiers.cellWidget(r, 3).findChild(QCheckBox)

    def _main_toggled(self, row, on):
        if on:
            for r in range(self.tiers.rowCount()):
                if r != row:
                    b = self._main_box(r)
                    b.blockSignals(True)
                    b.setChecked(False)
                    b.blockSignals(False)
        self._count_lines()

    def chosen(self) -> tuple[str, list[TierRule]]:
        """(main tier, a rule for each tier of the TextGrid) as set in the table."""
        main, rules = "", []
        for r in range(self.tiers.rowCount()):
            name = self.tiers.item(r, 0).text()
            f, lang = self.tiers.cellWidget(r, 2).currentData()
            rules.append(TierRule(name, f, lang))
            if self._main_box(r).isChecked():
                main = name
        return main, rules

    def _count_lines(self):
        grid = self._current_grid()
        if grid is None or not self.tiers.rowCount():
            return
        main, rules = self.chosen()
        if not main:
            self.lines_note.setText(f"<span style='color:{theme.colour('error').name()}'>Tick the main tier: "
                                    "its intervals are the text's lines.</span>")
            return
        try:
            n = len(tgmod.read_lines(grid, TierMapping(main, rules)))
        except tgmod.TextGridError as exc:
            self.lines_note.setText(str(exc))
            return
        self.lines_note.setText(f"{n} line{'s' if n != 1 else ''} with this mapping.")

    # ---- OK --------------------------------------------------------------
    def accept(self):
        ref = nfc(self.ref.text().strip())
        if not ref:
            QMessageBox.warning(self, "Text", "Every text needs a reference.")
            return
        if self.text is None and self.db.ref_taken(ref):
            QMessageBox.warning(self, "Text", f"The reference {ref} is already used.")
            return
        if self.tiers.rowCount() and not self.chosen()[0]:
            QMessageBox.warning(self, "Text", "Tick the main tier: its intervals are the text's lines.")
            return
        if self.new_wav is None and self.text is None:
            if QMessageBox.question(self, "Text", "Add the text without a recording? It can be chosen "
                                    "later with Edit.") != QMessageBox.Yes:
                return
        super().accept()

    def record(self) -> Text:
        """The text as set in the dialogue (files not copied yet)."""
        s = self.db.settings
        t = self.text.copy() if self.text else Text(ref=nfc(self.ref.text().strip()))
        for name, w in self.fields.items():
            value = (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()
            t.set(name, value)
            f = s.text_field(name)
            if f is not None and f.closed and value:
                f.add_value(value)
        t.date = self.date.text().strip()
        for attr, row in self.people.items():
            setattr(t, attr, list(row.keys))
        if self.text is None:
            from .utterances import clean_label
            t.file_label = clean_label(t.get(self._title_name())) or clean_label(self.new_wav.stem
                                                                                if self.new_wav else "")
        else:
            t.file_label = nfc(self.label.text().strip())
        if self.tiers.rowCount():
            main, rules = self.chosen()
            m = s.tier_mapping
            learned = False
            for r in rules:                       # tiers with no rule yet: learned for the next texts
                if m.rule(r.tier) is None:
                    m.rules.append(TierRule(r.tier, r.field, r.lang))
                    learned = True
            differs = main.lower() != m.main.lower() or any(
                (m.rule(r.tier).field, m.rule(r.tier).lang) != (r.field, r.lang) for r in rules)
            if differs:                           # this text's own mapping
                own = m.copy()
                own.main = main
                for r in rules:
                    hit = own.rule(r.tier)
                    hit.field, hit.lang = r.field, r.lang
                t.tiers = own
            else:
                t.tiers = None
            if learned:
                self.panel.doc.settings_changed()
        return t


# --------------------------------------------------------------------------
# The Texts tab
# --------------------------------------------------------------------------

class TextsPanel(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.main, self.doc = win, win.main, win.doc
        self._lines: list = []
        self._lines_for = None
        self.lines_error = ""

        page = self.page = QSplitter(Qt.Vertical)
        self.table = FilterTable()
        self.table.rowActivated.connect(lambda row: self.edit(row))
        self.table.deleteRequested.connect(self.delete)
        self.table.contextRequested.connect(self._text_menu)
        self.table.filtersChanged.connect(self._update_count)
        self.table.selectionModel().currentRowChanged.connect(lambda *a: self._show_lines())
        top = QWidget()                           # the texts, with their own buttons right under them
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        tl.addWidget(self.table, 1)
        tl.addWidget(self._texts_bar())
        page.addWidget(top)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.setSpacing(2)
        self.lines_title = QLabel()
        f = self.lines_title.font()
        f.setBold(True)
        self.lines_title.setFont(f)
        bl.addWidget(self.lines_title)
        self.lines = LinesView()                  # the lines as cells (19 October)
        self.lines.playRequested.connect(self.play_line)
        self.lines.clipActivated.connect(self._open_clip)
        self.lines.contextRequested.connect(self._line_menu)
        self.lines.countChanged.connect(self._update_count)
        self.lines.currentChanged.connect(lambda *_: self.win.autoplay.isChecked() and not self.lines.editing()
                                          and self.play_line())
        self.lines.editCommitted.connect(self.set_line_field)
        self.lines.pushRequested.connect(self.push_to_question)
        self.lines.todoRequested.connect(self.push_to_todo)
        self.lines.createTokenRequested.connect(self.create_token)
        self.lines.bookmarkToggled.connect(self.toggle_bookmark)
        self._bookmark_shown_for = None           # the text last opened at its bookmark
        QShortcut(QKeySequence("Ctrl+E"), win, self.toggle_edit_mode)   # Edit mode (Josh, 20 October)
        QShortcut(QKeySequence("Ctrl+S"), win, self.save_key)           # this text's TextGrid (21 October)
        QShortcut(QKeySequence("Ctrl+G"), win, self.go_to_bookmark)     # back to where you were (idea 32)
        self.doc.linesChanged.connect(self._lines_edited)
        self.doc.dirtyChanged.connect(lambda *_: self._save_icon())   # saving the database writes TextGrids too
        bl.addWidget(self.lines, 1)
        page.addWidget(box)
        page.setSizes([300, 400])
        self.bar = self._bar()                    # the lines' buttons: the window's options panel
        self._setup_columns()

    @property
    def db(self):
        return self.doc.db

    # ---- building ----------------------------------------------------
    def _texts_bar(self) -> QWidget:
        """Under the texts list: Add, Delete, Edit, Configure columns, Clear filters, search, count."""
        from .main_window import tool
        bar, bl = self.main._bar()
        self.main._row(bl, tool("Add", "add", self.add, "Add a text or song, with its recording and TextGrid"),
                             tool("Delete", "delete", self.delete, "Delete the selected text (Delete)"),
                             tool("Edit", "edit", self.edit, "Edit the selected text (Enter)"),
                             tool("Configure columns", "gear-columns", self.configure_columns),
                             tool("Clear all filters", "reset-filters", self.clear_filters))
        self.search = QLineEdit()
        self.search.setPlaceholderText("quick search of the texts' visible columns")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda text: (self.table.proxy.set_search(text), self._update_count()))
        bl.addWidget(self.search)
        self.text_count = QLabel()
        bl.addWidget(self.text_count)
        return bar

    def _bar(self) -> QWidget:
        """The lines' buttons, search and count (the window's options panel, under the lines)."""
        from .main_window import tool
        bar, bl = self.main._bar()

        def icon_tool(name, fn, tip, checkable=False):
            b = tool(tip, name, fn, tip)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)      # Josh's mockup: icons, names in the tooltips
            b.setCheckable(checkable)
            return b
        self.edit_btn = icon_tool("edit", lambda: self.set_edit_mode(self.edit_btn.isChecked()),
                                  "Edit mode (Ctrl+E): click a field to edit it in place (Tab, Shift+Tab, Up, Down move; "
                                  "Enter keeps, Esc drops). Off: the lines are for playing, clipping and Praat",
                                  checkable=True)
        self.save_btn = QToolButton()                # the text's TextGrid (Josh, 21 October)
        self.save_btn.setIconSize(QSize(20, 20))
        self.save_btn.setAutoRaise(True)
        self.save_btn.setToolTip("Save this text's TextGrid (Ctrl+S): write the line edits into it now. "
                                 "The database itself is saved with the main window's Save")
        self.save_btn.clicked.connect(lambda *_: self.save_textgrid())
        self.main._row(bl, self.save_btn,
                       icon_tool("play", self.play_line, "Play the selected line (Ctrl+Space)"),
                       self.edit_btn,
                       icon_tool("clip", self.clip, "Clip as utterance: cut the selected lines out of the "
                                 "recording as utterances, with their text (select several with Shift or Ctrl)"),
                       icon_tool("praat", self.open_in_praat,
                                 "Open in Praat: the text's recording with its TextGrid, at the selected line"),
                       icon_tool("refresh-text", self.refresh_text,
                                 "Refresh text: read the text's TextGrid again from its file and find all its "
                                 "lines again (asks first if there are line edits not yet saved)"),
                       icon_tool("gear", self.configure_view, "Configure view: which fields each line shows, "
                                 "in what order, and which line up word by word"),
                       self.main.conventions_button())
        self.restyle_icons()
        self.edit_label = QLabel("Edit mode")
        self.edit_label.hide()
        bl.itemAt(bl.count() - 1).layout().insertWidget(6, self.edit_label)
        self.line_search = QLineEdit()
        self.line_search.setPlaceholderText("quick search of the lines")
        self.line_search.setClearButtonEnabled(True)
        self.line_search.textChanged.connect(lambda text: (self.lines.set_search(text), self._update_count()))
        self.next_field = QComboBox()
        self.next_field.setToolTip("The field Next empty looks for")
        self.next_empty_btn = QPushButton("Next empty")
        self.next_empty_btn.setToolTip("The next line (after the selected one) whose chosen field is empty")
        self.next_empty_btn.clicked.connect(lambda *_: self.next_empty())
        self.line_search.setMinimumWidth(180)       # close to its field and Next empty (Josh, 21 October)
        self.line_search.setMaximumWidth(320)
        self.main._row(bl, self.line_search, self.next_field, self.next_empty_btn)
        self.count = QLabel()
        bl.addWidget(self.count)
        bl.addStretch(1)
        # the comparison area (two scratchpads, α and β), right-justified beside the bar (Josh, 22 October)
        outer = QWidget()
        ol = QHBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(bar, 1)
        cmp_panel, cl = self.main._bar()
        cl.addWidget(self._scratchpad())
        cl.addStretch(1)
        cmp_panel.setFixedWidth(280)
        ol.addWidget(cmp_panel)
        return outer

    def _scratchpad(self) -> QWidget:
        """The comparison area: two pitch scratchpads, α and β (IDEAS.md idea 33; Josh, 22 October).
        A trace typed in one is drawn and played (Ctrl+Shift+Space anywhere in the lines plays α), and
        saved nowhere: they go when the window closes."""
        from .scratchpad import ComparisonPads
        s = self.db.settings
        self.comparison = ComparisonPads(self.main, s.pitch_low, s.pitch_high,
                                         "Pitch scratchpad: type a pitch trace to see and hear it (Ctrl+Shift+"
                                         "Space plays α from anywhere in the lines). Nothing is saved: it's "
                                         "cleared when the window is closed")
        self.scratch, self.scratch_canvas = self.comparison.alpha.edit, self.comparison.alpha.canvas
        return self.comparison

    def play_scratch(self):
        """Ctrl+Shift+Space in the lines: the scratchpad's trace, in the voice of Settings → Pitch."""
        self.main.play_pitch(self.scratch.text())

    def _columns(self) -> list[Column]:
        db = self.db
        s = db.settings
        folder = storage.text_folder(db)
        cols = [Column("ref", "Reference", lambda t: t.ref)]
        for f in s.text_fields:
            cols.append(Column("f:" + f.name, f.title, lambda t, n=f.name: t.get(n), closed=f.closed,
                               tree=(lambda f=f: f.items) if f.closed else None))
        cols += [
            Column("date", "Date", lambda t: t.date),
            Column("participants", "Participants", lambda t: " ".join(t.participants)),
            Column("researchers", "Researchers", lambda t: " ".join(t.researchers)),
            Column("locations", "Locations", lambda t: ", ".join(t.locations)),
            Column("clips", "Utterances", lambda t: ", ".join(u.ref for u in db.clipped_from(t))),
            Column("file", "Recording", lambda t: t.file if t.file and (folder / t.file).exists() else "",
                   blank_labels=("Missing", "Present"),
                   display=lambda t: t.file or "(none)",
                   color=lambda t: theme.colour("dim") if not t.file else
                   (theme.colour("error") if not (folder / t.file).exists() else None)),
            Column("textgrid", "TextGrid", lambda t: t.textgrid if t.textgrid and (folder / t.textgrid).exists() else "",
                   blank_labels=("Missing", "Present"), display=lambda t: t.textgrid or "(none)",
                   color=lambda t: theme.colour("dim") if not t.textgrid else
                   (theme.colour("error") if not (folder / t.textgrid).exists() else None)),
        ]
        return cols

    def _default_keys(self):
        s = self.db.settings
        keys = ["ref"] + ["f:" + f.name for f in s.text_fields if f.role in ("title", "genre", "status")]
        return keys + ["date", "participants", "clips", "file"]

    def _setup_columns(self):
        cols = self._columns()
        saved = self.doc.ws.get_list("columns/texts")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_keys()
        self.table.set_columns(cols, keys)

    def configure_columns(self):
        cols = self._columns()
        dlg = ConfigureColumnsDialog(self.win, [(c.key, c.title) for c in cols], self.table.visible_keys())
        if dlg.exec():
            self.doc.ws_set("columns/texts", dlg.chosen())
            self._setup_columns()
            self.refresh()

    def clear_filters(self):
        self.table.clear_filters()
        self.search.clear()
        self.line_search.clear()

    # ---- refreshing ---------------------------------------------------
    def refresh(self):
        self.table.set_rows(list(self.db.texts))
        if self.table.current_row() is None and self.db.texts:
            self.table.select_row(self.table.visible_rows()[0] if self.table.visible_rows() else None)
        self._lines_for = None
        self._show_lines()
        self._update_count()

    def settings_changed(self):
        s = self.db.settings
        self.comparison.set_range(s.pitch_low, s.pitch_high)
        self.comparison.show_pitch()              # Show the pitch system (idea 9)
        self._setup_columns()
        self.refresh()

    def current(self) -> Text | None:
        return self.table.current_row()

    def select(self, text: Text):
        if text not in self.table.visible_rows():
            self.table.clear_filters()
            self.search.clear()
        self.table.select_row(text)

    def _update_count(self):
        n, shown = len(self.db.texts), self.table.proxy.rowCount()
        self.text_count.setText(f"{shown} of {n} text{'s' if n != 1 else ''} shown")
        k = len(self._lines) if self.current() is not None and not self.lines_error else 0
        self.count.setText(f"{len(self.lines.visible_rows())} of {k} line{'s' if k != 1 else ''} shown")

    def grid_path(self, t: Text) -> Path | None:
        return storage.text_folder(self.db) / t.textgrid if t.textgrid else None

    def wav_path(self, t: Text) -> Path | None:
        return storage.text_folder(self.db) / t.file if t.file else None

    def lines_of(self, t: Text) -> list:
        """The text's lines, from its TextGrid (read again only when it has changed)."""
        path = self.grid_path(t)
        self.lines_error = ""
        if path is None:
            self.lines_error = "This text has no TextGrid yet (Edit to choose one)."
            return []
        if not path.exists():
            self.lines_error = f"{path.name} isn't in Soundfiles\\Texts."
            return []
        try:
            buf = self.doc.buffer(t)              # the TextGrid as edited here (read once)
            return buf.lines(self.db, t) if buf is not None else []
        except tgmod.TextGridError as exc:
            self.lines_error = str(exc).replace("the TextGrid", path.name, 1)
            return []

    # ---- the lines view (19 October) -----------------------------------------
    def comment_key(self) -> str:
        """The token field a line's Comment is (the side box): the first comment field."""
        return next((f.name for f in self.db.settings.token_fields if f.is_comment), "")

    def view_choices(self) -> list[tuple[str, str, bool]]:
        """(key, title, IPA font) for what a line can show: the token fields (a multilingual one
        once per language), the comment field and pitch aside."""
        s = self.db.settings
        out = []
        for label, f, lang in field_choices(self.db)[2:]:
            fd = s.token_field(f)
            if fd is None or fd.is_comment or fd.role == "pitch":
                continue
            out.append((f"{f}:{lang}" if lang else f, label, fd.role in ("phonetic", "phonemic")))
        return out

    def view_specs(self) -> list[FieldSpec]:
        """The fields each line shows (Configure view; one setting for all texts)."""
        choices = {k: (title, ipa) for k, title, ipa in self.view_choices()}
        keys = [k for k in self.doc.ws.get_list("lines/fields") if k in choices]
        if not keys:                              # at first: the fields the tier mapping fills
            mapped = {r.key for r in self.db.settings.tier_mapping.rules if r.field}
            keys = [k for k in choices if k in mapped] or list(choices)[:4]
        aligned = self.main.aligned_set()         # one Line up setting for every cell view (idea 2)
        s = self.db.settings
        return [FieldSpec(k, choices[k][0], choices[k][1], k in aligned,
                          bool((fd := s.token_field(k.split(":")[0])) and fd.role == "translation"),
                          fd.role if fd is not None else "")
                for k in keys]

    def configure_view(self):
        dlg = ConfigureViewDialog(self.win, self.view_choices(), self.view_specs())
        if dlg.exec():
            keys, aligned = dlg.chosen()
            self.doc.ws_set("lines/fields", keys)                 # in the workspace (idea 36)
            old = self.main.aligned_set() - {k for k, _, _ in self.view_choices()}
            self.main.set_aligned(old | set(aligned))
            self._apply_view()

    def _apply_view(self):
        specs = self.view_specs()
        self.lines.set_fields(specs, self.comment_key())
        if callable(getattr(self.win, "show_cell", None)):    # the utterance cell shows the same fields
            self.win.show_cell()
        current = self.next_field.currentData()
        self.next_field.blockSignals(True)
        self.next_field.clear()
        for spec in specs:
            self.next_field.addItem(spec.title, spec.key)
        if self.comment_key():
            self.next_field.addItem(self.db.settings.token_field(self.comment_key()).title, self.comment_key())
        i = self.next_field.findData(current)
        self.next_field.setCurrentIndex(max(0, i))
        self.next_field.blockSignals(False)

    def restyle_icons(self):
        """The Clip button's bubble in the theme colour and its scissors in the text colour (white on
        dark), and Refresh text's arrows in the theme colour."""
        for b in self.bar.findChildren(QToolButton) if hasattr(self, "bar") else []:
            if b.property("icon_name") == "clip":
                b.setIcon(icon("clip", 20, theme.accent().name() + ";" + theme.colour("window_text").name()))
            elif b.property("icon_name") == "refresh-text":
                b.setIcon(icon("refresh-text", 20, theme.colour("pitch").name()))
        if hasattr(self, "comparison"):
            self.comparison.restyle()
        self._save_icon()

    def refresh_text(self):
        """Refresh text (Josh, 21 October): read the TextGrid again from its file, whatever its
        date says, and find every line again. Line edits not yet saved are saved first or dropped,
        after asking."""
        t = self.current()
        if t is None:
            return
        path = self.grid_path(t)
        if path is None or not path.exists():
            QMessageBox.information(self.win, "Refresh text", self.lines_error or
                                    f"{t.ref} has no TextGrid in Soundfiles\\Texts.")
            return
        buf = self.doc.text_buffers.get(t.id)
        if buf is not None and buf.changed:
            box = QMessageBox(QMessageBox.Warning, "Refresh text",
                              f"{t.ref} has line edits that aren't saved into its TextGrid yet.", parent=self.win)
            box.setInformativeText("Save and refresh: the database is saved (with the edits written into "
                                   "the TextGrid), then the TextGrid is read again.\nRefresh without saving: "
                                   "the edits to this text's lines are dropped, and the TextGrid is read as it "
                                   "is in the file.")
            save = box.addButton("Save and refresh", QMessageBox.AcceptRole)
            drop = box.addButton("Refresh without saving", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(save)
            box.exec()
            hit = box.clickedButton()
            if hit is save:
                if not self.main.save():
                    return
            elif hit is not drop:
                return
        try:
            if buf is not None and buf.path == path:
                buf.reload()
            else:
                old = self.doc.text_buffers.pop(t.id, None)
                new = self.doc.buffer(t)
                if old is not None and new is not None:   # undo of earlier line edits leaves it alone
                    new.generation = old.generation + 1
        except tgmod.TextGridError as exc:
            self.doc.text_buffers.pop(t.id, None)
            QMessageBox.warning(self.win, "Refresh text", str(exc).replace("the TextGrid", path.name, 1))
        self._shown_stamp = None
        if hasattr(self.win, "recheck") and self.db.utterances:   # clipped utterances: changed lines
            self.win.recheck()
        self.doc.linesChanged.emit(t.id)
        self._show_lines()
        n = len(self._lines)
        self.main.statusBar().showMessage(f"{t.ref} read again from {path.name}: {n} line{'s' if n != 1 else ''}.",
                                          6000)

    # ---- the bookmark (IDEAS.md idea 32, 21 October) ----------------------------------
    # One per text, for getting back to where you were in the narrative: kept in the workspace
    # (shared wherever the database is opened) by the text's id and the line's start time, so a
    # boundary moved in Praat still finds the nearest line. Set in edit mode; not an undo step.
    def _bookmarks(self) -> dict:
        return self.doc.ws.get_dict("bookmarks")

    def _bookmark_line(self, t, lines):
        if t is None or not lines:
            return None
        start = self._bookmarks().get(t.id)
        if not isinstance(start, (int, float)):
            return None
        return min(lines, key=lambda ln: abs(ln.start - start))

    def toggle_bookmark(self, line):
        """The margin clicked in edit mode: this line becomes the text's bookmark (moved from any
        other); clicked again on the bookmark, it goes."""
        t = self.current()
        if t is None or line is None:
            return
        marks = self._bookmarks()
        if self.lines.bookmark == line.id:
            marks.pop(t.id, None)
            self.lines.set_bookmark(None)
            note = f"Bookmark taken off {t.ref}."
        else:
            marks[t.id] = round(line.start, 4)
            self.lines.set_bookmark(line.id)
            note = f"{t.ref} bookmarked at {clock(line.start)} (Ctrl+G goes back to it)."
        self.doc.ws_set("bookmarks", marks or None)
        self.main.statusBar().showMessage(note, 5000)

    def go_to_bookmark(self):
        """Ctrl+G: the text's bookmarked line."""
        if not self.page.isVisible():
            return
        mark = self.lines.bookmark_row()
        if mark is None:
            if self.lines.bookmark is not None:       # hidden by the lines' search
                self.line_search.clear()
                mark = self.lines.bookmark_row()
        if mark is None:
            t = self.current()
            self.main.statusBar().showMessage(f"{t.ref if t else 'This text'} has no bookmark: in edit mode, "
                                              "click the margin beside a line.", 5000)
            return
        self.lines.select_row(mark)
        self.lines.setFocus()

    def toggle_edit_mode(self):
        """Ctrl+E: Edit mode on or off, while the lines are shown (the Texts tab)."""
        if self.lines.isVisible():
            self.set_edit_mode(not self.edit_btn.isChecked())
        elif getattr(self.win, "cell", None) is not None and self.win.cell.isVisible():   # the utterance cell
            self.win.set_cell_edit_mode(not self.win.cell_edit_btn.isChecked())

    def set_edit_mode(self, on: bool):
        self.edit_btn.setChecked(on)
        self.lines.set_edit_mode(on)
        self.edit_label.setVisible(on)
        self.edit_label.setStyleSheet(f"color: {theme.accent().name()}; font-weight: bold;")

    def next_empty(self):
        """The next line after the selected one whose chosen field is empty (wrapping round)."""
        key = self.next_field.currentData()
        rows = self.lines.visible_rows()
        if not key or not rows:
            return
        cur = self.lines.current_row()
        start = rows.index(cur) + 1 if cur in rows else 0
        for ln in rows[start:] + rows[:start]:
            if not ln.values.get(key, "").strip():
                self.lines.select_row(ln)
                if self.lines.edit_mode:
                    self.lines.start_edit(ln, key)
                return
        self.main.statusBar().showMessage(f"No line has an empty {self.next_field.currentText()}.", 5000)

    def select_line_at(self, start: float | None, nearest: bool = False):
        """Show the line starting at this time (from a notebook link); nearest: or else the nearest
        line (a hypothesis's link, after a boundary moved in Praat, as bookmarks do)."""
        if start is None:
            return
        hit = min(self.lines.rows, key=lambda ln: abs(ln.start - start), default=None)
        if hit is not None and (nearest or abs(hit.start - start) < 0.01):
            self.line_search.clear()
            self.lines.select_row(hit)

    def set_line_field(self, line, key: str, value: str):
        """An edit made in the lines view: into the TextGrid (held until saving), with the
        utterances clipped from the line and, for the Comment, the notebook. One undo step."""
        t = self.current()
        buf = self.doc.buffer(t, reload_if_saved_elsewhere=False) if t is not None else None
        if buf is None:
            return
        db = self.db
        before = buf.lines(db, t)
        line = next((ln for ln in before if ln.id == line.id), None)
        if line is None:
            return
        try:
            edits = lmod.plan_edit(buf, db, t, line, key, value)
        except lmod.LineEditError as exc:
            QMessageBox.warning(self.win, "Edit line", str(exc))
            self._show_lines()
            return
        if not edits:
            return
        merges = lmod.would_merge(edits)
        from .widgets import ask
        if merges and not ask(
                self.win, "Edit line", "This edit will merge several segments in Praat: "
                + ", ".join(f"{tier} ({n} segments)" for tier, n in merges)
                + ". The line's segments in that tier become one.", "Merge segments"):
            self._show_lines()
            return
        if any(e.created for e in edits):
            self.doc.settings_changed()               # the new tier's rule in the tier mapping
        buf.apply(edits)
        after = buf.lines(db, t)
        pairs = lmod.follow_clips(db, t, before, after, line, key, edits)
        utterances = []
        for u, a in pairs:
            b = u.copy()
            u.__dict__.update(a.copy().__dict__)
            utterances.append((u, b, a))
        note = None
        if key == self.comment_key():
            c = nbmod.line_comment(db, t, line.start, key, value, clock(line.start))
            k = self.main.session_keys()
            note = nbmod.record_line_comment(self.doc.notebook, db, self.main.work_date(), c,
                                             k.get("researchers", []), k.get("participants", []),
                                             k.get("locations", []))
        title = self.db.settings.token_field(key.split(":")[0])
        self.doc.push_line_edit(f"Edit {t.ref} {clock(line.start)} {title.title if title else key}", t, buf,
                                edits, utterances, note)
        self.worked_on(t)

    def worked_on(self, t):
        """The text is listed in the notebook's Texts tab for the day being worked on (Josh, 21
        October: the day its lines are edited or clipped, not the day it was added)."""
        main = self.main
        k = main.session_keys()
        if nbmod.note_text_worked_on(self.doc.notebook, self.db, main.work_date(), t, k.get("researchers", []),
                                     k.get("participants", []), k.get("locations", [])):
            self.doc.notebook_changed()
            if getattr(main, "notebook_dialog", None) is not None:
                main.notebook_dialog.reload()

    def _lines_edited(self, text_id: str):
        t = self.current()
        if t is not None and t.id == text_id:
            self._show_lines()

    def _grid_stamp(self, t):
        path = self.grid_path(t) if t is not None else None
        try:
            return (str(path), path.stat().st_mtime_ns) if path is not None else None
        except OSError:
            return (str(path), None)

    def lines_changed(self):
        """The window is active again (back from Praat): show the lines again if the TextGrid changed."""
        t = self.current()
        if t is not None and self._grid_stamp(t) != getattr(self, "_shown_stamp", None):
            self._show_lines()

    def _show_lines(self):
        t = self.current()
        self._shown_stamp = self._grid_stamp(t)
        lines = self.lines_of(t) if t is not None else []
        self._lines = lines
        if not self.lines.fields:
            self._apply_view()
        clips = {}
        if t is not None:
            from ..pull import find_line
            for u in self.db.clipped_from(t):
                ln = find_line(lines, u.source)
                if ln is not None and abs(ln.start - u.source.start) < 0.01:
                    clips.setdefault(ln.id, []).append(u.ref)
        self.lines.set_lines(lines, clips, show_speaker=len({ln.speaker for ln in lines if ln.speaker}) > 1)
        mark = self._bookmark_line(t, lines)
        self.lines.set_bookmark(mark.id if mark is not None else None)
        if t is not None and self._bookmark_shown_for != t.id:   # a text chosen: it opens at its bookmark
            self._bookmark_shown_for = t.id
            if mark is not None:
                self.lines.select_row(mark)
        buf = self.doc.text_buffers.get(t.id) if t is not None else None
        if t is None:
            self.lines_title.setText("Lines" if self.db.texts else
                                     "No texts yet: Add one, with its recording and Praat TextGrid.")
        elif self.lines_error:
            self.lines_title.setText(f"Lines of {t.ref}: "
                                     f"<span style='color:{theme.colour('error').name()}'>{self.lines_error}</span>")
        else:
            note = ""
            if buf is not None and buf.changed:
                note = ("  <span style='color:%s'>· edits not yet saved into the TextGrid%s</span>"
                        % (theme.colour("error").name() if buf.disk_changed() else theme.muted(),
                           " (and Praat has saved it since: saving will ask)" if buf.disk_changed() else ""))
            self.lines_title.setText(f"Lines of {t.ref} {self.db.text_title(t)}{note}")
        self._update_count()
        self._save_icon()

    # ---- saving the text's TextGrid (Ctrl+S, Josh 21 October) -------------------------
    def _save_icon(self):
        """The floppy: the theme colour while the text has line edits not yet in its TextGrid, grey otherwise."""
        if not hasattr(self, "save_btn"):
            return
        try:
            t = self.current()
        except RuntimeError:                      # the window has gone
            return
        buf = self.doc.text_buffers.get(t.id) if t is not None else None
        on = buf is not None and buf.changed
        c = theme.colour("pitch") if on else (theme.colour("disabled"))
        self.save_btn.setIcon(icon("save-solid", 20, c.name()))
        self.save_btn.setEnabled(on)

    def save_key(self):
        """Ctrl+S in the Texts and utterances window: on the Texts tab, this text's TextGrid; on
        the Utterances tab, the database (Josh, 21 October), as the main window's Save."""
        if self.page.isVisible():
            self.save_textgrid()
        else:
            self.main.save()

    def save_textgrid(self) -> bool:
        """Write the current text's line edits into its TextGrid now (backed up first), without
        saving the database. Asks first if Praat has saved the TextGrid since."""
        t = self.current()
        buf = self.doc.text_buffers.get(t.id) if t is not None else None
        if t is None or buf is None or not buf.changed:
            if t is not None:
                self.main.statusBar().showMessage(f"{t.ref} has no line edits to save into its TextGrid.", 4000)
            return False
        if buf.disk_changed():
            box = QMessageBox(QMessageBox.Warning, "Save TextGrid",
                              f"{t.ref}'s TextGrid was saved in Praat after you edited its lines here.",
                              parent=self.win)
            box.setInformativeText("Save my edits: Lemmatrix's version replaces Praat's (a copy of Praat's "
                                   "goes to Backups first).\nKeep Praat's: the unsaved line edits to "
                                   f"{t.ref} are dropped.")
            mine = box.addButton("Save my edits", QMessageBox.AcceptRole)
            praat = box.addButton("Keep Praat's", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is praat:
                buf.reload()
                self.doc.linesChanged.emit(t.id)
                return False
            if box.clickedButton() is not mine:
                return False
        try:
            buf.write(self.db)
        except OSError as exc:
            QMessageBox.warning(self.win, "Save TextGrid", f"Couldn't write {buf.path.name}: {exc}")
            return False
        self._shown_stamp = self._grid_stamp(t)
        self._show_lines()
        self.main.statusBar().showMessage(f"Saved {buf.path.name}. The previous version is in Backups.", 5000)
        return True

    # ---- texts -------------------------------------------------------
    def add(self):
        if not self.db.path:
            QMessageBox.information(self.win, "Add text", "Save the database first: the recordings go in "
                                    "the Soundfiles folder next to it.")
            return
        dlg = TextDialog(self)
        if not dlg.exec():
            return
        t = dlg.record()
        renames = self._copy_in(t, dlg.new_wav, dlg.new_grid)
        if renames is None:
            return
        self.doc.add_entry(t, renames=renames)
        self.select(t)
        self._note_comments(t)

    def _note_comments(self, t: Text):
        """A text just added: the comments already in its TextGrid go into the notebook, in the
        day the text was recorded (Josh, 19 October)."""
        key = self.comment_key()
        if not key or not t.date:
            return
        lines = [ln for ln in self.lines_of(t) if ln.values.get(key, "").strip()]
        for ln in lines:
            c = nbmod.line_comment(self.db, t, ln.start, key, ln.values[key], clock(ln.start))
            nbmod.record_line_comment(self.doc.notebook, self.db, t.date, c, t.researchers, t.participants,
                                      t.locations)
        if lines:
            self.doc.notebook_changed()
            self.main.statusBar().showMessage(f"{len(lines)} comment(s) from {t.ref}'s TextGrid went into the "
                                              f"notebook for {t.date}.", 8000)

    def _copy_in(self, t: Text, wav: Path | None, grid: Path | None) -> list | None:
        """Copy a new recording and TextGrid into Soundfiles/Texts under the text's names. A file
        already in Soundfiles/Texts is renamed there instead of copied. Returns the renames for
        undo (copies move aside, renamed files get their names back), or None on a problem."""
        folder = storage.text_folder(self.db)
        folder.mkdir(parents=True, exist_ok=True)
        out = []
        for src, ext, attr in ((wav, ".wav", "file"), (grid, ".TextGrid", "textgrid")):
            if src is None:
                continue
            name = self.db.expected_text_name(t, ext)
            dst = folder / name
            old = getattr(t, attr)
            if storage.in_folder(src, folder):    # already here: rename it, don't copy it
                if not storage.same_file(src, dst):
                    if dst.exists():
                        QMessageBox.warning(self.win, "Text", f"Can't rename {src.name}: {name} is "
                                            "already in Soundfiles\\Texts.")
                        return None
                    try:
                        src.rename(dst)
                    except OSError as exc:
                        QMessageBox.warning(self.win, "Text", f"Couldn't rename {src.name}: {exc}")
                        return None
                    out.append((src, dst))
                elif src.name != name:            # only the case differs
                    src.rename(dst)
                    out.append((src, dst))
                setattr(t, attr, name)
                continue
            if dst.exists() and not (old and old == name and storage.same_file(src, dst)):
                if old == name:                   # replacing this text's own file
                    if QMessageBox.question(self.win, "Text", f"Replace {name}? The one there now goes "
                                            "to the Recycle Bin.") != QMessageBox.Yes:
                        return None
                    from PySide6.QtCore import QFile
                    QFile.moveToTrash(str(dst))
                else:
                    QMessageBox.warning(self.win, "Text", f"{name} is already in Soundfiles\\Texts.")
                    return None
            try:
                if not storage.same_file(src, dst):
                    shutil.copy2(src, dst)
            except OSError as exc:
                QMessageBox.warning(self.win, "Text", f"Couldn't copy {src.name}: {exc}")
                return None
            setattr(t, attr, name)
            out.append((self.doc.hold_recording(dst), dst))
        return out

    def edit(self, row=None):
        t = row if isinstance(row, Text) else self.current()
        if t is None:
            return
        dlg = TextDialog(self, t)
        if not dlg.exec():
            return
        after = dlg.record()
        renames = []
        folder = storage.text_folder(self.db)
        if after.file_label != t.file_label:      # the title in file names: both files renamed
            for attr, ext in (("file", ".wav"), ("textgrid", ".TextGrid")):
                old = getattr(t, attr)
                if not old or attr == "file" and dlg.new_wav or attr == "textgrid" and dlg.new_grid:
                    continue
                new = self.db.expected_text_name(after, ext)
                src, dst = folder / old, folder / new
                if src.exists() and new != old:
                    if dst.exists() and not storage.same_file(src, dst):
                        QMessageBox.warning(self.win, "Text", f"Can't rename {old}: {new} already exists.")
                        return
                    src.rename(dst)
                    renames.append((src, dst))
                    setattr(after, attr, new)
        copies = self._copy_in(after, dlg.new_wav, dlg.new_grid)
        if copies is None:
            return

        def change(x, after=after):
            x.__dict__.update(after.copy().__dict__)
            x.id = t.id
        self.doc.edit_entry(t, change, f"Edit {t.ref}", renames=renames)
        self._lines_for = None
        self.refresh()
        self.select(t)

    def delete(self):
        t = self.current()
        if t is None:
            return
        clips = self.db.clipped_from(t)
        msg = f"Delete the text {t.ref} {self.db.text_title(t)}?"
        if t.file or t.textgrid:
            msg += ("\nIts recording and TextGrid go to the Recycle Bin when the database is closed; "
                    "until then, undo brings them back.")
        if clips:
            msg += (f"\nThe {len(clips)} utterance(s) clipped from it ({', '.join(u.ref for u in clips[:6])}) "
                    "stay, with their own recordings.")
        if QMessageBox.question(self.win, "Delete text", msg) != QMessageBox.Yes:
            return
        renames = []
        folder = storage.text_folder(self.db)
        self.main.player.stop()
        for name in (t.file, t.textgrid):
            if name and (folder / name).exists():
                held = self.doc.hold_recording(folder / name)
                try:
                    (folder / name).rename(held)
                    renames.append((folder / name, held))
                except OSError as exc:
                    QMessageBox.warning(self.win, "Delete text", f"Couldn't move {name} aside: {exc}.")
        self.doc.delete_entry(t, renames=renames)

    def _text_menu(self, row, pos):
        if row is not None:
            self.table.select_row(row)
        m = QMenu(self.win)
        for text, name, fn, on in (("Add", "add", self.add, True), ("Edit", "edit", self.edit, row is not None),
                                   ("Open in Praat", "praat", self.open_in_praat, row is not None),
                                   ("Refresh text", "refresh-text", self.refresh_text, row is not None),
                                   ("Delete", "delete", self.delete, row is not None)):
            a = m.addAction(icon(name, 16), text)
            a.setEnabled(on)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    def open_in_praat(self):
        t = self.current()
        if t is None:
            return
        wav = self.wav_path(t)
        if wav is None or not wav.exists():
            QMessageBox.information(self.win, "Open in Praat", "This text has no recording in Soundfiles\\Texts.")
            return
        buf = self.doc.text_buffers.get(t.id)
        if buf is not None and buf.changed:           # Praat would read the file without them
            box = QMessageBox(QMessageBox.Question, "Open in Praat", f"{t.ref} has line edits that aren't "
                              "saved into its TextGrid yet, so Praat would show it without them. Save first?",
                              parent=self.win)
            save = box.addButton("Save and open", QMessageBox.AcceptRole)
            plain = box.addButton("Open without saving", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(save)
            box.exec()
            hit = box.clickedButton()
            if hit not in (save, plain) or (hit is save and not self.main.save()):
                return
        grid = self.grid_path(t)
        lines = self.selected_lines()                 # opened at the selected line(s)
        select = (min(l.start for l in lines), max(l.end for l in lines)) if lines else None
        self.main.open_in_praat(wav, self.win, grid if grid is not None and grid.exists() else None, select)

    # ---- lines ---------------------------------------------------------
    def selected_lines(self) -> list:
        return self.lines.selected()

    def play_line(self, context: bool = False):
        t = self.current()
        lines = self.selected_lines()
        if t is None or not lines:
            return
        wav = self.wav_path(t)
        if wav is None or not wav.exists():
            QMessageBox.information(self.win, "Play", "This text has no recording in Soundfiles\\Texts.")
            return
        ln = lines[0]
        pad = CONTEXT if context else 0.0
        try:
            samples, rate = audio.read_segment(wav, ln.start - pad, ln.end + pad)
            self.main.player.play_samples(samples, rate)
        except (audio.AudioError, OSError, EOFError, Exception) as exc:      # wave.Error too
            QMessageBox.warning(self.win, "Play", f"Couldn't play {wav.name}: {exc}")

    def push_to_todo(self, line=None):
        """Push to To Do from a line's Comment (the orange flag; Josh, 21 October)."""
        self.push_to_question(line, nbmod.TODO)

    def push_to_question(self, line=None, kind: str = nbmod.QUESTION):
        """A line's Comment becomes an open question (or to do) in the notebook (the session's day),
        linked to the line, and the Comment is emptied: as the token dialogue's Push to question
        (Josh, 20 October)."""
        line = line or self.lines.current_row()
        t, key = self.current(), self.comment_key()
        if line is None or t is None or not key:
            return
        question = (line.values.get(key) or "").strip()
        if not question:
            return
        main = self.main
        date = main.work_date()
        k = main.session_keys()
        nbmod.push_line_question(self.doc.notebook, self.db, date, question, t, line.start, clock(line.start),
                                 k.get("researchers", []), k.get("participants", []), k.get("locations", []),
                                 kind)
        self.doc.notebook_changed()
        if getattr(main, "notebook_dialog", None) is not None:
            main.notebook_dialog.reload()
        self.set_line_field(line, key, "")
        main.statusBar().showMessage(f"Added to the {nbmod.name(kind, True, title=False)} of {date}", 5000)

    def _line_menu(self, row, pos):
        m = QMenu(self.win)
        on = row is not None
        key = self.lines.menu_key if on else ""
        sel = self.lines.text_selection()
        if sel is not None and on and sel[0].id == row.id:   # words highlighted in a field (idea 31)
            _, skey, words = sel
            a = m.addAction(themed_icon("text-token", 16), f"Create token from “{words}”…")
            a.triggered.connect(lambda *_: self.create_token(row, skey, words))
        else:
            a = m.addAction(themed_icon("text-token", 16), "Create token (highlight words first)")
            a.setEnabled(False)
        m.addSeparator()
        a = m.addAction(icon("edit", 16), f"Edit {self.lines.title(key)}" if key else "Edit field")
        a.setEnabled(bool(key))
        a.triggered.connect(lambda *_: self.lines.start_edit(row, key))
        a = m.addAction("Go to bookmark (Ctrl+G)")
        a.setEnabled(self.lines.bookmark is not None)
        a.triggered.connect(lambda *_: self.go_to_bookmark())
        a = m.addAction("Edit text…")
        a.setEnabled(self.current() is not None)
        a.triggered.connect(lambda *_: self.edit())
        key_c = self.comment_key()
        has_c = on and bool(key_c) and bool((row.values.get(key_c) or "").strip())
        a = m.addAction(icon("push-question", 16), "Push comment to question")
        a.setEnabled(has_c)
        a.triggered.connect(lambda *_: self.push_to_question(row))
        a = m.addAction(icon("push-todo", 16), "Push comment to To Do")
        a.setEnabled(has_c)
        a.triggered.connect(lambda *_: self.push_to_todo(row))
        if hasattr(self.main, "link_to_hypothesis"):                    # Cogitate: the whole line
            from .icons import icon as _icon
            from . import theme as _theme
            a = m.addAction(_icon("cogitate", 16, _theme.colour("pitch").name()), "Link line to hypothesis…")
            a.setEnabled(on and self.current() is not None)
            a.triggered.connect(lambda *_: self.link_line(row))
        m.addSeparator()
        for text, name, fn in (("Play line", "play", self.play_line),
                               ("Play in context", None, lambda: self.play_line(context=True)),
                               ("Clip as utterance…", None, self.clip),
                               ("Open in Praat", "praat", self.open_in_praat)):
            a = m.addAction(icon(name, 16), text) if name else m.addAction(text)
            a.setEnabled(on)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    def link_line(self, line):
        """Link line to hypothesis…: the whole line, found again by its text and start time."""
        from .. import hypotheses as hy
        t = self.current()
        if t is None or line is None:
            return None
        words = next((v for v in (line.values.get(f.key) for f in self.lines.fields) if v), "")
        return self.main.link_to_hypothesis(hy.line_link(self.db, t, line.start, words, clock(line.start)),
                                            self.win)

    def create_token(self, line, key: str, words: str, view=None):
        """Create token from a text's line (IDEAS.md idea 31, Josh 21 October): the lemma is picked
        first, then the token dialogue opens on a new token with only the highlighted words, in the
        field they came from (\"my dog\" from the Translation into the Translation). New lemma…
        makes a lemma instead, the words in its citation token."""
        from .move_dialog import CreateTokenDialog
        from .token_dialog import Slot, TokenDialog
        words = (words or "").strip()
        name, _, lang = key.partition(":")
        f = self.db.settings.token_field(name)
        if not words or f is None:
            return
        view = view or self.lines                 # the text's lines, or the utterance cell
        title = view.title(key)
        dlg = CreateTokenDialog(self.win, self.db, words, title, self.main.prefs.ipa_size,
                                new_lemma=lambda: self.main.new_lemma_for(dlg, words, name, lang))
        if not dlg.exec() or dlg.chosen() is None:
            return
        if dlg.made is not None:                  # a new lemma: the words are in its citation token
            slot = Slot(dlg.made, 0)
        else:
            slot = Slot(dlg.chosen(), None, (), explicit=True, defaults=True,
                        values={(name, lang or None): words})
        main = self.main
        main.dialog_autoplay = False
        tok = TokenDialog(main, [slot], 0, parent=self.win)
        tok.exec()
        tok.deleteLater()
        main.refresh()
        view.clear_text_selection()

    def _open_clip(self, line):
        """Double-click on a line's Utterances: show the (first) utterance clipped from it."""
        t = self.current()
        if t is None or line is None:
            return
        hits = [u for u in self.db.clipped_from(t)
                if abs(u.source.start - line.start) < 0.01 and abs(u.source.end - line.end) < 0.01]
        if hits:
            self.win.select(hits[0])
        else:
            self.play_line()

    def clip(self):
        """Clip the selected lines as utterances (one undo step)."""
        t = self.current()
        lines = self.selected_lines()
        if t is None or not lines:
            QMessageBox.information(self.win, "Clip as utterance", "Select a line first.")
            return
        wav = self.wav_path(t)
        if wav is None or not wav.exists():
            QMessageBox.information(self.win, "Clip as utterance", "This text has no recording to cut from.")
            return
        letter = self.win._ask_category(f"Clip {len(lines)} line{'s' if len(lines) != 1 else ''} as utterances"
                                        if len(lines) > 1 else "Clip as utterance")
        if not letter:
            return
        db = self.db
        s = db.settings
        folder = storage.utterance_folder(db)
        folder.mkdir(parents=True, exist_ok=True)
        from .utterances import clean_label
        digits = s.ref_digits
        prefix = s.ref_prefix(letter)            # "" in a database numbered on (no categories)
        number = int(db.suggest_utterance_reference(letter)[len(prefix):])
        pad = max(0, s.clip_padding) / 1000.0
        try:
            length = audio.duration(wav)
        except Exception as exc:
            QMessageBox.warning(self.win, "Clip as utterance", f"Couldn't read {wav.name}: {exc}")
            return
        modified = tgmod.modified(self.grid_path(t))
        items, renames, problems = [], [], []
        trans = s.token_field("translation")
        for ln in lines:
            ref = f"{prefix}{number:0{digits}d}"
            words = (ln.values.get(f"{trans.name}:{s.primary_gloss}", "") if trans else "") or \
                next(iter(ln.values.values()), "")
            label = clean_label(" ".join(words.split()[:6]))
            speaker = ln.speaker or (t.participants[0] if t.participants else "")
            u = db.new_utterance(ref, label, speaker, t.date)
            for key, value in ln.values.items():
                name, _, lang = key.partition(":")
                f = s.token_field(name)
                if f is not None:
                    u.token.set(name, value, (lang or s.primary_gloss) if f.multilingual else None, f.multilingual)
            u.source = ClipSource(t.id, ln.start, ln.end, dict(ln.copied), modified)
            name = db.expected_filename(u, u.token)
            dst = folder / name
            if dst.exists():
                problems.append(f"{clock(ln.start)}: {name} is already in Soundfiles\\Utterances")
                continue
            try:
                audio.clip_wav(wav, dst, max(0.0, ln.start - pad), min(length, ln.end + pad), speaker, t.date)
            except Exception as exc:
                problems.append(f"{clock(ln.start)}: {exc}")
                continue
            number += 1
            u.token.file = name
            renames.append((self.doc.hold_recording(dst), dst))
            items.append(u)
        if items:
            if len(items) == 1:
                self.doc.add_entry(items[0], renames=renames)
            else:
                self.doc.add_many(f"Clip {len(items)} lines of {t.ref}", items, renames)
            self.worked_on(t)
            self.main.statusBar().showMessage(
                f"Clipped as {items[0].ref}" + (f"–{items[-1].ref}" if len(items) > 1 else "") + ".", 8000)
        if problems:
            QMessageBox.warning(self.win, "Clip as utterance", "Not clipped:\n\n" + "\n".join(problems[:30]))
        return items
