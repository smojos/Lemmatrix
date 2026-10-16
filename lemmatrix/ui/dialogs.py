"""Smaller dialogues: entries, metadata, preferences, display setup, filters, tags."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QInputDialog)

from .. import matrix as mx
from ..model import (Database, Entry, Group, Participant, Tag, WordClass, forbidden_in, nfc)
from .matrix_view import ENTRY_TAG, TAG_TAG, ViewState, group_path
from .widgets import ipa_font


def _buttons(dlg) -> QDialogButtonBox:
    b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    b.accepted.connect(dlg.accept)
    b.rejected.connect(dlg.reject)
    return b


class NoForbidden(QLineEdit):
    """A line edit that refuses characters Windows forbids in file names."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._last = text
        self.textEdited.connect(self._check)

    def _check(self, text):
        bad = forbidden_in(text)
        if bad:
            pos = self.cursorPosition()
            self.setText(self._last)
            self.setCursorPosition(max(0, pos - 1))
            self.setToolTip(f"{bad} can't be used here, because it isn't allowed in file names.")
            from PySide6.QtWidgets import QToolTip
            QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self.toolTip(), self)
        else:
            self._last = text


# ==========================================================================
# Entries
# ==========================================================================

class EntryDialog(QDialog):
    """Add or edit an entry; suggests a reference from the chosen category."""

    def __init__(self, parent, db: Database, entry: Entry | None = None):
        super().__init__(parent)
        self.db = db
        self.entry = entry
        s = db.settings
        self.setWindowTitle("Edit entry" if entry else "Add entry")
        form = QFormLayout(self)
        self.category = QComboBox()
        self.category.addItem("(manual)", "")
        for c in s.ref_categories:
            self.category.addItem(f"{c.letter}  {c.name}", c.letter)
        self.ref = NoForbidden(entry.ref if entry else "")
        if entry:
            m = re.match(r"[A-Za-z]+", entry.ref)
            letter = m.group(0) if m else ""
            i = self.category.findData(letter)
            self.category.setCurrentIndex(max(0, i))
            self.category.setEnabled(False)
            self.ref.setReadOnly(True)
            self.ref.setToolTip("References never change, because they're part of sound file names.")
        else:
            self.category.currentIndexChanged.connect(self._suggest)
        form.addRow("Category", self.category)
        form.addRow("Reference", self.ref)
        self.fields: dict[tuple[str, str], QWidget] = {}
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    ed = NoForbidden() if (lang == s.primary_gloss and not entry) else QLineEdit()
                    ed.setText(entry.get(f.name, lang) if entry else "")
                    form.addRow(f"{f.title} ({lang})", ed)
                    self.fields[(f.name, lang)] = ed
            elif f.role == "word-class":
                cb = QComboBox()
                cb.addItem("")
                cb.addItems(s.tags.word_class_names())
                cb.setCurrentText(entry.get(f.name) if entry else "")
                form.addRow(f.title, cb)
                self.fields[(f.name, "")] = cb
            elif f.is_list:
                cb = QComboBox()
                cb.setEditable(True)
                cb.addItem("")
                values = set(f.values) | {e.get(f.name) for e in db.entries if e.get(f.name)}
                cb.addItems(sorted(values))
                cb.setCurrentText(entry.get(f.name) if entry else "")
                form.addRow(f.title, cb)
                self.fields[(f.name, "")] = cb
            else:
                ed = QLineEdit(entry.get(f.name) if entry else "")
                if f.role == "lemma":
                    ed.setFont(ipa_font(14))
                form.addRow(f.title, ed)
                self.fields[(f.name, "")] = ed
        self.file_gloss = NoForbidden(entry.file_gloss if entry else "")
        self.file_gloss.setPlaceholderText("copied from the gloss when the entry is created")
        form.addRow("Gloss in file names", self.file_gloss)
        if not entry:
            self.file_gloss.setEnabled(False)
            self.file_gloss.setToolTip("Set automatically from the primary gloss.")
        form.addRow(_buttons(self))

    def _suggest(self):
        letter = self.category.currentData()
        cat = next((c for c in self.db.settings.ref_categories if c.letter == letter), None)
        if not letter:
            return
        if cat and cat.numbering == "manual":
            self.ref.setText(letter)
            self.ref.setFocus()
            self.ref.setToolTip(f"{cat.name} are numbered by hand.")
        else:
            self.ref.setText(self.db.suggest_reference(letter))

    def accept(self):
        ref = nfc(self.ref.text().strip())
        if not ref:
            QMessageBox.warning(self, "Entry", "Every entry needs a reference.")
            return
        if self.entry is None and self.db.entry_by_ref(ref):
            QMessageBox.warning(self, "Entry", f"The reference {ref} is already used.")
            return
        super().accept()

    def apply(self, e: Entry):
        """Write the dialogue's values into an entry."""
        s = self.db.settings
        for (name, lang), w in self.fields.items():
            text = w.currentText() if isinstance(w, QComboBox) else w.text()
            f = s.entry_field(name)
            e.set(name, text.strip(), lang if f.multilingual else None, f.multilingual)
            if f.is_list and text.strip() and text.strip() not in f.values:
                f.values.append(text.strip())
        if self.entry is not None:
            e.file_gloss = nfc(self.file_gloss.text().strip())

    def new_entry(self, speaker: str, date: str) -> Entry:
        s = self.db.settings
        gloss_field = s.entry_field("gloss")
        gloss = self.fields.get((gloss_field.name, s.primary_gloss)).text().strip() if gloss_field else ""
        e = self.db.new_entry(self.ref.text().strip(), gloss=gloss, speaker=speaker, date=date)
        self.apply(e)
        e.file_gloss = nfc(gloss)
        return e


