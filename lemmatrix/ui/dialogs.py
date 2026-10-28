# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Smaller dialogues: entries, metadata, preferences, display setup, filters, tags."""

from __future__ import annotations

import re

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget, QInputDialog, QScrollArea, QFrame)

from ..model import (SEQUENCE, Database, Entry, Group, Tag, forbidden_in, nfc)
from . import keyboards
from . import widgets as _w  # (ask: buttons that say what they do)
from . import spellui, theme
from .widgets import caption, ipa_font, tip_abbreviated


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

MORE_KEY = "lemma_dialog/more"         # the workspace: the lemma fields behind the More arrow (idea 60)
MORE_OPEN = "dialogs/lemma_more"       # this computer: the arrow open or closed
OTHER_GLOSSES = "dialogs/lemma_other_glosses"   # this computer: the gloss's + open or closed
ALWAYS_SHOWN = ("lemma", "gloss", "word-class")


def default_more(db) -> list[str]:
    """Everything but Lemma, Gloss and Word Class starts behind the More arrow (Josh, 24 October)."""
    return [f.name for f in db.settings.entry_fields if f.role not in ALWAYS_SHOWN]


def more_fields(parent, db) -> set[str]:
    doc = getattr(parent, "doc", None)
    ws = getattr(doc, "ws", None) if doc is not None else None
    v = ws.get(MORE_KEY, None) if ws is not None else None
    names = [str(x) for x in v] if isinstance(v, list) else default_more(db)
    keep = {f.name for f in db.settings.entry_fields if f.role not in ALWAYS_SHOWN}
    return set(names) & keep


TOKEN_MORE_KEY = "token_dialog/more"   # the workspace: the token fields behind the dialogues' More arrow (idea 91)


def default_token_more(db) -> list[str]:
    """Constituents starts behind the token and utterance dialogues' More arrow (Josh, 28 October)."""
    return [f.name for f in db.settings.token_fields if f.role == "constituents"]


def token_more_fields(parent, db) -> set[str]:
    doc = getattr(parent, "doc", None)
    ws = getattr(doc, "ws", None) if doc is not None else None
    v = ws.get(TOKEN_MORE_KEY, None) if ws is not None else None
    names = [str(x) for x in v] if isinstance(v, list) else default_token_more(db)
    return set(names) & {f.name for f in db.settings.token_fields}


