# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The notebook window (View → Notebook) and the lists of all questions, to dos and snapshots
(View → Questions, View → To Do, View → Snapshots).

The notebook is one page a day: the session's date, who was there and where, notes
(in Charis, so IPA can be typed), the comments written that day with links to
their lemmas and tokens, the recordings made that day, and the questions and to dos.
The window stays open beside the main one; changes are saved with the database
(or by Write to notebook).
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QTextCharFormat
from PySide6.QtWidgets import (QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QMenu, QStyledItemDelegate, QTabWidget, QTextEdit, QToolButton, QToolTip,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import matrix as mx, notebook as nbmod
from .. import search
from ..model import today
from . import chiprow as chips
from . import widgets as _w  # (ask: buttons that say what they do)
from . import searchmark, theme
from .icons import icon
from .widgets import ipa_font, meaning
from .searchmark import power_placeholder as _power_placeholder

NEWEST, OLDEST = "newest", "oldest"
# the notebook's tabs; Snapshots after To Do (Josh, 24 October)
QUESTIONS_TAB, TODO_TAB, SNAPSHOTS_TAB, HYPOTHESES_TAB, COMMENTS_TAB, RECORDINGS_TAB, TEXTS_TAB = range(7)
KIND_ICON = {nbmod.QUESTION: "push-question", nbmod.TODO: "push-todo"}        # the green ?, the orange flag


def _cogitate_icon(size: int = 16):
    from .cogitate import cogitate_icon
    return cogitate_icon(size)


def kind_icon(kind: str, size: int = 18):
    return icon(KIND_ICON[kind], size)


def pin_icon(size: int = 16):
    """The pushpin of a pinned question or To Do, in the theme colour (lighter on dark)."""
    return icon("pin", size, theme.colour("pitch").name())


def pin_label(q) -> str:
    return "Unpin" if q is not None and q.pinned else "Pin to the top"


HYPOTHESIS_TIP = ("Convert to hypothesis: a new hypothesis whose summary is this question, linked to it as "
                  "Relevant; the question stays here, resolved, and Cogitate opens on the hypothesis")


def convert_label(kind: str) -> str:
    """What converting an item of this kind is called: "Convert to To Do", "Convert to question"."""
    return "Convert to To Do" if kind == nbmod.QUESTION else "Convert to question"


class WrapDelegate(QStyledItemDelegate):
    """Rows tall enough for their wrapped text (tree views don't work that out themselves)."""

    def __init__(self, view, query=None):
        super().__init__(view)
        self.view = view
        self.query = query                        # () -> the search bar's text: its matches are marked
        view.header().sectionResized.connect(lambda *_: view.doItemsLayout())

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        text = self.query().strip() if self.query else ""
        if text:
            searchmark.paint_wrapped_cell(self, painter, option, index, searchmark.fold_query(text))

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        width = self.view.header().sectionSize(index.column()) - 10
        text = index.data(Qt.DisplayRole) or ""
        if width > 20 and text:
            h = wrapped_height(text, index.data(Qt.FontRole) or option.font, width) + 6
            size.setHeight(max(size.height(), h))
        return size


def wrapped_height(text: str, font, width: int) -> int:
    """How tall text is wrapped to a width as the item views draw it: at word boundaries, or
    anywhere when one word (a long run of tags, 1SG.POSS.PL.F1) is wider than the column."""
    from PySide6.QtGui import QTextLayout, QTextOption
    fm = QFontMetrics(font)
    total = 0
    for para in text.split("\n"):
        lay = QTextLayout(para, font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        lay.setTextOption(opt)
        lay.beginLayout()
        n = 0
        while True:
            line = lay.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            n += 1
        lay.endLayout()
        total += max(1, n) * fm.lineSpacing()
    return total


def wrapping(view, query=None):
    view.setWordWrap(True)
    view.setTextElideMode(Qt.ElideNone)
    view.setItemDelegate(WrapDelegate(view, query))


TOKEN_WIDTH = 220      # the Token column's width until the researcher drags it (px)


def fixed_token_column(view, column: int, prefs, key: str):
    """The Token column of Questions and To Do (Josh, 27 October): a token with many tags no longer
    widens it and squeezes the others; it keeps the width the researcher drags it to (on this
    computer, like other column widths) and its text wraps onto more lines."""
    h = view.header()
    h.setSectionResizeMode(column, QHeaderView.Interactive)
    try:
        w = int(prefs.get_value(key) or 0)
    except (TypeError, ValueError):
        w = 0
    h.resizeSection(column, w if w >= 40 else TOKEN_WIDTH)

    def keep(index, _old, new):
        if index == column and new >= 40:
            prefs.set_value(key, int(new))
    h.sectionResized.connect(keep)


def pick_date(parent, title: str, start: str, taken=(), allow_taken: bool = True) -> str:
    """Ask for a day on a calendar (none later than today). Returns YYYY-MM-DD, or ""."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    cal = QCalendarWidget()
    cal.setMaximumDate(QDate.currentDate())
    cal.setGridVisible(True)
    bold = QTextCharFormat()
    bold.setFontWeight(QFont.Bold)
    bold.setForeground(QBrush(theme.accent()))
    for d in taken:
        cal.setDateTextFormat(QDate.fromString(d, "yyyy-MM-dd"), bold)
    if start:
        cal.setSelectedDate(QDate.fromString(start, "yyyy-MM-dd"))
    lay.addWidget(cal)
    if taken:
        note = QLabel("Days in the theme colour already have notes.")
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    cal.activated.connect(lambda *_: dlg.accept())
    lay.addWidget(buttons)
    if not dlg.exec():
        return ""
    return cal.selectedDate().toString("yyyy-MM-dd")


def ask_text(parent, title: str, label: str, text: str = "", one_line: bool = False) -> str | None:
    """A few lines of text (Charis, for IPA); None if cancelled. one_line: a name (a snapshot's),
    one line, Enter for OK (a line break got into names before: the audit, 25 October)."""
    from PySide6.QtWidgets import QLineEdit
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(520, 120 if one_line else 220)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(label))
    ed = QLineEdit(text) if one_line else QPlainTextEdit(text)
    ed.setFont(ipa_font(parent.window().main.prefs.ipa_size if hasattr(parent.window(), "main") else 13))
    lay.addWidget(ed, 0 if one_line else 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    if one_line:
        lay.addStretch(1)
        ed.returnPressed.connect(dlg.accept)
        ed.selectAll()
    ed.setFocus()
    if not dlg.exec():
        return None
    return (ed.text() if one_line else ed.toPlainText()).strip()


class DateLabel(QLabel):
    """The session's date; double-click to change it."""

    def __init__(self, on_double, parent=None):
        super().__init__(parent)
        self.on_double = on_double
        self.setToolTip("Double-click to change the date")

    def mouseDoubleClickEvent(self, event):
        self.on_double()


class NotebookDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.session: nbmod.Session | None = None
        self._loading = False
        self.setWindowTitle("Notebook")
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.resize(1040, 900)
        self._build()
        self.main.doc.changed.connect(self._doc_changed)
        self.main.doc.hypothesesChanged.connect(self._hypotheses_changed)

    @property
    def db(self):
        return self.main.doc.db

    @property
    def book(self) -> nbmod.Notebook:
        return self.main.doc.notebook

    # ================================================================ layout
    def _build(self):
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        outer.addLayout(top)

        # ---- the page's header: date, people, places --------------------------
        head = QVBoxLayout()
        title = QLabel("Notebook")
        f = QFont(title.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 2.2)
        title.setFont(f)
        head.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        def label(text):
            lbl = QLabel(text)
            lf = QFont(lbl.font())
            lf.setBold(True)
            lf.setPointSizeF(lf.pointSizeF() * 1.15)
            lbl.setFont(lf)
            return lbl
        grid.addWidget(label("Session"), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.date_label = DateLabel(self._change_date)
        df = QFont(self.date_label.font())
        df.setBold(True)
        df.setPointSizeF(df.pointSizeF() * 1.3)
        self.date_label.setFont(df)
        self.weekday = QLabel()
        self.weekday.setStyleSheet(f"color: {theme.muted()};")
        dl = QHBoxLayout()
        dl.setSpacing(12)
        dl.addWidget(self.date_label)
        dl.addWidget(self.weekday)
        dl.addStretch(1)
        grid.addLayout(dl, 0, 1)
        self.rows = {}
        for r, (kind, text) in enumerate(((chips.RESEARCHERS, "Researcher(s)"),
                                          (chips.PARTICIPANTS, "Participant(s)"),
                                          (chips.LOCATIONS, "Location(s)")), start=1):
            row = chips.ChipRow(kind, lambda: self.main.doc.db, edit_list=self.main.edit_lists)
            row.changed.connect(lambda kind=kind: self._chips_changed(kind))
            self.rows[kind] = row
            grid.addWidget(label(text), r, 0, Qt.AlignLeft | Qt.AlignTop)
            grid.addWidget(row, r, 1)
        grid.setColumnStretch(1, 1)
        head.addLayout(grid)
        head.addStretch(1)
        top.addLayout(head, 3)

        # ---- the list of days ---------------------------------------------------
        side = QVBoxLayout()
        sr = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the notebook")
        _power_placeholder(self.search)          # ⚡ power search (idea 86)
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Searches the notes, people, places, comments, questions and To Dos")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._search_changed)
        self.search.textChanged.connect(lambda *_: self._search_timer.start())
        self.calendar_btn = QToolButton()
        self.calendar_btn.setIcon(icon("calendar", 24, theme.accent().name()))
        self.calendar_btn.setIconSize(QSize(24, 24))
        self.calendar_btn.setAutoRaise(True)
        self.calendar_btn.setToolTip("Choose a day on the calendar")
        self.calendar_btn.clicked.connect(lambda *_: self._calendar())
        sr.addWidget(self.search, 1)
        sr.addWidget(self.calendar_btn)
        side.addLayout(sr)
        self.days = QListWidget()
        self.days.setMinimumWidth(300)
        self.days.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.days.setTextElideMode(Qt.ElideRight)
        self.days.setSpacing(2)
        self.days.currentItemChanged.connect(lambda cur, prev: self._day_chosen(cur))
        side.addWidget(self.days, 1)
        br = QHBoxLayout()
        self.sort = QComboBox()
        self.sort.addItem("New to old", NEWEST)
        self.sort.addItem("Old to new", OLDEST)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.main.doc.ws.get("notebook/sort", NEWEST))))
        self.sort.currentIndexChanged.connect(lambda *_: self._sort_changed())
        add = QToolButton()
        add.setIcon(icon("add", 20))
        add.setAutoRaise(True)
        add.setToolTip("Add note: a note for a day (today or earlier); it starts with that day's comments, "
                       "recordings and speakers")
        add.clicked.connect(lambda *_: self.add_note())
        self.delete_note_btn = QToolButton()
        self.delete_note_btn.setIcon(icon("delete", 20))
        self.delete_note_btn.setAutoRaise(True)
        self.delete_note_btn.setToolTip("Delete note: this day's note: its notes, questions, To Dos and record of comments")
        self.delete_note_btn.clicked.connect(lambda *_: self.delete_note())
        br.addWidget(self.sort)
        br.addStretch(1)
        br.addWidget(add)
        br.addWidget(self.delete_note_btn)
        side.addLayout(br)
        top.addLayout(side, 2)

        # ---- notes, comments, questions -------------------------------------------
        split = QSplitter(Qt.Vertical)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Write plain text notes here")
        self.notes.setFont(ipa_font(self.main.prefs.ipa_size))
        self.notes.textChanged.connect(self._notes_changed)
        notes_box = QWidget()                     # the notes, with the history switches under them
        nl = QVBoxLayout(notes_box)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(2)
        nl.addWidget(self.notes, 1)
        hist = QHBoxLayout()
        self.history_ticks = {}
        for section, label in nbmod.HISTORY_LABELS.items():
            box = QCheckBox(label)
            box.setToolTip(f"Write a line under {nbmod.HISTORY_HEADINGS[section]} in the day's notes for each "
                           f"{nbmod.HISTORY_WHAT[section]}"
                           ". Switching it off leaves what is written; nothing is written later for the days "
                           "it was off. The same as File → Settings → General (this database).")
            box.toggled.connect(lambda on, sec=section: self._history_toggled(sec, on))
            self.history_ticks[section] = box
            hist.addWidget(box)
        hist.addStretch(1)
        nl.addLayout(hist)
        split.addWidget(notes_box)

        self.tabs = QTabWidget()
        self.comments = QTreeWidget()
        self.comments.setColumnCount(2)
        self.comments.setHeaderLabels(["Comment", "Link"])
        self.comments.setRootIsDecorated(False)
        wrapping(self.comments, lambda: self.search.text())
        self.comments.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.comments.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.comments.header().setStretchLastSection(False)
        self.comments.itemDoubleClicked.connect(lambda it, col: self._follow(it))
        self.comments.setContextMenuPolicy(Qt.CustomContextMenu)
        self.comments.customContextMenuRequested.connect(self._comment_menu)
        self.comments.setToolTip("The comments written this day. Double-click to go to the lemma or token.")
        self.comments.setFont(ipa_font(self.main.prefs.ipa_size))
        self.recordings = QTreeWidget()
        self.recordings.setColumnCount(4)
        self.recordings.setHeaderLabels(["Lemma", "Tags", "Speaker", "Soundfile"])
        self.recordings.setRootIsDecorated(False)
        self.recordings.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.recordings.itemDoubleClicked.connect(lambda it, col: self._follow(it))
        self.recordings.setToolTip("Tokens recorded this day (by their date). Double-click to go to one.")
        self.texts = QTreeWidget()                # texts and songs dated this day (found, not stored)
        self.texts.setColumnCount(4)
        self.texts.setHeaderLabels(["Text", "Genre", "Participants", "Recording"])
        self.texts.setRootIsDecorated(False)
        self.texts.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.texts.itemDoubleClicked.connect(lambda it, col: self._open_text(it))
        self.texts.setToolTip("Texts and songs dated this day. Double-click to open one.")
        self.hyps = QTreeWidget()                 # the hypotheses worked on that day (Cogitate)
        self.hyps.setColumnCount(3)
        self.hyps.setHeaderLabels(["No.", "Summary", "Confidence"])
        self.hyps.setRootIsDecorated(False)
        self.hyps.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.hyps.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.hyps.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.hyps.header().setStretchLastSection(False)
        self.hyps.itemDoubleClicked.connect(lambda it, col: self.main.open_cogitate(it.data(0, Qt.UserRole)))
        self.hyps.setToolTip("The hypotheses made or edited this day (links included). Double-click to "
                             "open one in Cogitate.")
        self.q_panel = ItemsPanel(self, nbmod.QUESTION)    # the Questions tab, then To Do (21 October)
        self.t_panel = ItemsPanel(self, nbmod.TODO)
        self.questions, self.todos = self.q_panel.tree, self.t_panel.tree
        self.tabs.addTab(self.q_panel, "Questions")       # first (Josh, 18 October), then To Do, Comments…
        self.tabs.addTab(self.t_panel, "To Do")
        self.s_panel = SnapshotsPanel(self)               # Snapshots, after To Do (Josh, 24 October)
        self.tabs.addTab(self.s_panel, "Snapshots")
        self.tabs.addTab(self.hyps, "Hypotheses")         # after To Do (Josh, 21 October)
        self.tabs.addTab(self.comments, "Comments")
        self.tabs.addTab(self.recordings, "Recordings")
        self.tabs.addTab(self.texts, "Texts")
        split.addWidget(self.tabs)
        split.setSizes([380, 400])
        outer.addWidget(split, 1)

        self.empty_note = QLabel()
        self.empty_note.setStyleSheet(f"color: {theme.muted()};")
        outer.addWidget(self.empty_note)

    # ============================================================== the list
    def _history_toggled(self, section: str, on: bool):
        self.main.doc.ws_set(nbmod.HISTORY_SETTINGS[section], bool(on))

    def _show_history_ticks(self):
        ws = self.main.doc.ws
        for section, box in self.history_ticks.items():
            box.blockSignals(True)
            box.setChecked(ws.get_bool(nbmod.HISTORY_SETTINGS[section], True))
            box.blockSignals(False)

    def reload(self, date: str | None = None):
        """Fill the list of days again and show a day (the one shown, if no date is given)."""
        self._show_history_ticks()
        want = date or (self.session.date if self.session and self.session in self.book.sessions else None)
        if want and (s := self.book.session(want)) is not None and want == self.main.session_date():
            if nbmod.refresh_comments(self.db, s):
                self.main.doc.notebook_changed()
        self.calendar_btn.setIcon(icon("calendar", 24, theme.accent().name()))
        self._fill_days(want)

    def _sorted(self):
        return self.book.newest_first() if self.sort.currentData() == NEWEST else \
            sorted(self.book.sessions, key=lambda s: s.date)

    def _fill_days(self, want: str | None = None):
        text = self.search.text()
        self.days.blockSignals(True)
        self.days.clear()
        chosen = None
        for s in self._sorted():
            if not nbmod.matches(s, self.db, text, self.book):
                continue
            first = nbmod.summary(s)
            people = ", ".join(s.researchers + s.participants)
            it = QListWidgetItem(f"{nbmod.long_date(s.date)}   {people}" + (f"\n{first[:70]}" if first else ""))
            f = QFont(self.days.font())
            f.setBold(True)
            it.setFont(f)
            it.setData(Qt.UserRole, s.date)
            n_open = sum(1 for q in s.questions if q.is_open)
            t_open = sum(1 for q in s.todos if q.is_open)
            it.setToolTip(f"{nbmod.weekday(s.date)} {s.date}" +
                          (f"\n{n_open} open question(s)" if n_open else "") +
                          (f"\n{t_open} open To Do(s)" if t_open else ""))
            self.days.addItem(it)
            if s.date == want:
                chosen = it
        if chosen is None and self.days.count():
            chosen = self.days.item(0)
        self.days.blockSignals(False)
        if chosen is not None:
            self.days.setCurrentItem(chosen)
        self._show(self.book.session(chosen.data(Qt.UserRole)) if chosen is not None else None)

    def _day_chosen(self, item):
        self._show(self.book.session(item.data(Qt.UserRole)) if item is not None else None)

    def _sort_changed(self):
        self.main.doc.ws_set("notebook/sort", self.sort.currentData())
        self._fill_days(self.session.date if self.session else None)

    def _search_changed(self):
        self._fill_days(self.session.date if self.session else None)
        self._highlight()
        for view in (self.comments, self.questions, self.todos, self.s_panel.tree):      # their marks
            view.viewport().update()

    # ============================================================== one day
    def _show(self, s: nbmod.Session | None):
        self.session = s
        self._loading = True
        on = s is not None
        for w in (self.notes, self.tabs, self.questions, self.todos, self.delete_note_btn, self.date_label):
            w.setEnabled(on)
        for row in self.rows.values():
            row.setEnabled(on)
        if s is None:
            self.date_label.setText("—")
            self.weekday.setText("")
            for row in self.rows.values():
                row.set_keys([])
            self.notes.setPlainText("")
            self.comments.clear()
            self.recordings.clear()
            self.texts.clear()
            self.hyps.clear()
            self.questions.clear()
            self.todos.clear()
            self.empty_note.setText("No notes match the search." if self.search.text() and self.book.sessions
                                    else "No notes yet. Add note starts a day's page; so does Write to "
                                    "notebook in the Current Session.")
            self.tabs.setTabText(QUESTIONS_TAB, "Questions")
            self.tabs.setTabText(TODO_TAB, "To Do")
            self.tabs.setTabText(SNAPSHOTS_TAB, "Snapshots")
            self.s_panel.tree.clear()
            self.tabs.setTabText(HYPOTHESES_TAB, "Hypotheses")
            self.tabs.setTabText(COMMENTS_TAB, "Comments")
            self.tabs.setTabText(RECORDINGS_TAB, "Recordings")
            self.tabs.setTabText(TEXTS_TAB, "Texts")
        else:
            self.empty_note.setText("")
            self.date_label.setText(nbmod.long_date(s.date))
            self.weekday.setText(nbmod.weekday(s.date))
            self.rows[chips.RESEARCHERS].set_keys(s.researchers)
            self.rows[chips.PARTICIPANTS].set_keys(s.participants)
            self.rows[chips.LOCATIONS].set_keys(s.locations)
            if self.notes.toPlainText() != s.notes:
                self.notes.setPlainText(s.notes)
            self._fill_comments()
            self._fill_recordings()
            self._fill_texts()
            self._fill_hypotheses()
            self._fill_questions()
            self.s_panel.fill()
        self._loading = False
        self._question_buttons()
        self._highlight()

    def _fill_comments(self):
        self.comments.clear()
        s = self.session
        bad = theme.colour("error")
        for c in s.comments:
            it = QTreeWidgetItem([c.text, c.about or c.ref])
            it.setData(0, Qt.UserRole, c)
            it.setToolTip(0, c.text)
            gone = (self.db.text_by_id(c.entry_id) is None) if c.is_line else nbmod.find(self.db, c) is None
            if gone:
                it.setForeground(1, QBrush(bad))
                it.setText(1, f"{c.about or c.ref}  ({nbmod.missing_text(c).lower()})")
                it.setToolTip(1, nbmod.missing_text(c))
            else:
                it.setToolTip(1, "Double-click to go there" +
                              (f"\nField: {c.field}" if c.field != "Comment" else ""))
                f = QFont(self.comments.font())
                f.setUnderline(True)
                it.setFont(1, f)
                it.setForeground(1, QBrush(theme.accent()))
            self.comments.addTopLevelItem(it)
        self.tabs.setTabText(COMMENTS_TAB, f"Comments ({len(s.comments)})")
        QTimer.singleShot(0, self.comments.doItemsLayout)

    def _fill_recordings(self):
        self.recordings.clear()
        db = self.db
        defaults = mx.default_names(db)
        rows = nbmod.recordings(db, self.session.date)
        for e, i in rows:
            t = e.tokens[i]
            tags = " + ".join(mx.chips(db, [x for x in t.tags if x not in defaults]))
            from ..model import is_utterance
            if is_utterance(e):                   # marked as an utterance (they have no lemma)
                what = f"{e.ref} “{e.label}”" if e.label else e.ref
                it = QTreeWidgetItem([what, f"utterance{' · ' + tags if tags else ''}", t.speaker, t.file])
            else:
                it = QTreeWidgetItem([f"{e.ref} {db.lemma(e)} {meaning(db.gloss(e))}", tags or "citation", t.speaker,
                                      t.file])
            it.setFont(0, ipa_font(self.main.prefs.ipa_size))
            it.setData(0, Qt.UserRole, (e, i))
            self.recordings.addTopLevelItem(it)
        self.tabs.setTabText(RECORDINGS_TAB, f"Recordings ({len(rows)})")

    def _fill_questions(self, select: nbmod.Question | None = None):
        """Both lists, questions and to dos (an item selected in whichever it is in)."""
        for panel in (self.q_panel, self.t_panel):
            panel.fill(select)

    def _highlight(self):
        """Mark what the search found in the notes."""
        sels = []
        items = search.parse(self.search.text()).raw_items     # every item not left out (idea 86)
        if items:
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(theme.colour("selected_token")))
            doc = self.notes.document()
            for text in items:
                cur = doc.find(text, 0)
                while not cur.isNull():
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor, sel.format = cur, fmt
                    sels.append(sel)
                    cur = doc.find(text, cur)
        self.notes.setExtraSelections(sels)

    # ============================================================== editing
    def _changed(self):
        self.main.doc.notebook_changed()

    def _notes_changed(self):
        if self._loading or self.session is None:
            return
        self.session.notes = self.notes.toPlainText()
        if not self.book.dirty:
            self._changed()
        else:
            self.book.dirty = True
        self._highlight()

    def _chips_changed(self, kind):
        if self._loading or self.session is None:
            return
        setattr(self.session, kind, list(self.rows[kind].keys))
        self._changed()
        self._refresh_day_item()
        if self.session.date == self.main.session_date():
            self.main._fill_session()          # the panel shows the day it is working on

    def _refresh_day_item(self):
        date = self.session.date if self.session else None
        self._fill_days(date)

    def _doc_changed(self):
        """Edits in the main window: the day being worked on shows its comments as they are now."""
        if not self.isVisible() or self.session is None:
            return
        if self.session.date == self.main.session_date() and nbmod.refresh_comments(self.db, self.session):
            self.book.dirty = True
            self.main.doc.dirtyChanged.emit(True)
        self._fill_comments()
        self._fill_recordings()

    def _change_date(self):
        s = self.session
        if s is None:
            return
        taken = [x.date for x in self.book.sessions if x is not s]
        date = pick_date(self, "Session date", s.date, taken)
        if not date or date == s.date:
            return
        if date in taken:
            QMessageBox.warning(self, "Notebook", f"There are already notes for {date}. "
                                "One day has one page: delete one of them, or copy the notes across.")
            return
        s.date = date
        self.book.sort()
        self._changed()
        self._fill_days(date)

    def add_note(self, date: str | None = None):
        taken = [s.date for s in self.book.sessions]
        if date is None:
            start = self.main.session_date() if self.main.session_date() not in taken else today()
            date = pick_date(self, "Add a note for which day?", start, taken)
            if not date:
                return
        if (s := self.book.session(date)) is not None:
            self._fill_days(s.date)
            return
        try:
            s = self.book.add_session(date)
        except nbmod.NotebookError as exc:
            QMessageBox.warning(self, "Notebook", str(exc))
            return
        # what the database already knows about the day
        if date == self.main.session_date():
            keys = self.main.session_keys()
            s.researchers = keys[chips.RESEARCHERS]
            s.participants = keys[chips.PARTICIPANTS]
            s.locations = keys[chips.LOCATIONS]
        else:
            s.participants = nbmod.speakers(self.db, date)
        nbmod.refresh_comments(self.db, s)
        self._changed()
        if self.search.text() and not nbmod.matches(s, self.db, self.search.text(), self.book):
            self.search.clear()
        self._fill_days(date)
        self.notes.setFocus()

    def delete_note(self):
        s = self.session
        if s is None:
            return
        what = []
        if s.notes.strip():
            what.append("its notes")
        if s.questions:
            what.append(f"{len(s.questions)} question(s)")
        if s.todos:
            what.append(f"{len(s.todos)} To Do(s)")
        if s.comments:
            what.append(f"the record of {len(s.comments)} comment(s)")
        if s.snapshots:                            # (deleted with the day without a word before:
            what.append(f"{len(s.snapshots)} snapshot(s)")   # the audit, 25 October)
        if s.hypotheses:
            what.append(f"the record of {len(s.hypotheses)} hypothesis(es) worked on that day (the hypotheses stay)")
        if not _w.ask(self, "Delete note", f"Delete the note for {s.date}" +
                                (f", with {', '.join(what)}" if what else "") +
                                "?\n\nThe lemmas, tokens and their comments stay in the database.", "Delete note"):
            return
        self.book.remove(s)
        self._changed()
        self._fill_days()

    def _calendar(self):
        taken = [s.date for s in self.book.sessions]
        date = pick_date(self, "Go to a day", self.session.date if self.session else today(), taken)
        if not date:
            return
        if date in taken:
            self.search.clear()
            self._fill_days(date)
        elif _w.ask(self, "Notebook", f"There are no notes for {date}. Add a note for "
                                  "that day?", "Add a note"):
            self.add_note(date)

    def _fill_texts(self):
        self.texts.clear()
        db = self.db
        genre = db.settings.text_field("genre")
        ids = set(self.session.texts)             # the texts worked on that day (21 October)
        rows = [t for t in db.texts if t.id in ids]
        for t in rows:
            it = QTreeWidgetItem([f"{t.ref} {db.text_title(t)}", t.get(genre.name) if genre else "",
                                  " ".join(t.participants), t.file])
            it.setData(0, Qt.UserRole, t)
            self.texts.addTopLevelItem(it)
        self.tabs.setTabText(TEXTS_TAB, f"Texts ({len(rows)})")

    def _hypotheses_changed(self):
        """A hypothesis changed (or was undone): its line in the notes, and the Hypotheses tab."""
        if self.session is None or not self.isVisible():   # hidden: reloaded when opened again
            return
        if self.session not in self.book.sessions:       # an undo took the day away again
            self.reload()
            return
        if self.notes.toPlainText() != self.session.notes:
            self._loading = True
            cur = self.notes.textCursor().position()
            self.notes.setPlainText(self.session.notes)
            c = self.notes.textCursor()
            c.setPosition(min(cur, len(self.session.notes)))
            self.notes.setTextCursor(c)
            self._loading = False
        self._fill_hypotheses()

    def _fill_hypotheses(self):
        from .. import hypotheses as hy
        self.hyps.clear()
        ids = list(self.session.hypotheses)
        for hid in ids:
            h = hy.by_id(self.book, hid)
            if h is None:                         # deleted since
                continue
            it = QTreeWidgetItem([h.label, h.summary, h.confidence])
            it.setData(0, Qt.UserRole, h.id)
            it.setToolTip(1, h.formulation or h.summary)
            self.hyps.addTopLevelItem(it)
        self.tabs.setTabText(HYPOTHESES_TAB, f"Hypotheses ({self.hyps.topLevelItemCount()})")

    def _comment_menu(self, pos):
        it = self.comments.itemAt(pos)
        c = it.data(0, Qt.UserRole) if it is not None else None
        m = QMenu(self.comments)
        a = m.addAction("Go there")
        a.setEnabled(c is not None)
        a.triggered.connect(lambda *_: self._follow(it))
        a = m.addAction(_cogitate_icon(), "Link to hypothesis…")
        a.setEnabled(c is not None and self.session is not None)
        a.triggered.connect(lambda *_: self._link_comment(c))
        m.exec(self.comments.viewport().mapToGlobal(pos))

    def _link_comment(self, c):
        from .. import hypotheses as hy
        if c is not None and self.session is not None:
            self.main.link_to_hypothesis(hy.comment_link(self.session, c), self)
            self.reload()

    def _open_text(self, item):
        t = item.data(0, Qt.UserRole)
        if t is not None and t in self.db.texts:
            w = self.main.open_utterances()
            w.select_text(t)

    def _follow(self, item):
        data = item.data(0, Qt.UserRole)
        if isinstance(data, nbmod.NoteComment) and data.is_line:     # a text's line: shown in its text
            text = self.db.text_by_id(data.entry_id)
            if text is None:
                QMessageBox.information(self, "Notebook", nbmod.missing_text(data) + ".")
                return
            w = self.main.open_utterances()
            w.select_text(text)
            w.texts.select_line_at(data.line_start)
        elif isinstance(data, nbmod.NoteComment):
            where = nbmod.find(self.db, data)
            if where is None:
                QMessageBox.information(self, "Notebook", nbmod.missing_text(data) + ".")
                return
            self.main.go_to(*where)
        elif isinstance(data, tuple):
            self.main.go_to(*data)

    # ---- questions (the ItemsPanel does the work; these names are kept for the Questions tab) --
    def _question_buttons(self):
        for panel in (self.q_panel, self.t_panel):
            panel.buttons()