# ==========================================================================
# Metadata
# ==========================================================================

class MetadataDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        md = db.metadata
        self.setWindowTitle("Database metadata")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.lang_code = NoForbidden(md.language_code)
        self.lang_name = QLineEdit(md.language_name)
        self.var_code = NoForbidden(md.variety_code)
        self.var_name = QLineEdit(md.variety_name)
        self.researcher = QLineEdit(md.researcher)
        self.description = QLineEdit(md.description)
        form.addRow("Language code", self.lang_code)
        form.addRow("Language name", self.lang_name)
        form.addRow("Variety code", self.var_code)
        form.addRow("Variety name", self.var_name)
        form.addRow("Researcher", self.researcher)
        form.addRow("Description", self.description)
        self.glosses = QLineEdit(" ".join(db.settings.gloss_languages))
        self.glosses.setToolTip("Gloss languages, separated by spaces; the first is the primary one.")
        form.addRow("Gloss languages", self.glosses)
        lay.addLayout(form)
        lay.addWidget(QLabel("Participants (speakers)"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Code", "Name (optional)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for p in md.participants:
            self._add_row(p.code, p.name)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add participant")
        rem = QPushButton("Remove selected")
        add.clicked.connect(lambda: self._add_row("", ""))
        rem.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_buttons(self))

    def _add_row(self, code, name):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(code))
        self.table.setItem(r, 1, QTableWidgetItem(name))

    def accept(self):
        codes = []
        for r in range(self.table.rowCount()):
            code = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if forbidden_in(code):
                QMessageBox.warning(self, "Metadata", f"The code {code} contains {forbidden_in(code)}, "
                                    "which isn't allowed in file names.")
                return
            if code in codes:
                QMessageBox.warning(self, "Metadata", f"The code {code} is listed twice.")
                return
            if code:
                codes.append(code)
        langs = self.glosses.text().split()
        if not langs:
            QMessageBox.warning(self, "Metadata", "Give at least one gloss language, e.g. en.")
            return
        super().accept()

    def apply(self):
        md = self.db.metadata
        md.language_code = nfc(self.lang_code.text().strip())
        md.language_name = nfc(self.lang_name.text().strip())
        md.variety_code = nfc(self.var_code.text().strip())
        md.variety_name = nfc(self.var_name.text().strip())
        md.researcher = nfc(self.researcher.text().strip())
        md.description = nfc(self.description.text().strip())
        md.participants = []
        for r in range(self.table.rowCount()):
            code = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            name = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if code:
                md.participants.append(Participant(nfc(code), nfc(name)))
        langs = self.glosses.text().split()
        self.db.settings.gloss_languages = langs
        self.db.settings.primary_gloss = langs[0]


# ==========================================================================
# Preferences
# ==========================================================================

