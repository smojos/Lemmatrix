"""A row of chips for the people and places of a session, with a + button to add more.

Used in the Current Session panel and in the notebook. Researchers and participants
show their codes, locations their names; the tooltip gives the rest. Clicking a chip
offers to remove it (and, for a participant, to open the consent file).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QLayout, QMenu, QMessageBox, QToolButton, QWidget

from ..model import Database, Location
from . import theme
from .icons import icon
from .widgets import ChipButton, FlowLayout

RESEARCHERS, PARTICIPANTS, LOCATIONS = "researchers", "participants", "locations"
TITLES = {RESEARCHERS: "Researchers", PARTICIPANTS: "Participants", LOCATIONS: "Locations"}


def consent_path(db: Database, consent: str) -> Path | None:
    """The consent file as a full path (a relative one is relative to the database's folder)."""
    from .. import layout
    return layout.consent_full_path(db, consent)


def open_consent(parent, db: Database, code: str):
    p = db.metadata.participant(code)
    path = consent_path(db, p.consent) if p else None
    if path is None:
        QMessageBox.information(parent, "Consent", f"No consent file is set for {code}.\n"
                                "Set one in Edit → Lists → Participants.")
        return
    if not path.exists():
        QMessageBox.warning(parent, "Consent", f"The consent file for {code} isn't there:\n{path}")
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class Chip(ChipButton):
    """A chip that is always 'on' (filled); clicking it opens its menu."""

    def __init__(self, text: str, compact: bool, parent=None):
        super().__init__(text, parent)
        self.setChecked(True)
        if compact:
            f = QFont(self.font())
            f.setPointSize(max(8, f.pointSize() - 2))
            self.setFont(f)

    def nextCheckState(self):
        pass                                    # stays filled

    def paintEvent(self, event):
        """Filled with the theme colour, as in the notebook's design."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = theme.accent()
        if self.underMouse():
            fill = fill.darker(115)
        if not self.isEnabled():
            fill = theme.colour("chip_disabled")
        p.setPen(QPen(fill.darker(120), 1))
        p.setBrush(fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(theme.text_on(fill))
        p.setFont(self.font())
        p.drawText(r, Qt.AlignCenter, self.text())


class ChipRow(QWidget):
    """The chips of one kind (researchers, participants or locations) for a session."""

    changed = Signal()

    def __init__(self, kind: str, db_getter, compact: bool = False, edit_list=None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.db_getter = db_getter              # the database can change under the row
        self.compact = compact
        self.edit_list = edit_list              # opens Edit → Lists at this list
        self.keys: list[str] = []
        self.flow = FlowLayout(self, spacing=4)
        self.flow.setSizeConstraint(QLayout.SetNoConstraint)   # the height is set by _fit
        self.read_only = False

    @property
    def db(self) -> Database:
        return self.db_getter()

    # ---- contents -------------------------------------------------------
    def set_keys(self, keys):
        self.keys = list(dict.fromkeys(keys))
        self._rebuild()

    def _label(self, key: str) -> tuple[str, str]:
        md = self.db.metadata
        if self.kind == LOCATIONS:
            loc = md.location(key)
            tip = md.location_path(key)
            if loc and loc.code:
                tip += f"  [{loc.code}]"
            if loc and loc.description:
                tip += "\n\n" + _short(loc.description)
            return (loc.name if loc else key), tip + ("" if loc else "\n(not in the list of locations)")
        p = md.researcher(key) if self.kind == RESEARCHERS else md.participant(key)
        if p is None:
            return key, f"{key} (not in the list of {TITLES[self.kind].lower()})"
        tip = p.name or p.code
        if p.description:
            tip += "\n" + _short(p.description)
        if self.kind == PARTICIPANTS and p.consent:
            tip += "\nConsent: " + p.consent
        return key, tip

    def _rebuild(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if (w := item.widget()) is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for key in self.keys:
            text, tip = self._label(key)
            c = Chip(text, self.compact)
            c.setToolTip(tip + ("" if self.read_only else "\nClick to remove"))
            c.clicked.connect(lambda *_, key=key, c=c: self._chip_menu(key, c))
            self.flow.addWidget(c)
        if not self.read_only:
            add = QToolButton()
            add.setIcon(icon("add", 16 if self.compact else 20))
            add.setIconSize(QSize(16, 16) if self.compact else QSize(20, 20))
            add.setAutoRaise(True)
            add.setToolTip(f"Add to {TITLES[self.kind].lower()}")
            add.clicked.connect(lambda *_, b=add: self._add_menu(b))
            self.flow.addWidget(add)
        self._fit()
        QTimer.singleShot(0, self._fit)        # once the new chips have their final sizes

    def _fit(self):
        """Grow to the height the wrapped chips need (grid layouts don't ask on their own)."""
        h = self.flow.heightForWidth(max(60, self.width()))
        if h != self.minimumHeight():
            self.setMinimumHeight(h)
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    # ---- menus ----------------------------------------------------------
    def _chip_menu(self, key, chip):
        if self.read_only and self.kind != PARTICIPANTS:
            return
        m = QMenu(self)
        if not self.read_only:
            m.addAction(icon("delete", 16), f"Remove {chip.text()}").triggered.connect(
                lambda *_: self._remove(key))
        if self.kind == PARTICIPANTS:
            m.addAction("Open consent file").triggered.connect(
                lambda *_: open_consent(self, self.db, key))
        m.exec(chip.mapToGlobal(chip.rect().bottomLeft()))

    def _add_menu(self, button):
        m = QMenu(self)
        md = self.db.metadata
        if self.kind == LOCATIONS:
            for loc in md.locations:
                self._location_menu(m, loc)
        else:
            people = md.researchers if self.kind == RESEARCHERS else md.participants
            for p in people:
                a = m.addAction(f"{p.code}  {p.name}" if p.name else p.code)
                a.setEnabled(p.code not in self.keys)
                a.triggered.connect(lambda *_, k=p.code: self._add(k))
        if m.isEmpty():
            a = m.addAction(f"The list of {TITLES[self.kind].lower()} is empty")
            a.setEnabled(False)
        if self.edit_list:
            m.addSeparator()
            m.addAction(f"Edit the list of {TITLES[self.kind].lower()}…").triggered.connect(
                lambda *_: self.edit_list(self.kind))
        m.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _location_menu(self, menu, loc: Location):
        label = loc.name + (f"  [{loc.code}]" if loc.code else "")
        if loc.children:
            sub = menu.addMenu(label)
            a = sub.addAction(loc.name)
            a.setEnabled(loc.key not in self.keys)
            a.triggered.connect(lambda *_, k=loc.key: self._add(k))
            sub.addSeparator()
            for c in loc.children:
                self._location_menu(sub, c)
        else:
            a = menu.addAction(label)
            a.setEnabled(loc.key not in self.keys)
            a.triggered.connect(lambda *_, k=loc.key: self._add(k))

    def _add(self, key):
        if key not in self.keys:
            self.keys.append(key)
            self._rebuild()
            self.changed.emit()

    def _remove(self, key):
        if key in self.keys:
            self.keys.remove(key)
            self._rebuild()
            self.changed.emit()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self.flow.heightForWidth(w)

    def sizeHint(self):
        return QSize(200, self.flow.heightForWidth(200))


def _short(text: str, n: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"