# ==========================================================================
# View → Questions and View → To Do
# ==========================================================================

ALL, OPEN, RESOLVED = "all", "open", "resolved"


def link_look(item, column: int, q):
    """A question's token link: in the link colour, underlined, with a tooltip."""
    if q.link is None:
        return
    f = QFont(item.font(column))
    f.setUnderline(True)
    item.setFont(column, f)
    item.setForeground(column, QBrush(theme.colour("pitch")))
    item.setToolTip(column, "Double-click to go to this token")


def follow_link(parent, main, link):
    if link.is_line:                              # a text's line (pushed from its Comment): shown in its text
        text = main.doc.db.text_by_id(link.entry_id)
        if text is None:
            QMessageBox.information(parent, "Notebook", nbmod.missing_text(link) + ".")
            return
        w = main.open_utterances()
        w.select_text(text)
        w.texts.select_line_at(link.line_start)
        return
    where = nbmod.find(main.doc.db, link)
    if where is None:
        QMessageBox.information(parent, "Notebook", nbmod.missing_text(link) + ".")
        return
    main.go_to(*where)


class ItemActions:
    """What the notebook's Questions and To Do tabs and View → Questions and View → To Do share
    (Josh, 26 October: the same capabilities in both; the tab is the window filtered to its day).
    current() gives (session, item); each action is written once, here."""

    kind = nbmod.QUESTION

    def _main(self):
        raise NotImplementedError

    def current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    _current = current

    def _add_day(self):
        """The day a new item goes on: None for the Current Session's (the View windows)."""
        return None

    def _after(self, select=None):
        """The notebook changed: unsaved, this list filled again, the other places following."""
        main = self._main()
        main.doc.notebook_changed()
        self._fill(select)
        notebook_items_changed(main, self)

    # ---- the actions -------------------------------------------------------
    def add(self):
        """A new open item, linked to nothing: on the tab's day, or (the View windows) on the
        Current Session's day, which gets its notes with the session's people and places if it has
        none yet."""
        one = nbmod.name(self.kind)
        text = ask_text(self, f"Add {one if self.kind == nbmod.TODO else one.lower()}", f"{one}:")
        text = (text or "").strip()
        if not text:
            return
        main = self._main()
        day = self._add_day()
        if day is not None:
            q = nbmod.Question(text, today(), kind=self.kind)
            nbmod.items(day, self.kind).append(q)
        else:
            from . import chiprow as chips
            keys = main.session_keys()
            q = nbmod.push_question(main.doc.notebook, main.doc.db, main.work_date(), text, None, None,
                                    keys[chips.RESEARCHERS], keys[chips.PARTICIPANTS],
                                    keys[chips.LOCATIONS], self.kind)
            self._show_open()
        self._after(q)

    def _show_open(self):
        pass

    def edit(self):
        cur = self.current()
        if cur is None:
            return
        s, q = cur
        one = nbmod.name(self.kind)
        text = ask_text(self, f"Edit {one if self.kind == nbmod.TODO else one.lower()}",
                        f"{one} (from {s.date}):", q.text)
        if text and text != q.text:
            q.text, q.edited = text, today()
            self._after(q)

    def delete(self):
        cur = self.current()
        if cur is None:
            return
        s, q = cur
        one = nbmod.name(self.kind, title=False)
        if not _w.ask(self, f"Delete {one}", f"Delete this {one}?\n\n{q.text}", f"Delete {nbmod.name(self.kind, title=self.kind == nbmod.TODO)}"):
            return
        nbmod.items(s, self.kind).remove(q)
        self._after()

    def toggle(self):
        """Resolve / Mark as open."""
        cur = self.current()
        if cur is None:
            return
        q = cur[1]
        q.set_resolved("" if q.resolved else today())
        self._after(q)

    def toggle_pin(self):
        """Pin to the top / Unpin (Josh, 22 October)."""
        cur = self.current()
        if cur is None:
            return
        q = cur[1]
        q.pinned = not q.pinned
        self._after(q)

    def convert(self):
        """Convert to To Do / Convert to question: it moves to the other list, its day, dates and
        link kept."""
        cur = self.current()
        if cur is None:
            return
        s, q = cur
        nbmod.convert(s, q)
        self._after()
        self._moved(q)

    def _moved(self, q):
        pass

    def to_hypothesis(self):
        """Convert to hypothesis: a new hypothesis from the question (it stays, resolved)."""
        cur = self.current()
        if cur is None:
            return
        self._main().question_to_hypothesis(*cur)
        self._everywhere(cur[1])

    def link_to_hypothesis(self):
        """Link to hypothesis…: this question or To Do (it gets an id, kept after)."""
        from .. import hypotheses as hy
        cur = self.current()
        if cur is None:
            return
        s, q = cur
        main = self._main()
        had = q.id
        link = hy.question_link(s, q)
        if not had:
            main.doc.notebook_changed()     # the id is written with the notebook
        main.link_to_hypothesis(link, self)
        self._everywhere(q)

    def _everywhere(self, select=None):
        """After a hypothesis was made or linked: this list and the other places."""
        self._fill(select)
        notebook_items_changed(self._main(), self)

    def go_to_token(self):
        cur = self.current()
        if cur is not None and cur[1].link is not None:
            follow_link(self, self._main(), cur[1].link)

    # ---- the menu ----------------------------------------------------------
    def _menu_items(self, cur):
        on = cur is not None
        q = cur[1] if on else None
        one = nbmod.name(self.kind, title=False)
        return [(f"Add a {one}…", icon("add", 16), self.add, self._can_add()),
                (f"Edit {one}…", icon("edit", 16), self.edit, on),
                ("Mark as open" if on and not q.is_open else "Resolve", icon("resolve", 16), self.toggle, on),
                (pin_label(q), pin_icon(), self.toggle_pin, on),
                (convert_label(self.kind), kind_icon(nbmod.other(self.kind), 16), self.convert, on),
                *((("Convert to hypothesis", _cogitate_icon(), self.to_hypothesis, on),)
                  if self.kind == nbmod.QUESTION else ()),
                ("Go to token", None, self.go_to_token, on and q.link is not None),
                ("Link to hypothesis…", _cogitate_icon(), self.link_to_hypothesis, on),
                *self._extra_menu_items(cur),
                (f"Delete {one}", icon("delete", 16), self.delete, on)]

    def _can_add(self):
        return True

    def _extra_menu_items(self, cur):
        return ()

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is not None:
            self.tree.setCurrentItem(it)
        m = QMenu(self.tree)
        for text, ic, fn, enabled in self._menu_items(self.current()):
            a = m.addAction(ic, text) if ic is not None else m.addAction(text)
            a.setEnabled(enabled)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _double_clicked(self, item, column):
        q = item.data(0, Qt.UserRole)[1]
        if column == self.LINK_COLUMN and q.link is not None:      # the token's link: go to it
            self.go_to_token()
        else:
            self.edit()

    def _item(self, cols, s, q):
        it = QTreeWidgetItem(cols)
        it.setData(0, Qt.UserRole, (s, q))
        col = self.LINK_COLUMN - 1
        if q.pinned:
            it.setIcon(col, pin_icon())
        it.setToolTip(col, q.text)
        link_look(it, self.LINK_COLUMN, q)
        if not q.is_open:
            muted = QBrush(QColor(theme.muted()))
            for c in range(self.tree.columnCount()):
                if c != self.LINK_COLUMN:
                    it.setForeground(c, muted)
        return it