def _filled(w) -> bool:
    if isinstance(w, QComboBox):
        return bool(w.currentText().strip())
    if isinstance(w, QLineEdit):
        return bool(w.text().strip())
    return bool(getattr(w, "items", None))        # the From box's chips


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
            self.category.addItem(c.label, c.letter)
        self.ref = NoForbidden(entry.ref if entry else "")
        if entry:
            m = re.match(r"[A-Za-z]+", entry.ref)
            letter = m.group(0) if m else ""
            i = self.category.findData(letter)
            self.category.setCurrentIndex(max(0, i))
            self.category.setEnabled(False)
            self.ref.setReadOnly(True)
            self.ref.setToolTip("References never change, because they're part of soundfile names.")
        else:
            self.category.currentIndexChanged.connect(self._suggest)
        form.addRow("Category", self.category)
        form.addRow("Reference", self.ref)
        if entry is None and s.ref_scheme == SEQUENCE:   # built on the CAWL or Swadesh: the next number
            self.category.setCurrentIndex(1)
        self.fields: dict[tuple[str, str], QWidget] = {}
        self.other_rows = []                        # second languages' glosses: behind the gloss's + (idea 19)
        self.others_btn = None
        self.origin_on = origin_shown(parent)
        self.from_box = None
        self.setMinimumWidth(340)
        under_more = more_fields(parent, db)       # behind the More arrow (idea 60, Josh, 24 October)
        main_rows, more_rows = [], []
        for f in s.entry_fields:
            if f.role == "stem-type" and not self.origin_on:
                continue                            # Settings → General: Stem type and From hidden
            rows = more_rows if f.name in under_more else main_rows
            if f.multilingual:
                primary_row, others = None, []
                for lang in s.gloss_languages:
                    ed = NoForbidden() if (lang == s.primary_gloss and not entry) else QLineEdit()
                    ed.setText(entry.get(f.name, lang) if entry else "")
                    keyboards.tag(ed, f"{f.name}:{lang}")             # its own keyboard (idea 43)
                    if f.role == "gloss" and lang == "en":           # red lines under unknown words
                        spellui.attach(ed, getattr(parent, "speller", None))
                    self.fields[(f.name, lang)] = ed
                    shown = ed
                    if f.role == "gloss" and entry is not None:     # the EACW's clarification (idea 87)
                        from .. import wordlists as _wl
                        clar = _wl.clarification_for(db, entry, lang, getattr(getattr(parent, "doc", None),
                                                                              "workspace", None))
                        if clar:
                            shown = self._with_info(ed, clar)
                    if lang == s.primary_gloss:
                        primary_row = (caption(f, f" ({lang})"), shown)
                    else:
                        others.append((caption(f, f" ({lang})"), shown))
                if primary_row is not None and others and self.others_btn is None:
                    primary_row = (primary_row[0], self._with_plus(primary_row[1], [l for l, _ in others]))
                if primary_row is not None:
                    rows.append(primary_row)
                rows.extend(others)                 # right under it, shown by the +
                self.other_rows.extend(w for _, w in others)
            elif f.closed:
                cb = QComboBox()
                cb.setEditable(True)
                cb.setToolTip("Pick from the list, or type a new value to add it to the list")
                cb.addItem("")
                listed = f.all_values()
                cb.addItems(listed)
                extra = sorted({e.get(f.name) for e in db.entries if e.get(f.name)} - set(listed))
                cb.addItems(extra)
                cb.setCurrentText(entry.get(f.name) if entry else
                                  ("simple" if f.role == "stem-type" and "simple" in listed else ""))
                rows.append((caption(f), cb))
                self.fields[(f.name, "")] = cb
                if f.role == "stem-type":
                    self._add_from(rows, db, entry, parent)
            else:
                ed = keyboards.tag(QLineEdit(entry.get(f.name) if entry else ""), f.name)
                if f.role == "lemma":
                    ed.setFont(ipa_font(14))
                rows.append((caption(f), ed))
                self.fields[(f.name, "")] = ed
        self.file_gloss = NoForbidden(entry.file_gloss if entry else "")
        self.file_gloss.setPlaceholderText("copied from the gloss when the entry is created")
        more_rows.append(("Gloss in file names", self.file_gloss))
        if not entry:
            self.file_gloss.setEnabled(False)
            self.file_gloss.setToolTip("Set automatically from the primary gloss.")
        for label, w in main_rows:
            form.addRow(label, w)
        self._form = form
        self._more_rows(form, more_rows, parent)
        tip_abbreviated(form, s.entry_fields)      # the full name in the hover (idea 73)
        if self.others_btn is not None:            # the + beside the gloss (Josh, 24 October)
            prefs = getattr(parent, "prefs", None)
            # count the line edits, not the rows: a gloss with the EACW's clarification is
            # wrapped with its (i), and the wrapper has no text (Josh, 27 October: A008, A040)
            filled = sum(1 for (_, lang), ed in self.fields.items()
                         if lang and lang != s.primary_gloss and isinstance(ed, QLineEdit)
                         and ed.text().strip())
            if filled:
                self.others_btn.setToolTip(self.others_btn.toolTip() + f" ({filled} filled)")
            shown = prefs.get_bool(OTHER_GLOSSES, False) if prefs is not None else False
            self.others_btn.setChecked(shown)
            self._show_others(shown, remember=False)
            self.others_btn.toggled.connect(self._show_others)
        form.addRow(_buttons(self))
        self.adjustSize()
        self.resize(min(max(self.minimumWidth(), self.sizeHint().width()), 460), self.sizeHint().height())

    def _with_info(self, ed, text: str):
        """A gloss with a small ⓘ at its right whose hover is the EACW's clarification (idea 87): the
        list's, read from its edition, so it isn't edited here (Settings → General hides them)."""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(ed, 1)
        info = QLabel("ⓘ")
        info.setObjectName("clarification")
        info.setToolTip(text)
        info.setStyleSheet(f"color: {theme.muted()};")
        h.addWidget(info)
        return box

    def _with_plus(self, ed, labels):
        """The primary gloss with a small + at its right: the other languages' glosses under it."""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        h.addWidget(ed, 1)
        b = QToolButton()
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setText("+")
        f = b.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 3)
        b.setFont(f)
        b.setFixedWidth(24)
        b.setStyleSheet(f"color: {theme.colour('pitch').name()};")   # the theme colour, lighter on dark
        b.setToolTip("Glosses in the database's other gloss languages (" + ", ".join(labels)
                     + "): they help speakers understand, e.g. in ɛλicit requests")
        h.addWidget(b)
        self.others_btn = b
        return box

    def _show_others(self, on: bool, remember: bool = True):
        self.others_btn.setText("−" if on else "+")
        for w in self.other_rows:
            self._form.setRowVisible(w, on)
        self.adjustSize()
        if remember:
            prefs = getattr(self.parent(), "prefs", None)
            if prefs is not None:
                prefs.set_value(OTHER_GLOSSES, bool(on))

    def _more_rows(self, form, rows, parent):
        """The fields behind the More arrow (IDEAS.md idea 60, Josh, 24 October): everything but the
        reference, Lemma, Gloss and Word Class to begin with (Edit → Fields → Under More changes it).
        The arrow says how many of them are filled; open or closed as last left (this computer)."""
        self.more_btn = None
        if not rows:
            return
        filled = sum(1 for _, w in rows if w is not self.file_gloss and _filled(w))   # not the automatic one
        b = QToolButton()
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setText(f"More ({filled} filled)" if filled else "More")
        b.setToolTip("The lemma's other fields: " + ", ".join(label for label, _ in rows if label)
                     + ". Edit → Fields → Under More chooses which they are.")
        form.addRow(b)
        for label, w in rows:
            form.addRow(label, w)
        prefs = getattr(parent, "prefs", None)

        def show(on, remember=True):
            b.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
            for _, w in rows:
                form.setRowVisible(w, on)
            self.adjustSize()
            if remember and prefs is not None:
                prefs.set_value(MORE_OPEN, bool(on))
        shown = prefs.get_bool(MORE_OPEN, False) if prefs is not None else False
        b.setChecked(shown)
        b.toggled.connect(show)
        show(shown, remember=False)
        self.more_btn = b

    def _add_from(self, rows, db, entry, parent):
        """From, under Stem type: lemmas and languages, as chips (Josh, 22 October)."""
        from .frombox import FromBox
        self.from_box = FromBox(db, entry, getattr(parent, "prefs", None))
        rows.append(("From", self.from_box))
        if entry is not None:
            part = [x for x in db.entries if entry.id in x.from_lemmas]
            if part:
                lbl = QLabel("Part of: " + ", ".join(f"{x.ref} {db.lemma(x)}" for x in part))
                lbl.setWordWrap(True)
                lbl.setFont(ipa_font(12))
                lbl.setToolTip("The lemmas built from this one (their From)")
                rows.append(("", lbl))

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
        if self.entry is None and not self._wordlist_checks(ref):
            return
        super().accept()

    # ---- the EACW's reserved letters and hidden items (Josh, 23 October) -------------
    def _gloss_edit(self):
        g = self.db.settings.entry_field("gloss")
        return self.fields.get((g.name, self.db.settings.primary_gloss)) if g is not None else None

    def _ask(self, title: str, text: str, buttons) -> int:
        """A question with buttons of its own; returns the index of the one clicked (-1: closed)."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        made = [box.addButton(b, role) for b, role in buttons]
        box.exec()
        return made.index(box.clickedButton()) if box.clickedButton() in made else -1

    def _wordlist_checks(self, ref: str) -> bool:
        """Before a new lemma is made: f and m are reserved for the female and male of an item;
        a reference that is an EACW item the database doesn't have yet says so (and can become that
        item); a gloss that is such an item's is offered its reference. False: back to the dialogue."""
        from .. import wordlists as wl
        db = self.db
        gloss_ed = self._gloss_edit()
        gloss = gloss_ed.text().strip() if gloss_ed is not None else ""
        r = wl.reserved(ref)
        if r and db.settings.ref_scheme != SEQUENCE and ref not in wl.get(wl.EACW).by_number:
            stem, letter = r
            parent = db.entry_by_ref(stem)
            item = wl.get(wl.EACW).by_number.get(stem)
            pgloss = db.gloss(parent) if parent is not None else (item.gloss if item else "")
            other = wl.next_letter(db, stem)
            sex = "female" if letter == "f" else "male"
            k = self._ask("f and m", f"{letter} after a reference is reserved for the {sex} of its item. "
                          f"Is this the {sex} of {stem}{' ' + pgloss if pgloss else ''}?",
                          [(f"Yes, keep {ref}", QMessageBox.AcceptRole), (f"Use {other}", QMessageBox.ActionRole),
                           ("Cancel", QMessageBox.RejectRole)])
            if k == 1:
                ref = other
                self.ref.setText(ref)
            elif k != 0:
                return False
        item = wl.unused_item(db, ref)
        if item is not None:
            same = not gloss or wl.norm_gloss(gloss) in wl.gloss_keys(item.gloss)
            if not same:
                k = self._ask("EACW item", f"{ref} is an item of the Extended African Comparative Wordlist "
                              f"that this database doesn't have yet: {item.gloss}"
                              f"{'' if item.default else ' (hidden in the published list)'}. A lemma under its "
                              "reference takes its CAWL and Swadesh numbers.",
                              [(f"Make it {item.gloss}", QMessageBox.AcceptRole),
                               ("Keep my gloss", QMessageBox.ActionRole),
                               ("Change the reference", QMessageBox.RejectRole)])
                if k == 0 and gloss_ed is not None:
                    gloss_ed.setText(item.gloss)
                elif k != 1:
                    return False
            return True
        hits = [i for i in wl.gloss_items(db, gloss) if i.number != ref and not db.ref_taken(i.number)]
        if hits:
            i = hits[0]
            k = self._ask("EACW item", f"“{gloss}” is the Extended African Comparative Wordlist's item "
                          f"{i.number}{'' if i.default else ' (hidden in the published list)'}, which this "
                          "database doesn't have yet. Use its reference, so the lemma keeps the list's "
                          "correspondences?",
                          [(f"Use {i.number}", QMessageBox.AcceptRole), (f"Keep {ref}", QMessageBox.ActionRole),
                           ("Cancel", QMessageBox.RejectRole)])
            if k == 0:
                self.ref.setText(i.number)
            elif k != 1:
                return False
        return True

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
        if self.from_box is not None:
            e.from_lemmas, e.from_languages = self.from_box.lemmas(), self.from_box.languages()

    def new_entry(self, speaker: str, date: str) -> Entry:
        s = self.db.settings
        gloss_field = s.entry_field("gloss")
        gloss = self.fields.get((gloss_field.name, s.primary_gloss)).text().strip() if gloss_field else ""
        e = self.db.new_entry(self.ref.text().strip(), gloss=gloss, speaker=speaker, date=date)
        self.apply(e)
        e.file_gloss = nfc(gloss)
        from .. import wordlists as wl                # an EACW item: its fields and correspondences
        if wl.is_eacw(self.db) and not wl.renumber_pending(self.db) and (n := wl.canon(wl.EACW, e.ref)):
            wl.fill_item(self.db, e, wl.get(wl.EACW).by_number[n])   # never from old numbers (the review)
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
        self.stem.setToolTip("The database's file name. Its notebook, workspace and automatic backups follow it.")
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
            beside = [d for s, d in plan[1:] if s.parent == self.old.parent]
            for d in beside:
                what = {".notebook": "the notebook", ".workspace": "the workspace"}.get(d.suffix, d.suffix)
                parts.append(f"{what} → {d.name}")
            backups = len(plan) - 1 - len(beside)
            if backups:
                parts.append(f"{backups} automatic backup{'s' if backups != 1 else ''} in Backups")
            self.note.setText("Renames " + "; ".join(parts) + ". The window's settings follow.")
        ok_btn.setEnabled(changed)


