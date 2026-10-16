"""Tag chips grouped by group, one tag per group (token dialogue and Configure matrix)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from . import theme
from .widgets import ChipButton, FlowLayout


class TagPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons: dict[str, ChipButton] = {}
        self.groups: list[set[str]] = []
        self.on_change = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(6, 6, 6, 6)
        self.box.setSpacing(4)

    def build(self, db, word_class, selected, include_defaults: bool = True):
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        self.groups.clear()
        last_parent = None
        for path, g in db.settings.tags.leaf_groups_for(word_class):
            parents = path[1:-1]
            if parents and parents != last_parent:
                head = QLabel(" → ".join(parents))
                head.setStyleSheet("font-weight: 600; margin-top: 4px;")
                self.box.addWidget(head)
            last_parent = parents
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color: #9aa;")
            self.box.addWidget(line)
            title = QLabel(g.name.lower())
            title.setStyleSheet(f"font-style: italic; color: {theme.muted()};")
            title.setAlignment(Qt.AlignRight)
            self.box.addWidget(title)
            holder = QWidget()
            flow = FlowLayout(holder, spacing=6)
            names = set()
            for t in g.tags:
                if t.default and not include_defaults:
                    continue
                b = ChipButton(t.display())
                b.setChecked(t.name in selected)
                tip = t.name + (" (default, not in file names)" if t.default else f"  [{t.code}]")
                if t.description:
                    tip += "\n" + t.description
                b.setToolTip(tip)
                b.toggled.connect(lambda on, name=t.name: self._toggled(name, on))
                flow.addWidget(b)
                self.buttons[t.name] = b
                names.add(t.name)
            self.groups.append(names)
            self.box.addWidget(holder)
        self.box.addStretch(1)

    def _toggled(self, name, on):
        if on:
            for names in self.groups:
                if name in names:
                    for other in names - {name}:
                        b = self.buttons[other]
                        if b.isChecked():
                            b.blockSignals(True)
                            b.setChecked(False)
                            b.blockSignals(False)
                            b.update()
        if self.on_change:
            self.on_change()

    def selected(self) -> list[str]:
        return [n for n, b in self.buttons.items() if b.isChecked()]

    def set_enabled_all(self, on: bool):
        for b in self.buttons.values():
            b.setEnabled(on)
