"""The token dialogue: fields, tags and recording, with Back and Next."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from PySide6.QtCore import QFile

from .. import audio, pitch as pitchmod, storage
from ..model import Entry, Token
from PySide6.QtCore import QSize

from .icons import icon
from .tagpanel import TagPanel
from .widgets import PitchCanvas, ipa_font


@dataclass
class Slot:
    """A place the dialogue can show: an existing token or an empty cell."""
    entry: Entry
    index: int | None              # token index in entry.tokens, or None for a new token
    tags: tuple = ()               # tags for a new token
    explicit: bool = False         # created on purpose (double-click), so OK keeps it even if empty
    defaults: bool | None = None   # pre-select group defaults (None: only if tags were given)


class TokenDialog(QDialog):
    def __init__(self, main, slots: list[Slot], index: int):
        super().__init__(main)
        self.main = main
        self.doc = main.doc
        self.db = main.doc.db
        self.slots = slots
        self.pos = index
        self.token: Token | None = None
        self.original: Token | None = None
        self.recorder: audio.Recorder | None = None
        self.unknown_tags: list[str] = []
        self.setWindowTitle("Edit Token")
        self.resize(920, 780)
        self._build()
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
        title = QLabel("Edit Token")
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 6)
        tf.setBold(True)
        title.setFont(tf)
        left.addWidget(title, 0, 1)
        self.canvas = PitchCanvas(low=s.pitch_low, high=s.pitch_high, font=ipa_font(self.main.prefs.ipa_size + 3))
        self.canvas.setMinimumHeight(70)
        left.addWidget(QLabel("Pitch\nRendering"), 1, 0)
        left.addWidget(self.canvas, 1, 1)
        self.edits: dict[str, QLineEdit] = {}
        row = 2
        for f in s.token_fields:
            ed = QLineEdit()
            if f.role in ("phonetic", "phonemic"):
                ed.setFont(ipa_font(self.main.prefs.ipa_size + 3))
            else:
                ed.setFont(ipa_font(self.main.prefs.ipa_size + 1))
            if f.role == "pitch":
                ed.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9 ,]*"), ed))
                ed.setPlaceholderText("e.g. 12 33 41")
                ed.textChanged.connect(self._pitch_changed)
            ed.textChanged.connect(self._fields_changed)
            label = f.title + (f" ({s.primary_gloss})" if f.multilingual and len(s.gloss_languages) > 1 else "")
            left.addWidget(QLabel(label), row, 0)
            left.addWidget(ed, row, 1)
            self.edits[f.name] = ed
            row += 1
        self.pitch_note = QLabel()
        self.pitch_note.setStyleSheet("color: #b26a00;")
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
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tags)
        scroll.setFrameShape(QFrame.NoFrame)
        tl.addWidget(scroll)
        top.addWidget(tags_box, 2)

        rec = QGroupBox()
        rl = QGridLayout(rec)
        self.filename = QLabel()
        ff = self.filename.font()
        ff.setPointSize(ff.pointSize() + 3)
        self.filename.setFont(ff)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.filename, 0, 0, 1, 5)
        self.name_note = QLabel()
        self.name_note.setStyleSheet("color: #c62828;")
        rl.addWidget(self.name_note, 1, 0, 1, 5)
        rl.addWidget(QLabel("Speaker"), 2, 3, Qt.AlignRight)
        self.speaker = QComboBox()
        self.speaker.addItem("")
        for p in self.db.metadata.participants:
            self.speaker.addItem(p.code)
        self.speaker.currentTextChanged.connect(self._fields_changed)
        self.speaker.setFixedWidth(130)
        rl.addWidget(self.speaker, 2, 4)
        rl.addWidget(QLabel("Date"), 3, 3, Qt.AlignRight)
        self.date = QLineEdit()
        self.date.setPlaceholderText("YYYY-MM-DD")
        self.date.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"(\d{4}-\d{2}-\d{2})?"), self.date))
        self.date.textChanged.connect(self._fields_changed)
        self.date.setFixedWidth(130)
        rl.addWidget(self.date, 3, 4)

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
        buttons.addStretch(1)
        self.record_btn.clicked.connect(self._record)
        self.play_btn.clicked.connect(self._play)
        self.delete_btn.clicked.connect(self._delete_recording)
        self.update_btn.clicked.connect(self._update_name)
        rl.addLayout(buttons, 2, 0, 2, 2)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setMaximumHeight(10)
        self.meter.setToolTip("Recording level")
        self.meter.setFixedWidth(220)
        rl.addWidget(self.meter, 4, 0, 1, 2)
        rl.setColumnStretch(2, 1)
        outer.addWidget(rec)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("◀ Back")
        self.back_btn.setToolTip("Save and go to the previous token (Alt+Left)")
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setToolTip("Save and go to the next token (Alt+Right)")
        self.position = QLabel()
        self.position.setStyleSheet("color: #666;")
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
            self.token = self.db.new_token(e, sl.tags, self.main.session_speaker(),
                                           self.main.session_date(), defaults=sl.defaults)
        t = self.token
        self.header.setText(f"{e.ref}   {self.db.lemma(e)}   “{self.db.gloss(e)}”")
        for name, ed in self.edits.items():
            f = s.token_field(name)
            ed.blockSignals(True)
            ed.setText(t.get(name, s.primary_gloss) if f.multilingual else t.get(name))
            ed.blockSignals(False)
        self.canvas.low, self.canvas.high = s.pitch_low, s.pitch_high
        self._pitch_changed(t.get("Pitch"))
        wc = self.db.word_class(e)
        known = {tg.name for tg, _ in s.tags.tags_for(wc)}
        self.unknown_tags = [x for x in t.tags if x not in known]
        self.tags.build(self.db, wc, set(t.tags))
        self.speaker.blockSignals(True)
        if t.speaker and self.speaker.findText(t.speaker) < 0:
            self.speaker.addItem(t.speaker)
        self.speaker.setCurrentText(t.speaker)
        self.speaker.blockSignals(False)
        self.date.blockSignals(True)
        self.date.setText(t.collected)
        self.date.blockSignals(False)
        state = "new token" if self.original is None else f"token {sl.index + 1} of {len(e.tokens)}"
        self.position.setText(f"{self.pos + 1} / {len(self.slots)}  ·  {state}")
        self.back_btn.setEnabled(self.pos > 0)
        self.next_btn.setEnabled(self.pos < len(self.slots) - 1)
        self._refresh_name()
        if getattr(self.main, "dialog_autoplay", False) and t.file:
            QTimer.singleShot(150, self._play)

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
        wc = self.db.word_class(self.slot.entry)
        t.tags = s.tags.sort(wc, self.tags.selected() + self.unknown_tags)
        t.speaker = self.speaker.currentText()
        t.collected = self.date.text().strip()

    def _fields_changed(self, *_):
        self._collect()
        self._refresh_name()

    def _tags_changed(self):
        self._fields_changed()

    def _pitch_changed(self, text):
        self.canvas.set_pitch(text)
        s = self.db.settings
        self.pitch_note.setText(" ".join(pitchmod.problems(text, s.pitch_low, s.pitch_high)))

    def _expected(self) -> str:
        return self.db.expected_filename(self.slot.entry, self.token)

    def _path(self, name: str) -> Path:
        return storage.sound_folder(self.db) / name

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
        self.update_btn.setEnabled(bool(t.file) and t.file != exp and has_file
                                   and not self.db.settings.auto_update_names)
        if self.db.settings.auto_update_names and t.file and t.file != exp:
            self.name_note.setText(self.name_note.text() + " It will be renamed when you leave this token.")

    # ---------------------------------------------------------- committing
    def _commit(self, keep_empty: bool = False) -> bool:
        """Save the working token into the entry (with undo). Returns False on a problem."""
        self._collect()
        e = self.slot.entry
        t = self.token
        wc = self.db.word_class(e)
        problems = self.db.settings.tags.conflicts(wc, [x for x in t.tags if x not in self.unknown_tags])
        if problems:
            QMessageBox.warning(self, "Tags", "\n".join(problems))
            return False
        # Rename the recording if its name is out of date and renaming is automatic.
        if self.db.settings.auto_update_names and t.file and t.file != self._expected():
            self._rename_file(quiet=True)
        if self.original is None:
            if not (t.has_content() or keep_empty or self.slot.explicit):
                return True                       # passing through an empty cell
            token = t.copy()
            self.doc.edit_entry(e, lambda en: en.tokens.append(token), f"Add token to {e.ref}")
            self.slot.index = len(e.tokens) - 1
            self.original = e.tokens[self.slot.index]
        elif self.original != t:
            idx = self.slot.index
            token = t.copy()

            def change(en, idx=idx, token=token):
                en.tokens[idx] = token
            self.doc.edit_entry(e, change, f"Edit token in {e.ref}")
            self.original = e.tokens[idx]
        self.token = self.original.copy()
        return True

    def _rename_file(self, quiet: bool = False) -> bool:
        t = self.token
        exp = self._expected()
        src, dst = self._path(t.file), self._path(exp)
        if not src.exists():
            return False
        if dst.exists() and dst.resolve() != src.resolve():
            QMessageBox.warning(self, "File name", f"Can't rename {t.file}: a file called {exp} "
                                "already exists. Check for duplicate tokens.")
            return False
        try:
            src.rename(dst)
        except OSError as exc:
            QMessageBox.warning(self, "File name", f"Couldn't rename {t.file}: {exc}")
            return False
        t.file = exp
        return True

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
        exp = self._expected()
        existing = [p for p in {self.token.file, exp} if p and self._path(p).exists()]
        if existing:
            if QMessageBox.question(self, "Record", "Replace the existing recording?") != QMessageBox.Yes:
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
        # Whoever records now is the token's speaker; the date is the session's.
        speaker, date = self.main.session_speaker(), self.main.session_date()
        if speaker:
            t.speaker = speaker
        if date:
            t.collected = date
        self.speaker.blockSignals(True)
        if t.speaker and self.speaker.findText(t.speaker) < 0:
            self.speaker.addItem(t.speaker)
        self.speaker.setCurrentText(t.speaker)
        self.speaker.blockSignals(False)
        self.date.blockSignals(True)
        self.date.setText(t.collected)
        self.date.blockSignals(False)
        exp = self._expected()
        old = t.file
        try:
            audio.write_wav(self._path(exp), samples, rec.sample_rate, self.main.prefs.bit_depth,
                            artist=t.speaker, date=t.collected)
        except (OSError, audio.AudioError) as exc:
            QMessageBox.warning(self, "Record", f"Couldn't save the recording: {exc}")
            return
        if old and old != exp and self._path(old).exists():
            QFile.moveToTrash(str(self._path(old)))
        t.file = exp
        self._commit(keep_empty=True)
        self._refresh_name()

    def _update_meter(self):
        if self.recorder:
            self.meter.setValue(int(min(1.0, self.recorder.level) * 100))
            clip = self.recorder.level >= 0.99
            self.meter.setStyleSheet("QProgressBar::chunk { background: %s; }" % ("#c62828" if clip else "#43a047"))

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