class PreferencesDialog(QDialog):
    def __init__(self, parent, db: Database, prefs):
        super().__init__(parent)
        self.db, self.prefs = db, prefs
        s = db.settings
        self.setWindowTitle("Settings")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        w = QWidget()
        f = QFormLayout(w)
        self.pattern = QLineEdit(s.filename_pattern)
        self.pattern.setToolTip("Placeholders: {language} {variety} {speaker} {reference} {gloss} "
                                "{tags} {date}, or any field name. A separator before an empty part "
                                "is left out.")
        self.separator = QLineEdit(s.tag_separator)
        self.separator.setMaxLength(3)
        self.folder = QLineEdit(s.sound_folder)
        self.folder.setToolTip("Relative to the database file, unless it's a full path.")
        self.auto_names = QCheckBox("Update sound file names automatically")
        self.auto_names.setChecked(s.auto_update_names)
        f.addRow("File name pattern", self.pattern)
        f.addRow("Tag separator", self.separator)
        f.addRow("Sound folder", self.folder)
        f.addRow(self.auto_names)
        tabs.addTab(w, "Sound files (database)")

        w = QWidget()
        f = QFormLayout(w)
        self.low = QSpinBox()
        self.low.setRange(0, 9)
        self.low.setValue(s.pitch_low)
        self.high = QSpinBox()
        self.high.setRange(0, 9)
        self.high.setValue(s.pitch_high)
        f.addRow("Lowest pitch digit", self.low)
        f.addRow("Highest pitch digit", self.high)
        self.play_click = QCheckBox("Play cell when clicked")
        self.play_click.setChecked(s.play_cell_on_click)
        f.addRow(self.play_click)
        tabs.addTab(w, "Display (database)")

        w = QWidget()
        f = QFormLayout(w)
        self.source = QComboBox()
        self.source.addItem("Microphone", "microphone")
        self.source.addItem("Computer audio", "computer")
        self.source.setCurrentIndex(max(0, self.source.findData(prefs.record_source)))
        self.bits = QComboBox()
        for b in (16, 24, 32):
            self.bits.addItem(str(b), b)
        self.bits.setCurrentIndex(max(0, self.bits.findData(prefs.bit_depth)))
        self.rate = QComboBox()
        for r in (22050, 44100, 48000, 96000):
            self.rate.addItem(f"{r:,} Hz", r)
        self.rate.setCurrentIndex(max(0, self.rate.findData(prefs.sample_rate)))
        self.autoplay = QCheckBox("Auto-play: play a token's recording when moving to it")
        self.autoplay.setChecked(prefs.auto_play)
        self.confirm = QCheckBox("Confirm before deleting recordings")
        self.confirm.setChecked(prefs.confirm_delete)
        self.autosave = QSpinBox()
        self.autosave.setRange(0, 120)
        self.autosave.setSuffix(" min")
        self.autosave.setSpecialValueText("off")
        self.autosave.setValue(prefs.autosave_minutes)
        self.ipa = QSpinBox()
        self.ipa.setRange(8, 30)
        self.ipa.setValue(prefs.ipa_size)
        f.addRow("Recording source", self.source)
        f.addRow("Bit depth", self.bits)
        f.addRow("Sample rate", self.rate)
        f.addRow(self.autoplay)
        f.addRow(self.confirm)
        f.addRow("Autosave every", self.autosave)
        f.addRow("IPA font size", self.ipa)
        tabs.addTab(w, "This computer")
        lay.addWidget(_buttons(self))

    def accept(self):
        if self.low.value() >= self.high.value():
            QMessageBox.warning(self, "Settings", "The lowest pitch digit must be below the highest.")
            return
        if "{" not in self.pattern.text():
            QMessageBox.warning(self, "Settings", "The file name pattern needs at least one placeholder.")
            return
        bad = forbidden_in(self.separator.text())
        if bad:
            QMessageBox.warning(self, "Settings", f"The separator can't contain {bad}.")
            return
        super().accept()

    def apply(self) -> bool:
        """Apply the values. Returns True if file names may have changed."""
        s = self.db.settings
        old = (s.filename_pattern, s.tag_separator)
        s.filename_pattern = self.pattern.text().strip()
        s.tag_separator = self.separator.text()
        s.sound_folder = self.folder.text().strip() or "Soundfiles"
        s.auto_update_names = self.auto_names.isChecked()
        s.pitch_low, s.pitch_high = self.low.value(), self.high.value()
        s.play_cell_on_click = self.play_click.isChecked()
        p = self.prefs
        p.record_source = self.source.currentData()
        p.bit_depth = self.bits.currentData()
        p.sample_rate = self.rate.currentData()
        p.auto_play = self.autoplay.isChecked()
        p.confirm_delete = self.confirm.isChecked()
        p.autosave_minutes = self.autosave.value()
        p.ipa_size = self.ipa.value()
        return old != (s.filename_pattern, s.tag_separator)


