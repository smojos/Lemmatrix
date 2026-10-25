# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Cogitate (IDEAS.md idea 35, Josh, 21 October 2026): the window of hypotheses, and the picker that
links things to them. The hypotheses themselves are hypotheses.py; they live in the notebook.

The window (View → Cogitate, or Josh's icon between χμλ and the ? on the Matrix title's row) has
Josh's icon at its top right, as the ɛλicit request dialogue has its logo, and two tabs:

- List: one row per hypothesis (number, summary, confidence, the counts of each kind of link, last
  edited), with the usual filters and quick search, and Make, Delete and Edit. Edit is the same as
  selecting a row and clicking the Hypothesis tab; Make moves there with empty fields.
- Hypothesis: one hypothesis: its summary, careful formulation and confidence, the counts, the links
  (searched, filtered by mark and kind, broken ones shown or hidden; each opened, unlinked, marked
  or given a note), Link a hypothesis…, the hypotheses that cite this one, and Back and Next.

There is no shortcut that makes a hypothesis: they are made here, or with "Make a new hypothesis…"
in the picker (always "make", never "add"). Every change is one undo step (document.py).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSplitter,
                               QStackedWidget, QTabBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import hypotheses as hy
from . import theme
from .icons import icon, themed_icon
from .table import Column, FilterTable

LOGO = 88                         # Josh's icon at the window's top right, as in the ɛλicit request dialogue
LIST_TAB, HYPOTHESIS_TAB = 0, 1
TEXT_STEP = 1.2                   # the summary's and formulation's text: one size step above the usual


def cogitate_icon(size: int = 16):
    """Josh's Cogitate icon, its teal in the theme colour (lighter on dark)."""
    return icon("cogitate", size, theme.colour("pitch").name())


def _tool(name: str, tip: str, fn, text: str = "") -> QToolButton:
    b = QToolButton()
    if name:
        b.setIcon(themed_icon(name, 20))
        b.setIconSize(QSize(20, 20))
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if name else Qt.ToolButtonTextOnly)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.clicked.connect(lambda *_: fn())
    return b


def _stretch(table: FilterTable, key: str):
    """One column takes the room left; the others are as wide as their contents."""
    h = table.horizontalHeader()
    h.setStretchLastSection(False)
    for i, c in enumerate(table.model_.columns):
        h.setSectionResizeMode(i, QHeaderView.Stretch if c.key == key else QHeaderView.ResizeToContents)


def _split(table: FilterTable, left: str, right: str, width: int = 260):
    """Two columns share the room left: the border between them can be dragged (the left one is
    resizable, the right one takes the rest); the others are as wide as their contents."""
    h = table.horizontalHeader()
    h.setStretchLastSection(False)
    for i, c in enumerate(table.model_.columns):
        h.setSectionResizeMode(i, QHeaderView.Interactive if c.key == left else
                               QHeaderView.Stretch if c.key == right else QHeaderView.ResizeToContents)
        if c.key == left:
            h.resizeSection(i, width)


def mark_label(mark: str) -> str:
    return hy.MARK_NAMES.get(mark, mark)


# ==========================================================================
# Following a link: where each kind of link goes
# ==========================================================================

def open_link(main, link: hy.Link, parent=None) -> bool:
    """Go to what a link points at (a token in All data, an utterance, a text's line, a question in
    the notebook, a hypothesis, a snapshot's view). A gone one says so."""
    db, book = main.doc.db, main.doc.notebook
    hit = hy.find(db, book, link)
    if hit is None:
        QMessageBox.information(parent or main, "Cogitate", hy.gone_text(link) + ".")
        return False
    k = link.kind
    if k == hy.TOKEN:
        return bool(main.go_to(*hit))
    if k == hy.UTTERANCE:
        return bool(main.go_to(hit))
    if k == hy.LINE or (k == hy.COMMENT and link.token.startswith("line:")):
        w = main.open_utterances()
        w.select_text(hit)
        start = link.start
        if k == hy.COMMENT:
            try:
                start = float(link.token[len("line:"):])
            except ValueError:
                start = None
        w.texts.select_line_at(start, nearest=True)
        return True
    if k == hy.COMMENT:
        e, i = hit
        return bool(main.go_to(e, i))
    if k == hy.QUESTION:
        session, q = hit
        main.open_notebook(session.date)
        dlg = main.notebook_dialog
        if dlg is not None:
            from .notebook_dialog import QUESTIONS_TAB, TODO_TAB
            dlg.tabs.setCurrentIndex(TODO_TAB if q.is_todo else QUESTIONS_TAB)
            dlg._fill_questions(q)
        return True
    if k == hy.HYPOTHESIS:
        main.open_cogitate(hit.id)
        return True
    if k == hy.SNAPSHOT:
        main.restore_snapshot(hit)
        return True
    if k == hy.DRAWING:                            # a whiteboard drawing: opened as an image
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(hit)))
        return True
    return False


