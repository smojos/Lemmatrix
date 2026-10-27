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
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QPainter, QTextCharFormat,
                           QTextCursor, QTextFormat, QTextLayout)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .. import storage, xmlview
from . import theme
from .searchmark import power_placeholder as _power_placeholder

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


class _Highlighter:
    """Element names in the theme colour, attribute names muted, attribute values in ink.

    Lines are coloured as they come into view (style_visible, from the text's paintEvent), not all
    at once: a QSyntaxHighlighter coloured all ~600,000 lines of a 58,000-token database before
    the viewer could show anything (several seconds; 25 October)."""

    TAG = re.compile(r"</?([\w:.-]+)|/?>|<\?xml|\?>")
    ATTR = re.compile(r'([\w:.-]+)(=)("[^"]*")')

    def __init__(self, edit: "XmlText"):
        self.edit = edit
        self.done: set[int] = set()               # block numbers coloured since the text was set
        edit.highlighter = self
        self.restyle()

    def reset(self):
        self.done = set()

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

    def rehighlight(self):
        self.reset()
        self.edit.viewport().update()

    def ranges(self, text: str) -> list:
        """The colours of one line, as the layout takes them (later ranges win)."""
        if "<" not in text:
            return []
        out = []

        def add(start, length, f):
            r = QTextLayout.FormatRange()
            r.start, r.length, r.format = start, length, f
            out.append(r)
        for m in self.ATTR.finditer(text):
            add(m.start(1), len(m.group(1)), self.f_name)
            add(m.start(3), len(m.group(3)), self.f_value)
        for m in self.TAG.finditer(text):
            add(m.start(), m.end() - m.start(), self.f_tag)
        return out

    def style_visible(self):
        """Colour the lines on screen that aren't coloured yet."""
        e = self.edit
        block = e.firstVisibleBlock()
        top = e.blockBoundingGeometry(block).translated(e.contentOffset()).top()
        height = e.viewport().height()
        doc = e.document()
        while block.isValid() and top <= height:
            n = block.blockNumber()
            if block.isVisible() and n not in self.done:
                self.done.add(n)
                block.layout().setFormats(self.ranges(block.text()))
                doc.markContentsDirty(block.position(), block.length())
            top += e.blockBoundingRect(block).height()
            block = block.next()


class _LineNumbers(QWidget):
    def __init__(self, editor: "XmlText"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_numbers(self, event)

    def mousePressEvent(self, event):
        """A click on a ⊞ / ⊟ in the margin collapses or expands that element (Josh, 23 October)."""
        if event.button() == Qt.LeftButton and event.position().x() <= self.editor.FOLD_W + 2:
            line = self.editor.line_at(round(event.position().y()))
            if line is not None and line in self.editor.folds:
                self.editor.toggle(line)
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Right-click the margin: Collapse all, Expand all."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Collapse all").triggered.connect(lambda *_: self.editor.collapse_all(True))
        m.addAction("Expand all").triggered.connect(lambda *_: self.editor.collapse_all(False))
        m.exec(event.globalPos())

    def mouseMoveEvent(self, event):
        line = self.editor.line_at(round(event.position().y()))
        on = event.position().x() <= self.editor.FOLD_W + 2 and line in self.editor.folds
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        self.setToolTip(("Expand" if line in self.editor.collapsed else "Collapse")
                        + " (right-click: Collapse all, Expand all)" if on else "")


