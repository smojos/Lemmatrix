# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Smaller dialogues: entries, metadata, preferences, display setup, filters, tags."""

from __future__ import annotations

import re

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget, QInputDialog)

from ..model import (Database, Entry, Group, Tag, forbidden_in, nfc)
from . import spellui, theme
from .widgets import ipa_font


def _buttons(dlg) -> QDialogButtonBox:
    b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    b.accepted.connect(dlg.accept)
    b.rejected.connect(dlg.reject)
    return b


class PathEdit(QWidget):
    """A path in a text box with a Browse… button."""

    def __init__(self, text: str, folder: bool, title: str, parent=None):
        super().__init__(parent)
        self.folder, self.title = folder, title
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(text)
        self.edit.setMinimumWidth(300)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda *_: self._browse())
        lay.addWidget(self.edit, 1)
        lay.addWidget(browse)

    def setToolTip(self, tip):
        self.edit.setToolTip(tip)

    def text(self) -> str:
        return self.edit.text()

    def _browse(self):
        from PySide6.QtWidgets import QFileDialog
        start = self.edit.text() or str(Path.home())
        if self.folder:
            path = QFileDialog.getExistingDirectory(self, self.title, start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.title, str(Path(start).parent))
        if path:
            self.edit.setText(QDir.toNativeSeparators(path))


class ColourButton(QWidget):
    """A colour square to click for a colour chooser, with a Default button."""

    def __init__(self, colour: str, default: str, tip: str = "", parent=None):
        super().__init__(parent)
        self._colour, self._default = QColor(colour), default
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.swatch = QPushButton()
        self.swatch.setFixedSize(44, 24)
        self.swatch.setToolTip((tip + "\n" if tip else "") + "Click to choose another colour")
        self.swatch.clicked.connect(lambda *_: self._choose())
        reset = QPushButton("Default")
        reset.clicked.connect(lambda *_: self.set_colour(QColor(self._default)))
        lay.addWidget(self.swatch)
        lay.addWidget(reset)
        lay.addStretch(1)
        self.set_colour(self._colour)

    def set_colour(self, c: QColor):
        if c.isValid():
            self._colour = QColor(c)
        self.swatch.setStyleSheet(f"QPushButton {{ background: {self._colour.name()}; "
                                  "border: 1px solid #777; border-radius: 3px; }")

    def _choose(self):
        c = QColorDialog.getColor(self._colour, self, "Choose a colour")
        if c.isValid():
            self.set_colour(c)

    def colour(self) -> str:
        return self._colour.name()


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
        for c in s.categories():                    # lemma categories (not the utterances')
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
        others = []                                 # second languages: under Other languages (idea 19)
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    ed = NoForbidden() if (lang == s.primary_gloss and not entry) else QLineEdit()
                    ed.setText(entry.get(f.name, lang) if entry else "")
                    if f.role == "gloss" and lang == "en":           # red lines under unknown words
                        spellui.attach(ed, getattr(parent, "speller", None))
                    if lang == s.primary_gloss:
                        form.addRow(f"{f.title} ({lang})", ed)
                    else:
                        others.append((f"{f.title} ({lang})", ed))
                    self.fields[(f.name, lang)] = ed
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
        self.others_btn = None
        if others:
            self.others_btn = QToolButton()
            self.others_btn.setCheckable(True)
            self.others_btn.setAutoRaise(True)
            self.others_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            langs = [lang for lang in s.gloss_languages if lang != s.primary_gloss]
            self.others_btn.setText(f"Other languages ({', '.join(langs)})")
            self.others_btn.setToolTip("Glosses in the database's other gloss languages: they help "
                                       "speakers understand (e.g. in EλICIT requests)")
            form.addRow(self.others_btn)
            self.other_rows = []
            for label, ed in others:
                form.addRow(label, ed)
                self.other_rows.append(ed)
            prefs = getattr(parent, "prefs", None)

            def show(on, remember=True):
                self.others_btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
                for w in self.other_rows:
                    form.setRowVisible(w, on)
                if remember and prefs is not None:
                    prefs.set_value("dialogs/other_languages", bool(on))
            shown = prefs.get_bool("dialogs/other_languages", False) if prefs is not None else False
            self.others_btn.setChecked(shown)
            self.others_btn.toggled.connect(show)
            show(shown, remember=False)
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
        if self.entry is None and self.db.ref_taken(ref):
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
            if f.closed and text.strip():
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

