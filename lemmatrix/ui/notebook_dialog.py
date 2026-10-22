# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The notebook window (View → Notebook) and the lists of all questions and to dos (View →
Questions, View → To Do).

The notebook is one page a day: the session's date, who was there and where, notes
(in Charis, so IPA can be typed), the comments written that day with links to
their lemmas and tokens, the recordings made that day, and the questions and to dos.
The window stays open beside the main one; changes are saved with the database
(or by Write to notebook).
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QTextCharFormat
from PySide6.QtWidgets import (QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QMenu, QStyledItemDelegate, QTabWidget, QTextEdit, QToolButton, QToolTip,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import matrix as mx, notebook as nbmod
from ..model import today
from . import chiprow as chips
from . import searchmark, theme
from .icons import icon
from .widgets import ipa_font, meaning

NEWEST, OLDEST = "newest", "oldest"
QUESTIONS_TAB, TODO_TAB, HYPOTHESES_TAB, COMMENTS_TAB, RECORDINGS_TAB, TEXTS_TAB = range(6)   # the notebook's tabs
KIND_ICON = {nbmod.QUESTION: "push-question", nbmod.TODO: "push-todo"}        # the green ?, the orange flag


def _cogitate_icon(size: int = 16):
    from .cogitate import cogitate_icon
    return cogitate_icon(size)


def kind_icon(kind: str, size: int = 18):
    return icon(KIND_ICON[kind], size)


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
            fm = QFontMetrics(index.data(Qt.FontRole) or option.font)
            h = fm.boundingRect(QRect(0, 0, width, 100000), Qt.TextWordWrap, text).height() + 6
            size.setHeight(max(size.height(), h))
        return size


def wrapping(view, query=None):
    view.setWordWrap(True)
    view.setTextElideMode(Qt.ElideNone)
    view.setItemDelegate(WrapDelegate(view, query))


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


def ask_text(parent, title: str, label: str, text: str = "") -> str | None:
    """A few lines of text (Charis, for IPA); None if cancelled."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(520, 220)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(label))
    ed = QPlainTextEdit(text)
    ed.setFont(ipa_font(parent.window().main.prefs.ipa_size if hasattr(parent.window(), "main") else 13))
    lay.addWidget(ed, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    ed.setFocus()
    if not dlg.exec():
        return None
    return ed.toPlainText().strip()


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
        for section, label in ((nbmod.ELICIT_HISTORY, "Write ELICIT HISTORY"),
                               (nbmod.COGITATE_HISTORY, "Write COGITATE HISTORY")):
            box = QCheckBox(label)
            box.setToolTip(f"Write a line under {nbmod.HISTORY_HEADINGS[section]} in the day's notes for each "
                           f"{'ɛλicit request made or received' if section == nbmod.ELICIT_HISTORY else 'change to a hypothesis'}"
                           ". Switching it off leaves what is written; nothing is written later for the days "
                           "it was off. The same as Edit → Settings → General (this database).")
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
        self.q_delete, self.q_edit, self.q_resolve = self.q_panel.delete_btn, self.q_panel.edit_btn, \
            self.q_panel.resolve_btn
        self.tabs.addTab(self.q_panel, "Questions")       # first (Josh, 18 October), then To Do, Comments…
        self.tabs.addTab(self.t_panel, "To Do")
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
        for view in (self.comments, self.questions, self.todos):      # their marks
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
        text = self.search.text().strip()
        sels = []
        if text:
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(theme.colour("selected_token")))
            doc = self.notes.document()
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
        if QMessageBox.question(self, "Delete note", f"Delete the note for {s.date}" +
                                (f", with {', '.join(what)}" if what else "") +
                                "?\n\nThe lemmas, tokens and their comments stay in the database.") \
                != QMessageBox.Yes:
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
        elif QMessageBox.question(self, "Notebook", f"There are no notes for {date}. Add a note for "
                                  "that day?") == QMessageBox.Yes:
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
        if self.session is None:
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
    def _current_question(self) -> nbmod.Question | None:
        return self.q_panel.current()

    def _question_buttons(self):
        for panel in (self.q_panel, self.t_panel):
            panel.buttons()

    def add_question(self):
        self.q_panel.add()

    def edit_question(self):
        self.q_panel.edit()

    def delete_question(self):
        self.q_panel.delete()

    def toggle_resolved(self):
        self.q_panel.toggle()


class ItemsPanel(QWidget):
    """A notebook tab of questions or to dos (Josh, 21 October: To Do is the same as Questions):
    Add, Delete, Edit, Resolve and Convert at the top, then the list; right-click for the same."""

    def __init__(self, dlg: "NotebookDialog", kind: str):
        super().__init__()
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
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self.buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        ql.addWidget(self.tree, 1)

    @property
    def session(self):
        return self.dlg.session

    def _changed(self):
        self.dlg._changed()

    def fill(self, select: nbmod.Question | None = None):
        self.tree.clear()
        s = self.session
        if s is None:
            return
        muted = QBrush(QColor(theme.muted()))
        lst = nbmod.items(s, self.kind)
        for q in lst:
            it = QTreeWidgetItem([q.text, q.about, q.status, q.dated, q.resolved])
            it.setData(0, Qt.UserRole, q)
            it.setToolTip(0, q.text)
            link_look(it, 1, q)
            if not q.is_open:
                for c in (0, 2, 3, 4):
                    it.setForeground(c, muted)
            self.tree.addTopLevelItem(it)
            if q is select:
                self.tree.setCurrentItem(it)
        open_ = sum(1 for q in lst if q.is_open)
        title = "Questions" if self.kind == nbmod.QUESTION else "To Do"
        self.dlg.tabs.setTabText(QUESTIONS_TAB if self.kind == nbmod.QUESTION else TODO_TAB,
                                 f"{title} ({open_} open)" if lst else title)
        self.buttons()
        QTimer.singleShot(0, self.tree.doItemsLayout)

    def current(self) -> nbmod.Question | None:
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None and self.session is not None else None

    def buttons(self):
        q = self.current()
        for b in (self.delete_btn, self.edit_btn, self.resolve_btn, self.convert_btn):
            b.setEnabled(q is not None)
        one = nbmod.name(self.kind, title=False)
        self.resolve_btn.setToolTip(f"Mark the selected {one} as open again" if q and not q.is_open
                                    else f"Resolve the selected {one}")

    def _double_clicked(self, item, column):
        q = item.data(0, Qt.UserRole)
        if column == 1 and q.link is not None:          # the token's link: go to it
            follow_link(self.dlg, self.dlg.main, q.link)
        else:
            self.edit()

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is not None:
            self.tree.setCurrentItem(it)
        q = self.current()
        one = nbmod.name(self.kind, title=False)
        m = QMenu(self.tree)
        on = q is not None
        for text, ic, fn, enabled in (
                (f"Add a {one}…", icon("add", 16), self.add, self.session is not None),
                (f"Edit {one}…", icon("edit", 16), self.edit, on),
                ("Mark as open" if on and not q.is_open else "Resolve", icon("resolve", 16), self.toggle, on),
                (convert_label(self.kind), kind_icon(nbmod.other(self.kind), 16), self.convert, on),
                ("Go to token", None, lambda: follow_link(self.dlg, self.dlg.main, q.link),
                 on and q.link is not None),
                ("Link to hypothesis…", _cogitate_icon(), self.link_to_hypothesis, on),
                (f"Delete {one}", icon("delete", 16), self.delete, on)):
            a = m.addAction(ic, text) if ic is not None else m.addAction(text)
            a.setEnabled(enabled)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def link_to_hypothesis(self):
        """Link to hypothesis…: this question or To Do (it gets an id, kept after)."""
        from .. import hypotheses as hy
        q = self.current()
        if q is None or self.session is None:
            return
        had = q.id
        link = hy.question_link(self.session, q)
        if not had:
            self.dlg.main.doc.notebook_changed()     # the id is written with the notebook
        self.dlg.main.link_to_hypothesis(link, self.dlg)
        self.dlg.reload()

    def add(self):
        if self.session is None:
            return
        one = nbmod.name(self.kind)
        text = ask_text(self, f"Add {one if self.kind == nbmod.TODO else one.lower()}", f"{one}:")
        if text:
            q = nbmod.Question(text, today(), kind=self.kind)
            nbmod.items(self.session, self.kind).append(q)
            self._changed()
            self.fill(q)

    def edit(self):
        q = self.current()
        if q is None:
            return
        one = nbmod.name(self.kind)
        text = ask_text(self, f"Edit {one if self.kind == nbmod.TODO else one.lower()}", f"{one}:", q.text)
        if text and text != q.text:
            q.text, q.edited = text, today()
            self._changed()
            self.fill(q)

    def delete(self):
        q = self.current()
        if q is None:
            return
        one = nbmod.name(self.kind, title=False)
        if QMessageBox.question(self, f"Delete {one}", f"Delete this {one}?\n\n{q.text}") != QMessageBox.Yes:
            return
        nbmod.items(self.session, self.kind).remove(q)
        self._changed()
        self.fill()

    def toggle(self):
        q = self.current()
        if q is None:
            return
        q.resolved = "" if q.resolved else today()
        self._changed()
        self.fill(q)

    def convert(self):
        """Convert to To Do / Convert to question: it moves to the other tab, dates and link kept."""
        q = self.current()
        if q is None:
            return
        nbmod.convert(self.session, q)
        self._changed()
        self.dlg._fill_days(self.session.date)        # the day's tooltip counts
        self.dlg._fill_questions()
        QToolTip.showText(self.tree.viewport().mapToGlobal(self.tree.viewport().rect().topLeft()),
                          f"Moved to {'To Do' if q.is_todo else 'Questions'}", self.tree)


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


class ItemsDialog(QDialog):
    """Every question (or to do) in the notebook, newest day first."""

    def __init__(self, main, kind: str = nbmod.QUESTION):
        super().__init__(main)
        self.main, self.kind = main, kind
        one, many = nbmod.name(kind, title=False), nbmod.name(kind, True, title=False)
        self.setWindowTitle("Questions" if kind == nbmod.QUESTION else "To Do")
        self.setWindowIcon(kind_icon(kind, 32))
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
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self._buttons())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
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
        self.open_btn = QPushButton(icon("notebook", 18, theme.accent().name()), "Open in notebook")
        self.open_btn.clicked.connect(lambda *_: self.open_day())
        self.token_btn = QPushButton("Go to token")
        self.token_btn.setToolTip(f"Show the token the {one} was pushed from (also: double-click its link)")
        self.token_btn.clicked.connect(lambda *_: self.go_to_token())
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {theme.muted()};")
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for w in (self.resolve_btn, self.edit_btn, self.convert_btn, self.open_btn, self.token_btn):
            row.addWidget(w)
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def _all(self):
        return self.main.doc.notebook.all_items(self.kind)

    def _fill(self, select=None):
        which = self.show_which.currentData()
        text = self.search.text().strip().lower()
        self.tree.clear()
        muted = QBrush(QColor(theme.muted()))
        shown = 0
        for s, q in self._all():
            if (which == OPEN and not q.is_open) or (which == RESOLVED and q.is_open):
                continue
            if text and text not in q.text.lower() and text not in s.date:
                continue
            it = QTreeWidgetItem([s.date, q.text, q.about, q.status, q.dated, q.resolved])
            it.setData(0, Qt.UserRole, (s, q))
            it.setToolTip(1, q.text)
            link_look(it, 2, q)
            if not q.is_open:
                for c in (0, 1, 3, 4, 5):
                    it.setForeground(c, muted)
            self.tree.addTopLevelItem(it)
            shown += 1
            if q is select:
                self.tree.setCurrentItem(it)
        every = self._all()
        open_ = sum(1 for _, q in every if q.is_open)
        self.count.setText(f"{shown} shown · {open_} open of {len(every)}")
        self._buttons()
        QTimer.singleShot(0, self.tree.doItemsLayout)      # wrapped items get their height

    def _current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def _buttons(self):
        cur = self._current()
        for b in (self.resolve_btn, self.edit_btn, self.convert_btn, self.open_btn):
            b.setEnabled(cur is not None)
        self.resolve_btn.setText("Mark as open" if cur and not cur[1].is_open else "Resolve")
        self.token_btn.setEnabled(cur is not None and cur[1].link is not None)

    def _double_clicked(self, item, column):
        if column == 2 and item.data(0, Qt.UserRole)[1].link is not None:
            self.go_to_token()
        else:
            self.edit()

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is not None:
            self.tree.setCurrentItem(it)
        cur = self._current()
        if cur is None:
            return
        q = cur[1]
        m = QMenu(self.tree)
        for text, ic, fn, enabled in (
                (f"Edit {nbmod.name(self.kind, title=False)}…", icon("edit", 16), self.edit, True),
                ("Mark as open" if not q.is_open else "Resolve", icon("resolve", 16), self.toggle, True),
                (convert_label(self.kind), kind_icon(nbmod.other(self.kind), 16), self.convert, True),
                ("Open in notebook", icon("notebook", 16, theme.accent().name()), self.open_day, True),
                ("Go to token", None, self.go_to_token, q.link is not None)):
            a = m.addAction(ic, text) if ic is not None else m.addAction(text)
            a.setEnabled(enabled)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def go_to_token(self):
        cur = self._current()
        if cur is not None and cur[1].link is not None:
            follow_link(self, self.main, cur[1].link)

    def toggle(self):
        cur = self._current()
        if cur is None:
            return
        q = cur[1]
        q.resolved = "" if q.resolved else today()
        self.main.doc.notebook_changed()
        self._fill(q)

    def edit(self):
        cur = self._current()
        if cur is None:
            return
        q = cur[1]
        one = nbmod.name(self.kind)
        text = ask_text(self, f"Edit {one if self.kind == nbmod.TODO else one.lower()}",
                        f"{one} (from {cur[0].date}):", q.text)
        if text and text != q.text:
            q.text, q.edited = text, today()
            self.main.doc.notebook_changed()
            self._fill(q)

    def convert(self):
        """Convert to To Do / Convert to question: it leaves this list for the other one."""
        cur = self._current()
        if cur is None:
            return
        s, q = cur
        nbmod.convert(s, q)
        self.main.doc.notebook_changed()
        self._fill()
        self.count.setText(self.count.text() + f" · moved to {'To Do' if q.is_todo else 'Questions'}")
        if getattr(self.main, "notebook_dialog", None) is not None:
            self.main.notebook_dialog.reload()

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
