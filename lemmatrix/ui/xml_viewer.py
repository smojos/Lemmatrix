# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The XML viewer (IDEAS.md idea 23, built 21 October 2026): the database file, read-only.

Opened from Josh's χμλ button, between ɛλicit and Texts and utterances (or View → XML viewer). It
shows the database as Save would write it now, unsaved changes included, with line numbers, the
tags coloured, and a search bar that marks every match (diacritics and capitals ignored, as in the
other search bars) with Previous and Next. Opened with a token or lemma selected, it goes to that
place in the XML; otherwise to the beginning. Nothing can be edited here.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QPainter, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .. import storage, xmlview
from . import theme

MAX_MARKS = 5000                  # marks drawn at most (every match is still counted and reachable)


def _mono_font() -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    for name in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Menlo"):
        if name in QFontDatabase.families():
            f = QFont(name)
            break
    f.setStyleHint(QFont.Monospace)
    f.setPointSizeF(max(f.pointSizeF(), 10.0))
    return f


class _Highlighter(QSyntaxHighlighter):
    """Element names in the theme colour, attribute names muted, attribute values in ink."""

    TAG = re.compile(r"</?([\w:.-]+)|/?>|<\?xml|\?>")
    ATTR = re.compile(r'([\w:.-]+)(=)("[^"]*")')

    def __init__(self, doc):
        super().__init__(doc)
        self.restyle()

    def restyle(self):
        def fmt(c: QColor, bold=False):
            f = QTextCharFormat()
            f.setForeground(c)
            if bold:
                f.setFontWeight(QFont.DemiBold)
            return f
        self.f_tag = fmt(theme.colour("pitch"), bold=True)
        self.f_name = fmt(QColor(theme.muted()))
        self.f_value = fmt(QColor("#c8c8c8") if theme.dark() else QColor("#5a5a5a"))
        self.rehighlight()

    def highlightBlock(self, text: str):
        if "<" not in text:
            return
        for m in self.ATTR.finditer(text):
            self.setFormat(m.start(1), len(m.group(1)), self.f_name)
            self.setFormat(m.start(3), len(m.group(3)), self.f_value)
        for m in self.TAG.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.f_tag)


