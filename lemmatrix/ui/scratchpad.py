# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The phonetics scratchpad (Josh, 24 October: the Pitch and Segments scratchpads together; first
called the phonetics scratchpad): two pads, α and β, for asking a speaker "is it A or B?", in the main
window and under a text's lines (one widget, used twice: Josh, "complete clones"). A third, γ, is
an Easter egg (Josh, 24 October): it appears when the working panel is dragged tall enough for it
(Right Shift+C or G plays it: C follows A and B, G sounds like gamma) and goes again when there
isn't room.

Two tabs (IDEAS.md idea 46, Josh, 24 October):
- **Pitch** (idea 33): a pitch drawing with a box under it; a trace typed there (the usual
  notation, e.g. 55 3:3 21) is drawn as it is typed. With the pitch system hidden, or a pitch kind
  without scratchpads, the tab says *no pitch* and can't be chosen.
- **Segments**: a box for any sequence (ʌ, pu, t͡s); typing silently finds its soundfile (the
  session speaker's, one with no speaker, another speaker's, then Lemmatrix's own IPA soundfiles;
  `segments.voices`), and the record button beside the box records one into Soundfiles/Segments.

α and β play their pad on the tab shown: a click, Right Shift+A / Right Shift+B, or Enter. They are
grey when there is nothing to play. The boxes of both tabs sit at the same height, with α and β
centred on them (Josh). Tab goes round the pads' boxes, for typing (Josh). File → Open folder → Soundfiles › Segments opens their folder.
Nothing typed is saved: the pads are empty each time Lemmatrix opens."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QMenu, QSizePolicy, QStackedWidget,
                               QTabBar, QToolButton, QToolTip, QVBoxLayout, QWidget)

from .widgets import PitchCanvas, ipa_font

PITCH, SEGMENTS = "pitch", "segment"


def _play_pitch(main, value: str):
    """A pitch trace, in the voice and volume of Settings → Pitch."""
    main.play_pitch(value)


def _play_segment(main, value):
    """A segment soundfile (a segments.Voice), as it is."""
    from .. import audio
    from PySide6.QtWidgets import QMessageBox
    try:
        main.player.play([value.path], pad=True)    # silence round it, so no onset is lost
    except audio.AudioError as exc:
        QMessageBox.warning(main, "Play", str(exc))


# How each kind of content is played: kind -> function(main, value).
PLAYERS = {PITCH: _play_pitch, SEGMENTS: _play_segment}


class PitchScratchpad(QWidget):
    """The Pitch tab's pad: the drawing on top, the box under it."""
    KIND = PITCH
    changed = Signal()

    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        from .token_dialog import PitchValidator
        self.main = main
        self.kind = self.KIND
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(2)
        self.canvas = PitchCanvas(low=low, high=high, font=ipa_font(main.prefs.ipa_size + 3))
        self.canvas.setToolTip("Pitch scratchpad: the trace typed below, drawn")
        lay.addWidget(self.canvas)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("pitch scratchpad, e.g. 55 3:3 21")
        self.edit.setToolTip(tip)
        self.edit.setValidator(PitchValidator(self.edit))
        self.edit.setFont(ipa_font(main.prefs.ipa_size))
        self.edit.textChanged.connect(self.canvas.set_pitch)
        self.edit.textChanged.connect(lambda *_: self.changed.emit())
        self.edit.returnPressed.connect(self.play)
        row.addWidget(self.edit, 1)                # no play button: the pad's letter plays it
        lay.addLayout(row)

    def top_height(self) -> int:
        """The height above the box (the drawing), for lining the tabs and letters up."""
        return self.canvas.minimumHeight() + self.layout().spacing() + self.layout().contentsMargins().top()

    def set_range(self, low: int, high: int):
        self.canvas.set_range(low, high)

    def content(self) -> dict:
        """What the pad holds: its kind and its value."""
        return {"kind": self.kind, "value": self.edit.text()}

    def playable(self) -> bool:
        from .. import pitch as pitchmod
        try:
            return bool(self.edit.text().strip()) and bool(pitchmod.parse(self.edit.text()))
        except Exception:                          # noqa: BLE001 (a half-typed trace)
            return False

    def describe(self) -> str:
        return ""

    def play(self):
        """Play what the pad holds, by its kind."""
        c = self.content()
        if c["value"].strip():
            PLAYERS[c["kind"]](self.main, c["value"])