def refresh_notebook(main, date=None):
    """An open notebook window shows a change (main.refresh_notebook; a stand-in main may not have it)."""
    fn = getattr(main, "refresh_notebook", None)
    if callable(fn):
        fn(date)


def notebook_items_changed(main, origin=None):
    """A question or To Do changed in one place: the notebook window, the View windows that are
    open (not the one it changed in) and the badges follow. A hidden notebook is filled when next
    opened (open_notebook reloads it)."""
    nb = getattr(main, "notebook_dialog", None)
    if nb is not None and nb is not origin and getattr(origin, "dlg", None) is not nb and nb.isVisible():
        nb.reload()
    for dlg in getattr(main, "items_dialogs", {}).values():
        if dlg is not origin and dlg.isVisible() and callable(getattr(dlg, "refresh", None)):
            dlg.refresh()
    if callable(getattr(main, "update_badges", None)):
        main.update_badges()


class ItemsPanel(QWidget, ItemActions):
    """A notebook tab of questions or to dos (Josh, 21 October: To Do is the same as Questions):
    the day's items, with the View window's actions (Josh, 26 October); buttons at the top, the
    same and more on right-click."""

    LINK_COLUMN = 1

    def __init__(self, dlg: "NotebookDialog", kind: str):
        QWidget.__init__(self)
        self.dlg, self.kind = dlg, kind
        one = nbmod.name(kind, title=False)
        ql = QVBoxLayout(self)
        ql.setContentsMargins(0, 0, 0, 0)
        qb = QHBoxLayout()

        def qbutton(name, tip, fn, size=30, ic=None):
            b = QToolButton()
            b.setIcon(ic or icon(name, size))
            b.setIconSize(QSize(size, size))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda *_: fn())
            qb.addWidget(b)
            return b
        self.add_btn = qbutton("add", f"Add a {one}", self.add)
        self.delete_btn = qbutton("delete", f"Delete the selected {one}", self.delete)
        self.edit_btn = qbutton("edit", f"Edit the selected {one}", self.edit)
        self.resolve_btn = qbutton("resolve", f"Resolve the selected {one}", self.toggle)
        to = nbmod.other(kind)
        self.convert_btn = qbutton("", f"{convert_label(kind)}: the selected {one} moves to the "
                                   f"{nbmod.name(to, True)} tab, keeping its dates and link", self.convert,
                                   ic=kind_icon(to, 30))
        self.hypothesis_btn = None
        if kind == nbmod.QUESTION:                    # Convert to hypothesis (Josh, 22 October)
            self.hypothesis_btn = qbutton("", HYPOTHESIS_TIP, self.to_hypothesis, ic=_cogitate_icon(30))
        self.pin_btn = qbutton("", f"Pin the selected {one} to the top of the list (resolving it unpins it)",
                               self.toggle_pin, ic=pin_icon(30))
        self.link_btn = qbutton("", f"Link the selected {one} to a hypothesis", self.link_to_hypothesis,
                                ic=_cogitate_icon(30)) if kind == nbmod.TODO else None
        qb.addStretch(1)
        ql.addLayout(qb)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels([nbmod.name(kind), "Token", "Status", "Created / edited", "Resolved"])
        self.tree.setRootIsDecorated(False)
        wrapping(self.tree, lambda: dlg.search.text())
        self.tree.setFont(ipa_font(dlg.main.prefs.ipa_size))
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        fixed_token_column(self.tree, self.LINK_COLUMN, dlg.main.prefs, f"columns/{kind}/token-width")
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self.buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        ql.addWidget(self.tree, 1)

    def _main(self):
        return self.dlg.main

    @property
    def session(self):
        return self.dlg.session

    def _add_day(self):
        return self.session

    def _can_add(self):
        return self.session is not None

    def _fill(self, select=None):
        self.fill(select)

    def _everywhere(self, select=None):
        self.dlg.reload()                              # the Hypotheses tab and the notes too
        self.fill(select)
        notebook_items_changed(self.dlg.main, self)

    def _moved(self, q):
        self.dlg._fill_days(self.session.date)        # the day's tooltip counts
        self.dlg._fill_questions()
        QToolTip.showText(self.tree.viewport().mapToGlobal(self.tree.viewport().rect().topLeft()),
                          f"Moved to {'To Do' if q.is_todo else 'Questions'}", self.tree)

    def fill(self, select: nbmod.Question | None = None):
        self.tree.clear()
        s = self.session
        if s is None:
            return
        lst = nbmod.items(s, self.kind)
        for q in [x for x in lst if x.pinned] + [x for x in lst if not x.pinned]:   # pinned on top
            it = self._item([q.text, nbmod.about_now(self.dlg.main.doc.db, q), q.status, q.dated, q.resolved], s, q)
            self.tree.addTopLevelItem(it)
            if q is select:
                self.tree.setCurrentItem(it)
        open_ = sum(1 for q in lst if q.is_open)
        title = "Questions" if self.kind == nbmod.QUESTION else "To Do"
        self.dlg.tabs.setTabText(QUESTIONS_TAB if self.kind == nbmod.QUESTION else TODO_TAB,
                                 f"{title} ({open_} open)" if lst else title)
        self.buttons()
        QTimer.singleShot(0, self.tree.doItemsLayout)

    def buttons(self):
        cur = self.current()
        q = cur[1] if cur is not None else None
        for b in (self.delete_btn, self.edit_btn, self.resolve_btn, self.convert_btn, self.pin_btn,
                  self.hypothesis_btn, self.link_btn):
            if b is not None:
                b.setEnabled(q is not None)
        self.add_btn.setEnabled(self.session is not None)
        self.pin_btn.setToolTip("Unpin the selected item" if q is not None and q.pinned else
                                f"Pin the selected {nbmod.name(self.kind, title=False)} to the top of the "
                                "list (resolving it unpins it)")
        one = nbmod.name(self.kind, title=False)
        self.resolve_btn.setToolTip(f"Mark the selected {one} as open again" if q and not q.is_open
                                    else f"Resolve the selected {one}")


