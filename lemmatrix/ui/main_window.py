# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The main window: lemma list on the left, the Matrix on the right."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDate, QDir, QEvent, QObject, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
                               QProgressDialog,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSplitter, QStackedWidget, QTabBar, QToolButton, QVBoxLayout,
                               QWidget)

from .. import __version__, audio, filters as fl, layout, lock as lockmod, matrix as mx, storage
from . import theme
from . import widgets as _w  # (ask: buttons that say what they do)


def about_text() -> str:
    """Help → About Lemmatrix: version, copyright, licence, source and libraries."""
    from .. import CONCEPT_DOI, COPYRIGHT, SOURCE_URL, SUPPORT_EMAIL
    return (f"<b>Lemmatrix</b> {__version__}<br>"
            "<i>Human readable, machine processable, ethically collected and shared linguistic data.</i>"
            "<br><br>"
            "Phonological and grammatical analysis and linguistic documentation, for any language. "
            "Prototype (v0).<br><br>"
            f"{COPYRIGHT}<br>"
            "Lemmatrix, its idea and its design are the work of Joshua A. G. Smolders. "
            f'Cite it as <a href="https://doi.org/{CONCEPT_DOI}">doi:{CONCEPT_DOI}</a>.<br><br>'
            "Lemmatrix is free software, free of charge, always: you can redistribute it and/or modify "
            "it under the terms of the GNU Affero General Public License as published by the Free "
            "Software Foundation, either version 3 of the License, or (at your option) any later "
            "version, with the additional terms in NOTICE.md (keep the author's credit, mark changes, "
            "use another name). It comes with <b>no warranty</b>, to the extent permitted by law.<br><br>"
            "The icons, the splash screen and the ɛλicit drawings are the author's artwork, "
            "all rights reserved (ARTWORK.md), and so are the sample databases, the author's creative work "
            "(SAMPLES.md). The Extended African Comparative Wordlist is the "
            "author's data under CC BY 4.0 (lemmatrix/wordlists/LICENSE-EACW.md). "
            "The IPA soundfiles are from Wikimedia Commons, recorded by Peter Isotalo, Denelson83, "
            "Adamsa123, Halibutt and others, each under its own licence (lemmatrix/ipa/CREDITS.md). "
            "Lemmatrix™ (also written λemmatriχ™) and ɛλicit™ are trademarks of "
            "Joshua A. G. Smolders.<br><br>"
            f'Source code: <a href="{SOURCE_URL}">{SOURCE_URL.removeprefix("https://")}</a><br>'
            f'Support, bugs and suggestions: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a><br><br>'
            "<small>Built with Qt for Python (PySide6, LGPL-3.0), NumPy, sounddevice, SoundCard, "
            "lemminflect, pyspellchecker, pyzipper, praatio, Pillow, soundfile and pycountry, each under its own licence "
            "(THIRD-PARTY.md).</small>")
from ..defaults import new_database
from .. import bulk, notebook as nbmod, predict, report, spelling, wordlists
from ..model import Database, Entry, ListItem, Person, forbidden_in, today
from . import chiprow as chips
from .dialogs import EntryDialog, MetadataDialog, PreferencesDialog
from .document import Document
from .fields_dialog import FieldsDialog
from .filter_dialogs import ConfigureColumnsDialog
from .icons import toggle_icon, THEMED, elicit_icon, icon, icon_size, themed_icon
from .matrix_dialogs import ConfigureCellDialog, ConfigureMatrixDialog, ask_matrix_name
from .matrix_view import MatrixView
from .prefs import Prefs
from . import spellui
from . import symbols
from .spellui import SpellDelegate
from .table import ChipsDelegate, Column, DrawingDelegate, FilterTable, ListEditDelegate, SuggestionDelegate
from .token_dialog import Slot, TokenDialog
from . import widgets

def pitchmod_parse(text):
    from .. import pitch
    return pitch.parse(text or "")


SAMPLE = Path(__file__).resolve().parent.parent.parent / "samples" / "Sample.xml"
ELICIT_TEST = SAMPLE.parent / "Elicit test" / "ITA-STD_Elicit_Test.xml"
ALL_DATA, LEMMA_TAG, TAG_TAG = 0, 1, 2
HIDE_EMPTY = "lemmas/hide_empty"     # the workspace: Hide empty lemmas in the lemma list (idea 55)
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


ICON_ONLY = {"add", "delete", "edit", "play", "reset-filters",   # obvious, shared actions: the name is in the tooltip
             "gear-cells", "gear-columns", "gear-matrix", "find-missing", "move-token", "lemma-token", "hide-empty", "hide-empty-tokens", "tick",
             "camera", "xml-viewer"}


class _ElicitChecked(QObject):
    """Carries the background look in Google Drive back to the main thread."""
    done = Signal(object, object)


class _RestyleOnShow(QObject):
    """A hidden window missed a theme change: it is restyled the next time it is shown (25 October;
    before, the XML viewer kept the old theme's colours)."""
    _filter = None

    @classmethod
    def mark(cls, w: QWidget):
        if cls._filter is None:
            cls._filter = cls()
        if not w.property("restyle_on_show"):
            w.setProperty("restyle_on_show", True)
            w.installEventFilter(cls._filter)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and obj.property("restyle_on_show"):
            obj.setProperty("restyle_on_show", False)
            obj.removeEventFilter(self)
            obj._restyle()
        return False


def tool(text: str, icon_name: str | None, fn, tip: str = "") -> QToolButton:
    b = QToolButton()
    b.setText(text)
    if icon_name:
        size = 28 if icon_name == "xml-viewer" else 20   # Josh's χμλ has room round it: a little larger
        b.setProperty("icon_name", icon_name)
        b.setIcon(themed_icon(icon_name, size))
        b.setIconSize(icon_size(icon_name, size))
        b.setToolButtonStyle(Qt.ToolButtonIconOnly if icon_name in ICON_ONLY else Qt.ToolButtonTextBesideIcon)
    b.setToolTip(tip or text)
    b.setAutoRaise(True)
    b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
    return b


class DbTitle(QLabel):
    """The big title at the top left: language - variety - database name. Double-click: the metadata."""

    def __init__(self, on_double_click):
        super().__init__()
        self.on_double_click = on_double_click
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.3)
        self.setFont(f)
        self.setToolTip("Language - variety - database name. Double-click to edit the metadata.")

    def mouseDoubleClickEvent(self, event):
        self.on_double_click()



def bring_forward(w):
    """Show a window of its own and bring it to the front (out of the taskbar if minimised)."""
    if w.isMinimized():
        w.showNormal()
    w.show()
    w.raise_()
    w.activateWindow()