class XmlText(QPlainTextEdit):
    """Read-only text with line numbers at the left, and a ⊟ beside every element that spans
    more than one line: a click collapses it to its first line (⊞ expands it again)."""

    FOLD_W = 14                       # the room for the fold markers, left of the numbers

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(_mono_font())
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.numbers = _LineNumbers(self)
        self.numbers.setMouseTracking(True)
        self.folds: dict[int, int] = {}          # first line -> last line of each foldable element
        self.collapsed: set[int] = set()
        self.blockCountChanged.connect(lambda *_: self.setViewportMargins(self.number_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_numbers)
        self.setViewportMargins(self.number_width(), 0, 0, 0)

    def setPlainText(self, text: str):
        if getattr(self, "highlighter", None) is not None:
            self.highlighter.reset()              # new lines: coloured again as they come into view
        super().setPlainText(text)

    def paintEvent(self, event):
        if getattr(self, "highlighter", None) is not None:
            self.highlighter.style_visible()
        super().paintEvent(event)

    def number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self.FOLD_W + 14 + self.fontMetrics().horizontalAdvance("9") * digits

    # ---- folding (Josh, 23 October) ------------------------------------------------
    def set_folds(self, folds: dict[int, int], collapsed=()):
        """New text's foldable elements; collapsed: first lines to start collapsed."""
        self.folds = dict(folds)
        self.collapsed = {line for line in collapsed if line in self.folds}
        self._apply_folds()

    def line_at(self, y: int) -> int | None:
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid():
            if block.isVisible():
                h = round(self.blockBoundingRect(block).height())
                if top <= y < top + h:
                    return block.blockNumber()
                top += h
            block = block.next()
        return None

    def toggle(self, line: int):
        if line in self.collapsed:
            self.collapsed.discard(line)
        else:
            self.collapsed.add(line)
        self._apply_folds()

    def reveal(self, line: int):
        """Expand whatever hides `line` (a search match, the selected token)."""
        hiding = [a for a in self.collapsed if a < line <= self.folds[a]]
        if hiding:
            self.collapsed.difference_update(hiding)
            self._apply_folds()

    def collapse_all(self, collapse: bool = True):
        """Every element collapsed but the outermost (<database>), so its parts show one line each:
        the metadata, the settings, each entry; or every element expanded."""
        root = min(self.folds, default=None)
        self.collapsed = {a for a in self.folds if a != root} if collapse else set()
        self._apply_folds()

    def _apply_folds(self):
        doc = self.document()
        hidden = set()
        for a in self.collapsed:
            hidden.update(range(a + 1, self.folds[a] + 1))
        block = doc.firstBlock()
        while block.isValid():
            block.setVisible(block.blockNumber() not in hidden)
            block = block.next()
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        self.numbers.update()
        self.updateGeometry()

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
                n = block.blockNumber()
                p.setPen(QColor(theme.muted()))
                p.drawText(0, top, widget.width() - 6, h, Qt.AlignRight, str(n + 1))
                if n in self.folds:                # ⊟ expanded, ⊞ collapsed, in the theme colour
                    side = min(9, h - 4)
                    box = QRect(3, top + (h - side) // 2, side, side)
                    p.setPen(theme.colour("pitch"))
                    p.drawRect(box)
                    mid = box.center()
                    p.drawLine(box.left() + 2, mid.y(), box.right() - 2, mid.y())
                    if n in self.collapsed:
                        p.drawLine(mid.x(), box.top() + 2, mid.x(), box.bottom() - 2)
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
        _power_placeholder(self.search)          # ⚡ Power search (idea 86)
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
        self.highlighter = _Highlighter(self.text)
        lay.addWidget(self.text, 1)
        keep(self, main.prefs, "window/xml")
        self._restyle()

    # ---- content ------------------------------------------------------
    def refresh(self, keep_place: bool = True):
        """Show the database as it is now (what Save would write)."""
        import time
        self._refreshed = time.monotonic()
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
        old_lines = self.shown_text.split("\n")
        keep = [a for a in self.text.collapsed if a < len(old_lines)]
        self.shown_text = text
        self.folded = None
        self.target_line = None                  # its line may have moved
        self.text.setPlainText(text)
        lines = text.split("\n")                 # collapsed elements stay so where their line is the same
        self.text.set_folds(xmlview.fold_ranges(text),
                            [a for a in keep if a < len(lines) and lines[a] == old_lines[a]])
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
        if line is not None:
            self.text.reveal(line)
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
            from .. import search                  # one search for every bar (idea 86): every item
            found = set()                          # not left out; `--` means nothing here
            for item in search.parse(q).raw_items:
                found.update(self.folded.find_all(item))
            self.matches = sorted(found)
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
            self.text.reveal(self.shown_text.count("\n", 0, s))   # a match inside a collapsed element
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
        yellow = theme.search_mark()                 # one search yellow (Settings → Display)
        strong = theme.search_mark_strong()
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
            import time                          # back from the main window: any changes made there
            if time.monotonic() - getattr(self, "_refreshed", 0.0) > 1.0:   # (not again straight after
                self.refresh()                   # opening: the database was written out twice, 25 October)
