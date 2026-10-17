"""The main window: lemma list on the left, the Matrix on the right."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDate, QDir, QFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGroupBox,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__, audio, filters as fl, lock as lockmod, matrix as mx, storage
from . import theme
from ..defaults import new_database
from .. import notebook as nbmod
from ..model import Database, Entry, ListItem, Person, forbidden_in, today
from . import chiprow as chips
from .dialogs import EntryDialog, MetadataDialog, PreferencesDialog, TagStructureDialog
from .document import Document
from .fields_dialog import FieldsDialog
from .filter_dialogs import ConfigureColumnsDialog
from .icons import icon
from .matrix_dialogs import ConfigureCellDialog, ConfigureMatrixDialog, ask_matrix_name
from .matrix_view import MatrixView
from .prefs import Prefs
from .table import ChipsDelegate, Column, DrawingDelegate, FilterTable, ListEditDelegate
from .token_dialog import Slot, TokenDialog
from .widgets import ipa_font

def pitchmod_parse(text):
    from .. import pitch
    return pitch.parse(text or "")


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
    b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
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
        self.notebook_dialog = None               # the notebook window, once opened
        self.sound_files: set[str] = set()       # names in the sound folder, refreshed with the views
        self.cloud_files: set[str] = set()       # those of them that are online-only (OneDrive)
        self.resize(1500, 920)
        theme.from_prefs(self.prefs)
        self._build()
        self._build_menus()
        self._restyle()
        self._restore_window()
        self.doc.work_date = self.work_date
        self.doc.changed.connect(self._doc_changed)
        self.doc.dirtyChanged.connect(self._dirty_changed)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self._autosave)
        self._locked_path = ""                    # the database this window has marked as open
        self.heartbeat = QTimer(self)             # keeps the "last active" time in the marker fresh
        self.heartbeat.setInterval(5 * 60_000)
        self.heartbeat.timeout.connect(lambda: self._locked_path and lockmod.claim(self._locked_path))
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

    def _heading(self, text: str) -> QLabel:
        """A pane's title ("Lemma", "Matrix"): medium-large, in the theme colour (set in _restyle)."""
        lbl = QLabel(text)
        f = QFont(lbl.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.45)
        lbl.setFont(f)
        lbl.setContentsMargins(4, 2, 0, 0)
        return lbl

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
        main = self.main_split = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main)

        # ---- left: lemma list + its options -------------------------------
        left = self.left_split = QSplitter(Qt.Vertical)
        self.lemmas = FilterTable()
        lemma_box = QWidget()
        lb = QVBoxLayout(lemma_box)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setSpacing(2)
        self.lemma_title = self._heading("Lemma")
        lb.addWidget(self.lemma_title)
        lb.addWidget(self.lemmas, 1)
        left.addWidget(lemma_box)
        bar, bl = self._bar()
        self.lemma_count = QLabel()
        self._row(bl, tool("Add", "add", self.add_entry, "Add a lemma"),
                  tool("Delete", "delete", self.delete_entry, "Delete the selected lemma (Delete)"),
                  tool("Edit", "edit", self.edit_entry, "Edit the selected lemma (Enter)"),
                  tool("Configure columns", "gear", self.configure_lemma_columns),
                  tool("Clear all filters", "broom", self._clear_lemma_filters))
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
        right = self.right_split = QSplitter(Qt.Vertical)
        box = self.matrix_box = QWidget()
        bxl = QVBoxLayout(box)
        bxl.setContentsMargins(0, 0, 0, 0)
        bxl.setSpacing(2)
        self.matrix_title = self._heading("Matrix")
        bxl.addWidget(self.matrix_title)
        top = QHBoxLayout()
        self.count_line = QLabel()
        top.addWidget(self.count_line)
        top.addStretch(1)
        self.tabs = QTabBar()
        for name in ("All data", "Lemma/Tag", "Tag/Tag"):
            self.tabs.addTab(name)
        self.tabs.setExpanding(False)
        top.addWidget(self.tabs)
        bxl.addLayout(top)
        self.views = QStackedWidget()
        self.all_table = FilterTable()
        self.lt_view = MatrixView(self.doc.db)
        self.tt_view = MatrixView(self.doc.db)
        for w in (self.all_table, self.lt_view, self.tt_view):
            self.views.addWidget(w)
        bxl.addWidget(self.views, 1)
        # options for every tab
        self.autoplay = QCheckBox("Auto-play token soundfile")
        self.autoplay.setToolTip("Play a token's recording when you click it (in any tab) and when "
                                 "the token dialogue opens on it")
        self.autoplay.setChecked(self.prefs.autoplay_tokens)
        self.autoplay.toggled.connect(lambda on: setattr(self.prefs, "autoplay_tokens", bool(on)))
        self.only_data = QCheckBox("Show only lemmas with token data")
        self.only_data.setToolTip("All data: leave out lemmas whose tokens are all empty. Lemma/Tag: "
                                  "leave out lemmas with nothing in any of the matrix's columns. "
                                  "Tag/Tag: show nothing for a lemma without token data.")
        self.only_data.setChecked(self.prefs.only_lemmas_with_data)
        self.only_data.toggled.connect(self._only_data_toggled)
        opts = QHBoxLayout()
        opts.setContentsMargins(4, 0, 0, 0)
        opts.addWidget(self.autoplay)
        opts.addSpacing(16)
        opts.addWidget(self.only_data)
        opts.addStretch(1)
        bxl.addLayout(opts)
        normal = QFont(box.font())
        normal.setBold(False)              # set explicitly, or it would be inherited bold
        for w in (self.count_line, self.tabs, self.views, self.autoplay, self.only_data):
            w.setFont(normal)
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
        self.lemmas.ctrl_click_pins = True
        self.lemmas.filtersChanged.connect(lambda: self.schedule_refresh())
        self.lemmas.rowActivated.connect(lambda e: self.edit_entry())
        self.lemmas.deleteRequested.connect(self.delete_entry)
        self.lemmas.contextRequested.connect(self._lemma_menu)
        self.lemmas.selectionModel().currentRowChanged.connect(lambda *a: self._lemma_selected())
        self.all_table.filtersChanged.connect(self._update_counts)
        self.all_table.rowActivated.connect(lambda r: self.edit_token())
        self.all_table.deleteRequested.connect(self.delete_token)
        self.all_table.contextRequested.connect(self._all_menu)
        self.all_table.space_plays = True
        self.all_table.playRequested.connect(self.play_selected)
        self.all_table.clicked.connect(lambda *_: self.autoplay.isChecked() and self.play_selected())
        self.all_table.model_.edited.connect(self._cell_edited)
        self.lemmas.model_.edited.connect(self._lemma_edited)
        self.tabs.currentChanged.connect(self._tab_changed)
        for view, tab in ((self.lt_view, LEMMA_TAG), (self.tt_view, TAG_TAG)):
            view.tokenClicked.connect(lambda r, c, n, tab=tab: self._token_clicked(tab, r, c, n))
            view.cellActivated.connect(lambda r, c, n, tab=tab: self._cell_activated(tab, r, c, n))
            view.contextRequested.connect(lambda r, c, n, pos, tab=tab: self._matrix_menu(tab, pos))
            view.deleteRequested.connect(self.delete_token)
            view.switchRequested.connect(lambda tab=tab: self.switch_axes(tab))
            view.switch.setContextMenuPolicy(Qt.CustomContextMenu)   # to try the two arrow styles
            view.switch.customContextMenuRequested.connect(
                lambda pos, v=view: self._switch_style_menu(v.switch.mapToGlobal(pos)))
            view.playRequested.connect(self.play_selected)

    def _all_data_bar(self) -> QWidget:
        bar, bl = self._bar()
        self.all_count = QLabel()
        self._row(bl, tool("Add", "add", self.add_token, "Add a token"),
                  tool("Delete", "delete", self.delete_token, "Delete the selected token (Delete)"),
                  tool("Edit", "edit", self.edit_token, "Edit the selected token (Enter)"),
                  tool("Play", "play", self.play_selected, "Play the selected token (Ctrl+Space)"),
                  tool("Configure columns", "gear", self.configure_all_columns),
                  tool("Clear all filters", "broom", self._clear_all_filters))
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
                  tool("Play", "play", self.play_selected, "Play the selected token (Ctrl+Space)"),
                  tool("Configure cell", "gear", lambda tab=tab: self.configure_cell(tab),
                       "Choose what each cell shows"),
                  tool("Configure matrix", "gear", lambda tab=tab: self.configure_matrix(tab),
                       "Choose the rows and columns"),
                  tool("Clear matrix", "broom", lambda tab=tab: self.clear_matrix(tab),
                       "Empty the view: no rows or columns"))
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
        self._row(bl, QLabel("Matrix class"), d["cls"])
        self._row(bl, QLabel("Matrix"), d["saved"],
                  tool("Save matrix", None, lambda tab=tab: self.save_matrix(tab),
                       "Save this matrix under a name"),
                  tool("Rename matrix", None, lambda tab=tab: self.rename_matrix(tab),
                       "Rename the chosen saved matrix"),
                  tool("Delete matrix", None, lambda tab=tab: self.delete_saved_matrix(tab),
                       "Delete the chosen saved matrix"))
        bl.addStretch(1)
        return d

    def _session_panel(self) -> QWidget:
        panel, sl = self._bar()

        def styled(text="", bold=False, italic=False, scale=1.0):
            lbl = QLabel(text)
            fnt = QFont(lbl.font())
            fnt.setBold(bold)
            fnt.setItalic(italic)
            fnt.setPointSizeF(fnt.pointSizeF() * scale)
            lbl.setFont(fnt)
            return lbl

        def big_button(name, tip, fn):
            b = QToolButton()
            b.setIconSize(QSize(34, 34))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda *_: fn())
            b.setProperty("icon_name", name)
            return b
        head = QHBoxLayout()
        head.addWidget(styled("Current Session", bold=True, scale=1.25))
        head.addStretch(1)
        self.notebook_btn = big_button("notebook", "Open notebook", self.open_notebook)
        self.write_btn = big_button("write-notebook", "Write to notebook: the session's day gets these "
                                    "people and places and that day's comments", self.write_notebook)
        head.addWidget(self.write_btn)            # its arrow points at the notebook beside it
        head.addWidget(self.notebook_btn)
        sl.addLayout(head)
        self.sess_file = styled(italic=True)
        self.sess_codes = styled(bold=True)
        self.sess_codes.setToolTip("Language and variety codes, set in Edit → Metadata")
        sl.addWidget(self.sess_file)
        sl.addWidget(self.sess_codes)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        self.sess_rows = {}
        for r, (kind, title) in enumerate(((chips.RESEARCHERS, "Researchers"),
                                           (chips.PARTICIPANTS, "Participants"),
                                           (chips.LOCATIONS, "Locations"))):
            row = chips.ChipRow(kind, lambda: self.doc.db, compact=True, edit_list=self.edit_lists)
            row.changed.connect(self._session_people_changed)
            self.sess_rows[kind] = row
            lbl = QLabel(title)
            grid.addWidget(lbl, r if r < 2 else 3, 0, Qt.AlignTop | Qt.AlignRight)
            grid.addWidget(row, r if r < 2 else 3, 1)
        self.sess_speaker = QComboBox()
        self.sess_speaker.setToolTip("Speaker of new tokens and recordings: the first participant, "
                                     "until another is chosen here or in the token dialogue")
        self.sess_speaker.activated.connect(lambda _: self.set_speaker(self.sess_speaker.currentText()))
        grid.addWidget(QLabel("Speaker"), 2, 0, Qt.AlignRight)
        grid.addWidget(self.sess_speaker, 2, 1)
        grid.setColumnStretch(1, 1)
        sl.addLayout(grid)
        self.sess_date = QDateEdit(QDate.currentDate())
        self.sess_date.setDisplayFormat("yyyy-MM-dd")
        self.sess_date.setCalendarPopup(True)
        self.sess_date.setMaximumDate(QDate.currentDate())
        self.sess_date.setToolTip("The session's date: for new tokens and recordings, for comments, "
                                  "and the notebook's day. Resets to today each time Lemmatrix opens; "
                                  "it can't be a day that hasn't come yet.")
        self.sess_date.dateChanged.connect(lambda *_: self._session_date_changed())
        self.sess_nodate = QPushButton("No date")
        self.sess_nodate.setCheckable(True)
        self.sess_nodate.toggled.connect(self.sess_date.setDisabled)
        self.sess_nodate.toggled.connect(lambda *_: self._session_date_changed())
        dr = QHBoxLayout()
        dr.addWidget(QLabel("Date"))
        dr.addWidget(self.sess_date, 1)
        dr.addWidget(self.sess_nodate)
        sl.addLayout(dr)
        sl.addStretch(1)
        panel.setMaximumWidth(330)
        panel.setMinimumWidth(250)
        return panel

    def _build_menus(self):
        mb = self.menuBar()
        self.save_btn = QToolButton()               # top right, in the theme colour (see _notebook_icons)
        self.save_btn.setText("Save")
        self.save_btn.setToolTip("Save the database (Ctrl+S)")
        self.save_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.save_btn.setIconSize(QSize(18, 18))
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(lambda *_: self.save())
        corner = self._corner = QWidget()      # kept: PySide does not take ownership of it
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 2, 6, 2)
        cl.addWidget(self.save_btn)
        mb.setCornerWidget(corner, Qt.TopRightCorner)
        f = mb.addMenu("&File")
        self._act(f, "&New database…", self.new_file, QKeySequence.New)
        self._act(f, "&Open…", self.open_file, QKeySequence.Open)
        self._act(f, "Open a copy of the sample database", self.open_sample)
        f.addSeparator()
        self._act(f, "&Save", self.save, QKeySequence.Save)
        self._act(f, "Save &as…", self.save_as, QKeySequence.SaveAs)
        f.addSeparator()
        ex = f.addMenu("&Export")
        self._act(ex, "&Filtered database (current tab) as CSV…", lambda: self.export_csv(filtered=True))
        self._act(ex, "&Entire database as CSV…", lambda: self.export_csv(filtered=False))
        f.addSeparator()
        self._act(f, "E&xit", self.close, QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        undo = self.doc.undo.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.doc.undo.createRedoAction(self, "Redo")
        redo.setShortcut(QKeySequence.Redo)
        e.addAction(undo)
        e.addAction(redo)
        e.addSeparator()
        self._act(e, "&Metadata (language, variety, author)…", self.edit_metadata)
        self._act(e, "&Fields…", self.edit_fields)
        self._act(e, "&Lists (people, places, field lists, tags)…", self.edit_lists)
        self._act(e, "&Tag structure…", lambda: self.edit_lists("tags"))
        e.addSeparator()
        self._act(e, "&Settings…", self.edit_settings, QKeySequence.Preferences)
        t = mb.addMenu("&Tools")
        self._act(t, "Update all sound file names", self.update_all_names)
        self._act(t, "Check for duplicate file names", self.check_duplicates)
        self._act(t, "Find missing or unlinked recordings…", self.find_missing_recordings)
        self._act(t, "Open the sound folder", self.open_sound_folder)
        v = mb.addMenu("&View")
        self._act(v, "&Notebook", self.open_notebook, "Ctrl+B")
        self._act(v, "&Questions", self.open_questions)
        v.addSeparator()
        self._act(v, "Swap rows and columns", lambda: self.switch_axes(self.tabs.currentIndex()), "Ctrl+T")
        v.addSeparator()
        # the same keys as in the token dialogue
        self.play_action = self._act(None, "Play the selected token", self.play_selected, "Ctrl+Space")
        self.play_pitch_action = self._act(None, "Play the selected token's pitch", self.play_selected_pitch,
                                           "Ctrl+Shift+Space")
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
        if menu is None:                  # a shortcut only, not in a menu
            self.addAction(a)
        else:
            menu.addAction(a)
        return a

    # ============================================================ columns
    def _lemma_columns(self) -> list[Column]:
        db = self.doc.db
        s = db.settings
        edit = lambda row, text: None           # marks a column as editable in place
        cols = [Column("ref", "Reference", lambda e: e.ref)]
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    cols.append(Column(f"{f.name}:{lang}", f"{f.title} ({lang})" if len(s.gloss_languages) > 1
                                       else f.title, lambda e, n=f.name, l=lang: e.get(n, l), edit=edit))
            else:
                cols.append(Column(f.name, f.title, lambda e, n=f.name: e.get(n), closed=f.closed,
                                   tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                                   ipa=f.role == "lemma", edit=edit))
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
            out = [ListItem(fl.CITATION_ITEM)]
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
            # Value: the recording if it exists on disk, otherwise blank (so Blanks = no recording);
            # shown: the recording, or the name it would get, in grey.
            Column("file", "Sound file", lambda r: r.token.file if r.token.file in self.sound_files else "",
                   display=lambda r: r.token.file or db.expected_filename(r.entry, r.token),
                   color=lambda r: theme.colour("dim") if not r.token.file else
                   (theme.colour("error") if (r.token.file not in self.sound_files or
                                          r.token.file != db.expected_filename(r.entry, r.token)) else None),
                   tooltip=lambda r: ("Not recorded yet" if not r.token.file else
                                      f"{r.token.file} isn't in the sound folder" if r.token.file not in self.sound_files
                                      else f"Recorded as {r.token.file}\nExpected: {db.expected_filename(r.entry, r.token)}"
                                      f"\n{QDir.toNativeSeparators(str(storage.sound_folder(db) / r.token.file))}"
                                      + ("\nOnline only: needs internet to play" if r.token.file in self.cloud_files
                                         else ""))),
        ]
        return cols

    def _group_item(self, g):
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
        self._closed_editors(self.lemmas)
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
        self._closed_editors(self.all_table)
        self._all_sized = False

    def _closed_editors(self, table):
        """Closed fields edited in place get a drop-down of their list."""
        for c in table.model_.columns:
            if c.closed and c.edit and c.tree and not c.multi:
                table.set_delegate(c.key, ListEditDelegate(
                    lambda c=c: [i.name for top in c.tree() for i in top.walk()], table))

    def configure_lemma_columns(self):
        cols = self._lemma_columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.lemmas.visible_keys())
        if dlg.exec():
            self.prefs.set_list("columns/lemma", dlg.chosen())
            self.lemmas.set_columns(cols, dlg.chosen())
            self._closed_editors(self.lemmas)
            self.lemmas.set_rows(self.doc.db.entries)
            self.lemmas.resizeColumnsToContents()

    def configure_all_columns(self):
        cols = self._all_columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.all_table.visible_keys())
        if dlg.exec():
            self.prefs.set_list("columns/alldata", dlg.chosen())
            self._setup_columns()
            self.refresh()

    # ============================================================ database
    def load_database(self, db: Database):
        self.player.stop()
        if self.doc.db is not db:
            self._save_view()
        self._mark_open(db.path)
        self.doc.db = db
        self.doc.undo.clear()
        self.doc.undo.setClean()
        self.doc._settings_dirty = False
        self.doc.renamed.clear()
        self._load_notebook()
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
        self._restore_view()
        self._update_title()
        self._report_missing()
        if self.notebook_dialog is not None:
            self.notebook_dialog.reload()

    def _fill_session(self):
        """The Current Session panel: the file, the codes, and the session's people and places.

        If the notebook has a session for the date, the panel shows its people and places;
        otherwise the ones last used with this database."""
        db = self.doc.db
        md = db.metadata
        self.sess_file.setText(Path(db.path).name if db.path else "(not saved yet)")
        self.sess_codes.setText("  ".join(x for x in (md.language_code, md.variety_code) if x)
                                or "no language code")
        s = self.doc.notebook.session(self.session_date()) if self.session_date() else None
        if s is not None:
            keys = {chips.RESEARCHERS: s.researchers, chips.PARTICIPANTS: s.participants,
                    chips.LOCATIONS: s.locations}
        else:
            last = self.prefs.session_for(db.path) if db.path else {}
            keys = {k: [x for x in last.get(k, []) if isinstance(x, str)] for k in self.sess_rows}
            if not db.path and not keys[chips.PARTICIPANTS] and self.prefs.speaker in db.participant_codes():
                keys[chips.PARTICIPANTS] = [self.prefs.speaker]
        for kind, row in self.sess_rows.items():
            row.set_keys(keys.get(kind, []))
        self._fill_speakers()

    def speaker_choices(self) -> list[str]:
        """Who can be the speaker: the session's participants (all participants if none are picked)."""
        codes = self.sess_rows[chips.PARTICIPANTS].keys
        return list(codes) or self.doc.db.participant_codes()

    def _fill_speakers(self):
        """The speaker list follows the session's participants; the speaker stays if still there,
        otherwise it is the first participant."""
        md = self.doc.db.metadata
        choices = self.speaker_choices()
        current = self.prefs.speaker
        if current and current not in choices:
            current = ""
        if not current and self.sess_rows[chips.PARTICIPANTS].keys:
            current = choices[0]
        self.sess_speaker.blockSignals(True)
        self.sess_speaker.clear()
        self.sess_speaker.addItem("")
        for code in choices:
            self.sess_speaker.addItem(code)
            p = md.participant(code)
            if p and p.name:
                self.sess_speaker.setItemData(self.sess_speaker.count() - 1, p.name, Qt.ToolTipRole)
        self.sess_speaker.setCurrentText(current)
        self.sess_speaker.blockSignals(False)
        self.prefs.speaker = current

    def set_speaker(self, code: str):
        """The speaker for the next tokens and recordings (from here or the token dialogue)."""
        self.prefs.speaker = code
        self.sess_speaker.blockSignals(True)
        if code and self.sess_speaker.findText(code) < 0:
            self.sess_speaker.addItem(code)
        self.sess_speaker.setCurrentText(code)
        self.sess_speaker.blockSignals(False)

    def session_keys(self) -> dict[str, list[str]]:
        return {k: list(row.keys) for k, row in self.sess_rows.items()}

    def _session_people_changed(self):
        if self.doc.db.path:
            self.prefs.set_session_for(self.doc.db.path, self.session_keys())
        self._fill_speakers()

    def _session_date_changed(self):
        s = self.doc.notebook.session(self.session_date()) if self.session_date() else None
        if s is not None:                     # a day with notes: its people and places
            for kind, keys in ((chips.RESEARCHERS, s.researchers), (chips.PARTICIPANTS, s.participants),
                               (chips.LOCATIONS, s.locations)):
                self.sess_rows[kind].set_keys(keys)
            self._fill_speakers()
        self.write_btn.setEnabled(bool(self.session_date()))

    def work_date(self) -> str:
        """The day comments are dated with: the session's date, or today without one."""
        return self.session_date() or today()

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

    # ============================================================= notebook
    def _notebook_icons(self):
        a = theme.accent().name()
        self.notebook_btn.setIcon(icon("notebook", 34, a))
        self.write_btn.setIcon(icon("write-notebook", 34))
        self.save_btn.setIcon(icon("save", 18, a))
        self.save_btn.setStyleSheet(
            f"QToolButton {{ background: {a}; color: {theme.text_on(theme.accent()).name()}; "
            "border: none; border-radius: 4px; padding: 2px 10px 2px 6px; font-weight: bold; } "
            f"QToolButton:hover {{ background: {theme.mix(theme.accent(), QColor('white'), 0.15).name()}; }} "
            f"QToolButton:pressed {{ background: {theme.mix(theme.accent(), QColor('black'), 0.15).name()}; }}")
        swap = theme.colour("pitch").name() if self.prefs.get_value("display/swap_icon") == "theme" else None
        for v in (self.lt_view, self.tt_view):
            v.switch.setIcon(icon("switch", 22, swap))
            v.switch.setIconSize(QSize(22, 22))

    def _switch_style_menu(self, pos):
        menu = QMenu(self)
        now = self.prefs.get_value("display/swap_icon") or "black"
        for key, label in (("black", "Black arrows"), ("theme", "Arrows in the theme colour")):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(now == key)
            a.triggered.connect(lambda *_, k=key: (self.prefs.set_value("display/swap_icon", k),
                                                   self._notebook_icons()))
        menu.exec(pos)

    def _load_notebook(self):
        problem = self.doc.load_notebook()
        if problem:
            QMessageBox.warning(self, "Notebook", problem + "\n\nThe notebook won't be saved over, "
                                "so nothing in it is lost. Check the file, then open the database again.")
        # people found in the notebook join the lists (Q8)
        md = self.doc.db.metadata
        researchers, participants = self.doc.notebook.people()
        for codes, people in ((researchers, md.researchers), (participants, md.participants)):
            have = {p.code for p in people}
            people += [Person(c) for c in codes if c not in have]

    def _record_comments(self):
        """Bring the day's notebook session up to date with today's comments (on saving).

        A day with comments but no session yet gets one, with the panel's people and places."""
        date = self.session_date()
        if not date:
            return
        nb = self.doc.notebook
        s = nb.session(date)
        if s is not None:
            if nbmod.refresh_comments(self.doc.db, s):
                nb.dirty = True
        elif nbmod.dated_comments(self.doc.db, date):
            k = self.session_keys()
            nbmod.write_session(nb, self.doc.db, date, k[chips.RESEARCHERS], k[chips.PARTICIPANTS],
                                k[chips.LOCATIONS])

    def write_notebook(self):
        """Write to notebook: the day's session gets the panel's people and places and the
        day's comments; its notes and questions are left as they are. The notebook is saved."""
        date = self.session_date()
        if not date:
            QMessageBox.information(self, "Notebook", "The session has no date (No date is on), so "
                                    "there's no day to write to.")
            return
        k = self.session_keys()
        try:
            s = nbmod.write_session(self.doc.notebook, self.doc.db, date, k[chips.RESEARCHERS],
                                    k[chips.PARTICIPANTS], k[chips.LOCATIONS])
        except nbmod.NotebookError as exc:
            QMessageBox.warning(self, "Notebook", str(exc))
            return
        if not self.doc.db.path:
            self.doc.notebook_changed()
            self.statusBar().showMessage("Written to the notebook; it is saved with the database.", 6000)
        else:
            try:
                self.doc.notebook.dirty = True
                self.doc.save_notebook(self.prefs.backup_folder)
            except OSError as exc:
                QMessageBox.warning(self, "Notebook", f"Couldn't save the notebook: {exc}")
                return
            self.doc.dirtyChanged.emit(self.doc.dirty)
            n = len(s.comments)
            self.statusBar().showMessage(
                f"Written to the notebook for {date}" + (f", with {n} comment(s)." if n else "."), 6000)
        if self.notebook_dialog is not None:
            self.notebook_dialog.reload(date)

    def open_notebook(self, date: str | None = None):
        from .notebook_dialog import NotebookDialog
        if self.notebook_dialog is None:
            self.notebook_dialog = NotebookDialog(self)
        self.notebook_dialog.reload(date or self.session_date() or None)
        self.notebook_dialog.show()
        self.notebook_dialog.raise_()
        self.notebook_dialog.activateWindow()

    def open_questions(self):
        from .notebook_dialog import QuestionsDialog
        dlg = QuestionsDialog(self)
        dlg.exec()
        if self.notebook_dialog is not None:
            self.notebook_dialog.reload()

    def go_to(self, entry, index=None):
        """Show a lemma (and one of its tokens) from a notebook link."""
        if entry not in self.doc.db.entries:
            return False
        if entry not in self.lemmas.visible_rows():
            self._clear_lemma_filters()
        self.lemmas.select_row(entry)
        if index is not None:
            self.tabs.setCurrentIndex(ALL_DATA)
            row = TokenRow(entry, index)
            if row not in self.all_table.visible_rows():
                self._clear_all_filters()
                self.refresh()
            self.all_table.select_row(row)
        self.raise_()
        self.activateWindow()
        return True

    def session_date(self) -> str:
        return "" if self.sess_nodate.isChecked() else self.sess_date.date().toString("yyyy-MM-dd")

    def _dirty_changed(self, dirty: bool):
        self._update_title()

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

    # ========================================================= theme, view
    def _restyle(self):
        """Colours that follow the theme and accent (the data views stay black on white)."""
        self._notebook_icons()
        a = theme.accent()
        for lbl in (self.lemma_title, self.matrix_title):
            lbl.setStyleSheet(f"color: {theme.colour('pitch').name()};")   # the accent, lighter on dark
        muted = theme.muted()
        for lbl in (self.lemma_count, self.all_count):
            lbl.setStyleSheet(f"color: {muted};")
        self.count_line.setStyleSheet(f"color: {muted}; font-weight: normal;")
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
            f"QTabBar::tab:selected {{ background: {a.name()}; color: {theme.text_on(a).name()}; }}")
        for w in (self.lemmas, self.all_table, self.lt_view, self.tt_view):
            theme.as_data(w)
            w.viewport().update()

    @staticmethod
    def _spec_json(sp: mx.Spec) -> dict:
        return {"m": sp.match, "t": sorted(sp.tags)}

    @staticmethod
    def _spec_from(d) -> mx.Spec:
        match = d.get("m", mx.EXACT)
        if match == mx.CITATION:
            return mx.Spec.citation()
        return mx.Spec(frozenset(d.get("t", [])), match)

    def _save_view(self):
        """Remember this database's view (tab, lemma, matrices) for next time."""
        db = self.doc.db
        if not db.path:
            return
        e = self.lemmas.current_row()
        view = {
            "tab": self.tabs.currentIndex(),
            "lemma": e.ref if e is not None else "",
            "lt_class": self.lt_bar["cls"].currentData() or "",
            "switched": {KINDS[t]: on for t, on in self.switched.items()},
            "configs": [{"kind": c.kind, "class": c.word_class, "name": c.name, "blank": c.blank,
                         "cell": list(c.cell), "x": [self._spec_json(x) for x in c.x],
                         "y": [self._spec_json(y) for y in c.y]} for c in self.configs.values()],
        }
        self.prefs.set_view_for(db.path, view)

    def _restore_view(self):
        db = self.doc.db
        if not db.path:
            return
        view = self.prefs.view_for(db.path)
        if not view:
            return
        try:
            names = {(m.kind, m.word_class, m.name) for m in db.settings.matrices}
            for c in view.get("configs", []):
                cfg = mx.MatrixConfig(kind=c.get("kind", mx.LEMMA_TAG), word_class=c.get("class", ""),
                                      blank=bool(c.get("blank")))
                cfg.x = [self._spec_from(x) for x in c.get("x", [])]
                cfg.y = [self._spec_from(y) for y in c.get("y", [])]
                cfg.cell = list(c.get("cell") or mx.DEFAULT_CELL)
                name = c.get("name", "")
                cfg.name = name if (cfg.kind, cfg.word_class, name) in names else ""
                self.configs[(cfg.kind, cfg.word_class)] = cfg
            for t in (LEMMA_TAG, TAG_TAG):
                self.switched[t] = bool(view.get("switched", {}).get(KINDS[t], False))
            ref = view.get("lemma")
            e = db.entry_by_ref(ref) if ref else None
            if e is not None:
                self.lemmas.select_row(e)
            tab = int(view.get("tab", ALL_DATA))
            if tab in (ALL_DATA, LEMMA_TAG, TAG_TAG):
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(tab)
                self.tabs.blockSignals(False)
                self._tab_changed(tab)
            if tab == LEMMA_TAG and view.get("lt_class") is not None:
                self._set_class(LEMMA_TAG, view.get("lt_class"))
                self.refresh()
        except (TypeError, ValueError, AttributeError, KeyError):
            pass                                  # an unreadable view is simply forgotten

    def _save_window(self):
        self.prefs.set_value("window/geometry", self.saveGeometry())
        for name, sp in (("main", self.main_split), ("left", self.left_split), ("right", self.right_split)):
            self.prefs.set_value(f"window/{name}", sp.saveState())

    def _restore_window(self):
        g = self.prefs.get_bytes("window/geometry")
        if g:
            self.restoreGeometry(g)
        for name, sp in (("main", self.main_split), ("left", self.left_split), ("right", self.right_split)):
            st = self.prefs.get_bytes(f"window/{name}")
            if st:
                sp.restoreState(st)

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
        cb.addItem("(current)" if (cfg.x or cfg.y) else "(blank)" if cfg.blank else
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

    def _only_data_toggled(self, on):
        self.prefs.only_lemmas_with_data = bool(on)
        self.refresh()

    def _scan_sound_folder(self):
        folder = storage.sound_folder(self.doc.db)
        self.sound_files, self.cloud_files = storage.scan_sound_folder(folder)
        for v in (self.lt_view, self.tt_view):
            v.sound_files = self.sound_files
            v.cloud_files = self.cloud_files

    def refresh(self):
        db = self.doc.db
        tab = self.tabs.currentIndex()
        self._scan_sound_folder()
        visible = self.lemmas.visible_rows()
        pin = self.lemmas.pinned_row()
        self.lemma_count.setText(f"{len(visible)} of {len(db.entries)} lemmas shown"
                                 + (f"  ·  only {pin.ref} {db.lemma(pin)} (Ctrl+click again to show all)"
                                    if pin is not None else ""))
        only_data = self.only_data.isChecked()
        if tab == ALL_DATA:
            vis = set(map(id, visible))
            rows = [TokenRow(e, i) for e in db.entries if id(e) in vis
                    and (not only_data or any(t.has_content() for t in e.tokens))
                    for i in range(len(e.tokens))]
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
            hidden = ""
            if only_data and lay.rows:
                with_data = {lay.rows[r].entry.ref for r, _ in lay.cells}
                kept = [e for e in ents if e.ref in with_data]
                if len(kept) != len(ents):
                    hidden = f"  ·  {len(ents) - len(kept)} without token data hidden"
                    ents = kept
                    lay = mx.lemma_tag_layout(db, ents, cfg) if ents else \
                        mx.Layout(message="No lemma has token data in these columns.")
            view = self.lt_view
            total = len(mx.in_class(db, db.entries, cfg.word_class))
            self.count_line.setText(f"{len(ents)} {mx.class_label(cfg.word_class)} lemmas shown "
                                    f"of {total}{hidden}  ·  {len(db.entries)} lemmas in all")
        else:
            e = self.lemmas.current_row()
            if e is not None and e not in visible:
                e = None
            self._set_class(TAG_TAG, self._class_for(TAG_TAG))
            if only_data and e is not None and not any(t.has_content() for t in e.tokens):
                lay = mx.Layout(message="This lemma has no token data (Show only lemmas with token "
                                        "data is on).")
            else:
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
        if tab == LEMMA_TAG and not cfg.x and not cfg.blank:
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
        if (tab == TAG_TAG and not (cfg.x and cfg.y)) or cfg.blank:
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

    def rename_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.name:
            QMessageBox.information(self, "Rename matrix", "Choose a saved matrix first.")
            return
        mats = self.doc.db.settings.matrices
        same = [m for m in mats if m.kind == cfg.kind and m.word_class == cfg.word_class]
        name = ask_matrix_name(self, [m.name for m in same], cfg.name, "Rename matrix", replace=False)
        if not name or name == cfg.name:
            return
        for m in same:
            if m.name == cfg.name:
                m.name = name
        cfg.name = name
        self.doc.settings_changed()

    def clear_matrix(self, tab):
        """Back to a blank view: no rows or columns, nothing chosen."""
        cfg = self.config_for(tab)
        new = mx.MatrixConfig(kind=cfg.kind, word_class=cfg.word_class, cell=list(cfg.cell), blank=True)
        self.configs[(cfg.kind, cfg.word_class)] = new
        self.refresh()

    def delete_saved_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.name:
            QMessageBox.information(self, "Delete matrix", "Choose a saved matrix first.")
            return
        if QMessageBox.question(self, "Delete matrix", f"Delete the saved matrix “{cfg.name}”?") \
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
        self.dialog_autoplay = self.autoplay.isChecked()
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
        if n >= 0 and self.autoplay.isChecked():
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

    def _lemma_edited(self, entry, key, text):
        s = self.doc.db.settings
        name, _, lang = key.partition(":")
        f = s.entry_field(name)
        if f is None:
            return
        text = text.strip()
        if f.role == "gloss" and forbidden_in(text):
            QMessageBox.warning(self, "Gloss", f"{forbidden_in(text)} can't be used in a gloss, "
                                "because glosses can end up in file names.")
            return
        if f.role == "word-class" and text and text not in s.tags.word_class_names():
            QMessageBox.warning(self, "Word class", f"“{text}” isn't a word class. Add it in "
                                "Edit → Tag structure first.")
            return
        if f.closed and f.role != "word-class" and text:
            f.add_value(text)

        def change(e):
            e.set(name, text, lang or None, f.multilingual)
        self.doc.edit_entry(entry, change, f"Edit {f.title}")

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

    # ---- pitch playback and Praat --------------------------------------
    def play_pitch(self, text: str):
        """Play pitch notation in the voice chosen in Settings → Pitch."""
        from .. import pitchsound
        if not pitchmod_parse(text):
            self.statusBar().showMessage("No pitch to play.", 3000)
            return
        s = self.doc.db.settings
        samples = pitchsound.synthesise(text, s.pitch_low, s.pitch_high, self.prefs.pitch_voice,
                                        volume=self.prefs.pitch_volume / 100)
        try:
            self.player.play_samples(samples, pitchsound.RATE)
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play pitch", str(exc))

    def play_selected_pitch(self):
        sel = self.selected_token()
        if sel is None:
            self.statusBar().showMessage("Select a token first.", 3000)
            return
        e, i = sel
        self.play_pitch(e.tokens[i].get("Pitch"))

    def sound_path(self, token) -> Path | None:
        """The token's recording, if it's in the sound folder."""
        if not token.file:
            return None
        p = storage.sound_folder(self.doc.db) / token.file
        return p if p.exists() else None

    def ask_praat_path(self, parent=None) -> str:
        """Ask where Praat is; remembers the answer. Returns "" if cancelled."""
        import sys
        flt = "Praat (Praat.exe);;Programs (*.exe)" if sys.platform.startswith("win") else "All files (*)"
        path, _ = QFileDialog.getOpenFileName(parent or self, "Where is Praat?",
                                              str(Path(self.prefs.praat_path).parent)
                                              if self.prefs.praat_path else str(Path.home()), flt)
        if path:
            self.prefs.praat_path = path
        return path

    def open_in_praat(self, path, parent=None):
        from .. import praat
        parent = parent or self
        if path is None:
            QMessageBox.information(parent, "Open in Praat", "This token has no recording yet.")
            return
        exe = self.prefs.praat_path
        if not exe or not praat.executable(exe).exists():
            QMessageBox.information(parent, "Open in Praat",
                                    "Lemmatrix doesn't know where Praat is yet. Please show it where "
                                    "Praat is (you can change this later in Edit → Settings → Sound).")
            exe = self.ask_praat_path(parent)
            if not exe:
                return
        try:
            praat.open_sound(exe, path)
        except praat.PraatError as exc:
            QMessageBox.warning(parent, "Open in Praat", str(exc))

    def open_selected_in_praat(self):
        sel = self.selected_token()
        if sel is None:
            self.statusBar().showMessage("Select a token first.", 3000)
            return
        e, i = sel
        self.open_in_praat(self.sound_path(e.tokens[i]))

    def _token_items(self) -> list:
        """Menu items for the selected token: play, play pitch, Open in Praat."""
        sel = self.selected_token()
        tok = sel[0].tokens[sel[1]] if sel else None
        has_sound = tok is not None and self.sound_path(tok) is not None
        has_pitch = tok is not None and bool(pitchmod_parse(tok.get("Pitch")))
        return [("Play\tCtrl+Space", "play", self.play_selected, has_sound),
                ("Play pitch\tCtrl+Shift+Space", "play-pitch", self.play_selected_pitch, has_pitch),
                ("Open in Praat", "praat", self.open_selected_in_praat, has_sound)]

    # ---- context menus -------------------------------------------------
    def _menu(self, items, pos):
        m = QMenu(self)
        for item in items:
            if item is None:
                m.addSeparator()
                continue
            text, icon_name, fn = item[:3]
            a = m.addAction(icon(icon_name, 16), text) if icon_name else m.addAction(text)
            a.setEnabled(item[3] if len(item) > 3 else True)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    def _lemma_menu(self, row, pos):
        if row is not None:
            self.lemmas.select_row(row)
        self._menu([("Add lemma", "add", self.add_entry), ("Delete lemma", "delete", self.delete_entry),
                    ("Edit lemma", "edit", self.edit_entry), None,
                    ("Configure columns", "gear", self.configure_lemma_columns),
                    ("Clear all filters", "broom", self._clear_lemma_filters)], pos)

    def _all_menu(self, row, pos):
        if row is not None:
            self.all_table.select_row(row)
        self._menu([("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), None, *self._token_items(), None,
                    ("Configure columns", "gear", self.configure_all_columns),
                    ("Clear all filters", "broom", self._clear_all_filters)], pos)

    def _matrix_menu(self, tab, pos):
        self._menu([("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), None, *self._token_items()], pos)

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
        self.edit_lists("tags")

    def edit_lists(self, start: str | None = None):
        """Edit → Lists: people, places, field lists and the tag structure, in one dialogue."""
        from .lists_dialog import ListsDialog
        dlg = ListsDialog(self, self.doc.db, self.doc.notebook, start if isinstance(start, str) else None)
        if not dlg.exec():
            return
        db = self.doc.db
        renames = dlg.apply()
        speakers = renames[chips.PARTICIPANTS]
        if speakers:                              # the tokens' speakers follow renamed codes
            for e in db.entries:
                for t in e.tokens:
                    if t.speaker in speakers:
                        t.speaker = speakers[t.speaker]
            self.doc.undo.clear()                 # renames can't be undone safely
            if self.prefs.speaker in speakers:
                self.prefs.speaker = speakers[self.prefs.speaker]
        if any(renames.values()):
            self.doc.notebook.rename(renames[chips.RESEARCHERS], speakers, renames[chips.LOCATIONS])
            keys = self.session_keys()
            for kind, row in self.sess_rows.items():
                row.set_keys([renames[kind].get(k, k) for k in keys[kind]])
            self._session_people_changed()
        self._apply_tags(dlg.tags)
        self._fill_session()
        if self.notebook_dialog is not None:
            self.notebook_dialog.reload()

    def _apply_tags(self, dlg):
        """Use the tag structure from the tag editor; renamed tags are followed everywhere."""
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
            for m in db.settings.matrices:            # saved matrices follow too
                m.rename(tag_renames, class_renames)
            old = dict(self.configs)
            self.configs.clear()
            for cfg in old.values():                  # and the matrices on screen
                cfg.rename(tag_renames, class_renames)
                self.configs[(cfg.kind, cfg.word_class)] = cfg
        self._fill_classes()
        self._setup_columns()
        self.doc.settings_changed()
        self._maybe_update_names()

    def edit_settings(self):
        dlg = PreferencesDialog(self, self.doc.db, self.prefs)
        if dlg.exec():
            names_changed = dlg.apply()
            self._apply_autosave()
            theme.from_prefs(self.prefs)
            self._restyle()
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
            if dst.exists() and not storage.same_file(src, dst):     # a case-only rename is fine
                problems.append(f"{t.file}: {new} already exists")
                continue
            try:
                src.rename(dst)
            except OSError as exc:
                problems.append(f"{t.file}: {exc}")
                continue
            self.doc.edit_entry(e, lambda en, i=i, new=new: setattr(en.tokens[i], "file", new),
                                "Rename sound file", renames=[(src, dst)])
            done += 1
        msg = f"Renamed {done} recording(s)."
        if problems:
            msg += "\n\nNot renamed:\n" + "\n".join(problems[:30])
        QMessageBox.information(self, "Sound file names", msg)

    def missing_recordings(self):
        """Recordings in the sound folder that belong to tokens but aren't linked to them.

        Two kinds of token are looked at: those whose stored recording isn't in the folder
        (renamed outside Lemmatrix, say), and those with no recording at all (a recording
        added to the folder by hand, e.g. one cut out of a longer one). Each is matched with
        a recording of the same lemma (reference and gloss) that no other token uses: the
        one with the expected name if there is one, otherwise the closest name, best
        matches first. Returns ([(entry, token index, file name, had a name before)],
        [(entry, token index)] for stored recordings that couldn't be found at all).
        """
        import difflib
        db = self.doc.db
        folder = storage.sound_folder(db)
        try:
            on_disk = {p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".wav"}
        except OSError:
            on_disk = set()
        lower = {n.lower(): n for n in on_disk}
        claimed = {t.file.lower() for e in db.entries for t in e.tokens if t.file and t.file.lower() in lower}
        free = {n for n in on_disk if n.lower() not in claimed}
        found, lost = [], []
        for e in db.entries:
            needy = [i for i, t in enumerate(e.tokens) if not t.file or t.file.lower() not in lower]
            if not needy:
                continue
            stem = f"_{e.ref}_{e.file_gloss or db.gloss(e)}".lower()
            candidates = {n for n in free if stem in n.lower()}
            if not candidates:
                lost += [(e, i) for i in needy if e.tokens[i].file]
                continue
            pairs = []
            for i in needy:
                t = e.tokens[i]
                exp = db.expected_filename(e, t)
                for c in candidates:
                    if c.lower() == exp.lower():
                        score = 2.0                       # exactly the name it should have
                    else:
                        names = [exp] + ([t.file] if t.file else [])
                        score = max(difflib.SequenceMatcher(None, c.lower(), x.lower()).ratio() for x in names)
                    if score > 0.8:
                        pairs.append((score, i, c))
            done_tokens, done_files = set(), set()
            for score, i, c in sorted(pairs, key=lambda p: -p[0]):     # best matches first
                if i in done_tokens or c in done_files:
                    continue
                done_tokens.add(i)
                done_files.add(c)
                found.append((e, i, c, bool(e.tokens[i].file)))
            free -= done_files
            lost += [(e, i) for i in needy if i not in done_tokens and e.tokens[i].file]
        return found, lost

    def find_missing_recordings(self):
        found, lost = self.missing_recordings()
        if not found and not lost:
            QMessageBox.information(self, "Missing recordings",
                                    "Every recording is linked to its token, and no token's recording is missing.")
            return

        def label(e, i):
            t = e.tokens[i]
            tags = " + ".join(mx.chips(self.doc.db, t.tags, self.doc.db.word_class(e) or None)) or "citation"
            return f"{e.ref} {tags}"
        lines = [f"{label(e, i)}: {e.tokens[i].file}  →  {name}" if had else
                 f"{label(e, i)} (no recording yet)  →  {name}" for e, i, name, had in found]
        msg = ""
        if found:
            msg += f"These {len(found)} recording(s) seem to belong to these tokens:\n\n" + \
                "\n".join(lines[:40]) + ("\n…" if len(lines) > 40 else "")
        if lost:
            msg += ("\n\n" if msg else "") + f"{len(lost)} recording(s) couldn't be found at all:\n" + \
                "\n".join(f"{e.ref}: {e.tokens[i].file}" for e, i in lost[:20])
        if not found:
            QMessageBox.information(self, "Missing recordings", msg)
            return
        if QMessageBox.question(self, "Missing recordings",
                                msg + "\n\nLink the tokens to these recordings?") != QMessageBox.Yes:
            return
        for e, i, name, _ in found:
            self.doc.edit_entry(e, lambda en, i=i, name=name: setattr(en.tokens[i], "file", name),
                                "Link recording")
        self._maybe_update_names()

    def _report_missing(self):
        """A status-bar note when recordings aren't linked to their tokens."""
        found, lost = self.missing_recordings()
        if found or lost:
            self.statusBar().showMessage(f"{len(found) + len(lost)} recording(s) aren't linked to their tokens: "
                                         "Tools → Find missing recordings.", 15000)

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

    # ============================================================== export
    def _visible_table(self):
        """What the current tab shows, as (header, rows)."""
        tab = self.tabs.currentIndex()
        if tab == ALL_DATA:
            t = self.all_table
            cols = [c for c in t.model_.columns if c.kind != "drawing"]
            header = [c.title for c in cols]
            rows = []
            for r in t.visible_rows():
                out = []
                for c in cols:
                    v = c.display(r) if c.display else c.get(r)
                    if c.key == "tags" and not v:
                        v = "Citation"
                    out.append(", ".join(v) if isinstance(v, (list, tuple, set, frozenset)) else (v or ""))
                rows.append(out)
            return header, rows
        return self._matrix_table(tab)

    def _matrix_table(self, tab):
        db = self.doc.db
        lay = self.layouts.get(tab)
        cfg = self.config_for(tab)
        if lay is None or not (lay.rows and lay.cols):
            return [], []
        defaults = mx.default_names(db)
        fields = [f for f in cfg.cell if f != "drawing"]
        if "drawing" in cfg.cell and not any(db.settings.token_field(f) and
                                             db.settings.token_field(f).role == "pitch" for f in fields):
            pitch = next((f.name for f in db.settings.token_fields if f.role == "pitch"), None)
            if pitch:
                fields.insert(0, pitch)             # the drawing exports as its pitch digits

        def label(item):
            return f"{item.entry.ref} {item.label}" if item.entry is not None else item.label

        def text(t, name):
            f = db.settings.token_field(name)
            return t.get(name, db.settings.primary_gloss) if f and f.multilingual else t.get(name)

        corner = (f"{lay.entry.ref} {db.lemma(lay.entry)}" if lay.entry is not None else "")
        header = [corner] + [label(c) for c in lay.cols]
        rows = []
        for r, row in enumerate(lay.rows):
            out = [label(row)]
            for c in range(len(lay.cols)):
                hits = lay.tokens(r, c)
                entry, _ = lay.target(r, c)
                wc = mx.class_of(db, entry) if entry is not None else None
                blocks = []
                for _, t in hits:
                    lines = []
                    if len(hits) > 1:
                        extra = mx.extra_chips(db, t, lay.spec_at(r, c), wc or None, defaults)
                        if extra:
                            lines.append(" ".join(extra))
                    lines += [text(t, n) for n in fields if text(t, n)]
                    blocks.append("\n".join(lines))
                out.append("\n\n".join(blocks))
            rows.append(out)
        return header, rows

    def export_csv(self, filtered: bool):
        from .. import export
        db = self.doc.db
        tab = self.tabs.currentIndex()
        if filtered:
            header, rows = self._visible_table()
            what = {ALL_DATA: "All data", LEMMA_TAG: "Lemma-Tag", TAG_TAG: "Tag-Tag"}[tab]
            if not rows:
                QMessageBox.information(self, "Export", "Nothing is showing in this tab to export.")
                return
        else:
            header, rows = export.database_table(db)
            what = "entire database"
        stem = Path(db.path).stem if db.path else "Lemmatrix"
        start = Path(db.path).parent if db.path else Path.home() / "Documents"
        path, _ = QFileDialog.getSaveFileName(self, "Export as CSV", str(start / f"{stem} - {what}.csv"),
                                              "CSV (comma-separated) (*.csv)")
        if not path:
            return
        try:
            n = export.write_csv(path, header, rows)
        except OSError as exc:
            QMessageBox.warning(self, "Export", f"Couldn't write {Path(path).name}: {exc}")
            return
        self.statusBar().showMessage(f"Exported {n} rows to {QDir.toNativeSeparators(path)}.", 8000)

    # =============================================================== files
    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        r = QMessageBox.question(self, "Lemmatrix", "Save changes first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        if r == QMessageBox.Discard and self.doc.renamed:
            # recordings renamed since the last save get the names the saved database expects
            problems = self.doc.revert_renames()
            if problems:
                QMessageBox.warning(self, "Sound file names",
                                    "These recordings couldn't get their old names back, so "
                                    "Tools → Find missing recordings may be needed next time:\n\n"
                                    + "\n".join(problems[:30]))
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
        if not self._open_elsewhere_ok(path):
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
        self._record_comments()
        try:
            self.doc.save(backup_dir=self.prefs.backup_folder)
        except OSError as exc:
            QMessageBox.warning(self, "Save", f"Couldn't save: {exc}")
            return False
        self.prefs.last_file = self.doc.db.path
        self._fill_session()
        where = QDir.toNativeSeparators(str(storage.backup_folder(self.doc.db.path, self.prefs.backup_folder)))
        self.statusBar().showMessage(f"Saved. The previous version is in {where}.", 5000)
        return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save database as",
                                              self.doc.db.path or str(Path.home() / "Documents"),
                                              "Lemmatrix database (*.xml)")
        if not path:
            return False
        self.doc.db.path = path
        self._update_title()
        if self.save():
            self._mark_open(path)
            return True
        return False

    # ------------------------------------------- open on another computer
    def _open_elsewhere_ok(self, path: str) -> bool:
        """Warn if the database is open in another Lemmatrix (another computer, usually)."""
        info = lockmod.held_elsewhere(path)
        if info is None or str(Path(path).resolve()) == self._locked_path:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Open elsewhere")
        same = info.computer == lockmod.this_computer()
        box.setText(f"{Path(path).name} seems to be open "
                    + ("in another Lemmatrix window on this computer" if same else f"on {info.computer}") + ".")
        box.setInformativeText(
            f"{info.describe()}.\n\nIf it's open in two places and both save, OneDrive keeps one version "
            "and makes a conflict copy of the other, and the changes have to be merged by hand.\n\n"
            "If Lemmatrix on that computer was closed or crashed without tidying up, it's safe to open "
            "anyway.")
        anyway = box.addButton("Open anyway", QMessageBox.AcceptRole)
        box.addButton("Don't open", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is anyway

    def _mark_open(self, path: str):
        """Move this window's open-marker to the given database ("" for none)."""
        new = str(Path(path).resolve()) if path else ""
        if new == self._locked_path:
            return
        if self._locked_path:
            lockmod.release(self._locked_path)
        self._locked_path = new
        if new:
            lockmod.claim(new)
            self.heartbeat.start()
        else:
            self.heartbeat.stop()

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
            try:
                self._save_view()
                self._save_window()
                self._mark_open("")
            except Exception:                           # never stop the window closing
                pass
            # Nothing should react to the undo history being thrown away as the window closes.
            self.doc.undo.blockSignals(True)
            self.doc.blockSignals(True)
            event.accept()
        else:
            event.ignore()
