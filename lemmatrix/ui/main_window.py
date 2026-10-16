"""The main window: lemma list on the left, matrix view on the right."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDate, QFile, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QSplitter, QStyle, QTabBar,
                               QToolButton, QVBoxLayout, QWidget)

from .. import __version__, audio, matrix as mx, storage
from ..defaults import new_database
from ..model import Database
from .dialogs import (DisplaySetupDialog, EntryDialog, MetadataDialog, PreferencesDialog,
                      TagStructureDialog, TokenFilterDialog)
from .document import Document
from .lemma_list import LemmaList
from .matrix_view import (ALL_DATA, ENTRY_TAG, MODE_NAMES, TAG_TAG, MatrixStack, ViewState,
                          find_group, group_path)
from .prefs import Prefs
from .token_dialog import Slot, TokenDialog

SAMPLE = Path(__file__).resolve().parent.parent.parent / "samples" / "Sample.xml"


def _panel(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setFrameShape(QFrame.StyledPanel)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(8, 6, 8, 6)
    if title:
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; font-size: 15px;")
        lay.addWidget(t)
    return f, lay


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.prefs = Prefs()
        self.player = audio.Player()
        self.doc = Document(db or new_database())
        self.doc.setParent(self)
        self.state = ViewState()
        self.tfilter = mx.TokenFilter()
        self.layout_: mx.Layout | None = None
        self.resize(1500, 900)
        self._build()
        self._build_menus()
        self._connect_doc()
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self._autosave)
        self._apply_autosave()
        self.load_database(self.doc.db)

    # ================================================================ layout
    def _build(self):
        split = QSplitter(Qt.Horizontal)
        self.setCentralWidget(split)

        # ---- left: lemma list ------------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        self.lemmas = LemmaList(self.doc.db)
        ll.addWidget(self.lemmas, 1)
        box, bl = _panel()
        row = QHBoxLayout()
        st = self.style()
        for icon, tip, fn in ((QStyle.SP_FileDialogNewFolder, "Add entry", self.add_entry),
                              (QStyle.SP_TrashIcon, "Delete entry", self.delete_entry),
                              (QStyle.SP_FileDialogDetailedView, "Edit entry", self.edit_entry)):
            b = QToolButton()
            b.setIcon(st.standardIcon(icon))
            b.setText(tip.split()[0])
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.lemma_count = QLabel()
        self.lemma_count.setStyleSheet("color: #666;")
        row.addWidget(self.lemma_count)
        bl.addLayout(row)
        self.lemma_search = QLineEdit()
        self.lemma_search.setPlaceholderText("search lemmas")
        self.lemma_search.setClearButtonEnabled(True)
        bl.addWidget(self.lemma_search)
        cv = QHBoxLayout()
        cvl = QLabel("Filter CV shape")
        cvl.setStyleSheet("background: #bbb; padding: 3px 6px; font-weight: 600;")
        cv.addWidget(cvl)
        self.lemma_cv = QLineEdit()
        self.lemma_cv.setPlaceholderText("(C)V(V)C(.CVC)")
        self.lemma_cv.setEnabled(False)
        self.lemma_cv.setToolTip("Matches the Lemma field. Needs the analysis engine (Stage 2).")
        cv.addWidget(self.lemma_cv)
        bl.addLayout(cv)
        clear = QPushButton("Clear lemma filters")
        clear.clicked.connect(self._clear_lemma_filters)
        bl.addWidget(clear)
        ll.addWidget(box)
        split.addWidget(left)

        # ---- right: matrix view ----------------------------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.matrix_title = QLabel()
        self.matrix_title.setStyleSheet("color: #444;")
        top.addWidget(self.matrix_title)
        top.addStretch(1)
        self.tabs = QTabBar()
        for m in (ALL_DATA, TAG_TAG, ENTRY_TAG):
            self.tabs.addTab(MODE_NAMES[m])
        self.tabs.setExpanding(False)
        self.tabs.setStyleSheet("QTabBar::tab { padding: 6px 14px; } "
                                "QTabBar::tab:selected { background: #5b8fd6; color: white; }")
        top.addWidget(self.tabs)
        rl.addLayout(top)
        self.matrix = MatrixStack(self.doc.db, self.state)
        rl.addWidget(self.matrix, 1)

        bottom = QHBoxLayout()
        tools, tl = _panel()
        g = QGridLayout()
        tl.addLayout(g)
        self.add_token_btn = QPushButton("Add new token")
        self.setup_btn = QPushButton("Set up token display")
        self.filter_btn = QPushButton("Filter tokens…")
        self.play_cell_btn = QPushButton("▶ Play cell")
        self.matching = QComboBox()
        self.matching.addItem("Exactly", mx.EXACTLY)
        self.matching.addItem("Includes", mx.INCLUDES)
        self.matching.setToolTip("Exactly: only tokens with exactly the cell's tags.\n"
                                 "Includes: also tokens with extra tags, as labelled sub-rows.")
        self.token_search = QLineEdit()
        self.token_search.setPlaceholderText("search tokens")
        self.token_search.setClearButtonEnabled(True)
        self.token_cv = QLineEdit()
        self.token_cv.setPlaceholderText("CV shape (Phonetic) — Stage 2")
        self.token_cv.setEnabled(False)
        self.undo_action = self.doc.undo.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.doc.undo.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.addAction(self.undo_action)
        self.addAction(self.redo_action)
        self.undo_btn = QToolButton()
        self.undo_btn.setText("↶ Undo")
        self.undo_btn.clicked.connect(self.doc.undo.undo)
        self.doc.undo.canUndoChanged.connect(self.undo_btn.setEnabled)
        self.doc.undo.undoTextChanged.connect(self.undo_btn.setToolTip)
        self.undo_btn.setEnabled(False)
        self.redo_btn = QToolButton()
        self.redo_btn.setText("↷ Redo")
        self.redo_btn.clicked.connect(self.doc.undo.redo)
        self.doc.undo.canRedoChanged.connect(self.redo_btn.setEnabled)
        self.doc.undo.redoTextChanged.connect(self.redo_btn.setToolTip)
        self.redo_btn.setEnabled(False)
        self.views = QComboBox()
        self.views.setMinimumWidth(150)
        self.views.setToolTip("Saved views")
        self.save_view_btn = QPushButton("Save view…")
        g.addWidget(self.add_token_btn, 0, 0)
        g.addWidget(self.setup_btn, 0, 1)
        g.addWidget(self.filter_btn, 0, 2)
        g.addWidget(self.play_cell_btn, 0, 3)
        g.addWidget(self.undo_btn, 0, 4)
        g.addWidget(self.redo_btn, 0, 5)
        g.addWidget(QLabel("Matching"), 1, 0)
        g.addWidget(self.matching, 1, 1)
        g.addWidget(self.token_search, 1, 2)
        g.addWidget(self.token_cv, 1, 3, 1, 3)
        g.addWidget(QLabel("View"), 2, 0)
        g.addWidget(self.views, 2, 1)
        g.addWidget(self.save_view_btn, 2, 2)
        self.filter_note = QLabel()
        self.filter_note.setStyleSheet("color: #1f4fd1;")
        g.addWidget(self.filter_note, 2, 3, 1, 3)
        bottom.addWidget(tools, 1)

        sess, sl = _panel("Current Session")
        self.sess_file = QLabel()
        self.sess_file.setStyleSheet("font-style: italic;")
        self.sess_codes = QLabel()
        self.sess_codes.setStyleSheet("font-weight: 600;")
        self.sess_codes.setToolTip("Language and variety codes, set in Settings → Metadata")
        self.sess_speaker = QComboBox()
        self.sess_speaker.setToolTip("Speaker for new tokens and recordings (may be empty)")
        self.sess_date = QDateEdit(QDate.currentDate())
        self.sess_date.setDisplayFormat("yyyy-MM-dd")
        self.sess_date.setCalendarPopup(True)
        self.sess_date.setToolTip("Collection date for new tokens; resets to today each time "
                                  "Lemmatrix opens")
        self.sess_nodate = QPushButton("No date")
        self.sess_nodate.setCheckable(True)
        self.sess_nodate.setToolTip("Leave the collection date empty on new tokens")
        for w in (self.sess_file, self.sess_codes, self.sess_speaker):
            sl.addWidget(w)
        dr = QHBoxLayout()
        dr.addWidget(self.sess_date, 1)
        dr.addWidget(self.sess_nodate)
        sl.addLayout(dr)
        sess.setMaximumWidth(260)
        bottom.addWidget(sess)
        rl.addLayout(bottom)
        split.addWidget(right)
        split.setSizes([480, 1020])

        # ---- signals ---------------------------------------------------
        # Refreshes are coalesced: many filter signals in a row give one redraw,
        # and typing in a search box waits for a short pause.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_matrix)
        self._lemma_search_timer = QTimer(self)
        self._lemma_search_timer.setSingleShot(True)
        self._lemma_search_timer.setInterval(250)
        self._lemma_search_timer.timeout.connect(
            lambda: self.lemmas.proxy.set_text(self.lemma_search.text()))
        self._token_search_timer = QTimer(self)
        self._token_search_timer.setSingleShot(True)
        self._token_search_timer.setInterval(250)
        self._token_search_timer.timeout.connect(lambda: self._token_search(self.token_search.text()))
        self.lemmas.filtersChanged.connect(self.schedule_refresh)
        self.lemmas.currentEntryChanged.connect(self._entry_selected)
        self.lemmas.entryActivated.connect(lambda e: self.edit_entry())
        self.lemma_search.textChanged.connect(lambda _: self._lemma_search_timer.start())
        self.tabs.currentChanged.connect(self._tab_changed)
        self.add_token_btn.clicked.connect(self.add_token)
        self.setup_btn.clicked.connect(self.setup_display)
        self.filter_btn.clicked.connect(self.filter_tokens)
        self.play_cell_btn.clicked.connect(self.play_cell)
        self.matching.currentIndexChanged.connect(self._matching_changed)
        self.token_search.textChanged.connect(lambda _: self._token_search_timer.start())
        self.views.activated.connect(self._view_chosen)
        self.save_view_btn.clicked.connect(self.save_view)
        self.sess_speaker.currentTextChanged.connect(lambda t: setattr(self.prefs, "speaker", t))
        self.sess_nodate.toggled.connect(self.sess_date.setDisabled)
        p = self.matrix.paradigm
        p.cellActivated.connect(self._cell_activated)
        p.cellClicked.connect(self._cell_clicked)
        p.switchRequested.connect(self.switch_axes)
        self.matrix.all_view.doubleClicked.connect(self._row_activated)
        self.matrix.all_view.clicked.connect(self._row_clicked)
        self.matrix.all_model.edited.connect(self._cell_edited)

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
        e.addAction(self.undo_action)
        e.addAction(self.redo_action)

        s = mb.addMenu("&Settings")
        self._act(s, "&Metadata (language, variety, speakers)…", self.edit_metadata)
        self._act(s, "&Tag structure…", self.edit_tags)
        self._act(s, "&Settings…", self.edit_settings, QKeySequence.Preferences)

        t = mb.addMenu("&Tools")
        self._act(t, "Update all sound file names", self.update_all_names)
        self._act(t, "Check for duplicate file names", self.check_duplicates)
        self._act(t, "Open the sound folder", self.open_sound_folder)

        v = mb.addMenu("&View")
        self.column_menu = v.addMenu("Lemma list columns")
        self._act(v, "Swap rows and columns", self.switch_axes, "Ctrl+T")
        self._act(v, "Set up token display…", self.setup_display)

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

    def _connect_doc(self):
        self.doc.changed.connect(self._doc_changed)
        self.doc.dirtyChanged.connect(lambda d: self._update_title())

    # ============================================================ database
    def load_database(self, db: Database):
        self.player.stop()
        self.doc.db = db
        self.doc.undo.clear()
        self.doc.undo.setClean()
        self.doc._settings_dirty = False
        self.lemmas.set_database(db)
        self.matrix.set_database(db)
        self._all_sized = False
        self.state = ViewState()
        self.matrix.paradigm.state = self.state
        self.tfilter = mx.TokenFilter()
        self.lemma_search.clear()
        self.token_search.clear()
        self._fill_session()
        self._fill_views()
        self._fill_column_menu()
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(ENTRY_TAG)
        self.tabs.blockSignals(False)
        self._set_mode(ENTRY_TAG)
        if db.entries:
            self.lemmas.selectRow(0)
        self._update_title()
        self.refresh_matrix()

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

    def _fill_column_menu(self):
        self.column_menu.clear()
        m = self.lemmas.model_
        visible = [c[0] for c in m.columns]
        for key, title, _ in m.all_columns:
            a = self.column_menu.addAction(title)
            a.setCheckable(True)
            a.setChecked(key in visible)
            a.toggled.connect(self._columns_changed)

    def _columns_changed(self):
        m = self.lemmas.model_
        keys = [m.all_columns[i][0] for i, a in enumerate(self.column_menu.actions()) if a.isChecked()]
        self.lemmas.set_visible_columns(keys or ["ref"])
        self.refresh_matrix()

    def _clear_lemma_filters(self):
        self.lemma_search.clear()
        self.lemmas.clear_filters()

    def session_speaker(self) -> str:
        return self.sess_speaker.currentText()

    def session_date(self) -> str:
        return "" if self.sess_nodate.isChecked() else self.sess_date.date().toString("yyyy-MM-dd")

    def _update_title(self):
        db = self.doc.db
        name = Path(db.path).name if db.path else "Untitled"
        self.setWindowTitle(f"{'*' if self.doc.dirty else ''}{name} — Lemmatrix")

    def _doc_changed(self):
        self.lemmas.refresh()
        self.schedule_refresh()
        self._update_title()

    def schedule_refresh(self, delay: int = 0):
        self._refresh_timer.start(delay)

    # ============================================================== matrix
    def _tab_changed(self, i):
        self.state.mode = i
        self._set_mode(i)
        self.refresh_matrix()

    def _set_mode(self, mode):
        self.state.mode = mode
        self.matrix.setCurrentIndex(0 if mode == ALL_DATA else 1)
        self.matching.setEnabled(mode != ALL_DATA)
        self.setup_btn.setEnabled(mode != ALL_DATA)

    def _matching_changed(self):
        self.state.matching = self.matching.currentData()
        self.refresh_matrix()

    def _token_search(self, text):
        self.tfilter.text = text.strip()
        self.refresh_matrix()

    def _entry_selected(self, entry):
        if self.state.mode == TAG_TAG:
            self.refresh_matrix()

    def _tag_tag_groups(self, entry):
        db = self.doc.db
        wc = db.word_class(entry)
        rg = find_group(db, self.state.row_group, wc) if self.state.row_group else None
        cg = find_group(db, self.state.col_group, wc) if self.state.col_group else None
        if rg is None or cg is None or rg is cg:
            # Default: the first two groups this entry's tokens actually use.
            used = []
            groups = db.settings.tags.leaf_groups_for(wc)
            for path, g in groups:
                names = {t.name for t in g.tags if not t.default}
                if any(names & set(t.tags) for t in entry.tokens):
                    used.append(g)
            for path, g in groups:
                if g not in used:
                    used.append(g)
            if rg is None:
                rg = used[0] if used else None
            if cg is None or cg is rg:
                cg = next((g for g in used if g is not rg), None)
        return rg, cg

    def refresh_matrix(self):
        db = self.doc.db
        visible = self.lemmas.visible_entries()
        self.lemma_count.setText(f"{len(visible)} of {len(db.entries)}")
        self.matching.blockSignals(True)
        self.matching.setCurrentIndex(0 if self.state.matching == mx.EXACTLY else 1)
        self.matching.blockSignals(False)
        notes = []
        if any(self.tfilter.tags.values()) or self.tfilter.citation_only or self.tfilter.speakers \
                or self.tfilter.dates:
            notes.append("Token filters on")
        self.filter_note.setText(" · ".join(notes))
        if self.state.mode == ALL_DATA:
            vis = set(map(id, visible))
            rows = [(e, i) for e in db.entries if id(e) in vis
                    for i, t in enumerate(e.tokens) if self.tfilter.accepts(t)]
            self.matrix.all_model.set_rows(rows)
            if not getattr(self, "_all_sized", False) and rows:
                self.matrix.all_view.resizeColumnsToContents()   # first time only
                self._all_sized = True
            self.matrix_title.setText(f"{len(rows)} tokens")
            self.layout_ = None
            return
        if self.state.mode == ENTRY_TAG:
            lay = mx.entry_tag_layout(db, visible, self.state.headers, self.state.matching,
                                      self.tfilter, self.state.entry_label)
            self.matrix_title.setText(f"{len(visible)} entries")
        else:
            entry = self.lemmas.current_entry()
            if entry is not None and entry not in visible:
                entry = None
            rg, cg = self._tag_tag_groups(entry) if entry else (None, None)
            lay = mx.tag_tag_layout(db, entry, rg, cg, self.state.matching, self.tfilter)
            if entry is not None:
                self.matrix_title.setText(f"{entry.ref}  {db.lemma(entry)}  “{db.gloss(entry)}”"
                                          + (f"   —   {rg.name} × {cg.name}" if rg and cg else ""))
            else:
                self.matrix_title.setText("")
        if self.state.switched:
            lay = lay.transposed()
        self.layout_ = lay
        self.matrix.paradigm.state = self.state
        self.matrix.paradigm.set_layout(lay)
        if lay.message and not lay.rows:
            self.matrix_title.setText(lay.message)

    def switch_axes(self):
        if self.state.mode == ALL_DATA:
            return
        self.state.switched = not self.state.switched
        self.refresh_matrix()

    def setup_display(self):
        if self.state.mode == ALL_DATA:
            return
        dlg = DisplaySetupDialog(self, self.doc.db, self.state, self.lemmas.visible_entries(),
                                 self.lemmas.current_entry())
        if dlg.exec():
            dlg.apply()
            self.refresh_matrix()

    def filter_tokens(self):
        dlg = TokenFilterDialog(self, self.doc.db, self.tfilter)
        if dlg.exec():
            dlg.apply()
            self.refresh_matrix()

    # ---- saved views ---------------------------------------------------
    def _fill_views(self):
        self.views.blockSignals(True)
        self.views.clear()
        self.views.addItem("(current layout)")
        for v in self.doc.db.settings.views:
            self.views.addItem(v.get("name", "?"))
        self.views.blockSignals(False)

    def _view_chosen(self, i):
        if i <= 0:
            return
        d = self.doc.db.settings.views[i - 1]
        self.state = ViewState.from_dict(d)
        self.matrix.paradigm.state = self.state
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(self.state.mode)
        self.tabs.blockSignals(False)
        self._set_mode(self.state.mode)
        self.refresh_matrix()

    def save_view(self):
        name, ok = QInputDialog.getText(self, "Save view", "Name for this layout:",
                                        text=self.views.currentText() if self.views.currentIndex() > 0 else "")
        if not ok or not name.strip():
            return
        views = self.doc.db.settings.views
        d = self.state.to_dict(name.strip())
        for i, v in enumerate(views):
            if v.get("name") == d["name"]:
                views[i] = d
                break
        else:
            views.append(d)
        self.doc.settings_changed()
        self._fill_views()
        self.views.setCurrentText(d["name"])

    # ================================================ tokens and playback
    def _slots(self) -> list[Slot]:
        """Every place Back/Next visits, in reading order."""
        slots = []
        if self.state.mode == ALL_DATA:
            for e, i in self.matrix.all_model.rows:
                slots.append(Slot(e, i))
            return slots
        lay = self.layout_
        if lay is None:
            return slots
        for r, c in lay.reading_order():
            hits = lay.tokens(r, c)
            if hits:
                for e, t in hits:
                    slots.append(Slot(e, e.tokens.index(t)))
            else:
                entry, tags = lay.target(r, c)
                if entry is not None:
                    slots.append(Slot(entry, None, tuple(tags), defaults=True))
        return slots

    def _open_dialog(self, slots, index):
        if not slots:
            return
        dlg = TokenDialog(self, slots, index)
        dlg.exec()
        self.refresh_matrix()

    def _cell_activated(self, r, c, n):
        lay = self.layout_
        if lay is None:
            return
        slots = self._slots()
        hits = lay.tokens(r, c)
        if hits and n >= 0:
            e, t = hits[n]
            idx = next((i for i, s in enumerate(slots) if s.entry is e and s.index == e.tokens.index(t)), 0)
        else:
            entry, tags = lay.target(r, c)
            if entry is None:
                return
            idx = next((i for i, s in enumerate(slots) if s.entry is entry and s.index is None
                        and set(s.tags) == set(tags)), None)
            if idx is None:
                slots.append(Slot(entry, None, tuple(tags), defaults=True))
                idx = len(slots) - 1
            slots[idx].explicit = True
        self._open_dialog(slots, idx)

    def _row_activated(self, index):
        key = self.matrix.all_model.columns[index.column()][0]
        if key.startswith("f:"):
            return                     # editing in place
        self._open_dialog(self._slots(), index.row())

    def _row_clicked(self, index):
        if self.doc.db.settings.play_cell_on_click:
            self.play_cell()

    def _cell_clicked(self, r, c):
        if self.doc.db.settings.play_cell_on_click:
            self.play_cell()

    def _cell_edited(self, entry, i, name, text):
        s = self.doc.db.settings
        f = s.token_field(name)

        def change(e):
            e.tokens[i].set(name, text.strip(), s.primary_gloss if f.multilingual else None, f.multilingual)
        self.doc.edit_entry(entry, change, f"Edit {name}")

    def add_token(self):
        entry = None
        if self.state.mode == ALL_DATA:
            idx = self.matrix.all_view.currentIndex()
            if idx.isValid():
                entry = self.matrix.all_model.rows[idx.row()][0]
        elif self.layout_ is not None:
            idx = self.matrix.paradigm.currentIndex()
            if idx.isValid():
                entry = self.layout_.target(idx.row(), idx.column())[0]
        entry = entry or self.lemmas.current_entry()
        if entry is None:
            QMessageBox.information(self, "Add new token", "Select an entry first.")
            return
        self._open_dialog([Slot(entry, None, (), explicit=True, defaults=True)], 0)

    def selected_tokens(self):
        if self.state.mode == ALL_DATA:
            idx = self.matrix.all_view.currentIndex()
            return [self.matrix.all_model.token(idx.row())] if idx.isValid() else []
        idx = self.matrix.paradigm.currentIndex()
        if not idx.isValid() or self.layout_ is None:
            return []
        return self.layout_.tokens(idx.row(), idx.column())

    def play_cell(self):
        folder = storage.sound_folder(self.doc.db)
        paths = [folder / t.file for e, t in self.selected_tokens() if t.file]
        if not paths:
            self.statusBar().showMessage("Nothing recorded in this cell.", 3000)
            return
        try:
            if not self.player.play(paths):
                self.statusBar().showMessage("The recording isn't in the sound folder.", 4000)
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play", str(exc))

    # ============================================================= entries
    def add_entry(self):
        dlg = EntryDialog(self, self.doc.db)
        if dlg.exec():
            e = dlg.new_entry(self.session_speaker(), self.session_date())
            self.doc.add_entry(e)
            self.lemmas.select_entry(e)

    def edit_entry(self):
        e = self.lemmas.current_entry()
        if e is None:
            return
        dlg = EntryDialog(self, self.doc.db, e)
        if dlg.exec():
            self.doc.edit_entry(e, dlg.apply, f"Edit {e.ref}")

    def delete_entry(self):
        e = self.lemmas.current_entry()
        if e is None:
            return
        n = len(e.tokens)
        if QMessageBox.question(self, "Delete entry",
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
            self._maybe_update_names()

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
            self.doc.settings_changed()
            self._maybe_update_names()

    def edit_settings(self):
        dlg = PreferencesDialog(self, self.doc.db, self.prefs)
        if dlg.exec():
            names_changed = dlg.apply()
            self._apply_autosave()
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
        lines = []
        for name, items in list(dups.items())[:40]:
            refs = ", ".join(f"{e.ref} ({self.doc.db.settings.tags.display(self.doc.db.word_class(e), t.tags)}"
                             f"{', ' + t.speaker if t.speaker else ''})" for e, t in items)
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
            shutil.copytree(sounds, target / "Soundfiles", dirs_exist_ok=True)
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