class ItemsDialog(QDialog, ItemActions):
    """Every question (or to do) in the notebook, newest day first; the same actions as the
    notebook's tab (Josh, 26 October)."""

    LINK_COLUMN = 2

    def __init__(self, main, kind: str = nbmod.QUESTION):
        QDialog.__init__(self, main)
        self.main, self.kind = main, kind
        one, many = nbmod.name(kind, title=False), nbmod.name(kind, True, title=False)
        self.setWindowTitle("Questions" if kind == nbmod.QUESTION else "To Do")
        self.setWindowIcon(kind_icon(kind, 32))
        # Not modal: the main window stays usable beside it, and it can be minimised (Josh, 22 October)
        self.setModal(False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.resize(980, 620)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.show_which = QComboBox()
        self.show_which.addItem(f"Open {many}", OPEN)
        self.show_which.addItem(f"Resolved {many}", RESOLVED)
        self.show_which.addItem(f"All {many}", ALL)
        self.show_which.currentIndexChanged.connect(lambda *_: self._fill())
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search the {many}")
        _power_placeholder(self.search)          # ⚡ power search (idea 86)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._fill())
        top.addWidget(self.show_which)
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Session", nbmod.name(kind), "Token", "Status", "Created / edited", "Resolved"])
        self.tree.setRootIsDecorated(False)
        wrapping(self.tree, lambda: self.search.text())
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setFont(ipa_font(main.prefs.ipa_size))
        h = self.tree.header()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setStretchLastSection(False)
        fixed_token_column(self.tree, self.LINK_COLUMN, main.prefs, f"columns/{kind}/token-width")
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self._buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        # Add, at the bottom left (Josh, 25 October): onto the Current Session's day in the notebook
        self.add_btn = QPushButton(icon("add", 18), "")
        self.add_btn.setToolTip(f"Add a {one}, on the Current Session's day in the notebook")
        self.add_btn.clicked.connect(lambda *_: self.add())
        self.resolve_btn = QPushButton(icon("resolve", 18), "Resolve")
        self.resolve_btn.clicked.connect(lambda *_: self.toggle())
        self.edit_btn = QPushButton(icon("edit", 18), "")
        self.edit_btn.setToolTip(f"Edit the selected {one}")
        self.edit_btn.clicked.connect(lambda *_: self.edit())
        self.convert_btn = QPushButton(kind_icon(nbmod.other(kind), 18), "")      # icon only, named in its tooltip
        self.convert_btn.setToolTip(f"{convert_label(kind)}: the selected {one} moves to "
                                    f"{'View → To Do' if kind == nbmod.QUESTION else 'View → Questions'} "
                                    "(and the notebook's other tab), keeping its day, dates and link")
        self.convert_btn.clicked.connect(lambda *_: self.convert())
        self.hypothesis_btn = None
        if kind == nbmod.QUESTION:                    # Convert to hypothesis (Josh, 22 October)
            self.hypothesis_btn = QPushButton(_cogitate_icon(18), "")
            self.hypothesis_btn.setToolTip(HYPOTHESIS_TIP)
            self.hypothesis_btn.clicked.connect(lambda *_: self.to_hypothesis())
        self.link_btn = None
        if kind == nbmod.TODO:                        # (a question's Cogitate button converts it)
            self.link_btn = QPushButton(_cogitate_icon(18), "")
            self.link_btn.setToolTip(f"Link the selected {one} to a hypothesis")
            self.link_btn.clicked.connect(lambda *_: self.link_to_hypothesis())
        self.pin_btn = QPushButton(pin_icon(18), "")
        self.pin_btn.setToolTip(f"Pin the selected {one} to the top of the list (resolving it unpins it)")
        self.pin_btn.clicked.connect(lambda *_: self.toggle_pin())
        self.delete_btn = QPushButton(icon("delete", 18), "")
        self.delete_btn.setToolTip(f"Delete the selected {one}")
        self.delete_btn.clicked.connect(lambda *_: self.delete())
        self.open_btn = QPushButton(icon("notebook", 18, theme.accent().name()), "Open in notebook")
        self.open_btn.clicked.connect(lambda *_: self.open_day())
        self.token_btn = QPushButton("Go to token")
        self.token_btn.setToolTip(f"Show the token the {one} was pushed from (also: double-click its link)")
        self.token_btn.clicked.connect(lambda *_: self.go_to_token())
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {theme.muted()};")
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for w in (self.add_btn, self.resolve_btn, self.edit_btn, self.pin_btn, self.convert_btn,
                  self.hypothesis_btn, self.link_btn, self.delete_btn, self.open_btn, self.token_btn):
            if w is not None:
                row.addWidget(w)
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def _main(self):
        return self.main

    def _all(self):
        return self.main.doc.notebook.all_items(self.kind)

    def refresh(self):
        """Fill the list again from the notebook, keeping the selection (the notebook may have
        changed while this window was open beside the main window)."""
        cur = self._current()
        self._fill(cur[1] if cur is not None else None)

    def _notebook_follows(self):
        notebook_items_changed(self.main, self)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.refresh()

    def _show_open(self):
        if self.show_which.currentData() == RESOLVED:
            self.show_which.setCurrentIndex(self.show_which.findData(OPEN))

    def _moved(self, q):
        self.count.setText(self.count.text() + f" · moved to {'To Do' if q.is_todo else 'Questions'}")

    def _extra_menu_items(self, cur):
        return (("Open in notebook", icon("notebook", 16, theme.accent().name()), self.open_day, cur is not None),)

    def _fill(self, select=None):
        which = self.show_which.currentData()
        text = self.search.text()
        self.tree.clear()
        shown = 0
        for s, q in self._all():
            if (which == OPEN and not q.is_open) or (which == RESOLVED and q.is_open):
                continue
            if not search.matches(text, (q.text, s.date)):      # one search for every bar (idea 86)
                continue
            it = self._item([s.date, q.text, nbmod.about_now(self.main.doc.db, q), q.status, q.dated, q.resolved], s, q)
            self.tree.addTopLevelItem(it)
            shown += 1
            if q is select:
                self.tree.setCurrentItem(it)
        every = self._all()
        open_ = sum(1 for _, q in every if q.is_open)
        self.count.setText(f"{shown} shown · {open_} open of {len(every)}")
        self._buttons()
        QTimer.singleShot(0, self.tree.doItemsLayout)      # wrapped items get their height

    def _buttons(self):
        cur = self._current()
        for b in (self.resolve_btn, self.edit_btn, self.convert_btn, self.open_btn, self.hypothesis_btn,
                  self.pin_btn, self.link_btn, self.delete_btn):
            if b is not None:
                b.setEnabled(cur is not None)
        self.pin_btn.setToolTip("Unpin the selected item" if cur is not None and cur[1].pinned else
                                f"Pin the selected {nbmod.name(self.kind, title=False)} to the top of the "
                                "list (resolving it unpins it)")
        self.resolve_btn.setText("Mark as open" if cur and not cur[1].is_open else "Resolve")
        self.token_btn.setEnabled(cur is not None and cur[1].link is not None)

    def open_day(self):
        cur = self._current()
        if cur is None:
            return
        self.main.open_notebook(cur[0].date)
        if getattr(self.main, "notebook_dialog", None) is not None:      # on the tab it is in
            self.main.notebook_dialog.tabs.setCurrentIndex(TODO_TAB if cur[1].is_todo else QUESTIONS_TAB)
            self.main.notebook_dialog._fill_questions(cur[1])
        self.accept()


class QuestionsDialog(ItemsDialog):
    """View → Questions."""

    def __init__(self, main):
        super().__init__(main, nbmod.QUESTION)


class TodoDialog(ItemsDialog):
    """View → To Do."""

    def __init__(self, main):
        super().__init__(main, nbmod.TODO)


# ==========================================================================
# Snapshots (Josh, 24 October): the notebook's tab and View → Snapshots
# ==========================================================================
# A snapshot is taken by the camera under the working window. The list has no resolving: a snapshot
# is restored (double-click), renamed, pinned, linked to a hypothesis or deleted. Every change is one
# undo step (Document.change_snapshots). Deleting never breaks a hypothesis: its link keeps a copy.

def _setup(snap) -> str:
    """The Setup column: how the view read when taken, left blank while the name is still that."""
    return "" if snap.about == snap.name else snap.about


def snapshot_icon(size: int = 18):
    return icon("snapshots", size, theme.colour("pitch").name())


class SnapshotActions:
    """What the notebook's Snapshots tab and View → Snapshots share; current() gives (session, snapshot)."""

    def _main(self):
        raise NotImplementedError

    def restore(self):
        cur = self.current()
        if cur is not None:
            self._main().restore_snapshot(cur[1].view)

    def rename(self):
        cur = self.current()
        if cur is None:
            return
        snap = cur[1]
        text = ask_text(self, "Rename snapshot", f"Snapshot (taken {cur[0].date}"
                        f"{' ' + snap.time if snap.time else ''}):", snap.name, one_line=True)
        if text and text.strip() and text.strip() != snap.name:
            ident, new = snap.id, text.strip()

            def change():
                hit = self._main().doc.notebook.snapshot(ident)
                if hit is not None:
                    hit[1].name = new
            self._main().doc.change_snapshots("Rename snapshot", change)
            self._after(ident)

    def toggle_pin(self):
        cur = self.current()
        if cur is None:
            return
        ident = cur[1].id
        label = "Unpin snapshot" if cur[1].pinned else "Pin snapshot"   # (Undo said Pin either way)

        def change():
            hit = self._main().doc.notebook.snapshot(ident)
            if hit is not None:
                hit[1].pinned = not hit[1].pinned
        self._main().doc.change_snapshots(label, change)
        self._after(ident)

    def delete(self):
        cur = self.current()
        if cur is None:
            return
        from .. import hypotheses as hy
        snap = cur[1]
        book = self._main().doc.notebook
        citing = [h.label for h in book.hypotheses for ln in h.links
                  if ln.kind == hy.SNAPSHOT and ln.target == snap.id]
        msg = f"Delete this snapshot?\n\n{snap.name}"
        if citing:
            msg += (f"\n\nIt is cited by {', '.join(dict.fromkeys(citing))}. Those links keep their own "
                    "copy, so they still restore the view (shown grey: deleted from the list).")
        if not _w.ask(self, "Delete snapshot", msg, "Delete snapshot"):
            return
        ident = snap.id

        def change():
            hit = book.snapshot(ident)
            if hit is not None:
                nbmod.delete_snapshot(book, hit[1])
        self._main().doc.change_snapshots("Delete snapshot", change)
        self._after(None)

    def link_to_hypothesis(self):
        cur = self.current()
        if cur is not None:
            self._main().link_listed_snapshot(cur[1], self)
            self._after(cur[1].id)

    def _after(self, ident):
        """Fill again, the snapshot (found by id: undo puts back copies) selected."""
        self.fill(ident)

    def _menu_items(self, cur):
        on = cur is not None
        snap = cur[1] if on else None
        return [("Restore the view", icon("camera", 16, theme.colour("pitch").name()), self.restore, on),
                ("Rename…", icon("edit", 16), self.rename, on),
                ("Unpin" if snap is not None and snap.pinned else "Pin to the top", pin_icon(),
                 self.toggle_pin, on),
                ("Link to hypothesis…", _cogitate_icon(), self.link_to_hypothesis, on),
                ("Delete snapshot", icon("delete", 16), self.delete, on)]

    def _show_menu(self, tree, pos, extra=()):
        it = tree.itemAt(pos)
        if it is not None:
            tree.setCurrentItem(it)
        cur = self.current()
        m = QMenu(tree)
        for text, ic, fn, enabled in list(self._menu_items(cur)) + list(extra):
            a = m.addAction(ic, text) if ic is not None else m.addAction(text)
            a.setEnabled(enabled)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(tree.viewport().mapToGlobal(pos))

    @staticmethod
    def _item(cols, snap, session):
        it = QTreeWidgetItem(cols)
        it.setData(0, Qt.UserRole, (session, snap))
        it.setToolTip(0, f"{snap.name}\n{snap.about}\nDouble-click to restore the view")
        return it


class SnapshotsPanel(QWidget, SnapshotActions):
    """The notebook's Snapshots tab: the day's snapshots, newest first."""

    def __init__(self, dlg: "NotebookDialog"):
        QWidget.__init__(self)
        self.dlg = dlg
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()

        def button(ic, tip, fn):
            b = QToolButton()
            b.setIcon(ic)
            b.setIconSize(QSize(30, 30))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda *_: fn())
            row.addWidget(b)
            return b
        self.restore_btn = button(icon("camera", 30, theme.colour("pitch").name()),
                                  "Restore the view of the selected snapshot (also: double-click)", self.restore)
        self.rename_btn = button(icon("edit", 30), "Rename the selected snapshot", self.rename)
        self.pin_btn = button(pin_icon(30), "Pin the selected snapshot to the top of the list", self.toggle_pin)
        self.link_btn = button(_cogitate_icon(30), "Link the selected snapshot to a hypothesis",
                               self.link_to_hypothesis)
        self.delete_btn = button(icon("delete", 30), "Delete the selected snapshot (hypotheses citing it "
                                 "keep their copy)", self.delete)
        row.addStretch(1)
        lay.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Snapshot", "Time", "Setup"])
        self.tree.setRootIsDecorated(False)
        wrapping(self.tree, lambda: dlg.search.text())
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        self.tree.itemDoubleClicked.connect(lambda *_: self.restore())
        self.tree.currentItemChanged.connect(lambda *_: self.buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda pos: self._show_menu(self.tree, pos))
        lay.addWidget(self.tree, 1)

    def _main(self):
        return self.dlg.main

    def current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def fill(self, ident: str | None = None):
        self.tree.clear()
        s = self.dlg.session
        if s is None:
            return
        snaps = [x for _, x in sorted(enumerate(s.snapshots), key=lambda p: (p[1].time, p[0]), reverse=True)]
        for snap in [x for x in snaps if x.pinned] + [x for x in snaps if not x.pinned]:
            it = self._item([snap.name, snap.time, _setup(snap)], snap, s)
            if snap.pinned:
                it.setIcon(0, pin_icon())
            self.tree.addTopLevelItem(it)
            if snap.id == ident:
                self.tree.setCurrentItem(it)
        self.dlg.tabs.setTabText(SNAPSHOTS_TAB, f"Snapshots ({len(snaps)})" if snaps else "Snapshots")
        self.buttons()

    def buttons(self):
        on = self.current() is not None
        for b in (self.restore_btn, self.rename_btn, self.pin_btn, self.link_btn, self.delete_btn):
            b.setEnabled(on)


