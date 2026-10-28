# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Settings → Typology as chips (Josh, 28 October): a search bar at the top finds a chip from any
feature; each chip sits beside its label, under Pitch, Morphology and Syntax. A feature takes any
number of chips (so no "both"), added and removed freely, except the pitch kind: one fixed chip
with an ⓘ saying to change it in Settings → Pitch (a click on it goes there)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCompleter, QFormLayout, QGroupBox, QLabel, QLineEdit, QToolButton,
                               QVBoxLayout, QWidget)

from .. import pitchkind
from .. import typology as typ
from . import theme
from .widgets import FlowLayout

PITCH_INFO = ("The pitch kind is changed in Settings → Pitch (Change the pitch kind…), since changing "
              "it converts the database. Click to go there.")


def _chip(text: str, fixed: bool = False, tip: str = "") -> QToolButton:
    b = QToolButton()
    b.setText(text if fixed else text + "  ✕")
    colour = theme.accent().name() if fixed else theme.colour("pitch").name()
    b.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 10px; padding: 2px 8px; %s}"
                    % (colour, "font-weight: bold; " if fixed else ""))
    b.setToolTip(tip or ("Click to remove" if not fixed else ""))
    return b


class _Flow(QWidget):
    """A wrapping row of chips that grows down as it needs."""

    def __init__(self):
        super().__init__()
        self.flow = FlowLayout(self, spacing=6)

    def clear(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def fit(self):
        self.setMinimumHeight(self.flow.heightForWidth(max(120, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()


class TypologyBox(QWidget):
    changed = Signal()
    go_to_pitch = Signal()

    FEATURES = ((typ.MORPHOLOGY, "Morphology", "Morphology", typ.MORPHOLOGY_TIP),
                (typ.ORDER, "Syntax", "Constituent order", typ.ORDER_TIP))

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.kind = pitchkind.kind(db)
        self.chosen = {f: typ.values(db, f) for f, *_ in self.FEATURES}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.find = QLineEdit()
        self.find.setPlaceholderText("search for a chip to add (e.g. SVO, root-and-pattern)")
        self.find.setClearButtonEnabled(True)
        self.completer = QCompleter([], self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.find.setCompleter(self.completer)
        self.completer.activated.connect(self._chosen)
        self.find.returnPressed.connect(lambda: self._chosen(self.find.text()))
        lay.addWidget(self.find)
        # Pitch: the kind, fixed
        box = QGroupBox("Pitch")
        form = QFormLayout(box)
        row = QWidget()
        rl = FlowLayout(row, spacing=6)
        self.pitch_chip = _chip(pitchkind.LABELS.get(self.kind, self.kind), fixed=True,
                                tip=pitchkind.TIPS.get(self.kind, "") + ". Fixed here: " + PITCH_INFO)
        rl.addWidget(self.pitch_chip)
        self.pitch_info = QToolButton()
        self.pitch_info.setObjectName("typology-pitch-info")
        self.pitch_info.setText("ⓘ")
        self.pitch_info.setAutoRaise(True)
        self.pitch_info.setStyleSheet(f"color: {theme.muted()}; border: none;")
        self.pitch_info.setToolTip(PITCH_INFO)
        self.pitch_info.clicked.connect(lambda *_: self.go_to_pitch.emit())
        rl.addWidget(self.pitch_info)
        row.setMinimumHeight(rl.heightForWidth(300))
        form.addRow("Pitch kind", row)
        lay.addWidget(box)
        self.rows: dict[str, _Flow] = {}
        for feature, heading, label, tip in self.FEATURES:
            box = QGroupBox(heading)
            form = QFormLayout(box)
            flow = _Flow()
            flow.setToolTip(tip)
            self.rows[feature] = flow
            lab = QLabel(f"{label}  ⓘ" if feature == typ.ORDER else label)
            if feature == typ.ORDER:                      # the WALS chapters
                lab.setObjectName("typology-citations")
            lab.setToolTip(typ.CITATIONS if feature == typ.ORDER else tip)
            form.addRow(lab, flow)
            lay.addWidget(box)
        self._show()

    # ---- what is offered and chosen ----------------------------------------------
    def offered(self) -> dict[str, tuple[str, str]]:
        """{search label: (feature, value)} every chip not yet chosen."""
        out = {}
        for feature, _h, label, _t in self.FEATURES:
            for v, text in typ.CHOICES[feature]:
                if v not in self.chosen[feature]:
                    out[f"{text} · {label}"] = (feature, v)
        return out

    def add(self, feature: str, value: str) -> bool:
        if value in self.chosen[feature] or value not in dict(typ.CHOICES[feature]):
            return False
        self.chosen[feature].append(value)
        self._show()
        self.changed.emit()
        return True

    def remove(self, feature: str, value: str) -> bool:
        if value not in self.chosen[feature]:
            return False
        self.chosen[feature].remove(value)
        self._show()
        self.changed.emit()
        return True

    def apply_to(self, typology: dict):
        for feature in self.chosen:
            typ.set_values(typology, feature, self.chosen[feature])

    def _chosen(self, text: str):
        text = text.strip()
        if not text:
            return
        offered = self.offered()
        hit = offered.get(text)
        if hit is None:
            low = text.casefold()
            exact = [fv for lab, fv in offered.items() if lab.split(" · ")[0].casefold() == low]
            hits = exact or [fv for lab, fv in offered.items() if low in lab.casefold()]
            hit = hits[0] if len(hits) == 1 else None
        if hit is not None and self.add(*hit):
            QTimer.singleShot(0, self.find.clear)          # after the completer writes its text

    def _show(self):
        for feature, flow in self.rows.items():
            flow.clear()
            for v in self.chosen[feature]:
                b = _chip(typ.label(feature, v),
                          tip=(f"WALS {typ.WALS[v]}. " if feature == typ.ORDER and v in typ.WALS else "")
                          + "Click to remove")
                b.setProperty("value", v)
                b.clicked.connect(lambda *_, f=feature, v=v: self.remove(f, v))
                flow.flow.addWidget(b)
            if not self.chosen[feature]:
                none = QLabel("<i>unspecified</i>")
                none.setStyleSheet(f"color: {theme.muted()};")
                flow.flow.addWidget(none)
            flow.fit()
            QTimer.singleShot(0, flow.fit)
        self.completer.model().setStringList(list(self.offered()))