class _SequenceValidator(QValidator):
    """Characters Windows forbids in file names (the sequence names its soundfile) are said at the
    box, but not refused while typing: Keyman's IPA keyboards type < or > and then replace the
    letter before it (g< for ɢ), and refusing the < made the letter vanish (Josh, 25 October).
    Recording refuses such a sequence (SegmentPad.record)."""

    def __init__(self, edit, parent=None):
        super().__init__(parent)
        self.edit = edit

    def validate(self, text, pos):
        from .. import segments
        bad = segments.problem(text)
        if bad:
            QToolTip.showText(self.edit.mapToGlobal(self.edit.rect().bottomLeft()),
                              f"{bad} can't be in a sequence: it names its soundfile.", self.edit)
            return QValidator.Intermediate, text, pos
        return QValidator.Acceptable, text, pos


class SegmentPad(QWidget):
    """The Segments tab's pad: room above (so its box lines up with the pitch box), the box, and
    the record button beside it."""
    KIND = SEGMENTS
    changed = Signal()

    def __init__(self, main, parent=None):
        super().__init__(parent)
        from .icons import icon
        self.main = main
        self.kind = self.KIND
        self.chosen = None                        # a voice picked from the right-click menu
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(2)
        self.top = QWidget()                       # the pitch drawing's height, empty
        lay.addWidget(self.top)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.edit = QLineEdit()
        from . import keyboards
        keyboards.tag(self.edit, keyboards.SEGMENT)  # typed as transcriptions (idea 43)
        self.edit.setPlaceholderText("ʌ, pu, t͡s…")
        self.edit.setToolTip("Type a sequence (a sound, a syllable, anything): its soundfile is "
                             "found as you type. Enter, the letter or Right Shift plays it")
        self.edit.setFont(ipa_font(main.prefs.ipa_size))
        self.edit.setValidator(_SequenceValidator(self.edit, self.edit))
        self.edit.textChanged.connect(self._typed)
        self.edit.returnPressed.connect(self.play)
        self.edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.edit.customContextMenuRequested.connect(lambda pos: self.menu().exec(self.edit.mapToGlobal(pos)))
        row.addWidget(self.edit, 1)
        self.record_btn = QToolButton()            # outside the box (Josh, 24 October)
        self.record_btn.setIcon(icon("record", 24))
        self.record_btn.setIconSize(QSize(24, 24))
        self.record_btn.setAutoRaise(True)
        self.record_btn.setCursor(Qt.PointingHandCursor)
        self.record_btn.setToolTip("Record this sequence (into Soundfiles/Segments)")
        self.record_btn.clicked.connect(lambda *_: self.record())
        row.addWidget(self.record_btn, 0, Qt.AlignVCenter)
        lay.addLayout(row)

    def set_top(self, h: int):
        self.top.setFixedHeight(max(0, h - self.layout().spacing() - self.layout().contentsMargins().top()))

    def _db(self):
        doc = getattr(self.main, "doc", None)
        return doc.db if doc is not None else None

    def _typed(self, *_):
        self.chosen = None
        self.changed.emit()

    def sequence(self) -> str:
        from .. import segments
        return segments.norm(self.edit.text())

    def voices(self) -> list:
        from .. import segments
        db = self._db()
        if db is None or not self.sequence():
            return []
        return segments.voices(db, self.sequence(), self.main.session_speaker())

    def voice(self):
        found = self.voices()
        if self.chosen is not None and any(v.path == self.chosen.path for v in found):
            return self.chosen
        return found[0] if found else None

    def content(self) -> dict:
        return {"kind": self.kind, "value": self.edit.text()}

    def playable(self) -> bool:
        return self.voice() is not None

    def describe(self) -> str:
        """Whose voice plays, for the letter's hover."""
        v = self.voice()
        if v is None:
            return f"No soundfile for {self.sequence()} yet: record one" if self.sequence() else ""
        if v.native:
            return f"[{v.sequence}] {v.credit}"
        from .. import audio
        try:
            date = audio.read_info(v.path).get("ICRD", "") if v.path.suffix.lower() == ".wav" else ""
        except OSError:
            date = ""
        return f"{v.path.name}" + (f" · {v.speaker}" if v.speaker else "") + (f" · {date}" if date else "")

    def play(self):
        v = self.voice()
        if v is not None:
            PLAYERS[self.kind](self.main, v)

    def menu(self) -> QMenu:
        """The box's own menu, then every voice for the sequence (pick one) and Record…"""
        m = self.edit.createStandardContextMenu()
        found = self.voices()
        if found:
            m.addSeparator()
            cur = self.voice()
            for v in found:
                a = m.addAction(v.label())
                a.setCheckable(True)
                a.setChecked(cur is not None and v.path == cur.path)
                a.triggered.connect(lambda *_, v=v: self._choose(v))
        m.addSeparator()
        a = m.addAction("Record…")
        a.setEnabled(bool(self.sequence()))
        a.triggered.connect(lambda *_: self.record())
        return m

    def _choose(self, v):
        self.chosen = v
        self.changed.emit()
        self.play()

    def record(self):
        from PySide6.QtWidgets import QMessageBox
        if not self.sequence():
            self.edit.setFocus()
            QToolTip.showText(self.edit.mapToGlobal(self.edit.rect().bottomLeft()),
                              "Type the sequence to record first.", self.edit)
            return
        from .. import segments
        sequence = self.sequence()
        if segments.problem(sequence) and segments.called(sequence):
            sequence = segments.called(sequence)  # `?` records as ʔ: ? can't be in a file name
        bad = segments.problem(sequence)
        if bad:
            self.edit.setFocus()
            QToolTip.showText(self.edit.mapToGlobal(self.edit.rect().bottomLeft()),
                              f"{bad} can't be in a sequence: it names its soundfile.", self.edit)
            return
        db = self._db()
        if db is None or not db.path:
            QMessageBox.information(self, "Record", "Save the database first: segment soundfiles go into its "
                                    "Soundfiles/Segments folder.")
            return
        from .segment_record import SegmentRecordDialog
        dlg = SegmentRecordDialog(self.main, sequence, self)
        dlg.exec()
        self.chosen = None
        self.changed.emit()