class _LineNumbers(QWidget):
    def __init__(self, editor: "XmlText"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_numbers(self, event)


class XmlText(QPlainTextEdit):
    """Read-only text with line numbers at the left."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(_mono_font())
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.numbers = _LineNumbers(self)
        self.blockCountChanged.connect(lambda *_: self.setViewportMargins(self.number_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_numbers)
        self.setViewportMargins(self.number_width(), 0, 0, 0)

    def number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_numbers(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.numbers.setGeometry(QRect(cr.left(), cr.top(), self.number_width(), cr.height()))

    def paint_numbers(self, widget, event):
        p = QPainter(widget)
        p.fillRect(event.rect(), self.palette().alternateBase())
        p.setPen(QColor(theme.muted()))
        p.setFont(self.font())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        h = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                p.drawText(0, top, widget.width() - 6, h, Qt.AlignRight, str(block.blockNumber() + 1))
            top += round(self.blockBoundingRect(block).height())
            block = block.next()
        p.end()


class XmlViewerWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.setWindowTitle("XML viewer")
        from .winstate import fit_to_screen, keep
        fit_to_screen(self, 900, 760)
        self.shown_text = ""
        self.folded: xmlview.FoldedText | None = None
        self.matches: list[tuple[int, int]] = []
        self.current = -1
        self.target_line: int | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.title = main._heading("XML viewer")
        head.addWidget(self.title)
        self.where = QLabel()                    # the file and "read-only"
        head.addWidget(self.where, 0, Qt.AlignBottom)
        head.addStretch(1)
        lay.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search the XML (diacritics and capitals ignored)")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._enter)
        self._typing = QTimer(self)
        self._typing.setSingleShot(True)
        self._typing.setInterval(200)
        self._typing.timeout.connect(self.run_search)
        self.search.textChanged.connect(lambda *_: self._typing.start())
        bar.addWidget(self.search, 1)
        self.prev_btn = QToolButton()
        self.prev_btn.setArrowType(Qt.UpArrow)
        self.prev_btn.setToolTip("Previous match (Shift+Enter)")
        self.prev_btn.clicked.connect(lambda *_: self.prev_match())
        self.next_btn = QToolButton()
        self.next_btn.setArrowType(Qt.DownArrow)
        self.next_btn.setToolTip("Next match (Enter)")
        self.next_btn.clicked.connect(lambda *_: self.next_match())
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.next_btn)
        self.count = QLabel()
        self.count.setMinimumWidth(90)
        bar.addWidget(self.count)
        lay.addLayout(bar)

        self.text = XmlText()
        self.highlighter = _Highlighter(self.text.document())
        lay.addWidget(self.text, 1)
        keep(self, main.prefs, "window/xml")
        self._restyle()

    # ---- content ------------------------------------------------------
    def refresh(self, keep_place: bool = True):
        """Show the database as it is now (what Save would write)."""
        text = storage.to_string(self.doc.db)
        from pathlib import Path
        name = Path(self.doc.db.path).name if self.doc.db.path else "not saved yet"
        dirty = self.doc.dirty
        self.where.setText(f"{name} · read-only" + (" · unsaved changes included" if dirty else ""))
        if text == self.shown_text:
            return False
        bar = self.text.verticalScrollBar()
        hbar = self.text.horizontalScrollBar()
        v, h = bar.value(), hbar.value()
        self.shown_text = text
        self.folded = None
        self.target_line = None                  # its line may have moved
        self.text.setPlainText(text)
        if keep_place:
            bar.setValue(v)
            hbar.setValue(h)
        if self.search.text().strip():
            self.run_search(move=False)
        return True

    def go_to(self, selected):
        """Go to the place of `selected` ("token" or "entry", id) in the XML, or the beginning."""
        line = None
        if selected is not None:
            line = xmlview.line_of(self.shown_text, *selected)
        self.target_line = line
        block = self.text.document().findBlockByNumber(line or 0)
        cur = QTextCursor(block)
        self.text.setTextCursor(cur)
        bar = self.text.verticalScrollBar()
        bar.setValue(max(0, (line or 0) - 2) if line else 0)
        self.text.horizontalScrollBar().setValue(0)
        self._mark()

    # ---- search -------------------------------------------------------
    def run_search(self, move: bool = True):
        q = self.search.text().strip()
        if not q:
            self.matches, self.current = [], -1
        else:
            if self.folded is None or self.folded.text != self.shown_text:
                self.folded = xmlview.FoldedText(self.shown_text)
            self.matches = self.folded.find_all(q)
            if move:
                pos = self.text.textCursor().selectionStart() if self.current < 0 else \
                    self.text.textCursor().position()
                self.current = next((i for i, (s, _) in enumerate(self.matches) if s >= pos),
                                    0) if self.matches else -1
            elif self.current >= len(self.matches):
                self.current = len(self.matches) - 1
        self._show_current(move)

    def _enter(self):
        from PySide6.QtWidgets import QApplication
        if self._typing.isActive():              # Enter before the search ran: run it first
            self._typing.stop()
            self.run_search()
            return
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            self.prev_match()
        else:
            self.next_match()

    def next_match(self):
        if not self.matches:
            return self.run_search()
        self.current = (self.current + 1) % len(self.matches)
        self._show_current(True)

    def prev_match(self):
        if not self.matches:
            return
        self.current = (self.current - 1) % len(self.matches)
        self._show_current(True)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ShiftModifier:
            self.prev_match()
            return
        if event.key() == Qt.Key_F3:
            (self.prev_match if event.modifiers() & Qt.ShiftModifier else self.next_match)()
            return
        if event.key() == Qt.Key_F and event.modifiers() & Qt.ControlModifier:
            self.search.setFocus()
            self.search.selectAll()
            return
        super().keyPressEvent(event)

    def _show_current(self, move: bool):
        q = self.search.text().strip()
        if not q:
            self.count.setText("")
        elif not self.matches:
            self.count.setText("no matches")
        elif self.current < 0:
            n = len(self.matches)
            self.count.setText(f"{n} match{'es' if n != 1 else ''}")
        else:
            self.count.setText(f"{self.current + 1} / {len(self.matches)}")
        if move and 0 <= self.current < len(self.matches):
            s, e = self.matches[self.current]
            cur = self.text.textCursor()
            cur.setPosition(s)
            cur.setPosition(e, QTextCursor.KeepAnchor)
            self.text.setTextCursor(cur)
            self.text.centerCursor()
        self._mark()

    def _mark(self):
        """The marks: the target line in a light wash, every match yellow, the current one stronger."""
        sels = []
        if self.target_line is not None:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(theme.wash(0.85 if not theme.dark() else 0.7))   # a light wash
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = QTextCursor(self.text.document().findBlockByNumber(self.target_line))
            sels.append(sel)
        doc = self.text.document()
        yellow = QColor("#fff176") if not theme.dark() else QColor("#7a6a00")
        strong = QColor("#ffb300") if not theme.dark() else QColor("#b58900")
        for i, (s, e) in enumerate(self.matches[:MAX_MARKS]):
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(strong if i == self.current else yellow)
            c = QTextCursor(doc)
            c.setPosition(s)
            c.setPosition(e, QTextCursor.KeepAnchor)
            sel.cursor = c
            sels.append(sel)
        if self.current >= MAX_MARKS and self.current < len(self.matches):
            s, e = self.matches[self.current]
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(strong)
            c = QTextCursor(doc)
            c.setPosition(s)
            c.setPosition(e, QTextCursor.KeepAnchor)
            sel.cursor = c
            sels.append(sel)
        self.text.setExtraSelections(sels)

    # ---- style and life -----------------------------------------------
    def _restyle(self):
        self.title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        self.where.setStyleSheet(f"color: {theme.muted()};")
        self.count.setStyleSheet(f"color: {theme.muted()};")
        theme.as_data(self.text)
        self.highlighter.restyle()
        self._mark()
        self.text.numbers.update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange and self.isActiveWindow() and self.isVisible():
            self.refresh()                       # back from the main window: any changes made there