# ==========================================================================
# Set up token display
# ==========================================================================

class DisplaySetupDialog(QDialog):
    def __init__(self, parent, db: Database, state: ViewState, entries: list[Entry],
                 current: Entry | None):
        super().__init__(parent)
        self.db, self.state = db, state
        self.setWindowTitle("Set up token display")
        self.resize(520, 560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.matching = QComboBox()
        self.matching.addItem("Exactly: only tokens with exactly these tags", mx.EXACTLY)
        self.matching.addItem("Includes: also tokens with extra tags, as sub-rows", mx.INCLUDES)
        self.matching.setCurrentIndex(0 if state.matching == mx.EXACTLY else 1)
        form.addRow("Matching", self.matching)
        self.fields = QListWidget()
        names = [f.name for f in db.settings.token_fields]
        for n in state.cell_fields + [n for n in names if n not in state.cell_fields]:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in state.cell_fields else Qt.Unchecked)
            self.fields.addItem(it)
        self.fields.setDragDropMode(QAbstractItemView.InternalMove)
        self.fields.setMaximumHeight(130)
        form.addRow("Shown in cells\n(drag to reorder)", self.fields)
        lay.addLayout(form)

        self.mode = state.mode
        if state.mode == ENTRY_TAG:
            box = QGroupBox("Rows (tag combinations)")
            bl = QVBoxLayout(box)
            self.auto = QCheckBox("Automatic: every combination in the shown tokens")
            self.auto.setChecked(state.headers is None)
            bl.addWidget(self.auto)
            self.headers = QListWidget()
            self.headers.setDragDropMode(QAbstractItemView.InternalMove)
            found = mx.auto_headers(db, entries)
            chosen = state.headers or []
            for h in chosen + [h for h in found if h not in chosen]:
                it = QListWidgetItem(db.settings.tags.display(None, list(h)))
                it.setData(Qt.UserRole, sorted(h))
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if (state.headers is None or h in chosen) else Qt.Unchecked)
                self.headers.addItem(it)
            bl.addWidget(self.headers)
            self.auto.toggled.connect(lambda on: self.headers.setEnabled(not on))
            self.headers.setEnabled(state.headers is None and False or state.headers is not None)
            self.entry_label = QComboBox()
            for k, v in (("lemma", "Lemma"), ("reference", "Reference"), ("gloss", "Gloss")):
                self.entry_label.addItem(v, k)
            self.entry_label.setCurrentIndex(max(0, self.entry_label.findData(state.entry_label)))
            row = QHBoxLayout()
            row.addWidget(QLabel("Entry headers show the"))
            row.addWidget(self.entry_label)
            row.addStretch(1)
            bl.addLayout(row)
            lay.addWidget(box)
        elif state.mode == TAG_TAG:
            box = QGroupBox("Paradigm")
            bl = QFormLayout(box)
            wc = db.word_class(current) if current else None
            self.rows = QComboBox()
            self.cols = QComboBox()
            for path, g in db.settings.tags.leaf_groups_for(wc):
                p = group_path(path)
                self.rows.addItem(p)
                self.cols.addItem(p)
            self.rows.setCurrentText(state.row_group)
            self.cols.setCurrentText(state.col_group)
            if not state.col_group and self.cols.count() > 1:
                self.cols.setCurrentIndex(1)
            bl.addRow("Down the side", self.rows)
            bl.addRow("Across the top", self.cols)
            if current is None:
                bl.addRow(QLabel("Select an entry in the lemma list to choose its groups."))
            lay.addWidget(box)
        lay.addStretch(1)
        lay.addWidget(_buttons(self))

    def accept(self):
        if self.mode == TAG_TAG and self.rows.currentText() == self.cols.currentText() and self.rows.count():
            QMessageBox.warning(self, "Set up token display",
                                "The same group can't be on both axes. Pick two different groups.")
            return
        super().accept()

    def apply(self):
        st = self.state
        st.matching = self.matching.currentData()
        st.cell_fields = [self.fields.item(i).text() for i in range(self.fields.count())
                          if self.fields.item(i).checkState() == Qt.Checked]
        if self.mode == ENTRY_TAG:
            st.entry_label = self.entry_label.currentData()
            if self.auto.isChecked():
                st.headers = None
            else:
                st.headers = [frozenset(self.headers.item(i).data(Qt.UserRole))
                              for i in range(self.headers.count())
                              if self.headers.item(i).checkState() == Qt.Checked]
        elif self.mode == TAG_TAG:
            st.row_group = self.rows.currentText()
            st.col_group = self.cols.currentText()


