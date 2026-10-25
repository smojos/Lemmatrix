# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Recording a sequence for the segment scratchpad (IDEAS.md idea 46; Josh's mockup, 24 October).

A small dialogue of its own with the token dialogue's recording functions: the live file name
(`LXX-VXX-SP1_ʌ.wav`) and where it goes (Soundfiles/Segments), Record, Play, Delete recording,
Update file name, Open in Praat, the recording source, the level meter, Speaker (the participants
and, here only, the researchers) and Date. Recording only ever writes over the same sequence's
recording by the same speaker, after asking. Lemmatrix never changes a recording's level.
Segment soundfiles aren't in the database, so none of this is an undo step."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QFile, QRegularExpression, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from .. import audio, segments
from . import theme
from .icons import icon



class SegmentRecordDialog(QDialog):
    def __init__(self, main, sequence: str, parent=None):
        super().__init__(parent)
        self.main = main
        self.db = main.doc.db
        self.sequence = segments.norm(sequence)
        self.recorder = None
        self.setWindowTitle(f"Record {self.sequence}")
        outer = QVBoxLayout(self)
        rec = QGroupBox()
        rl = QGridLayout(rec)
        self.filename = QLabel()
        ff = self.filename.font()
        ff.setPointSize(ff.pointSize() + 3)
        self.filename.setFont(ff)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.filename, 0, 0, 1, 5)
        self.location = QLabel()
        self.location.setStyleSheet(f"color: {theme.muted()};")
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location.setWordWrap(True)
        rl.addWidget(self.location, 1, 0, 1, 5)
        self.name_note = QLabel()
        rl.addWidget(self.name_note, 2, 0, 1, 5)

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
        self.source_box = QComboBox()
        self.source_box.addItem("Microphone", "microphone")
        self.source_box.addItem("Computer audio", "computer")
        self.source_box.setToolTip("Record from: the same choice as Settings → Sound → Recording source "
                                   "(this computer)")
        self.source_box.setCurrentIndex(max(0, self.source_box.findData(main.prefs.record_source)))
        self.source_box.currentIndexChanged.connect(self._source_changed)
        buttons.addWidget(self.source_box, 0, Qt.AlignVCenter)
        rl.addLayout(buttons, 3, 0, 2, 2)
        self.record_btn.clicked.connect(lambda *_: self._record())
        self.play_btn.clicked.connect(lambda *_: self._play())
        self.delete_btn.clicked.connect(lambda *_: self._delete())
        self.update_btn.clicked.connect(lambda *_: self._update_name())
        self.praat_btn.clicked.connect(lambda *_: self._praat())

        rl.addWidget(QLabel("Speaker"), 3, 3, Qt.AlignRight)
        self.speaker = QComboBox()
        self.speaker.setToolTip("Whose voice this is: a participant, or (here only) a researcher. A "
                                "researcher's segment soundfiles go into no archive")
        self.speaker.setFixedWidth(160)
        rl.addWidget(self.speaker, 3, 4)
        rl.addWidget(QLabel("Date"), 4, 3, Qt.AlignRight)
        self.date = QLineEdit(main.session_date())
        self.date.setPlaceholderText("YYYY-MM-DD")
        self.date.setValidator(QRegularExpressionValidator(QRegularExpression(r"(\d{4}-\d{2}-\d{2})?"), self.date))
        self.date.setFixedWidth(160)
        rl.addWidget(self.date, 4, 4)
        from .levelmeter import LevelMeter
        self.meter = LevelMeter()
        self.meter.setFixedWidth(220)
        rl.addWidget(self.meter, 5, 0, 1, 2)
        self.level_note = QLabel()
        self.level_note.setWordWrap(True)
        self.level_note.setStyleSheet(f"color: {theme.colour('error').name()};")
        self.level_note.hide()
        rl.addWidget(self.level_note, 6, 0, 1, 5)
        rl.setColumnStretch(2, 1)
        outer.addWidget(rec)

        nav = QHBoxLayout()
        nav.addStretch(1)
        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        nav.addWidget(ok)
        nav.addWidget(cancel)
        outer.addLayout(nav)
        ok.clicked.connect(lambda *_: self._ok())
        cancel.clicked.connect(self.reject)
        QShortcut(QKeySequence("Ctrl+R"), self, self._record)
        QShortcut(QKeySequence("Ctrl+Space"), self, self._play)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(lambda: self.recorder and self.meter.set_level(self.recorder.level))

        self._fill_speakers(main.session_speaker())
        self.file: Path | None = None             # the recording this dialogue shows
        found = self._path(self.speaker_code())
        if found.exists():
            self.file = found
        self.speaker.currentIndexChanged.connect(lambda *_: self._speaker_changed())
        self._refresh()

    # ---- speakers
    def _fill_speakers(self, current: str):
        sp = self.speaker
        sp.clear()
        sp.addItem("", "")
        for code in self.main.speaker_choices():
            sp.addItem(code, code)
        for p in self.db.metadata.participants:   # every participant, the session's first
            if sp.findData(p.code) < 0:
                sp.addItem(p.code, p.code)
        if self.db.metadata.researchers:           # researchers as speakers, here only (Josh)
            sp.insertSeparator(sp.count())
            for p in self.db.metadata.researchers:
                if sp.findData(p.code) < 0:
                    sp.addItem(p.code, p.code)
                    sp.setItemData(sp.count() - 1, "Researcher: not archived", Qt.ToolTipRole)
        i = sp.findData(current)
        sp.setCurrentIndex(i if i >= 0 else 0)

    def speaker_code(self) -> str:
        return self.speaker.currentData() or ""

    def _speaker_changed(self):
        if self.file is None or not self.file.exists():
            found = self._path(self.speaker_code())
            self.file = found if found.exists() else None
        self._refresh()

    # ---- names
    def expected(self) -> str:
        return segments.filename(self.db, self.sequence, self.speaker_code())

    def _path(self, speaker: str) -> Path:
        return segments.folder(self.db) / segments.filename(self.db, self.sequence, speaker)

    def _refresh(self):
        exp = self.expected()
        self.filename.setText(exp)
        has = self.file is not None and self.file.exists()
        shown = self.file if has else segments.folder(self.db) / exp
        self.location.setText(("" if has else "Will be saved as ") + QDir.toNativeSeparators(str(shown)))
        if has and self.file.name != exp:
            self.name_note.setText(f"Recorded as {self.file.name}: the file name is out of date "
                                   "(Update file name, or OK renames it).")
            self.name_note.setStyleSheet(f"color: {theme.colour('error').name()};")
        else:
            self.name_note.setText("" if has else "Not recorded yet.")
            self.name_note.setStyleSheet(f"color: {theme.muted()};")
        for b in (self.play_btn, self.delete_btn, self.praat_btn):
            b.setEnabled(has)
        self.update_btn.setEnabled(has and self.file.name != exp)

    def _source_changed(self, *_):
        src = self.source_box.currentData()
        if src and src != self.main.prefs.record_source:
            self.main.prefs.record_source = src

    # ---- recording
    def _record(self):
        if self.recorder:
            self._stop()
            return
        target = segments.folder(self.db) / self.expected()
        # only ever over the same sequence by the same speaker, after asking (Josh)
        if target.exists() and QMessageBox.question(
                self, "Record", f"Replace {target.name}? The old one goes to the Recycle Bin.") != QMessageBox.Yes:
            return
        prefs = self.main.prefs
        self._source_changed()
        self.recorder = audio.Recorder(prefs.record_source, prefs.sample_rate)
        try:
            self.recorder.start()
        except audio.AudioError as exc:
            self.recorder = None
            QMessageBox.warning(self, "Record", str(exc))
            return
        self.main.player.stop()
        self.meter.reset()
        self.level_note.hide()
        self.record_btn.setIcon(icon("stop", 40))
        self.record_btn.setToolTip("Stop recording (Ctrl+R)")
        self.timer.start()

    def _stop(self):
        rec, self.recorder = self.recorder, None
        self.timer.stop()
        self.meter.set_level(0.0)
        self.record_btn.setIcon(icon("record", 40))
        self.record_btn.setToolTip("Record (Ctrl+R)")
        samples = rec.stop()
        if len(samples) == 0:
            QMessageBox.warning(self, "Record", "Nothing was recorded. Check the microphone.")
            return
        self.save(samples, rec.sample_rate)

    def save(self, samples, rate: int) -> bool:
        """A recording made: written under the expected name (the one it replaces to the Recycle
        Bin), with the speaker and date in the WAV's own metadata."""
        from . import levelmeter                     # clipped or very quiet: said, never changed
        verdict, db = levelmeter.check(samples)
        self.level_note.setText(levelmeter.message(verdict, db))
        self.level_note.setVisible(bool(verdict))
        target = segments.folder(self.db) / self.expected()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            QFile.moveToTrash(str(target))
        try:
            audio.write_wav(target, samples, rate, self.main.prefs.bit_depth,
                            artist=self.speaker_code(), date=self.date.text())
        except (OSError, audio.AudioError) as exc:
            QMessageBox.warning(self, "Record", f"Couldn't save the recording: {exc}")
            return False
        if self.file is not None and self.file != target and self.file.exists():
            QFile.moveToTrash(str(self.file))     # recorded again under another name: the old one goes
        self.file = target
        self._refresh()
        return True

    def _play(self):
        if self.recorder or self.file is None or not self.file.exists():
            return
        try:
            self.main.player.play([self.file])
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Play", str(exc))

    def _praat(self):
        if self.file is not None and self.file.exists():
            self.main.open_in_praat(self.file, self)

    def _delete(self, ask: bool = True) -> bool:
        if self.file is None or not self.file.exists():
            return False
        if ask and self.main.prefs.confirm_delete and QMessageBox.question(
                self, "Delete recording", f"Delete {self.file.name}? It will go to the Recycle Bin. "
                "Lemmatrix's own soundfile plays again where there is one.") != QMessageBox.Yes:
            return False
        self.main.player.stop()
        if not QFile.moveToTrash(str(self.file)):
            try:
                self.file.unlink()
            except OSError:
                QMessageBox.warning(self, "Delete recording", f"Couldn't delete {self.file.name}.")
                return False
        self.file = None
        self._refresh()
        return True

    def _update_name(self, ask: bool = True) -> bool:
        """The speaker changed after recording: the file follows (asking before replacing)."""
        if self.file is None or not self.file.exists():
            return True
        target = segments.folder(self.db) / self.expected()
        if self.file == target:
            return True
        if target.exists():
            if ask and QMessageBox.question(self, "Update file name",
                                            f"{target.name} is already there. Replace it? (It goes to the "
                                            "Recycle Bin.)") != QMessageBox.Yes:
                return False
            QFile.moveToTrash(str(target))
        try:
            self.file.rename(target)
        except OSError as exc:
            QMessageBox.warning(self, "Update file name", f"Couldn't rename {self.file.name}: {exc}")
            return False
        self.file = target
        self._refresh()
        return True

    def _ok(self):
        if self.recorder:
            self._stop()
        if self.file is not None and self.file.exists() and self.file.name != self.expected():
            if not self._update_name():
                return
        self.accept()

    def reject(self):
        if self.recorder:
            self.recorder.stop()
            self.recorder = None
            self.timer.stop()
        super().reject()
