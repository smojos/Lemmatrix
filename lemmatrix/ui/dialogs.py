"""Smaller dialogues: entries, metadata, preferences, display setup, filters, tags."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QInputDialog)

from ..model import (Database, Entry, Group, Participant, Tag, WordClass, forbidden_in, nfc)
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
            elif f.closed:
                cb = QComboBox()
                cb.setEditable(True)
                cb.setToolTip("Pick from the list, or type a new value to add it to the list")
                cb.addItem("")
                listed = f.all_values()
                cb.addItems(listed)
                extra = sorted({e.get(f.name) for e in db.entries if e.get(f.name)} - set(listed))
                cb.addItems(extra)
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
            if f.closed and f.role != "word-class" and text.strip():
                f.add_value(text.strip())
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

        self.low = QSpinBox()
        self.low.setRange(0, 9)
        self.low.setValue(s.pitch_low)
        self.high = QSpinBox()
        self.high.setRange(0, 9)
        self.high.setValue(s.pitch_high)

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
        self.with_tokens = QCheckBox("Delete recordings with their tokens (to the Recycle Bin)")
        self.with_tokens.setChecked(prefs.delete_recordings_with_tokens)
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
        def page(title, rows):
            w = QWidget()
            f = QFormLayout(w)
            for label, widget in rows:
                if label:
                    f.addRow(label, widget)
                else:
                    f.addRow(widget)
            tabs.addTab(w, title)

        page("Sound", [
            ("File name pattern", self.pattern), ("Tag separator", self.separator),
            ("Sound folder", self.folder), (None, self.auto_names),
            (None, QLabel("<b>On this computer</b>")),
            ("Recording source", self.source), ("Bit depth", self.bits), ("Sample rate", self.rate),
            (None, self.with_tokens), (None, self.confirm)])
        page("Display", [("Lowest pitch digit", self.low), ("Highest pitch digit", self.high),
                         ("IPA font size (this computer)", self.ipa)])
        page("General", [("Autosave every (this computer)", self.autosave)])
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
        p = self.prefs
        p.record_source = self.source.currentData()
        p.bit_depth = self.bits.currentData()
        p.sample_rate = self.rate.currentData()
        p.delete_recordings_with_tokens = self.with_tokens.isChecked()
        p.confirm_delete = self.confirm.isChecked()
        p.autosave_minutes = self.autosave.value()
        p.ipa_size = self.ipa.value()
        return old != (s.filename_pattern, s.tag_separator)


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
            b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
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