def pitch_kind_row(kind: str):
    """The Pitch kind choice (idea 9): Tonal, Intonational, Unspecified, with the (i) hover saying
    the database can be converted at any time. Returns (combo, row widget)."""
    from .. import pitchkind
    combo = QComboBox()
    for k in pitchkind.KINDS:
        combo.addItem(pitchkind.LABELS[k], k)
        combo.setItemData(combo.count() - 1, pitchkind.TIPS[k], Qt.ToolTipRole)
    combo.setCurrentIndex(max(0, combo.findData(kind)))
    combo.setToolTip("Whether the language is tonal: what pitch the database has (a fact about the "
                     "language, kept as typology in the database)")
    info = QLabel("ⓘ")
    info.setToolTip(pitchkind.CONVERT_NOTE)
    info.setStyleSheet(f"color: {theme.muted()};")
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(combo)
    h.addWidget(info)
    h.addStretch(1)
    return combo, w


class AckTable(QWidget):
    """One list of the acknowledgements (idea 59): a small table to type in, with + and −."""

    def __init__(self, headers, rows, tips=()):
        super().__init__()
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
        self._item = QTableWidgetItem
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for c, tip in enumerate(tips):
            self.table.horizontalHeaderItem(c).setToolTip(tip)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(len(headers) - 1, QHeaderView.Stretch)
        self.table.setMinimumHeight(96)
        self.table.setMaximumHeight(140)
        for row in rows:
            self.add(row)
        lay.addWidget(self.table, 1)
        side = QVBoxLayout()
        plus, minus = QToolButton(), QToolButton()
        plus.setText("+")
        plus.setToolTip("Add a row")
        minus.setText("−")
        minus.setToolTip("Remove the selected row")
        plus.clicked.connect(lambda *_: self.add([""] * self.table.columnCount(), edit=True))
        minus.clicked.connect(lambda *_: self.remove())
        side.addWidget(plus)
        side.addWidget(minus)
        side.addStretch(1)
        lay.addLayout(side)

    def add(self, values, edit: bool = False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate(values):
            self.table.setItem(r, c, self._item(v))
        if edit:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(self.table.item(r, 0))

    def remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def rows(self) -> list[list[str]]:
        """The rows typed, without the empty ones."""
        out = []
        for r in range(self.table.rowCount()):
            vals = [nfc((self.table.item(r, c).text() if self.table.item(r, c) else "").strip())
                    for c in range(self.table.columnCount())]
            if any(vals):
                out.append(vals)
        return out


class MetadataDialog(QDialog):
    """Language, variety, the database's name, author, description and gloss languages.

    Researchers, participants and locations are lists: Edit → Lists."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        md = db.metadata
        self.setWindowTitle("Database metadata")
        self.resize(600, 560)
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
        from .. import pitchkind
        self.pitch_kind, row = pitch_kind_row(pitchkind.kind(db))   # idea 9; converted by the main window
        form.addRow("Pitch kind", row)
        form.addRow("Database name", self.db_name)
        form.addRow("Author / owner", self.author)
        form.addRow("Description", self.description)
        from .glossbox import GlossLanguagesBox      # chips, only the supported languages (Josh, 28 October)
        primary = db.settings.primary_gloss
        self.glosses = GlossLanguagesBox([primary] + [l for l in db.settings.gloss_languages if l != primary])
        form.addRow("Gloss languages", self.glosses)
        from .. import wordlists as _wl                 # the EACW's shipped glosses and their status (idea 63)
        if _wl.is_eacw(db):
            shipped = "; ".join(f"{name} ({status[:1].lower()}{status[1:]})"
                                for name, status in _wl.gloss_statuses().values())
            note = QLabel(f"The EACW has glosses in {shipped}: adding fr, ar or am fills the empty glosses "
                          "of lemmas whose English gloss is still the list's.")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {theme.muted()};")
            form.addRow("", note)
        lay.addLayout(form)
        # Acknowledgements (idea 59, Josh, 24 October): two lists, an organisation's support and thanks
        ack = QGroupBox("Acknowledgements")
        al = QVBoxLayout(ack)
        al.addWidget(QLabel("Support (funders, institutions, grants)"))
        self.support = AckTable(["Organisation", "Grant or number", "What it funded"],
                                [[x.organisation, x.grant, x.funded] for x in md.support])
        al.addWidget(self.support)
        al.addWidget(QLabel("Thanks"))
        self.thanks = AckTable(["Person or group", "What for"], [[x.who, x.what_for] for x in md.thanks])
        al.addWidget(self.thanks)
        caution = QLabel("Thanks are left out of the Anonymous archive, and of the Ethical archive unless you "
                         "include them there; anyone named must have given their informed consent.")
        caution.setWordWrap(True)
        caution.setStyleSheet(f"color: {theme.muted()};")
        al.addWidget(caution)
        lay.addWidget(ack)
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
            self.images_btn.setToolTip("Pictures for ɛλicit requests, named by the token's reference and tag "
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
        super().accept()                          # the gloss languages always have their first

    def apply(self):
        md = self.db.metadata
        md.language_code = nfc(self.lang_code.text().strip())
        md.language_name = nfc(self.lang_name.text().strip())
        md.variety_code = nfc(self.var_code.text().strip())
        md.variety_name = nfc(self.var_name.text().strip())
        md.name = nfc(self.db_name.text().strip())
        md.author = nfc(self.author.text().strip())
        md.description = nfc(self.description.text().strip())
        from ..model import Support, Thanks
        md.support = [Support(*r) for r in self.support.rows()]
        md.thanks = [Thanks(*r) for r in self.thanks.rows()]
        langs = self.glosses.languages()
        self.db.settings.gloss_languages = langs
        self.db.settings.primary_gloss = langs[0]


# ==========================================================================
# Preferences
# ==========================================================================

# The app bar's badges (Josh, 24 October): Questions, To Do and Snapshots each have one, each
# switched on or off on its own in Settings → Display (this computer).
BADGE_QUESTIONS, BADGE_TODO, BADGE_SNAPSHOTS = "display/badge_questions", "display/badge_todo", "display/badge_snapshots"
BADGES = ((BADGE_QUESTIONS, "Questions: the number of open questions", "On the ? in the app bar"),
          (BADGE_TODO, "To Do: the number of open To Dos", "On the orange flag in the app bar"),
          (BADGE_SNAPSHOTS, "Snapshots: the number taken today", "On the Snapshots button in the app bar"))

ORIGIN_KEY = "origin/shown"      # Settings → General: Stem type and From shown (the workspace's)


def origin_shown(main) -> bool:
    """Whether Stem type and From are shown for the open database (Settings → General)."""
    ws = getattr(getattr(main, "doc", None), "workspace", None)
    return ws.get_bool(ORIGIN_KEY, True) if ws is not None else True


class PreferencesDialog(QDialog):
    def __init__(self, parent, db: Database, prefs):
        super().__init__(parent)
        self.db, self.prefs = db, prefs
        s = db.settings
        self.setWindowTitle("Settings")
        self.resize(660, 680)                 # the pages scroll if the screen is smaller
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
        self.auto_names = QCheckBox("Update soundfile names automatically")
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
        from PySide6.QtWidgets import QDoubleSpinBox
        self.splash = QDoubleSpinBox()
        self.splash.setRange(0.0, 5.0)
        self.splash.setSingleStep(0.5)
        self.splash.setDecimals(1)
        self.splash.setSuffix(" s")
        self.splash.setSpecialValueText("as short as possible")
        self.splash.setValue(prefs.splash_seconds)
        self.splash.setToolTip("How long the splash screen stays when Lemmatrix starts, at least "
                               "(it stays while the database opens either way). Click it to close it sooner.")
        self.welcome = QCheckBox("Show the welcome window at every start")
        self.welcome.setChecked(prefs.show_welcome)
        self.welcome.setToolTip("Not selected: Lemmatrix opens the database you opened most recently "
                                "(the welcome window still shows when it can't find one). It is shown "
                                "by itself the very first time.")
        self.ipa = QSpinBox()
        self.ipa.setRange(8, 30)
        self.ipa.setValue(prefs.ipa_size)
        self.abbreviate = QCheckBox("Abbreviate field names in the edit dialogues (pht, phm, trs…)")
        self.abbreviate.setChecked(prefs.abbreviate_fields)
        self.abbreviate.setToolTip("The token, utterance, lemma and text dialogues label each field by its "
                                   "abbreviation (Edit → Fields), the full name in the hover; the grids' "
                                   "column headers keep the full names")
        self.theme = QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.setCurrentIndex(max(0, self.theme.findData(prefs.theme)))
        self.theme.setToolTip("Light or dark, for the whole program")
        self.accent = ColourButton(prefs.accent, theme.DEFAULT_ACCENT,
                                   "Selected tabs, highlights, tag chips and pitch traces")
        # Two colours of one's own (Josh, 26 October): the search marks, and (Settings → Pitch) the
        # pitch traces; Default (or deselecting) goes back
        self.search_colour = ColourButton(prefs.search_colour, theme.DEFAULT_SEARCH,
                                          "What every search bar marks in the cells, lines and the XML "
                                          "viewer (darker on the dark theme). Default: yellow")
        self.bookmark_colour = ColourButton(prefs.bookmark_colour, theme.DEFAULT_BOOKMARK,
                                            "A text's bookmark in the margin of its lines (golden by default)")
        self.themed_buttons = QCheckBox("All buttons theme coloured")
        self.themed_buttons.setChecked(prefs.themed_buttons)
        self.themed_buttons.setToolTip("Add and Play's green, Delete's red, Update's blue, Record's purple and "
                                       "Praat's beige become theme-coloured versions of themselves")
        self.pitch_own = QCheckBox("Pitch traces in a colour of their own")
        self.pitch_own.setChecked(prefs.pitch_colour_on)
        self.pitch_own.setToolTip("Deselected, the pitch traces are drawn in the accent colour "
                                  "(Settings → Display), as before")
        self.pitch_colour = ColourButton(prefs.pitch_colour, theme.DEFAULT_ACCENT,
                                         "The pitch drawings' colour (lightened on the dark theme)")

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

        def page(title, sections, intro=None):
            """A tab of headed boxes; returns the boxes by heading (to grey a whole box)."""
            boxes = {}
            w = QWidget()
            v = QVBoxLayout(w)
            if intro is not None:
                v.addWidget(intro)
            for heading, rows in sections:
                box = QGroupBox(heading)
                boxes[heading] = box
                f = QFormLayout(box)
                for label, widget in rows:
                    if label:
                        f.addRow(label, widget)
                    else:
                        f.addRow(widget)
                v.addWidget(box)
            v.addStretch(1)
            area = QScrollArea()                  # a long page scrolls on a small screen
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setWidget(w)
            tabs.addTab(area, title)
            return boxes

        from .. import notebook as nbmod             # the notebook's history sections (this database)
        ws = getattr(getattr(parent, "doc", None), "workspace", None)
        self.history = {}
        for section, label in nbmod.HISTORY_LABELS.items():
            box = QCheckBox(label)
            box.setChecked(ws.get_bool(nbmod.HISTORY_SETTINGS[section], True) if ws is not None else True)
            box.setToolTip(f"A line under {nbmod.HISTORY_HEADINGS[section]} in the day's notes for each "
                           f"{nbmod.HISTORY_WHAT[section]}"
                           ". Switching it off leaves what is written; nothing is written later for the days it was off.")
            self.history[section] = box
        self.origin_on = QCheckBox("Show Stem type and From")       # Josh, 22 October
        self.origin_on.setChecked(ws.get_bool(ORIGIN_KEY, True) if ws is not None else True)
        self.origin_on.setToolTip("Where a lemma comes from: the Stem type field (simple, complex, loan) and "
                                  "From (the lemmas it's built from, the languages it was borrowed from). "
                                  "Off hides them everywhere; what's filled in is kept.")
        from .. import wordlists as _wl                # the EACW's clarifications as (i)s (idea 87, this database)
        self.clar_on = QCheckBox("Show the EACW's clarifications (an ⓘ beside each gloss)")
        self.clar_on.setChecked(ws.get_bool(_wl.CLARIFICATIONS_KEY, True) if ws is not None else True)
        self.clar_on.setEnabled(_wl.is_eacw(db))
        self.clar_on.setToolTip("The list's plain meaning of an item's gloss, in English and in each gloss language "
                                "the EACW has glosses in, shown in the hover of an ⓘ in the lemma dialogue and of "
                                "the gloss in the lemma list and All data. Off hides them all; nothing is lost."
                                if _wl.is_eacw(db) else "Only in a database built on the EACW.")
        # Decomposed transcriptions (ideas 18 and 21, Josh, 27 October; format 14): the database's promise
        self.decomposed_box = QCheckBox("Decompose Phonetic and Phonemic: no precomposed characters (é is e + ◌́)")
        self.decomposed_box.setChecked(s.decomposed)
        self.decomposed_box.setToolTip(
            "Selected: everything written into Phonetic and Phonemic is decomposed (Unicode NFD), typed, "
            "pasted, Bulk edit, TextGrids, ɛλicit, so every tone mark is a character of its own and analysis "
            "tools read tone suprasegmentally. The database file says so (<characters transcriptions=\"NFD\">). "
            "Deselected: precomposed where Unicode has the character (NFC). Changing it converts the data "
            "(one undo step); nothing is lost either way. Soundfile names are always composed.")
        self.kb = keyboards.KeyboardSection(self, db, prefs)   # automatic keyboard switching (idea 43)
        page("General", [("This computer", [("Autosave every", self.autosave),
                                            ("Full backup folder", self.backups),
                                            (None, self.welcome)]),
                         ("Lemmas (this database)", [(None, self.origin_on), (None, self.clar_on)]),
                         ("Transcriptions (this database)", [(None, self.decomposed_box)]),
                         ("Notebook (this database)", [(None, b) for b in self.history.values()]),
                         ("Warnings (this computer)", [(None, self.unusual), (None, self.spelling), (None, self.confirm)]),
                         ("Keyboards (this computer)", [(None, w) for w in self.kb.widgets()])])
        page("Sound", [
            ("This database", [("File name pattern", self.pattern), ("Tag separator", self.separator),
                               ("Utterance file names", self.utt_pattern),
                               ("Text file names", self.text_pattern),
                               ("Clips keep either side", self.padding),
                               (None, self.auto_names)]),
            ("This computer", [("Recording source", self.source), ("Bit depth", self.bits),
                               ("Sample rate", self.rate), (None, self.with_tokens),
                               ("Path to Praat", self.praat)])])
        from . import conventions as conv            # the cell views' display conventions (idea 26)
        c = conv.CURRENT
        self.conv_on = QCheckBox("Use the display conventions (the /[β]/ button under every cell view)")
        self.conv_on.setChecked(c.on)
        self.conv_brackets = QCheckBox("Phonetic in [square brackets]")
        self.conv_brackets.setChecked(c.brackets)
        self.conv_slashes = QCheckBox("Phonemic in /slashes/")
        self.conv_slashes.setChecked(c.slashes)
        self.conv_caps = QCheckBox("Glosses in capitals (PL, 1SG) in small caps, in the Morphemes line "
                                   "and the Constituents labels (NP, V)")
        self.conv_caps.setChecked(c.small_caps)
        self.conv_quotes = QComboBox()
        for key, label in ((conv.SINGLE, "‘single’ quotes"), (conv.DOUBLE, "“double” quotes"),
                           (conv.NO_QUOTES, "no quotes")):
            self.conv_quotes.addItem(label, key)
        self.conv_quotes.setCurrentIndex(max(0, self.conv_quotes.findData(c.quotes)))
        self.conv_labels = QComboBox()               # the Constituents drawing's labels (idea 91, Josh)
        for key, label in (("left", "left"), ("centre", "centred"), ("right", "right")):
            self.conv_labels.addItem(label, key)
        self.conv_labels.setCurrentIndex(max(0, self.conv_labels.findData(c.label_align)))
        self.conv_labels.setToolTip("Where a phrase's label sits on its bracket, and a floating label over its "
                                    "word, in the Constituents drawing")
        self.badges = {}                              # the app bar's badges (Josh, 24 October): each its own
        for key, label, tip in BADGES:
            box = QCheckBox(label)
            box.setChecked(prefs.get_bool(key, True))
            box.setToolTip(tip)
            self.badges[key] = box
        page("Display", [("This computer", [("Theme", self.theme), ("Accent colour", self.accent),
                                            ("Search highlight", self.search_colour),
                                            ("Bookmark colour", self.bookmark_colour),
                                            (None, self.themed_buttons),
                                            ("IPA font size", self.ipa),
                                            ("Splash screen", self.splash), (None, self.abbreviate)]),
                         ("Badges on the app bar (this computer)", [(None, b) for b in self.badges.values()]),
                         ("Display conventions: matrix cells, text lines, the utterance cell (this computer)",
                          [(None, self.conv_on), (None, self.conv_brackets), (None, self.conv_slashes),
                           (None, self.conv_caps), ("Translations in", self.conv_quotes),
                           ("Constituent labels", self.conv_labels)])])
        from .. import pitchview                     # Show the pitch system (idea 9; this database's workspace)
        # Hide the pitch system (Josh, 26 October: was "Show the pitch system"; selected hides it)
        self.pitch_hide = QCheckBox("Hide the pitch system")
        self.pitch_hide.setChecked(not pitchview.tick())
        self.pitch_hide.setToolTip("Hides the Pitch field, the pitch drawing, pitch playback (Ctrl+Shift+Space), "
                                   "Raise and Lower pitch, Bulk edit's Pitch shortcut and the pitch scratchpads "
                                   "everywhere, to declutter: the data is kept exactly as it is (tone fields such "
                                   "as Tone Class stay), and everything comes back as it was when it is "
                                   "deselected. Also View → Hide pitch system.")
        from .. import pitchkind
        kind = pitchkind.kind(db)                    # the database's pitch kind (idea 9)
        # "{language and variety} is Tonal", the kind bold, in the theme colour, a little larger;
        # what it means for the data and the views under it in italics (Josh, 26 October)
        md = db.metadata
        lang = md.language_name.strip() or "This database"
        if md.variety_name.strip():
            lang += f" ({md.variety_name.strip()})"
        self.kind_note = QLabel(f"{lang} is <span style='color:{theme.colour('pitch').name()}; "
                                f"font-weight:bold; font-size:large'>{pitchkind.LABELS[kind]}</span>")
        self.kind_note.setTextFormat(Qt.RichText)
        self.kind_note.setWordWrap(True)
        self.kind_note.setToolTip(pitchkind.CONVERT_NOTE)
        self.kind_tip = QLabel(f"<i>{pitchkind.TIPS[kind]}.</i>")
        self.kind_tip.setTextFormat(Qt.RichText)
        self.kind_tip.setWordWrap(True)
        self.kind_btn = QPushButton("Change the pitch kind…")
        self.kind_btn.setToolTip("Edit → Metadata → Pitch kind. " + pitchkind.CONVERT_NOTE)
        self.kind_btn.clicked.connect(lambda *_: self._change_kind())
        self.change_kind_requested = False
        boxes = page("Pitch", [("Pitch kind (this database)", [(None, self.kind_note), (None, self.kind_tip),
                                                               (None, self.kind_btn)]),
                       ("Show (this database)", [(None, self.pitch_hide)]),
                       ("This database", [("Lowest pitch digit", self.low),
                                          ("Highest pitch digit", self.high)]),
                       ("This computer", [("Pitch playback", voice_row),
                                          ("Playback volume", volume_row),
                                          (None, self.pitch_own), ("Pitch trace colour", self.pitch_colour)])])
        # Settings → Typology (IDEAS.md ideas 56 and 91, Josh, 28 October): the database's typological
        # features, data (the <typology> block, both archives). The pitch kind is here and in
        # Edit → Metadata (Josh: keep it in both); changing it converts the database, as there.
        # Josh, 28 October: chips under Pitch, Morphology and Syntax, a search bar at the top, any
        # number of chips per feature; the pitch kind fixed here (changed in Settings → Pitch).
        from .typologybox import TypologyBox
        self.typology_box = TypologyBox(db)
        typ_note = QLabel("<i>Facts about the language, kept in the database (and in both archives). The "
                          "constituent order is what the Constituents tier will be compared with (v2).</i>")
        typ_note.setTextFormat(Qt.RichText)
        typ_note.setWordWrap(True)
        typ_page = QWidget()
        tpl = QVBoxLayout(typ_page)
        tpl.addWidget(typ_note)
        tpl.addWidget(self.typology_box)
        tpl.addStretch(1)
        typ_area = QScrollArea()
        typ_area.setWidgetResizable(True)
        typ_area.setFrameShape(QFrame.NoFrame)
        typ_area.setWidget(typ_page)
        tabs.addTab(typ_area, "Typology")
        pitch_tab = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Pitch")
        self.typology_box.go_to_pitch.connect(lambda: tabs.setCurrentIndex(pitch_tab))
        # Settings → Advanced (IDEAS.md ideas 79 and 86, Josh, 27 October): Women, Fire, and Dangerous
        # Things (Lakoff's title, in his order), one list with no boxes. Reached only here, never from the menus at the top; everything
        # in it starts off on a new computer (Josh: "don't make them easy to access").
        from .. import search
        adv = QWidget()
        av = QVBoxLayout(adv)
        av.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        title = QLabel(f"<b style='color:{theme.accent().name()}'>Women, Fire, and Dangerous Things</b>")
        title.setTextFormat(Qt.RichText)
        info = QLabel("ⓘ")
        info.setStyleSheet(f"color: {theme.muted()};")
        info.setToolTip("Lakoff, George. 1987. Women, Fire, and Dangerous Things: What Categories Reveal about the Mind. Chicago: University of Chicago Press.")
        head.addWidget(title)
        head.addWidget(info)
        head.addStretch(1)
        av.addLayout(head)
        sub = QLabel("<i>Options for experienced users who want to work fast and smart; all off by default "
                     "(this computer).</i>")
        sub.setTextFormat(Qt.RichText)
        sub.setWordWrap(True)
        av.addWidget(sub)
        av.addSpacing(8)
        self.power_search = QCheckBox(search.PLACEHOLDER)
        self.power_search.setChecked(prefs.get_bool(search.POWER_KEY, False))
        self.power_search.setToolTip(
            "Every search bar reads doubles as operators (a single - + , / or ; is always searched as typed):\n"
            "--  leaves an item out of the whole search (goat ;; sheep --kid)\n"
            "++  AND: a row must have both, in any of its columns (goat ++ PL)\n"
            ";;  OR (goat ;; sheep); ++ binds tighter: goat ++ PL ;; sheep is (goat and PL) or sheep\n"
            "\\  before a double searches for it (\\--)\n"
            "In the lemma searches also: CAWL 345, SWADESH, EACW C001f, --CAWL, and a taxon.\n"
            "Off: what's typed is found as typed.")
        av.addWidget(self.power_search)
        example = QLabel("goat ++ PL ;; sheep --kid")
        example.setStyleSheet(f"color: {theme.muted()}; margin-left: 22px;")
        av.addWidget(example)
        from .. import advanced
        self.hot_mic_box = QCheckBox(advanced.HOT_MIC)       # idea 68 (Josh, 27 October)
        self.hot_mic_box.setChecked(prefs.get_bool(advanced.HOT_MIC_KEY, False))
        self.hot_mic_box.setToolTip("A take records straight over the soundfile already there, without asking "
                                "(the token, utterance and segment dialogues). The old one still goes to the "
                                "Recycle Bin. The Record button shows a flame while it's on.")
        hot_info = QLabel("ⓘ")
        hot_info.setStyleSheet(f"color: {theme.muted()};")
        hot_info.setToolTip("Not recommended with an orange or red theme")   # Josh: the flame would vanish
        row = QHBoxLayout()
        row.addWidget(self.hot_mic_box)
        row.addWidget(hot_info)
        row.addStretch(1)
        av.addSpacing(6)
        av.addLayout(row)
        hot_note = QLabel("overwrite soundfiles without warning")
        hot_note.setStyleSheet(f"color: {theme.muted()}; margin-left: 22px;")
        av.addWidget(hot_note)
        # ✂ auto-snip (idea 10, Josh, 27 October): the margins settable, the ✂ button while it's on
        self.auto_snip_box = QCheckBox(advanced.AUTO_SNIP)
        self.auto_snip_box.setChecked(prefs.get_bool(advanced.AUTO_SNIP_KEY, False))
        self.auto_snip_box.setToolTip(advanced.AUTO_SNIP_TIP)                 # Josh's hidden joke
        av.addSpacing(6)
        av.addWidget(self.auto_snip_box)
        snip_note = QLabel(advanced.AUTO_SNIP_LINE)
        snip_note.setWordWrap(True)
        snip_note.setStyleSheet(f"color: {theme.muted()}; margin-left: 22px;")
        av.addWidget(snip_note)
        from PySide6.QtWidgets import QDoubleSpinBox
        margins = QHBoxLayout()
        margins.setContentsMargins(22, 0, 0, 0)
        self.snip_margins = {}
        for key, (label, default) in advanced.SNIP_MARGINS.items():
            box = QDoubleSpinBox()
            box.setRange(0.0, 3.0)
            box.setSingleStep(0.05)
            box.setDecimals(2)
            box.setSuffix(" s")
            try:
                box.setValue(float(prefs.get_value(key)) if prefs.get_value(key) is not None else default)
            except (TypeError, ValueError):
                box.setValue(default)
            lab = QLabel(label)
            lab.setBuddy(box)
            margins.addWidget(lab)
            margins.addWidget(box)
            margins.addSpacing(10)
            self.snip_margins[key] = box
        self.snip_margins["recording/snip_before"].setToolTip("Silence kept before the first sound")
        self.snip_margins["recording/snip_after"].setToolTip("Silence kept after the last sound "
                                                             "(longer, so a quiet ending isn't clipped)")
        self.snip_margins["recording/snip_gap"].setToolTip("Tokens: a longer gap between repetitions "
                                                           "is shortened to this; a shorter one is left alone")
        snip_reset = QPushButton("Reset")
        snip_reset.setToolTip("Back to 0.25, 0.25 and 0.60 s")
        snip_reset.clicked.connect(lambda *_: [b.setValue(advanced.SNIP_MARGINS[k][1])
                                               for k, b in self.snip_margins.items()])
        margins.addWidget(snip_reset)
        margins.addStretch(1)
        av.addLayout(margins)

        def _snip_follow(on):
            for w in (*self.snip_margins.values(), snip_reset):
                w.setEnabled(on)
        self.auto_snip_box.toggled.connect(_snip_follow)
        _snip_follow(self.auto_snip_box.isChecked())
        self.fast_paste_box = QCheckBox(advanced.FAST_PASTE)  # idea 79 (Josh, 27 October)
        self.fast_paste_box.setChecked(prefs.get_bool(advanced.FAST_PASTE_KEY, False))
        self.fast_paste_box.setToolTip("Typing in Phonetic or Phonemic: Shift+Down copies it into the other "
                                   "transcription below, Shift+Up into the one above (in a grid, either arrow "
                                   "into the other column), replacing what's there, and moves there.")
        av.addSpacing(6)
        av.addWidget(self.fast_paste_box)
        paste_note = QLabel("Phonetic ⇄ Phonemic with Shift+Down / Shift+Up")
        paste_note.setStyleSheet(f"color: {theme.muted()}; margin-left: 22px;")
        av.addWidget(paste_note)
        from .. import bestfriend                 # 🐕 linguist's best friend (idea 21, Josh, 27 October)
        self.best_friend_box = QCheckBox(advanced.BEST_FRIEND)
        self.best_friend_box.setChecked(prefs.get_bool(advanced.BEST_FRIEND_KEY, False))
        self.best_friend_box.setToolTip("As you type in Phonetic and Phonemic (never when pasting): the rules "
                                        "selected below. Backspace or Ctrl+Z straight after a correction "
                                        "puts back what you typed.")
        av.addSpacing(6)
        av.addWidget(self.best_friend_box)
        bf_note = QLabel(advanced.BEST_FRIEND_LINE)
        bf_note.setStyleSheet(f"color: {theme.muted()}; margin-left: 22px;")
        av.addWidget(bf_note)
        self.bf_rules = {}
        for rule in bestfriend.RULES:
            box = QCheckBox(rule.label)
            box.setChecked(prefs.get_bool(rule.key, True))
            box.setStyleSheet("margin-left: 22px;")
            av.addWidget(box)
            self.bf_rules[rule.key] = box
        def _follow(on):
            for box in self.bf_rules.values():
                box.setEnabled(on)
        self.best_friend_box.toggled.connect(_follow)
        _follow(self.best_friend_box.isChecked())
        page("Advanced", [], intro=adv)
        lay.addWidget(_buttons(self))
        # Hidden: the boxes under it grey out whole, their headings and labels too (Josh, 26 October:
        # a bigger visual cue that something is turned off)
        under = [boxes["This database"], boxes["This computer"]]
        has = pitchkind.has_pitch_field(kind)     # unspecified: no pitch at all, only Change…

        def grey(*_):
            on = has and not self.pitch_hide.isChecked()
            for box in under:
                box.setEnabled(on)
            self.pitch_colour.setEnabled(on and self.pitch_own.isChecked())   # with its checkbox
        self.pitch_hide.toggled.connect(grey)
        self.pitch_own.toggled.connect(grey)
        self.pitch_hide.setEnabled(has)
        grey()

    def _change_kind(self):
        """Change the pitch kind…: closes Settings (its changes kept) and opens Edit → Metadata."""
        self.change_kind_requested = True
        self.accept()

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
        s.decomposed = self.decomposed_box.isChecked()   # the data is converted by the main window
        # Settings → Typology (idea 91): morphology and order; the pitch kind is changed in Settings → Pitch
        ty = dict(self.db.metadata.typology or {})    # chips (28 October); the pitch kind isn't set here
        self.typology_box.apply_to(ty)
        self.db.metadata.typology = ty
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
        p.abbreviate_fields = self.abbreviate.isChecked()
        p.splash_seconds = self.splash.value()
        if self.welcome.isChecked() != p.show_welcome:      # unchanged leaves the first start alone
            p.show_welcome = self.welcome.isChecked()
        p.theme = self.theme.currentData()
        p.accent = self.accent.colour()
        p.search_colour = self.search_colour.colour()
        p.bookmark_colour = self.bookmark_colour.colour()
        p.themed_buttons = self.themed_buttons.isChecked()
        p.pitch_colour_on = self.pitch_own.isChecked()
        p.pitch_colour = self.pitch_colour.colour()
        p.praat_path = self.praat.text().strip()
        p.pitch_voice = self.voice.currentData()
        p.pitch_volume = self.volume.value()
        p.full_backup_folder = self.backups.text().strip()
        for key, box in self.badges.items():
            p.set_value(key, box.isChecked())
        self.kb.apply()
        from .. import search                     # ⚡ power search (idea 86; this computer)
        p.set_value(search.POWER_KEY, self.power_search.isChecked())
        search.set_power(self.power_search.isChecked())
        from .. import advanced                   # 🔥 hot mic, 📋 fast paste (ideas 68, 79; this computer)
        for key, box in ((advanced.HOT_MIC_KEY, self.hot_mic_box), (advanced.FAST_PASTE_KEY, self.fast_paste_box),
                         (advanced.BEST_FRIEND_KEY, self.best_friend_box), *self.bf_rules.items(),
                         (advanced.AUTO_SNIP_KEY, self.auto_snip_box)):
            p.set_value(key, box.isChecked())
            advanced.set_on(key, box.isChecked())
        for key, box in self.snip_margins.items():   # ✂ auto-snip's margins (this computer)
            p.set_value(key, box.value())
            advanced.set_margin(key, box.value())
        doc = getattr(self.parent(), "doc", None)
        if doc is not None:                       # the notebook's history switches: the workspace's
            from .. import notebook as nbmod
            for section, box in self.history.items():
                doc.ws_set(nbmod.HISTORY_SETTINGS[section], box.isChecked())
            doc.ws_set(ORIGIN_KEY, self.origin_on.isChecked())
            from .. import wordlists as _wl
            doc.ws_set(_wl.CLARIFICATIONS_KEY, self.clar_on.isChecked())
            doc.set_pitch_shown(not self.pitch_hide.isChecked())   # a view setting: never marks it unsaved
        from . import conventions as conv
        conv.save(p, conv.Conventions(on=self.conv_on.isChecked(), brackets=self.conv_brackets.isChecked(),
                                      slashes=self.conv_slashes.isChecked(), small_caps=self.conv_caps.isChecked(),
                                      quotes=self.conv_quotes.currentData(),
                                      label_align=self.conv_labels.currentData()))
        return old != (s.filename_pattern, s.tag_separator, s.utterance_pattern, s.text_pattern)


# ==========================================================================
# Tag structure editor
# ==========================================================================

KIND_GROUP, KIND_TAG = "group", "tag"
NAME, CODE, DEFAULT, USUAL, DESC = range(5)
USUAL_ROLE = Qt.UserRole + 2                  # a group's own "usual for" word classes
ONLY_ROLE = Qt.UserRole + 3                   # a group marked "utterances only" (a rule, inherited)


class UsualDialog(QDialog):
    """Which word classes a tag group is usual for (none selected: its parent's, or every lemma)."""

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
                      + ("Nothing selected: as its parent group (" + ", ".join(inherited) + ")."
                         if inherited else "Nothing selected: usual for every lemma."))
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
        if not _w.ask(self, "Delete", msg, f"Delete and take it off {n} token{'s' if n != 1 else ''}" if n else f"Delete {cur.data(NAME, Qt.UserRole)}"):
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
        if dups and not _w.ask(self, "Tag structure", "Some codes are shared, so file names "
                                         "couldn't be told apart:\n" + "\n".join(dups) +
                                         "\n\nKeep them anyway?", "Keep them", "Go back"):
            return False
        # Two tokens of a lemma that would get one soundfile name (a new default has no code; Josh,
        # 26 October): Add Example tags, Choose for each (merge where nothing is lost), or Cancel
        from .. import tagclash
        from . import tagclash_dialog
        self.clash_plan = None
        clashes = tagclash.find(self.db, ts, self.renames(), self.deleted_tags())
        if clashes:
            choice = tagclash_dialog.ask(self, self.db, clashes)
            if choice is None:
                return False
            self.clash_plan = (clashes, choice)
        return True
