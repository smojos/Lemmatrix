"""The main window: lemma list on the left, the Matrix on the right."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDate, QFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__, audio, matrix as mx, storage
from ..defaults import new_database
from ..model import Database, Entry
from .dialogs import EntryDialog, MetadataDialog, PreferencesDialog, TagStructureDialog
from .document import Document
from .fields_dialog import FieldsDialog
from .filter_dialogs import ConfigureColumnsDialog
from .icons import icon
from .matrix_dialogs import ConfigureCellDialog, ConfigureMatrixDialog, ask_matrix_name
from .matrix_view import MatrixView
from .prefs import Prefs
from .table import ChipsDelegate, Column, DrawingDelegate, FilterTable
from .token_dialog import Slot, TokenDialog
from .widgets import ipa_font

SAMPLE = Path(__file__).resolve().parent.parent.parent / "samples" / "Sample.xml"
ALL_DATA, LEMMA_TAG, TAG_TAG = 0, 1, 2
KINDS = {LEMMA_TAG: mx.LEMMA_TAG, TAG_TAG: mx.TAG_TAG}


class TokenRow:
    """A row of All data: one token of one entry (compared by identity, not content)."""
    __slots__ = ("entry", "index")

    def __init__(self, entry: Entry, index: int):
        self.entry, self.index = entry, index

    @property
    def token(self):
        return self.entry.tokens[self.index]

    def __eq__(self, other):
        return isinstance(other, TokenRow) and other.entry is self.entry and other.index == self.index

    def __hash__(self):
        return hash((id(self.entry), self.index))


def tool(text: str, icon_name: str | None, fn, tip: str = "") -> QToolButton:
    b = QToolButton()
    b.setText(text)
    if icon_name:
        b.setIcon(icon(icon_name, 20))
        b.setIconSize(QSize(20, 20))
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setToolTip(tip or text)
    b.setAutoRaise(True)
    b.clicked.connect(fn)
    return b


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.prefs = Prefs()
        self.player = audio.Player()
        self.doc = Document(db or new_database())
        self.doc.setParent(self)
        self.configs: dict = {}               # (kind, word class) -> current MatrixConfig
        self.switched = {LEMMA_TAG: False, TAG_TAG: False}
        self.layouts: dict = {}
        self.dialog_autoplay = False
        self.resize(1500, 920)
        self._build()
        self._build_menus()
        self.doc.changed.connect(self._doc_changed)
        self.doc.dirtyChanged.connect(lambda d: self._update_title())
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self._autosave)
        self._apply_autosave()
        self.load_database(self.doc.db)

    # ================================================================ layout
    def _bar(self) -> tuple[QFrame, QVBoxLayout]:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)
        return f, lay

    def _row(self, lay, *widgets, stretch=True) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        for w in widgets:
            row.addWidget(w)
        if stretch:
            row.addStretch(1)
        lay.addLayout(row)
        return row

    def _build(self):
        main = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main)

        # ---- left: lemma list + its options -------------------------------
        left = QSplitter(Qt.Vertical)
        self.lemmas = FilterTable()
        left.addWidget(self.lemmas)
        bar, bl = self._bar()
        self.lemma_count = QLabel()
        self.lemma_count.setStyleSheet("color: #555;")
        self._row(bl, tool("Add", "add", self.add_entry, "Add a lemma"),
                  tool("Delete", "delete", self.delete_entry, "Delete the selected lemma (Delete)"),
                  tool("Edit", "edit", self.edit_entry, "Edit the selected lemma (Enter)"),
                  tool("Configure columns", "gear", self.configure_lemma_columns),
                  tool("Clear all filters", None, self._clear_lemma_filters))
        self.lemma_search = QLineEdit()
        self.lemma_search.setPlaceholderText("quick search of the visible columns")
        self.lemma_search.setClearButtonEnabled(True)
        bl.addWidget(self.lemma_search)
        cv = QLineEdit()
        cv.setPlaceholderText("CV shape filter, e.g. (C)V(V)C(.CVC) — Stage 2")
        cv.setEnabled(False)
        cv.setToolTip("Matches the Lemma field. Needs the analysis engine (Stage 2).")
        bl.addWidget(cv)
        bl.addWidget(self.lemma_count)
        bl.addStretch(1)
        left.addWidget(bar)
        left.setSizes([700, 170])
        main.addWidget(left)

        # ---- right: Matrix + options + session ----------------------------
        right = QSplitter(Qt.Vertical)
        box = QGroupBox("Matrix")
        box.setStyleSheet("QGroupBox { font-weight: 700; }")
        bxl = QVBoxLayout(box)
        top = QHBoxLayout()
        self.count_line = QLabel()
        self.count_line.setStyleSheet("color: #444; font-weight: normal;")
        top.addWidget(self.count_line)
        top.addStretch(1)
        self.tabs = QTabBar()
        for name in ("All data", "Lemma/Tag", "Tag/Tag"):
            self.tabs.addTab(name)
        self.tabs.setExpanding(False)
        self.tabs.setStyleSheet("QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
                                "QTabBar::tab:selected { background: #5b8fd6; color: white; }")
        top.addWidget(self.tabs)
        bxl.addLayout(top)
        self.views = QStackedWidget()
        self.all_table = FilterTable()
        self.lt_view = MatrixView(self.doc.db)
        self.tt_view = MatrixView(self.doc.db)
        for w in (self.all_table, self.lt_view, self.tt_view):
            self.views.addWidget(w)
        bxl.addWidget(self.views, 1)
        right.addWidget(box)

        bottom = QWidget()
        bot = QHBoxLayout(bottom)
        bot.setContentsMargins(0, 0, 0, 0)
        self.options = QStackedWidget()
        self.options.addWidget(self._all_data_bar())
        self.lt_bar = self._matrix_bar(LEMMA_TAG)
        self.tt_bar = self._matrix_bar(TAG_TAG)
        self.options.addWidget(self.lt_bar["widget"])
        self.options.addWidget(self.tt_bar["widget"])
        bot.addWidget(self.options, 1)
        bot.addWidget(self._session_panel())
        right.addWidget(bottom)
        right.setSizes([720, 150])
        main.addWidget(right)
        main.setSizes([470, 1030])

        # ---- signals -----------------------------------------------------
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        self._search_timers = {}
        for name, edit, fn in (("lemma", self.lemma_search, self.lemmas.proxy.set_search),
                               ("all", self.all_search, self.all_table.proxy.set_search)):
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(250)
            t.timeout.connect(lambda e=edit, f=fn: f(e.text()))
            edit.textChanged.connect(lambda _, t=t: t.start())
            self._search_timers[name] = t
        self.lemmas.filtersChanged.connect(lambda: self.schedule_refresh())
        self.lemmas.rowActivated.connect(lambda e: self.edit_entry())
        self.lemmas.deleteRequested.connect(self.delete_entry)
        self.lemmas.contextRequested.connect(self._lemma_menu)
        self.lemmas.selectionModel().currentRowChanged.connect(lambda *a: self._lemma_selected())
        self.all_table.filtersChanged.connect(self._update_counts)
        self.all_table.rowActivated.connect(lambda r: self.edit_token())
        self.all_table.deleteRequested.connect(self.delete_token)
        self.all_table.contextRequested.connect(self._all_menu)
        self.all_table.model_.edited.connect(self._cell_edited)
        self.tabs.currentChanged.connect(self._tab_changed)
        for view, tab in ((self.lt_view, LEMMA_TAG), (self.tt_view, TAG_TAG)):
            view.tokenClicked.connect(lambda r, c, n, tab=tab: self._token_clicked(tab, r, c, n))
            view.cellActivated.connect(lambda r, c, n, tab=tab: self._cell_activated(tab, r, c, n))
            view.contextRequested.connect(lambda r, c, n, pos, tab=tab: self._matrix_menu(tab, pos))
            view.deleteRequested.connect(self.delete_token)
            view.switchRequested.connect(lambda tab=tab: self.switch_axes(tab))

    def _all_data_bar(self) -> QWidget:
        bar, bl = self._bar()
        self.all_count = QLabel()
        self.all_count.setStyleSheet("color: #555;")
        self._row(bl, tool("Add", "add", self.add_token, "Add a token"),
                  tool("Delete", "delete", self.delete_token, "Delete the selected token (Delete)"),
                  tool("Edit", "edit", self.edit_token, "Edit the selected token (Enter)"),
                  tool("Configure columns", "gear", self.configure_all_columns),
                  tool("Clear all filters", None, self._clear_all_filters))
        self.all_search = QLineEdit()
        self.all_search.setPlaceholderText("quick search of the visible columns")
        self.all_search.setClearButtonEnabled(True)
        cv = QLineEdit()
        cv.setPlaceholderText("CV shape filter (Phonetic) — Stage 2")
        cv.setEnabled(False)
        row = self._row(bl, self.all_search, cv, stretch=False)
        row.setStretch(0, 2)
        row.setStretch(1, 1)
        bl.addWidget(self.all_count)
        bl.addStretch(1)
        return bar

    def _matrix_bar(self, tab) -> dict:
        bar, bl = self._bar()
        d = {"widget": bar}
        self._row(bl, tool("Add", "add", self.add_token, "Add a token in the selected cell"),
                  tool("Delete", "delete", self.delete_token, "Delete the selected token (Delete)"),
                  tool("Edit", "edit", self.edit_token, "Edit the selected token (Enter)"),
                  tool("Play", "play", self.play_selected, "Play the selected token"))
        d["cls"] = QComboBox()
        d["cls"].setMinimumWidth(120)
        d["cls"].setToolTip("A matrix shows one word class at a time" if tab == LEMMA_TAG
                            else "Set by the selected lemma")
        if tab == TAG_TAG:
            d["cls"].setEnabled(False)
        else:
            d["cls"].activated.connect(lambda _: self._class_chosen())
        d["saved"] = QComboBox()
        d["saved"].setMinimumWidth(170)
        d["saved"].setToolTip("Saved matrices for this word class")
        d["saved"].activated.connect(lambda i, tab=tab: self._saved_chosen(tab, i))
        d["autoplay"] = QCheckBox("Auto-play token soundfile")
        key = f"matrix/autoplay_{KINDS[tab]}"
        d["autoplay"].setChecked(self.prefs.get_bool(key))
        d["autoplay"].toggled.connect(lambda on, key=key: self.prefs.set_value(key, bool(on)))
        self._row(bl, QLabel("Matrix class"), d["cls"],
                  tool("Configure cell", "gear", lambda tab=tab: self.configure_cell(tab)),
                  tool("Configure matrix", "gear", lambda tab=tab: self.configure_matrix(tab)))
        self._row(bl, QLabel("Matrix"), d["saved"],
                  tool("Save matrix…", None, lambda tab=tab: self.save_matrix(tab)),
                  tool("Delete saved", None, lambda tab=tab: self.delete_saved_matrix(tab)),
                  d["autoplay"])
        bl.addStretch(1)
        return d

    def _session_panel(self) -> QWidget:
        f, sl = self._bar()
        t = QLabel("Current Session")
        t.setStyleSheet("font-weight: 700; font-size: 15px;")
        sl.addWidget(t)
        self.sess_file = QLabel()
        self.sess_file.setStyleSheet("font-style: italic;")
        self.sess_codes = QLabel()
        self.sess_codes.setStyleSheet("font-weight: 600;")
        self.sess_codes.setToolTip("Language and variety codes, set in Settings → Metadata")
        self.sess_speaker = QComboBox()
        self.sess_speaker.setToolTip("Speaker for new tokens and recordings (may be empty)")
        self.sess_speaker.currentTextChanged.connect(lambda t: setattr(self.prefs, "speaker", t))
        self.sess_date = QDateEdit(QDate.currentDate())
        self.sess_date.setDisplayFormat("yyyy-MM-dd")
        self.sess_date.setCalendarPopup(True)
        self.sess_date.setToolTip("Collection date for new tokens and recordings; resets to today "
                                  "each time Lemmatrix opens")
        self.sess_nodate = QPushButton("No date")
        self.sess_nodate.setCheckable(True)
        self.sess_nodate.toggled.connect(self.sess_date.setDisabled)
        for w in (self.sess_file, self.sess_codes, self.sess_speaker):
            sl.addWidget(w)
        dr = QHBoxLayout()
        dr.addWidget(self.sess_date, 1)
        dr.addWidget(self.sess_nodate)
        sl.addLayout(dr)
        sl.addStretch(1)
        f.setMaximumWidth(260)
        return f

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "&New database…", self.new_file, QKeySequence.New)
        self._act(f, "&Open…", self.open_file, QKeySequence.Open)
        self._act(f, "Open a copy of the sample database", self.open_sample)
        f.addSeparator()
        self._act(f, "&Save", self.save, QKeySequence.Save)
        self._act(f, "Save &as…", self.save_as, QKeySequence.SaveAs)
        f.addSeparator()
        self._act(f, "E&xit", self.close, QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        undo = self.doc.undo.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.doc.undo.createRedoAction(self, "Redo")
        redo.setShortcut(QKeySequence.Redo)
        e.addAction(undo)
        e.addAction(redo)
        s = mb.addMenu("&Settings")
        self._act(s, "&Metadata (language, variety, speakers)…", self.edit_metadata)
        self._act(s, "&Fields…", self.edit_fields)
        self._act(s, "&Tag structure…", self.edit_tags)
        self._act(s, "&Settings…", self.edit_settings, QKeySequence.Preferences)
        t = mb.addMenu("&Tools")
        self._act(t, "Update all sound file names", self.update_all_names)
        self._act(t, "Check for duplicate file names", self.check_duplicates)
        self._act(t, "Open the sound folder", self.open_sound_folder)
        v = mb.addMenu("&View")
        self._act(v, "Swap rows and columns", lambda: self.switch_axes(self.tabs.currentIndex()), "Ctrl+T")
        a = mb.addMenu("&Analyze")
        x = a.addAction("Analysis tools arrive with the analysis engine (Stage 2)")
        x.setEnabled(False)
        h = mb.addMenu("&Help")
        self._act(h, "About Lemmatrix", self.about)

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    # ============================================================ columns
    def _lemma_columns(self) -> list[Column]:
        db = self.doc.db
        s = db.settings
        cols = [Column("ref", "Reference", lambda e: e.ref)]
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    cols.append(Column(f"{f.name}:{lang}", f"{f.title} ({lang})" if len(s.gloss_languages) > 1
                                       else f.title, lambda e, n=f.name, l=lang: e.get(n, l)))
            else:
                cols.append(Column(f.name, f.title, lambda e, n=f.name: e.get(n), closed=f.closed,
                                   tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                                   ipa=f.role == "lemma"))
        return cols

    def _default_lemma_keys(self) -> list[str]:
        s = self.doc.db.settings
        keys = ["ref"]
        for f in s.entry_fields:
            if f.role == "lemma":
                keys.append(f.name)
            elif f.role == "gloss":
                keys.append(f"{f.name}:{s.primary_gloss}")
            elif f.role == "word-class":
                keys.append(f.name)
        return keys

    def _all_columns(self) -> list[Column]:
        db = self.doc.db
        s = db.settings
        defaults = mx.default_names(db)
        wcf = s.entry_field("word-class")
        gf = s.entry_field("gloss")

        def tag_tree():
            from ..model import ListItem
            out = []
            for wc in s.tags.word_classes:
                out.append(ListItem(wc.name, [self._group_item(g) for g in wc.groups]))
            out.append(ListItem("All classes", [self._group_item(g) for g in s.tags.all_classes]))
            return out

        cols = [
            Column("ref", "Reference", lambda r: r.entry.ref),
            Column("lemma", "Lemma", lambda r: db.lemma(r.entry), ipa=True),
            Column("gloss", "Gloss", lambda r: db.gloss(r.entry)),
            Column("wordclass", wcf.title if wcf else "Word Class", lambda r: db.word_class(r.entry),
                   closed=True, tree=lambda: s.list_items(wcf) if wcf else []),
            Column("tags", "Tags", lambda r: list(r.token.tags), closed=True, tree=tag_tree, multi=True,
                   unmarked=defaults, kind="chips",
                   tooltip=lambda r: ", ".join(r.token.tags) or "Citation (no tags)"),
            Column("drawing", "Pitch drawing", lambda r: r.token.get("Pitch"), kind="drawing"),
        ]
        for f in s.token_fields:
            cols.append(Column(
                "f:" + f.name, f.title,
                (lambda r, n=f.name, ml=f.multilingual: r.token.get(n, s.primary_gloss if ml else None)),
                closed=f.closed, tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                ipa=f.role in ("phonetic", "phonemic"),
                edit=lambda r, text: None))
        cols += [
            Column("speaker", "Speaker", lambda r: r.token.speaker),
            Column("date", "Date", lambda r: r.token.collected),
            Column("file", "Sound file", lambda r: r.token.file or db.expected_filename(r.entry, r.token),
                   color=lambda r: QColor("#888") if not r.token.file else
                   (QColor("#c62828") if r.token.file != db.expected_filename(r.entry, r.token) else None),
                   tooltip=lambda r: (f"Recorded as {r.token.file}\nExpected: "
                                      f"{db.expected_filename(r.entry, r.token)}") if r.token.file
                   else "Not recorded yet"),
        ]
        return cols

    def _group_item(self, g):
        from ..model import ListItem
        return ListItem(g.name, [ListItem(t.name) for t in g.tags] + [self._group_item(x) for x in g.groups])

    def _default_all_keys(self) -> list[str]:
        keys = ["ref", "lemma", "tags", "drawing"]
        keys += ["f:" + f.name for f in self.doc.db.settings.token_fields]
        return keys + ["speaker", "date", "file"]

    def _setup_columns(self):
        db = self.doc.db
        cols = self._lemma_columns()
        saved = self.prefs.get_list("columns/lemma")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_lemma_keys()
        self.lemmas.set_columns(cols, keys)
        self.lemmas.resizeColumnsToContents()
        cols = self._all_columns()
        saved = self.prefs.get_list("columns/alldata")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_all_keys()
        self.all_table.set_columns(cols, keys)
        defaults = mx.default_names(db)
        self.all_table.set_delegate("tags", ChipsDelegate(
            lambda r: mx.chips(db, mx.marked(r.token.tags, defaults), db.word_class(r.entry) or None)
            if r is not None else [], self.all_table))
        self.all_table.set_delegate("drawing", DrawingDelegate(
            lambda: (db.settings.pitch_low, db.settings.pitch_high), self.all_table))
        self._all_sized = False

    def configure_lemma_columns(self):
        cols = self._lemma_columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.lemmas.visible_keys())
        if dlg.exec():
            self.prefs.set_list("columns/lemma", dlg.chosen())
            self.lemmas.set_columns(cols, dlg.chosen())
            self.lemmas.set_rows(self.doc.db.entries)
            self.lemmas.resizeColumnsToContents()

    def configure_all_columns(self):
        cols = self._all_columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.all_table.visible_keys())
        if dlg.exec():
            self.prefs.set_list("columns/alldata", dlg.chosen())
            self._setup_columns()
            self.all_table.set_columns(cols, dlg.chosen())
            db = self.doc.db
            defaults = mx.default_names(db)
            self.all_table.set_delegate("tags", ChipsDelegate(
                lambda r: mx.chips(db, mx.marked(r.token.tags, defaults), db.word_class(r.entry) or None)
                if r is not None else [], self.all_table))
            self.all_table.set_delegate("drawing", DrawingDelegate(
                lambda: (db.settings.pitch_low, db.settings.pitch_high), self.all_table))
            self._all_sized = False
            self.refresh()

    # ============================================================ database
    def load_database(self, db: Database):
        self.player.stop()
        self.doc.db = db
        self.doc.undo.clear()
        self.doc.undo.setClean()
        self.doc._settings_dirty = False
        self.configs.clear()
        for v in (self.lt_view, self.tt_view):
            v.set_database(db)
        self._setup_columns()
        self.lemmas.set_rows(db.entries)
        self.lemma_search.clear()
        self.all_search.clear()
        self._fill_session()
        self._fill_classes()
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(ALL_DATA)
        self.tabs.blockSignals(False)
        self._tab_changed(ALL_DATA)
        if db.entries:
            self.lemmas.selectRow(0)
        self._update_title()

    def _fill_session(self):
        db = self.doc.db
        md = db.metadata
        self.sess_file.setText(Path(db.path).name if db.path else "(not saved yet)")
        self.sess_codes.setText("  ".join(x for x in (md.language_code, md.variety_code) if x)
                                or "no language code")
        self.sess_speaker.blockSignals(True)
        self.sess_speaker.clear()
        self.sess_speaker.addItem("")
        for p in md.participants:
            self.sess_speaker.addItem(p.code)
            if p.name:
                self.sess_speaker.setItemData(self.sess_speaker.count() - 1, p.name, Qt.ToolTipRole)
        if self.prefs.speaker and self.sess_speaker.findText(self.prefs.speaker) >= 0:
            self.sess_speaker.setCurrentText(self.prefs.speaker)
        self.sess_speaker.blockSignals(False)

    def _fill_classes(self):
        names = self.doc.db.settings.tags.word_class_names() + [mx.NO_CLASS]
        for bar in (self.lt_bar, self.tt_bar):
            cb = bar["cls"]
            current = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            for n in names:
                cb.addItem(mx.class_label(n), n)
            i = cb.findData(current) if current is not None else -1
            if i < 0:
                e = self.lemmas.current_row()
                i = cb.findData(mx.class_of(self.doc.db, e)) if e else 0
            cb.setCurrentIndex(max(0, i))
            cb.blockSignals(False)

    def session_speaker(self) -> str:
        return self.sess_speaker.currentText()

    def session_date(self) -> str:
        return "" if self.sess_nodate.isChecked() else self.sess_date.date().toString("yyyy-MM-dd")

    def _update_title(self):
        db = self.doc.db
        name = Path(db.path).name if db.path else "Untitled"
        self.setWindowTitle(f"{'*' if self.doc.dirty else ''}{name} — Lemmatrix")

    def _doc_changed(self):
        self.lemmas.set_rows(self.doc.db.entries)
        self.schedule_refresh()
        self._update_title()

    def schedule_refresh(self, delay: int = 0):
        self._refresh_timer.start(delay)

    # ============================================================== matrix
    def _tab_changed(self, i):
        self.views.setCurrentIndex(i)
        self.options.setCurrentIndex(i)
        if i == LEMMA_TAG:
            e = self.lemmas.current_row()
            if e is not None:
                self._set_class(LEMMA_TAG, mx.class_of(self.doc.db, e))
        self.refresh()

    def _lemma_selected(self):
        e = self.lemmas.current_row()
        tab = self.tabs.currentIndex()
        if e is not None and tab == LEMMA_TAG and mx.class_of(self.doc.db, e) != self.lt_bar["cls"].currentData():
            self._set_class(LEMMA_TAG, mx.class_of(self.doc.db, e))
            self.refresh()
        elif tab == TAG_TAG:
            self.refresh()

    def _set_class(self, tab, wc):
        cb = (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["cls"]
        i = cb.findData(wc)
        if i >= 0:
            cb.setCurrentIndex(i)

    def _class_chosen(self):
        self.refresh()

    def _class_for(self, tab) -> str:
        if tab == TAG_TAG:
            e = self.lemmas.current_row()
            return mx.class_of(self.doc.db, e) if e is not None else mx.NO_CLASS
        return self.lt_bar["cls"].currentData() or mx.NO_CLASS

    def config_for(self, tab) -> mx.MatrixConfig:
        wc = self._class_for(tab)
        key = (KINDS[tab], wc)
        if key not in self.configs:
            self.configs[key] = mx.MatrixConfig(kind=KINDS[tab], word_class=wc)
        return self.configs[key]

    def _fill_saved(self, tab):
        cb = (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["saved"]
        cfg = self.config_for(tab)
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("(current)" if (cfg.x or cfg.y) else
                   ("(automatic)" if tab == LEMMA_TAG else "(not configured)"))
        for m in self.doc.db.settings.matrices:
            if m.kind == cfg.kind and m.word_class == cfg.word_class:
                cb.addItem(m.name)
        i = cb.findText(cfg.name) if cfg.name else 0
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)

    def _saved_chosen(self, tab, i):
        if i <= 0:
            return
        cb = (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["saved"]
        cfg = self.config_for(tab)
        for m in self.doc.db.settings.matrices:
            if m.kind == cfg.kind and m.word_class == cfg.word_class and m.name == cb.itemText(i):
                self.configs[(cfg.kind, cfg.word_class)] = m.copy()
        self.refresh()

    def refresh(self):
        db = self.doc.db
        tab = self.tabs.currentIndex()
        visible = self.lemmas.visible_rows()
        self.lemma_count.setText(f"{len(visible)} of {len(db.entries)} lemmas shown")
        if tab == ALL_DATA:
            vis = set(map(id, visible))
            rows = [TokenRow(e, i) for e in db.entries if id(e) in vis for i in range(len(e.tokens))]
            self.all_table.set_rows(rows)
            if not getattr(self, "_all_sized", False) and rows:
                self.all_table.resizeColumnsToContents()
                self._all_sized = True
            self._update_counts()
            return
        cfg = self.config_for(tab)
        self._fill_saved(tab)
        if tab == LEMMA_TAG:
            ents = mx.in_class(db, visible, cfg.word_class)
            lay = mx.lemma_tag_layout(db, ents, cfg)
            view = self.lt_view
            total = len(mx.in_class(db, db.entries, cfg.word_class))
            self.count_line.setText(f"{len(ents)} {mx.class_label(cfg.word_class)} lemmas shown "
                                    f"of {total}  ·  {len(db.entries)} lemmas in all")
        else:
            e = self.lemmas.current_row()
            if e is not None and e not in visible:
                e = None
            self._set_class(TAG_TAG, self._class_for(TAG_TAG))
            lay = mx.tag_tag_layout(db, e, cfg)
            view = self.tt_view
            self.count_line.setText(f"{e.ref}  {db.lemma(e)}  “{db.gloss(e)}”  ·  "
                                    f"{mx.class_label(mx.class_of(db, e))}" if e else "")
        if lay.message:
            self.count_line.setText((self.count_line.text() + "  ·  " if self.count_line.text() else "")
                                    + lay.message)
        if self.switched[tab]:
            lay = lay.transposed()
        self.layouts[tab] = lay
        view.set_layout(lay, cfg.cell)

    def _update_counts(self):
        shown = self.all_table.proxy.rowCount()
        total = self.all_table.model_.rowCount()
        n = self.all_table.active_filters()
        self.all_count.setText(f"{shown} of {total} tokens shown"
                               + (f"  ·  {n} column filter{'s' if n != 1 else ''} on" if n else ""))
        if self.tabs.currentIndex() == ALL_DATA:
            self.count_line.setText(f"{shown} tokens shown")

    def switch_axes(self, tab):
        if tab == ALL_DATA:
            return
        self.switched[tab] = not self.switched[tab]
        self.refresh()

    def configure_cell(self, tab):
        cfg = self.config_for(tab)
        dlg = ConfigureCellDialog(self, self.doc.db, cfg.cell)
        if dlg.exec():
            cfg.cell = dlg.chosen()
            self.refresh()

    def configure_matrix(self, tab):
        cfg = self.config_for(tab)
        if tab == TAG_TAG and self.lemmas.current_row() is None:
            QMessageBox.information(self, "Configure matrix", "Select a lemma first: its word class "
                                    "decides which tags are available.")
            return
        ents = mx.in_class(self.doc.db, self.lemmas.visible_rows(), cfg.word_class)
        start = cfg
        if tab == LEMMA_TAG and not cfg.x:
            start = cfg.copy()
            start.x = mx.auto_specs(self.doc.db, ents)
        dlg = ConfigureMatrixDialog(self, self.doc.db, start, ents)
        if dlg.exec():
            new = dlg.result_config()
            new.name = ""
            self.configs[(cfg.kind, cfg.word_class)] = new
            self.refresh()

    def save_matrix(self, tab):
        cfg = self.config_for(tab)
        if tab == TAG_TAG and not (cfg.x and cfg.y):
            QMessageBox.information(self, "Save matrix", "Configure the matrix first.")
            return
        mats = self.doc.db.settings.matrices
        existing = [m.name for m in mats if m.kind == cfg.kind and m.word_class == cfg.word_class]
        name = ask_matrix_name(self, existing, cfg.name)
        if not name:
            return
        saved = cfg.copy()
        if tab == LEMMA_TAG and not saved.x:
            saved.x = mx.auto_specs(self.doc.db, mx.in_class(self.doc.db, self.lemmas.visible_rows(),
                                                             cfg.word_class))
        saved.name = name
        mats[:] = [m for m in mats if not (m.kind == saved.kind and m.word_class == saved.word_class
                                           and m.name == name)] + [saved]
        self.configs[(cfg.kind, cfg.word_class)] = saved.copy()
        self.doc.settings_changed()

    def delete_saved_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.name:
            QMessageBox.information(self, "Delete saved matrix", "Choose a saved matrix first.")
            return
        if QMessageBox.question(self, "Delete saved matrix", f"Delete the saved matrix “{cfg.name}”?") \
                != QMessageBox.Yes:
            return
        mats = self.doc.db.settings.matrices
        mats[:] = [m for m in mats if not (m.kind == cfg.kind and m.word_class == cfg.word_class
                                           and m.name == cfg.name)]
        cfg.name = ""
        self.doc.settings_changed()

    # ================================================ tokens and playback
    def _view(self, tab):
        return self.lt_view if tab == LEMMA_TAG else self.tt_view

    def _slots(self, tab) -> list[Slot]:
        """Every place Back/Next visits, in reading order."""
        if tab == ALL_DATA:
            return [Slot(r.entry, r.index) for r in self.all_table.visible_rows()]
        lay = self.layouts.get(tab)
        slots = []
        if lay is None:
            return slots
        for r, c in lay.reading_order():
            if (r, c) in lay.greyed:
                continue
            hits = lay.tokens(r, c)
            if hits:
                for e, t in hits:
                    slots.append(Slot(e, e.tokens.index(t)))
            else:
                entry, tags = lay.target(r, c)
                if entry is not None:
                    slots.append(Slot(entry, None, tuple(tags), defaults=True))
        return slots

    def _open_dialog(self, slots, index, tab):
        if not slots:
            return
        self.dialog_autoplay = tab != ALL_DATA and \
            (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["autoplay"].isChecked()
        dlg = TokenDialog(self, slots, index)
        dlg.exec()
        self.refresh()

    def _cell_activated(self, tab, r, c, n):
        lay = self.layouts.get(tab)
        if lay is None or (r, c) in lay.greyed:
            return
        slots = self._slots(tab)
        hits = lay.tokens(r, c)
        if hits and n >= 0:
            e, t = hits[n]
            i = e.tokens.index(t)
            idx = next((k for k, s in enumerate(slots) if s.entry is e and s.index == i), 0)
        elif hits:
            return
        else:
            entry, tags = lay.target(r, c)
            if entry is None:
                return
            idx = next((k for k, s in enumerate(slots) if s.entry is entry and s.index is None
                        and set(s.tags) == set(tags)), None)
            if idx is None:
                slots.append(Slot(entry, None, tuple(tags), defaults=True))
                idx = len(slots) - 1
            slots[idx].explicit = True
        self._open_dialog(slots, idx, tab)

    def _token_clicked(self, tab, r, c, n):
        bar = self.lt_bar if tab == LEMMA_TAG else self.tt_bar
        if n >= 0 and bar["autoplay"].isChecked():
            self.play_selected()

    def _cell_edited(self, row, key, text):
        s = self.doc.db.settings
        name = key[2:]
        f = s.token_field(name)
        if f.role == "pitch":
            from .. import pitch as pitchmod
            text = pitchmod.normalise(text)

        def change(e, i=row.index):
            e.tokens[i].set(name, text.strip(), s.primary_gloss if f.multilingual else None, f.multilingual)
        self.doc.edit_entry(row.entry, change, f"Edit {f.title}")

    def selected_token(self):
        """(entry, token index) of the selected token in the current tab, or None."""
        tab = self.tabs.currentIndex()
        if tab == ALL_DATA:
            r = self.all_table.current_row()
            return (r.entry, r.index) if r else None
        hit = self._view(tab).selected_token()
        if hit:
            e, t = hit
            return e, e.tokens.index(t)
        return None

    def add_token(self):
        tab = self.tabs.currentIndex()
        if tab != ALL_DATA:
            view = self._view(tab)
            lay = self.layouts.get(tab)
            if view.selected and lay is not None:
                r, c, _ = view.selected
                if (r, c) in lay.greyed:
                    return
                entry, tags = lay.target(r, c)
                if entry is not None:
                    self._open_dialog([Slot(entry, None, tuple(tags), explicit=True, defaults=True)], 0, tab)
                    return
        row = self.all_table.current_row() if tab == ALL_DATA else None
        entry = row.entry if row else self.lemmas.current_row()
        if entry is None:
            QMessageBox.information(self, "Add token", "Select a lemma first.")
            return
        self._open_dialog([Slot(entry, None, (), explicit=True, defaults=True)], 0, tab)

    def edit_token(self):
        tab = self.tabs.currentIndex()
        if tab != ALL_DATA:
            view = self._view(tab)
            if view.selected:
                self._cell_activated(tab, *view.selected)
            return
        sel = self.selected_token()
        if sel is None:
            return
        slots = self._slots(tab)
        e, i = sel
        idx = next((k for k, s in enumerate(slots) if s.entry is e and s.index == i), 0)
        self._open_dialog(slots, idx, tab)

    def delete_token(self):
        sel = self.selected_token()
        if sel is None:
            return
        e, i = sel
        t = e.tokens[i]
        db = self.doc.db
        tags = " + ".join(mx.chips(db, t.tags, db.word_class(e) or None)) or "citation"
        with_file = bool(t.file) and self.prefs.delete_recordings_with_tokens
        msg = f"Delete the {tags} token of {e.ref} {db.lemma(e)}?"
        if with_file:
            msg += f"\nIts recording ({t.file}) goes to the Recycle Bin."
        if QMessageBox.question(self, "Delete token", msg) != QMessageBox.Yes:
            return
        if with_file:
            path = storage.sound_folder(db) / t.file
            self.player.stop()
            if path.exists():
                QFile.moveToTrash(str(path))
        self.doc.edit_entry(e, lambda en, i=i: en.tokens.pop(i), f"Delete token from {e.ref}")

    def play_selected(self):
        tab = self.tabs.currentIndex()
        db = self.doc.db
        folder = storage.sound_folder(db)
        paths = []
        sel = self.selected_token()
        if sel:
            e, i = sel
            if e.tokens[i].file:
                paths = [folder / e.tokens[i].file]
        elif tab != ALL_DATA and self._view(tab).selected:
            r, c, _ = self._view(tab).selected
            paths = [folder / t.file for _, t in self.layouts[tab].tokens(r, c) if t.file]
        if not paths:
            self.statusBar().showMessage("Nothing recorded here.", 3000)
            return
        try:
            if not self.player.play(paths):
                self.statusBar().showMessage("The recording isn't in the sound folder.", 4000)
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play", str(exc))

    # ---- context menus -------------------------------------------------
    def _menu(self, items, pos):
        m = QMenu(self)
        for item in items:
            if item is None:
                m.addSeparator()
                continue
            text, icon_name, fn = item
            a = m.addAction(icon(icon_name, 16), text) if icon_name else m.addAction(text)
            a.triggered.connect(fn)
        m.exec(pos)

    def _lemma_menu(self, row, pos):
        if row is not None:
            self.lemmas.select_row(row)
        self._menu([("Add lemma", "add", self.add_entry), ("Delete lemma", "delete", self.delete_entry),
                    ("Edit lemma", "edit", self.edit_entry), None,
                    ("Configure columns", "gear", self.configure_lemma_columns),
                    ("Clear all filters", None, self._clear_lemma_filters)], pos)

    def _all_menu(self, row, pos):
        if row is not None:
            self.all_table.select_row(row)
        self._menu([("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), ("Play", "play", self.play_selected), None,
                    ("Configure columns", "gear", self.configure_all_columns),
                    ("Clear all filters", None, self._clear_all_filters)], pos)

    def _matrix_menu(self, tab, pos):
        self._menu([("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), ("Play", "play", self.play_selected)], pos)

    def _clear_lemma_filters(self):
        self.lemma_search.clear()
        self.lemmas.clear_filters()

    def _clear_all_filters(self):
        self.all_search.clear()
        self.all_table.clear_filters()

    # ============================================================= entries
    def add_entry(self):
        dlg = EntryDialog(self, self.doc.db)
        if dlg.exec():
            e = dlg.new_entry(self.session_speaker(), self.session_date())
            self.doc.add_entry(e)
            self.lemmas.set_rows(self.doc.db.entries)
            self.lemmas.select_row(e)

    def edit_entry(self):
        e = self.lemmas.current_row()
        if e is None:
            return
        dlg = EntryDialog(self, self.doc.db, e)
        if dlg.exec():
            self.doc.edit_entry(e, dlg.apply, f"Edit {e.ref}")

    def delete_entry(self):
        e = self.lemmas.current_row()
        if e is None:
            return
        n = len(e.tokens)
        if QMessageBox.question(self, "Delete lemma",
                                f"Delete {e.ref} {self.doc.db.lemma(e)} and its {n} token(s)?\n"
                                "Its recordings stay in the sound folder. You can undo this.") \
                != QMessageBox.Yes:
            return
        self.doc.delete_entry(e)

    # ============================================================ settings
    def edit_metadata(self):
        dlg = MetadataDialog(self, self.doc.db)
        if dlg.exec():
            dlg.apply()
            self.doc.settings_changed()
            self._fill_session()
            self._setup_columns()
            self._maybe_update_names()

    def edit_fields(self):
        dlg = FieldsDialog(self, self.doc.db)
        if dlg.exec():
            if dlg.apply():
                self.doc.undo.clear()             # renamed fields can't be undone safely
            self._setup_columns()
            self.doc.settings_changed()

    def edit_tags(self):
        dlg = TagStructureDialog(self, self.doc.db)
        if dlg.exec():
            db = self.doc.db
            tag_renames, class_renames = dlg.renames()
            db.settings.tags = dlg.structure()
            wc_field = db.settings.entry_field("word-class")
            for e in db.entries:          # follow renamed tags and word classes
                if wc_field and e.get(wc_field.name) in class_renames:
                    e.set(wc_field.name, class_renames[e.get(wc_field.name)])
                for t in e.tokens:
                    if any(x in tag_renames for x in t.tags):
                        t.tags = db.settings.tags.sort(db.word_class(e),
                                                       [tag_renames.get(x, x) for x in t.tags])
            if tag_renames or class_renames:
                self.doc.undo.clear()     # renames can't be undone safely
            self.configs.clear()
            self._fill_classes()
            self._setup_columns()
            self.doc.settings_changed()
            self._maybe_update_names()

    def edit_settings(self):
        dlg = PreferencesDialog(self, self.doc.db, self.prefs)
        if dlg.exec():
            names_changed = dlg.apply()
            self._apply_autosave()
            self.all_table.model_.ipa.setPointSize(self.prefs.ipa_size)
            self.lemmas.model_.ipa.setPointSize(self.prefs.ipa_size)
            self.doc.settings_changed()
            if names_changed:
                self._maybe_update_names()

    def _maybe_update_names(self):
        db = self.doc.db
        stale = [(e, t) for e in db.entries for t in e.tokens
                 if t.file and t.file != db.expected_filename(e, t)]
        if not stale:
            return
        if db.settings.auto_update_names:
            self.update_all_names(ask=False)
        else:
            self.statusBar().showMessage(f"{len(stale)} sound file names are out of date "
                                         "(Tools → Update all sound file names).", 8000)

    # =============================================================== tools
    def update_all_names(self, ask: bool = True):
        db = self.doc.db
        folder = storage.sound_folder(db)
        stale = [(e, i) for e in db.entries for i, t in enumerate(e.tokens)
                 if t.file and t.file != db.expected_filename(e, t)]
        if not stale:
            if ask:
                QMessageBox.information(self, "Sound file names", "All sound file names are up to date.")
            return
        if ask and QMessageBox.question(self, "Sound file names",
                                        f"Rename {len(stale)} recordings to match their tokens?") != QMessageBox.Yes:
            return
        problems, done = [], 0
        for e, i in stale:
            t = e.tokens[i]
            new = db.expected_filename(e, t)
            src, dst = folder / t.file, folder / new
            if not src.exists():
                problems.append(f"{t.file}: not in the sound folder")
                continue
            if dst.exists():
                problems.append(f"{t.file}: {new} already exists")
                continue
            try:
                src.rename(dst)
            except OSError as exc:
                problems.append(f"{t.file}: {exc}")
                continue
            self.doc.edit_entry(e, lambda en, i=i, new=new: setattr(en.tokens[i], "file", new),
                                "Rename sound file")
            done += 1
        msg = f"Renamed {done} recording(s)."
        if problems:
            msg += "\n\nNot renamed:\n" + "\n".join(problems[:30])
        QMessageBox.information(self, "Sound file names", msg)

    def check_duplicates(self):
        dups = self.doc.db.duplicate_filenames()
        if not dups:
            QMessageBox.information(self, "Duplicate file names", "No two tokens share a file name.")
            return
        db = self.doc.db
        lines = []
        for name, items in list(dups.items())[:40]:
            refs = ", ".join(f"{e.ref} ({' + '.join(mx.chips(db, t.tags, db.word_class(e) or None)) or 'citation'})"
                             for e, t in items)
            lines.append(f"{name}: {refs}")
        QMessageBox.warning(self, "Duplicate file names",
                            "These tokens would get the same file name:\n\n" + "\n".join(lines))

    def open_sound_folder(self):
        folder = storage.sound_folder(self.doc.db)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def about(self):
        QMessageBox.about(self, "About Lemmatrix",
                          f"<b>Lemmatrix</b> {__version__}<br>A phonology fieldwork database of lemmas "
                          "and their tokens.<br><br>Prototype (Stage 1).")

    # =============================================================== files
    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        r = QMessageBox.question(self, "Lemmatrix", "Save changes first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_file(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getSaveFileName(self, "New database", str(Path.home() / "Documents"),
                                              "Lemmatrix database (*.xml)")
        if not path:
            return
        db = new_database()
        db.path = path
        self.load_database(db)
        self.edit_metadata()
        self.save()

    def open_file(self, path: str | None = None):
        if not self._confirm_discard():
            return
        if not path:
            start = str(Path(self.doc.db.path).parent) if self.doc.db.path else str(Path.home())
            path, _ = QFileDialog.getOpenFileName(self, "Open database", start,
                                                  "Lemmatrix database (*.xml);;All files (*)")
        if not path:
            return
        try:
            db = storage.load(path)
        except (storage.FormatError, OSError) as exc:
            QMessageBox.warning(self, "Open", f"Couldn't open {Path(path).name}:\n{exc}")
            return
        self.prefs.last_file = path
        self.load_database(db)

    def open_sample(self):
        target = Path.home() / "Documents" / "Lemmatrix Sample"
        if not SAMPLE.exists():
            QMessageBox.warning(self, "Sample", "The sample database isn't in this copy of Lemmatrix.")
            return
        dst = target / "Sample.xml"
        if dst.exists() and QMessageBox.question(
                self, "Sample", f"{dst} already exists. Replace it with a fresh copy?") != QMessageBox.Yes:
            self.open_file(str(dst))
            return
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SAMPLE, dst)
        sounds = SAMPLE.parent / "Soundfiles"
        if sounds.exists():
            if (target / "Soundfiles").exists():
                shutil.rmtree(target / "Soundfiles", ignore_errors=True)
            shutil.copytree(sounds, target / "Soundfiles")
        self.open_file(str(dst))

    def save(self) -> bool:
        if not self.doc.db.path:
            return self.save_as()
        try:
            self.doc.save()
        except OSError as exc:
            QMessageBox.warning(self, "Save", f"Couldn't save: {exc}")
            return False
        self.prefs.last_file = self.doc.db.path
        self._fill_session()
        self.statusBar().showMessage("Saved. The previous version is in the Backups folder.", 4000)
        return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save database as",
                                              self.doc.db.path or str(Path.home() / "Documents"),
                                              "Lemmatrix database (*.xml)")
        if not path:
            return False
        self.doc.db.path = path
        self._update_title()
        return self.save()

    def _apply_autosave(self):
        m = self.prefs.autosave_minutes
        if m > 0:
            self.autosave.start(m * 60_000)
        else:
            self.autosave.stop()

    def _autosave(self):
        if self.doc.dirty and self.doc.db.path:
            self.save()

    def closeEvent(self, event):
        if self._confirm_discard():
            self.player.stop()
            event.accept()
        else:
            event.ignore()
