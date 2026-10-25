# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The Bulk edit window (Edit → Bulk edit…, Ctrl+Shift+B): change many lemmas or tokens at once.

Like FLEx's Bulk Edit: a filtered grid with a tick on every row, and an operation underneath.
The Lemmas and Tokens tabs work like the lemma list and All data in the main window, and
start with their filters: the Tokens tab shows the tokens of the lemmas the Lemmas tab
shows. In the Tokens tab the lemma columns are greyed: only token fields change there.

Preview shows the changes in the grid (new value highlighted, the old one struck through)
before anything happens. A problem in any ticked row cancels the whole operation. Apply
makes the change as one undo step, recordings renamed included.
"""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import QDate, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter,
                               QSizePolicy, QStackedWidget, QStyledItemDelegate, QTabBar, QToolButton, QVBoxLayout,
                               QWidget)

from .. import bulk, matrix as mx, storage
from ..model import ListItem
from . import theme
from .filter_dialogs import ConfigureColumnsDialog
from .icons import icon_size, ink_icon, themed_icon
from .searchmark import paint_cell
from .table import ChipsDelegate, Column, DrawingDelegate, FilterTable, RowModel
from .widgets import ipa_font

TICK = "__tick"
PREVIEW_ROLE = Qt.UserRole + 2
ERROR_ROLE = Qt.UserRole + 3
LEVELS = (bulk.LEMMAS, bulk.TOKENS)
REPLACE, SHORTCUTS, SET, COPY, CLEAR, PREDICT, CONDITIONS = range(7)
_noop = lambda row, text: None                # marks a column as changeable here (white, not grey)


class TokenRow:
    """A row of the Tokens tab: one token of one entry."""
    __slots__ = ("entry", "index")

    def __init__(self, entry, index):
        self.entry, self.index = entry, index

    @property
    def token(self):
        return self.entry.tokens[self.index]

    @property
    def id(self):
        return self.token.id

    def __eq__(self, other):
        return isinstance(other, TokenRow) and other.entry is self.entry and other.index == self.index

    def __hash__(self):
        return hash((id(self.entry), self.index))


def row_key(row):
    if isinstance(row, TokenRow):
        return (id(row.entry), row.index)
    return (id(row), None)


class BulkModel(RowModel):
    """The grid's rows, with a tick column and the preview's changes and problems."""

    def __init__(self, win: "BulkEditWindow"):
        super().__init__()
        self.win = win
        self.preview: dict = {}           # (row key, column key) -> bulk.Change
        self.errors: dict = {}            # (row key, column key) -> bulk.Problem

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows) or index.column() >= len(self.columns):
            return None
        row, col = self.rows[index.row()], self.columns[index.column()]
        if col.key == TICK:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self.win.is_ticked(row) else Qt.Unchecked
            if role == Qt.ToolTipRole:
                return "Selected rows are changed; deselect a row to leave it out"
            if role == Qt.UserRole + 1:
                return row
            if role == Qt.UserRole:
                return col.get(row)
            return None
        k = (row_key(row), col.key)
        if role == PREVIEW_ROLE:
            return self.preview.get(k)
        if role == ERROR_ROLE:
            return self.errors.get(k)
        ch = self.preview.get(k)
        if ch is not None:
            if role == Qt.DisplayRole:
                return ch.new
            if role == Qt.ToolTipRole:
                return f"Now: {ch.old or '(empty)'}\nAfter: {ch.new or '(empty)'}"
        p = self.errors.get(k)
        if p is not None and role == Qt.ToolTipRole:
            return p.message
        return super().data(index, role)

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.columns[index.column()].key == TICK:
            base |= Qt.ItemIsUserCheckable
        return base                        # nothing is edited in place here

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and self.columns[index.column()].key == TICK:
            on = value in (Qt.Checked, 2) or getattr(value, "value", None) == 2
            self.win.set_ticked([self.rows[index.row()]], on)
            return True
        return False

    def refresh_all(self):
        if self.rows and self.columns:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(self.columns) - 1))


class PreviewDelegate(QStyledItemDelegate):
    """Paints a previewed change (new value, old one struck through) or a problem; otherwise the
    column's own delegate (chips, pitch drawing) or the plain cell."""

    def __init__(self, fallback=None, parent=None):
        super().__init__(parent)
        self.fallback = fallback

    def paint(self, painter, option, index):
        ch, pr = index.data(PREVIEW_ROLE), index.data(ERROR_ROLE)
        if ch is None and pr is None:
            if self.fallback is not None:
                self.fallback.paint(painter, option, index)
            else:
                super().paint(painter, option, index)
                paint_cell(self, painter, option, index)   # what the search bar found
            return
        painter.save()
        r = option.rect
        font = index.data(Qt.FontRole) or QFont(option.font)
        if pr is not None and ch is None:
            painter.fillRect(r, theme.colour("error_fill"))
            painter.setPen(theme.colour("error_text"))
            f = QFont(font)
            f.setBold(True)
            painter.setFont(f)
            text = index.data(Qt.DisplayRole) or ""
            painter.drawText(QRectF(r).adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft,
                             f"⚠ {text}" if text else "⚠")
            painter.restore()
            return
        painter.fillRect(r, theme.wash(0.62 if theme.dark() else 0.80))
        bold = QFont(font)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(theme.colour("chip_text") if theme.dark() else theme.ink(0.55))
        rect = QRectF(r).adjusted(6, 0, -4, 0)
        new = ch.new or "(empty)"
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, new)
        w = painter.fontMetrics().horizontalAdvance(new) + 10
        if ch.old and w < rect.width() - 10:
            old = QFont(font)
            old.setStrikeOut(True)
            old.setPointSizeF(max(7.0, old.pointSizeF() * 0.9))
            painter.setFont(old)
            painter.setPen(theme.colour("dim"))
            painter.drawText(rect.adjusted(w, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, ch.old)
        painter.restore()

    def sizeHint(self, option, index):
        if self.fallback is not None and index.data(PREVIEW_ROLE) is None:
            return self.fallback.sizeHint(option, index)
        s = super().sizeHint(option, index)
        ch = index.data(PREVIEW_ROLE)
        if ch is not None:
            fm = option.fontMetrics
            s.setWidth(max(s.width(), fm.horizontalAdvance(ch.new) + fm.horizontalAdvance(ch.old) + 30))
        return s


class BulkTable(FilterTable):
    def __init__(self, win: "BulkEditWindow"):
        super().__init__()
        self.model_ = BulkModel(win)
        self.proxy.setSourceModel(self.model_)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)