# ==========================================================================
# Token filter
# ==========================================================================

class TokenFilterDialog(QDialog):
    """Pick tags (any within a group, all across groups), speakers and dates."""

    def __init__(self, parent, db: Database, tf: mx.TokenFilter):
        super().__init__(parent)
        self.db, self.tf = db, tf
        self.setWindowTitle("Filter tokens")
        self.resize(520, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tick tags to show only tokens that have them. Within a group, any "
                             "ticked tag matches; across groups, all must match."))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        seen = set()
        for path, g in db.settings.tags.all_leaf_groups():
            key = group_path(path)
            if key in seen:
                continue
            seen.add(key)
            gi = QTreeWidgetItem([key])
            gi.setData(0, Qt.UserRole, key)
            for t in g.tags:
                ti = QTreeWidgetItem([f"{t.display()}   {t.name if t.display() != t.name else ''}"])
                ti.setData(0, Qt.UserRole, t.name)
                ti.setFlags(ti.flags() | Qt.ItemIsUserCheckable)
                ti.setCheckState(0, Qt.Checked if t.name in tf.tags.get(key, set()) else Qt.Unchecked)
                gi.addChild(ti)
            self.tree.addTopLevelItem(gi)
            gi.setExpanded(bool(tf.tags.get(key)))
        lay.addWidget(self.tree, 1)
        self.citation = QCheckBox("Citation tokens only")
        self.citation.setChecked(tf.citation_only)
        lay.addWidget(self.citation)
        row = QHBoxLayout()
        self.speakers = QListWidget()
        for code in sorted({t.speaker for e in db.entries for t in e.tokens if t.speaker}
                           | set(db.participant_codes())):
            it = QListWidgetItem(code)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if code in tf.speakers else Qt.Unchecked)
            self.speakers.addItem(it)
        self.dates = QListWidget()
        for d in sorted({t.collected for e in db.entries for t in e.tokens if t.collected}, reverse=True):
            it = QListWidgetItem(d)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if d in tf.dates else Qt.Unchecked)
            self.dates.addItem(it)
        for title, w in (("Speakers", self.speakers), ("Collection dates", self.dates)):
            col = QVBoxLayout()
            col.addWidget(QLabel(title))
            col.addWidget(w)
            row.addLayout(col)
        lay.addLayout(row)
        b = _buttons(self)
        clear = b.addButton("Clear all", QDialogButtonBox.ResetRole)
        clear.clicked.connect(self._clear)
        lay.addWidget(b)

    def _clear(self):
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                g.child(j).setCheckState(0, Qt.Unchecked)
        for lw in (self.speakers, self.dates):
            for i in range(lw.count()):
                lw.item(i).setCheckState(Qt.Unchecked)
        self.citation.setChecked(False)

    def apply(self):
        tf = self.tf
        tf.tags = {}
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            picked = {g.child(j).data(0, Qt.UserRole) for j in range(g.childCount())
                      if g.child(j).checkState(0) == Qt.Checked}
            if picked:
                tf.tags[g.data(0, Qt.UserRole)] = picked
        tf.citation_only = self.citation.isChecked()
        tf.speakers = {self.speakers.item(i).text() for i in range(self.speakers.count())
                       if self.speakers.item(i).checkState() == Qt.Checked}
        tf.dates = {self.dates.item(i).text() for i in range(self.dates.count())
                    if self.dates.item(i).checkState() == Qt.Checked}


# ==========================================================================
# Tag structure editor
# ==========================================================================

KIND_WC, KIND_ALL, KIND_GROUP, KIND_TAG = "word class", "all classes", "group", "tag"