class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.prefs = Prefs()
        widgets.set_ipa_size(self.prefs.ipa_size)   # before any view is built (audit, 25 October)
        widgets.set_abbreviate(self.prefs.abbreviate_fields)   # the edit dialogues' labels (idea 73)
        from . import conventions                 # the cell views' display conventions (idea 26)
        conventions.load(self.prefs)
        self.player = audio.Player()
        self.doc = Document(db or new_database())
        self.doc.setParent(self)
        from . import keyboards                   # automatic keyboard switching (idea 43): this database's fields
        keyboards.set_context(lambda: (self.doc.db, self.prefs))
        self.configs: dict = {}               # (kind, word class) -> current MatrixConfig
        self.switched = {LEMMA_TAG: False, TAG_TAG: False}
        self.layouts: dict = {}
        self.dialog_autoplay = False
        self.notebook_dialog = None               # the notebook window, once opened
        self.items_dialogs = {}                   # View → Questions / To Do windows, once opened
        self.bulk_window = None                   # the bulk edit window, while it's open
        self.utterances_window = None             # View → Texts and utterances, while it's open
        self.xml_window = None                    # View → XML viewer, while it's open
        self.cogitate_window = None               # View → Cogitate (hypotheses), once opened
        self.whiteboard_window = None             # Tools → Whiteboard (idea 45), once opened
        self.sound_files: set[str] = set()       # names in the sound folder, refreshed with the views
        self.cloud_files: set[str] = set()       # those of them that are online-only (OneDrive)
        self._suggestions: dict = {}             # (entry id, tags) -> predicted translation, for All data
        self._suggestions_stale = True           # the database changed since they were worked out
        self.spell_checker = spelling.Checker()  # English spelling, with the database's word list
        self.speller = spellui.Speller(self.spelling_spans, self.spell_checker.suggestions,
                                       self.add_spelling_word)
        self.spelling_window = None
        self.resize(1500, 920)
        theme.from_prefs(self.prefs)
        widgets.SHOW_UNUSUAL = self.prefs.warn_unusual_tags
        self._build()
        self._build_menus()
        self._fix_status_bar()
        self._restyle()
        self._restore_window()
        self.doc.work_date = self.work_date
        self.doc.changed.connect(self._doc_changed)
        self.doc.pitchKindChanged.connect(self.pitch_view_changed)   # converted, or undone (idea 9)
        self.doc.snapshotsChanged.connect(self._snapshots_changed)   # the Snapshots list (24 October)
        self.doc.dirtyChanged.connect(self._dirty_changed)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self._autosave)
        self._locked_path = ""                    # the database this window has marked as open
        self.heartbeat = QTimer(self)             # keeps the "last active" time in the marker fresh
        self.heartbeat.setInterval(5 * 60_000)
        self.heartbeat.timeout.connect(lambda: self._locked_path and lockmod.claim(self._locked_path))
        self._apply_autosave()
        # The English word lists, loaded quietly once opening is done, rather than on the first gloss
        # checked (25 October); in a thread, so the window never waits for them
        def _warm():
            import threading
            from .. import spelling
            threading.Thread(target=spelling.warm, daemon=True).start()
        QTimer.singleShot(3000, _warm)
        self._view_timer = QTimer(self)           # the view, filters and searches into the workspace,
        self._view_timer.setSingleShot(True)      # a moment after they change (idea 36)
        self._view_timer.setInterval(800)
        self._view_timer.timeout.connect(self._save_view)
        for sig in (self.lemmas.filtersChanged, self.all_table.filtersChanged, self.lemma_search.textChanged,
                    self.all_search.textChanged, self.tabs.currentChanged):
            sig.connect(lambda *_: self._view_timer.start())
        self.elicit_drive_ready: dict[str, tuple[str, int, str]] = {}   # request id -> (speaker, recordings, why)
        self._elicit_checking = False
        self._elicit_signal = _ElicitChecked(self)  # the background look in Drive reports here
        self._elicit_signal.done.connect(self._elicit_checked)
        self.elicit_check = QTimer(self)          # ɛλicit requests out through Google Drive: looked at
        self.elicit_check.setInterval(10 * 60_000)  # every 10 minutes (and on opening a database)
        self.elicit_check.timeout.connect(self.check_elicit_drive)
        self.elicit_check.start()
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
        self.lemma_head = QWidget()                # same height as the matrix's title row, so the
        lh = QHBoxLayout(self.lemma_head)          # two tables start level (set in _restyle)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.addWidget(self.lemma_title)
        lh.addStretch(1)
        lb.addWidget(self.lemma_head)
        lb.addWidget(self.lemmas, 1)
        left.addWidget(lemma_box)
        bar, bl = self._bar()
        self.lemma_count = QLabel()               # "2369 / 2369": shown / all, at the right of the buttons
        row = self._row(bl, tool("Add", "add", self.add_entry, "Add a lemma"),
                        tool("Delete", "delete", self.delete_entry, "Delete the selected lemma or lemmas (Delete)"),
                        tool("Edit", "edit", self.edit_entry, "Edit the selected lemma (Enter)"),
                        tool("Create token for this lemma", "lemma-token", self.add_token_to_lemma,
                             "Create token for this lemma: a new token of the lemma selected here\n"
                             "With several lemmas selected (Ctrl+click, Shift+click, Ctrl+A): "
                             "one token per lemma for each combination of the tags you pick"),
                        tool("Configure columns", "gear-columns", self.configure_lemma_columns),
                        tool("Clear all filters", "reset-filters", self._clear_lemma_filters, "Clear all filters"))
        self.hide_empty = tool("Hide empty lemmas", "hide-empty", lambda: None,
                               "Hide empty lemmas: leave out the lemmas with no token data (no tokens, or "
                               "only tokens with nothing typed and no recording). Click again to show them; "
                               "Clear all filters shows them too.")
        self.hide_empty.setCheckable(True)        # this database's, in its workspace (idea 55, Josh, 24 October)
        self.hide_empty.setIcon(toggle_icon("hide-empty"))   # grey λ, a red line across while on (idea 74)
        self.hide_empty.toggled.connect(self._hide_empty_toggled)
        row.insertWidget(row.count() - 1 if row.count() else 0, self.hide_empty)
        row.addWidget(self.lemma_count)
        self.lemma_search = QLineEdit()
        self.lemma_search.setPlaceholderText("quick search of the visible columns")
        self.lemma_search.setClearButtonEnabled(True)
        bl.addWidget(self.lemma_search)
        cv = QLineEdit()
        cv.setPlaceholderText("CV shape filter, e.g. (C)V(V)C(.CVC) — Stage 2")
        cv.setEnabled(False)
        cv.setToolTip("Matches the Lemma field. Arrives in version 2 (Analyze).")
        bl.addWidget(cv)
        bl.addStretch(1)
        self.tick_button = tool("I found a tick!", "tick", lambda: self.send_report("bug"),
                                "I found a tick! Report a bug: an email to " + report.SUPPORT_EMAIL)
        self._row(bl, self.tick_button)            # bottom left of the lemma controls
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
        self.matrix_head = QWidget()               # the title, with the tabs on the same row
        top = QHBoxLayout(self.matrix_head)
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.matrix_title)
        top.addStretch(1)
        self.head_icons = QHBoxLayout()            # icons beside the tabs (more can go to the left later)
        self.head_icons.setContentsMargins(0, 0, 8, 0)
        self.head_icons.setSpacing(4)
        self.head_icons.addWidget(self._elicit_button())   # ɛλicit, left of Texts and utterances
        self.head_icons.addWidget(self._xml_button())      # the XML viewer, between them (21 October)
        self.head_icons.addWidget(self._cogitate_button())    # Cogitate, between χμλ and the ? (21 October)
        self.head_icons.addWidget(self._questions_button())   # Questions, Snapshots, To Do, Texts and utterances
        self.head_icons.addWidget(self._snapshots_button())   # Snapshots, between ? and the flag (24 October)
        self.head_icons.addWidget(self._todo_button())        # To Do's flag (Josh, 21 October)
        self.head_icons.addWidget(self._texts_button())
        top.addLayout(self.head_icons)
        self.tabs = QTabBar()
        for name in ("All data", "Lemma/Tag", "Tag/Tag"):
            self.tabs.addTab(name)
        self.tabs.setExpanding(False)
        top.addWidget(self.tabs, 0, Qt.AlignBottom)
        bxl.addWidget(self.matrix_head)
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
        self.autoplay.toggled.connect(lambda on: self.doc.ws_set("autoplay", bool(on)))   # each database its own
        # Hide empty tokens (idea 74, Josh, 26 October; was the checkbox "Show only lemmas with token
        # data" here): a τ toggle in each tab's options bar, the three kept in step (one setting)
        self.hide_tokens_btns = [self._hide_tokens_button() for _ in range(3)]
        self.only_data = self.hide_tokens_btns[0]          # All data's (the name kept for the code)
        self.only_data.toggled.connect(self._only_data_toggled)
        for b in self.hide_tokens_btns[1:]:
            b.toggled.connect(self.only_data.setChecked)
        opts = QHBoxLayout()
        opts.setContentsMargins(4, 0, 0, 0)
        opts.addWidget(self.autoplay)
        opts.addStretch(1)
        self.panels_btn = QToolButton()          # hides or shows the option panels below
        self.panels_btn.setAutoRaise(True)
        self.panels_btn.setIconSize(QSize(18, 18))
        self.panels_btn.clicked.connect(lambda *_: self.toggle_panels())
        opts.addWidget(self.panels_btn)
        bxl.addLayout(opts)
        normal = QFont(box.font())
        normal.setBold(False)              # set explicitly, or it would be inherited bold
        for w in (self.tabs, self.views, self.autoplay):
            w.setFont(normal)
        right.addWidget(box)

        bottom = QWidget()
        bot = self.bottom_row = QHBoxLayout(bottom)
        bot.setContentsMargins(0, 0, 0, 0)
        self.options = QStackedWidget()
        self.options.addWidget(self._all_data_bar())
        self.lt_bar = self._matrix_bar(LEMMA_TAG)
        self.tt_bar = self._matrix_bar(TAG_TAG)
        self.options.addWidget(self.lt_bar["widget"])
        self.options.addWidget(self.tt_bar["widget"])
        bot.addWidget(self.options, 1)
        bot.addWidget(self._scratch_panel())      # the pitch scratchpad, left of Current Session (22 October)
        bot.addWidget(self._session_panel())      # as wide as its chips need (_fit_session)
        # the dock for minimised windows, a strip along the bottom of the working panels (idea 78)
        from .dock import MinimiseDock
        panels = QWidget()
        pl = QVBoxLayout(panels)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(bottom, 1)
        self.dock = MinimiseDock()
        pl.addWidget(self.dock)
        right.addWidget(panels)
        right.setSizes([720, 150])
        right.installEventFilter(self)            # Current Session follows the pane's width
        main.addWidget(right)
        for sp in (left, right):                  # the option panels can be dragged out of sight
            sp.setCollapsible(0, False)
            sp.setCollapsible(1, True)
            sp.splitterMoved.connect(lambda *_: self._panels_icon())
        self._panel_sizes = {"left": 170, "right": 150}   # heights to give back when shown again
        main.setSizes([470, 1030])

        # ---- signals -----------------------------------------------------
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(lambda: self.refresh(after_edit=True))
        # The lemmas changed in place since All data and Lemma/Tag last showed them (ids), or None
        # for anything: what they redraw or measure again after an edit (_doc_changed)
        self._touched = {ALL_DATA: None, LEMMA_TAG: None}
        self._search_timers = {}
        for name, edit, fn in (("lemma", self.lemma_search, self.lemmas.proxy.set_search),
                               ("all", self.all_search, self.all_table.proxy.set_search)):
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(250)
            t.timeout.connect(lambda e=edit, f=fn: f(e.text()))
            edit.textChanged.connect(lambda _, t=t: t.start())
            self._search_timers[name] = t
        # `CAWL 345`, `SWADESH`… in the lemma list's search (idea 40): a filter like any search,
        # and the one lemma found is selected, so the matrix follows
        from .. import wordlists
        self.lemmas.proxy.term_match = lambda row, term: wordlists.search_match(self.doc.db, row, term)
        self._search_timers["lemma"].timeout.connect(self._select_wordlist_hit)
        self.lemmas.alt_click_pins = True         # the pin (Ctrl+click until 24 October, idea 64)
        self.lemmas.set_multi_select()            # Ctrl, Shift, Ctrl+Shift, Ctrl+A (idea 64)
        self.lemmas.filtersChanged.connect(lambda: self.schedule_refresh())
        self.lemmas.rowActivated.connect(lambda e: self.edit_entry())
        self.lemmas.deleteRequested.connect(self.delete_entry)
        self.lemmas.contextRequested.connect(self._lemma_menu)
        self.lemmas.selectionModel().currentRowChanged.connect(lambda *a: self._lemma_selected())
        self.all_table.filtersChanged.connect(self._update_counts)
        self.all_table.rowActivated.connect(lambda r: self.edit_token())
        self.all_table.lemmaActivated.connect(lambda r: self._jump_to_lemma(r.entry))
        self.all_table.deleteRequested.connect(self.delete_token)
        self.all_table.contextRequested.connect(self._all_menu)
        self.all_table.space_plays = True
        self.all_table.click_unselects = True     # a click on the selected token unselects it
        self.all_table.set_multi_select()         # Ctrl+click, Shift+click (Josh, 24 October)
        self.all_table.playRequested.connect(self.play_selected)
        self.all_table.clicked.connect(lambda *_: self.autoplay.isChecked() and self.play_selected())
        self.all_table.model_.edited.connect(self._cell_edited)
        self.lemmas.model_.edited.connect(self._lemma_edited)
        self.tabs.currentChanged.connect(self._tab_changed)
        for view, tab in ((self.lt_view, LEMMA_TAG), (self.tt_view, TAG_TAG)):
            view.tokenClicked.connect(lambda r, c, n, tab=tab: self._token_clicked(tab, r, c, n))
            view.cellActivated.connect(lambda r, c, n, tab=tab: self._cell_activated(tab, r, c, n))
            view.fieldEdited.connect(self._matrix_field_edited)
            view.contextRequested.connect(lambda r, c, n, pos, tab=tab: self._matrix_menu(tab, pos))
            view.deleteRequested.connect(self.delete_token)
            view.switchRequested.connect(lambda tab=tab: self.switch_axes(tab))
            view.columnMoved.connect(lambda a, b, tab=tab: self.move_matrix_column(tab, a, b))
            view.playRequested.connect(self.play_selected)
        self.lt_view.entryActivated.connect(self._jump_to_lemma)

    def _all_data_bar(self) -> QWidget:
        bar, bl = self._bar()
        self.all_count = QLabel()                 # "366 / 366": tokens shown / all
        top = self._row(bl, tool("Add", "add", self.add_token, "Add a token"),
                        tool("Delete", "delete", self.delete_token, "Delete the selected token (Delete)"),
                        tool("Edit", "edit", self.edit_token, "Edit the selected token (Enter)"),
                        tool("Play", "play", self.play_selected, "Play the selected token (Ctrl+Space)"),
                        tool("Move token to another lemma", "move-token", self.move_token,
                             "Move the selected token to another lemma…"),
                        tool("Find missing or unlinked recordings", "find-missing", self.find_missing_recordings,
                             "Find missing or unlinked recordings…"),
                        tool("Configure columns", "gear-columns", self.configure_all_columns),
                        tool("Clear all filters", "reset-filters", self._clear_all_filters),
                        self.hide_tokens_btns[0], self._camera_button())
        top.addWidget(self.all_count)
        self.all_search = QLineEdit()
        self.all_search.setPlaceholderText("quick search of the visible columns")
        self.all_search.setClearButtonEnabled(True)
        cv = QLineEdit()
        cv.setPlaceholderText("CV shape filter (Phonetic) — Stage 2")
        cv.setEnabled(False)
        bl.addWidget(self.all_search)             # the CV shape filter under the search (Josh, 23 October)
        bl.addWidget(cv)
        bl.addStretch(1)
        return bar

    def _matrix_bar(self, tab) -> dict:
        bar, bl = self._bar()
        d = {"widget": bar}
        # the pencil is edit mode here (Josh, 21 October): a token's lines edited in its cell; the
        # token dialogue opens with Enter, a double-click or the right-click menu
        d["edit_btn"] = tool("Edit mode", "edit", self.toggle_matrix_edit,
                             "Edit mode (Ctrl+E): click a line of a token to edit it in its cell (Enter keeps, "
                             "Esc drops, Tab goes to the next line). The token dialogue: Enter or double-click")
        d["edit_btn"].setCheckable(True)
        self._row(bl, tool("Add", "add", self.add_token, "Add a token in the selected cell"),
                  tool("Delete", "delete", self.delete_token, "Delete the selected token (Delete)"),
                  d["edit_btn"],
                  tool("Play", "play", self.play_selected, "Play the selected token (Ctrl+Space)"),
                  tool("Configure cell", "gear-cells", lambda tab=tab: self.configure_cell(tab),
                       "Configure cell: choose what each cell shows"),
                  tool("Configure matrix", "gear-matrix", lambda tab=tab: self.configure_matrix(tab),
                       "Configure matrix: choose the rows and columns"),
                  tool("Clear matrix", "reset-filters", lambda tab=tab: self.clear_matrix(tab),
                       "Clear matrix: empty the view, no rows or columns"),
                  self.hide_tokens_btns[1 if tab == LEMMA_TAG else 2],
                  self.conventions_button(), self._camera_button())
        d["saved"] = QComboBox()
        d["saved"].setMinimumWidth(170)
        d["saved"].setToolTip("Saved matrices" + (": the lemmas are the ones the lemma list shows"
                                                  if tab == LEMMA_TAG else ""))
        d["saved"].activated.connect(lambda i, tab=tab: self._saved_chosen(tab, i))
        self._row(bl, QLabel("Matrix"), d["saved"],
                  tool("Save matrix", None, lambda tab=tab: self.save_matrix(tab),
                       "Save this matrix under a name"),
                  tool("Rename matrix", None, lambda tab=tab: self.rename_matrix(tab),
                       "Rename the chosen saved matrix"),
                  tool("Delete matrix", None, lambda tab=tab: self.delete_saved_matrix(tab),
                       "Delete the chosen saved matrix"))
        d["edit_mode"] = QLabel("Edit mode")      # shown while Ctrl+E edit mode is on
        d["edit_mode"].hide()
        bl.itemAt(0).layout().insertWidget(4, d["edit_mode"])
        d["count"] = QLabel()                     # lemmas shown, the lemma, the matrix's messages
        d["count"].setWordWrap(True)
        bl.addWidget(d["count"])
        bl.addStretch(1)
        return d

    def _hide_tokens_button(self) -> QToolButton:
        b = tool("Hide empty tokens", "hide-empty-tokens", lambda: None,
                 "Hide empty tokens: All data leaves out the lemmas whose tokens are all empty; Lemma/Tag "
                 "the lemmas with nothing in any of the matrix's columns; Tag/Tag shows nothing for a lemma "
                 "without token data. Click again to show them; All data's Clear all filters shows them too.")
        b.setCheckable(True)
        b.setIcon(toggle_icon("hide-empty-tokens"))   # grey τ, a red line across while on (idea 74)
        return b

    def _only_data_toggled(self, on):
        for b in self.hide_tokens_btns[1:]:       # the other tabs' toggles follow
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        self.doc.ws_set("only_with_data", bool(on))
        self.refresh()

    # ---- snapshots (Cogitate, IDEAS.md ideas 16 and 35) -----------------------------------------
    def _camera_button(self) -> QToolButton:
        """The camera, in every tab's options: a click takes a snapshot of the complete setup into the
        Snapshots list (Josh, 24 October); right-click for the menu it used to open."""
        b = tool("Snapshot", "camera", self.take_snapshot,
                 "Take a snapshot: the complete setup (tab, lemma, filters, matrix), into the Snapshots "
                 "list (Ctrl+Shift+P). Right-click: link it to a hypothesis")
        b.setContextMenuPolicy(Qt.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda pos, b=b: self.snapshot_menu(b.mapToGlobal(pos)))
        return b

    def snapshot_menu(self, pos):
        m = QMenu(self)
        a = m.addAction(icon("camera", 16, theme.colour("pitch").name()), "Take snapshot")
        a.triggered.connect(lambda *_: self.take_snapshot())
        a = m.addAction(icon("cogitate", 16, theme.colour("pitch").name()), "Link snapshot to hypothesis…")
        a.triggered.connect(lambda *_: self.link_snapshot())
        a = m.addAction("Export to LaTeX table")
        a.setEnabled(False)
        a.setToolTip("A future feature, with the LaTeX system")
        m.exec(pos)

    def snapshot_about(self) -> str:
        """How a snapshot reads in a hypothesis: "Lemma/Tag · Basic Imperatives · 155 lemmas"."""
        tab = self.tabs.currentIndex()
        parts = [self.tabs.tabText(tab)]
        if tab in (LEMMA_TAG, TAG_TAG):
            cfg = self.config_for(tab)
            parts.append(cfg.name or ("an unsaved matrix" if (cfg.x or cfg.y) else "a blank matrix"))
        e = self.lemmas.current_row()
        if tab == TAG_TAG and e is not None:
            parts.append(" ".join(x for x in (e.ref, self.doc.db.lemma(e)) if x))
        elif tab == ALL_DATA:
            parts.append(f"{len(self.all_table.visible_rows())} tokens")
        else:
            parts.append(f"{len(self.lemmas.visible_rows())} lemmas")
        n = self.lemmas.active_filters() + self.all_table.active_filters()
        if n or self.lemmas.proxy.pinned or self.lemma_search.text() or self.all_search.text():
            parts.append("filtered")
        return " · ".join(parts)

    def take_snapshot(self, animate: bool = True):
        """The camera: the setup as it is now, into today's Snapshots (one undo step), with a box
        shrinking into the Snapshots button (Josh, 24 October). Returns (session, snapshot)."""
        import datetime as _dt
        self._save_view()
        view, about = self.view_state(), self.snapshot_about()
        day, clock = self.work_date() or today(), _dt.datetime.now().strftime("%H:%M")
        out = self.doc.change_snapshots(
            "Take snapshot", lambda: nbmod.take_snapshot(self.doc.notebook, day, view, about, clock),
            (day, nbmod.snapshot_line(nbmod.Snapshot("", about or "Snapshot", {}, day, clock))))
        if animate:
            self._snapshot_flight()
        self.statusBar().showMessage(f"Snapshot taken: {about}  (View → Snapshots, Ctrl+Shift+P)", 6000)
        return out

    def _snapshot_flight(self):
        """The visual cue: an outline of the working window shrinking into the Snapshots button."""
        from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect
        from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect
        src, dst = getattr(self, "views", None), getattr(self, "snapshots_btn", None)
        if src is None or dst is None or not self.isVisible():
            return
        start = QRect(src.mapTo(self, src.rect().topLeft()), src.size())
        end = QRect(dst.mapTo(self, dst.rect().center()), dst.size() / 3)
        end.moveCenter(dst.mapTo(self, dst.rect().center()))
        box = QFrame(self)
        c = theme.colour("pitch")
        box.setStyleSheet(f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 40); "
                          f"border: 3px solid {c.name()}; border-radius: 6px;")
        box.setAttribute(Qt.WA_TransparentForMouseEvents)
        box.setGeometry(start)
        fade = QGraphicsOpacityEffect(box)
        box.setGraphicsEffect(fade)
        box.show()
        box.raise_()
        grow = QPropertyAnimation(box, b"geometry", box)
        grow.setDuration(450)
        grow.setStartValue(start)
        grow.setEndValue(end)
        grow.setEasingCurve(QEasingCurve.InCubic)
        dim = QPropertyAnimation(fade, b"opacity", box)
        dim.setDuration(450)
        dim.setStartValue(1.0)
        dim.setEndValue(0.35)
        group = QParallelAnimationGroup(box)
        group.addAnimation(grow)
        group.addAnimation(dim)
        group.finished.connect(box.deleteLater)
        self._flight = group
        group.start()

    def link_snapshot(self):
        """Link snapshot to hypothesis… (the camera's right-click, Matrix ▸): a snapshot is taken into
        the list, then linked by its id, the link keeping its own copy of the setup."""
        from .. import hypotheses as hy
        _, snap = self.take_snapshot()
        return self.link_to_hypothesis(hy.snapshot_link(snap.view, snap.name, target=snap.id, date=snap.taken))

    def link_listed_snapshot(self, snap, parent=None):
        """Link to hypothesis… from the Snapshots list."""
        from .. import hypotheses as hy
        return self.link_to_hypothesis(hy.snapshot_link(snap.view, snap.name, target=snap.id, date=snap.taken),
                                       parent)

    def _snapshots_changed(self):
        """Taken, renamed, pinned or deleted (or undone): the badge and the open lists follow."""
        self.update_badges()
        dlg = self.items_dialogs.get("snapshots")
        if dlg is not None and dlg.isVisible():
            dlg.refresh()
        self.refresh_notebook()
        if self.cogitate_window is not None and self.cogitate_window.isVisible():
            self.cogitate_window.refill()

    def restore_snapshot(self, view: dict):
        """A snapshot clicked: that view again in the main window."""
        self.configs.clear()
        missing = self.apply_view(view or {})
        self.refresh()
        self.raise_()
        self.activateWindow()
        self.statusBar().showMessage("Snapshot restored" + (": " + " and ".join(missing) + " no longer exist"
                                                             if missing else "."), 8000)
        return missing

    # ---- edit mode in the matrices (Ctrl+E, 21 October) --------------------------------------
    def toggle_matrix_edit(self):
        """Ctrl+E on Lemma/Tag or Tag/Tag: a click on a token's line edits it in its cell."""
        tab = self.tabs.currentIndex()
        if tab not in (LEMMA_TAG, TAG_TAG):
            return
        on = not self._view(tab).edit_mode
        for t in (LEMMA_TAG, TAG_TAG):            # one edit mode for both matrices
            self._view(t).set_edit_mode(on)
        for bar in (self.lt_bar, self.tt_bar):
            bar["edit_mode"].setVisible(on)
            bar["edit_btn"].setChecked(on)
            bar["edit_mode"].setStyleSheet(f"color: {theme.accent().name()}; font-weight: bold;")
        self.statusBar().showMessage("Edit mode: click a line of a token to edit it (Enter keeps, Esc drops, "
                                     "Tab goes to the next line); Ctrl+E again to stop." if on else
                                     "Edit mode off.", 6000)

    def _matrix_field_edited(self, e, t, key: str, text: str):
        """An edit made in a matrix cell: the token's field, one undo step (as in All data)."""
        if t not in e.tokens:
            return
        s = self.doc.db.settings
        name, _, lang = key.partition(":")
        f = s.token_field(name)
        if f is None:
            return
        if f.role == "pitch":
            from .. import pitch as pitchmod
            text = pitchmod.normalise(text)
        i = e.tokens.index(t)

        def change(x, i=i):
            x.tokens[i].set(name, text.strip(), (lang or s.primary_gloss) if f.multilingual else None,
                            f.multilingual)
        self.doc.edit_entry(e, change, f"Edit {f.title}" + (f" ({lang})" if lang else ""))

    # ---- the display conventions (idea 26): one switch for every cell view ------------------
    def conventions_button(self) -> QToolButton:
        """The /[β]/ button under a cell view: all the display conventions on or off at once."""
        from . import conventions
        b = QToolButton()
        b.setText("/[β]/")
        b.setProperty("icon_name", "conventions")
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)   # drawn as an icon, so it sits level with the others
        b.setIcon(self._conventions_icon())
        b.setIconSize(QSize(round(20 * 2.3), 20))
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setChecked(conventions.CURRENT.on)
        b.setToolTip("Display conventions on or off, in every cell view: Phonetic in [brackets], Phonemic "
                     "in /slashes/, glosses in capitals in small caps, translations in quotes (which ones: "
                     "Settings → Display). Display only: the data stays as typed")
        b.toggled.connect(self.set_conventions_on)
        if not hasattr(self, "_conv_buttons"):
            self._conv_buttons = []
        self._conv_buttons.append(b)
        return b

    def _conventions_icon(self) -> QIcon:
        """/[β]/ drawn in the text colour, 20 px high like the other buttons' icons."""
        from PySide6.QtGui import QPainter, QPixmap
        h, w = 20, round(20 * 2.3)
        pm = QPixmap(w * 2, h * 2)
        pm.setDevicePixelRatio(2.0)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        f = widgets.ipa_font(12)
        f.setPixelSize(15)
        p.setFont(f)
        p.setPen(theme.colour("window_text"))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "/[β]/")
        p.end()
        return QIcon(pm)

    def set_conventions_on(self, on: bool):
        from . import conventions
        c = conventions.Conventions(**{**conventions.CURRENT.__dict__, "on": bool(on)})
        conventions.save(self.prefs, c)
        self.conventions_changed()

    def conventions_changed(self):
        """Every cell view follows the display conventions as they are now."""
        from . import conventions
        alive = []
        for b in getattr(self, "_conv_buttons", []):
            try:
                b.blockSignals(True)
                b.setChecked(conventions.CURRENT.on)
                b.setIcon(self._conventions_icon())   # the theme's text colour
                b.blockSignals(False)
                alive.append(b)
            except RuntimeError:                  # a window that has gone
                pass
        self._conv_buttons = alive
        self.refresh()
        w = self.utterances_window
        if w is not None:
            w.texts.lines._relayout()
            w.show_cell()

    def count_label(self, tab) -> QLabel:
        """The line under a tab's options that says what it shows."""
        return {ALL_DATA: self.all_count, LEMMA_TAG: self.lt_bar["count"], TAG_TAG: self.tt_bar["count"]}[tab]

    TEXTS_ICON = 48

    def _elicit_button(self) -> QToolButton:
        """Beside the tabs, left of Texts and utterances: ɛλicit (Josh's cloud), with its menu.
        While recordings wait for review it shows the rain cloud."""
        from PySide6.QtWidgets import QMenu
        b = self.elicit_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setPopupMode(QToolButton.InstantPopup)
        b.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        m = self.elicit_menu = QMenu(b)
        self.elicit_make = m.addAction("Make ɛλicit request…", self.make_elicit_request)
        self.elicit_receive = m.addAction("Receive ɛλicitation…", self.receive_elicitation)
        self.elicit_review = m.addAction("Review waiting recordings…", self.review_elicitation)
        m.addSeparator()
        self.elicit_signout = m.addAction("Sign out of Google Drive", self.sign_out_google)
        self.elicit_signout.setVisible(False)          # shown while signed in (when the menu opens)
        m.aboutToShow.connect(lambda: self.elicit_signout.setVisible(bool(self.prefs.google_token)))
        b.setMenu(m)
        return b

    def refresh_elicit_icon(self):
        """The ɛλicit button's icon and tooltip: the rain cloud while recordings wait for review."""
        from .. import elicit
        try:
            waiting = elicit.waiting_reviews(self.doc.db) if self.doc.db.path else []
        except OSError:
            waiting = []
        n = sum(k for _, k in waiting)
        try:
            outstanding = elicit.outstanding_drive(self.doc.db) if self.doc.db.path else []
        except OSError:
            outstanding = []
        out = len(outstanding)
        ids = {st.request.id for st in outstanding}
        ready = [v for k, v in getattr(self, "elicit_drive_ready", {}).items() if k in ids]
        self.elicit_btn.setIcon(elicit_icon(self.TEXTS_ICON, waiting=bool(n or ready)))
        tip = (f"ɛλicit: {n} recording{'s' if n != 1 else ''} waiting for review" if n
               else "ɛλicit: remote elicitation")
        for speaker, k, why in ready:              # in Google Drive, ready to download (Receive ɛλicitation)
            tip += (f"\n{speaker}'s request: {why}; Receive ɛλicitation" if why else
                    f"\n{speaker} has finished: {k} recording{'s' if k != 1 else ''} in Google Drive "
                    "(Receive ɛλicitation)")
        if out:
            tip += (f"\n{out} request{'s' if out != 1 else ''} out through Google Drive "
                    "(Receive ɛλicitation checks them)")
        self.elicit_btn.setToolTip(tip)
        self.elicit_review.setVisible(bool(n))
        self.elicit_review.setText(f"Review waiting recordings ({n})…")

    def check_elicit_drive(self):
        """Look in Google Drive, in the background, for requests out that have finished (or were
        turned down), so the button rains without opening Receive ɛλicitation. Only when signed in,
        and quietly: a problem (offline, signed out) just leaves things as they are."""
        from .. import cloud_keys, elicit, gdrive
        db = self.doc.db
        token = self.prefs.google_token
        if self._elicit_checking or not db.path or not cloud_keys.google_ready() or not token.get("refresh_token"):
            return
        try:
            outstanding = elicit.outstanding_drive(db)
        except OSError:
            return
        if not outstanding:
            return
        import threading
        self._elicit_checking = True
        path = db.path

        def keep(tok):                            # a refreshed sign-in: stored by the main thread in
            self._elicit_new_token = tok          # _elicit_checked, never here (QSettings isn't
                                                  # thread-safe: the audit, 25 October)

        def work():
            found = {}
            try:
                drive = gdrive.Drive(token, on_token=keep)
                for st in outstanding:
                    try:                          # expired: nothing left readable by link (P2)
                        elicit.unshare_expired(drive, st)
                    except Exception:             # noqa: BLE001 (tried again in 10 minutes)
                        pass
                    state = elicit.drive_state(drive, st)
                    if state.finished or state.turned_down:
                        found[st.request.id] = (st.request.speaker["code"], state.uploaded,
                                                state.summary(st.request) if state.turned_down else "")
            except Exception:                     # noqa: BLE001 (checked again in 10 minutes)
                found = None
            self._elicit_signal.done.emit(path, found)   # queued to the main thread
        threading.Thread(target=work, daemon=True).start()

    def _elicit_checked(self, path, found):
        self._elicit_checking = False
        tok, self._elicit_new_token = getattr(self, "_elicit_new_token", None), None
        if tok is not None:                       # a sign-in refreshed in the background check
            self.prefs.google_token = tok
        if found is None or path != self.doc.db.path:
            return
        new = set(found) - set(self.elicit_drive_ready)
        self.elicit_drive_ready = found
        self.refresh_elicit_icon()
        if new:
            names = ", ".join(sorted({found[k][0] for k in new}))
            self.statusBar().showMessage(f"ɛλicit: {names} — recordings ready in Google Drive "
                                         "(Receive ɛλicitation).", 15000)

    # ɛλicit's next request, kept in the database's workspace (idea 36): the tokens selected for it
    # (right-click Add to ɛλicit request, or left selected), and its settings and new sentences
    @property
    def elicit_basket(self) -> list[str]:
        return self.doc.ws.get_list("elicit/basket")

    @elicit_basket.setter
    def elicit_basket(self, ids: list[str]):
        self.doc.ws_set("elicit/basket", list(ids) or None)

    @property
    def elicit_draft(self) -> dict:
        return self.doc.ws.get_dict("elicit/draft")

    @elicit_draft.setter
    def elicit_draft(self, draft: dict):
        self.doc.ws_set("elicit/draft", dict(draft) if draft else None)

    @property
    def spelling_ignored(self) -> set[str]:
        """Check spelling → Ignore: words left out of its list, kept in the workspace (idea 36)."""
        return set(self.doc.ws.get_list("spelling/ignored"))

    def ignore_spelling(self, word: str):
        self.doc.ws_set("spelling/ignored", sorted(self.spelling_ignored | {word.lower()}))

    def _elicit_preselect(self) -> list[str]:
        """The tokens added with the right-click Add to ɛλicit request (and those left selected when
        the request dialogue was last closed): selected to begin with in Make ɛλicit request."""
        return list(self.elicit_basket)

    def in_elicit_request(self, token) -> bool:
        return token is not None and token.id in self.elicit_basket

    def toggle_elicit(self, token):
        """Right-click → Add to ɛλicit request (or Remove from it): selected when Make ɛλicit
        request opens next."""
        if token is None:
            return
        basket = self.elicit_basket
        if token.id in basket:
            basket.remove(token.id)
            self.elicit_basket = basket
            msg = "Taken out of the ɛλicit request"
        else:
            self.elicit_basket = basket + [token.id]
            item = next((e for e, t in self.doc.db.all_tokens() if t is token), None)
            from .. import elicit
            kind = "a rerecord" if item is not None and elicit.recording_path(self.doc.db, item, token) else "new"
            msg = f"Added to the ɛλicit request as {kind}"
        n = len(self.elicit_basket)
        self.statusBar().showMessage(f"{msg} ({n} selected for Make ɛλicit request).", 5000)

    def add_citations_to_elicit(self, entries):
        """The lemma list's right-click (idea 64): the selected lemmas' citation tokens, selected for
        the next ɛλicit request."""
        self.add_to_elicit([t for e in entries if (t := next((x for x in e.tokens if x.is_citation), None))])

    def add_to_elicit(self, tokens):
        """Select these tokens for the next ɛλicit request (those already selected stay)."""
        basket = self.elicit_basket
        new = [t.id for t in tokens if t.id not in basket]
        self.elicit_basket = basket + new
        self.statusBar().showMessage(f"Added {len(new)} token(s) to the ɛλicit request "
                                     f"({len(self.elicit_basket)} selected for Make ɛλicit request).", 6000)
        return len(new)

    def elicit_menu_item(self, token):
        """The right-click item for a token or an utterance (All data, the matrices, Utterances)."""
        on = self.in_elicit_request(token)
        return ("Remove from ɛλicit request" if on else "Add to ɛλicit request",
                elicit_icon(16), lambda t=token: self.toggle_elicit(t), token is not None)

    def _selected_token_obj(self):
        sel = self.selected_token()
        return sel[0].tokens[sel[1]] if sel else None

    def make_elicit_request(self):
        from .elicit_dialogs import RequestDialog
        db = self.doc.db
        if not db.path:
            QMessageBox.information(self, "Make ɛλicit request", "Save the database first.")
            return
        if not db.metadata.participants:
            QMessageBox.information(self, "Make ɛλicit request", "A request goes to a participant: add the "
                                    "speaker to the participants first (Edit → Lists → Participants).")
            return
        RequestDialog(self, self._elicit_preselect(), draft=self.elicit_draft).exec()

    def receive_elicitation(self):
        from .elicit_dialogs import choose_and_receive
        choose_and_receive(self)

    def sign_out_google(self):
        from .elicit_dialogs import sign_out_google
        sign_out_google(self)

    def review_elicitation(self):
        from .elicit_dialogs import review_waiting
        review_waiting(self)

    def _xml_button(self) -> QToolButton:
        """Beside the tabs, between ɛλicit and Texts and utterances: the XML viewer (Josh's χμλ)."""
        b = self.xml_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("XML viewer: the database file, read-only, at the selected token or lemma")
        b.clicked.connect(lambda *_: self.open_xml_viewer())
        return b

    def _cogitate_button(self) -> QToolButton:
        """Beside the tabs, between the XML viewer and Questions: Cogitate, the hypotheses (Josh's icon)."""
        b = self.cogitate_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("Cogitate: hypotheses, with their evidence and counterevidence")
        b.clicked.connect(lambda *_: self.open_cogitate())
        return b

    # ---- Cogitate: hypotheses (IDEAS.md idea 35) -----------------------------------------
    def open_cogitate(self, hypothesis_id: str | None = None, focus_summary: bool = False):
        """View → Cogitate: the List, or one hypothesis in the Hypothesis tab."""
        from .cogitate import CogitateWindow
        w = self._window("cogitate_window", CogitateWindow)
        w.show()
        w.refill()
        if hypothesis_id is not None:
            w.show_hypothesis(hypothesis_id, focus_summary)
        bring_forward(w)
        return w

    def link_to_hypothesis(self, link, parent=None):
        """Link to hypothesis…: the picker, then the link made (one undo step); Make a new
        hypothesis… makes one with this link and opens it. Returns the hypothesis, or None."""
        from .. import hypotheses as hy
        from .cogitate import LinkPicker
        dlg = LinkPicker(self, link, parent)
        if not dlg.exec() or dlg.choice is None:
            return None
        book, date = self.doc.notebook, self.work_date()
        if dlg.choice == LinkPicker.MAKE:
            h = self.doc.change_hypotheses(        # made with its link: one undo step
                "Make hypothesis", lambda j: hy.make(book, j, date, links=[link], db=self.doc.db))
            self.open_cogitate(h.id, focus_summary=True)
            return hy.by_id(book, h.id)
        h = hy.by_id(book, dlg.choice)
        if h is None:
            return None
        self.doc.change_hypotheses(f"Link to {h.label}", lambda j: hy.add_link(book, j, date, h, link, self.doc.db))
        self.statusBar().showMessage(f"Linked to {h.title()} as {link.mark}", 6000)
        self.refresh_notebook()
        return h

    def question_to_hypothesis(self, session, q):
        """Convert to hypothesis (Josh, 22 October; IDEAS.md idea 35, Later): a new hypothesis whose
        summary is the question as written (confidence: the first level), linked to the question as
        Relevant (one undo step); the question stays in Questions, resolved. Cogitate opens on the
        new hypothesis with the cursor in Formulation. Returns the hypothesis."""
        from .. import hypotheses as hy
        if q is None or session is None:
            return None
        link = hy.question_link(session, q)          # gives the question an id, if it had none
        book, date = self.doc.notebook, self.work_date()
        # the hypothesis and the question's resolving are one undo step (Undo left the question
        # resolved before: the audit, 25 October)
        from .document import ItemStateCommand
        self.doc.undo.beginMacro("Convert to hypothesis")
        h = self.doc.change_hypotheses(
            "Convert to hypothesis",
            lambda j: hy.make(book, j, date, summary=q.text, links=[link], db=self.doc.db))
        if not q.resolved:
            before = (q.resolved, q.pinned)
            q.set_resolved(today())
            self.doc.undo.push(ItemStateCommand(self.doc, "Resolve the question", q, before, (q.resolved, q.pinned)))
        self.doc.undo.endMacro()
        self.doc.notebook_changed()
        self.refresh_notebook()
        w = self.open_cogitate(h.id)
        w.formulation.setFocus()
        self.statusBar().showMessage(f"{h.label} made from the question, which is now resolved", 6000)
        return hy.by_id(book, h.id)

    def link_token_to_hypothesis(self, entry=None, index=None, parent=None):
        """A token or an utterance (the selected one, if none is given) to a hypothesis."""
        from .. import hypotheses as hy
        if entry is None:
            sel = self.selected_token()
            if sel is None:
                return None
            entry, index = sel
        if index is None or not (0 <= index < len(entry.tokens)):
            index = 0 if entry.tokens else None
        t = entry.tokens[index] if index is not None else None
        if t is None:
            return None
        return self.link_to_hypothesis(hy.token_link(self.doc.db, entry, t), parent)

    def hypothesis_menu_item(self, enabled: bool = True, fn=None):
        """The right-click item: Link to hypothesis… (Josh's Cogitate icon)."""
        return ("Link to hypothesis…", icon("cogitate", 16, theme.colour("pitch").name()),
                fn or (lambda: self.link_token_to_hypothesis()), enabled)

    def _questions_button(self) -> QToolButton:
        """Beside the tabs, between the XML viewer and Texts and utterances: View → Questions (Josh's ?)."""
        b = self.questions_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("Questions: every question in the notebook (Ctrl+Shift+Q)")
        b.clicked.connect(lambda *_: self.open_questions())
        self._add_badge("questions", b)
        return b

    def _snapshots_button(self) -> QToolButton:
        """Between the ? and the To Do flag: View → Snapshots (Josh's icon, 24 October)."""
        b = self.snapshots_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("Snapshots: every snapshot in the notebook (Ctrl+Shift+P). The camera under the "
                     "working window takes one.")
        b.clicked.connect(lambda *_: self.open_snapshots())
        self._add_badge("snapshots", b)
        return b

    def _todo_button(self) -> QToolButton:
        """Beside the ?: View → To Do (Josh's checkmarks, 48 px; 21 October, icon 22 October)."""
        b = self.todo_btn = QToolButton()
        b.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("To Do: every to do in the notebook (Ctrl+Shift+T)")
        b.clicked.connect(lambda *_: self.open_todos())
        # The badge: the number of open to dos, top right, in the theme colour (Josh, 22 October)
        self.todo_badge = self._add_badge("todo", b)
        return b

    def _add_badge(self, key: str, button) -> QLabel:
        """A badge at a button's top right (Questions, Snapshots, To Do; Josh, 22 and 24 October)."""
        if not hasattr(self, "badges"):
            self.badges = {}
        lbl = QLabel(button)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        lbl.hide()
        button.installEventFilter(self)
        self.badges[key] = (button, lbl)
        return lbl

    def badge_counts(self) -> dict:
        """What each badge counts: open questions, open To Dos, the snapshots taken today."""
        book = getattr(self.doc, "notebook", None)
        if book is None:
            return {"questions": 0, "todo": 0, "snapshots": 0}
        day = self.work_date() if hasattr(self, "sess_nodate") else today()
        s = book.session(day)
        return {"questions": sum(1 for _, q in book.all_items(nbmod.QUESTION) if q.is_open),
                "todo": sum(1 for _, q in book.all_items(nbmod.TODO) if q.is_open),
                "snapshots": len(s.snapshots) if s is not None else 0}

    def update_todo_badge(self):
        """Every badge (the name is older: the To Do badge came first)."""
        self.update_badges()

    def update_badges(self):
        """The app bar's badges: just the number, none when it is 0 or the badge is switched off
        in Settings → Display (each on its own, this computer)."""
        from .dialogs import BADGE_QUESTIONS, BADGE_SNAPSHOTS, BADGE_TODO
        keys = {"questions": BADGE_QUESTIONS, "todo": BADGE_TODO, "snapshots": BADGE_SNAPSHOTS}
        counts = self.badge_counts()
        for name, (button, badge) in getattr(self, "badges", {}).items():
            n = counts.get(name, 0)
            if n == 0 or not self.prefs.get_bool(keys[name], True):
                badge.hide()
                continue
            self._style_badge(button, badge, n)

    def _style_badge(self, button, badge, n: int):
        badge.setText(str(n) if n < 100 else "99+")
        f = badge.font()
        f.setBold(True)
        f.setPixelSize(11)
        badge.setFont(f)
        h = 17
        w = max(h, badge.fontMetrics().horizontalAdvance(badge.text()) + 8)
        badge.setFixedSize(w, h)
        badge.setStyleSheet(f"background: {theme.colour('pitch').name()}; color: white; "
                            f"border-radius: {h // 2}px; padding: 0px;")
        badge.move(max(0, button.width() - badge.width() - 1), 1)
        badge.show()
        badge.raise_()

    def _place_todo_badge(self):
        for button, badge in getattr(self, "badges", {}).values():
            badge.move(max(0, button.width() - badge.width() - 1), 1)

    def xml_target(self):
        """Where the XML viewer opens: the selected token (All data or a matrix cell), else the lemma
        list's lemma, as ("token" | "entry", id); None for the beginning."""
        hit = self.selected_token()
        if hit is not None:
            e, i = hit
            if 0 <= i < len(e.tokens):
                return "token", e.tokens[i].id
        e = self.lemmas.current_row()
        return ("entry", e.id) if e is not None else None

    def open_whiteboard(self):
        """Tools → Whiteboard (idea 45): a cheap drawing tool, kept in the workspace until wiped."""
        from .whiteboard import WhiteboardWindow
        w = self._window("whiteboard_window", WhiteboardWindow)
        bring_forward(w)
        return w

    def open_xml_viewer(self, target=None):
        """View → XML viewer: the database file, read-only, at the selected token or lemma, or at
        target: ("utterance" or "text", id), from Texts and utterances' options panel."""
        from .xml_viewer import XmlViewerWindow
        w = self._window("xml_window", XmlViewerWindow)
        w.refresh(keep_place=False)
        w.go_to(target or self.xml_target())
        bring_forward(w)
        return w

    def _texts_button(self) -> QToolButton:
        """Beside the tabs: the button that opens Texts and utterances (Josh's icon)."""
        self.texts_btn = QToolButton()
        self.texts_btn.setIconSize(QSize(self.TEXTS_ICON, self.TEXTS_ICON))
        self.texts_btn.setAutoRaise(True)
        self.texts_btn.setCursor(Qt.PointingHandCursor)
        self.texts_btn.setToolTip("Texts and utterances (Ctrl+U)")
        self.texts_btn.clicked.connect(lambda *_: self.open_utterances())
        return self.texts_btn

    def _scratch_panel(self) -> QWidget:
        """The phonetics scratchpad (Josh, 22 October; named 24 October): α and β, with the Pitch and Segments tabs (IDEAS.md
        ideas 33 and 46), as under a text's lines, for every tab of the Matrix, against Current
        Session. Nothing typed is saved: they're empty each time Lemmatrix opens."""
        from .scratchpad import PhoneticsScratchpad
        panel, pl = self._bar()
        s = self.doc.db.settings
        self.comparison = PhoneticsScratchpad(self, s.pitch_low, s.pitch_high,
                                         "Pitch scratchpad: type a pitch trace to see and hear it (Enter, or "
                                         "click its letter). Nothing is saved")
        self.scratchpad = self.comparison.alpha
        pl.addWidget(self.comparison, 1)          # all the panel's height: γ comes when it's tall (idea 46)
        panel.setFixedWidth(280)
        return panel

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

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        self.sess_rows = {}
        for r, (kind, title) in enumerate(((chips.RESEARCHERS, "Researchers"),
                                           (chips.PARTICIPANTS, "Participants"),
                                           (chips.LOCATIONS, "Locations"))):
            row = chips.ChipRow(kind, lambda: self.doc.db, compact=True, edit_list=self.edit_lists,
                                codes=True)       # places by their codes, like the people (21 October)
            row.changed.connect(self._session_people_changed)
            row.rebuilt.connect(lambda: QTimer.singleShot(0, self._fit_session))
            self.sess_rows[kind] = row
            lbl = QLabel(title)
            grid.addWidget(lbl, r, 0, Qt.AlignTop | Qt.AlignLeft)
            grid.addWidget(row, r, 1)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        sl.addLayout(grid)
        self.sess_date = QDateEdit(QDate.currentDate())
        self.sess_date.setDisplayFormat("yyyy-MM-dd")
        self.sess_date.setCalendarPopup(True)
        self.sess_date.setMaximumDate(QDate.currentDate())
        self._today = QDate.currentDate()
        self._day_timer = QTimer(self)            # past midnight, the session moves on to the new day
        self._day_timer.timeout.connect(self._check_new_day)
        self._day_timer.start(60_000)
        self.sess_date.setToolTip("The session's date: for new tokens and recordings, for comments, "
                                  "and the notebook's day. Resets to today each time Lemmatrix opens; "
                                  "it can't be a day that hasn't come yet.")
        self.sess_date.dateChanged.connect(lambda *_: self._session_date_changed())
        self.sess_nodate = QPushButton("No date")
        self.sess_nodate.setCheckable(True)
        self.sess_nodate.toggled.connect(self.sess_date.setDisabled)
        self.sess_nodate.toggled.connect(lambda *_: self._session_date_changed())
        dr = QHBoxLayout()                        # in the chips' column, under them
        dr.setContentsMargins(0, 0, 0, 0)
        dr.addWidget(self.sess_date)
        dr.addWidget(self.sess_nodate)
        dr.addStretch(1)
        grid.addWidget(QLabel("Date"), 3, 0, Qt.AlignVCenter | Qt.AlignLeft)
        grid.addLayout(dr, 3, 1)
        sl.addStretch(1)
        self.sess_panel, self._sess_head, self._sess_grid, self._sess_date_row = panel, head, grid, dr
        return panel

    SESSION_MAX = 0.33       # Current Session grows leftward up to a third of the matrix pane's width

    def _fit_session(self):
        """Current Session is as narrow as its contents (Josh, 21 October): it grows leftward as chips
        are added, up to a third of the matrix pane's width; past that the chips wrap onto more lines."""
        panel = getattr(self, "sess_panel", None)
        if panel is None:
            return
        g = self._sess_grid
        labels = max(g.itemAtPosition(r, 0).widget().sizeHint().width() for r in range(4))
        content = max([row.natural_width() for row in self.sess_rows.values()]
                      + [self._sess_date_row.sizeHint().width()])
        m = panel.layout().contentsMargins()
        frame = 2 * panel.frameWidth() + m.left() + m.right()
        need = max(self._sess_head.sizeHint().width(), labels + g.horizontalSpacing() + content) + frame
        cap = max(self._sess_head.sizeHint().width() + frame, int(self.right_split.width() * self.SESSION_MAX))
        w = min(need, cap)
        if panel.width() != w or panel.minimumWidth() != w:
            panel.setFixedWidth(w)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "right_split", None) and event.type() == QEvent.Resize:
            self._fit_session()
        if event.type() == QEvent.Resize and any(obj is b for b, _ in getattr(self, "badges", {}).values()):
            self._place_todo_badge()
        return super().eventFilter(obj, event)

    def _build_menus(self):
        mb = self.menuBar()
        self.save_btn = QToolButton()               # top left, after the title: a floppy in the theme colour
        self.save_btn.setToolTip("Save database (Ctrl+S)")   # icon only: the name is in the tooltip
        self.save_btn.setIconSize(QSize(20, 20))
        self.save_btn.setAutoRaise(True)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(lambda *_: self.save())
        corner = self._corner = QWidget()      # kept: PySide does not take ownership of it
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 2, 2, 2)
        cl.setSpacing(4)
        self.db_title = DbTitle(self.edit_metadata)   # language - variety - database name
        cl.addWidget(self.db_title)
        cl.addWidget(self.save_btn)
        mb.setCornerWidget(corner, Qt.TopLeftCorner)        # away from the window's close button
        self.theme_btn = QToolButton()              # top right: switch between the light and dark themes
        self.theme_btn.setIconSize(QSize(22, 22))
        self.theme_btn.setAutoRaise(True)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(lambda *_: self.toggle_theme())
        mb.setCornerWidget(self.theme_btn, Qt.TopRightCorner)
        f = mb.addMenu("&File")
        self._act(f, "&New database…", self.new_file, QKeySequence.New)
        self._act(f, "&Open…", self.open_file, QKeySequence.Open)
        self.recent_menu = f.addMenu("Open &recent")       # idea 51 (Josh, 23 October)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        f.addSeparator()
        self._act(f, "&Save", self.save, QKeySequence.Save)
        self._act(f, "&Rename database…", self.rename_database)
        self.folder_menu = f.addMenu("Open &folder")        # the main folder and every subfolder (22 October)
        self.folder_menu.aboutToShow.connect(self._fill_folder_menu)
        f.addSeparator()
        self._act(f, "&Full backup…", self.full_backup)
        ex = f.addMenu("&Export")
        self._act(ex, "&Filtered database (current tab) as CSV…", lambda: self.export_csv(filtered=True))
        self._act(ex, "&Entire database as CSV…", lambda: self.export_csv(filtered=False))
        self._act(ex, "&Tag structure as CSV…", lambda: self.export_csv(filtered=False, tags=True))
        self._act(ex, "&Wordlist (EACW, CAWL, Swadesh)…", self.export_wordlist)   # idea 40
        ex.addSeparator()
        # two archives (idea 44): data to share, never the notebook's ideas unless asked
        self._act(ex, "&Anonymous archive…", lambda: self.export_archive("anonymous"))
        self._act(ex, "Et&hical archive…", lambda: self.export_archive("ethical"))
        f.addSeparator()
        # Settings in File, as in Office, with the gear and Ctrl+, (Josh, 22 October; Edit before)
        self.settings_action = self._act(f, "&Settings…", self.edit_settings, "Ctrl+,")
        self.settings_action.setIcon(icon("gear", 16))
        self.settings_action.setIconVisibleInMenu(True)
        self.settings_action.setMenuRole(QAction.PreferencesRole)   # the Lemmatrix menu on a Mac
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
        self._act(e, "&Bulk edit…", self.open_bulk_edit, "Ctrl+Shift+B")   # Ctrl+E is edit mode (21 October)
        e.addSeparator()
        self._act(e, "&Write to notebook", self.write_notebook)   # the session panel's pencil (22 October)
        t = mb.addMenu("&Tools")                       # grouped (Josh, 23 October): audits first
        t.addSection("Audits")                          # look first, change only when confirmed
        self._act(t, "Check for duplicate file names", self.check_duplicates)
        self._act(t, "Find missing or unlinked recordings…", self.find_missing_recordings)
        self._act(t, "Check clipped utterances…", self.check_clipped)
        self._act(t, "Check reference order…", self.check_reference_order)     # 23 October
        self._act(t, "Check wordlist integrity…", self.check_wordlist_integrity)   # idea 66, 24 October
        self._act(t, "Check &spelling…", self.check_spelling, "F7")
        self._act(t, "Give every lemma its citation token…", self.give_citation_tokens)   # idea 64
        self._act(t, "Copy citation forms to empty lemmas…", self.copy_citation_forms)   # idea 67
        t.addSection("Soundfiles")
        self._act(t, "Update all soundfile names", self.update_all_names)
        self._act(t, "Fill in recording dates from the soundfiles…", self.fill_recording_dates)
        t.addSection("Wordlists")
        self._act(t, "Link to wordlists…", self.link_wordlists)                 # idea 40
        self._act(t, "Insert EACW items…", lambda *_: self.insert_eacw_items())  # idea 40, 23 October
        self._act(t, "Convert references from a table…", self.convert_references)
        t.addSeparator()
        t.addMenu(self.elicit_menu)                    # the ɛλicit button's own menu (22 October)
        self.elicit_menu.setTitle("ɛλicit")
        t.addSeparator()
        self._act(t, "&Whiteboard", lambda *_: self.open_whiteboard(), "Ctrl+Shift+W")   # an Easter egg: no button
        v = mb.addMenu("&View")
        self._act(v, "&Notebook", self.open_notebook, "Ctrl+B")
        self._act(v, "&Questions", self.open_questions, "Ctrl+Shift+Q")
        self._act(v, "To &Do", self.open_todos, "Ctrl+Shift+T")
        self._act(v, "&Snapshots", self.open_snapshots, "Ctrl+Shift+P")      # Josh, 24 October
        self._act(v, "&Texts and utterances", lambda *_: self.open_utterances(), "Ctrl+U")
        self._act(v, "&XML viewer", lambda *_: self.open_xml_viewer())
        self._act(v, "&Cogitate (hypotheses)", lambda *_: self.open_cogitate())
        v.addSeparator()
        self._build_matrix_menu(v.addMenu("&Matrix"))
        # Settings → Pitch → Hide the pitch system, here too (idea 9; no shortcut). Selected hides it
        # (Josh, 26 October: Hide, as in Settings; it was Show pitch system)
        self.pitch_view_action = self._act(v, "Hide &pitch system", lambda *_: self.set_pitch_shown(
            not self.pitch_view_action.isChecked()))
        self.pitch_view_action.setCheckable(True)
        self.pitch_view_action.setChecked(False)
        self._act(v, "Hide or show the working panels", self.toggle_panels)
        # the same keys as in the token dialogue
        self.play_action = self._act(None, "Play the selected token", self.play_selected, "Ctrl+Space")
        self.play_pitch_action = self._act(None, "Play the selected token's pitch", self.play_selected_pitch,
                                           "Ctrl+Shift+Space")
        self._act(None, "Open the selected token in Praat", self.open_selected_in_praat, "Ctrl+Alt+Space")
        self._act(None, "Record the selected token", self.record_selected, "Ctrl+R")
        a = mb.addMenu("&Analyze")
        x = a.addAction("Analysis tools arrive in version 2 (Analyze)")
        x.setEnabled(False)
        c = mb.addMenu("&Compose")
        x = c.addAction("Writing-up tools arrive in version 3 (Compose): LaTeX and Word export, papers")
        x.setEnabled(False)
        h = mb.addMenu("&Help")
        self.tick_action = self._act(h, "I found a tick!", lambda: self.send_report("bug"))
        self.tick_action.setIcon(themed_icon("tick", 16))
        self.tick_action.setToolTip("Report a bug: an email to " + report.SUPPORT_EMAIL)
        self._act(h, "Request a feature", lambda: self.send_report("feature"))
        h.addSeparator()
        self._act(h, "&Keyboard shortcuts…", self.show_shortcuts)
        sm = h.addMenu("&Sample databases")                 # moved from File (22 October); a walkthrough later
        self._act(sm, "Open a copy of the sample database", self.open_sample)
        self._act(sm, "Open a copy of the ɛλicit test database", self.open_elicit_test)
        h.addSeparator()
        self._act(h, "About Lemmatrix", self.about)

    # ---- View → Matrix and File → Open folder (22 October) ---------------------------------
    def _build_matrix_menu(self, m):
        """The matrix options' buttons as menu items, for the tab shown (Lemma/Tag or Tag/Tag)."""
        tab = lambda: self.tabs.currentIndex()                         # noqa: E731
        items = [self._act(m, "Configure &cell…", lambda: self.configure_cell(tab())),
                 self._act(m, "Configure &matrix…", lambda: self.configure_matrix(tab()))]
        m.addSeparator()
        items += [self._act(m, "&Save matrix…", lambda: self.save_matrix(tab())),
                  self._act(m, "&Rename matrix…", lambda: self.rename_matrix(tab())),
                  self._act(m, "&Delete matrix…", lambda: self.delete_saved_matrix(tab())),
                  self._act(m, "C&lear matrix", lambda: self.clear_matrix(tab()))]
        m.addSeparator()
        self.matrix_edit_action = self._act(m, "&Edit mode", self.toggle_matrix_edit, "Ctrl+E")
        self.matrix_edit_action.setCheckable(True)
        items += [self.matrix_edit_action,
                  self._act(m, "S&wap rows and columns", lambda: self.switch_axes(tab()), "Ctrl+T")]
        m.addSeparator()
        self._act(m, "Take sna&pshot", self.take_snapshot)                   # every tab (24 October)
        self._act(m, "Link snapshot to &hypothesis…", self.link_snapshot)

        def update(*_):
            on = tab() in (LEMMA_TAG, TAG_TAG)
            for a in items:
                a.setEnabled(on)
            self.matrix_edit_action.setChecked(on and self._view(tab()).edit_mode)
        m.aboutToShow.connect(update)
        self.tabs.currentChanged.connect(update)       # so Ctrl+E and Ctrl+T work on the matrices only
        update()

    FOLDERS = (("Main folder", ()), None,
               ("Soundfiles", (layout.SOUNDFILES,)),
               ("Soundfiles › Tokens", (layout.SOUNDFILES, layout.TOKENS)),
               ("Soundfiles › Utterances", (layout.SOUNDFILES, layout.UTTERANCES)),
               ("Soundfiles › Texts", (layout.SOUNDFILES, layout.TEXTS)),
               ("Soundfiles › Segments", (layout.SOUNDFILES, layout.SEGMENTS)),
               ("Soundfiles › _Deleted recordings", (layout.SOUNDFILES, layout.HELD)), None,
               ("Backups", (layout.BACKUPS,)), ("Documentation", (layout.DOCUMENTATION,)),
               ("Images", (layout.IMAGES,)), ("Elicit", ("Elicit",)), ("Exports", (layout.EXPORTS,)),
               ("Whiteboard", (layout.WHITEBOARD,)))
    MADE_ON_DEMAND = {layout.HELD, layout.BACKUPS, "Elicit", layout.WHITEBOARD}   # made by Lemmatrix when needed

    def _fill_folder_menu(self):
        m = self.folder_menu
        m.clear()
        path = self.doc.db.path
        if not path:
            a = m.addAction("Save the database first")
            a.setEnabled(False)
            return
        main = layout.main_folder(path)
        for item in self.FOLDERS:
            if item is None:
                m.addSeparator()
                continue
            label, parts = item
            folder = main.joinpath(*parts)
            a = m.addAction(label)
            if parts and parts[-1] in self.MADE_ON_DEMAND and not folder.is_dir():
                a.setEnabled(False)
                a.setText(label + " (not made yet)")
                continue
            a.setToolTip(str(folder))
            a.triggered.connect(lambda *_, folder=folder: self.open_folder(folder))

    def open_folder(self, folder: Path):
        """File → Open folder: a folder of the database's main folder in the file manager (made if missing)."""
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---- Help → Keyboard shortcuts (22 October) --------------------------------------------
    OTHER_SHORTCUTS = (
        ("All data and the matrices", (("Space, Ctrl+Space", "Play the selected token"),
                                       ("Ctrl+Shift+Space", "Play its pitch"),
                                       ("Ctrl+Alt+Space", "Open it in Praat"),
                                       ("Ctrl+R", "Open it and record"), ("Enter", "Open the token dialogue"),
                                       ("Delete", "Delete the selected token"),
                                       ("Ctrl + mouse wheel, Ctrl+0", "Zoom a matrix, and back"),
                                       ("Shift + mouse wheel", "Scroll sideways"),
                                       ("Ctrl+click, Shift+click, Ctrl+A", "Select several lemmas"),
                                       ("Alt+click a lemma", "Show only that lemma"))),
        ("Token and utterance dialogues", (("Ctrl+R", "Record / stop"), ("Ctrl+Space", "Play"),
                                           ("Ctrl+Shift+Space", "Play the pitch"),
                                           ("Ctrl+Alt+Space", "Open the recording in Praat"),
                                           ("Alt+← / Alt+→", "Back / Next"),
                                           ("→", "Accept the predicted translation"),
                                           ("Ctrl+click a tag", "More than one tag in a group"))),
        ("A text's lines", (("Ctrl+E", "Edit mode"), ("Ctrl+S", "Save this text's TextGrid"),
                            ("Ctrl+Space, Space", "Play the line"),
                            ("Ctrl+Alt+Space", "Open it in Praat (Utterances: the utterance)"),
                            ("Ctrl+G", "Go to the bookmark"),
                            ("Ctrl+Shift+Space", "Play the pitch scratchpad"),
                            ("Tab, Shift+Tab, ↑, ↓", "Move between fields (edit mode)"),
                            ("Ctrl + mouse wheel, Ctrl+0", "Zoom, and back"))),
        ("The phonetics scratchpad (α, β)", (("Right Shift+A", "Play α"), ("Right Shift+B", "Play β"),
                                        ("Click α or β", "Play it"), ("Enter in a pad", "Play it"))),
        ("Cogitate and the XML viewer", (("Alt+← / Alt+→", "Back / Next hypothesis"),
                                         ("Ctrl+F", "XML viewer: the search"),
                                         ("Enter, Shift+Enter, F3", "Next / previous match"))),
        ("The whiteboard", (("Mouse wheel", "The size of the marker or eraser"),
                            ("Ctrl+Z, Ctrl+Y", "Undo / redo a stroke"),
                            ("Ctrl+S", "Save as PNG in the Whiteboard folder"),
                            ("Ctrl+C", "Copy the drawing"),
                            ("Double-click the eraser", "Wipe the board"))))

    def shortcut_rows(self) -> list[tuple[str, list[tuple[str, str]]]]:
        """Every shortcut: the menus' (read from the menus themselves), then the others."""
        out = []
        for top in self.menuBar().actions():
            menu = top.menu()
            if menu is None:
                continue
            rows = []

            def walk(m, prefix):
                for a in m.actions():
                    if a.menu() is not None:
                        walk(a.menu(), prefix + a.text().replace("&", "") + " › ")
                    elif not a.isSeparator() and not a.shortcut().isEmpty():
                        rows.append((a.shortcut().toString(QKeySequence.NativeText),
                                     prefix + a.text().replace("&", "").split("\t")[0]))
            walk(menu, top.text().replace("&", "") + " › ")
            if rows:
                out.append((top.text().replace("&", ""), rows))
        out.append(("Main window", [(a.shortcut().toString(QKeySequence.NativeText), a.text())
                                    for a in self.actions() if not a.shortcut().isEmpty()]))
        out += [(t, list(r)) for t, r in self.OTHER_SHORTCUTS]
        from .. import pitchview                  # the pitch system hidden: its keys do nothing (idea 9)
        if not pitchview.shown():
            out = [(t, [(k, d) for k, d in rows if "Ctrl+Shift+Space" not in k
                        and "pitch" not in d.lower()]) for t, rows in out]   # α and β still play segments
            out = [(t, rows) for t, rows in out if rows]
        return out

    def show_shortcuts(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard shortcuts")
        lay = QVBoxLayout(dlg)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Keys", "Does"])
        tree.setRootIsDecorated(False)
        for title, rows in self.shortcut_rows():
            head = QTreeWidgetItem([title, ""])
            f = head.font(0)
            f.setBold(True)
            head.setFont(0, f)
            head.setForeground(0, theme.accent())
            head.setFlags(Qt.ItemIsEnabled)
            tree.addTopLevelItem(head)
            for keys, does in rows:
                tree.addTopLevelItem(QTreeWidgetItem([keys, does]))
        tree.resizeColumnToContents(0)
        lay.addWidget(tree)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(620, 620)
        dlg.exec()

    def send_report(self, kind: str):
        """I found a tick! (kind "bug") or Request a feature: opens an email to the support address."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        attached = self._setup_for_report(kind)
        if attached is False:
            return                                # Cancel
        url = report.mailto(kind, attached.name if attached else "")
        if not QDesktopServices.openUrl(QUrl(url, QUrl.TolerantMode)):
            QMessageBox.information(self, "Email", "No email program opened. Please write to "
                                    f"{report.SUPPORT_EMAIL}.")

    def _setup_for_report(self, kind: str):
        """Offer to send the database's setup with the email (IDEAS.md idea 50, Josh, 24 October):
        fields, lists, tags, categories and settings, no data at all. Returns the file made, None
        (just the email) or False (Cancel)."""
        db = self.doc.db
        if not db.path:
            return None
        from .. import layout, setup_export
        box = QMessageBox(self)
        box.setWindowTitle("I found a tick!" if kind == "bug" else "Request a feature")
        box.setText("Would you like to send your database's setup with the email?")
        box.setInformativeText(
            "It shows the developer how your database is set up: its fields and their lists, the tag "
            "structure, the reference categories and the settings. It holds no data at all: no lemmas, "
            "tokens, texts or recordings, no people and no places, and the language and variety only as "
            "LXX and VXX.\n\nNothing in your database changes: the setup is a copy, saved in your "
            "Exports folder. The email can't attach it by itself, so the folder opens for you to drag "
            "the file into the email.")
        make = box.addButton("Make the setup file", QMessageBox.AcceptRole)
        plain = box.addButton("Just the email", QMessageBox.ActionRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(plain)
        box.exec()
        if box.clickedButton() is plain:
            return None
        if box.clickedButton() is not make:
            return False
        try:
            path = setup_export.write(db, layout.exports_folder(db.path))
        except OSError as exc:
            QMessageBox.warning(self, "Setup", f"The setup couldn't be written: {exc}")
            return None
        self.open_folder(path.parent)
        self.statusBar().showMessage(f"Setup saved as {path.name} in Exports: drag it into the email.", 8000)
        return path

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(lambda *_: fn())   # never Qt's checked flag as fn's first argument
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
        from .. import wordlists
        # the wordlists' numbers are hidden (idea 40): only in the Reference's hover (and the XML)
        cols = [Column("ref", "Reference", lambda e: e.ref,          # with the peek (23 October)
                       tooltip=lambda e: wordlists.peek(db, e) or None)]
        from .dialogs import origin_shown
        shown = origin_shown(self)                # Settings → General: Stem type and From
        for f in s.entry_fields:
            if f.role == "stem-type" and not shown:
                continue
            if f.multilingual:
                for lang in s.gloss_languages:
                    cols.append(Column(f"{f.name}:{lang}", f"{f.title} ({lang})" if len(s.gloss_languages) > 1
                                       else f.title, lambda e, n=f.name, l=lang: e.get(n, l), edit=edit))
            else:
                cols.append(Column(f.name, f.title, lambda e, n=f.name: e.get(n), closed=f.closed,
                                   tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                                   ipa=f.role == "lemma", edit=edit))
            if f.role == "stem-type":             # From, beside Stem type: lemmas and languages
                from .frombox import from_text
                cols.append(Column("from", "From", lambda e: from_text(db, e), ipa=True))
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

        def tag_tree():
            out = [ListItem(fl.CITATION_ITEM)]
            out += [self._group_item(g) for g in s.tags.groups]
            return out

        cols = [
            # the lemma's columns: double-click goes to the lemma in the lemma list
            Column("ref", "Reference", lambda r: r.entry.ref, lemma_level=True),
            Column("lemma", "Lemma", lambda r: db.lemma(r.entry), ipa=True, lemma_level=True),
            Column("gloss", "Gloss", lambda r: db.gloss(r.entry), lemma_level=True),
            # the second languages' glosses: offered in Configure columns, not shown by default (idea 19)
            *[Column("gloss:" + lang, f"Gloss ({lang})", lambda r, l=lang: db.gloss(r.entry, l), lemma_level=True)
              for lang in self._other_languages()],
            Column("wordclass", wcf.title if wcf else "Word Class", lambda r: db.word_class(r.entry),
                   closed=True, tree=lambda: s.list_items(wcf) if wcf else [], lemma_level=True),
            Column("tags", "Tags", lambda r: list(r.token.tags), closed=True, tree=tag_tree, multi=True,
                   unmarked=defaults, kind="chips",
                   tooltip=lambda r: s.tags.tag_tip(r.token.tags)
                   + "".join("\n⚠ " + n for n in (mx.unusual_notes(db, r.entry, r.token.tags)
                                                    if self.prefs.warn_unusual_tags else []))),
            Column("drawing", "Pitch drawing", lambda r: r.token.get("Pitch"), kind="drawing",
                   tooltip=lambda r: f"Pitch: {p}" if (p := r.token.get("Pitch")) else None),
        ]
        for f in s.token_fields:
            get = (lambda r, n=f.name, ml=f.multilingual: r.token.get(n, s.primary_gloss if ml else None))
            tip = None
            if self._predicts(f):                 # the English translation: suggestions in its tooltip
                tip = (lambda r, get=get: None if get(r) else (
                    f"Suggestion: {sug.text}\n{sug.describe()}\nDouble-click and press → to accept "
                    "it, or right-click → Accept suggested translation."
                    if (sug := self.suggestion_for(r)) else None))
            cols.append(Column(
                "f:" + f.name, f.title, get,
                closed=f.closed, tree=(lambda f=f: s.list_items(f)) if f.closed else None,
                ipa=f.role in ("phonetic", "phonemic"),
                edit=lambda r, text: None, tooltip=tip))
            if f.multilingual:                     # second languages: Translation (ar)...
                for lang in self._other_languages():
                    cols.append(Column(f"f:{f.name}:{lang}", f"{f.title} ({lang})",
                                       lambda r, n=f.name, l=lang: r.token.get(n, l),
                                       edit=lambda r, text: None))
        cols += [
            Column("speaker", "Speaker", lambda r: r.token.speaker),
            Column("date", "Date", lambda r: r.token.collected),
            # Value: the recording if it exists on disk, otherwise blank (so Blanks = no recording);
            # shown: the recording, or the name it would get, in grey.
            Column("file", "Soundfile", lambda r: r.token.file if r.token.file in self.sound_files else "",
                   blank_labels=("Missing", "Present"), flag=lambda r: r.token.rerecord, flag_label="Rerecord",
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
        from .. import pitchview                  # Show the pitch system off: no pitch columns (idea 9)
        return pitchview.columns(cols, s, pitchview.TOKENS)

    def _group_item(self, g):
        return ListItem(g.name, [ListItem(t.name) for t in g.tags] + [self._group_item(x) for x in g.groups])

    def _other_languages(self) -> list[str]:
        """The database's gloss languages other than the primary one: there to help speakers
        understand (ɛλicit), so hidden until a column or cell line is set to show them."""
        s = self.doc.db.settings
        return [lang for lang in s.gloss_languages if lang != s.primary_gloss]

    def _default_all_keys(self) -> list[str]:
        keys = ["ref", "lemma", "tags", "drawing"]
        keys += ["f:" + f.name for f in self.doc.db.settings.token_fields]
        return keys + ["speaker", "date", "file"]

    def _setup_columns(self):
        db = self.doc.db
        cols = self._lemma_columns()
        saved = self.doc.ws.get_list("columns/lemma")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_lemma_keys()
        if not self.lemmas.set_columns(cols, keys):       # widths kept when the columns stay
            self.lemmas.resizeColumnsToContents()
        self._closed_editors(self.lemmas)
        self._spell_delegates()
        cols = self._all_columns()
        saved = self.doc.ws.get_list("columns/alldata")
        keys = [k for k in saved if any(c.key == k for c in cols)] or self._default_all_keys()
        kept = self.all_table.set_columns(cols, keys)
        defaults = mx.default_names(db)
        self.all_table.set_delegate("tags", ChipsDelegate(
            lambda r: mx.chips(db, mx.marked(r.token.tags, defaults), r.entry)
            if r is not None else [], self.all_table))
        self.all_table.set_delegate("drawing", DrawingDelegate(
            lambda: (db.settings.pitch_low, db.settings.pitch_high), self.all_table))
        for f in db.settings.token_fields:
            if self._predicts(f):
                self.all_table.set_delegate("f:" + f.name, SuggestionDelegate(
                    lambda r: (sug.text if (sug := self.suggestion_for(r)) else ""), self.speller,
                    self.all_table))
        if db.settings.primary_gloss == spelling.LANG:
            self.all_table.set_delegate("gloss", SpellDelegate(self.speller, self.all_table))
        self._closed_editors(self.all_table)
        if not kept:                              # sized to the data once; afterwards the widths stay
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
            self.doc.ws_set("columns/lemma", dlg.chosen())
            self.lemmas.set_columns(cols, dlg.chosen())
            self._closed_editors(self.lemmas)
            self._spell_delegates()
            self.lemmas.set_rows(self.doc.db.entries)
            self.lemmas.resizeColumnsToContents()

    def configure_all_columns(self):
        cols = self._all_columns()
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], self.all_table.visible_keys())
        if dlg.exec():
            from .. import pitchview              # pitch hidden: its columns kept where they were
            self.doc.ws_set("columns/alldata", pitchview.keep_hidden(
                self.doc.ws.get_list("columns/alldata") or self._default_all_keys(), dlg.chosen(),
                self.doc.db.settings, pitchview.TOKENS))
            self._setup_columns()
            self.refresh()

    # ============================================================ database
    def load_database(self, db: Database, workspace=None):
        """Show a database. workspace: (Workspace, as on disk?) from _workspace_for(); without it
        the workspace is found without asking (a missing one starts blank)."""
        self.player.stop()
        if self.doc.db is not db:
            self.doc.empty_held()                 # the closed database's deleted recordings: Recycle Bin
        if self.bulk_window is not None:          # it belongs to the database being closed
            self.bulk_window.close()
        if self.utterances_window is not None:
            self.utterances_window.close()
        if self.xml_window is not None:           # it shows the database being closed
            self.xml_window.close()
            self.xml_window.deleteLater()
            self.xml_window = None
        if self.cogitate_window is not None:      # its hypotheses are the closed database's notebook's
            self.cogitate_window.close()
            self.cogitate_window.deleteLater()
            self.cogitate_window = None
        if self.whiteboard_window is not None:    # its drawing is the closed database's workspace's
            self.whiteboard_window.close()
            self.whiteboard_window.deleteLater()
            self.whiteboard_window = None
        if self.doc.db is not db:
            self._save_view()
            self.doc.write_workspace()            # the closed database's working state, written now
        if workspace is None:
            workspace = self._workspace_for(db, ask=False)
        self._mark_open(db.path)
        self.doc.db = db
        ws, written = workspace
        self.doc.set_workspace(ws, written)
        if not written:
            self.doc.write_workspace()            # made now (from an older database, or blank)
        self.doc.text_buffers.clear()             # unsaved line edits of the database closed are dropped
        self.doc.undo.clear()
        self.doc.undo.setClean()
        self.doc._settings_dirty = False
        self.doc.renamed.clear()
        self._suggestions_stale = True
        self.spell_checker.set_words(db.settings.spelling_words)
        if self.spelling_window is not None:      # it belongs to the database being closed
            self.spelling_window.close()
        self._load_notebook()
        self.doc.bring_back_held()
        self.configs.clear()
        for v in (self.lt_view, self.tt_view):
            v.set_database(db)
        symbols.set_current(self._symbols())      # Σymbols: this database's list
        self.comparison.set_range(db.settings.pitch_low, db.settings.pitch_high)
        self._sync_pitch_view()                   # this database's Show the pitch system (idea 9)
        for box, name in ((self.autoplay, "autoplay"), (self.only_data, "only_with_data")):
            box.blockSignals(True)                # each database has its own (in its workspace)
            box.setChecked(self.doc.ws.get_bool(name))
            box.blockSignals(False)
        self.hide_empty.blockSignals(True)        # Hide empty lemmas (idea 55): this database's too
        self.hide_empty.setChecked(self.doc.ws.get_bool(HIDE_EMPTY))
        self.hide_empty.blockSignals(False)
        self._apply_hide_empty()
        self._setup_columns()
        self.lemmas.proxy.pinned = None           # an Alt+click pin belongs to the database closed
        self.all_table.proxy.pinned = None
        self.lemmas.proxy.filters.clear()         # so do the filters (this one's come back with its view)
        self.all_table.proxy.filters.clear()
        self.lemmas.set_rows(db.entries)
        self.lemma_search.clear()
        self.all_search.clear()
        self._fill_session()
        self._note_recent()                       # File → Open recent (idea 51)
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(ALL_DATA)
        self.tabs.blockSignals(False)
        self._tab_changed(ALL_DATA)
        if db.entries:
            self.lemmas.selectRow(0)
        self._restore_view()
        self._update_title()
        self._report_missing()
        self.refresh_notebook()
        for dlg in self.items_dialogs.values():      # another database's notebook
            dlg.refresh()
        self.update_todo_badge()
        if (db.workspace_from_file or db.upgraded) and not db.load_notes:   # quietly, saving writes the new format
            self.doc.settings_changed()
        if getattr(db, "added_fields", None):     # a new core field (Stem type, 22 October): said quietly
            self.statusBar().showMessage(
                f"Added the new field {', '.join(db.added_fields)} (where a lemma comes from, with From). "
                "It's empty; Settings → General can hide it.", 15000)
        if db.load_notes:                         # e.g. an older file upgraded to the current format
            notes, db.load_notes = db.load_notes, []
            self.doc.settings_changed()           # unsaved, so saving writes the new format
            QMessageBox.information(self, "Database upgraded", "\n\n".join(notes))
        self._check_layout(db)
        from .wordlist_dialogs import offer_update   # the EACW updated since (idea 66)
        offer_update(self)

    # ------------------------------------------------- the workspace file (idea 36)
    def _workspace_for(self, db: Database, ask: bool = True):
        """(the Workspace that goes with the database, whether it is as on disk), or None if the
        person cancelled. A database from before format 7 makes its workspace from what it held,
        with this computer's remembered settings for it; a missing one asks (Locate…, Cancel,
        Start a new workspace) when ask, and starts blank otherwise."""
        from .. import workspace as wsmod
        if not db.path:
            return wsmod.Workspace(), False
        path = wsmod.path_for(db.path)
        if path.exists():
            try:
                return wsmod.load(path, db), True
            except wsmod.WorkspaceError as exc:
                if ask:
                    QMessageBox.warning(self, "Workspace", f"{exc}\n\nThe database opens with the default "
                                        "workspace this time, and the file is left as it is (it isn't "
                                        "written over).")
                return wsmod.Workspace(path=str(path), unreadable=True), True
        if db.workspace_from_file:                # format 6: its working state moves out of it
            return self._migrated_workspace(db, str(path)), False
        if ask:
            choice = self._ask_missing_workspace(db)
            if choice is None:
                return None
            if choice:                            # located: copied beside the database
                try:
                    shutil.copy2(choice, path)
                    return wsmod.load(path, db), True
                except (OSError, wsmod.WorkspaceError) as exc:
                    QMessageBox.warning(self, "Workspace", f"Couldn't use {Path(choice).name}: {exc}\n\n"
                                        "The database opens with a new workspace.")
        self._clear_working_state(db)
        return wsmod.Workspace(path=str(path)), False

    @staticmethod
    def _clear_working_state(db: Database):
        """A blank workspace: nothing of the working state kept in the database's objects."""
        s = db.settings
        s.matrices, s.spelling_words = [], []
        s.play_cell_on_click, s.pitch_style = False, "contours"
        for _, t in db.all_tokens():
            t.rerecord = False

    def _ask_missing_workspace(self, db: Database):
        """Missing workspace: a path picked (Locate…), "" (Start a new workspace) or None (Cancel)."""
        from .. import workspace as wsmod
        name = Path(db.path).name
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Workspace missing")
        box.setText(f"The workspace file for {name} is missing.")
        box.setInformativeText(f"{wsmod.path_for(db.path).name} keeps what you were working on: saved "
                               "matrices, filters and columns, the Current Session, tokens flagged to be "
                               "recorded again, the spelling list. It should be beside the database.\n\n"
                               "Locate it, or start a new workspace with the defaults.")
        locate = box.addButton("Locate…", QMessageBox.AcceptRole)
        new = box.addButton("Start a new workspace", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        hit = box.clickedButton()
        if hit is new:
            return ""
        if hit is not locate:
            return None
        found, _ = QFileDialog.getOpenFileName(self, "Locate the workspace", str(Path(db.path).parent),
                                               "Lemmatrix workspace (*.workspace);;All files (*)")
        return found or None

    def _migrated_workspace(self, db: Database, path: str):
        """The workspace for a database from before format 7: its saved matrices, rerecord flags and
        spelling list stay in its objects (written into the workspace), and this computer's settings
        for it are copied in once (the view, the Current Session, columns, Configure view…)."""
        from .. import workspace as wsmod
        ws = wsmod.Workspace(path=path)
        p = self.prefs
        if (v := p.view_for(db.path)):
            ws.set("view", v)
        if (v := p.session_for(db.path)):
            ws.set("session", v)
        if (sp := p.get_value("session/speaker")) and isinstance(sp, str):
            ws.set("session/speaker", sp)
        dates = p.full_backup_dates(db.path)
        if any(dates.values()):
            ws.set("fullbackup", dates)
        for key in ("columns/lemma", "columns/alldata", "columns/utterances", "columns/texts",
                    "columns/bulk-lemmas", "columns/bulk-tokens", "lines/fields", "lines/aligned"):
            if (v := p.get_list(key)):
                ws.set(key, v)
        ws.set("autoplay", p.autoplay_tokens)
        ws.set("only_with_data", p.only_lemmas_with_data)
        if (v := p.get_value("notebook/sort")):
            ws.set("notebook/sort", str(v))
        return ws

    # ------------------------------------------------- the fixed folder layout
    def _check_layout(self, db: Database):
        """On opening: another database in the same folder, consent forms moved into
        Documentation (relinked quietly), and the reminder to make a full backup."""
        if not db.path:
            return
        others = layout.other_databases(db.path)
        if others:
            QMessageBox.warning(
                self, "Another database in this folder",
                f"{', '.join(p.name for p in others[:5])} {'is' if len(others) == 1 else 'are'} in the same "
                f"folder as {Path(db.path).name}. Each database needs a folder of its own, since the "
                "recordings (Soundfiles), backups and documentation in it belong to one database.\n\n"
                "Close Lemmatrix and move one of them, with its notebook, into a folder of its own "
                "(its recordings too, if it has any).")
        self._praat_text_names(db)
        relinked = layout.relink_consent(db)
        if relinked:
            self.doc.settings_changed()
            self.statusBar().showMessage(
                f"Consent forms found in Documentation and relinked: {', '.join(relinked)}.", 10000)
        self._remind_new_day()
        self._offer_empty_days()
        self._remind_full_backup()
        self._remind_elicit()

    def _remind_elicit(self):
        """On opening: ɛλicit recordings waiting for review (Review now, Later), and a look in
        Google Drive for requests out."""
        from .elicit_dialogs import remind
        self.elicit_drive_ready = {}
        self.refresh_elicit_icon()
        remind(self)
        self.check_elicit_drive()

    def _praat_text_names(self, db: Database):
        """On opening: recordings (tokens', utterances' and texts', and texts' TextGrids) named
        before names followed Praat's (spaces and punctuation as underscores: texts 18 October,
        tokens and utterances 19 October) are renamed. If Praat has already saved an edited file
        under its own name beside the old one, and it is newer, that one is kept and the old one
        held like a deleted recording. Not saving puts everything back."""
        from ..filenames import build_filename, praat_name
        jobs = []                                 # (what, folder, current name, wanted name, set it)
        folder = storage.text_folder(db)
        for t in db.texts:
            for attr, ext in (("file", ".wav"), ("textgrid", ".TextGrid")):
                cur = getattr(t, attr)
                if cur:
                    jobs.append((t.ref, folder, cur, db.expected_text_name(t, Path(cur).suffix or ext),
                                 lambda name, t=t, attr=attr: setattr(t, attr, name)))
        for e, tok in db.all_tokens():
            if tok.file:
                stem = tok.file.rsplit(".", 1)[0]
                if praat_name(stem) == stem:      # already as Praat writes it: nothing to rename (the
                    continue                      # common case; building every expected name took seconds)
                want = build_filename(db, e, tok, Path(tok.file).suffix or ".wav")
                jobs.append((e.ref, storage.folder_for(db, e), tok.file, want,
                             lambda name, tok=tok: setattr(tok, "file", name)))
        renamed, adopted, clashes = [], [], []
        for ref, folder, cur, want, set_name in jobs:
            if cur == want or praat_name(Path(cur).stem) != Path(want).stem:
                continue                          # up to date, or out of date for another reason
            src, dst = folder / cur, folder / want
            try:
                if not src.exists():
                    if not dst.exists():
                        continue
                    renamed.append(want)          # only Praat's copy is there
                elif dst.exists() and not storage.same_file(src, dst):
                    if dst.stat().st_mtime < src.stat().st_mtime:
                        clashes.append(f"{ref}: {cur} and {want}")
                        continue
                    held = self.doc.hold_recording(src)          # Praat's newer copy is kept
                    src.rename(held)
                    self.doc._note_rename(src, held)
                    adopted.append(f"{ref}: {want}")
                else:
                    src.rename(dst)
                    self.doc._note_rename(src, dst)
                    renamed.append(want)
            except OSError as exc:
                clashes.append(f"{ref}: {exc}")
                continue
            set_name(want)
        if not (renamed or adopted or clashes):
            return
        self.doc.settings_changed()
        msg = ("Soundfiles (and texts' TextGrids) are now named the way Praat names them (underscores "
               "for spaces and punctuation), so saving in Praat with the name it suggests overwrites "
               "the file Lemmatrix reads instead of making a second one.")
        if renamed:
            msg += f"\n\nRenamed {len(renamed)}: {', '.join(renamed[:8])}{' …' if len(renamed) > 8 else ''}."
        if adopted:
            msg += ("\n\nPraat had saved these under its own name; the newer ones are used now "
                    f"and the older ones set aside: {', '.join(adopted[:12])}"
                    f"{' …' if len(adopted) > 12 else ''}.")
        if clashes:
            msg += ("\n\nNot renamed (both names exist and the old one is newer; check which to keep): "
                    + ", ".join(clashes))
        msg += "\n\nSave to keep the new names; closing without saving puts the old ones back."
        QMessageBox.information(self, "Soundfile names", msg)

    def _remind_full_backup(self):
        """Once a week: a full backup is due (File → Full backup)."""
        path = self.doc.db.path
        if not path:
            return
        dates = self._backup_dates()
        if not dates["first_seen"]:
            self._set_backup_date("first_seen", today())
            return
        if not layout.reminder_due(dates["last"], dates["snoozed"], dates["first_seen"]):
            return
        if self._ask_backup_reminder(dates["last"]):
            self.full_backup()
        else:
            import datetime as _dt
            later = (_dt.date.today() + _dt.timedelta(days=layout.REMIND_DAYS)).isoformat()
            self._set_backup_date("snoozed", later)

    def _backup_dates(self) -> dict:
        """The full backup's dates for this database, kept in its workspace (a backup made on one
        computer counts on every computer): last, snoozed (no reminder before), first_seen."""
        d = self.doc.ws.get_dict("fullbackup")
        return {k: str(d.get(k, "") or "") for k in ("last", "snoozed", "first_seen")}

    def _set_backup_date(self, which: str, day: str):
        d = self._backup_dates()
        d[which] = day
        self.doc.ws_set("fullbackup", d)

    def _ask_backup_reminder(self, last: str) -> bool:
        """True for Back up now; False for remind me again in 7 days."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Full backup")
        box.setText(("The last full backup of this database was on " + last + "." if last else
                     "This database hasn't had a full backup yet.") +
                    " It's time to make one.")
        box.setInformativeText("File → Full backup saves the database's whole folder (the database, "
                               "notebook, recordings and documentation) as one zip file, to keep on "
                               "another drive or in a cloud folder.")
        now = box.addButton("Back up now", QMessageBox.AcceptRole)
        box.addButton("Thanks, remind me again in 7 days", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is now

    def full_backup(self) -> bool:
        """File → Full backup: the database's whole folder as one dated zip, saved outside it."""
        db = self.doc.db
        if not db.path:
            QMessageBox.information(self, "Full backup", "Save the database first.")
            return False
        if self.doc.dirty:
            r = _w.choose(self, "Full backup", "Save the database first, so the backup has your latest "
                          "changes?", ["Save, then back up", "Back up without saving"])
            if r is None or (r == 0 and not self.save()):
                return False
        main = layout.main_folder(db.path)
        start = Path(self.prefs.full_backup_folder) if self.prefs.full_backup_folder else \
            Path.home() / "Documents"
        if layout.inside(start, main):
            start = main.parent
        path = self._full_backup_path(str(start / layout.full_backup_name(db.path)))
        if not path:
            return False
        if layout.inside(Path(path), main):
            QMessageBox.warning(self, "Full backup", "A full backup can't go inside the database's own "
                                "folder (it would back itself up). Choose another drive or a cloud folder.")
            return False
        progress = QProgressDialog("Making the full backup…", "Cancel", 0, 100, self)
        progress.setWindowTitle("Full backup")
        progress.setMinimumDuration(400)
        progress.setAutoClose(False)

        def step(done, total, name):
            progress.setMaximum(max(total, 1))
            progress.setValue(done)
            progress.setLabelText(f"Making the full backup…\n{name}" if name else "Finishing…")
            QApplication.processEvents()
            if progress.wasCanceled():
                raise layout.Cancelled()
        try:
            n = layout.full_backup(db.path, path, step)
        except layout.Cancelled:
            progress.close()
            self.statusBar().showMessage("Full backup cancelled; nothing was saved.", 6000)
            return False
        except (OSError, ValueError) as exc:
            progress.close()
            QMessageBox.warning(self, "Full backup", f"Couldn't make the full backup: {exc}")
            return False
        progress.close()
        if not self.prefs.full_backup_folder:     # the first one: next time it starts there
            self.prefs.full_backup_folder = str(Path(path).parent)
        self._set_backup_date("last", today())
        self._set_backup_date("snoozed", "")
        self.statusBar().showMessage(f"Full backup made: {n} files in {QDir.toNativeSeparators(path)}.", 10000)
        return True

    def _full_backup_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, "Full backup", suggested, "Zip file (*.zip)")
        if path and not path.lower().endswith(".zip"):
            path += ".zip"
        return path

    def set_unusual_warning(self, on: bool):
        """The soft warning for tags that aren't usual for their lemma's word class (Settings →
        General → Warnings; "Don't show this again" turns it off)."""
        self.prefs.warn_unusual_tags = bool(on)
        widgets.SHOW_UNUSUAL = bool(on)
        for w in (self.all_table, self.lt_view, self.tt_view):
            w.viewport().update()
        if self.bulk_window is not None:
            self.bulk_window.tables_repaint()

    def _fill_session(self):
        """The Current Session panel: the session's people and places.

        They are what the panel had when last used with this database (closing the program included),
        even an empty panel. Only when nothing has been remembered yet do they come from the notebook:
        the session's day if it has notes, otherwise the latest day with people or places."""
        db = self.doc.db
        self._fill_db_title()
        last = self.doc.ws.get_dict("session") if db.path else {}
        if last:
            keys = {k: [x for x in last.get(k, []) if isinstance(x, str)] for k in self.sess_rows}
        else:
            s = self.doc.notebook.session(self.session_date()) if self.session_date() else None
            if s is None or not (s.researchers or s.participants or s.locations):
                s = self._latest_notebook_session()
            keys = ({chips.RESEARCHERS: list(s.researchers), chips.PARTICIPANTS: list(s.participants),
                     chips.LOCATIONS: list(s.locations)} if s is not None
                    else {k: [] for k in self.sess_rows})
            if not db.path and not keys[chips.PARTICIPANTS] and self.speaker_code in db.participant_codes():
                keys[chips.PARTICIPANTS] = [self.speaker_code]
        # the day the panel was last used (for the new-day question, _remind_new_day)
        self._session_last_day = str(self.doc.ws.get("session/day", "") or "") if db.path else ""
        for kind, row in self.sess_rows.items():
            row.set_keys(keys.get(kind, []))
        self._remember_session()
        self._fill_speakers()

    def _latest_notebook_session(self):
        """The most recent day in the notebook (up to the session's date) with people or places."""
        upto = self.session_date() or today()
        days = [s for s in self.doc.notebook.sessions
                if s.date <= upto and (s.researchers or s.participants or s.locations)]
        return max(days, key=lambda s: s.date, default=None)

    def _remember_session(self):
        """The panel's people and places are remembered for the next run, whichever way they got there
        (picked, or loaded from a day in the notebook)."""
        if self.doc.db.path:                      # an empty panel is remembered too (in the workspace)
            self.doc.ws_set("session", self.session_keys())
            self.doc.ws_set("session/day", today())

    def _offer_empty_days(self):
        """On a new day (Josh, 23 October): notebook days with nothing in them but people and
        places (Write to notebook pressed, then nothing done) are offered to be cleared."""
        last = getattr(self, "_session_last_day", "")
        if not self.doc.db.path or not last or last >= today():
            return
        days = nbmod.empty_days(self.doc.notebook, self.doc.db, today())
        if not days:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Empty notebook days")
        n = len(days)
        box.setText(f"{n} day{'s' if n != 1 else ''} in the notebook {'have' if n != 1 else 'has'} nothing in "
                    "{} but people and places: {}.".format("them" if n != 1 else "it",
                                                         ", ".join(s.date for s in days[:8]) +
                                                         (f" and {n - 8} more" if n > 8 else "")))
        box.setInformativeText("Write to notebook was pressed on those days, but no notes, comments, "
                               "questions, To Dos, recordings or texts followed. Clear them?")
        clear = box.addButton("Clear them", QMessageBox.DestructiveRole)
        box.addButton("Keep them", QMessageBox.RejectRole)
        box.setDefaultButton(clear)
        box.exec()
        if box.clickedButton() is not clear:
            return
        for s in days:
            self.doc.notebook.remove(s)
        self.doc.notebook_changed()
        self.refresh_notebook()
        self.statusBar().showMessage(f"Cleared {n} empty notebook day{'s' if n != 1 else ''}.", 6000)

    def _remind_new_day(self):
        """On opening on a new day (Josh, 21 October): the Current Session still has the people and
        places of the last day it was used, so ask whether to keep them or start with an empty panel."""
        last = getattr(self, "_session_last_day", "")
        if not self.doc.db.path or not last or last >= today():
            return
        if not any(self.session_keys().values()):
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Current Session")
        box.setText(f"It's a new day. The Current Session was last used on {last}.")
        names = "  ·  ".join(", ".join(v) for v in self.session_keys().values() if v)
        box.setInformativeText(f"Keep its people and places ({names}) for today, or reset it? "
                               "Reset keeps the researcher; the participants and places go.")
        keep = box.addButton("Keep", QMessageBox.AcceptRole)
        box.addButton("Reset", QMessageBox.DestructiveRole)
        box.setDefaultButton(keep)
        box.exec()
        if box.clickedButton() is not keep:
            # Reset keeps the researcher (Josh, 23 October): you, as this computer knows you (File →
            # New database), or the panel's researchers if it doesn't; participants and places go
            me = self.prefs.you.get("code", "")
            have = list(self.sess_rows[chips.RESEARCHERS].keys)
            keep_researchers = [c for c in have if c == me] if me and me in have else have
            for kind, row in self.sess_rows.items():
                row.set_keys(keep_researchers if kind == chips.RESEARCHERS else [])
            self._fill_speakers()
        self._remember_session()

    @staticmethod
    def title_of(db) -> str:
        """Language - Variety - Database name, as at the top of the window."""
        md = db.metadata
        parts = [md.language_name or md.language_code, md.variety_name or md.variety_code, md.name]
        return " - ".join(p for p in parts if p) or "Unnamed database"

    def _fill_db_title(self):
        self.db_title.setText(self.title_of(self.doc.db))

    # ---- File → Open recent (IDEAS.md idea 51; Josh, 23 October) ------------------------------
    def _fill_recent_menu(self):
        """The 10 databases opened most recently on this computer, the most recent first; one that
        isn't there any more is greyed, "(not found)"; Clear recent at the bottom."""
        m = self.recent_menu
        m.clear()
        items = self.prefs.recent
        for r in items:
            title = r.get("title") or Path(r["path"]).stem
            here = Path(r["path"]).exists()
            a = m.addAction(title if here else f"{title} (not found)")
            a.setToolTip(QDir.toNativeSeparators(r["path"]))
            a.setEnabled(here)
            if self.doc.db.path and Path(self.doc.db.path).resolve() == Path(r["path"]).resolve():
                a.setCheckable(True)
                a.setChecked(True)               # the one open now
            a.triggered.connect(lambda *_, p=r["path"]: self.open_file(p))
        if not items:
            m.addAction("No recent databases").setEnabled(False)
            return
        m.addSeparator()
        m.addAction("Clear recent").triggered.connect(lambda *_: setattr(self.prefs, "recent", []))
        m.setToolTipsVisible(True)

    def _note_recent(self):
        if self.doc.db.path:
            self.prefs.add_recent(self.doc.db.path, self.title_of(self.doc.db))

    def speaker_choices(self) -> list[str]:
        """Who can be the speaker: the session's participants (all participants if none are picked)."""
        codes = self.sess_rows[chips.PARTICIPANTS].keys
        return list(codes) or self.doc.db.participant_codes()

    def _fill_speakers(self):
        """The speaker follows the session's participants: it stays if still there, otherwise it
        is the first participant. (It is chosen in the token dialogue.)"""
        choices = self.speaker_choices()
        current = self.speaker_code
        if current and current not in choices:
            current = ""
        if not current and self.sess_rows[chips.PARTICIPANTS].keys:
            current = choices[0]
        self.speaker_code = current

    def set_speaker(self, code: str):
        """The speaker for the next tokens and recordings (chosen in the token dialogue)."""
        self.speaker_code = code

    @property
    def speaker_code(self) -> str:
        """The session's speaker, kept in the database's workspace."""
        v = self.doc.ws.get("session/speaker", "")
        return v if isinstance(v, str) else ""

    @speaker_code.setter
    def speaker_code(self, code: str):
        self.doc.ws_set("session/speaker", code or "")

    def session_keys(self) -> dict[str, list[str]]:
        return {k: list(row.keys) for k, row in self.sess_rows.items()}

    def _session_people_changed(self):
        if self.doc.db.path:                      # (also when the last chip is removed)
            self.doc.ws_set("session", self.session_keys())
        self._fill_speakers()

    def _session_date_changed(self):
        s = self.doc.notebook.session(self.session_date()) if self.session_date() else None
        if s is not None:                     # a day with notes: its people and places
            for kind, keys in ((chips.RESEARCHERS, s.researchers), (chips.PARTICIPANTS, s.participants),
                               (chips.LOCATIONS, s.locations)):
                self.sess_rows[kind].set_keys(keys)
            self._remember_session()
            self._fill_speakers()
        self.write_btn.setEnabled(bool(self.session_date()))

    def _check_new_day(self):
        """A new day: today can be picked, and a session dated yesterday (the old today) moves on
        to today. A date picked for backfilling stays."""
        now = QDate.currentDate()
        if now == self._today:
            return
        old, self._today = self._today, now
        self.sess_date.setMaximumDate(now)
        if self.sess_date.date() == old:
            self.sess_date.setDate(now)

    def work_date(self) -> str:
        """The day comments are dated with: the session's date, or today without one."""
        return self.session_date() or today()

    def session_speaker(self) -> str:
        return self.speaker_code

    # ============================================================= notebook
    def _notebook_icons(self):
        a = theme.accent().name()
        self.notebook_btn.setIcon(icon("notebook", 34, a))
        self.texts_btn.setIcon(icon("texts-utterances", self.TEXTS_ICON, a))
        self.xml_btn.setIcon(icon("xml-viewer", self.TEXTS_ICON, theme.colour("pitch").name()))
        self.questions_btn.setIcon(icon("questions", self.TEXTS_ICON, theme.colour("pitch").name()))
        self.todo_btn.setIcon(icon("todo", self.TEXTS_ICON, theme.colour("pitch").name()))
        self.snapshots_btn.setIcon(icon("snapshots", self.TEXTS_ICON, theme.colour("pitch").name()))
        self.update_todo_badge()
        self.cogitate_btn.setIcon(icon("cogitate", self.TEXTS_ICON, theme.colour("pitch").name()))
        if self.cogitate_window is not None:
            self.cogitate_window._restyle()
        self.refresh_elicit_icon()
        self.write_btn.setIcon(icon("write-notebook", 34))
        self._save_icon()
        self._style_menu_bar()
        self._panels_icon()
        if hasattr(self, "tick_action"):
            self.tick_action.setIcon(themed_icon("tick", 16))
        for w in QApplication.topLevelWidgets():         # icons in the theme's colours follow it, every window
            for b in w.findChildren(QToolButton):
                if b.property("icon_name") in THEMED:
                    b.setIcon(themed_icon(b.property("icon_name"), b.iconSize().height() or 20))
        for v in (self.lt_view, self.tt_view):           # the accent, lighter on dark
            v.switch.setIcon(icon("switch-plain" if theme.dark() else "switch", 22,   # no white edge on dark
                                  theme.colour("pitch").name()))
            v.switch.setIconSize(QSize(22, 22))

    # ---- option panels -------------------------------------------------
    def panels_hidden(self) -> bool:
        return all(sp.sizes()[1] == 0 for sp in (self.left_split, self.right_split))

    def toggle_panels(self):
        """Hide both option panels (lemma options; matrix options and Current Session), or show them."""
        hide = not self.panels_hidden()
        for name, sp in (("left", self.left_split), ("right", self.right_split)):
            top, bottom = sp.sizes()
            if hide:
                if bottom:
                    self._panel_sizes[name] = bottom
                sp.setSizes([top + bottom, 0])
            elif bottom == 0:
                h = self._panel_sizes[name]
                sp.setSizes([max(100, top - h), h])
        self._panels_icon()

    def _style_menu_bar(self):
        """File, Edit… level with the title and Save (centred in the bar's height), flat, no lines."""
        mb = self.menuBar()
        fm = mb.fontMetrics()
        pad = max(2, (self._corner.sizeHint().height() - fm.height()) // 2 - 1)
        mb.setStyleSheet(
            f"QMenuBar {{ background: {theme.colour('window').name()}; border: none; }} "
            f"QMenuBar::item {{ background: transparent; color: {theme.colour('window_text').name()}; "
            f"padding: {pad}px 8px; margin: 0; border: none; }} "
            f"QMenuBar::item:selected, QMenuBar::item:pressed {{ background: {theme.wash(0.75).name()}; "
            "border-radius: 4px; }")

    def _panels_icon(self):
        hidden = self.panels_hidden()
        self.panels_btn.setIcon(icon("chevron-up" if hidden else "chevron-down", 18, theme.colour("pitch").name()))
        self.panels_btn.setToolTip("Show the working panels" if hidden else
                                   "Hide the working panels (the lemma list's, the working window's and "
                                   "Current Session); they can also be dragged down out of sight")

    def _load_notebook(self):
        problem = self.doc.load_notebook()
        if problem:
            QMessageBox.warning(self, "Notebook", problem + "\n\nThe notebook won't be saved over, "
                                "so nothing in it is lost. Check the file, then open the database again.")
        elif self.doc.notebook.repaired:
            QMessageBox.information(self, "Notebook", "The notebook had invisible characters in it (from a "
                                    "paste, perhaps) that made it unreadable. They have been taken out; "
                                    "saving writes the repaired notebook (a backup of the old one is kept).")
        # people found in the notebook join the lists (Q8)
        md = self.doc.db.metadata
        researchers, participants = self.doc.notebook.people()
        for codes, people, make in ((researchers, md.researchers, Person.researcher),
                                    (participants, md.participants, Person)):
            have = {p.code for p in people}
            people += [make(c) for c in codes if c not in have]

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
                self.doc.save_notebook()
            except OSError as exc:
                QMessageBox.warning(self, "Notebook", f"Couldn't save the notebook: {exc}")
                return
            self.doc.dirtyChanged.emit(self.doc.dirty)
            n = len(s.comments)
            self.statusBar().showMessage(
                f"Written to the notebook for {date}" + (f", with {n} comment(s)." if n else "."), 6000)
        self.refresh_notebook(date)

    def refresh_notebook(self, date: str | None = None):
        """The notebook changed: an open notebook window shows it; a hidden one is filled when it
        is next opened (open_notebook). The one place that reloads it (the audit, 26 October)."""
        if self.notebook_dialog is not None and self.notebook_dialog.isVisible():
            self.notebook_dialog.reload(date)

    def open_notebook(self, date: str | None = None):
        from .notebook_dialog import NotebookDialog
        w = self._window("notebook_dialog", NotebookDialog)
        w.reload(date or self.session_date() or None)
        bring_forward(w)

    def open_questions(self):
        from .notebook_dialog import QuestionsDialog
        return self._open_items("questions", QuestionsDialog)

    def open_todos(self):
        """View → To Do: every to do in the notebook, as View → Questions (Josh, 21 October)."""
        from .notebook_dialog import TodoDialog
        return self._open_items("todo", TodoDialog)

    def open_snapshots(self):
        """View → Snapshots (Ctrl+Shift+P): every snapshot, as View → Questions (Josh, 24 October)."""
        from .notebook_dialog import SnapshotsDialog
        return self._open_items("snapshots", SnapshotsDialog)

    def _window(self, attr: str, cls):
        """A window of its own, made the first time (then kept in self.<attr>, or set back to None
        by the windows freed when closed: Bulk edit, Check spelling, Texts and utterances)."""
        w = getattr(self, attr, None)
        if w is None:
            w = cls(self)
            setattr(self, attr, w)
            self._watch_minimise(w, attr)
        return w

    # The dock's icon for each window of its own (idea 78): the app bar's where it has one
    DOCK_ICONS = {"utterances_window": "texts_btn", "cogitate_window": "cogitate_btn", "xml_window": "xml_btn",
                  "notebook_dialog": "notebook_btn", "questions": "questions_btn", "todo": "todo_btn",
                  "snapshots": "snapshots_btn"}

    def _watch_minimise(self, w, key: str):
        """Dock this window when it is minimised (idea 78, Josh, 26 October)."""
        dock = getattr(self, "dock", None)
        if dock is None:
            return

        def icon_fn():
            btn = getattr(self, self.DOCK_ICONS.get(key, ""), None)
            if btn is not None and not btn.icon().isNull():
                return btn.icon()
            if key == "whiteboard_window":
                from .whiteboard_art import blackboard_icon
                return blackboard_icon(22)
            if key == "bulk_window":
                return icon("edit", 22)
            if key == "spelling_window":
                from .dock import letters_icon
                return letters_icon("abc")
            ic = w.windowIcon()
            return ic if not ic.isNull() else self.windowIcon()
        dock.watch(w, icon_fn)

    def _open_items(self, key, cls):
        """View → Questions / To Do: a window beside the main one, not modal, so the main window
        stays usable while it is open; one of each, brought forward if already open (Josh, 22 October)."""
        dlg = self.items_dialogs.get(key)
        if dlg is None:
            dlg = cls(self)
            dlg.finished.connect(lambda *_: self.refresh_notebook())
            self.items_dialogs[key] = dlg
            self._watch_minimise(dlg, key)
        else:
            dlg.refresh()
        bring_forward(dlg)
        return dlg

    def go_to(self, entry, index=None):
        """Show a lemma (and one of its tokens) from a notebook link; an utterance is shown in the
        Texts and utterances window."""
        from ..model import is_utterance
        if is_utterance(entry):
            if entry not in self.doc.db.utterances:
                return False
            self.open_utterances(select=entry)
            return True
        if entry not in self.doc.db.entries:
            return False
        if entry not in self.lemmas.visible_rows():
            self._clear_lemma_filters(toggles=False)    # the toggles only if needed, said below
        # Hide empty lemmas and Hide empty tokens aren't filters, so clearing the
        # filters left an empty lemma hidden and the link selected nothing (the audit, 25 October)
        shown = []
        if not any(r is entry for r in self.lemmas.visible_rows()) and self.hide_empty.isChecked():
            self.hide_empty.setChecked(False)
            shown.append("Hide empty lemmas")
        self.lemmas.select_row(entry)
        if index is not None:
            self.tabs.setCurrentIndex(ALL_DATA)
            row = TokenRow(entry, index)
            if row not in self.all_table.visible_rows():
                self._clear_all_filters(toggles=False)
                self.refresh()
            if row not in self.all_table.visible_rows() and self.only_data.isChecked():
                self.only_data.setChecked(False)
                shown.append("Hide empty tokens")
                self.refresh()
            self.all_table.select_row(row)
        if shown:
            self.statusBar().showMessage(f"Turned off {' and '.join(shown)} to show {entry.ref}.", 8000)
        self.raise_()
        self.activateWindow()
        return True

    def session_date(self) -> str:
        return "" if self.sess_nodate.isChecked() else self.sess_date.date().toString("yyyy-MM-dd")

    def _dirty_changed(self, dirty: bool):
        self._update_title()
        self._save_icon()
        self.update_todo_badge()             # the notebook marks itself changed this way

    def _fix_status_bar(self):
        """The status bar is there from the start, at the height a message needs, so a message
        (e.g. "Saved.") never makes it grow and nudge the panes above it (Josh, 20 October)."""
        sb = self.statusBar()
        sb.showMessage(" ")
        h = max(sb.sizeHint().height(), sb.fontMetrics().height() + 8)
        sb.clearMessage()
        sb.setFixedHeight(h)

    def _save_icon(self):
        """The floppy: the theme colour (lighter on dark) with unsaved changes, grey once saved."""
        c = theme.colour("pitch") if self.doc.dirty else QColor("#6e6e6e" if theme.dark() else "#a6a6a6")
        self.save_btn.setIcon(icon("save-solid", 20, c.name()))

    def _update_title(self):
        db = self.doc.db
        name = Path(db.path).name if db.path else "Untitled"
        self.setWindowTitle(f"{'*' if self.doc.dirty else ''}{name} — Lemmatrix")

    def _doc_changed(self):
        self._suggestions_stale = True
        touched = self._with_dependants(self.doc.last_touched)
        for k, was in self._touched.items():
            self._touched[k] = None if was is None or touched is None else was | touched
        self.lemmas.set_rows(self.doc.db.entries, touched)
        # All data's rows point at tokens by position: a token just deleted (the last of its
        # lemma, e.g. one just added) would be painted before the refresh below and crash.
        rows = self.all_table.model_.rows
        if any(r.index >= len(r.entry.tokens) for r in rows):
            self.all_table.set_rows([r for r in rows if r.index < len(r.entry.tokens)])
        self.schedule_refresh()
        self._update_title()

    def _with_dependants(self, touched):
        """The lemmas changed (ids), with those whose From names one of them (its form shows in
        their From column), or None."""
        if not touched:
            return touched
        ids = {e.id for e in self.doc.db.entries if id(e) in touched}
        more = {id(e) for e in self.doc.db.entries if ids.intersection(e.from_lemmas)}
        return touched | more if more else touched

    def _take_touched(self, tab, after_edit: bool):
        """What `tab` needs to redraw: the lemmas edited since it last showed them, after an edit;
        None (everything) otherwise. Starts counting again."""
        touched = self._touched.get(tab)
        self._touched[tab] = frozenset()
        return touched if after_edit and touched else None

    def schedule_refresh(self, delay: int = 0):
        self._refresh_timer.start(delay)

    # ========================================================= theme, view
    def _restyle(self):
        """Colours that follow the theme and accent (the data views stay black on white)."""
        from . import icons as _icons
        _icons.refresh_all()                      # the drawn icons (All buttons theme coloured, the accent)
        self._notebook_icons()
        self.comparison.restyle()
        self.theme_btn.setIcon(icon("lightbulb", 22, "#e8e8e8" if theme.dark() else "#1b1b1b"))
        self.theme_btn.setToolTip("Switch to the light theme" if theme.dark() else "Switch to the dark theme")
        a = theme.accent()
        a_ = theme.accent()
        self.db_title.setStyleSheet(
            f"QLabel {{ background: {a_.name()}; color: {theme.text_on(a_).name()}; border-radius: 4px; "
            "padding: 3px 10px; font-weight: bold; }")
        h = max(self.tabs.sizeHint().height(), self.matrix_title.sizeHint().height(),
                self.texts_btn.sizeHint().height())
        for head in (self.lemma_head, self.matrix_head):   # both title rows the same height
            head.setFixedHeight(h)
        # Qt doesn't always pass a new theme down to the matrix pane (its option checkboxes stayed
        # black on white after switching to dark), so it is given the palette directly.
        self.matrix_box.setPalette(theme.interface_palette())
        for lbl in (self.lemma_title, self.matrix_title):
            lbl.setStyleSheet(f"color: {theme.colour('pitch').name()};")   # the accent, lighter on dark
        muted = theme.muted()
        for lbl in (self.lemma_count, self.all_count):
            lbl.setStyleSheet(f"color: {muted};")
        for tab in (LEMMA_TAG, TAG_TAG):
            self.count_label(tab).setStyleSheet(f"color: {muted};")
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
            f"QTabBar::tab:selected {{ background: {a.name()}; color: {theme.text_on(a).name()}; }}")
        for w in (self.lemmas, self.all_table, self.lt_view, self.tt_view):
            theme.as_data(w)
            w.viewport().update()
        for b in list(getattr(self, "_conv_buttons", [])):   # /[β]/ in the theme's text colour
            try:
                b.setIcon(self._conventions_icon())
            except RuntimeError:
                self._conv_buttons.remove(b)
        # windows already open (Texts and utterances, Bulk edit…) follow a theme change too
        from PySide6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            if w is not self and callable(getattr(w, "_restyle", None)):
                if w.isVisible():
                    w._restyle()
                else:                             # hidden (the XML viewer, Cogitate…): when next shown
                    _RestyleOnShow.mark(w)

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
        self.doc.ws_set("view", self.view_state())

    def view_state(self) -> dict:
        """The complete setup of the main window: the tab, the lemma, the matrices and swapped
        axes, the lemma list's and All data's filters, searches and pin. The workspace keeps it as
        the last view; a snapshot (Cogitate) keeps a copy of it in its link."""
        e = self.lemmas.current_row()
        view = {
            "tab": self.tabs.currentIndex(),
            "lemma": e.ref if e is not None else "",
            "switched": {KINDS[t]: on for t, on in self.switched.items()},
            "configs": [{"kind": c.kind, "name": c.name, "blank": c.blank,
                         "cell": list(c.cell), "x": [self._spec_json(x) for x in c.x],
                         "y": [self._spec_json(y) for y in c.y]} for c in self.configs.values()],
        }
        view["filters"] = {"lemma": self.lemmas.filter_state(), "alldata": self.all_table.filter_state()}
        view["search"] = {"lemma": self.lemma_search.text(), "alldata": self.all_search.text()}
        if e is not None:
            view["lemma_id"] = e.id
        return view

    def _restore_view(self):
        db = self.doc.db
        if not db.path:
            return
        view = self.doc.ws.get_dict("view")
        if view:
            self.apply_view(view)

    def apply_view(self, view: dict) -> list[str]:
        """Put back a view_state(): on opening (the workspace's last view) or from a snapshot.
        Returns what couldn't be put back (a lemma or tags since deleted), for a note."""
        db = self.doc.db
        missing = []
        try:
            names = {(m.kind, m.name) for m in db.settings.matrices}
            for c in view.get("configs", []):
                kind = c.get("kind", mx.LEMMA_TAG)
                if kind in self.configs:              # views saved before 18 October had one per class
                    continue
                cfg = mx.MatrixConfig(kind=kind, blank=bool(c.get("blank")))
                cfg.x = [self._spec_from(x) for x in c.get("x", [])]
                cfg.y = [self._spec_from(y) for y in c.get("y", [])]
                cfg.cell = list(c.get("cell") or mx.DEFAULT_CELL)
                name = c.get("name", "")
                cfg.name = name if (cfg.kind, name) in names else ""
                self.configs[cfg.kind] = cfg
            for t in (LEMMA_TAG, TAG_TAG):
                self.switched[t] = bool(view.get("switched", {}).get(KINDS[t], False))
            f = view.get("filters") or {}             # the filters, searches and pin (idea 36)
            self.lemmas.set_filter_state(f.get("lemma") or {})
            self.all_table.set_filter_state(f.get("alldata") or {})
            q = view.get("search") or {}
            self.lemma_search.setText(str(q.get("lemma", "") or ""))
            self.all_search.setText(str(q.get("alldata", "") or ""))
            ref = view.get("lemma")
            e = db.item_by_id(view.get("lemma_id") or "") if view.get("lemma_id") else None
            if e is None or e not in db.entries:
                e = db.entry_by_ref(ref) if ref else None
            if e is not None:
                self.lemmas.select_row(e)
            elif ref:
                missing.append(f"the lemma {ref}")
            known = {tg.name for tg, _ in db.settings.tags.tags()}
            gone = sorted({t for c in self.configs.values() for sp in c.x + c.y for t in sp.tags} - known)
            if gone:
                missing.append("the tags " + ", ".join(gone))
            tab = int(view.get("tab", ALL_DATA))
            if tab in (ALL_DATA, LEMMA_TAG, TAG_TAG):
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(tab)
                self.tabs.blockSignals(False)
                self._tab_changed(tab)
        except (TypeError, ValueError, AttributeError, KeyError):
            pass                                  # an unreadable view is simply forgotten
        return missing

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
        self.refresh()

    def _jump_to_lemma(self, entry):
        """Double-clicking a lemma in Lemma/Tag selects it in the lemma list."""
        self.lemmas.select_row(entry)
        self.lemmas.setFocus()

    def _lemma_selected(self):
        tab = self.tabs.currentIndex()
        if tab == TAG_TAG:
            self.refresh()

    def config_for(self, tab) -> mx.MatrixConfig:
        key = KINDS[tab]
        if key not in self.configs:
            self.configs[key] = mx.MatrixConfig(kind=key)
        return self.configs[key]

    def _fill_saved(self, tab):
        cb = (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["saved"]
        cfg = self.config_for(tab)
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("(current)" if (cfg.x or cfg.y) else "(blank)")
        names = [m.name for m in self.doc.db.settings.matrices if m.kind == cfg.kind]
        model = cb.model()
        for label, depth, name in mx.matrix_tree(names):   # groups by > (idea 37)
            cb.addItem("\u2003" * depth + label, name)
            row = cb.count() - 1
            if name is None:                    # only a heading: not a matrix of its own
                item = model.item(row)
                if item is not None:
                    item.setEnabled(False)
                    f = item.font()
                    f.setItalic(True)
                    item.setFont(f)
            else:
                cb.setItemData(row, mx.shown_matrix_name(name), Qt.ToolTipRole)
        i = cb.findData(cfg.name) if cfg.name else 0
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)

    def _saved_chosen(self, tab, i):
        if i <= 0:
            return
        cb = (self.lt_bar if tab == LEMMA_TAG else self.tt_bar)["saved"]
        cfg = self.config_for(tab)
        name = cb.itemData(i)
        if not name:
            return                              # a group heading
        for m in self.doc.db.settings.matrices:
            if m.kind == cfg.kind and m.name == name:
                self.configs[cfg.kind] = m.copy()
        self.refresh()

    def _hide_empty_toggled(self, on):
        self.doc.ws_set(HIDE_EMPTY, bool(on) or None)
        self._apply_hide_empty()
        self.lemmas.proxy.refilter()

    def _apply_hide_empty(self):
        """The lemma list leaves out lemmas with no token data while Hide empty lemmas is on (idea 55)."""
        on = self.hide_empty.isChecked()
        self.lemmas.proxy.extra = (lambda e: any(t.has_content() for t in e.tokens)) if on else None

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._scan_key = None                 # back from another program: list the folder again

    def _scan_sound_folder(self, force: bool = False):
        """Which recordings are in Soundfiles/Tokens (and online-only). Listed again only when the
        folder has changed (a file added, removed or renamed: every recording is saved by renaming)
        or Lemmatrix has just become the active window again (Explorer, Praat, OneDrive may have
        changed something); every refresh listed all 58,000 files before (25 October)."""
        folder = storage.sound_folder(self.doc.db)
        try:
            key = (str(folder), folder.stat().st_mtime_ns)
        except OSError:
            key = (str(folder), None)
        scanned = force or key != getattr(self, "_scan_key", None) or not hasattr(self, "sound_files")
        if scanned:
            self.sound_files, self.cloud_files = storage.scan_sound_folder(folder)
            self._scan_key = key
        for v in (self.lt_view, self.tt_view):
            v.sound_files = self.sound_files
            v.cloud_files = self.cloud_files
        return scanned

    def refresh(self, after_edit: bool = False):
        """The tab shown, again. after_edit: called for an edit (_doc_changed), so All data
        redraws, and Lemma/Tag measures again, only the lemmas it changed."""
        if hasattr(self, "_view_timer"):
            self._view_timer.start()              # the lemma or matrix shown may have changed
        db = self.doc.db
        tab = self.tabs.currentIndex()
        touched = self._take_touched(tab, after_edit)
        if self._scan_sound_folder():
            touched = None                        # a recording's colour may have changed anywhere
        visible = self.lemmas.visible_rows()
        pin = self.lemmas.pinned_row()
        pins = self.lemmas.pinned_rows() if pin is None and self.lemmas.proxy.pinned else []
        self.lemma_count.setText(f"{len(visible)} / {len(db.entries)}")
        self.lemma_count.setToolTip(f"{len(visible)} of {len(db.entries)} lemmas shown"
                                    + (f"\nOnly {pin.ref} {db.lemma(pin)}: Alt+click it again to show all"
                                       if pin is not None else "")
                                    + (f"\n{len(pins)} lemmas pinned: Alt+click a lemma, or Clear all "
                                       "filters, to show all" if pins else ""))
        only_data = self.only_data.isChecked()
        if tab == ALL_DATA:
            vis = set(map(id, visible))
            rows = [TokenRow(e, i) for e in db.entries if id(e) in vis
                    and (not only_data or any(t.has_content() for t in e.tokens))
                    for i in range(len(e.tokens))]
            self.all_table.set_rows(rows, touched)
            if not getattr(self, "_all_sized", False) and rows:
                self.all_table.resizeColumnsToContents()
                self._all_sized = True
            self._update_counts()
            return
        cfg = self.config_for(tab)
        self._fill_saved(tab)
        if tab == LEMMA_TAG:
            ents = list(visible)
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
            count = self.count_label(tab)
            count.setText(f"{len(ents)} lemmas shown of {len(db.entries)}{hidden}" if cfg.x else "")
        else:
            e = self.lemmas.current_row()
            if e is not None and e not in visible:
                e = None
            if only_data and e is not None and not any(t.has_content() for t in e.tokens):
                lay = mx.Layout(message="This lemma has no token data (Show only lemmas with token "
                                        "data is on).")
            else:
                lay = mx.tag_tag_layout(db, e, cfg)
            view = self.tt_view
            count = self.count_label(tab)
            count.setText(f"{e.ref}  {db.lemma(e)}  {widgets.meaning(db.gloss(e))}"
                                    + (f"  ·  {db.word_class(e)}" if db.word_class(e) else "") if e else "")
        if lay.message:
            count.setText((count.text() + "  ·  " if count.text() else "") + lay.message)
        if self.switched[tab]:
            lay = lay.transposed()
        self.layouts[tab] = lay
        view.aligned = self.aligned_set()
        from .. import pitchview                  # pitch hidden: no drawing or Pitch line (idea 9)
        view.set_layout(lay, pitchview.visible(cfg.cell, db.settings, pitchview.TOKENS),
                        changed=touched if tab == LEMMA_TAG else None)

    def _update_counts(self):
        shown = self.all_table.proxy.rowCount()
        total = self.all_table.model_.rowCount()
        n = self.all_table.active_filters()
        self.all_count.setText(f"{shown} / {total}")
        self.all_count.setToolTip(f"{shown} of {total} tokens shown"
                                  + (f"\n{n} column filter{'s' if n != 1 else ''} on" if n else ""))

    def switch_axes(self, tab):
        if tab == ALL_DATA:
            return
        self.switched[tab] = not self.switched[tab]
        self.refresh()

    def configure_cell(self, tab):
        cfg = self.config_for(tab)
        dlg = ConfigureCellDialog(self, self.doc.db, cfg.cell, self.aligned_set())
        if dlg.exec():
            cfg.cell = dlg.chosen()
            db = self.doc.db
            aligned = self.aligned_set()
            for k, on in dlg.aligned().items():
                aligned -= {k, mx.line_key(db, k)}
                if on:
                    aligned.add(mx.line_key(db, k))
            self.set_aligned(aligned)
            self.refresh()

    # ---- which lines line up word by word (idea 2), one setting for every cell view -----------
    def aligned_set(self) -> set[str]:
        """The keys of the fields that line up (Phonemic, Morphemes, Translation:en…), in the
        workspace; Phonemic and Morphemes at first."""
        saved = self.doc.ws.get_list("lines/aligned")
        if saved == ["-"]:
            return set()
        if saved:
            return set(saved)
        s = self.doc.db.settings
        return {f.name for f in s.token_fields if f.role in ("phonemic", "morphemes")}

    def set_aligned(self, keys: set[str]):
        self.doc.ws_set("lines/aligned", sorted(keys) or ["-"])
        for v in (self.lt_view, self.tt_view):
            v.aligned = set(keys)
        w = self.utterances_window
        if w is not None:
            w.texts._apply_view()

    def move_matrix_column(self, tab, old: int, new: int):
        """A column dragged to another place (21 October): its line moves in the matrix's
        configuration (the rows' list when the axes are swapped), as Configure matrix's arrows would."""
        cfg = self.config_for(tab)
        if self.switched[tab]:
            if tab != TAG_TAG:
                return                            # lemmas along the top: their order is the lemma list's
            lines = cfg.y
        else:
            lines = cfg.x
        if not (0 <= old < len(lines) and 0 <= new < len(lines)):
            return
        new_cfg = cfg.copy()
        target = new_cfg.y if lines is cfg.y else new_cfg.x
        target.insert(new, target.pop(old))
        new_cfg.name = ""                         # as after Configure matrix: it's now the current one
        self.configs[cfg.kind] = new_cfg
        self.refresh()

    def configure_matrix(self, tab):
        cfg = self.config_for(tab)
        ents = self.lemmas.visible_rows()
        dlg = ConfigureMatrixDialog(self, self.doc.db, cfg, ents)
        if dlg.exec():
            new = dlg.result_config()
            new.name = ""
            self.configs[cfg.kind] = new
            self.refresh()

    def save_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.x or (tab == TAG_TAG and not cfg.y):
            QMessageBox.information(self, "Save matrix", "Configure the matrix first.")
            return
        mats = self.doc.db.settings.matrices
        existing = [m.name for m in mats if m.kind == cfg.kind]
        name = ask_matrix_name(self, existing, cfg.name)
        if not name:
            return
        saved = cfg.copy()
        saved.name = name
        mats[:] = [m for m in mats if not (m.kind == saved.kind and m.name == name)] + [saved]
        self.configs[cfg.kind] = saved.copy()
        self.doc.workspace_changed()              # saved matrices are in the workspace (idea 36)

    def rename_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.name:
            QMessageBox.information(self, "Rename matrix", "Choose a saved matrix first.")
            return
        mats = self.doc.db.settings.matrices
        same = [m for m in mats if m.kind == cfg.kind]
        name = ask_matrix_name(self, [m.name for m in same], cfg.name, "Rename matrix", replace=False)
        if not name or name == cfg.name:
            return
        for m in same:
            if m.name == cfg.name:
                m.name = name
        cfg.name = name
        self.doc.workspace_changed()

    def clear_matrix(self, tab):
        """Back to a blank view: no rows or columns, nothing chosen."""
        cfg = self.config_for(tab)
        new = mx.MatrixConfig(kind=cfg.kind, cell=list(cfg.cell), blank=True)
        self.configs[cfg.kind] = new
        self.refresh()

    def delete_saved_matrix(self, tab):
        cfg = self.config_for(tab)
        if not cfg.name:
            QMessageBox.information(self, "Delete matrix", "Choose a saved matrix first.")
            return
        if not _w.ask(self, "Delete matrix", f"Delete the saved matrix “{cfg.name}”?", "Delete matrix"):
            return
        mats = self.doc.db.settings.matrices
        mats[:] = [m for m in mats if not (m.kind == cfg.kind and m.name == cfg.name)]
        cfg.name = ""
        self.doc.workspace_changed()

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

    def _open_dialog(self, slots, index, tab, record: bool = False):
        if not slots:
            return
        self.dialog_autoplay = self.autoplay.isChecked() and not record
        dlg = TokenDialog(self, slots, index)
        if record:                                # Ctrl+R: open it and start recording straight away
            QTimer.singleShot(0, dlg._record)
        dlg.exec()
        dlg.deleteLater()                         # not kept, hidden, under the main window
        self.refresh()

    def _cell_activated(self, tab, r, c, n, record: bool = False):
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
        self._open_dialog(slots, idx, tab, record)

    def _token_clicked(self, tab, r, c, n):
        if n >= 0 and self.autoplay.isChecked():
            self.play_selected()

    def _cell_edited(self, row, key, text):
        s = self.doc.db.settings
        name, _, lang = key[2:].partition(":")      # f:Translation, or f:Translation:ar
        f = s.token_field(name)
        if f.role == "pitch":
            from .. import pitch as pitchmod
            text = pitchmod.normalise(text)

        def change(e, i=row.index):
            e.tokens[i].set(name, text.strip(), (lang or s.primary_gloss) if f.multilingual else None,
                            f.multilingual)
        self.doc.edit_entry(row.entry, change, f"Edit {f.title}" + (f" ({lang})" if lang else ""))

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
        if f.closed and text and text not in f.all_values():
            f.add_value(text)
            self.doc.settings_changed()

        def change(e):
            e.set(name, text, lang or None, f.multilingual)
        self.doc.edit_entry(entry, change, f"Edit {f.title}")

    def selected_token(self):
        """(entry, token index) of the selected token in the current tab, or None."""
        tab = self.tabs.currentIndex()
        if tab == ALL_DATA:
            r = self.all_table.selected_row()
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
        # All data (Josh, 21 October): a selected token's lemma; with no token selected (a click on
        # a selected row unselects it), the lemma selected in the lemma list.
        row = self.all_table.selected_row() if tab == ALL_DATA else None
        entry = row.entry if row else self.lemmas.current_row()
        if entry is None:
            QMessageBox.information(self, "Add token", "Select a lemma first.")
            return
        self._open_dialog([Slot(entry, None, (), explicit=True, defaults=True)], 0, tab)

    def add_token_to_lemma(self):
        """λ→τ, Create token for this lemma: a new token of the lemma list's selected lemma,
        whatever is selected in the matrix (21 October). With several lemmas selected, the batch
        box (idea 64): one token per lemma and per combination of the tags picked."""
        if len(self.lemmas.selected_rows()) > 1:
            self.batch_tokens()
            return
        entry = self.lemmas.current_row()
        if entry is None:
            QMessageBox.information(self, "Create token", "Select a lemma first.")
            return
        self._open_dialog([Slot(entry, None, (), explicit=True, defaults=True)], 0, self.tabs.currentIndex())

    def edit_token(self, record: bool = False):
        tab = self.tabs.currentIndex()
        if tab != ALL_DATA:
            view = self._view(tab)
            if view.selected:
                self._cell_activated(tab, *view.selected, record=record)
            return
        sel = self.selected_token()
        if sel is None:
            return
        slots = self._slots(tab)
        e, i = sel
        idx = next((k for k, s in enumerate(slots) if s.entry is e and s.index == i), 0)
        self._open_dialog(slots, idx, tab, record)

    def record_selected(self):
        """Ctrl+R: open the selected token (an empty matrix cell: a new one) and start recording."""
        self.edit_token(record=True)

    def delete_tokens(self, rows) -> bool:
        """Delete several tokens selected in All data (Josh, 24 October): asked once, one undo step;
        their recordings are held as for one (undo brings them back)."""
        db = self.doc.db
        pairs_ = [(r.entry, r.entry.tokens[r.index]) for r in rows if 0 <= r.index < len(r.entry.tokens)]
        if not pairs_:
            return False
        gone = {id(t) for _, t in pairs_}
        lemmas = {id(e) for e, _ in pairs_}
        if not _w.ask(self, "Delete tokens",
                                f"Delete {len(pairs_)} tokens of {len(lemmas)} lemma(s)?\n"
                                "Their recordings go to the Recycle Bin when the database is closed; "
                                "until then, undo brings them back.", f"Delete {len(pairs_)} tokens"):
            return False
        folder = storage.sound_folder(db)
        renames = []
        if self.prefs.delete_recordings_with_tokens:
            self.player.stop()
            # each recording held once, though several of the selected tokens share it (the second
            # hold failed and rolled the whole delete back: the audit, 25 October)
            held = set()
            for e, t in pairs_:
                shared = bool(t.file) and any(o.file == t.file and id(o) not in gone
                                              for en in db.entries for o in en.tokens)
                path = folder / t.file if t.file else None
                if path is not None and not shared and path.exists() and str(path).lower() not in held:
                    held.add(str(path).lower())
                    renames.append((path, self.doc.hold_recording(path)))
        changed = []
        for e in db.entries:
            if id(e) in lemmas:
                c = e.copy()
                c.tokens = [ct for ct, ot in zip(c.tokens, e.tokens) if id(ot) not in gone]
                changed.append((e, c))
        problems = self.doc.apply_changes(f"Delete {len(pairs_)} tokens", changed, renames, stamp=False)
        if problems:
            QMessageBox.warning(self, "Delete tokens", "\n".join(problems))
            return False
        return True

    def delete_token(self):
        if self.tabs.currentIndex() == ALL_DATA and len(rows := self.all_table.selected_rows()) > 1:
            self.delete_tokens(rows)
            return
        sel = self.selected_token()
        if sel is None:
            return
        e, i = sel
        t = e.tokens[i]
        db = self.doc.db
        tags = " + ".join(mx.chips(db, t.tags)) or "citation"
        shared = bool(t.file) and any(o is not t and o.file == t.file for en in db.entries for o in en.tokens)
        with_file = bool(t.file) and self.prefs.delete_recordings_with_tokens and not shared
        msg = f"Delete the {tags} token of {e.ref} {db.lemma(e)}?"
        if with_file:
            msg += f"\nIts recording ({t.file}) goes to the Recycle Bin when the database is closed; " \
                   "until then, undo brings it back."
        elif shared:
            msg += f"\nIts recording ({t.file}) stays: another token uses it too."
        if not _w.ask(self, "Delete token", msg, "Delete token"):
            return
        renames = []
        if with_file:
            path = storage.sound_folder(db) / t.file
            self.player.stop()
            if path.exists():                     # held, so undo can bring it back
                held = self.doc.hold_recording(path)
                try:
                    path.rename(held)
                    renames.append((path, held))
                except OSError as exc:
                    QMessageBox.warning(self, "Delete token", f"Couldn't move {t.file} aside: {exc}. "
                                        "The token is deleted; its recording stays in the sound folder.")
        self.doc.edit_entry(e, lambda en, i=i: en.tokens.pop(i), f"Delete token from {e.ref}",
                            renames=renames)

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
        from .. import pitchview
        if not pitchview.shown(pitchview.TOKENS):
            return                                # Ctrl+Shift+Space does nothing with pitch hidden (idea 9)
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

    def open_in_praat(self, path, parent=None, textgrid=None, select=None):
        from .. import praat
        parent = parent or self
        if path is None:
            QMessageBox.information(parent, "Open in Praat", "This token has no recording yet.")
            return
        exe = self.prefs.praat_path
        if not exe or not praat.executable(exe).exists():
            QMessageBox.information(parent, "Open in Praat",
                                    "Lemmatrix doesn't know where Praat is yet. Please show it where "
                                    "Praat is (you can change this later in File → Settings → Sound).")
            exe = self.ask_praat_path(parent)
            if not exe:
                return
        try:
            praat.open_sound(exe, path, textgrid, select)
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
        from .. import pitchview
        return [("Play\tCtrl+Space", "play", self.play_selected, has_sound),
                *([("Play pitch\tCtrl+Shift+Space", "play-pitch", self.play_selected_pitch, has_pitch)]
                  if pitchview.shown(pitchview.TOKENS) else []),
                ("Open in Praat\tCtrl+Alt+Space", "praat", self.open_selected_in_praat, has_sound)]

    # ---- context menus -------------------------------------------------
    def _menu(self, items, pos):
        m = QMenu(self)
        for item in items:
            if item is None:
                m.addSeparator()
                continue
            text, icon_name, fn = item[:3]
            if isinstance(icon_name, QIcon):          # an icon already drawn (ɛλicit's)
                ic = icon_name
            else:
                ic = themed_icon(icon_name, 16) if icon_name else None
            a = m.addAction(ic, text) if ic else m.addAction(text)
            a.setEnabled(item[3] if len(item) > 3 else True)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    def _lemma_menu(self, row, pos):
        if row is not None and not any(r is row for r in self.lemmas.selected_rows()):
            self.lemmas.select_row(row)           # a right-click inside the selection keeps it
        sel = self.lemmas.selected_rows()
        many = len(sel) > 1
        pinned = self.lemmas.proxy.pinned is not None
        self._menu([*self._spelling_items(self.lemmas, pos, row), ("Add lemma", "add", self.add_entry),
                    (f"Delete {len(sel)} lemmas" if many else "Delete lemma", "delete", self.delete_entry),
                    ("Edit lemma", "edit", self.edit_entry),
                    (f"Create tokens for the {len(sel)} selected lemmas…" if many else "Create token for this lemma",
                     "lemma-token", self.add_token_to_lemma, row is not None),
                    ("Show all lemmas again" if pinned else
                     (f"Show only the {len(sel)} selected lemmas" if many else "Show only this lemma"),
                     None, (lambda: self.lemmas.pin_rows([])) if pinned else (lambda: self.lemmas.pin_rows(sel)),
                     pinned or bool(sel)),
                    ("Add the citation token" + ("s" if many else "") + " to the ɛλicit request",
                     elicit_icon(16), lambda: self.add_citations_to_elicit(sel), bool(sel)),
                    *([("Insert EACW items…", "add", lambda: self.insert_eacw_items(row))]
                      if wordlists.is_eacw(self.doc.db) else []), None,
                    ("Configure columns", "gear-columns", self.configure_lemma_columns),
                    ("Clear all filters", "reset-filters", self._clear_lemma_filters)], pos)

    # ---- spelling (section 5.10) -----------------------------------------
    def _spell_delegates(self):
        """Red lines under unknown words in the lemma list's English gloss."""
        g = self.doc.db.settings.entry_field("gloss")
        if g is not None:
            self.lemmas.set_delegate(f"{g.name}:{spelling.LANG}", SpellDelegate(self.speller, self.lemmas))

    def spelling_spans(self, text: str) -> list:
        """The unknown words in a text, for the underlines (none when they're turned off)."""
        if not self.prefs.underline_spelling:
            return []
        return self.spell_checker.misspelled(text)

    def add_spelling_word(self, word: str):
        """Count a word as spelled correctly from now on: it goes into the database's word list."""
        s = self.doc.db.settings
        word = word.strip()
        if not word or word.lower() in {w.lower() for w in s.spelling_words}:
            return
        s.spelling_words.append(word)
        self.spell_checker.set_words(s.spelling_words)
        self.doc.workspace_changed()              # the word list is in the workspace (idea 36)
        self._repaint_spelling()
        self.statusBar().showMessage(f"“{word}” added to the database's word list.", 5000)

    def _repaint_spelling(self):
        for t in (self.lemmas, self.all_table):
            t.viewport().update()
        for w in QApplication.topLevelWidgets():
            if w.isVisible():
                w.update()
                for ed in w.findChildren(spellui.SpellOverlay):
                    ed.update()

    def set_spelling_underlines(self, on: bool):
        self.prefs.underline_spelling = bool(on)
        self._repaint_spelling()

    def check_spelling(self):
        """Tools → Check spelling…: a window of its own, beside the main one."""
        from .spelling_dialog import SpellingWindow
        bring_forward(self._window("spelling_window", SpellingWindow))

    def _spelling_items(self, table, pos, row) -> list:
        """Right-click on an underlined gloss or translation: its corrections and Add to the word list."""
        if row is None or not self.prefs.underline_spelling:
            return []
        idx = table.indexAt(table.viewport().mapFromGlobal(pos))
        if not idx.isValid():
            return []
        key = table.model_.columns[idx.column()].key
        db = self.doc.db
        g = db.settings.entry_field("gloss")
        tname = predict.translation_field(db)
        lang = spelling.LANG
        if table is self.lemmas and g is not None and key == f"{g.name}:{lang}":
            entry, index, name = row, None, g.name
        elif table is self.all_table and key == "gloss" and g is not None and db.settings.primary_gloss == lang:
            entry, index, name = row.entry, None, g.name
        elif table is self.all_table and tname and key == "f:" + tname and db.settings.primary_gloss == lang:
            entry, index, name = row.entry, row.index, tname
        else:
            return []
        text = entry.get(name, lang) if index is None else entry.tokens[index].get(name, lang)
        items = []
        for word in list(dict.fromkeys(w for _, _, w in self.spell_checker.misspelled(text)))[:3]:
            def replace(new, word=word, entry=entry, index=index, name=name):
                def change(e):
                    target = e if index is None else e.tokens[index]
                    target.set(name, spelling.replace_word(target.get(name, lang), word, new), lang, True)
                self.doc.edit_entry(entry, change, f"Spelling: {word} → {new}")
            items += spellui.spelling_items(word, self.speller, replace) + [None]
        return items

    # ---- predicted translations in All data (section 5.9) ----------------
    def _predicts(self, f) -> bool:
        """Whether this token field gets suggestions: the translation, shown in English."""
        return f.role == "translation" and not f.closed and self.doc.db.settings.primary_gloss == predict.LANG

    def suggestion_for(self, row):
        """The predicted translation for an All data row whose English translation is empty."""
        if row is None:
            return None
        db = self.doc.db
        name = predict.translation_field(db)
        if not name or row.token.get(name, predict.LANG):
            return None
        if self._suggestions_stale:              # worked out again after any change
            self.doc.predictor.refresh(db)
            self._suggestions.clear()
            self._suggestions_stale = False
        key = (row.entry.id, tuple(row.token.tags))
        if key not in self._suggestions:
            self._suggestions[key] = self.doc.predictor.suggest(db, row.entry, row.token.tags, refresh=False)
        return self._suggestions[key]

    def accept_suggestion(self, row=None):
        """Right-click → Accept suggested translation: the row's suggestion becomes its translation."""
        row = row or self.all_table.current_row()
        sug = self.suggestion_for(row)
        if sug is None:
            return
        name = predict.translation_field(self.doc.db)

        def change(e, i=row.index, text=sug.text):
            e.tokens[i].set(name, text, predict.LANG, True)
        self.doc.edit_entry(row.entry, change, "Accept suggested translation")

    def _all_menu(self, row, pos):
        self.all_table.keep_selection(row)        # a right-click inside the selection keeps it
        rows = self.all_table.selected_rows()
        accept = ([None, ("Accept suggested translation", "", lambda r=row: self.accept_suggestion(r))]
                  if self.suggestion_for(row) else [])
        if len(rows) > 1:                         # several tokens: what acts on them all
            toks = [r.entry.tokens[r.index] for r in rows]
            self._menu([("Add token", "add", self.add_token),
                        (f"Delete {len(rows)} tokens", "delete", self.delete_token), None,
                        (f"Add {len(rows)} tokens to the ɛλicit request", elicit_icon(16),
                         lambda: self.add_to_elicit(toks)), None,
                        ("Configure columns", "gear-columns", self.configure_all_columns),
                        ("Clear all filters", "reset-filters", self._clear_all_filters)], pos)
            return
        self._menu([*self._spelling_items(self.all_table, pos, row),("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), self._move_item(), *accept, None,
                    *self._token_items(), self.elicit_menu_item(self._selected_token_obj()),
                    self.hypothesis_menu_item(self.selected_token() is not None),
                    *self._pitch_items(self._pitch_column_at(pos)), *self._same_tags_items(row, pos), None,
                    ("Configure columns", "gear-columns", self.configure_all_columns),
                    ("Clear all filters", "reset-filters", self._clear_all_filters)], pos)

    def _matrix_menu(self, tab, pos):
        self._menu([("Add token", "add", self.add_token), ("Delete token", "delete", self.delete_token),
                    ("Edit token", "edit", self.edit_token), self._move_item(), None, *self._token_items(),
                    self.elicit_menu_item(self._selected_token_obj()),
                    self.hypothesis_menu_item(self.selected_token() is not None), *self._pitch_items()], pos)

    def _move_item(self):
        return ("Move to another lemma…", "move-token", self.move_token, self.selected_token() is not None)

    def move_token(self):
        """Move the selected token (with its recording) to another lemma: one undo step."""
        from .. import move as mv
        from .move_dialog import MoveTokenDialog
        sel = self.selected_token()
        if sel is None:
            QMessageBox.information(self, "Move token", "Select a token first.")
            return
        db = self.doc.db
        source, index = sel
        dlg = MoveTokenDialog(self, db, source, index, self.prefs.ipa_size)
        if not dlg.exec() or dlg.chosen() is None:
            return
        target = dlg.chosen()
        folder = storage.sound_folder(db)
        plan = mv.plan(db, [sel], target, folder)
        if not plan.moves:
            return
        add_examples = False
        if plan.clashes:
            m = plan.clashes[0]
            found = db.settings.tags.find(m.example)
            code = found[0].display() if found else "x" + m.example.rsplit(" ", 1)[-1]
            box = QMessageBox(QMessageBox.Question, "Same tags",
                              f"{m.clash}.\n\nAdd the example tag {code}, so its recording gets a name of "
                              "its own?", parent=self)
            add = box.addButton(f"Add {code}", QMessageBox.AcceptRole)
            keep = box.addButton("Move it as it is", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(add)
            box.exec()
            if box.clickedButton() not in (add, keep):
                return
            add_examples = box.clickedButton() is add
        self.player.stop()
        pairs, renames, grew = mv.changes(db, plan, folder, add_examples)
        trouble = self.doc.apply_changes(f"Move token to {target.ref}", pairs, renames, stamp=False)
        if trouble:
            QMessageBox.warning(self, "Move token", "The token wasn't moved:\n" + "\n".join(trouble))
            return
        if grew:
            self.doc.settings_changed()
        moved = plan.moves[0].token
        idx = next((i for i, t in enumerate(target.tokens) if t.id == moved.id), None)
        notes = mx.unusual_notes(db, target, moved.tags) if self.prefs.warn_unusual_tags else []
        msg = f"Moved the token to {target.ref} {db.lemma(target)}."
        if notes:
            msg += " Its tags aren't all usual for this lemma's word class (marked)."
        if moved.file and not db.settings.auto_update_names and moved.file != db.expected_filename(target, moved):
            msg += " Its recording's name is out of date (Update file name)."
        if plan.problems:
            QMessageBox.information(self, "Move token", msg + "\n\nNot renamed:\n" + "\n".join(plan.problems))
        self.statusBar().showMessage(msg, 10000)
        if idx is not None and self.tabs.currentIndex() == ALL_DATA:   # shown where it went, if it's in view
            row = TokenRow(target, idx)
            if row in self.all_table.visible_rows():
                self.all_table.select_row(row)

    def _same_tags_items(self, row, pos) -> list:
        """On the Tags column: Filter for same, the Tags filter set to exactly this token's tags."""
        idx = self.all_table.indexAt(self.all_table.viewport().mapFromGlobal(pos))
        if row is None or not idx.isValid() or self.all_table.model_.columns[idx.column()].key != "tags":
            return []
        return [None, ("Filter for same", "", lambda r=row: self.all_table.filter_same_tags(r))]

    def _pitch_column_at(self, pos) -> bool:
        """Whether the right-click in All data is on the pitch field (its digits or its drawing)."""
        idx = self.all_table.indexAt(self.all_table.viewport().mapFromGlobal(pos))
        if not idx.isValid():
            return False
        key = self.all_table.model_.columns[idx.column()].key
        f = self._pitch_field()
        return key == "drawing" or (f is not None and key == "f:" + f.name)

    def _pitch_field(self):
        return next((f for f in self.doc.db.settings.token_fields if f.role == "pitch"), None)

    def _pitch_items(self, show: bool = True) -> list:
        """Raise pitch and Lower pitch for the selected token: Bulk edit's shortcut, for one token."""
        sel = self.selected_token()
        f = self._pitch_field()
        from .. import pitchview
        if (not show or sel is None or f is None or not pitchview.shown(pitchview.TOKENS)
                or not sel[0].tokens[sel[1]].get(f.name).strip()):
            return []
        text = sel[0].tokens[sel[1]].get(f.name)
        s = self.doc.db.settings
        items = [None]
        for label, step in (("Raise pitch", 1), ("Lower pitch", -1)):
            try:
                bulk.shift_pitch(text, step, s.pitch_low, s.pitch_high)
                ok = True
            except bulk.RowError:
                ok = False                       # past the display range: greyed, as in Bulk edit
            items.append((label, "", lambda step=step: self.shift_selected_pitch(step), ok))
        return items

    def shift_selected_pitch(self, step: int):
        sel = self.selected_token()
        f = self._pitch_field()
        if sel is None or f is None:
            return
        entry, index = sel
        s = self.doc.db.settings
        try:
            new = bulk.shift_pitch(entry.tokens[index].get(f.name), step, s.pitch_low, s.pitch_high)
        except bulk.RowError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            return

        def change(e, i=index):
            e.tokens[i].set(f.name, new)
        self.doc.edit_entry(entry, change, "Raise pitch" if step > 0 else "Lower pitch")

    def _clear_lemma_filters(self, toggles: bool = True):
        """Clear all filters (the lemma list): the search, the column filters, the pin, and Hide
        empty lemmas (idea 74, Josh, 26 October)."""
        self.lemma_search.clear()
        self.lemmas.clear_filters()
        if toggles and self.hide_empty.isChecked():
            self.hide_empty.setChecked(False)

    def _clear_all_filters(self, toggles: bool = True):
        """Clear all filters (All data): the search, the column filters, and Hide empty tokens (idea 74)."""
        self.all_search.clear()
        self.all_table.clear_filters()
        if toggles and self.only_data.isChecked():
            self.only_data.setChecked(False)

    # ============================================================= entries
    def add_entry(self):
        dlg = EntryDialog(self, self.doc.db)
        if dlg.exec():
            e = dlg.new_entry(self.session_speaker(), self.session_date())
            self.doc.add_entry(e, self._entry_place(e))
            self.lemmas.set_rows(self.doc.db.entries)
            self.lemmas.select_row(e)

    def new_lemma_for(self, parent, words: str, field: str, lang: str = ""):
        """New lemma… in Create token (idea 31): the lemma dialogue, with the words as the gloss
        (from a translation) or the lemma form (from a transcription) to start with; the words go
        into its citation token's field too. Returns the new entry, or None if cancelled."""
        db = self.doc.db
        s = db.settings
        f = s.token_field(field)
        dlg = EntryDialog(parent, db)
        role = f.role if f is not None else ""
        target = s.entry_field("gloss") if role == "translation" else \
            s.entry_field("lemma") if role in ("phonetic", "phonemic") else None
        if target is not None:
            ed = dlg.fields.get((target.name, (lang or s.primary_gloss) if target.multilingual else ""))
            if ed is not None and hasattr(ed, "setText"):
                ed.setText(words)
        if not dlg.exec():
            return None
        e = dlg.new_entry(self.session_speaker(), self.session_date())
        if e.tokens and f is not None:
            e.tokens[0].set(field, words, (lang or s.primary_gloss) if f.multilingual else None, f.multilingual)
        self.doc.add_entry(e, self._entry_place(e))
        self.lemmas.set_rows(db.entries)
        return e

    def _entry_place(self, e) -> int | None:
        """Where a new lemma goes: in an EACW database at its place in the list's order, items and
        the researcher's own references alike (Josh, 23 October); otherwise at the end."""
        db = self.doc.db
        return wordlists.insert_position(db.entries, e.ref) if wordlists.is_eacw(db) else None

    def edit_entry(self):
        e = self.lemmas.current_row()
        if e is None:
            return
        dlg = EntryDialog(self, self.doc.db, e)
        if dlg.exec():
            self.doc.edit_entry(e, dlg.apply, f"Edit {e.ref}")

    def open_utterances(self, select=None):
        """View → Texts and utterances (Ctrl+U): a window of its own beside the main one."""
        from .utterances import TextsUtterancesWindow
        w = self._window("utterances_window", TextsUtterancesWindow)
        if isinstance(select, bool):              # a menu's "checked" flag, not an utterance
            select = None
        if not w.isVisible() and select is None:  # opened afresh: on the Texts tab
            from .utterances import TEXTS
            w.tabs.setCurrentIndex(TEXTS)
        bring_forward(w)
        if select is not None:
            w.select(select)
        return w

    def open_bulk_edit(self):
        """Edit → Bulk edit…: change many lemmas or tokens at once, in a window of its own."""
        from .bulk_window import BulkEditWindow
        bring_forward(self._window("bulk_window", BulkEditWindow))

    def delete_entry(self):
        sel = self.lemmas.selected_rows()
        if len(sel) > 1:                          # several selected (idea 64): asked once, one undo step
            n = sum(len(e.tokens) for e in sel)
            refs = ", ".join(e.ref for e in sel[:8]) + (" …" if len(sel) > 8 else "")
            if not _w.ask(self, "Delete lemmas",
                                    f"Delete {len(sel)} lemmas ({refs}) and their {n} token(s)?\n"
                                    "Their recordings stay in the sound folder. You can undo this.", f"Delete {len(sel)} lemmas"):
                return
            gone = set(map(id, sel))
            self.doc.restructure(f"Delete {len(sel)} lemmas", [e for e in self.doc.db.entries if id(e) not in gone])
            return
        e = self.lemmas.current_row()
        if e is None:
            return
        n = len(e.tokens)
        if not _w.ask(self, "Delete lemma",
                                f"Delete {e.ref} {self.doc.db.lemma(e)} and its {n} token(s)?\n"
                                "Its recordings stay in the sound folder. You can undo this.", "Delete lemma"):
            return
        self.doc.delete_entry(e)

    # ============================================================ settings
    def edit_metadata(self, focus: str = ""):
        from .. import pitchkind
        dlg = MetadataDialog(self, self.doc.db)
        if focus == "pitch kind":
            dlg.pitch_kind.setFocus()
        before = self.doc.settings_snapshot()     # OK with nothing changed: not unsaved
        if dlg.exec():
            dlg.apply()
            new = dlg.pitch_kind.currentData()
            if new != pitchkind.kind(self.doc.db):
                self.convert_pitch_kind(new)      # its own undo step (idea 9)
            self.doc.settings_changed(before)
            self._fill_session()
            self._fill_db_title()
            self._setup_columns()
            self._maybe_update_names()

    def convert_pitch_kind(self, new: str) -> bool:
        """Convert the database's pitch kind (idea 9). Data the new kind doesn't show is kept hidden
        unless selected for deleting (after the full-backup question); one undo step."""
        from .. import pitchkind
        from .pitchkind_dialog import BACKUP_FIRST, CANCEL, DELETE, ConvertDialog, ask_backup
        db = self.doc.db
        holding = pitchkind.holdings(db, new)
        delete = set()
        if holding:
            dlg = ConvertDialog(self, db, new, holding)
            dlg.exec()
            if dlg.answer == CANCEL:
                return False
            if dlg.answer == DELETE:
                b = ask_backup(self)
                if b == CANCEL:
                    return False
                if b == BACKUP_FIRST and not self.full_backup():
                    return False                  # the backup didn't happen: nothing deleted
                delete = dlg.ticked()
        done = self.doc.convert_pitch_kind(new, delete)
        self.statusBar().showMessage(f"Pitch kind: {pitchkind.LABELS[new]}"
                                     + (". " + "; ".join(done) if done else "") + ".", 8000)
        return True

    def edit_fields(self):
        dlg = FieldsDialog(self, self.doc.db)
        before = self.doc.settings_snapshot()     # OK with nothing changed: not unsaved
        if dlg.exec():
            from .dialogs import MORE_KEY, default_more
            more = dlg.more_names()                  # the lemma dialogue's More arrow (idea 60): the workspace's
            if more != default_more(self.doc.db) or self.doc.ws.get(MORE_KEY, None) is not None:
                self.doc.ws_set(MORE_KEY, more)
            if dlg.apply():
                self.doc.undo.clear()             # renamed fields can't be undone safely
                self._follow_field_renames(dlg.renames)
            self._setup_columns()
            self.doc.settings_changed(before)

    def _follow_field_renames(self, renames: dict):
        """A renamed field keeps its place everywhere the workspace names it (columns, Line up,
        Configure view, the More arrow) and in every matrix's cell lines, saved or on screen:
        before, it silently dropped out of them (the audit, 25 October)."""
        from ..workspace import rename_fields, renamed_key
        tokens = renames.get("token") or {}
        cfgs = list(self.doc.db.settings.matrices) + list(self.configs.values())
        moved = False
        for c in cfgs:
            new = [renamed_key(k, tokens) for k in c.cell]
            if new != c.cell:
                c.cell, moved = new, True
        if rename_fields(self.doc.ws, renames) or moved:
            self.doc.write_workspace()

    def _symbols(self) -> list[str]:
        """The Σymbols list (Edit → Lists → Symbols): the workspace's, or the defaults."""
        v = self.doc.ws.get("symbols", None)
        return [s for s in v if isinstance(s, str)] if isinstance(v, list) else list(symbols.DEFAULT)

    def edit_lists(self, start: str | None = None):
        """Edit → Lists: people, places, field lists and the tag structure, in one dialogue."""
        from .lists_dialog import ListsDialog
        dlg = ListsDialog(self, self.doc.db, self.doc.notebook, start if isinstance(start, str) else None,
                          symbols=self._symbols())
        if not dlg.exec():
            return
        db = self.doc.db
        renames = dlg.apply()
        if dlg.symbol_list() != self._symbols():   # Σymbols: kept in the workspace
            self.doc.ws_set("symbols", dlg.symbol_list())
            symbols.set_current(dlg.symbol_list())
        speakers = renames[chips.PARTICIPANTS]
        if speakers:                              # the tokens' speakers follow renamed codes
            for _, t in db.all_tokens():          # utterances' too
                if t.speaker in speakers:
                    t.speaker = speakers[t.speaker]
            self.doc.undo.clear()                 # renames can't be undone safely
            if self.speaker_code in speakers:
                self.speaker_code = speakers[self.speaker_code]
        if renames[chips.PARTICIPANTS] or renames[chips.RESEARCHERS]:
            from .. import segments               # their segment soundfiles follow (idea 46)
            people = {**renames[chips.RESEARCHERS], **speakers}
            segments.rename_speakers(db, people)
            self._follow_people_renames(people)
        if any(renames.values()):
            for t in db.texts:                    # texts' people and places follow renamed codes
                t.participants = [speakers.get(c, c) for c in t.participants]
                t.researchers = [renames[chips.RESEARCHERS].get(c, c) for c in t.researchers]
                t.locations = [renames[chips.LOCATIONS].get(c, c) for c in t.locations]
            self.doc.notebook.rename(renames[chips.RESEARCHERS], speakers, renames[chips.LOCATIONS])
            keys = self.session_keys()
            for kind, row in self.sess_rows.items():
                row.set_keys([renames[kind].get(k, k) for k in keys[kind]])
            self._session_people_changed()
        self._apply_tags(dlg.tags, dlg.value_renames())
        if getattr(dlg, "confidence_changed", False):   # Cogitate's levels are the notebook's
            self.doc.notebook_changed()
            self.doc.hypothesesChanged.emit()
        self._fill_session()
        self.refresh_notebook()

    def _follow_people_renames(self, people: dict[str, str]):
        """Renamed codes outside the records (the audit, P7): TextGrid tier names (tx@SP1),
        clipped utterances' copies of them, the stored ɛλicit requests and the request being
        put together; a TextGrid that couldn't be written is named."""
        from .. import recode
        res = recode.follow(self.doc.db, people)
        draft = self.elicit_draft
        if draft:
            new = dict(draft)
            for key in ("speaker", "researcher"):
                if new.get(key) in people:
                    new[key] = people[new[key]]
            l2p = {}
            for k, v in (new.get("l2_people") or {}).items():
                lang, _, code = k.partition("|")
                l2p[f"{lang}|{people.get(code, code)}"] = v
            new["l2_people"] = l2p
            if new != draft:
                self.elicit_draft = new
        if res.utterances:                        # the copies are in the database: an unsaved change
            self.doc._settings_dirty = True
            self.doc.dirtyChanged.emit(True)
        if res.failed:
            QMessageBox.warning(self, "Edit → Lists",
                                "The renamed codes couldn't be written into the tier names of "
                                + ", ".join(res.failed) + " (open in Praat, or unreadable). Rename those "
                                "tiers in Praat.")

    def _apply_tags(self, dlg, value_renames: dict | None = None):
        """Use the tag structure from the tag editor; renamed tags, and values renamed in the
        closed fields' lists (word classes included), are followed everywhere."""
        db = self.doc.db
        s = db.settings
        tag_renames = dlg.renames()
        value_renames = value_renames or {}
        deleted = dlg.deleted_tags() if hasattr(dlg, "deleted_tags") else set()
        old_codes = {t.name: t.file_code() for t, _ in s.tags.tags()}
        names_before = {id(t): db.expected_filename(e, t) for e, t in db.all_tokens() if t.file}
        s.tags = dlg.structure()
        new_codes = {t.name: t.file_code() for t, _ in s.tags.tags()}
        recoded = {tag_renames.get(n, n) for n, c in old_codes.items()
                   if tag_renames.get(n, n) in new_codes and new_codes[tag_renames.get(n, n)] != c}
        if deleted:                                   # deleted tags come off the tokens that used them
            for _, t in db.all_tokens():
                if deleted & set(t.tags):
                    t.tags = [x for x in t.tags if x not in deleted]
        wcf = s.entry_field("word-class")
        if wcf is not None:                         # the hints follow renamed word classes
            s.tags.rename_classes(value_renames.get(wcf.name, {}))
        fields = [(f, True) for f in s.entry_fields] + [(f, False) for f in s.token_fields]
        for e in db.items():                      # lemmas and utterances
            for f, on_entry in fields:
                r = value_renames.get(f.name)
                if not r:
                    continue
                for obj in ([e] if on_entry else e.tokens):
                    if obj.get(f.name) in r:
                        obj.set(f.name, r[obj.get(f.name)])
            for t in e.tokens:
                if any(x in tag_renames for x in t.tags):
                    t.tags = s.tags.sort([tag_renames.get(x, x) for x in t.tags])
        fixed = (0, 0)
        plan = getattr(dlg, "clash_plan", None)     # tokens that would share a name (tagclash)
        if plan:
            from .. import tagclash
            fixed = tagclash.apply(db, *plan)
            dlg.clash_plan = None
            tagged, merged = fixed
            self.statusBar().showMessage(
                "Same soundfile names avoided: " + ", ".join(x for x in (
                    f"{tagged} Example tag{'s' if tagged != 1 else ''} added" if tagged else "",
                    f"{merged} pair{'s' if merged != 1 else ''} merged" if merged else "") if x) + ".", 8000)
        if tag_renames or deleted or any(value_renames.values()) or any(fixed):
            self.doc.undo.clear()     # renames can't be undone safely
            for m in s.matrices:                      # saved matrices follow too
                m.rename(tag_renames)
            for cfg in self.configs.values():         # and the matrices on screen
                cfg.rename(tag_renames)
        self._setup_columns()
        self.doc.settings_changed()
        # Recordings whose names a changed code or a deleted tag put out of date: renamed straight
        # away when names update automatically, otherwise asked about.
        moved = {id(t) for e, t in db.all_tokens()
                 if t.file and id(t) in names_before and db.expected_filename(e, t) != names_before[id(t)]
                 and db.expected_filename(e, t) != t.file and (recoded & set(t.tags) or deleted)}
        if moved and not s.auto_update_names:
            why = "codes changed" if recoded else "tags changed"
            box = QMessageBox(QMessageBox.Question, "Soundfile names",
                              f"The tag {why}, so {len(moved)} recording{'s' if len(moved) != 1 else ''}' "
                              "names are out of date. Rename them now?", parent=self)
            rename = box.addButton("Rename", QMessageBox.AcceptRole)
            box.addButton("Leave names out of date", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is rename:
                self.update_all_names(ask=False, only=moved)
                return
        self._maybe_update_names()

    # ---- Show the pitch system (IDEAS.md idea 9; DESIGN.md 3.5) ------------------------------
    def set_pitch_shown(self, on: bool):
        """Show or hide the pitch system for the open database (its workspace): the Pitch field,
        the drawing, pitch playback and the scratchpads, everywhere. The data is never touched."""
        self.doc.set_pitch_shown(on)              # the other windows follow settingsChanged
        self.pitch_view_changed()

    def pitch_view_changed(self):
        """Every view of the main window follows Show the pitch system as it is now."""
        self._sync_pitch_view()
        self._setup_columns()
        self.refresh()                            # no status message: the phonetics scratchpad says it (Josh)

    def _sync_pitch_view(self):
        from .. import pitchview
        a = getattr(self, "pitch_view_action", None)
        if a is not None:
            a.blockSignals(True)
            a.setChecked(not pitchview.tick())     # Hide pitch system: selected while hidden
            a.setEnabled(pitchview.has())          # an unspecified database has no pitch to show
            a.blockSignals(False)
        if hasattr(self, "comparison"):
            self.comparison.show_pitch()

    def toggle_theme(self):
        """The lightbulb: light theme to dark, or dark to light (the same as Settings → Display → Theme)."""
        self.prefs.theme = "light" if theme.dark() else "dark"
        theme.from_prefs(self.prefs)
        self._restyle()

    def edit_settings(self):
        dlg = PreferencesDialog(self, self.doc.db, self.prefs)
        before = self.doc.settings_snapshot()     # OK with nothing changed: not unsaved
        if dlg.exec():
            names_changed = dlg.apply()
            self.set_unusual_warning(self.prefs.warn_unusual_tags)
            self.set_spelling_underlines(self.prefs.underline_spelling)
            self._apply_autosave()
            theme.from_prefs(self.prefs)
            self._restyle()
            self._sync_pitch_view()               # Show the pitch system (Settings → Pitch)
            self.update_badges()                  # each badge switched on or off (Settings → Display)
            self._setup_columns()                 # Stem type and From shown or hidden
            self.apply_ipa_size()
            widgets.set_abbreviate(self.prefs.abbreviate_fields)
            self.conventions_changed()
            self.doc.settings_changed(before)
            s = self.doc.db.settings
            self.comparison.set_range(s.pitch_low, s.pitch_high)
            if self.notebook_dialog is not None:  # its history checkboxes follow Settings
                self.notebook_dialog._show_history_ticks()
            if names_changed:
                self._maybe_update_names()
            if dlg.change_kind_requested:         # Settings → Pitch → Change the pitch kind…
                self.edit_metadata(focus="pitch kind")

    def apply_ipa_size(self):
        """Settings → Display → IPA font size, in every open view at its own zoom: the grids (lemma
        list, All data, Utterances, texts, Bulk edit, Cogitate), the matrices and the text lines."""
        from PySide6.QtWidgets import QApplication

        from .lines_view import LinesView
        from .matrix_view import MatrixView
        from .table import FilterTable
        widgets.set_ipa_size(self.prefs.ipa_size)
        for w in QApplication.allWidgets():
            if isinstance(w, FilterTable):
                w.apply_ipa_size()
            elif isinstance(w, MatrixView):
                w.delegate.set_zoom(w.zoom)
                selected = w.selected
                w.set_layout(w.model_.layout_, w.cell_fields)
                w.selected = selected
            elif isinstance(w, LinesView):
                w._apply_fonts()
                w._relayout()

    def _maybe_update_names(self):
        db = self.doc.db
        stale = [(e, t) for e, t in db.all_tokens()      # utterances' recordings too
                 if t.file and t.file != db.expected_filename(e, t)] + self._stale_texts()
        if not stale:
            return
        if db.settings.auto_update_names:
            self.update_all_names(ask=False)
        else:
            self.statusBar().showMessage(f"{len(stale)} soundfile names are out of date "
                                         "(Tools → Update all soundfile names).", 8000)

    # =============================================================== tools
    def update_all_names(self, ask: bool = True, only: set | None = None):
        """only: rename just these tokens' recordings (by id(token)), texts left alone."""
        db = self.doc.db
        stale = [(e, i) for e in db.items() for i, t in enumerate(e.tokens)
                 if t.file and t.file != db.expected_filename(e, t) and (only is None or id(t) in only)]
        texts = self._stale_texts() if only is None else []
        if not stale and texts:                   # only texts' files are out of date
            self._rename_texts(texts, ask)
            return
        if not stale:
            if ask:
                QMessageBox.information(self, "Soundfile names", "All soundfile names are up to date.")
            return
        if ask and not _w.ask(self, "Soundfile names",
                                        f"Rename {len(stale)} recordings to match their tokens?", f"Rename {len(stale)} recording{'s' if len(stale) != 1 else ''}"):
            return
        # One undo step for the lot. Every recording first moves to a temporary name, then to its
        # new one, so names can swap or chain (A → B while B → C) without getting in the way.
        problems, plan = [], []
        # tokens' and utterances' recordings are in folders of their own
        sources = {str(storage.folder_for(db, e) / e.tokens[i].file).lower() for e, i in stale}
        targets: dict[str, str] = {}
        for e, i in stale:
            t = e.tokens[i]
            folder = storage.folder_for(db, e)
            new = db.expected_filename(e, t)
            src, dst = folder / t.file, folder / new
            key = str(dst).lower()
            if not src.exists():
                problems.append(f"{t.file}: not in its sound folder")
            elif key in targets:
                problems.append(f"{t.file}: {new} would also be the name of {targets[key]}")
            elif dst.exists() and key not in sources and not storage.same_file(src, dst):
                problems.append(f"{t.file}: {new} already exists")
            else:
                targets[key] = t.file
                plan.append((e, i, src, dst))
        renames = [(src, src.with_name(src.name + ".lemmatrix-renaming")) for _, _, src, _ in plan]
        renames += [(src.with_name(src.name + ".lemmatrix-renaming"), dst) for _, _, src, dst in plan]
        changed: dict[int, Entry] = {}
        for e, i, _, dst in plan:
            after = changed.setdefault(id(e), e.copy())
            after.tokens[i].file = dst.name
        order = {id(e): e for e, _, _, _ in plan}               # entries in plan order, once each
        pairs = [(e, changed[k]) for k, e in order.items()]
        tplan, tproblems = self._text_plan(texts, set(sources)) if texts else ([], [])
        pairs += [p for p, _ in tplan]
        for _, rn in tplan:
            renames = [(src, src.with_name(src.name + ".lemmatrix-renaming")) for src, _ in rn] + renames + \
                [(src.with_name(src.name + ".lemmatrix-renaming"), dst) for src, dst in rn]
        problems += tproblems
        trouble = self.doc.apply_changes("Update all soundfile names", pairs, renames, stamp=False) \
            if (plan or tplan) else []
        done = 0 if trouble else len(plan) + sum(len(rn) for _, rn in tplan)
        problems = trouble + problems
        msg = f"Renamed {done} recording(s)."
        if problems:
            msg += "\n\nNot renamed:\n" + "\n".join(problems[:30])
        QMessageBox.information(self, "Soundfile names", msg)

    def missing_recordings(self):
        """Recordings in the sound folder that belong to tokens but aren't linked to them.

        Two kinds of token are looked at: those whose stored recording isn't in the folder
        (renamed outside Lemmatrix, say), and those with no recording at all (a recording
        added to the folder by hand, e.g. one cut out of a longer one). Each is matched with
        a recording of the same lemma (reference and gloss) that no other token uses (an utterance:
        one in Soundfiles/Utterances with its reference in the name): the
        one with the expected name if there is one, otherwise the closest name, best
        matches first. Returns ([(entry, token index, file name, had a name before)],
        [(entry, token index)] for stored recordings that couldn't be found at all).
        """
        import difflib
        import re as _re
        db = self.doc.db
        found, lost = [], []
        # lemma tokens in Soundfiles/Tokens, by reference and gloss; utterances in
        # Soundfiles/Utterances, by reference (followed by _ or the end of the name)
        for folder, items, matches in (
                (storage.sound_folder(db), db.entries,
                 lambda e: (lambda n, stem=f"_{e.ref}_{e.file_gloss or db.gloss(e)}".lower(): stem in n)),
                (storage.utterance_folder(db), db.utterances,
                 lambda u: (lambda n, rx=_re.compile(r"_" + _re.escape(u.ref.lower()) + r"(_|\.wav$)"):
                            bool(rx.search(n))))):
            if not items:
                continue
            try:
                on_disk = {p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".wav"}
            except OSError:
                on_disk = set()
            lower = {n.lower(): n for n in on_disk}
            claimed = {t.file.lower() for e in items for t in e.tokens if t.file and t.file.lower() in lower}
            free = {n for n in on_disk if n.lower() not in claimed}
            for e in items:
                needy = [i for i, t in enumerate(e.tokens) if not t.file or t.file.lower() not in lower]
                if not needy:
                    continue
                belongs = matches(e)
                candidates = {n for n in free if belongs(n.lower())}
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
                            score = max(difflib.SequenceMatcher(None, c.lower(), x.lower()).ratio()
                                        for x in names)
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

    def check_clipped(self):
        """Tools → Check clipped utterances…: every utterance whose line changed in its TextGrid."""
        from .pull_dialog import CheckDialog
        dlg = CheckDialog(self)
        dlg.exec()
        if self.utterances_window is not None:
            self.utterances_window.refresh()

    def find_missing_recordings(self):
        found, lost = self.missing_recordings()
        if not found and not lost:
            QMessageBox.information(self, "Missing recordings",
                                    "Every recording is linked to its token, and no token's recording is missing.")
            return

        def label(e, i):
            from ..model import is_utterance
            if is_utterance(e):
                return f"{e.ref} (utterance)"
            t = e.tokens[i]
            tags = " + ".join(mx.chips(self.doc.db, t.tags)) or "citation"
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
        if not _w.ask(self, "Missing recordings",
                                msg + "\n\nLink the tokens to these recordings?", "Link them"):
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

    # ---- texts' recordings and TextGrids --------------------------------
    def _stale_texts(self) -> list:
        """Texts whose recording or TextGrid has another name than the pattern gives now."""
        db = self.doc.db
        return [t for t in db.texts if (t.file and t.file != db.expected_text_name(t)) or
                (t.textgrid and t.textgrid != db.expected_text_name(t, ".TextGrid"))]

    def _text_plan(self, texts, taken: set) -> tuple[list, list]:
        """([((text, renamed copy), [(src, dst)…])], problems) for renaming texts' files."""
        db = self.doc.db
        folder = storage.text_folder(db)
        plan, problems = [], []
        for t in texts:
            after, moves = t.copy(), []
            for attr, ext in (("file", ".wav"), ("textgrid", ".TextGrid")):
                old = getattr(t, attr)
                new = db.expected_text_name(t, ext)
                if not old or old == new:
                    continue
                src, dst = folder / old, folder / new
                if not src.exists():
                    problems.append(f"{old}: not in Soundfiles\\Texts")
                elif dst.exists() and not storage.same_file(src, dst):
                    problems.append(f"{old}: {new} already exists")
                else:
                    moves.append((src, dst))
                    setattr(after, attr, new)
            if moves:
                plan.append(((t, after), moves))
        return plan, problems

    def _rename_texts(self, texts, ask: bool):
        if ask and not _w.ask(self, "Soundfile names", f"Rename the files of {len(texts)} "
                                        "text(s) to match the pattern?", (f"Rename {len(texts)} texts' files" if len(texts) != 1 else "Rename the text's files")):
            return
        plan, problems = self._text_plan(texts, set())
        renames = [m for _, rn in plan for m in rn]
        trouble = self.doc.apply_changes("Update all soundfile names", [p for p, _ in plan], renames,
                                         stamp=False) if plan else []
        msg = f"Renamed {0 if trouble else len(renames)} file(s)."
        if trouble + problems:
            msg += "\n\nNot renamed:\n" + "\n".join((trouble + problems)[:30])
        QMessageBox.information(self, "Soundfile names", msg)

    def check_duplicates(self):
        dups = self.doc.db.duplicate_filenames()
        if not dups:
            QMessageBox.information(self, "Duplicate file names", "No two tokens share a file name.")
            return
        db = self.doc.db
        lines = []
        for name, items in list(dups.items())[:40]:
            refs = ", ".join(f"{e.ref} ({' + '.join(mx.chips(db, t.tags)) or 'citation'})"
                             for e, t in items)
            lines.append(f"{name}: {refs}")
        QMessageBox.warning(self, "Duplicate file names",
                            "These tokens would get the same file name:\n\n" + "\n".join(lines))

    def about(self):
        QMessageBox.about(self, "About Lemmatrix", about_text())

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
        from .. import pitchview                  # the export follows what's shown (idea 9)
        shown_cell = pitchview.visible(cfg.cell, db.settings, pitchview.TOKENS)
        fields = [f for f in shown_cell if f != "drawing"]
        if "drawing" in shown_cell and not any(db.settings.token_field(f) and
                                             db.settings.token_field(f).role == "pitch" for f in fields):
            pitch = next((f.name for f in db.settings.token_fields if f.role == "pitch"), None)
            if pitch:
                fields.insert(0, pitch)             # the drawing exports as its pitch digits

        def label(item):
            return f"{item.entry.ref} {item.label}" if item.entry is not None else item.label

        def text(t, name):
            return mx.cell_text(db, t, name)

        corner = (f"{lay.entry.ref} {db.lemma(lay.entry)}" if lay.entry is not None else "")
        header = [corner] + [label(c) for c in lay.cols]
        rows = []
        for r, row in enumerate(lay.rows):
            out = [label(row)]
            for c in range(len(lay.cols)):
                hits = lay.tokens(r, c)
                entry, _ = lay.target(r, c)
                blocks = []
                for _, t in hits:
                    lines = []
                    if len(hits) > 1:
                        extra = mx.extra_chips(db, t, lay.spec_at(r, c), entry, defaults)
                        if extra:
                            lines.append(" ".join(extra))
                    lines += [text(t, n) for n in fields if text(t, n)]
                    blocks.append("\n".join(lines))
                out.append("\n\n".join(blocks))
            rows.append(out)
        return header, rows

    def fill_recording_dates(self):
        """Tools → Fill in recording dates: tokens' dates from their soundfiles' metadata."""
        from .dates_dialog import RecordingDatesDialog
        RecordingDatesDialog(self).exec()

    def export_archive(self, kind: str = "ethical"):
        """File → Export → Anonymous archive / Ethical archive (idea 44): a copy of the data to share,
        with nobody named (anonymous) or only the people selected Identifiable? (ethical)."""
        from .export_dialog import ArchiveExportDialog
        ArchiveExportDialog(self, kind).exec()


    def _select_wordlist_hit(self):
        """A wordlist search (CAWL 345) that finds one lemma selects it."""
        from .. import wordlists
        from .searchmark import terms
        if not any(wordlists.search_term(t) for t in terms(self.lemma_search.text())):
            return
        rows = self.lemmas.visible_rows()
        if len(rows) == 1 and self.lemmas.current_row() is not rows[0]:
            self.lemmas.select_row(rows[0])

    def export_wordlist(self):
        """File → Export → Wordlist…: the EACW, CAWL or Swadesh list of this database (idea 40)."""
        from .wordlist_dialogs import WordlistExportDialog
        WordlistExportDialog(self).exec()

    def insert_eacw_items(self, near=None):
        """Insert EACW items… (Josh, 23 October): the list's items this database doesn't have, those
        beside a lemma first (its hidden letters)."""
        from .wordlist_dialogs import insert_eacw_items
        insert_eacw_items(self, near)

    def convert_references(self):
        """Tools → Convert references from a table… (Josh, 23 October): a conversion map."""
        from .convert_dialog import ConvertReferencesDialog
        ConvertReferencesDialog(self).exec()

    def batch_tokens(self):
        """λ→τ with several lemmas selected (idea 64): the batch box, then the closing box."""
        from .batch_tokens import run_batch
        run_batch(self)

    def give_citation_tokens(self):
        """Tools → Audits → Give every lemma its citation token… (idea 64): an empty one, first,
        for each lemma without one (e.g. from a conversion); one undo step."""
        from .. import batch
        pairs = batch.citation_pairs(self.doc.db)
        if not pairs:
            QMessageBox.information(self, "Citation tokens", "Every lemma has its citation token.")
            return
        refs = ", ".join(e.ref for e, _ in pairs[:10]) + (" …" if len(pairs) > 10 else "")
        if not _w.ask(self, "Citation tokens",
                                f"{len(pairs)} lemma{'s have' if len(pairs) != 1 else ' has'} no citation token "
                                f"(a token without tags): {refs}\n\nGive each an empty one? It has no speaker "
                                "or date until it is recorded. You can undo this.", f"Add {len(pairs)} citation token{'s' if len(pairs) != 1 else ''}"):
            return
        self.doc.apply_changes(f"Citation tokens for {len(pairs)} lemmas", pairs, stamp=False)
        self.statusBar().showMessage(f"Gave {len(pairs)} lemma(s) an empty citation token.", 8000)

    def copy_citation_forms(self):
        """Tools → Copy citation forms to empty lemmas… (idea 67, Josh): each lemma with an empty
        Lemma takes its citation token's form (Phonemic, else Phonetic, or as chosen); one undo step."""
        from .. import citation_copy as cc
        from .citation_copy_dialog import CopyCitationDialog
        if self.doc.db.settings.entry_field("lemma") is None:
            return
        dlg = CopyCitationDialog(self, self.doc.db, self.prefs.ipa_size)
        if not dlg.plan.copies and not dlg.plan.no_form:
            QMessageBox.information(self, "Copy citation forms", "Every lemma has its Lemma filled.")
            return
        if not dlg.exec() or not dlg.chosen():
            return
        chosen = dlg.chosen()
        self.doc.apply_changes(f"Copy {len(chosen)} citation forms to lemmas",
                               cc.changed_copies(self.doc.db, chosen), stamp=False)
        self.statusBar().showMessage(f"Copied {len(chosen)} citation form(s) into empty Lemma fields.", 8000)
        self._maybe_update_names()               # a soundfile pattern with the Lemma in it follows

    def check_reference_order(self):
        """Tools → Check reference order… (Josh, 23 October): lemmas out of the EACW's order."""
        from .wordlist_dialogs import check_reference_order
        check_reference_order(self)

    def check_wordlist_integrity(self):
        """Tools → Audits → Check wordlist integrity… (idea 66): one report, select and fix."""
        from .wordlist_dialogs import check_wordlist_integrity
        check_wordlist_integrity(self)

    def link_wordlists(self):
        """Tools → Link to wordlists…: an existing database's base list and numbers (idea 40)."""
        from .wordlist_dialogs import link_to_wordlists
        link_to_wordlists(self)

    def export_csv(self, filtered: bool, tags: bool = False):
        from .. import export
        db = self.doc.db
        tab = self.tabs.currentIndex()
        if tags:
            header, rows = export.tag_structure_table(db)
            what = "tag structure"
        elif filtered:
            header, rows = self._visible_table()
            what = {ALL_DATA: "All data", LEMMA_TAG: "Lemma-Tag", TAG_TAG: "Tag-Tag"}[tab]
            if not rows:
                QMessageBox.information(self, "Export", "Nothing is showing in this tab to export.")
                return
        else:
            header, rows = export.database_table(db)
            what = "entire database"
        stem = Path(db.path).stem if db.path else "Lemmatrix"
        start = layout.existing_folder(layout.exports_folder(db.path)) if db.path else Path.home() / "Documents"
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
                QMessageBox.warning(self, "Soundfile names",
                                    "These recordings couldn't get their old names back, so "
                                    "Tools → Find missing recordings may be needed next time:\n\n"
                                    + "\n".join(problems[:30]))
        return r == QMessageBox.Discard

    def new_file(self):
        if not self._confirm_discard():
            return
        from .. import newdb
        from .new_database import NewDatabaseDialog
        dlg = NewDatabaseDialog(self, self.prefs)  # one window (idea 9, Josh, 23 October)
        if not dlg.exec():
            return
        path = self._new_database_path("New database")
        if not path:
            return
        db = newdb.make(dlg.choices())
        db.path = path
        layout.create_layout(path)
        self.load_database(db)
        self.save()

    def _new_database_path(self, title: str) -> str:
        """Where a new database goes. A folder that already has a database gets a folder of its
        own for the new one, named after it (each database has its own main folder)."""
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path.home() / "Documents"),
                                              "Lemmatrix database (*.xml)")
        if not path:
            return ""
        if not path.lower().endswith(".xml"):
            path += ".xml"
        p = Path(path)
        others = [o for o in layout.other_databases(path)]
        if p.exists() and layout.is_database(p):
            others.append(p)
        if others:
            target = p.parent / p.stem / p.name
            if not _w.ask(self, title, f"{p.parent.name} already has a database in it ({others[0].name}). Each "
                          "database needs a folder of its own, since its recordings, backups and documentation "
                          f"go in it.\n\nMake a folder called “{p.stem}” there for the new database?",
                          "Make the folder"):
                return ""
            if target.exists():
                QMessageBox.warning(self, title, f"{target} already exists.")
                return ""
            target.parent.mkdir(parents=True, exist_ok=True)
            path = str(target)
        return path

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
        workspace = self._workspace_for(db)
        if workspace is None:                     # Cancel at "the workspace file is missing"
            return
        self.prefs.last_file = path
        self.load_database(db, workspace)

    def open_sample(self):
        target = Path.home() / "Documents" / "Lemmatrix Sample"
        if not SAMPLE.exists():
            QMessageBox.warning(self, "Sample", "The sample database isn't in this copy of Lemmatrix.")
            return
        dst = target / "Sample.xml"
        if dst.exists():
            if not _w.ask(self, "Sample", f"{dst} already exists. Replace it with a fresh "
                                    "copy?", "Replace with a fresh copy", "Open the one there"):
                self.open_file(str(dst))
                return
            # first the unsaved changes, and let go of the sample if it is the one open: Save could
            # otherwise write the old data over the fresh copy (the audit, 25 October), as the
            # ɛλicit test database already does
            if not self._confirm_discard():
                return
            if self.doc.db.path and Path(self.doc.db.path).parent == target:
                self.load_database(new_database())
        from .. import workspace as wsmod
        try:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SAMPLE, dst)
            if wsmod.path_for(SAMPLE).exists():   # its saved matrices are in its workspace
                shutil.copy2(wsmod.path_for(SAMPLE), wsmod.path_for(dst))
            from .. import notebook as nbmod      # questions, To Dos, snapshots, hypotheses (Josh, 25 October)
            if nbmod.path_for(SAMPLE).exists():
                shutil.copy2(nbmod.path_for(SAMPLE), nbmod.path_for(dst))
            elif nbmod.path_for(dst).exists():    # a fresh copy has no notebook of an older one
                nbmod.path_for(dst).unlink()
            sounds = SAMPLE.parent / "Soundfiles"
            if sounds.exists():
                if (target / "Soundfiles").exists():
                    shutil.rmtree(target / "Soundfiles", ignore_errors=True)
                shutil.copytree(sounds, target / "Soundfiles")
            for folder in ("Documentation", "Whiteboard"):   # DML's consent form; drawings linked to hypotheses
                if (SAMPLE.parent / folder).exists():
                    shutil.copytree(SAMPLE.parent / folder, target / folder, dirs_exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Sample", f"The sample couldn't be copied to {target}: {exc}")
            return
        self.open_file(str(dst))

    def open_elicit_test(self):
        """Help → Sample databases → Open a copy of the ɛλicit test database: the Italian one (samples/Elicit test),
        copied to Documents\\Lemmatrix Elicit Test with its recordings and pictures."""
        if not ELICIT_TEST.exists():
            QMessageBox.warning(self, "ɛλicit test database", "The test database isn't in this copy of Lemmatrix.")
            return
        target = Path.home() / "Documents" / "Lemmatrix Elicit Test"
        dst = target / ELICIT_TEST.name
        if dst.exists():
            if not _w.ask(self, "ɛλicit test database", f"{dst} already exists. Replace it with a fresh "
                                    "copy? (Its requests and recordings in Elicit go too.)", "Replace with a fresh copy", "Open the one there"):
                self.open_file(str(dst))
                return
            if not self._confirm_discard():
                return
            if self.doc.db.path and Path(self.doc.db.path).parent == target:
                self.load_database(new_database())        # let go of it before it is replaced
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(ELICIT_TEST.parent, target, dirs_exist_ok=True)
        self.open_file(str(dst))

    def save(self) -> bool:
        if not self.doc.db.path:                  # a database never saved (there is no Save as)
            path = self._new_database_path("Save database")
            if not path:
                return False
            self.doc.db.path = path
            layout.create_layout(path)
            self._mark_open(path)
            self._update_title()
        self._record_comments()
        self._save_view()                         # into the workspace, written with the save
        if not self._textgrid_conflicts():
            return False
        try:
            self.doc.save()
        except OSError as exc:
            QMessageBox.warning(self, "Save", f"Couldn't save: {exc}")
            return False
        self.prefs.last_file = self.doc.db.path
        self._fill_db_title()
        self._note_recent()                       # its title may have changed
        self._remember_session()                  # the panel as it is (not rebuilt: no flicker)
        where = QDir.toNativeSeparators(str(storage.backup_folder(self.doc.db.path)))
        self.statusBar().showMessage(f"Saved. The previous version is in {where}.", 5000)
        return True

    def rename_database(self) -> bool:
        """File → Rename database: its name in the title and its file name (with the notebook and
        the automatic backups), keeping the window's settings and the full-backup reminder."""
        from .dialogs import RenameDatabaseDialog
        db = self.doc.db
        if not db.path:
            QMessageBox.information(self, "Rename database", "Save the database first.")
            return False
        info = lockmod.held_elsewhere(db.path)
        if info is not None:
            QMessageBox.warning(self, "Rename database", f"{Path(db.path).name} seems to be open on "
                                f"{info.describe()}. Close it there first.")
            return False
        dlg = RenameDatabaseDialog(self, db)
        if not dlg.exec():
            return False
        if self.doc.dirty and not widgets.ask(
                self, "Rename database", "There are unsaved changes. Renaming saves the database, with "
                "them, under its new name.", "Save and rename"):
            return False
        old, stem, name = db.path, dlg.new_stem(), dlg.new_name()
        new = old
        if stem != Path(old).stem:
            self._mark_open("")
            try:
                new = str(layout.rename_database(old, stem))
            except layout.RenameError as exc:
                self._mark_open(old)
                QMessageBox.warning(self, "Rename database", str(exc))
                return False
            db.path = new
            self.prefs.move_database(old, new)
            self._mark_open(new)
        db.metadata.name = name
        self.doc.settings_changed()
        self._fill_db_title()
        ok = self.save()
        self._update_title()
        if ok and new != old:
            self.statusBar().showMessage(f"Renamed to {Path(new).name}.", 5000)
        return ok

    def _textgrid_conflicts(self) -> bool:
        """Before saving: a TextGrid with line edits here that Praat has saved meanwhile.
        Returns False to cancel the save."""
        for text, buf in self.doc.edited_buffers():
            if text is None or not buf.disk_changed():
                continue
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Save")
            box.setText(f"{text.ref}'s TextGrid was saved in Praat after you edited its lines here.")
            box.setInformativeText("Save my edits: Lemmatrix's version replaces Praat's (a copy of Praat's "
                                   "goes to Backups first).\nKeep Praat's: the unsaved line edits to "
                                   f"{text.ref} are dropped.")
            mine = box.addButton("Save my edits", QMessageBox.AcceptRole)
            praat = box.addButton("Keep Praat's", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is praat:
                buf.reload()
                self.doc.linesChanged.emit(text.id)
            elif box.clickedButton() is not mine:
                return False
        return True

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
                self.doc.empty_held()
            except Exception:                     # never stop the window closing
                pass
            try:
                self._save_view()
                self.doc.write_workspace()        # the working state, written now (idea 36)
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
