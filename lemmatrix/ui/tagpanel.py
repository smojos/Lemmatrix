"""Tag chips grouped by group, one tag per group (token dialogue and Configure matrix).

With `multi` on (Configure matrix), Ctrl+click picks a further tag in the same group
instead of replacing the one picked; combinations() then gives one tag set for every
combination of the picked tags."""

from __future__ import annotations

import itertools

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from . import theme
from .widgets import ChipButton, FlowLayout


class TagPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons: dict[str, ChipButton] = {}
        self.groups: list[set[str]] = []
        self.on_change = None
        self.multi = False                    # Ctrl+click adds a tag within a group
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(6, 6, 6, 6)
        self.box.setSpacing(4)

    def build(self, db, selected, classes=None, show_all: bool = True, include_defaults: bool = True,
              utterance: bool = False):
        """Chips for the tag groups, under their parent groups' names.

        classes: the lemma's word class and those above it (token dialogue). Then, unless
        show_all, only the groups usual for it are shown, plus any group the token already
        has a tag in; tags of the other groups are marked as unusual when picked. Groups for
        utterances only aren't offered at all (unless the token has a tag in one).
        utterance: the utterance dialogue. The utterance-only groups and the groups with no
        "usual for" hint come first, the rest under Show all; nothing is marked as unusual,
        since utterances have no word class.
        Returns how many groups are hidden.
        """
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().hide()              # gone now, not only when Qt gets round to deleting it
                item.widget().deleteLater()
        self.buttons.clear()
        self.groups.clear()
        ts = db.settings.tags
        usual = ts.usual_map()
        only = ts.only_map()
        hidden = 0
        last_parent = None
        for path, g in ts.leaf_groups():
            has_tag = any(t.name in selected for t in g.tags)
            g_only = only.get(id(g), False)
            if utterance:
                is_usual = g_only or not usual.get(id(g))
            elif classes is not None and g_only and not has_tag:
                continue                          # utterances only: never offered on lemma tokens
            else:
                is_usual = (classes is None or ts.is_usual(g, classes, usual)) and not \
                    (g_only and classes is not None)
            if not (show_all or is_usual or has_tag):
                hidden += 1
                continue
            parents = path[:-1]
            if parents and parents != last_parent:
                head = QLabel(" → ".join(parents))
                head.setStyleSheet(f"font-weight: bold; margin-top: 4px; "   # top-level grouping
                                   f"color: {theme.colour('pitch').name()};")   # in the theme colour
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
                b.unusual = not is_usual and not utterance
                tip = t.name + (" (default, not in file names)" if t.default else f"  [{t.code}]")
                if t.description:
                    tip += "\n" + t.description
                if g_only:
                    tip += "\nFor utterances only"
                elif not is_usual and not utterance:
                    tip += f"\nNot usual for this lemma's word class (usual for {', '.join(usual[id(g)])})"
                b.setToolTip(tip)
                b.toggled.connect(lambda on, name=t.name: self._toggled(name, on))
                flow.addWidget(b)
                self.buttons[t.name] = b
                names.add(t.name)
            self.groups.append(names)
            self.box.addWidget(holder)
        self.box.addStretch(1)
        return hidden

    def _toggled(self, name, on):
        ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if on and not (self.multi and ctrl):
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

    def combinations(self) -> list[list[str]]:
        """One tag list per combination: groups with several picked tags multiply."""
        picked = [[n for n in self.buttons if n in names and self.buttons[n].isChecked()]
                  for names in self.groups]
        picked = [p for p in picked if p]
        if not picked:
            return [[]]
        return [list(c) for c in itertools.product(*picked)]

    def set_enabled_all(self, on: bool):
        for b in self.buttons.values():
            b.setEnabled(on)
