"""The token dialogue: fields, tags and recording, with Back and Next."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QDir, QEvent, QRegularExpression, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QRegularExpressionValidator, QShortcut, QValidator
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)
from PySide6.QtCore import QFile

from .. import audio, matrix as mx, pitch as pitchmod, predict, storage
from ..model import Entry, Token
from PySide6.QtCore import QSize

from . import spellui, theme
from .icons import icon
from .table import show_suggestion
from .tagpanel import TagPanel
from .widgets import PitchCanvas, ipa_font


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


class TokenDialog(QDialog):
    def __init__(self, main, slots: list[Slot], index: int, parent=None):
        super().__init__(parent or main)
        self.main = main
        self.doc = main.doc
        self.db = main.doc.db
        self.slots = slots
        self.pos = index
        self.token: Token | None = None
        self.original: Token | None = None
        self.recorder: audio.Recorder | None = None
        self._renames: list = []                  # recordings renamed, to go with the next commit
        self._clash_asked: set[str] = set()       # tokens already offered an Example tag on saving
        self.unknown_tags: list[str] = []
        self.suggestion: predict.Suggestion | None = None   # the predicted translation shown, if any
        self.setWindowTitle("Edit Token")
        self.resize(920, 780)
        self._build()
        g = self.main.prefs.get_bytes("window/token_dialog")
        if g:                                     # the size and place it had when last closed
            self.restoreGeometry(g)
        self._load()

    # ------------------------------------------------------------------ UI
    def _build(self):
        s = self.db.settings
        outer = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setFont(ipa_font(15))
        self.header.setStyleSheet("font-weight: 600; padding: 2px 0 6px 0;")
        outer.addWidget(self.header)

        top = QHBoxLayout()
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
                                   "Edit → Settings → Pitch")
        self.pitch_play.clicked.connect(lambda *_: self._play_pitch())
        drawing = QHBoxLayout()                 # the drawing, with its play button beside it
        drawing.setContentsMargins(0, 0, 0, 0)
        drawing.addWidget(self.canvas, 1)
        drawing.addWidget(self.pitch_play, 0, Qt.AlignVCenter)
        left.addWidget(QLabel("Pitch\nRendering"), 1, 0, Qt.AlignVCenter)
        left.addLayout(drawing, 1, 1)
        self.edits: dict[str, QLineEdit] = {}
        self.translation: QLineEdit | None = None      # the English translation: gets suggestions
        self.comment: QLineEdit | None = None          # the first comment field: Push to question
        row = 2
        for f in s.token_fields:
            ed = QLineEdit()
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
                ed.installEventFilter(self)
                spellui.attach(ed, getattr(self.main, "speller", None))   # red lines under unknown words
                ed.textChanged.connect(lambda *_: self._update_suggestion())
            label = f.title + (f" ({s.primary_gloss})" if f.multilingual and len(s.gloss_languages) > 1 else "")
            left.addWidget(QLabel(label), row, 0)
            if self.comment is None and f.is_comment:
                self.comment = ed
                self.push_btn = QToolButton()
                self.push_btn.setIcon(icon("push-question", 22))
                self.push_btn.setIconSize(QSize(22, 22))
                self.push_btn.setAutoRaise(True)
                self.push_btn.setToolTip("Push to question: the comment becomes an open question in the "
                                         "session's notebook, linked to this token, and the box is cleared")
                self.push_btn.clicked.connect(lambda *_: self.push_to_question())
                ed.textChanged.connect(lambda text: self.push_btn.setEnabled(bool(text.strip())))
                box = QHBoxLayout()               # the box, with the button beside it
                box.setContentsMargins(0, 0, 0, 0)
                box.addWidget(ed, 1)
                box.addWidget(self.push_btn, 0, Qt.AlignVCenter)
                left.addLayout(box, row, 1)
            else:
                left.addWidget(ed, row, 1)
            self.edits[f.name] = ed
            row += 1
        self.pitch_note = QLabel()
        self.pitch_note.setStyleSheet(f"color: {theme.colour('warning').name()};")
        left.addWidget(self.pitch_note, row, 1)
        left.setRowStretch(row + 1, 1)
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
        top.addWidget(tags_box, 2)

        rec = QGroupBox()
        rl = QGridLayout(rec)
        self.filename = QLabel()
        ff = self.filename.font()
        ff.setPointSize(ff.pointSize() + 3)
        self.filename.setFont(ff)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.filename, 0, 0, 1, 4)
        self.rerecord_btn = QToolButton()        # the rerecord flag: faint grey, red when on
        self.rerecord_btn.setCheckable(True)
        self.rerecord_btn.setAutoRaise(True)
        self.rerecord_btn.setIconSize(QSize(36, 36))
        self.rerecord_btn.setCursor(Qt.PointingHandCursor)
        self.rerecord_btn.setStyleSheet("QToolButton, QToolButton:checked, QToolButton:hover "
                                        "{ border: none; background: transparent; }")
        self.rerecord_btn.toggled.connect(self._rerecord_toggled)
        rl.addWidget(self.rerecord_btn, 0, 4, Qt.AlignRight | Qt.AlignTop)
        self.location = QLabel()
        self.location.setStyleSheet(f"color: {theme.muted()};")
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location.setWordWrap(True)
        rl.addWidget(self.location, 1, 0, 1, 5)
        self.name_note = QLabel()
        self.name_note.setStyleSheet(f"color: {theme.colour('error').name()};")
        rl.addWidget(self.name_note, 2, 0, 1, 5)
        rl.addWidget(QLabel("Speaker"), 3, 3, Qt.AlignRight)
        self.speaker = QComboBox()
        self.speaker.setToolTip("The token's speaker. Choosing one makes them the speaker of the "
                                "next recordings too, until another is chosen.")
        self.speaker.currentTextChanged.connect(self._fields_changed)
        self.speaker.activated.connect(lambda _: self.main.set_speaker(self.speaker.currentText()))
        self.speaker.setFixedWidth(130)
        rl.addWidget(self.speaker, 3, 4)
        rl.addWidget(QLabel("Date"), 4, 3, Qt.AlignRight)
        self.date = QLineEdit()
        self.date.setPlaceholderText("YYYY-MM-DD")
        self.date.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"(\d{4}-\d{2}-\d{2})?"), self.date))
        self.date.textChanged.connect(self._fields_changed)
        self.date.setFixedWidth(130)
        rl.addWidget(self.date, 4, 4)

        buttons = QHBoxLayout()
        def icon_button(name, tip):
            b = QPushButton()
            b.setIcon(icon(name, 40))
            b.setIconSize(QSize(40, 40))
            b.setFixedSize(48, 48)
            b.setFlat(True)
            b.setToolTip(tip)
            b.setStyleSheet("QPushButton { border: none; }")
            buttons.addWidget(b)
            return b
        self.record_btn = icon_button("record", "Record (Ctrl+R)")
        self.play_btn = icon_button("play", "Play (Ctrl+Space)")
        self.delete_btn = icon_button("delete-recording", "Delete recording")
        self.update_btn = icon_button("update", "Update file name")
        self.praat_btn = icon_button("praat", "Open in Praat")
        buttons.addStretch(1)
        self.record_btn.clicked.connect(self._record)
        self.play_btn.clicked.connect(self._play)
        self.delete_btn.clicked.connect(self._delete_recording)
        self.update_btn.clicked.connect(self._update_name)
        self.praat_btn.clicked.connect(lambda *_: self._open_in_praat())
        rl.addLayout(buttons, 3, 0, 2, 2)
        rec.setContextMenuPolicy(Qt.CustomContextMenu)
        rec.customContextMenuRequested.connect(lambda pos, rec=rec: self._recording_menu(rec.mapToGlobal(pos)))
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setMaximumHeight(10)
        self.meter.setToolTip("Recording level")
        self.meter.setFixedWidth(220)
        rl.addWidget(self.meter, 5, 0, 1, 2)
        rl.setColumnStretch(2, 1)
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
        QShortcut(QKeySequence("Alt+Left"), self, lambda: self._move(-1))
        QShortcut(QKeySequence("Alt+Right"), self, lambda: self._move(1))

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_meter)

    # ---------------------------------------------------------------- data
    @property
    def slot(self) -> Slot:
        return self.slots[self.pos]

    def _load(self):
        sl = self.slot
        e = sl.entry
        s = self.db.settings
        if sl.index is not None and sl.index < len(e.tokens):
            self.original = e.tokens[sl.index]
            self.token = self.original.copy()
        else:
            self.original = None
            self.token = self._new_token(sl)
        t = self.token
        self._show_header(e)
        for name, ed in self.edits.items():
            f = s.token_field(name)
            ed.blockSignals(True)
            ed.setText(t.get(name, s.primary_gloss) if f.multilingual else t.get(name))
            ed.blockSignals(False)
        self.canvas.set_range(s.pitch_low, s.pitch_high)
        self._pitch_changed(t.get("Pitch"))
        known = {tg.name for tg, _ in s.tags.tags()}
        self.unknown_tags = [x for x in t.tags if x not in known]
        self._build_tags(set(t.tags))
        self._fill_speakers(t.speaker)
        self.date.blockSignals(True)
        self.date.setText(t.collected)
        self.date.blockSignals(False)
        self._show_rerecord(t.rerecord)
        if self.comment is not None:
            self.push_btn.setEnabled(bool(self.comment.text().strip()))
        self.position.setText(self._position_text())
        self.back_btn.setEnabled(self.pos > 0)
        self.next_btn.setEnabled(self.pos < len(self.slots) - 1)
        self._refresh_name()
        self._update_suggestion()
        if getattr(self.main, "dialog_autoplay", False) and t.file:
            QTimer.singleShot(150, self._play)

    # ---- what differs for utterances (UtteranceDialog) ----------------
    def _new_token(self, sl: Slot) -> Token:
        return self.db.new_token(sl.entry, sl.tags, self.main.session_speaker(),
                                 self.main.session_date(), defaults=sl.defaults)

    def _show_header(self, e):
        self.header.setText(f"{e.ref}   {self.db.lemma(e)}   “{self.db.gloss(e)}”")

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
                text = pitchmod.normalise(text)       # a lone digit becomes 55
            if f.multilingual:
                t.set(name, text, s.primary_gloss)
            else:
                t.set(name, text)
        t.tags = s.tags.sort(self.tags.selected() + self.unknown_tags)
        t.speaker = self.speaker.currentText()
        t.collected = self.date.text().strip()
        t.rerecord = self.rerecord_btn.isChecked()

    def _fields_changed(self, *_):
        self._collect()
        self._refresh_name()

    def _tags_changed(self):
        self._fields_changed()
        self._update_unusual()
        self._update_suggestion()

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

    def eventFilter(self, obj, event):
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
            self.name_note.setText("" if t.file else "<span style='color:#666'>Not recorded yet.</span>")
        has_file = bool(t.file) and self._path(t.file).exists()
        self.play_btn.setEnabled(has_file)
        self.delete_btn.setEnabled(has_file)
        self.praat_btn.setEnabled(has_file)
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

    # ---------------------------------------------------------- committing
    def _commit(self, keep_empty: bool = False, check_clash: bool = True) -> bool:
        """Save the working token into the entry (with undo). Returns False on a problem."""
        self._collect()
        e = self.slot.entry
        t = self.token
        saving = (t.has_content() or keep_empty or self.slot.explicit) if self.original is None \
            else self.original != t
        if check_clash and saving and t.id not in self._clash_asked and self._clashes():
            self._clash_asked.add(t.id)           # offered once; "Keep" saves it as it is
            self._offer_example(recording=False)
            self._collect()
            t = self.token
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
            self.doc.edit_entry(e, lambda en: en.tokens.append(token), f"Add token to {e.ref}",
                                renames=renames)
            self.slot.index = len(e.tokens) - 1
            self.original = e.tokens[self.slot.index]
        elif self.original != t:
            idx = self.slot.index
            token = t.copy()

            def change(en, idx=idx, token=token):
                en.tokens[idx] = token
            renames, self._renames = self._renames, []
            self.doc.edit_entry(e, change, f"Edit token in {e.ref}", renames=renames)
            self.original = e.tokens[idx]
        self.token = self.original.copy()
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
        """The first Example tag that gives this token a file name of its own (a new one if needed)."""
        from ..defaults import EXAMPLES, INSTANCES
        from ..model import Group, Tag
        ts = self.db.settings.tags
        group = next((g for _, g in ts.leaf_groups() if g.name.lower() == EXAMPLES.lower()), None)
        if group is None:                         # an older structure without it: add it
            top = next((g for g in ts.groups if g.name.lower() == INSTANCES.lower()), None)
            if top is None:
                top = Group(INSTANCES)
                ts.groups.append(top)
            group = Group(EXAMPLES)
            top.groups.append(group)
        mine = {x.name for x in group.tags}
        base = [x for x in self.token.tags if x not in mine]
        for tag in group.tags:
            if not self._clashes(base + [tag.name]):
                return tag.name
        names, codes = {x.name for x, _ in ts.tags()}, {x.code for x, _ in ts.tags()}
        n = len(group.tags) + 1
        while f"Example {n}" in names or f"X{n}" in codes or self._clashes(base + [f"Example {n}"]):
            n += 1
        group.tags.append(Tag(f"Example {n}", f"X{n}"))
        self.doc.settings_changed()
        return f"Example {n}"

    def _offer_example(self, recording: bool) -> bool:
        """Two recordings would share a name: offer a free Example tag. True if one was added."""
        others = self._clashes()
        e, o = others[0]
        name = self._expected()
        what = " + ".join(mx.chips(self.db, o.tags)) or "citation"
        tag = self._free_example()
        found = self.db.settings.tags.find(tag)
        code = found[0].display() if found else tag
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Same recording name")
        who = "This lemma already has" if e is self.slot.entry else f"{e.ref} already has"
        box.setText(f"{who} a token with this file name ({what}): {name}\n\n"
                    f"Add the example tag {code} to this token, so its recording gets a name of its own?")
        add = box.addButton(f"Add {code}" + (" and record" if recording else ""), QMessageBox.AcceptRole)
        box.addButton("Cancel" if recording else "Keep as it is", QMessageBox.RejectRole)
        box.setDefaultButton(add)
        box.exec()
        if box.clickedButton() is not add:
            return False
        mine = {x.name for _, g in self.db.settings.tags.leaf_groups()
                if g.name.lower() == "examples" for x in g.tags}
        tags = [x for x in self.token.tags if x not in mine] + [tag]
        self.token.tags = self.db.settings.tags.sort(tags)
        self._build_tags(set(self.token.tags))
        self._fields_changed()
        return True

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
        fields = [e for e in self.edits.values() if e.isVisible() and e.isEnabled()]
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
        if not self._commit():
            return
        self.main.player.stop()
        self.pos = target
        self._load()

    def _ok(self):
        if self.recorder:
            self._stop_recording()
        if self._commit(keep_empty=self.slot.explicit):
            self.main.player.stop()
            self.accept()

    def done(self, result):
        """However the dialogue closes (OK, Cancel, Esc, the window's X), its size is remembered."""
        self.main.prefs.set_value("window/token_dialog", self.saveGeometry())
        super().done(result)

    def reject(self):
        if self.recorder:
            self.recorder.stop()
            self.recorder = None
            self.timer.stop()
        self.main.player.stop()
        super().reject()

    # ----------------------------------------------------------- recording
    def _record(self):
        if self.recorder:
            self._stop_recording()
            return
        self._collect()
        if self._clashes() and not self._offer_example(recording=True):
            return                                # never record over another token's recording
        exp = self._expected()
        own = [p for p in {self.token.file, exp} if p and self._path(p).exists()]
        if own:
            ask = ("Replace this token's recording?" if self.token.file in own else
                   f"A file called {exp} is already in the sound folder, though no token uses it. "
                   "Replace it? (It goes to the Recycle Bin.)")
            if QMessageBox.question(self, "Record", ask) != QMessageBox.Yes:
                return
        prefs = self.main.prefs
        self.recorder = audio.Recorder(prefs.record_source, prefs.sample_rate)
        try:
            self.recorder.start()
        except audio.AudioError as exc:
            self.recorder = None
            QMessageBox.warning(self, "Record", str(exc))
            return
        self.main.player.stop()
        self.record_btn.setIcon(icon("stop", 40))
        self.record_btn.setToolTip("Stop recording (Ctrl+R)")
        self.timer.start()

    def _stop_recording(self):
        rec, self.recorder = self.recorder, None
        self.timer.stop()
        self.meter.setValue(0)
        self.record_btn.setIcon(icon("record", 40))
        self.record_btn.setToolTip("Record (Ctrl+R)")
        samples = rec.stop()
        if len(samples) == 0:
            QMessageBox.warning(self, "Record", "Nothing was recorded. Check the microphone.")
            return
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
            audio.write_wav(self._path(exp), samples, rec.sample_rate, self.main.prefs.bit_depth,
                            artist=t.speaker, date=t.collected)
        except (OSError, audio.AudioError) as exc:
            QMessageBox.warning(self, "Record", f"Couldn't save the recording: {exc}")
            return
        if old and old != exp and self._path(old).exists():
            QFile.moveToTrash(str(self._path(old)))
        t.file = exp
        t.rerecord = False                        # recorded again: the flag goes
        self._show_rerecord(False)
        self._commit(keep_empty=True)
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
                     "Sound file filter)")

    def _rerecord_toggled(self, on: bool):
        self._show_rerecord(on)
        self._fields_changed()

    # --------------------------------------------------- push to question
    def push_to_question(self):
        """The comment becomes an open question in the session's notebook, linked to this token."""
        if self.comment is None or not self.comment.text().strip():
            return
        text = self.comment.text().strip()
        main = self.main
        if self.original is None:                 # a new token: it exists now, so the link works
            self._collect()
            if not self._commit(keep_empty=True):
                return
        date = main.work_date()
        keys = main.session_keys()
        from .. import notebook as nbmod
        from . import chiprow as chips
        nbmod.push_question(self.doc.notebook, self.db, date, text, self.slot.entry, self.token,
                            keys[chips.RESEARCHERS], keys[chips.PARTICIPANTS], keys[chips.LOCATIONS])
        self.doc.notebook_changed()
        if getattr(main, "notebook_dialog", None) is not None:
            main.notebook_dialog.reload()
        self.comment.clear()
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(self.push_btn.mapToGlobal(self.push_btn.rect().bottomLeft()),
                          f"Added to the questions of {date}", self.push_btn)

    def _update_meter(self):
        if self.recorder:
            self.meter.setValue(int(min(1.0, self.recorder.level) * 100))
            clip = self.recorder.level >= 0.99
            self.meter.setStyleSheet("QProgressBar::chunk { background: %s; }" % (theme.colour("error").name() if clip else theme.colour("sound_ok").name()))

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
        if self.recorder:
            return
        self.main.play_pitch(self.canvas.text)

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
        m.exec(global_pos)

    def _delete_recording(self):
        t = self.token
        if not t.file:
            return
        if self.main.prefs.confirm_delete:
            if QMessageBox.question(self, "Delete recording",
                                    f"Delete {t.file}? It will go to the Recycle Bin.") != QMessageBox.Yes:
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