# ==========================================================================
# The link picker: Link to hypothesis…
# ==========================================================================


class LinkPicker(QDialog):
    """Which hypothesis to link to, as what, with a note; or Make a new hypothesis…"""

    MAKE = "make"

    def __init__(self, main, link: hy.Link, parent=None):
        super().__init__(parent or main)
        self.main, self.link = main, link
        self.choice = None                       # a hypothesis id, or MAKE
        self.setWindowTitle("Link to hypothesis")
        self.resize(620, 460)
        lay = QVBoxLayout(self)
        what = QLabel(f"<b>{_esc(hy.KIND_NAMES[link.kind])}:</b> {_esc(hy.label(main.doc.db, main.doc.notebook, link))}")
        what.setWordWrap(True)
        lay.addWidget(what)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search the hypotheses")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._fill())
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["No.", "Summary", "Confidence"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        self.tree.currentItemChanged.connect(lambda *_: self._buttons())
        lay.addWidget(self.tree, 1)
        marks = QHBoxLayout()
        marks.addWidget(QLabel("Link as"))
        self.marks = QButtonGroup(self)
        last = str(main.prefs.get_value("cogitate/mark") or hy.RELEVANT)     # the mark chosen last time
        for m in hy.MARKS:
            r = QRadioButton(mark_label(m))
            r.setProperty("mark", m)
            r.setChecked(m == (link.mark if link.mark != hy.RELEVANT else last))
            self.marks.addButton(r)
            marks.addWidget(r)
        marks.addStretch(1)
        lay.addLayout(marks)
        self.note = QLineEdit(link.note)
        self.note.setPlaceholderText("a note on the link, e.g. why this counts (optional)")
        lay.addWidget(self.note)
        buttons = QDialogButtonBox()
        self.make_btn = buttons.addButton("Make a new hypothesis…", QDialogButtonBox.ActionRole)
        self.make_btn.setIcon(icon("add", 18))
        self.make_btn.clicked.connect(self._make)
        self.ok_btn = buttons.addButton("Link", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill()

    def _fill(self):
        text = self.search.text()
        book = self.main.doc.notebook
        self.tree.clear()
        for h in sorted(book.hypotheses, key=lambda h: -h.number):     # the newest first
            if not hy.matches(h, text):
                continue
            it = QTreeWidgetItem([h.label, h.summary or "(no summary yet)", h.confidence])
            it.setData(0, Qt.UserRole, h.id)
            it.setToolTip(1, h.formulation or h.summary)
            self.tree.addTopLevelItem(it)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._buttons()

    def _buttons(self):
        self.ok_btn.setEnabled(self.tree.currentItem() is not None)

    def mark(self) -> str:
        b = self.marks.checkedButton()
        return b.property("mark") if b is not None else hy.RELEVANT

    def _make(self):
        self.choice = self.MAKE
        super().accept()

    def accept(self):
        it = self.tree.currentItem()
        if it is None:
            return
        self.choice = it.data(0, Qt.UserRole)
        super().accept()

    def done(self, r):
        if r:
            self.main.prefs.set_value("cogitate/mark", self.mark())
        self.link.mark = self.mark()
        self.link.note = self.note.text().strip()
        super().done(r)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ==========================================================================
# The window
# ==========================================================================

class _LinkRow:
    """A row of the links list: the link, and how it reads now."""

    def __init__(self, link: hy.Link, item: str, gone: bool, faded: bool = False):
        self.link, self.item, self.gone = link, item, gone
        self.faded = faded            # a snapshot deleted from the list: grey, still restores (24 October)

    def __eq__(self, other):
        return isinstance(other, _LinkRow) and other.link is self.link

    def __hash__(self):
        return id(self.link)


class _HypRow:
    """A row of the List: a hypothesis (looked up by id, since undo puts back copies)."""

    def __init__(self, h: hy.Hypothesis):
        self.h = h
        self.id = h.id

    def __eq__(self, other):
        return isinstance(other, _HypRow) and other.id == self.id

    def __hash__(self):
        return hash(self.id)


class CogitateWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.current_id: str | None = None
        self.shown_id: str | None = None          # the hypothesis the Hypothesis tab's fields hold
        self._loading = False
        self.setWindowTitle("Cogitate")
        from .winstate import fit_to_screen, keep
        fit_to_screen(self, 1000, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        head = QHBoxLayout()                      # the title and tabs; Josh's icon at the top right
        left = QVBoxLayout()
        self.title = main._heading("Cogitate")
        left.addWidget(self.title)
        self.sub = QLabel("Hypotheses, kept at the end of the notebook")
        left.addWidget(self.sub)
        left.addStretch(1)
        self.tabs = QTabBar()
        self.tabs.addTab("List")
        self.tabs.addTab("Hypothesis")
        self.tabs.setExpanding(False)
        self.tabs.currentChanged.connect(self._tab_changed)
        left.addWidget(self.tabs, 0, Qt.AlignLeft)
        head.addLayout(left, 1)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignRight | Qt.AlignTop)
        gap = round(LOGO * 0.15)
        self.logo.setContentsMargins(0, 0, gap, 0)
        self.logo.setToolTip("Cogitate")
        head.addWidget(self.logo, 0, Qt.AlignRight | Qt.AlignTop)
        lay.addLayout(head)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._list_page())
        self.pages.addWidget(self._hypothesis_page())
        lay.addWidget(self.pages, 1)

        for keys, fn in ((QKeySequence("Alt+Left"), self.back), (QKeySequence("Alt+Right"), self.next)):
            QShortcut(keys, self, activated=fn)
        QShortcut(QKeySequence.Undo, self, activated=lambda: (self._commit(), self.doc.undo.undo()))
        QShortcut(QKeySequence.Redo, self, activated=self.doc.undo.redo)
        self.doc.hypothesesChanged.connect(self._changed)
        keep(self, main.prefs, "window/cogitate")
        self._restyle()
        self.refill()

    # ---- the List tab ------------------------------------------------------
    def _list_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 4, 0, 0)
        self.table = FilterTable()
        cols = [
            Column("number", "No.", lambda r: r.h.label),
            Column("summary", "Summary", lambda r: r.h.summary, tooltip=lambda r: r.h.formulation or None),
            Column("confidence", "Confidence", lambda r: r.h.confidence, closed=True,
                   tree=lambda: self.doc.notebook.confidence),
            Column("evidence", "Evidence", lambda r: str(r.h.count(hy.EVIDENCE))),
            Column("counter", "Counterevidence", lambda r: str(r.h.count(hy.COUNTER))),
            Column("relevant", "Relevant", lambda r: str(r.h.count(hy.RELEVANT))),
            Column("edited", "Last edited", lambda r: r.h.edited),
        ]
        self.table.set_columns(cols, [c.key for c in cols])
        _stretch(self.table, "summary")
        self.table.rowActivated.connect(lambda r: self.edit())
        self.table.deleteRequested.connect(self.delete)
        self.table.contextRequested.connect(self._list_menu)
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self._list_selected())
        pl.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.make_btn = _tool("add", "Make a new hypothesis", self.make)
        self.delete_btn = _tool("delete", "Delete the selected hypothesis (Delete)", self.delete)
        self.edit_btn = _tool("edit", "Edit: the selected hypothesis in the Hypothesis tab (Enter)", self.edit)
        for b in (self.make_btn, self.delete_btn, self.edit_btn):
            bar.addWidget(b)
        bar.addWidget(_tool("reset-filters", "Clear all filters", self._clear_filters))
        self.list_search = QLineEdit()
        self.list_search.setPlaceholderText("quick search of the hypotheses")
        self.list_search.setClearButtonEnabled(True)
        self.list_search.textChanged.connect(lambda t: self.table.proxy.set_search(t))
        bar.addWidget(self.list_search, 1)
        self.list_count = QLabel()
        bar.addWidget(self.list_count)
        pl.addLayout(bar)
        return page

    def _list_selected(self):
        r = self.table.current_row()
        if r is not None and not self._loading:
            self.current_id = r.id
        self._list_buttons()

    def _list_buttons(self):
        on = self.table.current_row() is not None
        self.delete_btn.setEnabled(on)
        self.edit_btn.setEnabled(on)

    def _clear_filters(self):
        self.table.clear_filters()
        self.list_search.clear()

    def _list_menu(self, row, pos):
        if row is not None:
            self.table.select_row(row)
        m = QMenu(self)
        for text, name, fn, on in (("Make a new hypothesis", "add", self.make, True),
                                   ("Edit", "edit", self.edit, row is not None),
                                   ("Delete", "delete", self.delete, row is not None)):
            a = m.addAction(icon(name, 16), text)
            a.setEnabled(on)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(pos)

    # ---- the Hypothesis tab ----------------------------------------------------
    def _hypothesis_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 4, 0, 0)
        top = QHBoxLayout()
        self.number = QLabel("—")
        f = QFont(self.number.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.6)
        self.number.setFont(f)
        top.addWidget(self.number)
        self.counts = QLabel()
        top.addWidget(self.counts, 1)
        self.back_btn = QPushButton("Back")
        self.back_btn.setToolTip("The hypothesis before, in the List as it is filtered (Alt+←)")
        self.back_btn.clicked.connect(self.back)
        self.next_btn = QPushButton("Next")
        self.next_btn.setToolTip("The next hypothesis, in the List as it is filtered (Alt+→)")
        self.next_btn.clicked.connect(self.next)
        top.addWidget(self.back_btn)
        top.addWidget(self.next_btn)
        pl.addLayout(top)

        form = QFormLayout()
        self.summary = QLineEdit()
        self.summary.setPlaceholderText("the claim, usually one sentence")
        self.summary.editingFinished.connect(self._commit)
        form.addRow("Summary", self.summary)
        self.formulation = _CommitText(self._commit)
        self.formulation.setPlaceholderText("the careful formulation")
        self.formulation.setFixedHeight(120)
        form.addRow("Formulation", self.formulation)
        for w in (self.summary, self.formulation):  # one size step up from the usual text (Josh, 22 October)
            f = QFont(w.font())
            f.setPointSizeF(f.pointSizeF() * TEXT_STEP)
            w.setFont(f)
        self.confidence = QComboBox()
        self.confidence.activated.connect(lambda *_: self._commit())
        self.confidence.setToolTip("The confidence levels are edited in Edit → Lists → Confidence")
        row = QHBoxLayout()
        row.addWidget(self.confidence)
        row.addStretch(1)
        form.addRow("Confidence", row)
        pl.addLayout(form)

        split = QSplitter(Qt.Vertical)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        lhead = QLabel("Links")
        lf = QFont(lhead.font())
        lf.setBold(True)
        lhead.setFont(lf)
        ll.addWidget(lhead)
        filt = QHBoxLayout()
        self.link_search = QLineEdit()
        self.link_search.setPlaceholderText("search the links")
        self.link_search.setClearButtonEnabled(True)
        self.link_search.textChanged.connect(lambda *_: self._fill_links())
        filt.addWidget(self.link_search, 1)
        self.mark_filter = QComboBox()
        self.mark_filter.addItem("Evidence, counterevidence and relevant", "")
        for m in hy.MARKS:
            self.mark_filter.addItem(mark_label(m), m)
        self.mark_filter.currentIndexChanged.connect(lambda *_: self._fill_links())
        filt.addWidget(self.mark_filter)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("Every kind", "")
        for k in hy.KINDS:
            self.kind_filter.addItem(hy.KIND_PLURALS[k], k)
        self.kind_filter.currentIndexChanged.connect(lambda *_: self._fill_links())
        filt.addWidget(self.kind_filter)
        self.show_broken = QCheckBox("Broken links")
        self.show_broken.setToolTip("Show links whose item no longer exists")
        self.show_broken.setChecked(True)
        self.show_broken.toggled.connect(lambda *_: self._fill_links())
        filt.addWidget(self.show_broken)
        ll.addLayout(filt)
        self.links = FilterTable()
        lcols = [
            Column("kind", "Kind", lambda r: hy.KIND_NAMES[r.link.kind]),
            Column("item", "Item", lambda r: r.item, ipa=True,
                   tooltip=lambda r: hy.gone_text(r.link) if r.gone else (
                       hy.SNAPSHOT_DELETED + ": this link keeps its own copy and still restores the view"
                       if r.faded else "Double-click to go there"),
                   color=lambda r: theme.colour("error") if r.gone else (
                       theme.colour("muted") if r.faded else None)),
            Column("note", "Note", lambda r: r.link.note, edit=lambda r, t: None),   # before Mark (Josh, 22 October)
            Column("mark", "Mark", lambda r: mark_label(r.link.mark)),
            Column("linked", "Linked", lambda r: r.link.linked),
        ]
        self.links.set_columns(lcols, [c.key for c in lcols])
        _split(self.links, "item", "note")
        self.links.model_.edited.connect(self._note_edited)
        self.links.rowActivated.connect(lambda r: self.open(r))
        self.links.deleteRequested.connect(self.unlink)
        self.links.contextRequested.connect(self._link_menu)
        ll.addWidget(self.links, 1)
        lbar = QHBoxLayout()
        self.open_btn = _tool("", "Go to the selected link's item (double-click)", lambda: self.open(), "Open")
        self.unlink_btn = _tool("delete", "Unlink: take the selected link off this hypothesis", self.unlink)
        self.link_h_btn = _tool("", "Link another hypothesis to this one, as evidence, counterevidence or relevant",
                                self.link_hypothesis, "Link a hypothesis…")
        self.link_h_btn.setIcon(cogitate_icon(20))
        self.link_h_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for b in (self.unlink_btn, self.open_btn, self.link_h_btn):
            lbar.addWidget(b)
        lbar.addStretch(1)
        self.link_count = QLabel()
        lbar.addWidget(self.link_count)
        ll.addLayout(lbar)
        split.addWidget(links)

        cited = QWidget()
        cl = QVBoxLayout(cited)
        cl.setContentsMargins(0, 0, 0, 0)
        chead = QLabel("Cited by")
        chead.setFont(lf)
        chead.setToolTip("The hypotheses that link to this one")
        cl.addWidget(chead)
        self.cited = QTreeWidget()
        self.cited.setColumnCount(3)
        self.cited.setHeaderLabels(["No.", "Summary", "As"])
        self.cited.setRootIsDecorated(False)
        self.cited.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.cited.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.cited.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.cited.header().setStretchLastSection(False)
        self.cited.itemDoubleClicked.connect(lambda it, c: self.show_hypothesis(it.data(0, Qt.UserRole)))
        self.cited.setToolTip("Double-click to open that hypothesis")
        cl.addWidget(self.cited, 1)
        split.addWidget(cited)
        split.setSizes([420, 110])
        pl.addWidget(split, 1)
        return page

    # ---- filling ----------------------------------------------------------
    @property
    def book(self):
        return self.doc.notebook

    def current(self) -> hy.Hypothesis | None:
        return hy.by_id(self.book, self.current_id) if self.current_id else None

    def refill(self):
        """The List and the hypothesis shown, as they are now."""
        self._loading = True
        rows = [_HypRow(h) for h in sorted(self.book.hypotheses, key=lambda h: h.number)]
        self.table.set_rows(rows)
        if self.current_id and self.current() is not None:
            self.table.select_row(_HypRow(self.current()))
        n = len(rows)
        shown = len(self.table.visible_rows())
        self.list_count.setText(f"{shown} / {n}" if n else "")
        self.list_count.setToolTip("hypotheses shown / all")
        self._loading = False
        self._list_buttons()
        self._show()
        self._fill_confidence()

    def _fill_confidence(self):
        h = self.current()
        self.confidence.blockSignals(True)
        self.confidence.clear()
        levels = hy.confidence_list(self.book)
        if h is not None and h.confidence and h.confidence not in levels:
            levels = levels + [h.confidence]
        self.confidence.addItems(levels)
        if h is not None:
            self.confidence.setCurrentText(h.confidence)
        self.confidence.blockSignals(False)

    def _show(self):
        h = self.current()
        on = h is not None
        self._loading = True
        self.shown_id = h.id if h is not None else None
        for w in (self.summary, self.formulation, self.confidence, self.links, self.link_search,
                  self.mark_filter, self.kind_filter, self.show_broken, self.link_h_btn, self.cited):
            w.setEnabled(on)
        if h is None:
            self.number.setText("—")
            self.counts.setText("Choose a hypothesis in the List, or make one there.")
            self.summary.setText("")
            self.formulation.setPlainText("")
            self.links.set_rows([])
            self.cited.clear()
        else:
            self.number.setText(h.label)
            self.counts.setText(f"{h.count(hy.EVIDENCE)} evidence · {h.count(hy.COUNTER)} counterevidence · "
                                f"{h.count(hy.RELEVANT)} relevant")
            if self.summary.text() != h.summary:
                self.summary.setText(h.summary)
            if self.formulation.toPlainText() != h.formulation:
                self.formulation.setPlainText(h.formulation)
            self._fill_links()
            self.cited.clear()
            for o, ln in hy.cited_by(self.book, h):
                it = QTreeWidgetItem([o.label, o.summary, mark_label(ln.mark)])
                it.setData(0, Qt.UserRole, o.id)
                self.cited.addTopLevelItem(it)
        self._loading = False
        self._nav_buttons()
        self._link_buttons()

    def _fill_links(self):
        h = self.current()
        if h is None:
            self.links.set_rows([])
            self.link_count.setText("")
            return
        db, book = self.doc.db, self.book
        mark, kind = self.mark_filter.currentData(), self.kind_filter.currentData()
        text = self.link_search.text().strip().lower()
        rows = []
        for ln in h.links:
            gone = hy.is_gone(db, book, ln)
            if gone and not self.show_broken.isChecked():
                continue
            if mark and ln.mark != mark or kind and ln.kind != kind:
                continue
            item = hy.label(db, book, ln)
            if gone:
                item = f"{item}  ({hy.gone_text(ln).lower()})"
            if text and not any(text in (x or "").lower() for x in (item, ln.note, ln.text, ln.about)):
                continue
            faded = ln.kind == hy.SNAPSHOT and bool(ln.target) and hy.snapshot_listed(book, ln) is None
            rows.append(_LinkRow(ln, item, gone, faded))
        self.links.set_rows(rows)
        self.link_count.setText(f"{len(rows)} / {len(h.links)}" if h.links else "no links yet")
        self.link_count.setToolTip("links shown / all")
        self._link_buttons()

    def _link_buttons(self):
        on = self.links.current_row() is not None
        self.open_btn.setEnabled(on)
        self.unlink_btn.setEnabled(on)

    def _nav_buttons(self):
        ids = [r.id for r in self.table.visible_rows()]
        i = ids.index(self.current_id) if self.current_id in ids else -1
        self.back_btn.setEnabled(i > 0)
        self.next_btn.setEnabled(0 <= i < len(ids) - 1)

    def _changed(self):
        if not self.isVisible():
            return
        if self.current_id and self.current() is None:     # deleted, or undone
            self.current_id = None
        self.refill()

    def _tab_changed(self, i):
        self._commit()
        self.pages.setCurrentIndex(i)
        if i == HYPOTHESIS_TAB:
            if self.current_id is None:
                r = self.table.current_row()
                if r is not None:
                    self.current_id = r.id
            if self.current_id != self.shown_id or self.current_id is None:
                self._show()                      # the List's selection, not the one shown before
                self._fill_confidence()

    # ---- going places ------------------------------------------------------
    def show_hypothesis(self, ident: str | None, focus_summary: bool = False):
        """Open a hypothesis in the Hypothesis tab."""
        self._commit()
        if ident is not None and hy.by_id(self.book, ident) is None:
            return
        self.current_id = ident
        self.refill()
        self.tabs.setCurrentIndex(HYPOTHESIS_TAB)
        self.pages.setCurrentIndex(HYPOTHESIS_TAB)
        if focus_summary:
            self.summary.setFocus()

    def back(self):
        self._step(-1)

    def next(self):
        self._step(1)

    def _step(self, d: int):
        ids = [r.id for r in self.table.visible_rows()]
        if self.current_id not in ids:
            return
        i = ids.index(self.current_id) + d
        if 0 <= i < len(ids):
            self.show_hypothesis(ids[i])

    def edit(self):
        r = self.table.current_row()
        if r is not None:
            self.show_hypothesis(r.id)

    # ---- changes -------------------------------------------------------------
    def _date(self) -> str:
        return self.main.work_date()

    def make(self, links=()):
        """Make a new hypothesis: the Hypothesis tab with empty fields (and these links)."""
        self._commit()
        date = self._date()
        h = self.doc.change_hypotheses("Make hypothesis",
                                       lambda j: hy.make(self.book, j, date, links=list(links), db=self.doc.db))
        self.show_hypothesis(h.id, focus_summary=True)
        return h

    def delete(self):
        r = self.table.current_row() if self.pages.currentIndex() == LIST_TAB else None
        h = r.h if r is not None else self.current()
        if h is None:
            return
        h = hy.by_id(self.book, h.id)
        if QMessageBox.question(self, "Delete hypothesis",
                                f"Delete {h.title()}?\n\nIts number isn't given out again; hypotheses that "
                                "link to it keep the link, marked as no longer existing.") != QMessageBox.Yes:
            return
        date = self._date()
        self.doc.change_hypotheses(f"Delete {h.label}", lambda j: hy.delete(self.book, j, date, h))
        if self.current_id == h.id:
            self.current_id = None
        self.refill()

    def _commit(self):
        """The summary, formulation and confidence as typed, into the hypothesis they were filled
        from (one undo step). Never into the List's selection: selecting another hypothesis there
        changes current_id before the fields are filled again, and committing to it copied one
        hypothesis's summary and formulation over another's (Josh, 22 October)."""
        if self._loading:
            return
        h = hy.by_id(self.book, self.shown_id) if self.shown_id else None
        if h is None:
            return
        summary, formulation = self.summary.text(), self.formulation.toPlainText()
        conf = self.confidence.currentText()
        if (summary.strip(), formulation.strip(), conf) == (h.summary, h.formulation, h.confidence):
            return
        date = self._date()
        self.doc.change_hypotheses(f"Edit {h.label}",
                                   lambda j: hy.edit(self.book, j, date, h, summary, formulation,
                                                     conf if conf else None))

    def open(self, row=None):
        row = row or self.links.current_row()
        if row is not None:
            open_link(self.main, row.link, self)

    def unlink(self):
        row = self.links.current_row()
        h = self.current()
        if row is None or h is None:
            return
        date = self._date()
        self.doc.change_hypotheses(f"Unlink from {h.label}",
                                   lambda j: hy.unlink(self.book, j, date, h, row.link, self.doc.db))

    def set_mark(self, row, mark: str):
        h = self.current()
        if row is None or h is None:
            return
        date = self._date()
        self.doc.change_hypotheses(f"Mark as {mark_label(mark).lower()}",
                                   lambda j: hy.set_link(self.book, j, date, h, row.link, mark=mark, db=self.doc.db))

    def _note_edited(self, row, key, text):
        h = self.current()
        if h is None or key != "note":
            return
        date = self._date()
        QTimer.singleShot(0, lambda: self.doc.change_hypotheses(
            f"Note on a link of {h.label}",
            lambda j: hy.set_link(self.book, j, date, h, row.link, note=text, db=self.doc.db)))

    def edit_note(self, row):
        if row is None:
            return
        text, ok = QInputDialog.getText(self, "Note", "Note on the link:", text=row.link.note)
        if ok:
            self._note_edited(row, "note", text)

    def link_hypothesis(self):
        """Link another hypothesis to this one."""
        h = self.current()
        if h is None:
            return
        self._commit()
        others = [o for o in self.book.hypotheses if o.id != h.id]
        if not others:
            QMessageBox.information(self, "Cogitate", "There is no other hypothesis to link yet.")
            return
        dlg = _PickHypothesis(self, others)
        if not dlg.exec() or dlg.chosen() is None:
            return
        o = hy.by_id(self.book, dlg.chosen())
        link = hy.hypothesis_link(o, dlg.mark(), dlg.note.text())
        date = self._date()
        self.doc.change_hypotheses(f"Link {o.label} to {h.label}",
                                   lambda j: hy.add_link(self.book, j, date, h, link, self.doc.db))

    def _link_menu(self, row, pos):
        if row is not None:
            self.links.select_row(row)
        m = QMenu(self)
        a = m.addAction("Open")
        a.setEnabled(row is not None)
        a.triggered.connect(lambda *_: self.open(row))
        m.addSeparator()
        for mk in hy.MARKS:
            a = m.addAction(f"Mark as {mark_label(mk).lower()}")
            a.setCheckable(True)
            a.setChecked(row is not None and row.link.mark == mk)
            a.setEnabled(row is not None)
            a.triggered.connect(lambda *_, mk=mk: self.set_mark(row, mk))
        a = m.addAction("Edit note…")
        a.setEnabled(row is not None)
        a.triggered.connect(lambda *_: self.edit_note(row))
        m.addSeparator()
        a = m.addAction(icon("delete", 16), "Unlink")
        a.setEnabled(row is not None)
        a.triggered.connect(lambda *_: self.unlink())
        m.exec(pos)

    # ---- the window -------------------------------------------------------------
    def _restyle(self):
        a = theme.accent()
        self.title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        self.sub.setStyleSheet(f"color: {theme.muted()};")
        for lbl in (self.list_count, self.link_count, self.counts):
            lbl.setStyleSheet(f"color: {theme.muted()};")
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 14px; font-weight: normal; } "
            f"QTabBar::tab:selected {{ background: {a.name()}; color: {theme.text_on(a).name()}; }}")
        self.logo.setPixmap(cogitate_icon(LOGO).pixmap(LOGO, LOGO))
        self.link_h_btn.setIcon(cogitate_icon(20))
        for t in (self.table, self.links):
            theme.as_data(t)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange and self.isActiveWindow() and self.isVisible():
            self._fill_links()                    # back from the main window: items renamed or deleted

    def closeEvent(self, event):
        self._commit()
        super().closeEvent(event)

    def reject(self):
        self._commit()
        super().reject()


