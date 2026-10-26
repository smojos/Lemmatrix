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

from PySide6.QtCore import QDir, QFile, QRegularExpression, Qt
from PySide6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from .. import audio, segments
from . import theme
from . import widgets as _w  # (ask: buttons that say what they do)



class SegmentRecordDialog(QDialog):
    def __init__(self, main, sequence: str, parent=None):
        super().__init__(parent)
        self.main = main
        self.db = main.doc.db
        self.sequence = segments.norm(sequence)
        self.setWindowTitle(f"Record {self.sequence}")
        outer = QVBoxLayout(self)
        from .recording_panel import RecordingPanel   # one for tokens, utterances and segments
        rec = self.rec_panel = RecordingPanel(main, self, name_span=5, stretch_before_source=False)
        rl = rec.grid
        for name in ("filename", "location", "name_note", "record_btn", "play_btn", "delete_btn",
                     "update_btn", "praat_btn", "source_box", "meter", "level_note"):
            setattr(self, name, getattr(rec, name))
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
        QShortcut(QKeySequence("Ctrl+Alt+Space"), self, self._praat)       # as in the token dialogue

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

    # The take in progress and the meter's timer are the recording panel's (recording_panel.py)
    @property
    def recorder(self):
        return self.rec_panel.recorder if hasattr(self, "rec_panel") else None

    @recorder.setter
    def recorder(self, value):
        self.rec_panel.recorder = value

    @property
    def timer(self):
        return self.rec_panel.timer

    # ---- recording
    def _record(self):
        if self.recorder:
            self._stop()
            return
        target = segments.folder(self.db) / self.expected()
        # only ever over the same sequence by the same speaker, after asking (Josh)
        if target.exists() and not _w.ask(
                self, "Record", f"Replace {target.name}? The old one goes to the Recycle Bin.", "Replace it"):
            return
        self.rec_panel.start()

    def _stop(self):
        take = self.rec_panel.stop()
        if take is not None:
            self.save(*take)

    def save(self, samples, rate: int) -> bool:
        """A recording made: written under the expected name (the one it replaces to the Recycle
        Bin), with the speaker and date in the WAV's own metadata."""
        self.rec_panel.show_level(samples)           # clipped or very quiet: said, never changed
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
        if ask and self.main.prefs.confirm_delete and not _w.ask(
                self, "Delete recording", f"Delete {self.file.name}? It will go to the Recycle Bin. "
                "Lemmatrix's own soundfile plays again where there is one.", "Delete recording"):
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
            if ask and not _w.ask(self, "Update file name",
                                            f"{target.name} is already there. Replace it? (It goes to the "
                                            "Recycle Bin.)", "Replace it"):
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
        self.rec_panel.cancel()                   # a take in progress is thrown away
        super().reject()