class SnapshotsDialog(QDialog, SnapshotActions):
    """View → Snapshots (Ctrl+Shift+P): every snapshot, newest first, the pinned ones on top; a window
    beside the main one, not modal, as View → Questions and View → To Do."""

    def __init__(self, main):
        QDialog.__init__(self, main)
        self.main = main
        self.setWindowTitle("Snapshots")
        self.setWindowIcon(snapshot_icon(32))
        self.setModal(False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.resize(980, 620)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the snapshots")
        _power_placeholder(self.search)          # ⚡ power search (idea 86)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self.fill())
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Session", "Snapshot", "Time", "Setup"])
        self.tree.setRootIsDecorated(False)
        wrapping(self.tree, lambda: self.search.text())
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        h = self.tree.header()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setStretchLastSection(False)
        self.tree.itemDoubleClicked.connect(lambda *_: self.restore())
        self.tree.currentItemChanged.connect(lambda *_: self._buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.tree, pos, [("Open in notebook", icon("notebook", 16,
                                        theme.accent().name()), self.open_day, self.current() is not None)]))
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.restore_btn = QPushButton(icon("camera", 18, theme.colour("pitch").name()), "Restore")
        self.restore_btn.setToolTip("Restore the selected snapshot's view in the main window (also: double-click)")
        self.restore_btn.clicked.connect(lambda *_: self.restore())
        self.rename_btn = QPushButton(icon("edit", 18), "")
        self.rename_btn.setToolTip("Rename the selected snapshot")
        self.rename_btn.clicked.connect(lambda *_: self.rename())
        self.pin_btn = QPushButton(pin_icon(18), "")
        self.pin_btn.setToolTip("Pin the selected snapshot to the top of the list")
        self.pin_btn.clicked.connect(lambda *_: self.toggle_pin())
        self.link_btn = QPushButton(_cogitate_icon(18), "")
        self.link_btn.setToolTip("Link the selected snapshot to a hypothesis")
        self.link_btn.clicked.connect(lambda *_: self.link_to_hypothesis())
        self.delete_btn = QPushButton(icon("delete", 18), "")
        self.delete_btn.setToolTip("Delete the selected snapshot (hypotheses citing it keep their copy)")
        self.delete_btn.clicked.connect(lambda *_: self.delete())
        self.open_btn = QPushButton(icon("notebook", 18, theme.accent().name()), "Open in notebook")
        self.open_btn.clicked.connect(lambda *_: self.open_day())
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {theme.muted()};")
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for w in (self.restore_btn, self.rename_btn, self.pin_btn, self.link_btn, self.delete_btn, self.open_btn):
            row.addWidget(w)
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.fill()

    def _main(self):
        return self.main

    def current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def refresh(self):
        cur = self.current()
        self.fill(cur[1].id if cur is not None else None)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.refresh()

    def fill(self, ident: str | None = None):
        text = self.search.text()
        self.tree.clear()
        every = self.main.doc.notebook.all_snapshots()
        shown = 0
        for s, snap in every:
            if not search.matches(text, (snap.name, snap.about, s.date)):   # idea 86
                continue
            it = self._item([s.date, snap.name, snap.time, _setup(snap)], snap, s)
            if snap.pinned:
                it.setIcon(1, pin_icon())
            self.tree.addTopLevelItem(it)
            shown += 1
            if snap.id == ident:
                self.tree.setCurrentItem(it)
        self.count.setText(f"{shown} shown of {len(every)}")
        self._buttons()
        QTimer.singleShot(0, self.tree.doItemsLayout)

    def _buttons(self):
        cur = self.current()
        for b in (self.restore_btn, self.rename_btn, self.pin_btn, self.link_btn, self.delete_btn, self.open_btn):
            b.setEnabled(cur is not None)
        self.pin_btn.setToolTip("Unpin the selected snapshot" if cur is not None and cur[1].pinned
                                else "Pin the selected snapshot to the top of the list")

    def open_day(self):
        cur = self.current()
        if cur is None:
            return
        self.main.open_notebook(cur[0].date)
        nb = getattr(self.main, "notebook_dialog", None)
        if nb is not None:
            nb.tabs.setCurrentIndex(SNAPSHOTS_TAB)
            nb.s_panel.fill(cur[1].id)
