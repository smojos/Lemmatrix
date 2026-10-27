# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The token dialogue: fields, tags and recording, with Back and Next."""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QDir, QEvent, QRegularExpression, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QRegularExpressionValidator, QShortcut, QValidator
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)
from PySide6.QtCore import QFile

from .. import audio, matrix as mx, pitch as pitchmod, predict, storage
from ..model import Entry, Token, new_id
from PySide6.QtCore import QSize

from . import keyboards
from . import widgets as _w  # (ask: buttons that say what they do)
from . import spellui, theme
from .icons import icon
from .table import show_suggestion
from .tagpanel import TagPanel
from .widgets import PitchCanvas, caption, ipa_font, meaning


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PitchValidator(QValidator):
    """Digits, spaces, commas and colons; the IPA length mark ː becomes a colon as you type."""
    ALLOWED = QRegularExpression(r"^[0-9 ,:]*$")

    def validate(self, text, pos):
        text = text.replace(pitchmod.LENGTH_MARK, ":")
        ok = self.ALLOWED.match(text).hasMatch()
        return (QValidator.Acceptable if ok else QValidator.Invalid), text, pos


@dataclass
class Slot:
    """A place the dialogue can show: an existing token or an empty cell."""
    entry: Entry
    index: int | None              # token index in entry.tokens, or None for a new token
    tags: tuple = ()               # tags for a new token
    explicit: bool = False         # created on purpose (double-click), so OK keeps it even if empty
    defaults: bool | None = None   # pre-select group defaults (None: only if tags were given)
    values: dict = field(default_factory=dict)   # a new token's fields filled in: {(field, lang or None): text}