class TagStructureDialog(QDialog):
    """Edit word classes, groups (nested) and tags, with codes and defaults."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Tag structure")
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Word classes, then groups, then tags. A token takes at most one tag from "
                             "each group. The order here is the tag order in file names.\n"
                             "Double-click a name, code or description to edit it. A group's default "
                             "has no code and adds nothing to file names."))
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Code", "Default", "Description"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._changed)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for text, fn in (("Add word class", self._add_wc), ("Add group", self._add_group),
                         ("Add tag", self._add_tag), ("Delete", self._delete),
                         ("Move up", lambda: self._move(-1)), ("Move down", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(_buttons(self))
        self._fill()

    # tree <-> structure ------------------------------------------------
    def _item(self, kind, name, code="", default=False, desc=""):
        it = QTreeWidgetItem([name, code if kind == KIND_TAG else "", "", desc])
        it.setData(0, Qt.UserRole, kind)
        it.setData(0, Qt.UserRole + 1, name)          # original name, to follow renames
        flags = it.flags()
        if kind != KIND_ALL:
            flags |= Qt.ItemIsEditable
        it.setFlags(flags)
        if kind == KIND_TAG:
            it.setCheckState(2, Qt.Checked if default else Qt.Unchecked)
        if kind in (KIND_WC, KIND_ALL):
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
        return it

    def _fill_group(self, parent_item, g: Group):
        gi = self._item(KIND_GROUP, g.name)
        parent_item.addChild(gi)
        for t in g.tags:
            gi.addChild(self._item(KIND_TAG, t.name, t.code, t.default, t.description))
        for sub in g.groups:
            self._fill_group(gi, sub)

    def _fill(self):
        self.tree.blockSignals(True)
        ts = self.db.settings.tags
        for wc in ts.word_classes:
            wi = self._item(KIND_WC, wc.name)
            self.tree.addTopLevelItem(wi)
            for g in wc.groups:
                self._fill_group(wi, g)
        ai = self._item(KIND_ALL, "All classes")
        self.tree.addTopLevelItem(ai)
        for g in ts.all_classes:
            self._fill_group(ai, g)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _read_group(self, gi) -> Group:
        g = Group(nfc(gi.text(0).strip()))
        for i in range(gi.childCount()):
            c = gi.child(i)
            if c.data(0, Qt.UserRole) == KIND_TAG:
                default = c.checkState(2) == Qt.Checked
                g.tags.append(Tag(nfc(c.text(0).strip()), "" if default else nfc(c.text(1).strip()),
                                  default, nfc(c.text(3).strip())))
            else:
                g.groups.append(self._read_group(c))
        return g

    def structure(self):
        from ..model import TagStructure
        ts = TagStructure()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            groups = [self._read_group(top.child(j)) for j in range(top.childCount())]
            if top.data(0, Qt.UserRole) == KIND_ALL:
                ts.all_classes = groups
            else:
                ts.word_classes.append(WordClass(nfc(top.text(0).strip()), groups))
        return ts

    def renames(self) -> tuple[dict[str, str], dict[str, str]]:
        """(tag renames, word-class renames) made in this dialogue: old name -> new name."""
        tags, classes = {}, {}

        def walk(item):
            kind = item.data(0, Qt.UserRole)
            old, new = item.data(0, Qt.UserRole + 1), nfc(item.text(0).strip())
            if old and old != new:
                if kind == KIND_TAG:
                    tags[old] = new
                elif kind == KIND_WC:
                    classes[old] = new
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return tags, classes

    # editing -----------------------------------------------------------
    def _changed(self, item, column):
        kind = item.data(0, Qt.UserRole)
        if kind != KIND_TAG:
            return
        self.tree.blockSignals(True)
        if column == 2 and item.checkState(2) == Qt.Checked:
            parent = item.parent()
            for i in range(parent.childCount()):
                sib = parent.child(i)
                if sib is not item and sib.data(0, Qt.UserRole) == KIND_TAG:
                    sib.setCheckState(2, Qt.Unchecked)
            item.setText(1, "")
        if column in (0, 1) and (forbidden_in(item.text(1)) or "," in item.text(0)):
            QMessageBox.warning(self, "Tag structure", "Codes can't contain / \\ : * ? \" < > |, "
                                "and tag names can't contain commas.")
            item.setText(1, "".join(c for c in item.text(1) if not forbidden_in(c)))
            item.setText(0, item.text(0).replace(",", ""))
        self.tree.blockSignals(False)

    def _selected(self):
        return self.tree.currentItem()

    def _add_wc(self):
        name, ok = QInputDialog.getText(self, "Add word class", "Name (e.g. NUMERAL):")
        if ok and name.strip():
            idx = self.tree.topLevelItemCount() - 1
            it = self._item(KIND_WC, name.strip())
            self.tree.insertTopLevelItem(max(idx, 0), it)
            self.tree.setCurrentItem(it)

    def _add_group(self):
        cur = self._selected()
        if cur is None:
            return
        while cur.data(0, Qt.UserRole) == KIND_TAG:
            cur = cur.parent()
        name, ok = QInputDialog.getText(self, "Add group", "Group name:")
        if ok and name.strip():
            it = self._item(KIND_GROUP, name.strip())
            cur.addChild(it)
            cur.setExpanded(True)
            self.tree.setCurrentItem(it)

    def _add_tag(self):
        cur = self._selected()
        if cur is None:
            return
        if cur.data(0, Qt.UserRole) == KIND_TAG:
            cur = cur.parent()
        if cur.data(0, Qt.UserRole) != KIND_GROUP:
            QMessageBox.information(self, "Add tag", "Select a group first: tags always belong to a group.")
            return
        name, ok = QInputDialog.getText(self, "Add tag", "Tag name:")
        if ok and name.strip():
            it = self._item(KIND_TAG, name.strip().replace(",", ""), name.strip()[:6].upper())
            cur.addChild(it)
            cur.setExpanded(True)
            self.tree.setCurrentItem(it)

    def _used(self, names: set[str]) -> int:
        return sum(1 for e in self.db.entries for t in e.tokens if names & set(t.tags))

    def _names_under(self, item) -> set[str]:
        out = set()
        if item.data(0, Qt.UserRole) == KIND_TAG:
            out.add(item.text(0))
        for i in range(item.childCount()):
            out |= self._names_under(item.child(i))
        return out

    def _delete(self):
        cur = self._selected()
        if cur is None or cur.data(0, Qt.UserRole) == KIND_ALL:
            return
        names = self._names_under(cur)
        n = self._used(names)
        if cur.data(0, Qt.UserRole) == KIND_WC:
            n += sum(1 for e in self.db.entries if self.db.word_class(e) == cur.text(0))
        msg = f"Delete {cur.data(0, Qt.UserRole)} “{cur.text(0)}”?"
        if n:
            msg += f"\n{n} entries or tokens still use it; their tags are kept but no longer recognised."
        if QMessageBox.question(self, "Delete", msg) != QMessageBox.Yes:
            return
        parent = cur.parent()
        if parent:
            parent.removeChild(cur)
        else:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(cur))

    def _move(self, step):
        cur = self._selected()
        if cur is None or cur.data(0, Qt.UserRole) == KIND_ALL:
            return
        parent = cur.parent()
        if parent:
            i = parent.indexOfChild(cur)
            j = i + step
            if 0 <= j < parent.childCount():
                parent.takeChild(i)
                parent.insertChild(j, cur)
        else:
            i = self.tree.indexOfTopLevelItem(cur)
            j = i + step
            if 0 <= j < self.tree.topLevelItemCount() - 1:     # All classes stays last
                self.tree.takeTopLevelItem(i)
                self.tree.insertTopLevelItem(j, cur)
        self.tree.setCurrentItem(cur)
        cur.setExpanded(True)

    def accept(self):
        ts = self.structure()
        for _, g in ts.all_leaf_groups():
            names = [t.name for t in g.tags]
            if len(set(names)) != len(names):
                QMessageBox.warning(self, "Tag structure", f"The group “{g.name}” has two tags with the same name.")
                return
            for t in g.tags:
                if not t.default and not t.code:
                    QMessageBox.warning(self, "Tag structure",
                                        f"“{t.name}” needs a code. Only a group's default can be without one.")
                    return
        dups = ts.duplicate_codes()
        if dups and QMessageBox.question(self, "Tag structure", "Some codes are shared, so file names "
                                         "couldn't be told apart:\n" + "\n".join(dups) +
                                         "\n\nKeep them anyway?") != QMessageBox.Yes:
            return
        super().accept()
