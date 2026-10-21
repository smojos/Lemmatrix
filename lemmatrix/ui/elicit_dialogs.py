# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""ɛλicit's dialogues (IDEAS.md idea 19, stage 1): Make ɛλicit request, the message to send with
it, and the review of the recordings that come back (Receive ɛλicitation)."""

from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableView,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import cloud_keys, gdrive
from .. import elicit as el
from .. import elicit_prompts, filenames, layout, storage
from ..model import is_utterance
from . import theme
from .winstate import fit_to_screen

NAME = "ɛλicit"
RECEIVE = "Receive ɛλicitation"


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setBold(True)
    f.setPointSizeF(f.pointSizeF() * 1.3)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {theme.colour('pitch').name()};")
    return lbl


def run_with_progress(parent, title: str, label: str, fn, can_cancel: bool = False):
    """Run fn(progress, cancelled) off the main thread, with a progress dialogue, and return what
    it returns (or raise what it raised). progress(n, total, text) updates the dialogue."""
    import threading
    import time
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication, QProgressDialog
    state = {"done": False, "result": None, "error": None, "text": label, "n": 0, "total": 0, "cancel": False}

    def progress(n, total, text):
        state.update(n=n, total=total, text=text)

    def work():
        try:
            state["result"] = fn(progress, lambda: state["cancel"])
        except BaseException as exc:              # noqa: BLE001 (passed on below)
            state["error"] = exc
        finally:
            state["done"] = True
    threading.Thread(target=work, daemon=True).start()
    dlg = QProgressDialog(label, "Cancel" if can_cancel else "", 0, 0, parent)
    if not can_cancel:
        dlg.setCancelButton(None)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(200)
    dlg.setMinimumWidth(420)
    while not state["done"]:
        QApplication.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.02)
        if can_cancel and dlg.wasCanceled():
            state["cancel"] = True
        dlg.setMaximum(state["total"])
        dlg.setValue(state["n"])
        dlg.setLabelText(state["text"])
    dlg.close()
    if state["error"] is not None:
        raise state["error"]
    return state["result"]


def google_drive(main, sign_in: bool = True):
    """The researcher's Google Drive, signed in on this computer (asking to sign in if not, when
    sign_in). None if signed out or the keys aren't there."""
    if not cloud_keys.google_ready():
        return None
    prefs = main.prefs
    token = prefs.google_token
    if not token.get("refresh_token"):
        if not sign_in:
            return None
        box = QMessageBox(QMessageBox.Information, "Google Drive",
                          "ɛλicit sends requests through your Google Drive. Your browser opens now for you to "
                          "sign in to Google and allow Lemmatrix to keep the files it makes there (and only "
                          "those: it can't see anything else in your Drive).", parent=main)
        go = box.addButton("Sign in", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is not go:
            return None
        import webbrowser
        try:
            token = run_with_progress(main, "Google Drive", "Waiting for you to sign in in your browser…",
                                      lambda progress, cancelled: gdrive.authorize(webbrowser.open, cancelled),
                                      can_cancel=True)
        except gdrive.DriveError as exc:
            QMessageBox.warning(main, "Google Drive", str(exc))
            return None
        prefs.google_token = token

    def keep(tok):
        prefs.google_token = tok
    return gdrive.Drive(token, on_token=keep)


def sign_out_google(main):
    token = main.prefs.google_token
    main.prefs.google_token = {}
    try:
        run_with_progress(main, "Google Drive", "Signing out…", lambda p, c: gdrive.revoke(token))
    except Exception:                             # noqa: BLE001 (signed out here whatever Google says)
        pass
    main.statusBar().showMessage("Signed out of Google Drive.", 5000)


def _drive_problem(main, title, exc):
    if isinstance(exc, gdrive.SignInNeeded):
        main.prefs.google_token = {}
        QMessageBox.warning(main, title, f"{exc}\n\nTry again: Lemmatrix will ask you to sign in.")
    else:
        QMessageBox.warning(main, title, str(exc))


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


# --------------------------------------------------------------------------
# Make ɛλicit request
# --------------------------------------------------------------------------

class _Row:
    __slots__ = ("entry", "token", "utterance", "recorded", "image", "kind", "ticked", "cells")


COLUMNS = ("", "Reference", "Form", "Tags", "Card shows", "Recording", "Picture", "Card")


class ItemModel(QAbstractTableModel):
    """Every lemma token and utterance, with a tick and the kind of card (New or Rerecord)."""

    def __init__(self, db, rows):
        super().__init__()
        self.db, self.rows = db, rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        r = self.rows[index.row()]
        c = index.column()
        if role == Qt.CheckStateRole and c == 0:
            return Qt.Checked if r.ticked else Qt.Unchecked
        if role == Qt.DisplayRole:
            if c == 7:
                return "Rerecord" if r.kind == el.RERECORD else "New"
            return r.cells[c] if c else ""
        if role == Qt.ToolTipRole and c == 7:
            return ("It has a soundfile: the card plays it, to be repeated" if r.recorded else
                    "No soundfile yet: the card shows its gloss or translation")
        if role == Qt.ForegroundRole and c == 4 and r.kind == el.NEW and not r.cells[4]:
            return theme.colour("muted")
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            self.rows[index.row()].ticked = Qt.CheckState(value) == Qt.Checked
            self.dataChanged.emit(index, index)
            return True
        return False


class ItemFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.ticked_only = False
        self.scope = 0                           # 0 everything, 1 lemma tokens, 2 citation tokens, 3 utterances

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        if self.ticked_only and not r.ticked:
            return False
        if self.scope == 1 and r.utterance or self.scope == 3 and not r.utterance:
            return False
        if self.scope == 2 and (r.utterance or not r.token.is_citation):
            return False
        if self.text:
            return self.text in " ".join(r.cells[1:7]).casefold()
        return True


class RequestDialog(QDialog):
    """Choose the speaker, the researcher, the second language and the cards; then write the
    request's zip and show the message to send with it."""

    def __init__(self, main, preselect=(), new_utterances=(), speaker: str = "", draft: dict | None = None):
        super().__init__(main)
        self.main = main
        self.db = main.doc.db
        self.made = None                          # the zip, once made
        self.setWindowTitle(f"Make {NAME} request")
        self._images = self._image_index()
        draft = draft or {}
        self._build(set(preselect), list(new_utterances or draft.get("new", [])), speaker)
        self._apply_draft(draft, keep_speaker=bool(speaker))
        fit_to_screen(self, 1100, 760)

    # ---- remembered between openings (Josh, 21 October) --------------
    def _apply_draft(self, draft: dict, keep_speaker: bool = False):
        """The settings as they were left when the dialogue was last closed (in memory, for the
        open database): speaker, researcher, second language and its name, repetitions, Send as."""
        def choose(combo, value):
            i = combo.findData(value)
            if i >= 0 and combo.model().item(i) is not None and combo.model().item(i).isEnabled():
                combo.setCurrentIndex(i)
        if "speaker" in draft and not keep_speaker:
            choose(self.speaker, draft["speaker"])
        if "researcher" in draft:
            choose(self.researcher, draft["researcher"])
        if "l2" in draft:
            choose(self.l2, draft["l2"])
        if "l2_name" in draft:
            self.l2_name.setText(draft["l2_name"])
        if "repeat" in draft:
            self.repeat.setChecked(bool(draft["repeat"]))
        if "send_by" in draft:
            choose(self.send_by, draft["send_by"])

    def new_utterance_rows(self) -> list[dict]:
        """The new sentences typed in, as {language: translation}."""
        en = self.db.settings.primary_gloss
        lang = self.l2.currentData() or ""
        out = []
        for r in range(self.new_table.rowCount()):
            a = (self.new_table.item(r, 0).text() if self.new_table.item(r, 0) else "").strip()
            b = (self.new_table.item(r, 1).text() if self.new_table.item(r, 1) else "").strip()
            if a or b:
                out.append({k: v for k, v in ((en, a), (lang or "_", b)) if v})
        return out

    def draft(self, with_items: bool = True) -> dict:
        d = {"speaker": self.speaker.currentData(), "researcher": self.researcher.currentData(),
             "l2": self.l2.currentData() or "", "l2_name": self.l2_name.text(),
             "repeat": self.repeat.isChecked(), "send_by": self.send_by.currentData()}
        d["new"] = self.new_utterance_rows() if with_items else []
        return d

    def reset_request(self):
        """Reset request: clears the ticks and the new sentences; the settings stay."""
        if (any(r.ticked for r in self.model.rows) or self.new_table.rowCount()) and QMessageBox.question(
                self, f"Make {NAME} request", "Untick everything and clear the new sentences?") != QMessageBox.Yes:
            return
        self._untick_all()
        self.new_table.setRowCount(0)
        self._update_counts()

    # ---- the rows -----------------------------------------------------
    def _image_index(self) -> set[str]:
        folder = layout.images_folder(self.db.path) if self.db.path else None
        if folder is None or not folder.is_dir():
            return set()
        return {p.stem.lower() for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in layout.IMAGE_EXTENSIONS}

    def _rows(self, preselect) -> list[_Row]:
        db = self.db
        rows = []
        for e, t in db.all_tokens():
            r = _Row()
            r.entry, r.token, r.utterance = e, t, is_utterance(e)
            r.recorded = el.recording_path(db, e, t) is not None
            r.image = (not r.utterance) and filenames.image_stem(db, e, t).lower() in self._images
            r.kind = el.RERECORD if r.recorded else el.NEW   # Josh, 20 October: a soundfile means rerecord
            r.ticked = t.id in preselect
            show, texts = el.card_texts(db, el.Item(el.NEW, e, t), [db.settings.primary_gloss])
            form = el._form(db, t) or (db.lemma(e) if not r.utterance else e.label)
            tags = "" if r.utterance else db.settings.tags.display(t.tags)
            r.cells = ["", e.ref, form, tags, next(iter(texts.values()), ""),
                       (t.speaker or "?") if r.recorded else "", "✓" if r.image else ""]
            rows.append(r)
        return rows

    # ---- layout -------------------------------------------------------
    def _build(self, preselect, new_utterances, speaker):
        db, md, s = self.db, self.db.metadata, self.db.settings
        lay = QVBoxLayout(self)
        lay.addWidget(_title(f"Make {NAME} request"))
        form = QFormLayout()
        self.speaker = QComboBox()
        for p in md.participants:
            self.speaker.addItem(f"{p.code} · {p.name}" if p.name else p.code, p.code)
        if speaker:
            self.speaker.setCurrentIndex(max(0, self.speaker.findData(speaker)))
        else:
            current = self.main.session_speaker() if hasattr(self.main, "session_speaker") else ""
            if current and self.speaker.findData(current) >= 0:
                self.speaker.setCurrentIndex(self.speaker.findData(current))
        self.speaker.currentIndexChanged.connect(self._update_counts)
        form.addRow("Speaker", self.speaker)
        self.researcher = QComboBox()
        for p in md.researchers:
            self.researcher.addItem(f"{p.code} · {p.name}" if p.name else p.code, p.code)
        form.addRow("Researcher", self.researcher)
        self.l2 = QComboBox()
        self.l2.addItem("None", "")
        for lang in s.gloss_languages:
            if lang == s.primary_gloss:
                continue
            name = elicit_prompts.LANGUAGE_NAMES.get(lang.split("-")[0], lang)
            note = "" if elicit_prompts.prompts(lang) else " (prompts in English only: not built in yet)"
            self.l2.addItem(f"{lang} · {name}{note}", lang)
        if self.l2.count() > 1:
            self.l2.setCurrentIndex(1)
        self.l2.currentIndexChanged.connect(self._l2_changed)
        self.l2.setToolTip("Prompts, glosses and translations are shown in English and in this language. "
                           "Glosses and translations come from the database only, never machine-translated.")
        form.addRow("Second language", self.l2)
        self.l2_name = QLineEdit()
        self.l2_name.setPlaceholderText(md.language_name or md.language_code)
        self.l2_name_label = QLabel()
        form.addRow(self.l2_name_label, self.l2_name)
        self.repeat = QCheckBox("Ask for tokens to be said 2 or 3 times (utterances: once)")
        self.repeat.setChecked(True)
        form.addRow("", self.repeat)
        self.send_by = QComboBox()
        self.send_by.addItem("A link, through your Google Drive (recordings come straight back)", "drive")
        self.send_by.addItem("A file (zip) to send by hand", "file")
        if not cloud_keys.google_ready():
            self.send_by.model().item(0).setEnabled(False)
            self.send_by.setItemText(0, "A link, through Google Drive (this copy of Lemmatrix has no Google keys yet)")
            self.send_by.setCurrentIndex(1)
        form.addRow("Send as", self.send_by)
        lay.addLayout(form)

        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("search the references, forms, tags and glosses")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.scope = QComboBox()
        self.scope.addItems(["Everything", "Lemma tokens", "Citation tokens", "Utterances"])
        self.scope.currentIndexChanged.connect(self._filter)
        self.ticked_only = QCheckBox("Ticked only")
        self.ticked_only.toggled.connect(self._filter)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.scope)
        bar.addWidget(self.ticked_only)
        shown = QPushButton("Tick the tokens All data shows")
        shown.setToolTip("Ticks every token the main window's All data shows now (its filters and search)")
        shown.clicked.connect(self._tick_all_data)
        untick = QPushButton("Untick all")
        untick.clicked.connect(self._untick_all)
        bar.addWidget(shown)
        bar.addWidget(untick)
        tl.addLayout(bar)
        self.model = ItemModel(db, self._rows(preselect))
        self.proxy = ItemFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        for c, w in enumerate((28, 70, 150, 170, 220, 80, 56, 80)):
            self.table.setColumnWidth(c, w)
        hh.setStretchLastSection(True)
        self.table.doubleClicked.connect(self._double_clicked)
        self.model.dataChanged.connect(lambda *_: self._update_counts())
        tl.addWidget(self.table, 1)
        tl.addWidget(QLabel("Tick what to ask for (or double-click a row). One with a soundfile is a Rerecord: "
                            "the speaker hears it and repeats it. One without is New: the card shows its gloss "
                            "or translation."))
        split.addWidget(top)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel("<b>New utterances</b>: sentences to ask for, typed here; each answer becomes a new "
                            "utterance (U) when the recordings come back."))
        self.new_table = QTableWidget(0, 2)
        self.new_table.verticalHeader().hide()
        self.new_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.new_table.itemChanged.connect(lambda *_: self._update_counts())
        for tr in new_utterances:
            self._add_new_row(tr)
        bl.addWidget(self.new_table, 1)
        nb = QHBoxLayout()
        add = QPushButton("Add a sentence")
        add.clicked.connect(lambda: self._add_new_row({}, edit=True))
        rem = QPushButton("Remove")
        rem.clicked.connect(self._remove_new_row)
        nb.addWidget(add)
        nb.addWidget(rem)
        nb.addStretch(1)
        bl.addLayout(nb)
        split.addWidget(bottom)
        split.setSizes([520, 160])
        lay.addWidget(split, 1)

        self.count = QLabel()
        lay.addWidget(self.count)
        buttons = QDialogButtonBox()
        reset = buttons.addButton("Reset request", QDialogButtonBox.ResetRole)
        reset.setToolTip("Unticks everything and clears the new sentences (the settings stay)")
        reset.clicked.connect(self.reset_request)
        self.make_btn = buttons.addButton("Make request…", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._make)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._l2_changed()
        first = next((i for i, r in enumerate(self.model.rows) if r.ticked), None)
        if first is not None:                     # everything shows; the first ticked one in view
            self.table.scrollTo(self.proxy.mapFromSource(self.model.index(first, 0)))

    def done(self, result):
        """The ticks, the new sentences and the settings are kept for next time (the right-click
        Add to ɛλicit request adds to the ticks); once a request is made the ticks and the new
        sentences are cleared and the settings stay."""
        if hasattr(self.main, "elicit_basket"):
            made = self.made is not None
            self.main.elicit_basket = [] if made else [r.token.id for r in self.model.rows if r.ticked]
            self.main.elicit_draft = self.draft(with_items=not made)
        super().done(result)

    def _l2_changed(self, *_):
        lang = self.l2.currentData() or ""
        name = elicit_prompts.LANGUAGE_NAMES.get(lang.split("-")[0], lang) if lang else ""
        self.l2_name_label.setText(f"Language's name in {name}" if lang else "Language's name")
        self.l2_name.setEnabled(bool(lang))
        self.l2_name.setToolTip(f"How \"{self.db.metadata.language_name}\" is written in {name}, for the "
                                f"question \"How do you say this in …?\" (e.g. italiensk)" if lang else "")
        en = self.db.settings.primary_gloss
        self.new_table.setHorizontalHeaderLabels([f"Translation ({en})", f"Translation ({lang})" if lang else "—"])
        self.new_table.setColumnHidden(1, not lang)
        self._update_counts()

    def _add_new_row(self, translations: dict, edit: bool = False):
        r = self.new_table.rowCount()
        self.new_table.insertRow(r)
        en = self.db.settings.primary_gloss
        lang = self.l2.currentData() if hasattr(self, "l2") else ""
        other = next((v for k, v in translations.items() if k != en), "")
        self.new_table.setItem(r, 0, QTableWidgetItem(translations.get(en, "")))
        self.new_table.setItem(r, 1, QTableWidgetItem(translations.get(lang, other) if lang else other))
        if edit:
            self.new_table.setCurrentCell(r, 0)
            self.new_table.editItem(self.new_table.item(r, 0))

    def _remove_new_row(self):
        rows = sorted({i.row() for i in self.new_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.new_table.removeRow(r)
        self._update_counts()

    def _filter(self, *_):
        self.proxy.text = self.search.text().strip().casefold()
        self.proxy.scope = self.scope.currentIndex()
        self.proxy.ticked_only = self.ticked_only.isChecked()
        self.proxy.invalidate()

    def _double_clicked(self, idx):
        src = self.proxy.mapToSource(idx)
        if src.column() != 0:
            r = self.model.rows[src.row()]
            r.ticked = not r.ticked
            self.model.dataChanged.emit(self.model.index(src.row(), 0), self.model.index(src.row(), 0))

    def _tick_all_data(self):
        try:
            shown = {r.token.id for r in self.main.all_table.visible_rows()}
        except AttributeError:
            shown = set()
        for r in self.model.rows:
            if r.token.id in shown:
                r.ticked = True
        self.model.layoutChanged.emit()
        self._update_counts()

    def _untick_all(self):
        for r in self.model.rows:
            r.ticked = False
        self.model.layoutChanged.emit()
        self._update_counts()

    # ---- what will be sent ---------------------------------------------
    def items(self) -> list:
        out = [el.Item(r.kind, r.entry, r.token) for r in self.model.rows if r.ticked]
        en = self.db.settings.primary_gloss
        lang = self.l2.currentData() or ""
        for r in range(self.new_table.rowCount()):
            a = (self.new_table.item(r, 0).text() if self.new_table.item(r, 0) else "").strip()
            b = (self.new_table.item(r, 1).text() if self.new_table.item(r, 1) else "").strip()
            if a or (b and lang):
                tr = {en: a} if a else {}
                if b and lang:
                    tr[lang] = b
                out.append(el.Item(el.NEW_UTTERANCE, translations=tr))
        return out

    def _update_counts(self, *_):
        if not hasattr(self, "count"):
            return
        items = self.items()
        size = el.estimated_size(self.db, items)
        n_re = sum(1 for i in items if i.kind == el.RERECORD)
        text = f"{len(items)} card{'s' if len(items) != 1 else ''}"
        if n_re:
            text += f" ({n_re} rerecord{'s' if n_re != 1 else ''})"
        text += f" · about {_mb(size)} with the recordings coming back"
        if size > el.SIZE_WARNING:
            text += " · over 50 MB: consider a smaller request"
        self.count.setText(text)
        self.make_btn.setEnabled(bool(items) and self.speaker.count() > 0)

    def _warnings(self, items) -> bool:
        """The warnings before sending; True to go on."""
        db = self.db
        problems = []
        missing = [el.item_label(db, i) for i in items if el.missing_translation(db, i)]
        if missing:
            problems.append("These have no Translation, so their cards will show the lemma's gloss and the "
                            "tags instead:\n  • " + "\n  • ".join(missing))
        ethics = [f"{el.item_label(db, i)}: {why}" for i in items if (why := el.ethics_problem(db, i))]
        if ethics:
            problems.append("This could potentially constitute an ethics violation. These rerecords send a "
                            "recording to another speaker, but:\n  • " + "\n  • ".join(ethics))
        size = el.estimated_size(db, items)
        if size > el.SIZE_WARNING:
            problems.append(f"The request comes to about {_mb(size)} with the recordings coming back: a lot for "
                            "a phone's storage and the speaker's data. A smaller request may be better.")
        if problems:
            box = QMessageBox(QMessageBox.Warning, f"Make {NAME} request", "\n\n".join(problems), parent=self)
            go = box.addButton("Make it anyway", QMessageBox.AcceptRole)
            box.addButton("Go back", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not go:
                return False
        code = self.speaker.currentData()
        p = db.metadata.participant(code)
        name = f"{p.name} ({code})" if p and p.name else code
        text = (f"Send this request only to {name}, someone who has a participant agreement with you. "
                "The page asks whoever opens it whether they are that person and whether they have signed an "
                "agreement, but that doesn't replace your own care.")
        if p is not None and not p.consent:
            text += f"\n\nNo consent form is linked for {code} in Edit → Lists."
        box = QMessageBox(QMessageBox.Information, f"Make {NAME} request", text, parent=self)
        go = box.addButton("Make the request", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        return box.clickedButton() is go

    def _make(self):
        db = self.db
        if not db.path:
            QMessageBox.information(self, f"Make {NAME} request", "Save the database first.")
            return
        if self.researcher.count() == 0:
            QMessageBox.information(self, f"Make {NAME} request",
                                    "Add yourself to the researchers first (Edit → Lists → Researchers).")
            return
        items = self.items()
        if not items or not self._warnings(items):
            return
        req = el.new_request(db, items, self.speaker.currentData(), self.researcher.currentData(),
                             self.l2.currentData() or "", self.l2_name.text(), self.repeat.isChecked(),
                             theme.accent().name())
        if self.send_by.currentData() == "drive":
            drive = google_drive(self.main)
            if drive is None:
                return
            try:
                run_with_progress(self, f"Make {NAME} request", "Putting the request in your Google Drive…",
                                  lambda progress, cancelled: el.publish_drive(
                                      db, req, items, drive, cloud_keys.GOOGLE_API_KEY, progress))
            except (OSError, el.ElicitError, gdrive.DriveError) as exc:
                shutil.rmtree(el.elicit_folder(db.path) / el.request_folder_name(req), ignore_errors=True)
                _drive_problem(self.main, f"Make {NAME} request", exc)
                return
            self.made = el.elicit_folder(db.path) / el.request_folder_name(req) / "request.json"
            self.request = req
            self.accept()
            self.main.refresh_elicit_icon()
            SentDialog(self.main, req, self.made).exec()
            return
        try:
            self.made = el.write_request(db, req, items)
        except (OSError, el.ElicitError) as exc:
            QMessageBox.warning(self, f"Make {NAME} request", f"The request couldn't be written: {exc}")
            return
        self.request = req
        self.accept()
        SentDialog(self.main, req, self.made).exec()


class SentDialog(QDialog):
    """The request is made: the file to send, and the message to paste with it."""

    def __init__(self, parent, req, path: Path):
        super().__init__(parent)
        self.setWindowTitle(f"{NAME} request made")
        self.path = path
        lay = QVBoxLayout(self)
        by_link = req.transport == "drive"
        lay.addWidget(_title(f"Send it to {req.speaker['name']}"))
        if by_link:
            lay.addWidget(QLabel("Paste this message (with its link) into WhatsApp, Signal or an email. The "
                                 f"recordings come back to your Google Drive by themselves. The link works until "
                                 f"{req.expires}."))
        else:
            lay.addWidget(QLabel(f"Send <b>{path.name}</b> by WhatsApp, Signal or email, with this message. "
                                 f"The request expires on {req.expires}."))
        self.text = QPlainTextEdit(el.message_text(req))
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)
        lay.addWidget(QLabel(f"It is kept in {layout.main_folder(parent.doc.db.path).name}/{el.ELICIT}/"
                             f"{path.parent.name}. When the recordings come back, choose {RECEIVE}."))
        row = QHBoxLayout()
        copy = QPushButton("Copy the message")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        if by_link:
            folder = QPushButton("Copy the link only")
            folder.clicked.connect(lambda: QGuiApplication.clipboard().setText(req.drive.get("link", "")))
        else:
            folder = QPushButton("Show the file")
            folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(folder)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(640, 420)


# --------------------------------------------------------------------------
# Receive ɛλicitation and review
# --------------------------------------------------------------------------

def choose_and_receive(main):
    """Receive ɛλicitation: the requests out through Google Drive (checked there), or a zip."""
    db = main.doc.db
    if not db.path:
        QMessageBox.information(main, RECEIVE, "Open the database the request was made from first.")
        return
    if el.outstanding_drive(db):
        ReceiveDialog(main).exec()
        return
    receive_zip(main)


def receive_zip(main):
    """Receive ɛλicitation from a zip the speaker sent: unpack it, and review it."""
    db = main.doc.db
    start = Path.home() / "Downloads"
    path, _ = QFileDialog.getOpenFileName(main, RECEIVE + ": the recordings' zip",
                                          str(start if start.is_dir() else Path.home()), "Zip files (*.zip)")
    if not path:
        return
    try:
        st = el.receive(db, path)
    except (OSError, el.ElicitError) as exc:
        QMessageBox.warning(main, RECEIVE, str(exc))
        return
    main.refresh_elicit_icon()
    ReviewDialog(main, st).exec()


class ReceiveDialog(QDialog):
    """The requests out through Google Drive, as they are there now: download a finished one (or
    take what has come so far), withdraw one; or receive a zip instead."""

    def __init__(self, main):
        super().__init__(main)
        self.main, self.db = main, main.doc.db
        self.setWindowTitle(RECEIVE)
        self.states: dict[str, el.DriveState] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(_title(RECEIVE))
        lay.addWidget(QLabel("Requests out through your Google Drive:"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Speaker", "Made", "Expires", "Now"))
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, w in enumerate((150, 100, 100)):
            self.table.setColumnWidth(c, w)
        self.table.currentCellChanged.connect(lambda *_: self._buttons())
        self.table.cellDoubleClicked.connect(lambda *_: self.download())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.get_btn = QPushButton("Download and review")
        self.get_btn.clicked.connect(self.download)
        self.withdraw_btn = QPushButton("Withdraw…")
        self.withdraw_btn.setToolTip("Deletes the request's folder in your Google Drive: its link stops working")
        self.withdraw_btn.clicked.connect(self.withdraw)
        check = QPushButton("Check again")
        check.clicked.connect(self.check)
        row.addWidget(self.get_btn)
        row.addWidget(self.withdraw_btn)
        row.addWidget(check)
        row.addStretch(1)
        zip_btn = QPushButton("From a zip file…")
        zip_btn.clicked.connect(self._zip)
        row.addWidget(zip_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(760, 360)
        self.requests = el.outstanding_drive(self.db)
        self._fill()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.check)

    def _fill(self):
        self.table.setRowCount(len(self.requests))
        for i, st in enumerate(self.requests):
            r = st.request
            state = self.states.get(r.id)
            now = state.summary(r) if state else "not checked yet"
            if state is None and r.expires < _dt.date.today().isoformat():
                now = "expired"
            sp = r.speaker
            for c, v in enumerate((f"{sp['code']} · {sp['name']}" if sp["name"] != sp["code"] else sp["code"],
                                   r.created[:10], r.expires, now)):
                self.table.setItem(i, c, QTableWidgetItem(v))
        if self.requests and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        self._buttons()

    def _current(self):
        i = self.table.currentRow()
        return self.requests[i] if 0 <= i < len(self.requests) else None

    def _buttons(self):
        st = self._current()
        state = self.states.get(st.request.id) if st else None
        self.get_btn.setEnabled(bool(state and not state.gone and (state.uploaded or state.finished)))
        self.withdraw_btn.setEnabled(st is not None)

    def _drive(self):
        return google_drive(self.main)

    def check(self):
        if not self.requests:
            return
        drive = self._drive()
        if drive is None:
            return
        try:
            found = run_with_progress(self, RECEIVE, "Looking in your Google Drive…",
                                      lambda p, c: {st.request.id: el.drive_state(drive, st) for st in self.requests})
        except (OSError, gdrive.DriveError) as exc:
            _drive_problem(self.main, RECEIVE, exc)
            return
        self.states.update(found)
        self.main.elicit_drive_ready = {k: (st.request.speaker["code"], v.uploaded,
                                            v.summary(st.request) if v.turned_down else "")
                                        for st in self.requests if (k := st.request.id) in self.states
                                        and ((v := self.states[k]).finished or v.turned_down)}
        self.main.refresh_elicit_icon()
        self._fill()

    def download(self):
        st = self._current()
        state = self.states.get(st.request.id) if st else None
        if st is None or state is None or not (state.uploaded or state.finished):
            return
        if not state.finished:
            if QMessageBox.question(self, RECEIVE, f"{st.request.speaker['code']} hasn't finished: {state.uploaded} "
                                    f"of {len(st.request.cards)} cards have come so far. Take those and end the "
                                    "request? Its link then stops working.") != QMessageBox.Yes:
                return
        drive = self._drive()
        if drive is None:
            return
        try:
            got = run_with_progress(self, RECEIVE, "Downloading the recordings…",
                                    lambda p, c: el.receive_drive(self.db, st, drive, state, p))
        except (OSError, el.ElicitError, gdrive.DriveError) as exc:
            _drive_problem(self.main, RECEIVE, exc)
            return
        self.accept()
        self.main.refresh_elicit_icon()
        ReviewDialog(self.main, got).exec()

    def withdraw(self):
        st = self._current()
        if st is None:
            return
        state = self.states.get(st.request.id)
        what = (f"Withdraw the request for {st.request.speaker['code']}? Its folder in your Google Drive is deleted, "
                "with anything recorded so far, and the link stops working.")
        if state is not None and state.turned_down:
            what = (f"The request was {state.summary(st.request)}. Delete its folder in your Google Drive?")
        if QMessageBox.question(self, RECEIVE, what) != QMessageBox.Yes:
            return
        drive = self._drive()
        if drive is None:
            return
        try:
            run_with_progress(self, RECEIVE, "Deleting the request's folder…",
                              lambda p, c: el.close_drive(drive, st, "withdrawn " + _dt.date.today().isoformat()))
        except (OSError, gdrive.DriveError) as exc:
            _drive_problem(self.main, RECEIVE, exc)
            return
        self.requests.remove(st)
        self._fill()
        self.main.refresh_elicit_icon()

    def _zip(self):
        self.accept()
        receive_zip(self.main)


class ReviewDialog(QDialog):
    """Play through the recordings, approve or reject them one by one (or Approve all); for a
    rerecord, compare the old and the new and keep one. Closing applies what was decided (one
    undo step); anything not decided waits for later."""

    COLS = ("#", "Asked for", "Card", "Came back", "Decision")

    def __init__(self, main, st: el.Stored):
        super().__init__(main)
        self.main, self.st = main, st
        self.db = main.doc.db
        self.decisions: dict[int, str] = {}
        sp = st.request.speaker
        self.setWindowTitle(f"Review {NAME} recordings")
        lay = QVBoxLayout(self)
        lay.addWidget(_title(f"Recordings from {sp['name']} ({sp['code']})" if sp["name"] != sp["code"]
                             else f"Recordings from {sp['code']}"))
        answers = (st.response or {}).get("cards", [])
        rec = sum(1 for a in answers if a.get("status") == "recorded")
        skipped = sum(1 for a in answers if a.get("status") == "skipped")
        info = f"Request of {st.request.created[:10]}: {len(st.request.cards)} cards, {rec} recorded"
        if skipped:
            info += f", {skipped} skipped"
        missing = len(st.request.cards) - len(answers)
        if missing:
            info += f", {missing} not reached"
        lay.addWidget(QLabel(info + "."))
        self.table = QTableWidget(len(st.request.cards), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        for c, w in enumerate((36, 300, 110, 150, 160)):
            self.table.setColumnWidth(c, w)
        hh.setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        self.waiting = {c.n for c in el.waiting(self.db, st)}
        self._fill()
        self.table.currentCellChanged.connect(lambda *_: self._current_changed())
        self.table.cellDoubleClicked.connect(lambda *_: self.play_new())

        row = QHBoxLayout()
        self.play_new_btn = QPushButton("Play new (Space)")
        self.play_new_btn.clicked.connect(self.play_new)
        self.play_old_btn = QPushButton("Play old")
        self.play_old_btn.clicked.connect(self.play_old)
        self.approve_btn = QPushButton("Approve (A)")
        self.approve_btn.clicked.connect(lambda: self.decide(el.APPROVED))
        self.reject_btn = QPushButton("Reject (R)")
        self.reject_btn.clicked.connect(lambda: self.decide(el.REJECTED))
        self.undecide_btn = QPushButton("Undecided")
        self.undecide_btn.clicked.connect(lambda: self.decide(None))
        all_btn = QPushButton("Approve all")
        all_btn.setToolTip("Approves every recording not decided yet")
        all_btn.clicked.connect(self.approve_all)
        for b in (self.play_new_btn, self.play_old_btn, self.approve_btn, self.reject_btn, self.undecide_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(all_btn)
        lay.addLayout(row)
        self.autoplay = QCheckBox("Play each recording when it is selected")
        self.autoplay.setChecked(True)
        lay.addWidget(self.autoplay)
        self.summary = QLabel()
        lay.addWidget(self.summary)
        bottom = QHBoxLayout()
        self.again_btn = QPushButton("Send again…")
        self.again_btn.setToolTip("A new request with the cards skipped or rejected")
        self.again_btn.clicked.connect(self.send_again)
        bottom.addWidget(self.again_btn)
        bottom.addStretch(1)
        done = QPushButton("Close")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        lay.addLayout(bottom)
        fit_to_screen(self, 900, 600)
        first = next((i for i, c in enumerate(st.request.cards) if c.n in self.waiting), 0)
        self.table.setCurrentCell(first, 1)
        self._current_changed(play=False)

    # ---- the table ----------------------------------------------------
    def _status(self, c) -> str:
        a = self.st.answer(c.n)
        if a is None:
            return "Not reached"
        if a.get("status") == "skipped":
            return f"Skipped by {self.st.request.speaker['code']}"
        if self.st.recording(c.n) is None:
            return "Recording missing"
        secs = a.get("seconds")
        return f"Recorded{f' ({secs:.1f} s)' if isinstance(secs, (int, float)) else ''}"

    def _decision_text(self, c) -> str:
        d = self.decisions.get(c.n)
        if d is None and c.n not in self.waiting:
            saved = self.st.review.get(str(c.n), {}).get("decision")
            d = {el.APPROVED: "in the database", el.REJECTED: "rejected"}.get(saved)
            if d:
                return f"Done ({d})"
            return ""
        if d == el.APPROVED:
            return "Keep new" if c.kind == el.RERECORD else "Approve"
        if d == el.REJECTED:
            return "Keep old" if c.kind == el.RERECORD else "Reject"
        return "waiting" if c.n in self.waiting else ""

    def _fill(self):
        kinds = {el.NEW: "New", el.RERECORD: "Rerecord", el.NEW_UTTERANCE: "New utterance"}
        for i, c in enumerate(self.st.request.cards):
            vals = (str(c.n), c.label, kinds.get(c.kind, c.kind), self._status(c), self._decision_text(c))
            for col, v in enumerate(vals):
                it = self.table.item(i, col)
                if it is None:
                    it = QTableWidgetItem()
                    self.table.setItem(i, col, it)
                it.setText(v)
                if col == 4:
                    it.setForeground(theme.colour("muted") if v == "waiting" else self.palette().text())
        undecided = sum(1 for n in self.waiting if n not in self.decisions)
        approved = sum(1 for d in self.decisions.values() if d == el.APPROVED)
        rejected = sum(1 for d in self.decisions.values() if d == el.REJECTED)
        if hasattr(self, "summary"):
            self.summary.setText(f"To approve: {approved} · to reject: {rejected} · undecided: {undecided}"
                                 + (" (they wait for later when you close)" if undecided else ""))
            self.again_btn.setEnabled(bool(self._again_numbers()))

    def _card(self):
        r = self.table.currentRow()
        return self.st.request.cards[r] if 0 <= r < len(self.st.request.cards) else None

    def _current_changed(self, play: bool = True):
        c = self._card()
        can = c is not None and c.n in self.waiting
        self.play_new_btn.setEnabled(c is not None and self.st.recording(c.n) is not None)
        old = self._old_path(c)
        self.play_old_btn.setEnabled(old is not None)
        for b in (self.approve_btn, self.reject_btn, self.undecide_btn):
            b.setEnabled(can)
        if c is not None:
            re = c.kind == el.RERECORD
            self.approve_btn.setText("Keep new (A)" if re else "Approve (A)")
            self.reject_btn.setText("Keep old (R)" if re else "Reject (R)")
        if play and can and self.autoplay.isChecked():
            self.play_new()

    def _old_path(self, c):
        if c is None or c.kind == el.NEW_UTTERANCE:
            return None
        item = self.db.item_by_id(c.entry)
        t = next((t for t in item.tokens if t.id == c.token), None) if item is not None else None
        return el.recording_path(self.db, item, t) if t is not None else None

    def _play(self, path):
        if path is None:
            return
        try:
            self.main.player.play([path])
        except Exception as exc:                  # noqa: BLE001 (audio errors are reported, not fatal)
            QMessageBox.warning(self, "Play", str(exc))

    def play_new(self):
        c = self._card()
        if c is not None:
            self._play(self.st.recording(c.n))

    def play_old(self):
        self._play(self._old_path(self._card()))

    def decide(self, decision):
        c = self._card()
        if c is None or c.n not in self.waiting:
            return
        if decision is None:
            self.decisions.pop(c.n, None)
        else:
            self.decisions[c.n] = decision
        self._fill()
        if decision is not None:                  # on to the next one waiting
            rows = [i for i, x in enumerate(self.st.request.cards)
                    if x.n in self.waiting and x.n not in self.decisions]
            later = [i for i in rows if i > self.table.currentRow()] or rows
            if later:
                self.table.setCurrentCell(later[0], 1)

    def approve_all(self):
        for n in self.waiting:
            self.decisions.setdefault(n, el.APPROVED)
        self._fill()

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key_Space:
            self.play_new()
        elif k == Qt.Key_A:
            self.decide(el.APPROVED)
        elif k == Qt.Key_R:
            self.decide(el.REJECTED)
        else:
            super().keyPressEvent(event)

    # ---- applying -----------------------------------------------------
    def _again_numbers(self) -> list[int]:
        out = [c.n for c in el.skipped(self.st)]
        out += [n for n, d in self.decisions.items() if d == el.REJECTED]
        out += [int(k) for k, v in self.st.review.items() if v.get("decision") == el.REJECTED]
        return sorted(set(out))

    def apply(self) -> bool:
        """Put the approved recordings in (one undo step) and note every decision."""
        approved = [n for n, d in self.decisions.items() if d == el.APPROVED]
        rejected = [n for n, d in self.decisions.items() if d == el.REJECTED]
        if approved:
            plan = el.plan(self.db, self.st, sorted(approved))
            doc = self.main.doc
            label = f"{NAME}: recordings from {self.st.request.speaker['code']}"
            doc.undo.beginMacro(label)
            problems = doc.apply_changes(label, plan.pairs, plan.renames) if (plan.pairs or plan.renames) else []
            if not problems and plan.new_utterances:
                moved = []
                try:
                    for held, dest in plan.new_renames:   # into place first; undo moves them back
                        Path(dest).parent.mkdir(parents=True, exist_ok=True)
                        Path(held).rename(dest)
                        moved.append((held, dest))
                except OSError as exc:
                    for held, dest in reversed(moved):
                        Path(dest).rename(held)
                    problems = [str(exc)]
                else:
                    doc.add_many(label, plan.new_utterances, plan.new_renames)
            doc.undo.endMacro()
            if problems:
                el.discard_plan(plan)
                QMessageBox.warning(self, f"Review {NAME} recordings",
                                    "The recordings couldn't be put in: " + "; ".join(problems))
                return False
            today = _dt.date.today().isoformat()
            for n, applied in plan.applied.items():
                if "utterance" in applied:
                    dest = storage.utterance_folder(self.db)
                else:
                    dest = storage.folder_for(self.db, self.db.item_by_id(self.st.request.card(n).entry))
                try:
                    applied["size"] = (Path(dest) / applied["file"]).stat().st_size
                except OSError:
                    pass
                self.st.review[str(n)] = {"decision": el.APPROVED, "applied": applied, "date": today}
            if plan.notes:
                QMessageBox.information(self, f"Review {NAME} recordings", "\n".join(plan.notes))
        for n in rejected:
            self.st.review[str(n)] = {"decision": el.REJECTED, "date": _dt.date.today().isoformat()}
        if approved or rejected:
            try:
                self.st.save_review()
            except OSError as exc:
                QMessageBox.warning(self, f"Review {NAME} recordings", f"The review couldn't be noted: {exc}")
        self.decisions.clear()
        return True

    def done(self, result):
        self.main.player.stop()
        if not self.apply():
            return
        super().done(result)
        self.main.refresh_elicit_icon()
        left = len(el.waiting(self.db, self.st))
        if left:
            self.main.statusBar().showMessage(f"{NAME}: {left} recording{'s' if left != 1 else ''} saved for "
                                              "review later.", 8000)

    def send_again(self):
        numbers = self._again_numbers()
        items = el.items_again(self.db, self.st, numbers)
        if not items:
            return
        speaker = self.st.request.speaker["code"]
        self.accept()
        new_utts = [i.translations for i in items if i.kind == el.NEW_UTTERANCE]
        pre = [i.token.id for i in items if i.kind != el.NEW_UTTERANCE]
        RequestDialog(self.main, pre, new_utts, speaker, draft=getattr(self.main, "elicit_draft", None)).exec()


def remind(main):
    """On opening a database: recordings waiting for review, with Review now and Later."""
    waiting = el.waiting_reviews(main.doc.db)
    if not waiting:
        return
    lines = [f"{NAME}: {n} recording{'s' if n != 1 else ''} from {st.request.speaker['code']} "
             f"{'are' if n != 1 else 'is'} waiting for review." for st, n in waiting]
    box = QMessageBox(QMessageBox.Information, NAME, "\n".join(lines), parent=main)
    now = box.addButton("Review now", QMessageBox.AcceptRole)
    box.addButton("Later", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is now:
        ReviewDialog(main, waiting[0][0]).exec()


def review_waiting(main):
    """The button's menu: review the first request with recordings waiting."""
    waiting = el.waiting_reviews(main.doc.db)
    if waiting:
        ReviewDialog(main, waiting[0][0]).exec()