class PhoneticsScratchpad(QWidget):
    """The phonetics scratchpad: the Pitch and Segments tabs over α and β. Each letter is on its pad's
    left, large, bold, in the theme colour (grey with nothing to play), centred on the box."""

    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        self.main = main
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        self.tabs = QTabBar()
        self.tabs.addTab("Pitch")
        self.tabs.addTab("Segments")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._tab_menu)
        outer.addWidget(self.tabs, 0, Qt.AlignLeft)
        rows = QVBoxLayout()
        rows.setSpacing(4)
        self.pads, self.seg_pads, self.letters, self.stacks, self.letter_tops, self.rows = [], [], [], [], [], []
        # α and β; γ, an Easter egg (Josh, 24 October), only while the working panel is dragged
        # tall enough for a third row
        for letter, keys in (("α", "A"), ("β", "B"), ("γ", "C or G")):
            roww = QWidget()
            row = QHBoxLayout(roww)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            # the letter is the play button (Josh, 24 October), centred on the box (Josh): room
            # above it as tall as the drawing, then the letter at the box's height
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            top = QWidget()
            col.addWidget(top)
            lbl = QToolButton()
            lbl.setText(letter)
            lbl.setAutoRaise(True)
            lbl.setCursor(Qt.PointingHandCursor)
            f = lbl.font()
            f.setBold(True)
            f.setPointSizeF(f.pointSizeF() * 2.2)
            lbl.setFont(f)
            lbl.setProperty("key", keys)
            i = len(self.letters)
            lbl.clicked.connect(lambda _=False, i=i: self.play_row(i))
            col.addWidget(lbl, 0, Qt.AlignVCenter)
            row.addLayout(col)
            pitch = PitchScratchpad(main, low, high, tip)
            seg = SegmentPad(main)
            stack = QStackedWidget()
            stack.addWidget(pitch)
            stack.addWidget(seg)
            stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            row.addWidget(stack, 1)
            rows.addWidget(roww)
            for p in (pitch, seg):
                p.changed.connect(self.refresh)
            self.pads.append(pitch)
            self.seg_pads.append(seg)
            self.letters.append(lbl)
            self.stacks.append(stack)
            self.letter_tops.append(top)
            self.rows.append(roww)
        self.rows[2].hide()                        # γ: hidden until there is room for it
        outer.addLayout(rows)
        outer.addStretch(1)
        # γ mustn't make the panel's minimum taller, or it could never be dragged smaller again
        from PySide6.QtWidgets import QLayout
        outer.setSizeConstraint(QLayout.SetNoConstraint)
        for p in self.pads + self.seg_pads:        # Tab loops round the pads (Josh, 24 October)
            p.edit.installEventFilter(self)
        self.alpha, self.beta, self.gamma = self.pads
        self.seg_alpha, self.seg_beta, self.seg_gamma = self.seg_pads
        self.tabs.currentChanged.connect(self._tab_changed)
        self._sync_heights()
        self.restyle()
        want = 1 if getattr(main.prefs, "comparison_tab", PITCH) == SEGMENTS else 0
        self._auto = True
        self.tabs.setCurrentIndex(want)
        self._auto = False
        self._tab_changed(want, remember=False)
        self.show_pitch()

    # ---- tabs
    def current(self) -> str:
        return SEGMENTS if self.tabs.currentIndex() == 1 else PITCH

    def current_pads(self) -> list:
        return self.seg_pads if self.current() == SEGMENTS else self.pads

    def _tab_changed(self, index: int, remember: bool = True):
        for st in self.stacks:
            st.setCurrentIndex(1 if index == 1 else 0)
        if remember and not getattr(self, "_auto", False) and self.tabs.isTabEnabled(index):
            self.main.prefs.comparison_tab = SEGMENTS if index == 1 else PITCH
        self.refresh()

    def set_tab(self, kind: str):
        i = 1 if kind == SEGMENTS else 0
        if self.tabs.isTabEnabled(i):
            self.tabs.setCurrentIndex(i)

    def _tab_menu(self, pos):
        if self.tabs.tabAt(pos) == 0 and not self.tabs.isTabEnabled(0):
            m = self.note_menu()
            if m.actions():
                m.exec(self.tabs.mapToGlobal(pos))

    def note_menu(self) -> QMenu:
        """The right-click menu of the *no pitch* tab: Unhide pitch (where the kind has pitch)."""
        from .. import pitchview
        m = QMenu(self)
        if pitchview.has(pitchview.SCRATCHPADS):
            a = m.addAction("Unhide pitch")
            a.triggered.connect(lambda *_: self.main.set_pitch_shown(True))
        return m

    # ---- playing
    def play(self, pad):
        """A pad played (its letter clicked, or Right Shift+A / B), if it is the tab shown."""
        if pad in self.current_pads():
            pad.play()

    def play_row(self, i: int):
        if self.rows[i].isVisible() or not self.isVisible():
            self.play(self.current_pads()[i])

    def has_gamma(self) -> bool:
        return not self.rows[2].isHidden()

    def play_key(self, key: str) -> bool:
        """Right Shift+A plays α, Right Shift+B β, and Right Shift+C or G γ while it is shown, on
        the tab shown. False if the key has nothing to play here (it is then typed)."""
        i = {"A": 0, "B": 1, "C": 2, "G": 2}.get(key.upper())
        if i is None or (i == 2 and not self.has_gamma()):
            return False
        self.play_row(i)
        return True

    # ---- γ: shown while the area is tall enough for a third row
    def _third_fits(self) -> bool:
        lay = self.layout()
        sp = lay.spacing()
        row = max(r.sizeHint().height() for r in self.rows[:2])
        need = (self.tabs.sizeHint().height() + sp + 3 * row + 2 * 4 + sp)
        return self.height() >= need

    def resizeEvent(self, event):
        super().resizeEvent(event)
        fits = self._third_fits()
        if fits != self.has_gamma():
            self.rows[2].setVisible(fits)
            self.refresh()

    # ---- the pitch system
    def set_range(self, low: int, high: int):
        for p in self.pads:
            p.set_range(low, high)
        self._sync_heights()

    def show_pitch(self, on: bool | None = None):
        """The Pitch tab, or *no pitch* (the pitch system hidden, or a pitch kind without
        scratchpads: it can't be chosen); None: as the open database says."""
        from .. import pitchview
        if on is None:
            on = pitchview.shown(pitchview.SCRATCHPADS)
        self._auto = True                         # Qt moves off a disabled tab by itself
        self.tabs.setTabEnabled(0, on)
        self.tabs.setTabText(0, "Pitch" if on else "no pitch")
        kind_has = pitchview.has(pitchview.SCRATCHPADS)
        self.tabs.setTabToolTip(0, "" if on else (
            "The pitch system is hidden. Right-click to unhide it (or View → Show pitch system, or "
            "File → Settings → Pitch)" if kind_has else
            "This database's pitch kind has no pitch scratchpads (Edit → Metadata → Pitch kind)"))
        try:                                      # switched for the pitch system: not remembered
            if not on and self.tabs.currentIndex() == 0:
                self.tabs.setCurrentIndex(1)
            elif on and self.main.prefs.comparison_tab != SEGMENTS and self.tabs.currentIndex() == 1:
                self.tabs.setCurrentIndex(0)      # back to the tab this computer was on
        finally:
            self._auto = False
        self._tab_changed(self.tabs.currentIndex(), remember=False)

    # ---- looks
    def _two_rows(self) -> int:
        """The area's height with α and β only: its minimum, γ or not."""
        sp = self.layout().spacing()
        row = max(r.sizeHint().height() for r in self.rows[:2])
        return self.tabs.sizeHint().height() + sp + 2 * row + 4

    def sizeHint(self):
        h = super().sizeHint()
        h.setHeight(self._two_rows())
        return h

    def minimumSizeHint(self):
        h = super().minimumSizeHint()
        h.setHeight(self._two_rows())
        return h

    def _sync_heights(self):
        """The boxes of both tabs at the same height, and α and β centred on them (Josh)."""
        h = self.pads[0].top_height()
        for seg in self.seg_pads:
            seg.set_top(h)
        box = self.pads[0].edit.sizeHint().height()
        wide = max(lbl.sizeHint().width() for lbl in self.letters)   # the boxes' left edges in line
        for top, lbl, seg in zip(self.letter_tops, self.letters, self.seg_pads):
            top.setFixedHeight(h)
            lbl.setFixedHeight(max(box, seg.record_btn.sizeHint().height()))
            lbl.setFixedWidth(wide)

    def refresh(self):
        """α and β in the theme colour when there is something to play, grey when not; their
        hover says whose voice it is."""
        from . import theme
        on, off = theme.colour("pitch").name(), theme.colour("disabled").name()
        for pad, lbl in zip(self.current_pads(), self.letters):
            ok = pad.playable()
            lbl.setStyleSheet(
                f"QToolButton {{ color: {on if ok else off}; border: none; padding: 0 4px; }}"
                f"QToolButton:hover {{ background: {theme.wash(0.8).name()}; border-radius: 6px; }}")
            tip = f"Play {lbl.text()} (Right Shift+{lbl.property('key')})"
            more = pad.describe()
            lbl.setToolTip(tip + ("\n" + more if more else ""))

    def restyle(self):
        from . import theme
        # given the palette directly: on Windows Qt didn't always pass a theme change down to the
        # pads, so their boxes stayed dark after switching to light (Josh, 24 October)
        self.setPalette(theme.interface_palette())
        a = theme.accent()
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 3px 10px; font-weight: normal; } "
            f"QTabBar::tab:selected {{ background: {a.name()}; color: {theme.text_on(a).name()}; }}"
            f"QTabBar::tab:disabled {{ color: {theme.colour('disabled').name()}; font-style: italic; }}")
        self.refresh()

    # a file added or deleted by hand (Explorer, Praat) shows when the window comes back
    def showEvent(self, event):
        super().showEvent(event)
        w = self.window()
        if w is not None and getattr(self, "_watching", None) is not w:
            w.installEventFilter(self)
            self._watching = w
        self._sync_heights()
        self.refresh()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.WindowActivate:
            self.refresh()
            return False
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab) \
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            back = event.key() == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
            return self.tab_to(obj, -1 if back else 1)
        return False

    def tab_to(self, edit, step: int) -> bool:
        """Tab from a pad's box to the next pad's on the tab shown, round and round (α > β > α, or
        α > β > γ > α while γ shows); Shift+Tab back. For typing: nothing plays."""
        boxes = [p.edit for p, row in zip(self.current_pads(), self.rows) if not row.isHidden()]
        if edit not in boxes:
            return False
        nxt = boxes[(boxes.index(edit) + step) % len(boxes)]
        nxt.setFocus(Qt.TabFocusReason)
        nxt.selectAll()
        return True