# ==========================================================================

class BulkEditWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.db = main.doc.db
        self.setWindowTitle("Bulk edit")
        self.unticked: set = set()          # row keys left out (new rows start ticked)
        self.plan: bulk.Plan | None = None
        self._op = None                     # the operation the preview was made for
        self._applying = False
        from .winstate import fit_to_screen
        fit_to_screen(self, 1360, 900)           # the default: as big as fits (a saved size wins)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        top = QHBoxLayout()
        self.title = QLabel("Bulk edit")
        f = QFont(self.title.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.45)
        self.title.setFont(f)
        top.addWidget(self.title)
        top.addSpacing(24)
        self.levels = QTabBar()
        self.levels.addTab("Lemmas")
        self.levels.addTab("Tokens")
        self.levels.setExpanding(False)
        self.levels.setToolTip("Lemmas: change lemma fields (and word classes). Tokens: change token "
                               "fields, tags, speakers and dates.")
        top.addWidget(self.levels)
        top.addStretch(1)
        self.count = QLabel()
        top.addWidget(self.count)
        lay.addLayout(top)

        split = self.split = QSplitter(Qt.Vertical)
        grids = QWidget()
        gl = QVBoxLayout(grids)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(4)
        self.pages = QStackedWidget()
        self.tables: dict[str, BulkTable] = {}
        self.searches: dict[str, QLineEdit] = {}
        for level in LEVELS:
            self.pages.addWidget(self._grid_page(level))
        gl.addWidget(self.pages, 1)
        split.addWidget(grids)
        split.addWidget(self._operation_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        for a in (self.doc.undo.createUndoAction(self, "Undo"), self.doc.undo.createRedoAction(self, "Redo")):
            self.addAction(a)
        self.actions()[0].setShortcut(QKeySequence.Undo)
        self.actions()[1].setShortcut(QKeySequence.Redo)

        self._setup_columns()
        self._copy_main_filters()
        self.tables[bulk.LEMMAS].filtersChanged.connect(self._lemmas_filtered)
        self.tables[bulk.TOKENS].filtersChanged.connect(self._filters_changed)
        self.levels.currentChanged.connect(self._level_changed)
        self.doc.changed.connect(self._doc_changed)
        self.doc.settingsChanged.connect(self._settings_changed)
        self._fill_rows()
        self.levels.setCurrentIndex(1)           # tokens first: most changes are to transcriptions
        self._level_changed(1)
        self._restyle()
        from . import winstate
        winstate.keep(self, self.main.prefs, "window/bulk")   # size, place and splitter, as adjusted

    # ---- building ----------------------------------------------------
    def _grid_page(self, level: str) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        bar = QHBoxLayout()
        broom = QToolButton()
        broom.setProperty("icon_name", "reset-filters")     # follows the theme with the main window's
        broom.setIcon(ink_icon("reset-filters", 20))
        broom.setIconSize(QSize(20, 20))
        broom.setToolTip("Clear all filters")
        broom.setAutoRaise(True)
        broom.clicked.connect(lambda *_, lv=level: self._clear_filters(lv))
        gear = QToolButton()
        gear.setProperty("icon_name", "gear-columns")
        gear.setIcon(themed_icon("gear-columns", 20))
        gear.setIconSize(icon_size("gear-columns", 20))
        gear.setToolTip("Configure columns")
        gear.setAutoRaise(True)
        gear.clicked.connect(lambda *_, lv=level: self._configure_columns(lv))
        bar.addWidget(gear)
        bar.addWidget(broom)                                # after Configure columns, as everywhere else
        search = QLineEdit()
        search.setPlaceholderText("quick search of the visible columns")
        search.setClearButtonEnabled(True)
        search.setMaximumWidth(360)
        bar.addWidget(search, 1)
        self.searches[level] = search
        for text, on in (("Select all shown", True), ("Deselect all shown", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda *_, lv=level, on=on: self.set_ticked(self.tables[lv].visible_rows(), on))
            bar.addWidget(b)
        tick_sel = QPushButton("Deselect highlighted rows")
        tick_sel.setToolTip("Leave the highlighted rows out (highlight several with Shift or Ctrl)")
        tick_sel.clicked.connect(lambda *_, lv=level: self.set_ticked(self._selected(lv), False))
        bar.addWidget(tick_sel)
        bar.addStretch(1)
        pl.addLayout(bar)
        table = BulkTable(self)
        self.tables[level] = table
        search.textChanged.connect(lambda text, t=table: t.proxy.set_search(text))
        pl.addWidget(table, 1)
        return page

    def _tabbar(self, names) -> QTabBar:
        bar = QTabBar()
        for n in names:
            bar.addTab(n)
        bar.setExpanding(False)
        return bar

    def _operation_panel(self) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(8, 6, 8, 8)
        self.ops = self._tabbar(["Replace", "Shortcuts", "Set value", "Copy", "Clear", "Predict", "Conditions"])
        self.ops.setTabEnabled(CONDITIONS, False)
        self.ops.setTabToolTip(CONDITIONS, "Syllable and environment conditions (e.g. y → j only before "
                                           "a vowel) arrive in version 2 (Analyze)")
        bl.addWidget(self.ops)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.op_pages = QStackedWidget()
        self.op_pages.addWidget(self._replace_page())
        self.op_pages.addWidget(self._shortcut_page())
        self.op_pages.addWidget(self._set_page())
        self.op_pages.addWidget(self._copy_page())
        self.op_pages.addWidget(self._clear_page())
        self.op_pages.addWidget(self._predict_page())
        stage2 = QLabel("Conditions on syllables and environments arrive in version 2 (Analyze).")
        self.op_pages.addWidget(stage2)
        body.addWidget(self.op_pages, 3)
        body.addWidget(self._options(), 2)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.linkActivated.connect(self._link)
        self.summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary.setMinimumWidth(300)
        self.summary_box = QFrame()
        self.summary_box.setFrameShape(QFrame.StyledPanel)
        sl = QVBoxLayout(self.summary_box)
        sl.addWidget(self.summary)
        sl.addStretch(1)
        body.addWidget(self.summary_box, 3)
        bl.addLayout(body, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.clear_btn = QPushButton("Clear preview")
        self.preview_btn = QPushButton("Preview")
        self.apply_btn = QPushButton("Apply")
        close = QPushButton("Close")
        self.preview_btn.setDefault(True)
        self.apply_btn.setToolTip("Make the previewed changes (one undo step)")
        self.clear_btn.clicked.connect(lambda *_: self.clear_preview())
        self.preview_btn.clicked.connect(lambda *_: self.preview())
        self.apply_btn.clicked.connect(lambda *_: self.apply())
        close.clicked.connect(lambda *_: self.close())
        for b in (self.clear_btn, self.preview_btn, self.apply_btn, close):
            buttons.addWidget(b)
        bl.addLayout(buttons)
        self.ops.currentChanged.connect(self._op_changed)
        return box

    def _form(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 4, 0, 0)
        return w, form

    def _watch(self, *widgets):
        for w in widgets:
            sig = (getattr(w, "currentIndexChanged", None) or getattr(w, "textChanged", None)
                   or getattr(w, "dateChanged", None))
            if sig is not None:
                sig.connect(lambda *_: self.clear_preview())
            if isinstance(w, QComboBox) and w.isEditable():
                w.currentTextChanged.connect(lambda *_: self.clear_preview())

    def _replace_page(self) -> QWidget:
        w, form = self._form()
        self.r_field = QComboBox()
        self.r_find = QLineEdit()
        self.r_repl = QLineEdit()
        for ed in (self.r_find, self.r_repl):
            ed.setFont(ipa_font(14))
        self.r_find.setPlaceholderText("what to find")
        self.r_repl.setPlaceholderText("leave empty to delete what is found")
        form.addRow("Field", self.r_field)
        form.addRow("Find", self.r_find)
        form.addRow("Replace with", self.r_repl)
        # Josh, 21 October: a Clear under the fields empties Find and Replace with
        self.r_clear = QPushButton("Clear fields")
        self.r_clear.setToolTip("Empty Find and Replace with")
        self.r_clear.clicked.connect(lambda *_: self.clear_replace_fields())
        row = QHBoxLayout()
        row.addWidget(self.r_clear)
        row.addStretch(1)
        form.addRow("", row)
        self._watch(self.r_field, self.r_find, self.r_repl)
        self.r_field.currentIndexChanged.connect(lambda *_: self._sync_options())
        return w

    def _fill_shortcuts(self):
        """The shortcuts offered: the Pitch shortcut not while the pitch system is hidden (idea 9)."""
        from .. import pitchview
        current = self.s_which.currentData()
        self.s_which.blockSignals(True)
        self.s_which.clear()
        for sc in bulk.SHORTCUTS:
            if "pitch" in sc.roles and not pitchview.shown(pitchview.TOKENS):
                continue
            self.s_which.addItem(sc.name, sc.key)
        self.s_which.setCurrentIndex(max(0, self.s_which.findData(current)))
        self.s_which.blockSignals(False)

    def _targets(self) -> list:
        """The fields Bulk edit offers at this level: Pitch not while the pitch system is hidden."""
        from .. import pitchview
        return [t for t in bulk.targets(self.db, self.level)
                if t.role != "pitch" or pitchview.shown(pitchview.TOKENS)]

    def clear_replace_fields(self):
        self.r_find.clear()
        self.r_repl.clear()
        self.r_find.setFocus()

    def _shortcut_page(self) -> QWidget:
        w, form = self._form()
        self.s_which = QComboBox()
        self._fill_shortcuts()
        self.s_dir = QComboBox()
        self.s_field = QComboBox()
        self.s_note = QLabel()
        self.s_note.setWordWrap(True)
        form.addRow("Shortcut", self.s_which)
        form.addRow("Direction", self.s_dir)
        form.addRow("Field", self.s_field)
        form.addRow(self.s_note)
        self.s_which.currentIndexChanged.connect(lambda *_: self._shortcut_chosen())
        self._watch(self.s_which, self.s_dir, self.s_field)
        return w

    def _set_page(self) -> QWidget:
        w, form = self._form()
        self.v_field = QComboBox()
        self.v_stack = QStackedWidget()
        self.v_text = QLineEdit()
        self.v_list = QComboBox()
        self.v_list.setEditable(True)
        self.v_list.setToolTip("Pick from the list, or type a new value to add it to the list")
        tags = QWidget()
        tl = QHBoxLayout(tags)
        tl.setContentsMargins(0, 0, 0, 0)
        self.v_tag_action = QComboBox()
        self.v_tag_action.addItem("Add tag", bulk.ADD_TAG)
        self.v_tag_action.addItem("Remove tag", bulk.REMOVE_TAG)
        self.v_tag = QComboBox()
        self.v_tag.setToolTip("Adding a tag takes off any other tag of its group")
        tl.addWidget(self.v_tag_action)
        tl.addWidget(self.v_tag, 1)
        self.v_speaker = QComboBox()
        self.v_speaker.setEditable(True)
        self.v_date = QDateEdit(QDate.currentDate())
        self.v_date.setCalendarPopup(True)
        self.v_date.setDisplayFormat("yyyy-MM-dd")
        self.v_date.setMaximumDate(QDate.currentDate())
        for x in (self.v_text, self.v_list, tags, self.v_speaker, self.v_date):
            self.v_stack.addWidget(x)
        self.v_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.v_stack.setFixedHeight(max(x.sizeHint().height() for x in (self.v_text, self.v_list, tags)))
        self.v_note = QLabel()
        self.v_note.setWordWrap(True)
        form.addRow("Field", self.v_field)
        form.addRow("Value", self.v_stack)
        form.addRow(self.v_note)
        self.v_field.currentIndexChanged.connect(lambda *_: self._set_field_chosen())
        self._watch(self.v_field, self.v_text, self.v_list, self.v_tag_action, self.v_tag,
                    self.v_speaker, self.v_date)
        return w

    def _copy_page(self) -> QWidget:
        w, form = self._form()
        self.c_from = QComboBox()
        self.c_to = QComboBox()
        self.c_mode = QComboBox()
        self.c_mode.addItem("Overwrite", bulk.OVERWRITE)
        self.c_mode.addItem("Append (after a space)", bulk.APPEND)
        self.c_mode.addItem("Only where empty", bulk.ONLY_EMPTY)
        form.addRow("From", self.c_from)
        form.addRow("To", self.c_to)
        form.addRow("How", self.c_mode)
        self._watch(self.c_from, self.c_to, self.c_mode)
        self.c_to.currentIndexChanged.connect(lambda *_: self._sync_options())
        return w

    def _clear_page(self) -> QWidget:
        w, form = self._form()
        self.x_field = QComboBox()
        form.addRow("Field", self.x_field)
        note = QLabel("Empties the field in every selected row.")
        note.setStyleSheet(f"color: {theme.muted()};")
        form.addRow(note)
        self._watch(self.x_field)
        self.x_field.currentIndexChanged.connect(lambda *_: self._sync_options())
        return w

    def _predict_page(self) -> QWidget:
        w, form = self._form()
        self.p_field = QLabel()
        form.addRow("Field", self.p_field)
        self.p_note = QLabel()
        self.p_note.setWordWrap(True)
        form.addRow(self.p_note)
        return w

    def _predict_chosen(self):
        key = bulk.predicted_target(self.db)
        if key:
            self.p_field.setText(bulk.target(self.db, bulk.TOKENS, key).title)
            note = ("Fills each selected token's empty English translation with its suggestion, the grey "
                    "text the token dialogue shows. Translations already there are left alone, and so are "
                    "tokens without a suggestion. Check the preview and deselect any wrong ones before Apply.")
        else:
            self.p_field.setText("(no English translation field)")
            note = "Predicted translations are only for an English translation field."
        if self.level == bulk.LEMMAS:
            note = "Predicted translations are filled in on the Tokens tab."
        self.p_note.setText(note)
        self.p_note.setStyleSheet(f"color: {theme.muted()};")

    def _options(self) -> QWidget:
        w = QWidget()
        ol = QVBoxLayout(w)
        ol.setContentsMargins(0, 4, 0, 0)
        head = QLabel("Options")
        f = QFont(head.font())
        f.setBold(True)
        head.setFont(f)
        ol.addWidget(head)
        self.o_regex = QCheckBox("Regular expression")
        self.o_regex.setToolTip("Find is a regular expression; \\1 in Replace with puts back a group.\n"
                                "Letters and their diacritics count as separate characters here "
                                "(ỹ is y followed by a tilde).")
        self.o_case = QCheckBox("Match case")
        self.o_keep = QCheckBox("Keep diacritics")
        self.o_keep.setChecked(True)
        self.o_keep.setToolTip("On: tone and other marks stay on the new letter (y → j turns ỹ into j̃).\n"
                               "Off: a letter carrying a mark counts as a different letter and is left alone.")
        self.o_rename = QCheckBox("Rename soundfiles")
        self.o_rename.setChecked(True)
        self.o_rename.setToolTip("Recordings whose names change (tags, gloss in file names, word class…) "
                                 "are renamed with the change, and back again on undo.")
        self.o_dates = QCheckBox("Update comment dates")
        self.o_dates.setToolTip("On: changed comments get the session's date and go into that day's "
                                "notebook record.\nOff: they keep the dates they have.")
        for c in (self.o_regex, self.o_case, self.o_keep, self.o_rename, self.o_dates):
            ol.addWidget(c)
            c.toggled.connect(lambda *_: self.clear_preview())
        ol.addStretch(1)
        return w

    # ---- columns and rows --------------------------------------------
    def _tick_column(self) -> Column:
        return Column(TICK, "✓", lambda r: "Selected" if self.is_ticked(r) else "Not selected", closed=True,
                      tree=lambda: [ListItem("Selected"), ListItem("Not selected")], edit=_noop)

    def _columns(self, level: str) -> list[Column]:
        m = self.main
        if level == bulk.LEMMAS:
            cols = m._lemma_columns()
            cols.append(Column("file_gloss", "Gloss in file names", lambda e: e.file_gloss, edit=_noop))
        else:
            cols = [dataclasses.replace(c, edit=_noop) if c.key in ("tags", "speaker", "date") else c
                    for c in m._all_columns()]
        return [self._tick_column()] + cols

    def _default_keys(self, level: str) -> list[str]:
        saved = self.main.doc.ws.get_list(f"columns/bulk-{level}")
        if saved:
            return saved
        if level == bulk.LEMMAS:
            keys = self.main.lemmas.visible_keys() + ["file_gloss"]
        else:
            keys = self.main.all_table.visible_keys()
        return list(dict.fromkeys(keys))

    def _set_columns(self, level: str, keys: list[str]):
        table = self.tables[level]
        cols = self._columns(level)
        keys = [TICK] + [k for k in keys if k != TICK]
        table.set_columns(cols, keys)
        db = self.db
        table.setItemDelegate(PreviewDelegate(None, table))
        if level == bulk.TOKENS:
            defaults = mx.default_names(db)
            chips = ChipsDelegate(lambda r: mx.chips(db, mx.marked(r.token.tags, defaults), r.entry)
                                  if r is not None else [],
                                  table)
            table.set_delegate("tags", PreviewDelegate(chips, table))
            draw = DrawingDelegate(lambda: (db.settings.pitch_low, db.settings.pitch_high), table)
            table.set_delegate("drawing", PreviewDelegate(draw, table))
            table._keep = (chips, draw)
        table.horizontalHeader().resizeSection(0, 34)

    def _setup_columns(self):
        for level in LEVELS:
            self._set_columns(level, self._default_keys(level))

    def _configure_columns(self, level: str):
        cols = [c for c in self._columns(level) if c.key != TICK]
        current = [k for k in self.tables[level].visible_keys() if k != TICK]
        dlg = ConfigureColumnsDialog(self, [(c.key, c.title) for c in cols], current)
        if dlg.exec():
            from .. import pitchview              # pitch hidden: its columns kept where they were
            self.main.doc.ws_set(f"columns/bulk-{level}", pitchview.keep_hidden(
                self.main.doc.ws.get_list(f"columns/bulk-{level}"), dlg.chosen(), self.db.settings,
                pitchview.TOKENS))
            self._set_columns(level, dlg.chosen())
            self._fill_rows()

    def _copy_main_filters(self):
        """Start with the main window's filters: the lemma list's and All data's."""
        m = self.main
        lt, tt = self.tables[bulk.LEMMAS], self.tables[bulk.TOKENS]
        lt.proxy.filters = dict(m.lemmas.proxy.filters)
        lt.proxy.pinned = m.lemmas.proxy.pinned
        # the wordlist searches (CAWL 345, SWADESH, a taxon) and Hide empty lemmas, as the lemma
        # list has them, so Bulk edit starts on the same lemmas (the audit, 25 October)
        lt.proxy.term_match = m.lemmas.proxy.term_match
        lt.proxy.extra = m.lemmas.proxy.extra
        tt.proxy.filters = dict(m.all_table.proxy.filters)
        for level, text in ((bulk.LEMMAS, m.lemma_search.text()), (bulk.TOKENS, m.all_search.text())):
            self.searches[level].setText(text)
        for t in (lt, tt):
            t._refresh_header()
            t.proxy.refilter()

    def _fill_rows(self):
        self.tables[bulk.LEMMAS].set_rows(list(self.db.entries))
        self._fill_tokens()

    def _fill_tokens(self):
        shown = self.tables[bulk.LEMMAS].visible_rows()
        self.tables[bulk.TOKENS].set_rows([TokenRow(e, i) for e in shown for i in range(len(e.tokens))])
        self._update_count()

    def _clear_filters(self, level: str):
        self.searches[level].clear()
        self.tables[level].clear_filters()

    def _lemmas_filtered(self):
        self._fill_tokens()
        self._filters_changed()

    def _filters_changed(self):
        self.clear_preview()
        self._update_count()

    # ---- ticks -------------------------------------------------------
    def is_ticked(self, row) -> bool:
        return row_key(row) not in self.unticked

    def set_ticked(self, rows, on: bool):
        for r in rows:
            if on:
                self.unticked.discard(row_key(r))
            else:
                self.unticked.add(row_key(r))
        self.tables[self.level].model_.refresh_all()
        self.clear_preview()
        self._update_count()

    def _selected(self, level: str) -> list:
        t = self.tables[level]
        out = []                                  # by identity: lemmas can't go into a set
        for i in t.selectionModel().selectedRows():
            r = t.row_at(i)
            if r is not None and not any(r is x for x in out):
                out.append(r)
        return out

    @property
    def level(self) -> str:
        return LEVELS[self.levels.currentIndex()]

    def chosen_rows(self) -> list:
        """The rows to change: shown and ticked, in the grid's order, as (entry, token index)."""
        out = []
        for r in self.tables[self.level].visible_rows():
            if not self.is_ticked(r):
                continue
            out.append((r.entry, r.index) if isinstance(r, TokenRow) else (r, None))
        return out

    def _update_count(self):
        t = self.tables[self.level]
        shown = t.visible_rows()
        ticked = sum(1 for r in shown if self.is_ticked(r))
        noun = "lemmas" if self.level == bulk.LEMMAS else "tokens"
        n = t.active_filters()
        self.count.setText(f"{len(shown)} {noun} shown  ·  {ticked} selected"
                           + (f"  ·  {n} column filter{'s' if n != 1 else ''} on" if n else ""))

    # ---- fields and pages --------------------------------------------
    def _fill_combo(self, cb: QComboBox, items, keep=True):
        current = cb.currentData() if keep else None
        cb.blockSignals(True)
        cb.clear()
        for t in items:
            cb.addItem(t.title, t.key)
        i = cb.findData(current) if current else -1
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)

    def _level_changed(self, i: int):
        self.pages.setCurrentIndex(i)
        ts = self._targets()
        text = [t for t in ts if t.text]
        self._fill_combo(self.r_field, text)
        self._fill_combo(self.v_field, ts)
        self._fill_combo(self.c_from, text)
        self._fill_combo(self.c_to, text)
        if self.c_to.count() > 1 and self.c_to.currentIndex() == self.c_from.currentIndex():
            self.c_to.setCurrentIndex(1)
        self._fill_combo(self.x_field, text)
        self._shortcut_chosen()
        self._set_field_chosen()
        self._predict_chosen()
        self.clear_preview()
        self._update_count()

    def _op_changed(self, i: int):
        self.op_pages.setCurrentIndex(i)
        self._sync_options()
        self.clear_preview()

    def _shortcut_chosen(self):
        sc = bulk.shortcut(self.s_which.currentData())
        self.s_dir.blockSignals(True)
        self.s_dir.clear()
        for d in sc.directions:
            self.s_dir.addItem(d.label, d.key)
        self.s_dir.blockSignals(False)
        fields = [t for t in self._targets() if t.role in sc.roles]
        self._fill_combo(self.s_field, fields)
        if not fields:
            self.s_field.addItem(f"(no {' or '.join(sorted(set(sc.roles)))} field here)", "")
        self.s_note.setText(sc.description)
        self.s_note.setStyleSheet(f"color: {theme.muted()};")
        self._sync_options()

    def _set_field_chosen(self):
        key = self.v_field.currentData()
        if not key:
            return
        t = bulk.target(self.db, self.level, key)
        s = self.db.settings
        note = ""
        if t.kind == "tags":
            self.v_tag.clear()
            for path, g in s.tags.leaf_groups():
                for tg in g.tags:
                    self.v_tag.addItem(f"{tg.name}   ({' › '.join(path)})", tg.name)
                    if tg.description:
                        self.v_tag.setItemData(self.v_tag.count() - 1, tg.description, Qt.ToolTipRole)
            self.v_stack.setCurrentIndex(2)
            note = ("Adding a tag takes off any other tag of its group. A tag that isn't usual for a "
                    "lemma's word class is allowed, and marked.")
        elif t.kind == "speaker":
            self.v_speaker.clear()
            self.v_speaker.addItems(self.db.participant_codes())
            self.v_speaker.setCurrentText(self.main.session_speaker())
            self.v_stack.setCurrentIndex(3)
        elif t.kind == "date":
            self.v_stack.setCurrentIndex(4)
        elif t.closed:
            f = s.entry_field(t.name) if t.kind == "entry" else s.token_field(t.name)
            self.v_list.clear()
            self.v_list.addItem("")
            self.v_list.addItems(f.all_values() if f else [])
            self.v_stack.setCurrentIndex(1)
        else:
            self.v_text.setFont(ipa_font(14) if t.ipa else QFont())
            self.v_stack.setCurrentIndex(0)
            note = "Leave it empty to clear the field (or use Clear)."
        self.v_note.setText(note)
        self.v_note.setStyleSheet(f"color: {theme.muted()};")
        self._sync_options()

    def _sync_options(self):
        op = self.ops.currentIndex()
        self.o_regex.setEnabled(op == REPLACE)
        self.o_case.setEnabled(op == REPLACE)
        uses = op == REPLACE or (op == SHORTCUTS and bulk.shortcut(self.s_which.currentData()).uses_diacritics)
        self.o_keep.setEnabled(uses)

    # ---- preview and apply -------------------------------------------
    def options(self) -> bulk.Options:
        return bulk.Options(regex=self.o_regex.isChecked(), match_case=self.o_case.isChecked(),
                            keep_diacritics=self.o_keep.isChecked(), rename_files=self.o_rename.isChecked(),
                            update_comment_dates=self.o_dates.isChecked())

    def build_op(self):
        op = self.ops.currentIndex()
        if op == REPLACE:
            return bulk.Replace(self.r_field.currentData(), self.r_find.text(), self.r_repl.text())
        if op == SHORTCUTS:
            if not self.s_field.currentData():
                raise bulk.BulkError(f"There's no field here for {self.s_which.currentText()}.")
            return bulk.RunShortcut(self.s_field.currentData(), self.s_which.currentData(),
                                    self.s_dir.currentData())
        if op == SET:
            key = self.v_field.currentData()
            t = bulk.target(self.db, self.level, key)
            if t.kind == "tags":
                return bulk.SetValue(key, self.v_tag.currentData() or "", self.v_tag_action.currentData())
            if t.kind == "speaker":
                return bulk.SetValue(key, self.v_speaker.currentText())
            if t.kind == "date":
                return bulk.SetValue(key, self.v_date.date().toString("yyyy-MM-dd"))
            if t.closed:
                return bulk.SetValue(key, self.v_list.currentText())
            return bulk.SetValue(key, self.v_text.text())
        if op == COPY:
            return bulk.CopyField(self.c_from.currentData(), self.c_to.currentData(), self.c_mode.currentData())
        if op == CLEAR:
            return bulk.ClearField(self.x_field.currentData())
        if op == PREDICT:
            if self.level == bulk.LEMMAS:
                raise bulk.BulkError("Predicted translations are filled in on the Tokens tab.")
            key = bulk.predicted_target(self.db)
            if not key:
                raise bulk.BulkError("Predicted translations are only for an English translation field.")
            return bulk.FillPredicted(key)
        raise bulk.BulkError("Conditions arrive in version 2 (Analyze).")

    def _make_plan(self, op) -> bulk.Plan:
        folder = storage.sound_folder(self.db)
        on_disk = storage.scan_sound_folder(folder)[0]
        return bulk.plan(self.db, self.level, self.chosen_rows(), op, self.options(), folder, on_disk,
                         predictor=getattr(self.doc, "predictor", None))

    def preview(self):
        self.clear_preview()
        rows = self.chosen_rows()
        if not rows:
            self._show("Nothing is selected.", error=True)
            return
        try:
            op = self.build_op()
            bulk.target(self.db, self.level, op.target)     # checks the target exists (raises if not)
            keys = self.tables[self.level].visible_keys()
            if op.target not in keys:            # make sure the changed column can be seen
                self._set_columns(self.level, keys + [op.target])
            plan = self._make_plan(op)
        except bulk.BulkError as exc:
            self._show(str(exc), error=True)
            return
        self._show_plan(plan, op)

    def _show_plan(self, plan: bulk.Plan, op):
        self.plan, self._op = plan, op
        m = self.tables[self.level].model_
        m.preview = {(row_key_of(c.row), c.key): c for c in plan.changes}
        m.errors = {(row_key_of(p.row), p.key or op.target): p for p in plan.problems if p.row is not None}
        m.refresh_all()
        noun = "lemma" if self.level == bulk.LEMMAS else "token"
        ticked = len(self.chosen_rows())
        if plan.problems:
            n = len(plan.problems)
            grouped: dict[str, list[str]] = {}          # the same problem in many rows: one line
            for pr in plan.problems:
                refs = grouped.setdefault(pr.message, [])
                if pr.row is not None and pr.row[0].ref not in refs:
                    refs.append(pr.row[0].ref)
            lines = []
            for msg, refs in grouped.items():
                count = sum(1 for pr in plan.problems if pr.message == msg)
                where = ""
                if count > 1:
                    where = f" ({count} {noun}s: {', '.join(refs[:6])}{'…' if len(refs) > 6 else ''})"
                elif refs and not msg.startswith(refs[0]):
                    where = f" ({refs[0]})"
                lines.append(f"<li>{_esc(msg + where)}</li>")
            items = "".join(lines[:8])
            more = f"<li>… and {len(lines) - 8} more</li>" if len(lines) > 8 else ""
            self._show(f"<b>Can't apply: {n} problem{'s' if n != 1 else ''}.</b> Nothing has been "
                       f"changed.<ul>{items}{more}</ul>", error=True, rich=True)
            self.apply_btn.setEnabled(False)
            return
        changed = plan.rows_changed
        if not changed and not plan.pairs:
            self._show(f"No selected {noun} would change.")
            self.apply_btn.setEnabled(False)
            return
        warn_unusual = self.main.prefs.warn_unusual_tags
        lines = "".join(f"<li>{_esc(x)}</li>" for x in bulk.summary(plan, self.level, warn_unusual))
        if plan.unusual and warn_unusual:
            lines += "<li><a href='unusual-off'>Don't show this warning again</a></li>"
        warn = bool(plan.renames or plan.comment_dates or (plan.unusual and warn_unusual))
        self._show(f"<b>{changed} of {ticked} selected {noun}{'s' if ticked != 1 else ''} will change.</b>"
                   f"<ul>{lines}</ul>" + ("" if not plan.renames else
                                          "<span>Renamed: " + _esc(", ".join(
                                              f"{a.name} → {b.name}" for a, b in plan.renames[:4]))
                                          + (" …" if len(plan.renames) > 4 else "") + "</span>"),
                   warn=warn, rich=True)
        self.apply_btn.setEnabled(True)

    def apply(self):
        if self.plan is None or self._op is None or not self.plan.ok:
            return
        try:
            plan = self._make_plan(self._op)       # again, in case anything changed since the preview
        except bulk.BulkError as exc:
            self._show(str(exc), error=True)
            return
        if not plan.ok:
            self._show_plan(plan, self._op)
            return
        settings_changed = False
        for name, value in plan.new_values:
            f = self.db.settings.entry_field(name) if plan.level == bulk.LEMMAS else self.db.settings.token_field(name)
            if f is not None:
                f.add_value(value)
                settings_changed = True
        self._applying = True
        try:
            problems = self.doc.apply_changes(plan.label, plan.pairs, plan.renames,
                                              stamp=self.options().update_comment_dates)
        finally:
            self._applying = False
        if settings_changed:
            self.doc.settings_changed()
            self.main._setup_columns()
            self.main.refresh()
        self._fill_rows()
        self.clear_preview()
        if problems:
            self._show("Nothing was changed: " + "; ".join(problems), error=True)
            return
        noun = "lemma" if self.level == bulk.LEMMAS else "token"
        n = plan.rows_changed
        self._show(f"<b>Done:</b> {n} {noun}{'s' if n != 1 else ''} changed"
                   + (f", {len(plan.renames)} recording{'s' if len(plan.renames) != 1 else ''} renamed"
                      if plan.renames else "")
                   + ". Undo (Ctrl+Z) undoes the whole bulk edit.", rich=True)

    def clear_preview(self):
        self.plan, self._op = None, None
        if hasattr(self, "apply_btn"):
            self.apply_btn.setEnabled(False)
        for t in self.tables.values():
            m = t.model_
            if m.preview or m.errors:
                m.preview, m.errors = {}, {}
                m.refresh_all()
        if hasattr(self, "summary") and not self._applying:
            self._show("Choose an operation, then Preview to see what would change.")

    def _link(self, href: str):
        if href == "unusual-off":                    # "Don't show this warning again"
            self.main.set_unusual_warning(False)
            if self.plan is not None and self._op is not None:
                self._show_plan(self.plan, self._op)

    def tables_repaint(self):
        for t in self.tables.values():
            t.viewport().update()

    def _show(self, text: str, error=False, warn=False, rich=False):
        self.summary.setTextFormat(Qt.RichText if rich else Qt.PlainText)
        self.summary.setText(text)
        if error:
            bg, line = theme.colour("error_fill").name(), theme.colour("error").name()
        elif warn:
            bg, line = theme.wash(0.86 if not theme.dark() else 0.7).name(), theme.colour("warning").name()
        else:
            bg, line = theme.colour("alt_base").name(), theme.colour("grid").name()
        self.summary_box.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid {line}; "
                                       "border-radius: 4px; } QLabel { border: none; }")

    # ---- keeping up with the main window -------------------------------
    def _doc_changed(self):
        if self._applying:
            return
        self._fill_rows()
        self.clear_preview()

    def _settings_changed(self):
        if self._applying:
            return
        self._setup_columns()
        self._fill_shortcuts()                    # Pitch's shortcut follows Show the pitch system
        self._level_changed(self.levels.currentIndex())

    def _restyle(self):
        a = theme.accent()
        self.title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        tabs = ("QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
                f"QTabBar::tab:selected {{ background: {a.name()}; color: {theme.text_on(a).name()}; }}"
                f"QTabBar::tab:disabled {{ color: {theme.colour('disabled').name()}; }}")
        self.levels.setStyleSheet(tabs)
        self.ops.setStyleSheet(tabs)
        self.count.setStyleSheet(f"color: {theme.muted()};")
        for t in self.tables.values():
            theme.as_data(t)
        self.apply_btn.setStyleSheet(f"QPushButton:enabled {{ background: {a.name()}; "
                                     f"color: {theme.text_on(a).name()}; font-weight: bold; "
                                     "padding: 4px 18px; border-radius: 3px; }")

    def closeEvent(self, event):
        try:
            self.doc.changed.disconnect(self._doc_changed)
            self.doc.settingsChanged.disconnect(self._settings_changed)
        except (RuntimeError, TypeError):
            pass
        if getattr(self.main, "bulk_window", None) is self:
            self.main.bulk_window = None
        super().closeEvent(event)
        if event.isAccepted():
            self.deleteLater()                    # forgotten by the main window: freed, not kept hidden


def row_key_of(row) -> tuple:
    """A plan's row (entry, token index) as the grid's row key."""
    e, i = row
    return (id(e), i)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