class RenameDatabaseDialog(QDialog):
    """File → Rename database: the database's name (in the title) and its file name together."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        from .. import layout
        self.layout_ = layout
        self.db = db
        self.old = Path(db.path)
        self.setWindowTitle("Rename database")
        md = db.metadata
        self.name = QLineEdit(md.name)
        self.name.setToolTip("The database's own name, shown in the title (Edit → Metadata)")
        self.stem = QLineEdit(self.old.stem)
        self.stem.setToolTip("The database's file name. Its notebook and automatic backups follow it.")
        self._follow = True                       # the file name follows the name until edited
        self.name.textEdited.connect(self._name_edited)
        self.stem.textEdited.connect(self._stem_edited)
        self.note = QLabel()
        self.note.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("File name", self.stem)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Rename")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.resize(460, self.sizeHint().height())
        self._update()

    def _name_edited(self, text):
        if self._follow:
            md = self.db.metadata
            self.stem.setText(self.layout_.suggested_stem(self.old.stem, md.name, text.strip(),
                                                          md.language_code, md.variety_code))
        self._update()

    def _stem_edited(self, _):
        self._follow = False
        self._update()

    def new_name(self) -> str:
        return nfc(self.name.text().strip())

    def new_stem(self) -> str:
        return nfc(self.stem.text())

    def _update(self):
        ok_btn = self.buttons.button(QDialogButtonBox.Ok)
        stem = self.new_stem()
        changed = stem != self.old.stem or self.new_name() != self.db.metadata.name
        try:
            plan = self.layout_.rename_plan(self.old, stem) if stem != self.old.stem else []
        except self.layout_.RenameError as exc:
            self.note.setText(str(exc))
            ok_btn.setEnabled(False)
            return
        if not plan:
            self.note.setText("The file name stays the same." if changed else "")
        else:
            parts = [f"{self.old.name} → {plan[0][1].name}"]
            nb = [d for s, d in plan[1:] if s.parent == self.old.parent]
            if nb:
                parts.append(f"the notebook → {nb[0].name}")
            backups = len(plan) - 1 - len(nb)
            if backups:
                parts.append(f"{backups} automatic backup{'s' if backups != 1 else ''} in Backups")
            self.note.setText("Renames " + "; ".join(parts) + ". The window's settings and the "
                              "full-backup reminder follow.")
        ok_btn.setEnabled(changed)


class MetadataDialog(QDialog):
    """Language, variety, the database's name, author, description and gloss languages.

    Researchers, participants and locations are lists: Edit → Lists."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        md = db.metadata
        self.setWindowTitle("Database metadata")
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.lang_code = NoForbidden(md.language_code)
        self.lang_name = QLineEdit(md.language_name)
        self.var_code = NoForbidden(md.variety_code)
        self.var_name = QLineEdit(md.variety_name)
        self.db_name = QLineEdit(md.name)
        self.db_name.setPlaceholderText("e.g. Complete Lexicon")
        self.db_name.setToolTip("The database's own name, shown at the top of the window with the language "
                                "and variety. It isn't the file name.")
        self.author = QLineEdit(md.author)
        self.author.setToolTip("Who owns this database. The researchers of each session are in "
                               "Edit → Lists → Researchers.")
        self.description = QLineEdit(md.description)
        form.addRow("Language code", self.lang_code)
        form.addRow("Language name", self.lang_name)
        form.addRow("Variety code", self.var_code)
        form.addRow("Variety name", self.var_name)
        form.addRow("Database name", self.db_name)
        form.addRow("Author / owner", self.author)
        form.addRow("Description", self.description)
        self.glosses = QLineEdit(" ".join(db.settings.gloss_languages))
        self.glosses.setToolTip("Gloss languages, separated by spaces; the first is the primary one (the "
                                "language of the analysis). The others are second languages, to help "
                                "speakers understand (e.g. in EλICIT requests): hidden everywhere until a "
                                "column, a cell line or a dialogue's Other languages is set to show them.")
        form.addRow("Gloss languages", self.glosses)
        lay.addLayout(form)
        note = QLabel("Researchers, participants (speakers) and locations: Edit → Lists.")
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
        # Consent forms and other documentation live in the main folder's Documentation folder
        from .. import layout
        self.docs_btn = QPushButton("Open documentation folder")
        if db.path:
            where = QDir.toNativeSeparators(str(layout.documentation_folder(db.path)))
            self.docs_btn.setToolTip(f"Consent forms and other documentation:\n{where}")
        else:
            self.docs_btn.setEnabled(False)
            self.docs_btn.setToolTip("Save the database first: the Documentation folder is next to it")
        self.docs_btn.clicked.connect(lambda *_: self.open_documentation())
        self.images_btn = QPushButton("Open images folder")
        if db.path:
            where = QDir.toNativeSeparators(str(layout.images_folder(db.path)))
            self.images_btn.setToolTip("Pictures for EλICIT requests, named by the token's reference and tag "
                                       "codes: D001.jpg for a citation token, D001_PL.jpg for its plural "
                                       f"(JPG, PNG or GIF). Never shown in Lemmatrix.\n{where}")
        else:
            self.images_btn.setEnabled(False)
            self.images_btn.setToolTip("Save the database first: the Images folder is next to it")
        self.images_btn.clicked.connect(lambda *_: self.open_folder(layout.images_folder(self.db.path), "Images"))
        row = QHBoxLayout()
        row.addWidget(self.docs_btn)
        row.addWidget(self.images_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        lay.addWidget(_buttons(self))

    def open_documentation(self):
        """Open the Documentation folder (made if it isn't there yet) in the file manager."""
        from .. import layout
        self.open_folder(layout.documentation_folder(self.db.path), "Documentation")

    def open_folder(self, folder, name: str):
        """Open a folder of the main folder (made if it isn't there yet) in the file manager."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, name, f"Couldn't make the {name} folder: {exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def accept(self):
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
        md.name = nfc(self.db_name.text().strip())
        md.author = nfc(self.author.text().strip())
        md.description = nfc(self.description.text().strip())
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
        self.resize(640, 500)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        self.pattern = QLineEdit(s.filename_pattern)
        self.pattern.setToolTip("Placeholders: {language} {variety} {speaker} {reference} {gloss} "
                                "{tags} {date}, or any field name. A separator before an empty part "
                                "is left out.")
        self.utt_pattern = QLineEdit(s.utterance_pattern)
        self.utt_pattern.setToolTip("Utterances' recordings (in Soundfiles\\Utterances). {label} is the "
                                    "utterance's file label; utterances have no tags in their file names.")
        self.text_pattern = QLineEdit(s.text_pattern)
        self.text_pattern.setToolTip("Texts' and songs' recordings and TextGrids (in Soundfiles\\Texts). "
                                     "{title} is the title as it was when the text was added.")
        self.padding = QSpinBox()
        self.padding.setRange(0, 2000)
        self.padding.setSuffix(" ms")
        self.padding.setValue(s.clip_padding)
        self.padding.setToolTip("How much of the text's recording a clipped utterance keeps either side "
                                "of its line")
        self.separator = QLineEdit(s.tag_separator)
        self.separator.setMaxLength(3)
        self.praat = PathEdit(prefs.praat_path, folder=False, title="Where is Praat?")
        self.praat.setToolTip("The Praat program, used by Open in Praat (Praat.exe on Windows)")
        self.praat.edit.setPlaceholderText("not found: click Browse to show where Praat is")
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
        self.unusual = QCheckBox("Mark tags that aren't usual for their lemma's word class")
        self.unusual.setToolTip("A dashed amber outline on the tag's chip, and a note in the token "
                                "dialogue and bulk edit. Any tag can still go on any token.\n"
                                "“Don't show this again” on the note turns this off.")
        self.unusual.setChecked(prefs.warn_unusual_tags)
        self.spelling = QCheckBox("Underline English words that may be misspelled")
        self.spelling.setToolTip("Red wavy lines in the English glosses and translations (lemma list, "
                                 "All data, the token and lemma dialogues). Tools → Check spelling "
                                 "works either way.")
        self.spelling.setChecked(prefs.underline_spelling)
        self.autosave = QSpinBox()
        self.autosave.setRange(0, 120)
        self.autosave.setSuffix(" min")
        self.autosave.setSpecialValueText("off")
        self.autosave.setValue(prefs.autosave_minutes)
        self.ipa = QSpinBox()
        self.ipa.setRange(8, 30)
        self.ipa.setValue(prefs.ipa_size)
        self.theme = QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.setCurrentIndex(max(0, self.theme.findData(prefs.theme)))
        self.theme.setToolTip("Light or dark, for the whole program")
        self.accent = ColourButton(prefs.accent, theme.DEFAULT_ACCENT,
                                   "Selected tabs, highlights, tag chips and pitch traces")
        from .. import pitchsound
        self.voice = QComboBox()
        for key, label in pitchsound.VOICES.items():
            self.voice.addItem(label, key)
        self.voice.setItemData(0, "A robotic buzz that follows the trace exactly", Qt.ToolTipRole)
        self.voice.setItemData(1, "A human-like hum: mmm mmm mmm", Qt.ToolTipRole)
        self.voice.setItemData(2, "A human-like whistle", Qt.ToolTipRole)
        self.voice.setCurrentIndex(max(0, self.voice.findData(prefs.pitch_voice)))
        listen = QPushButton("Listen")
        listen.setToolTip("Play an example (22 4:42 , 1:4 55) in this voice")
        listen.clicked.connect(lambda *_: self._listen())
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(prefs.pitch_volume)
        self.volume.setFixedWidth(180)
        vol_label = QLabel(f"{prefs.pitch_volume}%")
        vol_label.setMinimumWidth(40)
        self.volume.valueChanged.connect(lambda v: vol_label.setText(f"{v}%"))
        volume_row = QWidget()
        vl = QHBoxLayout(volume_row)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self.volume)
        vl.addWidget(vol_label)
        vl.addStretch(1)
        self.backups = PathEdit(prefs.full_backup_folder, folder=True, title="Folder for full backups")
        self.backups.edit.setPlaceholderText("Documents")
        self.backups.setToolTip("Where File → Full backup offers to save the zip of the database's "
                                "whole folder: a cloud folder or another drive, say (never inside the "
                                "database's own folder).\nThe automatic backups made on each save always "
                                "go in the Backups folder next to the database.")
        voice_row = QWidget()
        vr = QHBoxLayout(voice_row)
        vr.setContentsMargins(0, 0, 0, 0)
        vr.addWidget(self.voice)
        vr.addWidget(listen)
        vr.addStretch(1)

        def page(title, sections):
            w = QWidget()
            v = QVBoxLayout(w)
            for heading, rows in sections:
                box = QGroupBox(heading)
                f = QFormLayout(box)
                for label, widget in rows:
                    if label:
                        f.addRow(label, widget)
                    else:
                        f.addRow(widget)
                v.addWidget(box)
            v.addStretch(1)
            tabs.addTab(w, title)

        page("General", [("This computer", [("Autosave every", self.autosave),
                                            ("Full backup folder", self.backups)]),
                         ("Warnings (this computer)", [(None, self.unusual), (None, self.spelling), (None, self.confirm)])])
        page("Sound", [
            ("This database", [("File name pattern", self.pattern), ("Tag separator", self.separator),
                               ("Utterance file names", self.utt_pattern),
                               ("Text file names", self.text_pattern),
                               ("Clips keep either side", self.padding),
                               (None, self.auto_names)]),
            ("This computer", [("Recording source", self.source), ("Bit depth", self.bits),
                               ("Sample rate", self.rate), (None, self.with_tokens),
                               ("Path to Praat", self.praat)])])
        page("Display", [("This computer", [("Theme", self.theme), ("Accent colour", self.accent),
                                            ("IPA font size", self.ipa)])])
        page("Pitch", [("This database", [("Lowest pitch digit", self.low),
                                          ("Highest pitch digit", self.high)]),
                       ("This computer", [("Pitch playback", voice_row),
                                          ("Playback volume", volume_row)])])
        lay.addWidget(_buttons(self))

    def _listen(self):
        from .. import audio, pitchsound
        main = self.parent()
        player = getattr(main, "player", None)
        if player is None:
            return
        samples = pitchsound.synthesise("22 4:42 , 1:4 55", self.low.value(), max(self.high.value(),
                                        self.low.value() + 1), self.voice.currentData(),
                                        volume=self.volume.value() / 100)
        try:
            player.play_samples(samples, pitchsound.RATE)
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Listen", str(exc))

    def accept(self):
        if self.low.value() >= self.high.value():
            QMessageBox.warning(self, "Settings", "The lowest pitch digit must be below the highest.")
            return
        if "{" not in self.pattern.text() or "{" not in self.utt_pattern.text():
            QMessageBox.warning(self, "Settings", "The file name pattern needs at least one placeholder.")
            return
        if "{reference}" not in self.text_pattern.text():
            QMessageBox.warning(self, "Settings", "Text file names need {reference}: it is what tells "
                                "them apart.")
            return
        if "{reference}" not in self.utt_pattern.text():
            QMessageBox.warning(self, "Settings", "Utterance file names need {reference}: it is what tells "
                                "them apart.")
            return
        bad = forbidden_in(self.separator.text())
        if bad:
            QMessageBox.warning(self, "Settings", f"The separator can't contain {bad}.")
            return
        super().accept()

    def apply(self) -> bool:
        """Apply the values. Returns True if file names may have changed."""
        s = self.db.settings
        old = (s.filename_pattern, s.tag_separator, s.utterance_pattern, s.text_pattern)
        s.filename_pattern = self.pattern.text().strip()
        s.utterance_pattern = self.utt_pattern.text().strip()
        s.text_pattern = self.text_pattern.text().strip()
        s.clip_padding = self.padding.value()
        s.tag_separator = self.separator.text()
        s.auto_update_names = self.auto_names.isChecked()
        s.pitch_low, s.pitch_high = self.low.value(), self.high.value()
        p = self.prefs
        p.record_source = self.source.currentData()
        p.bit_depth = self.bits.currentData()
        p.sample_rate = self.rate.currentData()
        p.delete_recordings_with_tokens = self.with_tokens.isChecked()
        p.confirm_delete = self.confirm.isChecked()
        p.warn_unusual_tags = self.unusual.isChecked()
        p.underline_spelling = self.spelling.isChecked()
        p.autosave_minutes = self.autosave.value()
        p.ipa_size = self.ipa.value()
        p.theme = self.theme.currentData()
        p.accent = self.accent.colour()
        p.praat_path = self.praat.text().strip()
        p.pitch_voice = self.voice.currentData()
        p.pitch_volume = self.volume.value()
        p.full_backup_folder = self.backups.text().strip()
        return old != (s.filename_pattern, s.tag_separator, s.utterance_pattern, s.text_pattern)


# ==========================================================================
# Tag structure editor
# ==========================================================================

KIND_GROUP, KIND_TAG = "group", "tag"
NAME, CODE, DEFAULT, USUAL, DESC = range(5)
USUAL_ROLE = Qt.UserRole + 2                  # a group's own "usual for" word classes
ONLY_ROLE = Qt.UserRole + 3                   # a group marked "utterances only" (a rule, inherited)


class UsualDialog(QDialog):
    """Which word classes a tag group is usual for (none ticked: its parent's, or every lemma)."""

    def __init__(self, parent, group: str, classes: list, chosen: list[str], inherited: tuple,
                 only: bool = False, inherited_only: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Usual for")
        lay = QVBoxLayout(self)
        self.only = QCheckBox("Utterances only: its tags go on utterances, never on lemma tokens")
        self.only.setToolTip("A rule, not a hint: the token dialogue doesn't offer these tags for lemmas. "
                             "Its sub-groups are for utterances only too.")
        self.only.setChecked(only or inherited_only)
        self.only.setEnabled(not inherited_only)
        if inherited_only:
            self.only.setText(self.only.text() + " (as its parent group)")
        lay.addWidget(self.only)
        note = QLabel(f"Which word classes is “{group}” usual for? Its groups are shown first in the "
                      "token dialogue for lemmas of these classes, their defaults go on new tokens, and "
                      "on other lemmas its tags are marked as unusual (they're still allowed). A class "
                      "includes the classes nested under it in the Word Class list.\n\n"
                      + ("Nothing ticked: as its parent group (" + ", ".join(inherited) + ")."
                         if inherited else "Nothing ticked: usual for every lemma."))
        note.setWordWrap(True)
        lay.addWidget(note)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        lay.addWidget(self.tree, 1)
        known = set()

        def add(parent, item):
            it = QTreeWidgetItem([item.name])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if item.name in chosen else Qt.Unchecked)
            known.add(item.name)
            (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
            for c in item.children:
                add(it, c)
        for item in classes:
            add(None, item)
        for name in chosen:                       # a class since removed from the list
            if name not in known:
                it = QTreeWidgetItem([f"{name}  (no longer in the Word Class list)"])
                it.setData(0, Qt.UserRole, name)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setForeground(0, QBrush(theme.colour("dim")))
                self.tree.addTopLevelItem(it)
        self.tree.expandAll()
        if not classes:
            lay.addWidget(QLabel("The Word Class list is empty: add classes in Edit → Lists → Word Class."))
        self.only.toggled.connect(lambda on: self.tree.setEnabled(not on))
        self.tree.setEnabled(not self.only.isChecked())
        lay.addWidget(_buttons(self))
        self.resize(460, 480)

    def utterances_only(self) -> bool:
        return self.only.isChecked() and self.only.isEnabled()

    def chosen(self) -> list[str]:
        out = []

        def walk(it):
            if it.checkState(0) == Qt.Checked:
                out.append(it.data(0, Qt.UserRole) or it.text(0))
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out


class TagStructureDialog(QDialog):
    """Edit the tag groups (nested), their tags, codes and defaults, and what they're usual for."""

    def __init__(self, parent, db: Database, word_classes=None):
        super().__init__(parent)
        self.db = db
        # () -> the Word Class list (ListItems); Edit → Lists passes its own, being edited
        self.word_classes = word_classes or (lambda: (db.settings.entry_field("word-class").items
                                                      if db.settings.entry_field("word-class") else []))
        self.setWindowTitle("Tag structure")
        self.resize(860, 640)
        lay = QVBoxLayout(self)
        intro = QLabel("Groups, then tags, organised however you like. Any tag can go on any token, but a "
                       "token takes at most one tag from each group. The order here is the tag order in "
                       "file names. Double-click a name, code or description to edit it; a group's "
                       "default has no code. “Usual for” is a hint: which word classes a group is for "
                       "(double-click it to choose); a group can also be for utterances only.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Name", "Code", "Default", "Usual for", "Description"])
        self.tree.header().setSectionResizeMode(NAME, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(USUAL, 170)
        self.tree.itemChanged.connect(self._changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        lay.addWidget(self.tree, 1)
        self.problem_note = QLabel()
        self.problem_note.setWordWrap(True)
        self.problem_note.setStyleSheet(f"color: {theme.colour('error_text').name()};")
        lay.addWidget(self.problem_note)
        row = QHBoxLayout()
        for text, fn, tip in (("Add group", self._add_top, "A new group at the top level"),
                              ("Add sub-group", self._add_group, "A new group inside the selected group"),
                              ("Add tag", self._add_tag, "A new tag in the selected group"),
                              ("Usual for…", self._choose_usual, "Which word classes the selected group is for"),
                              ("Delete", self._delete, ""), ("Move up", lambda: self._move(-1), ""),
                              ("Move down", lambda: self._move(1), "")):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
            row.addWidget(b)
        lay.addLayout(row)
        self.button_box = _buttons(self)
        lay.addWidget(self.button_box)
        self._fill()

    # tree <-> structure ------------------------------------------------
    def _item(self, kind, name, code="", default=False, desc="", usual=(), only=False):
        it = QTreeWidgetItem([name, code if kind == KIND_TAG else "", "", "", desc])
        it.setData(NAME, Qt.UserRole, kind)
        it.setData(NAME, Qt.UserRole + 1, name)          # original name, to follow renames
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        if kind == KIND_TAG:
            it.setCheckState(DEFAULT, Qt.Checked if default else Qt.Unchecked)
        else:
            it.setData(NAME, USUAL_ROLE, list(usual))
            it.setData(NAME, ONLY_ROLE, bool(only))
            f = it.font(NAME)
            f.setBold(True)
            it.setFont(NAME, f)
        return it

    def _fill_group(self, parent_item, g: Group):
        gi = self._item(KIND_GROUP, g.name, desc=g.description, usual=g.usual, only=g.utterances_only)
        if parent_item is None:
            self.tree.addTopLevelItem(gi)
        else:
            parent_item.addChild(gi)
        for t in g.tags:
            gi.addChild(self._item(KIND_TAG, t.name, t.code, t.default, t.description))
        for sub in g.groups:
            self._fill_group(gi, sub)

    def _fill(self, structure=None):
        self.tree.blockSignals(True)
        for g in (structure or self.db.settings.tags).groups:
            self._fill_group(None, g)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._show_usual()
        self._mark_problems()

    def load(self, structure):
        """Show this structure instead (Reset to defaults in Edit → Lists)."""
        self.tree.clear()
        self._deleted = set()
        self._fill(structure)

    def _tops(self):
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    # "usual for", shown on every group: its own (bold) or inherited (grey) ------
    def _show_usual(self):
        known = {i.name for top in self.word_classes() for i in top.walk()}
        self.tree.blockSignals(True)

        def walk(it, inherited, only_above=False):
            if it.data(NAME, Qt.UserRole) != KIND_GROUP:
                return
            own = it.data(NAME, USUAL_ROLE) or []
            only = bool(it.data(NAME, ONLY_ROLE))
            if only or only_above:
                it.setText(USUAL, "utterances only" if only else "(utterances only)")
                it.setForeground(USUAL, QBrush() if only else QBrush(theme.colour("dim")))
                it.setToolTip(USUAL, "Its tags go on utterances only, never on lemma tokens"
                              + ("" if only else " (as its parent group)") + ". Double-click to change.")
            elif own:
                missing = [c for c in own if c not in known]
                it.setText(USUAL, ", ".join(own))
                it.setForeground(USUAL, QBrush(theme.colour("error_text")) if missing else QBrush())
                it.setToolTip(USUAL, (f"{', '.join(missing)}: no longer in the Word Class list\n" if missing
                                      else "") + "Double-click to change")
            else:
                it.setText(USUAL, f"({', '.join(inherited)})" if inherited else "every lemma")
                it.setForeground(USUAL, QBrush(theme.colour("dim")))
                it.setToolTip(USUAL, "As its parent group; double-click to choose" if inherited
                              else "No hint: usual for every lemma. Double-click to choose word classes.")
            for i in range(it.childCount()):
                walk(it.child(i), tuple(own) or inherited, only or only_above)
        for top in self._tops():
            walk(top, ())
        self.tree.blockSignals(False)

    def _inherited(self, it) -> tuple:
        p = it.parent()
        while p is not None:
            own = p.data(NAME, USUAL_ROLE) or []
            if own:
                return tuple(own)
            p = p.parent()
        return ()

    def _double_clicked(self, item, column):
        if column == USUAL and item.data(NAME, Qt.UserRole) == KIND_GROUP:
            self._choose_usual(item)

    def _choose_usual(self, item=None):
        item = item or self._selected()
        while item is not None and item.data(NAME, Qt.UserRole) == KIND_TAG:
            item = item.parent()
        if item is None:
            QMessageBox.information(self, "Usual for", "Select a group first.")
            return
        above, p = False, item.parent()
        while p is not None:
            above = above or bool(p.data(NAME, ONLY_ROLE))
            p = p.parent()
        dlg = UsualDialog(self, item.text(NAME), self.word_classes(), item.data(NAME, USUAL_ROLE) or [],
                          self._inherited(item), bool(item.data(NAME, ONLY_ROLE)), above)
        if dlg.exec():
            item.setData(NAME, USUAL_ROLE, dlg.chosen())
            item.setData(NAME, ONLY_ROLE, dlg.utterances_only())
            self._show_usual()

    def refresh_usual(self):
        """The Word Class list changed (Edit → Lists): redraw the hints."""
        self._show_usual()

    def rename_classes(self, renames: dict[str, str]):
        """Follow word classes renamed in the Word Class list while this editor is open."""
        if not renames:
            return

        def walk(it):
            own = it.data(NAME, USUAL_ROLE)
            if own:
                it.setData(NAME, USUAL_ROLE, list(dict.fromkeys(renames.get(c, c) for c in own)))
            for i in range(it.childCount()):
                walk(it.child(i))
        for top in self._tops():
            walk(top)
        self._show_usual()

    # duplicate and missing names/codes, shown in red as you edit -----------
    def _tag_items(self, item=None) -> list:
        kids = self._tops() if item is None else [item.child(i) for i in range(item.childCount())]
        out = []
        for c in kids:
            if c.data(NAME, Qt.UserRole) == KIND_TAG:
                out.append(c)
            else:
                out += self._tag_items(c)
        return out

    def _problems(self) -> tuple[dict, dict, set]:
        """({item: why} for names, {item: why} for codes, items missing a code)."""
        bad_names, bad_codes, missing = {}, {}, set()
        by_name, by_code = {}, {}
        for it in self._tag_items():
            by_name.setdefault(nfc(it.text(NAME).strip()), []).append(it)
            default = it.checkState(DEFAULT) == Qt.Checked
            code = nfc(it.text(CODE).strip())
            if not default and not code:
                missing.add(id(it))
            if code and not default:
                by_code.setdefault(code, []).append(it)
        for name, its in by_name.items():
            if len(its) > 1:
                for it in its:
                    bad_names[id(it)] = f"{len(its)} tags are called “{name}”"
        for code, its in by_code.items():
            if len(its) > 1:
                for it in its:
                    bad_codes[id(it)] = f"{len(its)} tags share the code {code}"
        return bad_names, bad_codes, missing

    def _mark_problems(self):
        bad_names, bad_codes, missing = self._problems()
        red, pale = QBrush(theme.colour("error_text")), QBrush(theme.colour("error_fill"))
        self.tree.blockSignals(True)
        for it in self._tag_items():
            k = id(it)
            # None clears a colour (an empty QBrush would hide the text)
            it.setData(NAME, Qt.ForegroundRole, red if k in bad_names else None)
            it.setData(CODE, Qt.ForegroundRole, red if k in bad_codes else None)
            it.setData(CODE, Qt.BackgroundRole, pale if k in missing else None)
            f = it.font(NAME)
            f.setBold(k in bad_names)
            it.setFont(NAME, f)
            f = it.font(CODE)
            f.setBold(k in bad_codes)
            it.setFont(CODE, f)
            tips = [bad_names.get(k, ""), bad_codes.get(k, ""),
                    "This tag needs a code (only a group's default can be without one)" if k in missing else ""]
            tip = "\n".join(t for t in tips if t)
            it.setToolTip(NAME, tip)
            it.setToolTip(CODE, tip)
        self.tree.blockSignals(False)
        n = len(bad_names) + len(bad_codes) + len(missing)
        self.problem_note.setText("" if not n else
                                  "Red: tags with the same name or code, or a missing code. Tag names must "
                                  "be unique in the whole structure. Hover over them to see why.")

    def _read_group(self, gi) -> Group:
        g = Group(nfc(gi.text(NAME).strip()), usual=list(gi.data(NAME, USUAL_ROLE) or []),
                  utterances_only=bool(gi.data(NAME, ONLY_ROLE)), description=nfc(gi.text(DESC).strip()))
        for i in range(gi.childCount()):
            c = gi.child(i)
            if c.data(NAME, Qt.UserRole) == KIND_TAG:
                default = c.checkState(DEFAULT) == Qt.Checked
                g.tags.append(Tag(nfc(c.text(NAME).strip()), "" if default else nfc(c.text(CODE).strip()),
                                  default, nfc(c.text(DESC).strip())))
            else:
                g.groups.append(self._read_group(c))
        return g

    def structure(self):
        from ..model import TagStructure
        return TagStructure([self._read_group(top) for top in self._tops()])

    def renames(self) -> dict[str, str]:
        """Tags renamed in this dialogue: old name -> new name."""
        tags = {}
        for it in self._tag_items():
            old, new = it.data(NAME, Qt.UserRole + 1), nfc(it.text(NAME).strip())
            if old and old != new:
                tags[old] = new
        return tags

    # editing -----------------------------------------------------------
    def _changed(self, item, column):
        if item.data(NAME, Qt.UserRole) != KIND_TAG:
            return
        self.tree.blockSignals(True)
        if column == DEFAULT and item.checkState(DEFAULT) == Qt.Checked:
            parent = item.parent()
            for i in range(parent.childCount()):
                sib = parent.child(i)
                if sib is not item and sib.data(NAME, Qt.UserRole) == KIND_TAG:
                    sib.setCheckState(DEFAULT, Qt.Unchecked)
            item.setText(CODE, "")
        if column in (NAME, CODE) and (forbidden_in(item.text(CODE)) or "," in item.text(NAME)):
            QMessageBox.warning(self, "Tag structure", "Codes can't contain / \\ : * ? \" < > |, "
                                "and tag names can't contain commas.")
            item.setText(CODE, "".join(c for c in item.text(CODE) if not forbidden_in(c)))
            item.setText(NAME, item.text(NAME).replace(",", ""))
        self.tree.blockSignals(False)
        self._mark_problems()

    def _selected(self):
        return self.tree.currentItem()

    def _add_top(self):
        name, ok = QInputDialog.getText(self, "Add group", "Group name (e.g. Nominal):")
        if ok and name.strip():
            it = self._item(KIND_GROUP, name.strip())
            self.tree.addTopLevelItem(it)
            self.tree.setCurrentItem(it)
            self._show_usual()

    def _add_group(self):
        cur = self._selected()
        if cur is None:
            return self._add_top()
        while cur.data(NAME, Qt.UserRole) == KIND_TAG:
            cur = cur.parent()
        name, ok = QInputDialog.getText(self, "Add sub-group", f"Group name (inside “{cur.text(NAME)}”):")
        if ok and name.strip():
            it = self._item(KIND_GROUP, name.strip())
            cur.addChild(it)
            cur.setExpanded(True)
            self.tree.setCurrentItem(it)
            self._show_usual()

    def _add_tag(self):
        cur = self._selected()
        if cur is None:
            QMessageBox.information(self, "Add tag", "Select a group first: tags always belong to a group.")
            return
        if cur.data(NAME, Qt.UserRole) == KIND_TAG:
            cur = cur.parent()
        name, ok = QInputDialog.getText(self, "Add tag", "Tag name:")
        if ok and name.strip():
            it = self._item(KIND_TAG, name.strip().replace(",", ""), name.strip()[:6].upper())
            cur.addChild(it)
            cur.setExpanded(True)
            self.tree.setCurrentItem(it)
            self._mark_problems()

    def _used(self, names: set[str]) -> int:
        return sum(1 for _, t in self.db.all_tokens() if names & set(t.tags))   # utterances too

    def _names_under(self, item) -> set[str]:
        """The tags in item (a tag, or a group and everything in it), by the names tokens use."""
        out = set()
        if item.data(NAME, Qt.UserRole) == KIND_TAG:
            out.add(item.data(NAME, Qt.UserRole + 1) or item.text(NAME))
        for i in range(item.childCount()):
            out |= self._names_under(item.child(i))
        return out

    def deleted_tags(self) -> set[str]:
        """Tags deleted in this dialogue that tokens use: they're taken off those tokens."""
        gone = set(getattr(self, "_deleted", set()))
        if gone:                                      # (one added again with the same name stays)
            gone -= {it.data(NAME, Qt.UserRole + 1) for it in self._tag_items()}
            gone -= {nfc(it.text(NAME).strip()) for it in self._tag_items()}
        return gone

    def clashes(self, names: set[str]) -> list[str]:
        """Lemmas where taking these tags off would leave two tokens with the same tags."""
        gone = self.deleted_tags() | set(names)
        out = []
        for e in self.db.entries:                     # utterances have one token each
            if not any(gone & set(t.tags) for t in e.tokens):
                continue
            seen = {}
            for t in e.tokens:
                key = frozenset(x for x in t.tags if x not in gone)
                if key in seen:
                    what = self.db.settings.tags.display(sorted(key)) if key else "Citation"
                    out.append(f"{e.ref} {self.db.gloss(e)}: two tokens would both be {what}")
                    break
                seen[key] = t
        return out

    def _delete(self):
        cur = self._selected()
        if cur is None:
            return
        names = self._names_under(cur)
        n = self._used(names)
        what = f"{cur.data(NAME, Qt.UserRole)} “{cur.text(NAME)}”"
        if n:
            clash = self.clashes(names)
            if clash:
                QMessageBox.warning(self, "Delete", f"{what} can't be deleted yet: taking it off the tokens "
                                    "that use it would leave two tokens of a lemma with the same tags, so "
                                    "their recordings would get the same name:\n\n" + "\n".join(clash[:20])
                                    + (f"\n… and {len(clash) - 20} more" if len(clash) > 20 else "")
                                    + "\n\nGive those tokens other tags first (or delete one of each pair).")
                return
            msg = (f"{what} is used by {n} token{'s' if n != 1 else ''}. Delete it and take it off "
                   f"{'them' if n != 1 else 'it'}?\n\nTheir recordings' names change with their tags.")
        else:
            msg = f"Delete {what}?"
        if QMessageBox.question(self, "Delete", msg) != QMessageBox.Yes:
            return
        if n:
            self._deleted = self.deleted_tags() | {x for x in names if self._used({x})}
        parent = cur.parent()
        if parent:
            parent.removeChild(cur)
        else:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(cur))
        self._show_usual()
        self._mark_problems()

    def _move(self, step):
        cur = self._selected()
        if cur is None:
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
            if 0 <= j < self.tree.topLevelItemCount():
                self.tree.takeTopLevelItem(i)
                self.tree.insertTopLevelItem(j, cur)
        self.tree.setCurrentItem(cur)
        cur.setExpanded(True)

    def accept(self):
        if self.validate():
            super().accept()

    def validate(self) -> bool:
        """Check the structure before it's used: False (after saying why) if it can't be."""
        ts = self.structure()
        bad_names, _, _ = self._problems()
        if bad_names:
            QMessageBox.warning(self, "Tag structure", "Two tags have the same name (shown in red). Tokens "
                                "store tag names, so they couldn't be told apart:\n\n"
                                + "\n".join(sorted(set(bad_names.values()))))
            return False
        for t, _ in ts.tags():
            if not t.default and not t.code:
                QMessageBox.warning(self, "Tag structure",
                                    f"“{t.name}” needs a code. Only a group's default can be without one.")
                return False
        dups = ts.duplicate_codes()
        if dups and QMessageBox.question(self, "Tag structure", "Some codes are shared, so file names "
                                         "couldn't be told apart:\n" + "\n".join(dups) +
                                         "\n\nKeep them anyway?") != QMessageBox.Yes:
            return False
        return True