class TokenDialog(QDialog):
    MULTI_TOKENS = True       # Ctrl+click picks several tags in a group: one token per combination
    SNIP_GAPS = True          # ✂ auto-snip shortens long gaps between repetitions (tokens only)
    MAX_TOKENS = 50           # at most this many tokens from one OK

    def __init__(self, main, slots: list[Slot], index: int, parent=None):
        super().__init__(parent or main)
        self.main = main
        self.doc = main.doc
        self.db = main.doc.db
        self.slots = slots
        self.pos = index
        self.token: Token | None = None
        self.original: Token | None = None
        self._renames: list = []                  # recordings renamed, to go with the next commit
        self.unknown_tags: list[str] = []
        self.suggestion: predict.Suggestion | None = None   # the predicted translation shown, if any
        self.setWindowTitle("Edit Token")
        self.resize(920, 780)
        self._build()
        self._scroll_body()
        g = self.main.prefs.get_bytes("window/token_dialog")
        if g:                                     # the size and place it had when last closed
            self.restoreGeometry(g)
        self._load()

    def _scroll_body(self):
        """Everything but the bottom row (Back, Next, OK, Cancel) in a scroll area, so the dialogue
        is never taller than the screen: the utterance dialogue, with its Lemmas and Source boxes
        and large IPA, was, and its recording area was out of reach (Josh, 25 October)."""
        outer = self.layout()
        nav = outer.itemAt(outer.count() - 1)
        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 0)
        while outer.count() > 1:
            item = outer.takeAt(0)
            stretch = 0
            if item.widget() is not None:
                inner.addWidget(item.widget())
            elif item.layout() is not None:
                lay = item.layout()
                lay.setParent(None)
                stretch = 1 if lay is getattr(self, "_top_layout", None) else 0
                inner.addLayout(lay, stretch)
            else:
                inner.addItem(item)
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self.body_scroll = scroll
        outer.insertWidget(0, scroll, 1)
        assert outer.itemAt(1) is nav

    def showEvent(self, event):
        super().showEvent(event)
        from .winstate import _clamp
        _clamp(self)                              # a remembered size taller than this screen

    # ------------------------------------------------------------------ UI
    PITCH_PART = "tokens"      # which part of the pitch system this dialogue shows (pitchview, idea 9)

    def pitch_shown(self) -> bool:
        """Settings → Pitch → Show the pitch system: off hides the drawing, its play button, the
        Pitch field and pitch playback here; the token's Pitch is kept as it is."""
        from .. import pitchview
        return pitchview.shown(self.PITCH_PART)

    def _build(self):
        s = self.db.settings
        pitch_on = self.pitch_shown()
        outer = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setFont(ipa_font(15))
        self.header.setStyleSheet("font-weight: 600; padding: 2px 0 6px 0;")
        # The header row: the token, then Cogitate at the top right (Josh's mockup, 25 October: it
        # links the whole token or utterance, not its comment, so it doesn't belong among the fields)
        self.head_row = QHBoxLayout()
        self.head_row.setContentsMargins(0, 0, 0, 0)
        self.head_row.addWidget(self.header, 1)
        outer.addLayout(self.head_row)

        top = QHBoxLayout()
        self._top_layout = top                    # the part that stretches (_scroll_body)
        outer.addLayout(top, 1)

        left = QGridLayout()
        left.setColumnStretch(1, 1)
        self.canvas = PitchCanvas(low=s.pitch_low, high=s.pitch_high, font=ipa_font(self.main.prefs.ipa_size + 3))
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._canvas_menu)
        self.canvas.setToolTip("Right-click to play the pitch")
        self.pitch_play = QToolButton()
        self.pitch_play.setIcon(icon("play-pitch", 22))
        self.pitch_play.setIconSize(QSize(22, 22))
        self.pitch_play.setAutoRaise(True)
        self.pitch_play.setToolTip("Play the pitch (Ctrl+Shift+Space); the sound is set in "
                                   "File → Settings → Pitch")
        self.pitch_play.clicked.connect(lambda *_: self._play_pitch())
        drawing = QHBoxLayout()                 # the drawing, with its play button beside it
        drawing.setContentsMargins(0, 0, 0, 0)
        drawing.addWidget(self.canvas, 1)
        drawing.addWidget(self.pitch_play, 0, Qt.AlignVCenter)
        self.drawing_label = QLabel("Pitch\nRendering")
        left.addWidget(self.drawing_label, 1, 0, Qt.AlignVCenter)
        left.addLayout(drawing, 1, 1)
        for w in (self.drawing_label, self.canvas, self.pitch_play):
            w.setVisible(pitch_on)               # hidden with the pitch system (idea 9)
        self.edits: dict[str, QLineEdit] = {}
        self.translation: QLineEdit | None = None      # the English translation: gets suggestions
        self.comment: QLineEdit | None = None          # the first comment field: Push to question
        row = 2
        for f in s.token_fields:
            if f.role == "pitch" and not pitch_on:
                continue                          # not edited here: the token keeps its Pitch as it is
            ed = keyboards.tag(QLineEdit(), f.name)        # its own keyboard (idea 43)
            if f.role in ("phonetic", "phonemic"):
                ed.setFont(ipa_font(self.main.prefs.ipa_size + 3))
            else:
                ed.setFont(ipa_font(self.main.prefs.ipa_size + 1))
            if f.role == "pitch":
                ed.setValidator(PitchValidator(ed))
                ed.setPlaceholderText("e.g. 11 4:42 1:4")
                ed.textChanged.connect(self._pitch_changed)
            ed.textChanged.connect(self._fields_changed)
            if f.role == "translation" and s.primary_gloss == predict.LANG:
                self.translation = ed
                spellui.attach(ed, getattr(self.main, "speller", None))   # red lines under unknown words
                ed.textChanged.connect(lambda *_: self._update_suggestion())
            label = caption(f, f" ({s.primary_gloss})" if f.multilingual and len(s.gloss_languages) > 1 else "")
            lbl = QLabel(label)
            if label != f.title and not label.startswith(f.title + " "):
                lbl.setToolTip(f.title)           # an abbreviation shown (idea 73): the name in the hover
            left.addWidget(lbl, row, 0)
            if self.comment is None and f.is_comment:
                self.comment = ed
                self.push_btn = QToolButton()
                self.push_btn.setIcon(icon("push-question", 22))
                self.push_btn.setIconSize(QSize(22, 22))
                self.push_btn.setAutoRaise(True)
                self.push_btn.setToolTip("Push to question: the comment becomes an open question in the "
                                         "session's notebook, linked to this token, and the box is cleared")
                self.push_btn.clicked.connect(lambda *_: self.push_to_question())
                self.todo_btn = QToolButton()     # Push to To Do: the orange flag (Josh, 21 October)
                self.todo_btn.setIcon(icon("push-todo", 22))
                self.todo_btn.setIconSize(QSize(22, 22))
                self.todo_btn.setAutoRaise(True)
                self.todo_btn.setToolTip("Push to To Do: the comment becomes an open to do in the "
                                         "session's notebook, linked to this token, and the box is cleared")
                self.todo_btn.clicked.connect(lambda *_: self.push_to_todo())
                for b in (self.push_btn, self.todo_btn):
                    b.setEnabled(False)
                    ed.textChanged.connect(lambda text, b=b: b.setEnabled(bool(text.strip())))
                box = QHBoxLayout()               # the box, with the buttons beside it
                box.setContentsMargins(0, 0, 0, 0)
                box.addWidget(ed, 1)
                box.addWidget(self.push_btn, 0, Qt.AlignVCenter)
                box.addWidget(self.todo_btn, 0, Qt.AlignVCenter)
                left.addLayout(box, row, 1)
            else:
                left.addWidget(ed, row, 1)
            self.edits[f.name] = ed
            ed.installEventFilter(self)           # Ctrl+Space plays, never types a space
            row += 1
        row = self._build_other_languages(left, row)
        self.pitch_note = QLabel()
        self.pitch_note.setStyleSheet(f"color: {theme.colour('warning').name()};")
        left.addWidget(self.pitch_note, row, 1)
        self.pitch_note.setVisible(pitch_on)
        row += 1
        # Cogitate: a 48 px button with Josh's icon (Link to hypothesis…; Josh, 22 October: it
        # replaced the words), with "In hypotheses: H3 (evidence)…" before it, in the header row
        self.hyp_btn = QToolButton()
        self.hyp_btn.setIconSize(QSize(48, 48))
        self.hyp_btn.setAutoRaise(True)
        self.hyp_btn.setCursor(Qt.PointingHandCursor)
        self.hyp_btn.setToolTip("Link to hypothesis… (Cogitate): link this token to a hypothesis, as "
                                "evidence, counterevidence or relevant")
        self.hyp_btn.clicked.connect(lambda *_: self.link_to_hypothesis())
        self._hyp_icon()
        self.hyp_line = QLabel()
        self.hyp_line.setTextFormat(Qt.RichText)
        self.hyp_line.setWordWrap(True)
        self.hyp_line.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hyp_line.linkActivated.connect(self._hypothesis_link)
        self.head_row.addWidget(self.hyp_line, 0, Qt.AlignVCenter)
        self.head_row.addWidget(self.hyp_btn, 0, Qt.AlignVCenter)
        try:
            self.doc.hypothesesChanged.connect(self._show_hypotheses)
        except (AttributeError, RuntimeError):
            pass
        left.setRowStretch(row, 1)
        lw = QWidget()
        lw.setLayout(left)
        top.addWidget(lw, 3)

        tags_box = QGroupBox("Tags")
        f = tags_box.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        tags_box.setFont(f)
        tl = QVBoxLayout(tags_box)
        self.tags = TagPanel()
        self.tags.setFont(self.font())
        self.tags.on_change = self._tags_changed
        self.tags.multi = self.MULTI_TOKENS
        if self.MULTI_TOKENS:
            tags_box.setToolTip("Ctrl+click picks more than one tag in a group: OK then makes one "
                                "token for each combination (e.g. 3SG.A, 3PL.A × FUT1, FUT2 = 4 tokens).")
        scroll = QScrollArea()
        scroll.setFocusPolicy(Qt.NoFocus)          # not a stop of its own when tabbing
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tags)
        scroll.setFrameShape(QFrame.NoFrame)
        tl.addWidget(scroll)
        self.show_all = False                     # Show all tags: stays on for Back and Next
        self.show_all_btn = QPushButton()
        plain = QFont(self.font())
        plain.setBold(False)                      # set explicitly, or it inherits the Tags title's bold
        plain.setPointSizeF(self.font().pointSizeF())
        self.show_all_btn.setFont(plain)
        if theme.dark():                          # light grey on dark grey
            fg, bg, hover = "#c8c8c8", "#45474b", "#505256"
        else:                                     # dark grey on grey
            fg, bg, hover = "#444444", "#d6d6d6", "#cbcbcb"
        self.show_all_btn.setStyleSheet(
            f"QPushButton {{ color: {fg}; background: {bg}; border: none; border-radius: 4px; "
            f"padding: 4px 10px; font-weight: normal; }} "
            f"QPushButton:hover, QPushButton:checked {{ background: {hover}; }}")
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.setToolTip("Shown first: the tag groups usual for this lemma's word class, "
                                     "and any group the token has a tag in")
        self.show_all_btn.toggled.connect(self._show_all_toggled)
        tl.addWidget(self.show_all_btn, 0, Qt.AlignLeft)
        self.unusual_note = QLabel()
        self.unusual_note.setFont(self.font())
        self.unusual_note.setWordWrap(True)
        self.unusual_note.setTextFormat(Qt.RichText)
        self.unusual_note.linkActivated.connect(lambda *_: self._stop_unusual_warning())
        tl.addWidget(self.unusual_note)
        self.combo_note = QLabel()                # "→ 4 tokens", as in Configure matrix
        self.combo_note.setFont(self.font())
        self.combo_note.setStyleSheet("font-weight: 600;")
        self.combo_note.setWordWrap(True)
        self.combo_note.hide()
        tl.addWidget(self.combo_note)
        top.addWidget(tags_box, 2)

        from .recording_panel import RecordingPanel   # one for tokens, utterances and segments
        rec = self.rec_panel = RecordingPanel(self.main, self)
        rl = rec.grid
        for name in ("filename", "location", "name_note", "record_btn", "play_btn", "delete_btn",
                     "update_btn", "praat_btn", "source_box", "meter", "level_note"):
            setattr(self, name, getattr(rec, name))
        self.rerecord_btn = QToolButton()        # the rerecord flag: faint grey, red when on
        self.rerecord_btn.setCheckable(True)
        self.rerecord_btn.setAutoRaise(True)
        self.rerecord_btn.setIconSize(QSize(36, 36))
        self.rerecord_btn.setCursor(Qt.PointingHandCursor)
        self.rerecord_btn.setStyleSheet("QToolButton, QToolButton:checked, QToolButton:hover "
                                        "{ border: none; background: transparent; }")
        self.rerecord_btn.toggled.connect(self._rerecord_toggled)
        rl.addWidget(self.rerecord_btn, 0, 4, Qt.AlignRight | Qt.AlignTop)
        rl.addWidget(QLabel("Speaker"), 3, 3, Qt.AlignRight)
        self.speaker = QComboBox()
        self.speaker.setToolTip("The token's speaker. Choosing one makes them the speaker of the "
                                "next recordings too, until another is chosen.")
        self.speaker.currentTextChanged.connect(self._fields_changed)
        self.speaker.activated.connect(lambda _: self.main.set_speaker(self.speaker.currentText()))
        self.speaker.activated.connect(lambda _: setattr(self, "_planned", False))   # chosen on purpose
        self.speaker.setFixedWidth(130)
        rl.addWidget(self.speaker, 3, 4)
        rl.addWidget(QLabel("Date"), 4, 3, Qt.AlignRight)
        self.date = QLineEdit()
        self.date.setPlaceholderText("YYYY-MM-DD")
        self.date.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"(\d{4}-\d{2}-\d{2})?"), self.date))
        self.date.textChanged.connect(self._fields_changed)
        self.date.textEdited.connect(lambda _: setattr(self, "_planned", False))   # typed on purpose
        self.date.installEventFilter(self)        # Ctrl+Space plays here too
        self.date.setFixedWidth(130)
        rl.addWidget(self.date, 4, 4)

        self.record_btn.clicked.connect(self._record)
        self.play_btn.clicked.connect(self._play)
        self.delete_btn.clicked.connect(self._delete_recording)
        self.update_btn.clicked.connect(self._update_name)
        self.praat_btn.clicked.connect(lambda *_: self._open_in_praat())
        rec.snip_gaps = self.SNIP_GAPS            # ✂ auto-snip: gaps for tokens, ends only for utterances
        rec.snip_btn.clicked.connect(lambda *_: self._proselytize())
        rec.setContextMenuPolicy(Qt.CustomContextMenu)
        rec.customContextMenuRequested.connect(lambda pos, rec=rec: self._recording_menu(rec.mapToGlobal(pos)))
        outer.addWidget(rec)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("◀ Back")
        self.back_btn.setToolTip("Save and go to the previous token (Alt+Left)")
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setToolTip("Save and go to the next token (Alt+Right)")
        self.position = QLabel()
        self.position.setStyleSheet(f"color: {theme.muted()};")
        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.position)
        nav.addStretch(1)
        nav.addWidget(ok)
        nav.addWidget(cancel)
        outer.addLayout(nav)
        self.back_btn.clicked.connect(lambda: self._move(-1))
        self.next_btn.clicked.connect(lambda: self._move(1))
        ok.clicked.connect(self._ok)
        cancel.clicked.connect(self.reject)

        QShortcut(QKeySequence("Ctrl+R"), self, self._record)
        QShortcut(QKeySequence("Ctrl+Space"), self, self._play)
        QShortcut(QKeySequence("Ctrl+Shift+Space"), self, self._play_pitch)
        QShortcut(QKeySequence("Ctrl+Alt+Space"), self, self._praat_key)   # as in All data (26 October)
        QShortcut(QKeySequence("Alt+Left"), self, lambda: self._move(-1))
        QShortcut(QKeySequence("Alt+Right"), self, lambda: self._move(1))

    # The take in progress and the meter's timer are the recording panel's (recording_panel.py)
    @property
    def recorder(self):
        return self.rec_panel.recorder if hasattr(self, "rec_panel") else None

    @recorder.setter
    def recorder(self, value):
        if hasattr(self, "rec_panel"):
            self.rec_panel.recorder = value

    @property
    def timer(self):
        return self.rec_panel.timer

    # ---------------------------------------------------------------- data
    @property
    def slot(self) -> Slot:
        return self.slots[self.pos]

    def _load(self):
        sl = self.slot
        e = sl.entry
        s = self.db.settings
        self.level_note.hide()                    # the level check belongs to the last recording
        self.meter.reset()
        if sl.index is not None and sl.index < len(e.tokens):
            self.original = e.tokens[sl.index]
            self.token = self.original.copy()
        else:
            self.original = None
            self.token = self._new_token(sl)
            for (name, lang), text in sl.values.items():   # e.g. words from a text's line (idea 31)
                f = s.token_field(name)
                if f is not None:
                    self.token.set(name, text, (lang or s.primary_gloss) if f.multilingual else None,
                                   f.multilingual)
        t = self.token
        self._show_header(e)
        for name, ed in self.edits.items():
            f = s.token_field(name)
            ed.blockSignals(True)
            ed.setText(t.get(name, s.primary_gloss) if f.multilingual else t.get(name))
            ed.blockSignals(False)
        for (name, lang), ed in self.other_edits.items():
            ed.blockSignals(True)
            ed.setText(t.get(name, lang))
            ed.blockSignals(False)
        self.canvas.set_range(s.pitch_low, s.pitch_high)
        self._pitch_changed(t.get("Pitch"))
        known = {tg.name for tg, _ in s.tags.tags()}
        self.unknown_tags = [x for x in t.tags if x not in known]
        self._build_tags(set(t.tags))
        # A planned token (a batch's, idea 64: no speaker, no date, no recording yet) shows the
        # Current Session's speaker and date as its defaults; they are written when it is recorded
        # or something is typed in it (Josh, 24 October), not on merely opening and closing it.
        self._planned = (self.original is not None and not t.speaker and not t.collected and not t.file)
        speaker, date = ((self.main.session_speaker(), self.main.session_date()) if self._planned
                         else (t.speaker, t.collected))
        self._fill_speakers(speaker)
        self.date.blockSignals(True)
        self.date.setText(date)
        self.date.blockSignals(False)
        self._show_rerecord(t.rerecord)
        if self.comment is not None:
            self.push_btn.setEnabled(bool(self.comment.text().strip()))
            self.todo_btn.setEnabled(bool(self.comment.text().strip()))
        self.position.setText(self._position_text())
        self.back_btn.setEnabled(self.pos > 0)
        self.next_btn.setEnabled(self.pos < len(self.slots) - 1)
        self._refresh_name()
        self._update_suggestion()
        self._show_hypotheses()
        if getattr(self.main, "dialog_autoplay", False) and t.file:
            QTimer.singleShot(150, self._play)

    # ---- what differs for utterances (UtteranceDialog) ----------------
    def _new_token(self, sl: Slot) -> Token:
        return self.db.new_token(sl.entry, sl.tags, self.main.session_speaker(),
                                 self.main.session_date(), defaults=sl.defaults)

    def _show_header(self, e):
        self.header.setText(f"{e.ref}   {self.db.lemma(e)}   {meaning(self.db.gloss(e))}")

    def _position_text(self) -> str:
        sl, e = self.slot, self.slot.entry
        state = "new token" if self.original is None else f"token {sl.index + 1} of {len(e.tokens)}"
        return f"{self.pos + 1} / {len(self.slots)}  ·  {state}"

    def _tag_args(self) -> dict:
        """How the tag panel is built: for this lemma's word class."""
        return {"classes": self.db.classes(self.slot.entry)}

    def _folder(self) -> Path:
        return storage.sound_folder(self.db)

    def _fill_speakers(self, current: str):
        """The session's participants (and the token's own speaker, if someone else)."""
        self.speaker.blockSignals(True)
        self.speaker.clear()
        self.speaker.addItem("")
        for code in self.main.speaker_choices():
            self.speaker.addItem(code)
        if current and self.speaker.findText(current) < 0:
            self.speaker.addItem(current)
        self.speaker.setCurrentText(current)
        self.speaker.blockSignals(False)

    def _collect(self):
        """Copy the widgets into the working token."""
        s = self.db.settings
        t = self.token
        for name, ed in self.edits.items():
            f = s.token_field(name)
            text = ed.text().strip()
            if f.role == "pitch":
                text = pitchmod.normalise(text)       # tidies spacing
            if f.multilingual:
                t.set(name, text, s.primary_gloss)
            else:
                t.set(name, text)
        for (name, lang), ed in self.other_edits.items():
            t.set(name, ed.text().strip(), lang)
        t.tags = self.tag_combinations()[0]
        t.speaker = self.speaker.currentText()
        t.collected = self.date.text().strip()
        t.rerecord = self.rerecord_btn.isChecked()
        o = self.original
        if getattr(self, "_planned", False) and o is not None and not t.file \
                and t.values == o.values and t.multi == o.multi:
            t.speaker, t.collected = o.speaker, o.collected   # nothing collected yet: still blank

    def _fields_changed(self, *_):
        self._collect()
        self._refresh_name()

    def _tags_changed(self):
        self._fields_changed()
        self._update_unusual()
        self._update_combo_note()
        self._update_suggestion()

    # ---- several tokens at once (IDEAS.md idea 25, section 5.6) ------
    def tag_combinations(self) -> list[list[str]]:
        """The tag lists the picked tags make: one, or one per combination after Ctrl+click.

        The first is this token's own. An existing token keeps its tags in first place when
        they are one of the combinations (so editing it adds tokens around it)."""
        ts = self.db.settings.tags
        if self.tags.multi:
            combos = [ts.sort(c + self.unknown_tags) for c in self.tags.combinations()]
        else:
            combos = [ts.sort(self.tags.selected() + self.unknown_tags)]
        if self.original is not None and list(self.original.tags) in combos[1:]:
            own = list(self.original.tags)
            combos.remove(own)
            combos.insert(0, own)
        return combos

    def _update_combo_note(self):
        n = len(self.tag_combinations()) if self.tags.multi else 1
        if n > 1:
            more = (f" More than {self.MAX_TOKENS}: pick fewer tags." if n > self.MAX_TOKENS else "")
            self.combo_note.setText(f"→ {n} tokens, one for each combination." + more)
        self.combo_note.setVisible(n > 1)

    def _plan_extras(self, combos: list[list[str]]):
        """The combinations after the first: (to make, already in the database, so skipped)."""
        make, skipped = [], []
        for tags in combos[1:]:
            (skipped if self._clashes(tags) else make).append(tags)
        return make, skipped

    def _label(self, tags) -> str:
        return " + ".join(mx.chips(self.db, tags)) or "citation"

    def _confirm_extras(self, make: list, skipped: list):
        """Ask before making the extra tokens. None: Cancel; else whether to copy the fields."""
        n = 1 + len(make)
        lines = [f"{self._label(self.token.tags)}  (this token)"] + [self._label(t) for t in make]
        text = f"This makes {n} token{'s' if n != 1 else ''}:\n\n" + "\n".join("  " + x for x in lines)
        if skipped:
            text += ("\n\nAlready in the database, so skipped:\n"
                     + "\n".join("  " + self._label(t) for t in skipped))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Several tokens")
        box.setText(text)
        typed = bool(self.token.values or self.token.multi)
        check = None
        if make and typed:
            from PySide6.QtWidgets import QCheckBox
            check = QCheckBox("Copy what's typed here (Phonetic, Translation…) to the new tokens")
            check.setChecked(self.main.prefs.get_bool("token_dialog/copy_to_new_tokens", True))
            box.setCheckBox(check)
        if make:
            box.setInformativeText("The recording stays with this token; the new ones have none yet.")
        ok = box.addButton(f"Make {n} token{'s' if n != 1 else ''}", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        if box.clickedButton() is not ok:
            return None
        if check is not None:
            self.main.prefs.set_value("token_dialog/copy_to_new_tokens", check.isChecked())
            return check.isChecked()
        return False

    def _extra_token(self, tags, copy_fields: bool) -> Token:
        base = self.token
        if copy_fields:
            x = base.copy()
            x.id = new_id()
            x.file, x.rerecord, x.changed = "", False, {}
        else:
            x = Token(speaker=base.speaker, collected=base.collected)
        x.tags = list(tags)
        return x

    # ---- predicted translation ---------------------------------------
    def _update_suggestion(self):
        """Grey italic suggestion in the empty English translation; → accepts it (section 5.9)."""
        ed = self.translation
        if ed is None:
            return
        sug = None
        if not ed.text().strip():
            predictor = getattr(self.doc, "predictor", None)
            if predictor is not None:
                sug = predictor.suggest(self.db, self.slot.entry, self.token.tags)
        self.suggestion = sug
        show_suggestion(ed, sug.text if sug else "")
        ed.setToolTip(f"Suggestion: {sug.text}\n{sug.describe()}\nPress → to accept it, or type "
                      "something else." if sug else "")

    def accept_suggestion(self) -> bool:
        if self.translation is None or self.suggestion is None or self.translation.text():
            return False
        text = self.suggestion.text
        self.translation.setText(text)              # (this clears the suggestion)
        self.translation.setCursorPosition(len(text))
        return True

    def key_fields(self) -> list:
        """The fields where Ctrl+Space plays (and Ctrl+Shift+Space the pitch) instead of typing."""
        return [*self.edits.values(), *self.other_edits.values(), self.date]

    # ---- second languages (idea 19) ----------------------------------
    def _build_other_languages(self, grid, row: int) -> int:
        """The translations in the database's other gloss languages, under the token's fields:
        hidden behind "Other languages" until it's opened (remembered on this computer). They
        are there to help speakers understand (ɛλicit), not for the analysis."""
        s = self.db.settings
        self.other_edits: dict[tuple[str, str], QLineEdit] = {}
        self.other_rows: list = []
        self.others_btn = None
        others = [lang for lang in s.gloss_languages if lang != s.primary_gloss]
        fields = [f for f in s.token_fields if f.multilingual]
        if not others or not fields:
            return row
        self.others_btn = QToolButton()
        self.others_btn.setCheckable(True)
        self.others_btn.setAutoRaise(True)
        self.others_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.others_btn.setFocusPolicy(Qt.NoFocus)
        self.others_btn.setText(f"Other languages ({', '.join(others)})")
        self.others_btn.setToolTip("Translations in the database's other gloss languages: they help "
                                   "speakers understand (e.g. in ɛλicit requests)")
        self.others_btn.toggled.connect(self._show_other_languages)
        grid.addWidget(self.others_btn, row, 0, 1, 2, Qt.AlignLeft)
        row += 1
        for f in fields:
            for lang in others:
                label = QLabel(caption(f, f" ({lang})"))
                if getattr(f, "abbr", "") and label.text().startswith(f.abbr + " ("):
                    label.setToolTip(f"{f.title} ({lang})")
                ed = keyboards.tag(QLineEdit(), f"{f.name}:{lang}")
                ed.setFont(ipa_font(self.main.prefs.ipa_size + 1))
                ed.textChanged.connect(self._fields_changed)
                ed.installEventFilter(self)
                grid.addWidget(label, row, 0)
                grid.addWidget(ed, row, 1)
                self.other_edits[(f.name, lang)] = ed
                self.other_rows += [label, ed]
                row += 1
        shown = self.main.prefs.get_bool("dialogs/other_languages", False)
        self.others_btn.setChecked(shown)
        self._show_other_languages(shown, remember=False)
        return row

    def _show_other_languages(self, shown: bool, remember: bool = True):
        self.others_btn.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)
        for w in self.other_rows:
            w.setVisible(shown)
        if remember:
            self.main.prefs.set_value("dialogs/other_languages", bool(shown))

    def eventFilter(self, obj, event):
        # Ctrl+Space plays (Ctrl+Shift+Space: the pitch) even with the cursor in a field: on some
        # computers (keyboard layouts and IPA keyboards) the field would take it and type a space.
        if (event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and obj in self.key_fields()
                and event.key() == Qt.Key_Space
                and event.modifiers() & Qt.ControlModifier
                and not event.modifiers() & (Qt.AltModifier | Qt.MetaModifier)):
            if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
                (self._play_pitch if event.modifiers() & Qt.ShiftModifier else self._play)()
            event.accept()
            return True
        if (obj is self.translation and event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Right
                and not (event.modifiers() & ~Qt.KeypadModifier)
                and self.accept_suggestion()):
            return True
        return super().eventFilter(obj, event)

    def _build_tags(self, selected: set):
        hidden = self.tags.build(self.db, selected, show_all=self.show_all, **self._tag_args())
        b = self.show_all_btn
        b.blockSignals(True)
        b.setChecked(self.show_all)
        b.blockSignals(False)
        if self.show_all:
            b.setText("Show usual tags only")
            b.setVisible(True)
        else:
            b.setText(f"Show all tags ({hidden} more group{'s' if hidden != 1 else ''})")
            b.setVisible(hidden > 0)
        self._update_unusual()
        self._update_combo_note()

    def _show_all_toggled(self, on: bool):
        self.show_all = bool(on)
        self._collect()
        self._build_tags(set(self.token.tags))

    def _update_unusual(self):
        """The soft warning: tags that aren't usual for this lemma's word class."""
        if not self.main.prefs.warn_unusual_tags:
            self.unusual_note.hide()
            return
        notes = mx.unusual_notes(self.db, self.slot.entry, self.tags.selected())
        if not notes:
            self.unusual_note.hide()
            return
        colour = theme.colour("warning").name()
        text = "<br>".join(f"⚠ {_esc(n)}" for n in notes)
        self.unusual_note.setText(f"<span style='color:{colour}'>{text}</span> "
                                  "<a href='off'>Don't show this again</a>")
        self.unusual_note.setToolTip("Any tag can go on any token; this only says it's unusual. "
                                     "The warning can be turned back on in Settings → General.")
        self.unusual_note.show()

    def _stop_unusual_warning(self):
        self.main.set_unusual_warning(False)
        self.unusual_note.hide()
        self.tags.update()
        for b in self.tags.buttons.values():
            b.update()

    def _pitch_changed(self, text):
        self.canvas.set_pitch(text)
        s = self.db.settings
        self.pitch_note.setText(" ".join(pitchmod.problems(text, s.pitch_low, s.pitch_high)))

    def _expected(self) -> str:
        return self.db.expected_filename(self.slot.entry, self.token)

    def _path(self, name: str) -> Path:
        return self._folder() / name

    def _refresh_name(self):
        exp = self._expected()
        t = self.token
        self.filename.setText(exp)
        if t.file and t.file != exp:
            self.name_note.setText(f"Recorded as {t.file}: the file name is out of date.")
        elif t.file and not self._path(t.file).exists():
            self.name_note.setText(f"The recording {t.file} isn't in the sound folder.")
        else:
            self.name_note.setText("" if t.file else f"<span style='color:{theme.muted()}'>Not recorded yet.</span>")   # the theme's grey
        has_file = bool(t.file) and self._path(t.file).exists()
        self.play_btn.setEnabled(has_file)
        self.delete_btn.setEnabled(has_file)
        self.praat_btn.setEnabled(has_file)
        self.rec_panel.snip_btn.setEnabled(has_file)
        folder = self._folder()
        shown = folder / (t.file if has_file else exp)
        self.location.setText(("" if has_file else "Will be saved as ")
                              + QDir.toNativeSeparators(str(shown))
                              + ("   (online only: needs internet to play)"
                                 if has_file and storage.is_cloud_only(shown) else ""))
        self.update_btn.setEnabled(bool(t.file) and t.file != exp and has_file
                                   and not self.db.settings.auto_update_names)
        if self.db.settings.auto_update_names and t.file and t.file != exp:
            self.name_note.setText(self.name_note.text() + " It will be renamed when you leave this token.")

    def _source_changed(self, *_):
        self.rec_panel.source_changed()

    # ---------------------------------------------------------- committing
    PITCH_LIKE = re.compile(r"^(?=.*\d)[\d\s:,\u02d0]+$")

    def check_pitch_like(self) -> bool:
        """Phonetic or Phonemic holding only digits and colons asks whether it was meant for
        Pitch (Josh, 21 October), with Move it to Pitch. False: back to the dialogue."""
        s = self.db.settings
        if not self.pitch_shown():
            return True                           # no warning while the pitch system is hidden (idea 9)
        pitch_ed = next((ed for n, ed in self.edits.items() if s.token_field(n).role == "pitch"), None)
        for name, ed in self.edits.items():
            f = s.token_field(name)
            text = ed.text().strip()
            if f.role not in ("phonetic", "phonemic") or not self.PITCH_LIKE.match(text):
                continue
            box = QMessageBox(QMessageBox.Question, "Pitch?",
                              f"{f.title} holds “{text}”.\n\nDid you mean to put that in the Pitch field?",
                              parent=self)
            move = box.addButton("Move it to Pitch", QMessageBox.AcceptRole) if pitch_ed else None
            box.addButton(f"Keep it in {f.title}", QMessageBox.DestructiveRole)
            cancel = box.addButton(QMessageBox.Cancel)
            if pitch_ed and pitch_ed.text().strip():
                box.setInformativeText(f"Pitch already has “{pitch_ed.text().strip()}”: "
                                       "moving replaces it.")
            box.setDefaultButton(move or cancel)
            box.exec()
            if box.clickedButton() is cancel:
                ed.setFocus()
                return False
            if move is not None and box.clickedButton() is move:
                pitch_ed.setText(text)
                ed.setText("")
        return True

    def _commit(self, keep_empty: bool = False, check_clash: bool = True, extras: bool = False) -> bool:
        """Save the working token into the entry (with undo). Returns False on a problem.

        extras: leaving the token (OK, Back, Next), so tags picked with Ctrl+click also make
        a token for each further combination, in the same undo step. Saves on the way
        (recording, Push to question…) keep only the first combination for now."""
        if extras and not self.check_pitch_like():
            return False
        self._collect()
        e = self.slot.entry
        t = self.token
        combos = self.tag_combinations() if extras else [list(t.tags)]
        new_tokens: list[Token] = []
        if len(combos) > 1:
            if len(combos) > self.MAX_TOKENS:
                QMessageBox.warning(self, "Several tokens", f"These tags make {len(combos)} tokens; "
                                    f"at most {self.MAX_TOKENS} can be made at once. Pick fewer tags.")
                return False
            problems = []
            for c in combos:
                problems += [p for p in self.db.settings.tags.conflicts(
                    [x for x in c if x not in self.unknown_tags]) if p not in problems]
            if problems:
                QMessageBox.warning(self, "Tags", "\n".join(problems))
                return False
            keep_empty = True                     # tokens picked on purpose, typed or not
        saving = (t.has_content() or keep_empty or self.slot.explicit) if self.original is None \
            else self.original != t
        # A new token, or one whose tags changed, may not take a name another token's recording
        # has (two soundfiles of one name, Josh 21 October): add an Example tag, or go back and
        # change the tags. A clash it already had (converted data) doesn't stop other edits.
        retagged = self.original is None or list(self.original.tags) != list(t.tags)
        if check_clash and saving and retagged and self._clashes():
            # The same configuration as a token this lemma already has (Josh, 24 October): switch
            # to it, add an Example tag, or overwrite it. Another lemma's file name (rare) and
            # several combinations at once keep the plain Example offer.
            e0, other = self._clashes()[0]
            if e0 is self.slot.entry and len(combos) == 1:
                done = self._resolve_duplicate(other)
                if done is not None:
                    return done                   # switched (False: stay open) or overwritten (True)
            elif not self._offer_example(recording=False):
                return False                      # Cancel: back to the dialogue, nothing saved
            self._collect()
            t = self.token
        if len(combos) > 1:
            make, skipped = self._plan_extras(combos)
            copy_fields = self._confirm_extras(make, skipped)
            if copy_fields is None:
                return False                      # Cancel: back to the dialogue, nothing saved
            new_tokens = [self._extra_token(c, copy_fields) for c in make]
        problems = self.db.settings.tags.conflicts([x for x in t.tags if x not in self.unknown_tags])
        if problems:
            QMessageBox.warning(self, "Tags", "\n".join(problems))
            return False
        # Rename the recording if its name is out of date and renaming is automatic.
        if self.db.settings.auto_update_names and t.file and t.file != self._expected():
            self._rename_file()
        if self.original is None:
            if not (t.has_content() or keep_empty or self.slot.explicit):
                return True                       # passing through an empty cell
            token = t.copy()
            renames, self._renames = self._renames, []

            def add(en, token=token, more=new_tokens):
                for x in (token, *more):
                    en.add_token(x)
            n = 1 + len(new_tokens)
            self.doc.edit_entry(e, add, f"Add {n} tokens to {e.ref}" if n > 1 else f"Add token to {e.ref}",
                                renames=renames)
            self.slot.index = len(e.tokens) - 1 - len(new_tokens)
            self.original = e.tokens[self.slot.index]
        elif self.original != t or new_tokens:
            idx = self.slot.index
            token = t.copy()

            def change(en, idx=idx, token=token, more=new_tokens):
                en.tokens[idx] = token
                en.tokens.extend(more)
            renames, self._renames = self._renames, []
            label = f"Edit token and add {len(new_tokens)} in {e.ref}" if new_tokens else f"Edit token in {e.ref}"
            self.doc.edit_entry(e, change, label, renames=renames)
            self.original = e.tokens[idx]
        self.token = self.original.copy()
        if len(combos) > 1:                       # made: the picks go back to this token's own
            self._build_tags(set(self.token.tags))
        return True

    # ------------------------------------------------ recordings sharing a name
    def _clashes(self, tags=None) -> list:
        """Other tokens whose recording has, or would have, this token's file name."""
        t = self.token
        probe = t.copy()
        if tags is not None:
            probe.tags = list(tags)
        name = self.db.expected_filename(self.slot.entry, probe).lower()
        out = []
        for e in self.db.entries:
            for o in e.tokens:
                if o.id == t.id or (self.original is not None and o is self.original):
                    continue
                if (o.file and o.file.lower() == name) or \
                        (e is self.slot.entry and self.db.expected_filename(e, o).lower() == name):
                    out.append((e, o))
        return out

    def _free_example(self) -> str:
        """The first Example tag that gives this token a file name of its own, or the name a new
        one would have. Nothing is added here: the tag (and its group, in an older structure) is
        added only when the researcher chooses Add (_ensure_example). It used to be added before
        the question, so Cancel left a new tag behind and the database unsaved (the audit, 25 October)."""
        from ..defaults import EXAMPLES
        ts = self.db.settings.tags
        group = next((g for _, g in ts.leaf_groups() if g.name.lower() == EXAMPLES.lower()), None)
        tags = group.tags if group is not None else []
        mine = {x.name for x in tags}
        base = [x for x in self.token.tags if x not in mine]
        for tag in tags:
            if not self._clashes(base + [tag.name]):
                return tag.name
        names, codes = {x.name for x, _ in ts.tags()}, {x.code.lower() for x, _ in ts.tags()}
        n = len(tags) + 1
        while f"Example {n}" in names or f"x{n}" in codes or self._clashes(base + [f"Example {n}"]):
            n += 1
        return f"Example {n}"

    def _example_chip(self, tag: str) -> str:
        """How an Example tag is shown (its code, x3), whether it exists yet or not."""
        found = self.db.settings.tags.find(tag)
        if found:
            return found[0].display()
        from ..model import Tag
        return Tag(tag, "x" + tag.rsplit(" ", 1)[-1]).display()

    def _ensure_example(self, tag: str):
        """Add the Example tag (and the Instances › Examples groups if missing), once chosen."""
        from ..defaults import EXAMPLES, INSTANCES
        from ..model import Group, Tag
        ts = self.db.settings.tags
        if ts.find(tag):
            return
        group = next((g for _, g in ts.leaf_groups() if g.name.lower() == EXAMPLES.lower()), None)
        if group is None:                         # an older structure without it: add it
            top = next((g for g in ts.groups if g.name.lower() == INSTANCES.lower()), None)
            if top is None:
                top = Group(INSTANCES)
                ts.groups.append(top)
            group = Group(EXAMPLES)
            top.groups.append(group)
        group.tags.append(Tag(tag, "x" + tag.rsplit(" ", 1)[-1]))
        self.doc.settings_changed()

    def _offer_example(self, recording: bool) -> bool:
        """Two recordings would share a name: offer a free Example tag. True if one was added."""
        others = self._clashes()
        e, o = others[0]
        name = self._expected()
        what = " + ".join(mx.chips(self.db, o.tags)) or "citation"
        tag = self._free_example()
        code = self._example_chip(tag)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Same recording name")
        who = "This lemma already has" if e is self.slot.entry else f"{e.ref} already has"
        box.setText(f"{who} a token with this file name ({what}): {name}\n\n"
                    f"Add the example tag {code} to this token, so its recording gets a name of its own?")
        if not recording:
            box.setInformativeText("Or Cancel and change the tags.")
        add = box.addButton(f"Add {code}" + (" and record" if recording else ""), QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(add)
        box.exec()
        if box.clickedButton() is not add:
            return False
        self._apply_example(tag)
        return True

    def _apply_example(self, tag: str):
        """Give the working token this Example tag in place of any other Example tag."""
        self._ensure_example(tag)
        mine = {x.name for _, g in self.db.settings.tags.leaf_groups()
                if g.name.lower() == "examples" for x in g.tags}
        tags = [x for x in self.token.tags if x not in mine] + [tag]
        self.token.tags = self.db.settings.tags.sort(tags)
        self._build_tags(set(self.token.tags))
        self._fields_changed()

    # ------------------------------------- the same configuration (Josh, 24 October)
    def _core_found(self, o: Token) -> list[tuple[str, bool]]:
        """The core token fields holding data in a token: (title, bold), Phonemic in bold."""
        s = self.db.settings
        out = []
        for f in s.token_fields:
            if not f.builtin or (f.role == "pitch" and not self.pitch_shown()):
                continue
            has = any(v for v in o.multi.get(f.name, {}).values()) if f.multilingual else bool(o.values.get(f.name))
            if has:
                out.append((f.title, f.role == "phonemic"))
        return out

    def _ask_duplicate(self, o: Token, chip: str) -> str:
        from .duplicate_token import DuplicateBox
        box = DuplicateBox(self, self._core_found(o), chip)
        box.exec()
        return box.choice

    def _ask_soundfile(self, mine: Path, theirs: Path) -> str | None:
        """Two soundfiles: 'mine', 'theirs', or None (Cancel)."""
        from .duplicate_token import SoundfileBox
        box = SoundfileBox(self, mine, theirs, lambda p: self.main.player.play([p]))
        box.exec()
        self.main.player.stop()
        return box.keep

    def _confirm_overwrite(self, what: str) -> bool:
        from .duplicate_token import OverwriteBox
        return OverwriteBox(self, what).exec() == QDialog.Accepted

    def _resolve_duplicate(self, o: Token):
        """The box: True when overwritten (the dialogue goes on as after a save), False when
        switched or cancelled (the dialogue stays open), None when Add was chosen (the Example tag
        is on the token and saving carries on as before)."""
        from .duplicate_token import DuplicateBox
        tag = self._free_example()
        chip = self._example_chip(tag)
        while True:
            choice = self._ask_duplicate(o, chip)
            if choice == DuplicateBox.ADD:
                self._apply_example(tag)
                return None
            if choice not in (DuplicateBox.SWITCH, DuplicateBox.OVERWRITE):
                return False                      # Cancel: back to the dialogue, nothing saved
            done = self._merge_into(o, overwrite=choice == DuplicateBox.OVERWRITE)
            if done is not None:
                return done                       # else a Cancel further on: back to the box

    def _merge_into(self, o: Token, overwrite: bool):
        """Put the working token's data into the existing token o (one undo step).

        Switch (overwrite False): only o's empty fields are filled. Overwrite: every field typed
        here replaces o's; an empty field here never erases anything. With a soundfile on both,
        the researcher picks the one to keep (the other is held with the deleted recordings, so
        Undo brings it back); the speaker and date go with the soundfile kept. A token being edited
        (not new) is removed once its data is in o. Returns True (overwritten), False (switched)
        or None (a Cancel on the way: nothing changed)."""
        self._collect()
        e, t, s = self.slot.entry, self.token, self.db.settings
        merged = o.copy()
        overwritten: list[str] = []
        for f in s.token_fields:
            if f.multilingual:
                mine, theirs = t.multi.get(f.name, {}), merged.multi.setdefault(f.name, {})
                for lang, text in mine.items():
                    if text and (overwrite or not theirs.get(lang)):
                        if theirs.get(lang) and theirs[lang] != text:
                            overwritten.append(f.title)
                        theirs[lang] = text
                if not theirs:
                    merged.multi.pop(f.name, None)
            else:
                text = t.values.get(f.name, "")
                if text and (overwrite or not merged.values.get(f.name)):
                    if merged.values.get(f.name) and merged.values[f.name] != text:
                        overwritten.append(f.title)
                    merged.values[f.name] = text
        overwritten = list(dict.fromkeys(overwritten))
        here = t.file and self._path(t.file).exists()
        there = o.file and self._path(o.file).exists()
        keep = "mine" if here else "theirs"
        if here and there and not storage.same_file(self._path(t.file), self._path(o.file)):
            keep = self._ask_soundfile(self._path(t.file), self._path(o.file))
            if keep is None:
                return None
        if overwrite and (overwritten or (here and there and keep == "mine")):
            what = list(overwritten) + (["the soundfile"] if here and there and keep == "mine" else [])
            from .duplicate_token import join
            if not self._confirm_overwrite(join(what)):
                return None
        # the speaker and date (and the rerecord flag) go with the soundfile kept
        if keep == "mine" and here:
            merged.speaker, merged.collected, merged.rerecord = t.speaker, t.collected, t.rerecord
        elif not there and not here:
            if t.speaker and (overwrite or not merged.speaker):
                merged.speaker = t.speaker
            if t.collected and (overwrite or not merged.collected):
                merged.collected = t.collected
        renames = list(self._renames)
        self._renames = []
        base = len(renames)
        try:
            if keep == "mine" and here:
                name = self.db.expected_filename(e, merged)
                if there:
                    src = self._path(o.file)
                    held = self.doc.hold_recording(src)
                    src.rename(held)
                    renames.append((src, held))
                src, dst = self._path(t.file), self._path(name)
                if src != dst:
                    src.rename(dst)
                    renames.append((src, dst))
                merged.file = name
            elif here:                            # theirs kept: this token's recording put aside
                src = self._path(t.file)
                held = self.doc.hold_recording(src)
                src.rename(held)
                renames.append((src, held))
        except OSError as exc:
            for a, b in reversed(renames[base:]):
                try:
                    Path(b).rename(a)
                except OSError:
                    pass
            self._renames = renames[:base]
            QMessageBox.warning(self, "Soundfile", f"Couldn't move the soundfile: {exc}")
            return None
        oi = e.tokens.index(o)
        ci = self.slot.index if self.original is not None else None

        def change(en, oi=oi, ci=ci, merged=merged):
            en.tokens[oi] = merged
            if ci is not None:
                del en.tokens[ci]
        label = f"Overwrite token in {e.ref}" if overwrite else f"Edit token in {e.ref}"
        self.doc.edit_entry(e, change, label, renames=renames)
        new_index = oi - (1 if ci is not None and ci < oi else 0)
        if ci is not None:                        # Back and Next: the slots after it moved up
            for sl in self.slots:
                if sl is not self.slot and sl.entry is e and sl.index is not None and sl.index > ci:
                    sl.index -= 1
        self.slot.index = new_index
        self._load()
        return overwrite

    def _rename_file(self) -> bool:
        t = self.token
        exp = self._expected()
        src, dst = self._path(t.file), self._path(exp)
        if not src.exists():
            return False
        if dst.exists() and not storage.same_file(src, dst):     # a case-only rename is fine
            QMessageBox.warning(self, "File name", f"Can't rename {t.file}: a file called {exp} "
                                "already exists. Check for duplicate tokens.")
            return False
        try:
            src.rename(dst)
        except OSError as exc:
            QMessageBox.warning(self, "File name", f"Couldn't rename {t.file}: {exc}")
            return False
        self._renames.append((src, dst))
        t.file = exp
        return True

    def focusNextPrevChild(self, forward: bool) -> bool:
        """Tab and Shift+Tab go round the token's fields only (tags and buttons are for the mouse)."""
        fields = [e for e in (*self.edits.values(), *self.other_edits.values()) if e.isVisible() and e.isEnabled()]
        current = self.focusWidget()
        if current in fields:
            i = (fields.index(current) + (1 if forward else -1)) % len(fields)
            fields[i].setFocus(Qt.TabFocusReason)
            fields[i].selectAll()
            return True
        return super().focusNextPrevChild(forward)

    def _move(self, step: int):
        if self.recorder:
            self._stop_recording()
        target = self.pos + step
        if not 0 <= target < len(self.slots):
            return
        if not self._commit(extras=True):
            return
        self.main.player.stop()
        self.pos = target
        self._load()

    def _ok(self):
        if self.recorder:
            self._stop_recording()
        if self._commit(keep_empty=self.slot.explicit, extras=True):
            self.main.player.stop()
            self.accept()

    def done(self, result):
        """However the dialogue closes (OK, Cancel, Esc, the window's X), its size is remembered."""
        self.main.prefs.set_value("window/token_dialog", self.saveGeometry())
        super().done(result)

    def reject(self):
        self.rec_panel.cancel()                   # a take in progress is thrown away
        self.main.player.stop()
        super().reject()

    # ----------------------------------------------------------- recording
    def _record(self):
        if self.recorder:
            self._stop_recording()
            return
        self._collect()
        clashes = self._clashes()
        if clashes:
            # the same box as saving (Josh, 24 October): switch, add an Example tag, overwrite.
            # Switched or overwritten, the dialogue shows that token and records onto it (its own
            # recording is asked about below, as always); Cancel records nothing.
            e0, other = clashes[0]
            if e0 is self.slot.entry and len(self.tag_combinations()) == 1:
                self._resolve_duplicate(other)
                if self._clashes():
                    return                        # Cancel: nothing recorded
                self._collect()
            elif not self._offer_example(recording=True):
                return                            # never record over another token's recording
        exp = self._expected()
        own = [p for p in {self.token.file, exp} if p and self._path(p).exists()]
        if own:
            if self.token.file in own:            # this token's own: 🔥 hot mic records straight over it
                from .recording_panel import ask_record_over
                if not ask_record_over(self, "Replace this token's recording?", "Record over it"):
                    return
            elif not _w.ask(self, "Record", f"A file called {exp} is already in the sound folder, though no "
                            "token uses it. Replace it? (It goes to the Recycle Bin.)", "Replace it"):
                return                            # a stray file of that name always asks
        self.rec_panel.start()

    def _stop_recording(self):
        take = self.rec_panel.stop()
        if take is None:
            return
        samples, rate = take
        self.rec_panel.show_level(samples)           # clipped or very quiet: said, never changed
        samples, untrimmed = self.rec_panel.auto_snip(samples, rate)   # ✂ auto-snip (idea 10)
        self._collect()
        t = self.token
        # Whoever is the session's speaker now (perhaps no one) is the token's speaker;
        # the date is the session's.
        speaker, date = self.main.session_speaker(), self.main.session_date()
        t.speaker = speaker
        if date:
            t.collected = date
        self._fill_speakers(t.speaker)
        self.date.blockSignals(True)
        self.date.setText(t.collected)
        self.date.blockSignals(False)
        exp = self._expected()
        if self._clashes():                       # the tags changed while recording: still never overwrite
            QMessageBox.warning(self, "Record", f"{exp} belongs to another token, so this recording "
                                "wasn't saved. Give this token an Example tag and record again.")
            return
        old = t.file
        if self._path(exp).exists():              # the recording being replaced: to the Recycle Bin
            QFile.moveToTrash(str(self._path(exp)))
        try:
            audio.write_wav(self._path(exp), samples, rate, self.main.prefs.bit_depth,
                            artist=t.speaker, date=t.collected)
        except (OSError, audio.AudioError) as exc:
            QMessageBox.warning(self, "Record", f"Couldn't save the recording: {exc}")
            return
        if untrimmed is not None:                 # the take as recorded: held, never in the way
            from .autosnip import hold_untrimmed
            hold_untrimmed(self.main, self._path(exp), untrimmed, rate, t.speaker, t.collected)
        if old and old != exp and self._path(old).exists():
            QFile.moveToTrash(str(self._path(old)))
        t.file = exp
        t.rerecord = False                        # recorded again: the flag goes
        self._show_rerecord(False)
        self._commit(keep_empty=True)
        self._refresh_name()

    def _proselytize(self):
        """The ✂ button: snip this soundfile once (made outside Lemmatrix, or before auto-snip)."""
        t = self.token
        if self.recorder or not t.file or not self._path(t.file).exists():
            return
        from .autosnip import proselytize
        if proselytize(self.main, self, self._path(t.file), self.SNIP_GAPS):
            self._refresh_name()

    # ------------------------------------------------------- rerecord flag
    def _show_rerecord(self, on: bool):
        b = self.rerecord_btn
        b.blockSignals(True)
        b.setChecked(on)
        b.blockSignals(False)
        faint = "#55575b" if theme.dark() else "#d6d6d6"        # very subtle until it's on
        b.setIcon(icon("thumbs-down", 36, "#e02424" if on else faint))
        b.setToolTip("Marked to be recorded again: click to unmark. Recording over it unmarks it."
                     if on else "Mark the recording to be recorded again (Rerecord in All data's "
                     "Soundfile filter)")

    def _rerecord_toggled(self, on: bool):
        self._show_rerecord(on)
        self._fields_changed()

    # --------------------------------------------------- push to question
    def push_to_todo(self):
        """Push to To Do: as Push to question, into the day's To Do list."""
        from .. import notebook as nbmod
        self.push_to_question(nbmod.TODO)

    def push_to_question(self, kind: str = "question"):
        """The comment becomes an open question (or to do) in the session's notebook, linked to this token."""
        if self.comment is None or not self.comment.text().strip():
            return
        text = self.comment.text().strip()
        main = self.main
        if self.original is None:                 # a new token: it exists now, so the link works
            # saved without the comment: it goes to the notebook, not into the token (it stayed in
            # the token if the dialogue was then cancelled: the audit, 25 October)
            self.comment.clear()
            self._collect()
            if not self._commit(keep_empty=True):
                self.comment.setText(text)
                return
        date = main.work_date()
        keys = main.session_keys()
        from .. import notebook as nbmod
        from . import chiprow as chips
        nbmod.push_question(self.doc.notebook, self.db, date, text, self.slot.entry, self.token,
                            keys[chips.RESEARCHERS], keys[chips.PARTICIPANTS], keys[chips.LOCATIONS], kind)
        self.doc.notebook_changed()
        from .notebook_dialog import refresh_notebook
        refresh_notebook(main)
        self.comment.clear()
        from PySide6.QtWidgets import QToolTip
        b = self.todo_btn if kind == nbmod.TODO else self.push_btn
        QToolTip.showText(b.mapToGlobal(b.rect().bottomLeft()),
                          f"Added to the {nbmod.name(kind, True, title=False)} of {date}", b)

    # --------------------------------------------------- Cogitate (hypotheses)
    def _show_hypotheses(self):
        """The hypotheses this token (or utterance) is in, worked out from the notebook."""
        from .. import hypotheses as hy
        from ..model import is_utterance
        try:
            lbl = self.hyp_line
            lbl.isVisible()
        except (AttributeError, RuntimeError):    # the dialogue has gone
            return
        e, t = self.slot.entry, self.token
        found = []
        if t is not None and self.original is not None:
            kind = hy.UTTERANCE if is_utterance(e) else hy.TOKEN
            found = hy.linked_to_item(self.doc.notebook, kind, e.id, t.id)
        a = theme.colour("pitch").name()
        links = ", ".join(f"<a href='h:{h.id}' style='color:{a}'>{h.label}</a> ({ln.mark})" for h, ln in found)
        lbl.setText(f"In hypotheses: {links}" if links else "")
        lbl.setToolTip("\n".join(h.title(80) for h, _ in found))
        self._hyp_icon()

    def _hyp_icon(self):
        """The Cogitate button's icon, its teal in the theme colour (lighter on dark)."""
        try:
            self.hyp_btn.setIcon(icon("cogitate", 48, theme.colour("pitch").name()))
        except (AttributeError, RuntimeError):
            pass

    def _hypothesis_link(self, href: str):
        if href.startswith("h:"):
            self.main.open_cogitate(href[2:])
        elif href == "link":
            self.link_to_hypothesis()

    def link_to_hypothesis(self):
        """Link to hypothesis… from the dialogue (a new token is saved first, so the link works)."""
        from .. import hypotheses as hy
        if self.original is None:
            self._collect()
            if not self._commit(keep_empty=True):
                return None
        h = self.main.link_to_hypothesis(hy.token_link(self.db, self.slot.entry, self.token), self)
        self._show_hypotheses()
        return h

    def _play(self):
        if self.recorder:
            return
        t = self.token
        if not t.file:
            return
        try:
            self.main.player.play([self._path(t.file)])
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play", str(exc))

    def _play_pitch(self):
        if self.recorder or not self.pitch_shown():
            return
        self.main.play_pitch(self.canvas.text)

    def _praat_key(self):
        """Ctrl+Alt+Space: Open in Praat, when the button would (a recording to open)."""
        if self.praat_btn.isEnabled():
            self._open_in_praat()

    def _open_in_praat(self):
        t = self.token
        path = self._path(t.file) if t.file and self._path(t.file).exists() else None
        self.main.open_in_praat(path, self)

    def _canvas_menu(self, pos):
        m = QMenu(self)
        a = m.addAction(icon("play-pitch", 16), "Play pitch")
        a.setEnabled(bool(pitchmod.parse(self.canvas.text)))
        a.triggered.connect(lambda *_: self._play_pitch())
        m.exec(self.canvas.mapToGlobal(pos))

    def _recording_menu(self, global_pos):
        m = QMenu(self)
        for text, name, fn, on in (
                ("Stop recording" if self.recorder else "Record", "stop" if self.recorder else "record",
                 self._record, True),
                ("Play", "play", self._play, self.play_btn.isEnabled()),
                ("Open in Praat", "praat", self._open_in_praat, self.praat_btn.isEnabled()),
                ("Delete recording", "delete-recording", self._delete_recording, self.delete_btn.isEnabled()),
                ("Update file name", "update", self._update_name, self.update_btn.isEnabled())):
            a = m.addAction(icon(name, 16), text)
            a.setEnabled(on)
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.addSeparator()
        a = m.addAction(icon("cogitate", 16, theme.colour("pitch").name()), "Link to hypothesis…")
        a.triggered.connect(lambda *_: self.link_to_hypothesis())
        m.exec(global_pos)

    def _delete_recording(self):
        t = self.token
        if not t.file:
            return
        if self.main.prefs.confirm_delete:
            if not _w.ask(self, "Delete recording",
                                    f"Delete {t.file}? It will go to the Recycle Bin.", "Delete recording"):
                return
        self.main.player.stop()
        path = self._path(t.file)
        if path.exists() and not QFile.moveToTrash(str(path)):
            QMessageBox.warning(self, "Delete recording", f"Couldn't move {t.file} to the Recycle Bin.")
            return
        t.file = ""
        self._commit(keep_empty=True)
        self._refresh_name()

    def _update_name(self):
        if self._rename_file():
            self._commit(keep_empty=True)
            self._refresh_name()