class _CommitText(QPlainTextEdit):
    """The formulation: committed when the field is left."""

    def __init__(self, commit):
        super().__init__()
        self._on_leave = commit

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._on_leave()


class _PickHypothesis(QDialog):
    """Link a hypothesis… (from the Hypothesis tab): which one, and as what."""

    def __init__(self, parent, hypotheses):
        super().__init__(parent)
        self.setWindowTitle("Link a hypothesis")
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["No.", "Summary"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for h in sorted(hypotheses, key=lambda h: h.number):
            it = QTreeWidgetItem([h.label, h.summary])
            it.setData(0, Qt.UserRole, h.id)
            self.tree.addTopLevelItem(it)
        self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.tree, 1)
        marks = QHBoxLayout()
        marks.addWidget(QLabel("Link as"))
        self.group = QButtonGroup(self)
        for m in hy.MARKS:
            r = QRadioButton(mark_label(m))
            r.setProperty("mark", m)
            r.setChecked(m == hy.RELEVANT)
            self.group.addButton(r)
            marks.addWidget(r)
        marks.addStretch(1)
        lay.addLayout(marks)
        self.note = QLineEdit()
        self.note.setPlaceholderText("a note on the link (optional)")
        lay.addWidget(self.note)
        buttons = QDialogButtonBox()
        buttons.addButton("Link", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def mark(self) -> str:
        b = self.group.checkedButton()
        return b.property("mark") if b is not None else hy.RELEVANT
