# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The recording panel, one for the token, utterance and segment dialogues (the audit, section 8,
step 3: written twice and inherited a third time, which is how the utterance dialogue's Record
crashed, B1).

The panel is the controls and the capture: the file name and where it goes, a note under them,
Record, Play, Delete recording, Update file name, Open in Praat, Record from (Microphone or
Computer audio: this computer's setting, Settings → Sound), the level meter and, after a take, a
note if it clipped or was very quiet. **It never writes, moves or deletes a file**: start() starts
the microphone, stop() gives the take back, and the dialogue decides the folder and the name and
writes it, as each did before (tokens into Soundfiles/Tokens, utterances into
Soundfiles/Utterances, segments into Soundfiles/Segments). The buttons other than Record are
wired by the dialogue too. Lemmatrix never changes a recording's level.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton

from .. import advanced, audio
from . import theme
from .icons import icon



def record_icon() -> str:
    """The Record button's icon: the hot mic (Josh's flame in the cup) while 🔥 hot mic is on."""
    return "record-hot" if advanced.hot_mic() else "record"


def record_tip() -> str:
    return ("Record (Ctrl+R). 🔥 hot mic is on: a take goes straight over the soundfile already there"
            if advanced.hot_mic() else "Record (Ctrl+R)")


def ask_record_over(parent, text: str, go: str) -> bool:
    """Record over a soundfile already there? 🔥 hot mic on: yes, without asking (IDEAS.md idea 68,
    Josh, 27 October); off: asked every time. The replaced soundfile still goes to the Recycle Bin."""
    if advanced.hot_mic():
        return True
    from . import widgets as _w
    return _w.ask(parent, "Record", text, go)

class RecordingPanel(QGroupBox):
    """The grid's rows: 0 the file name (columns 0–3; the dialogue may put something at column 4),
    1 where it goes, 2 a note, 3–4 the buttons and Record from (columns 0–1; the dialogue puts
    Speaker and Date at columns 3–4), 5 the meter, 6 the level note."""

    def __init__(self, main, parent=None, name_span: int = 4, stretch_before_source: bool = True):
        super().__init__(parent)
        self.main = main
        self.recorder: audio.Recorder | None = None
        self.grid = rl = QGridLayout(self)
        self.filename = QLabel()
        ff = self.filename.font()
        ff.setPointSize(ff.pointSize() + 3)
        self.filename.setFont(ff)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.filename, 0, 0, 1, name_span)
        self.location = QLabel()
        self.location.setStyleSheet(f"color: {theme.muted()};")
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location.setWordWrap(True)
        rl.addWidget(self.location, 1, 0, 1, 5)
        self.name_note = QLabel()
        self.name_note.setStyleSheet(f"color: {theme.colour('error').name()};")
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
        self.record_btn = icon_button(record_icon(), record_tip())
        listen = lambda key, _on, b=self.record_btn: (key == advanced.HOT_MIC_KEY and self.recorder is None  # noqa: E731
                                                      and (b.setIcon(icon(record_icon(), 40)),
                                                           b.setToolTip(record_tip())))
        advanced.listen(listen)                  # 🔥 hot mic switched: the button follows at once
        self.destroyed.connect(lambda *_: advanced.unlisten(listen))
        self.play_btn = icon_button("play", "Play (Ctrl+Space)")
        self.delete_btn = icon_button("delete-recording", "Delete recording")
        self.update_btn = icon_button("update", "Update file name")
        self.praat_btn = icon_button("praat", "Open in Praat (Ctrl+Alt+Space)")
        # ✂ auto-snip's button (idea 10, Josh, 27 October): shown while auto-snip is on; the dialogue
        # wires it (autosnip.proselytize) and enables it when there's a soundfile
        self.snip_btn = icon_button("snip-fire", advanced.SNIP_BUTTON_TIP)
        self.snip_gaps = True                    # tokens: gaps shortened too; utterances, segments: ends only
        self._snip_icon()
        self.snip_btn.setVisible(advanced.auto_snip())
        snip_listen = lambda key, on, b=self.snip_btn: key == advanced.AUTO_SNIP_KEY and b.setVisible(on)  # noqa: E731
        advanced.listen(snip_listen)
        self.destroyed.connect(lambda *_: advanced.unlisten(snip_listen))
        if stretch_before_source:
            buttons.addStretch(1)
        # the recording source (Josh, 21 October): the same setting as Settings → Sound
        self.source_box = QComboBox()
        self.source_box.addItem("Microphone", "microphone")
        self.source_box.addItem("Computer audio", "computer")
        self.source_box.setToolTip("Record from: the same choice as Settings → Sound → Recording source "
                                   "(this computer)")
        self.source_box.setCurrentIndex(max(0, self.source_box.findData(main.prefs.record_source)))
        self.source_box.currentIndexChanged.connect(self.source_changed)
        buttons.addWidget(self.source_box, 0, Qt.AlignVCenter)
        rl.addLayout(buttons, 3, 0, 2, 2)

        from .levelmeter import LevelMeter           # in dB, with zones and a peak (Josh, 22 October)
        self.meter = LevelMeter()
        self.meter.setFixedWidth(220)
        rl.addWidget(self.meter, 5, 0, 1, 2)
        self.level_note = QLabel()                    # after recording: clipped or very quiet
        self.level_note.setWordWrap(True)
        self.level_note.setStyleSheet(f"color: {theme.colour('error').name()};")
        self.level_note.hide()
        rl.addWidget(self.level_note, 6, 0, 1, 5)
        self.snip_note = QLabel()                     # ✂ auto-snip: what it cut (Josh: "no visual cue")
        self.snip_note.setWordWrap(True)
        self.snip_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.snip_note.hide()
        rl.addWidget(self.snip_note, 7, 0, 1, 5)
        rl.setColumnStretch(2, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_meter)

    # ---- the source ---------------------------------------------------------
    def source_changed(self, *_):
        src = self.source_box.currentData()
        if src and src != self.main.prefs.record_source:
            self.main.prefs.record_source = src

    # ---- recording ------------------------------------------------------------
    def start(self) -> bool:
        """Start the microphone (or computer audio); False, after saying why, if it can't."""
        prefs = self.main.prefs
        self.source_changed()
        self.snip_note.hide()
        self.recorder = audio.Recorder(prefs.record_source, prefs.sample_rate)
        try:
            self.recorder.start()
        except audio.AudioError as exc:
            self.recorder = None
            QMessageBox.warning(self.window(), "Record", str(exc))
            return False
        self.main.player.stop()
        self.meter.reset()
        self.level_note.hide()
        self.record_btn.setIcon(icon("stop", 40))
        self.record_btn.setToolTip("Stop recording (Ctrl+R)")
        self.timer.start()
        return True

    def _idle(self):
        self.timer.stop()
        self.meter.set_level(0.0)
        self.record_btn.setIcon(icon(record_icon(), 40))
        self.record_btn.setToolTip(record_tip())

    def _snip_icon(self, glow: bool = False):
        self.snip_btn.setIcon(icon("snip-fire-glow" if glow else "snip-fire", 40,
                                   theme.colour("window_text").name()))

    def auto_snip(self, samples, rate: int):
        """✂ auto-snip on a fresh take: (the take to save, the untrimmed take to hold, or None)."""
        if not advanced.auto_snip():
            return samples, None
        from .. import snip
        try:
            out, rep = snip.snip(samples, rate, gaps=self.snip_gaps, **advanced.snip_margins())
        except Exception:                         # never lose a take over trimming it
            return samples, None
        if rep.changed:
            self.show_snip(rep)                   # said only when it cut something
        return (out, samples) if rep.changed else (samples, None)

    def flash_snip(self):
        """The ✂ button's flame flashes bright a few times (Josh: a light cue, no heavy animation)."""
        for i in range(6):
            QTimer.singleShot(i * 110, self, lambda glow=(i % 2 == 0): self._snip_icon(glow))

    def show_snip(self, rep, original: str = ""):
        """✂ auto-snip's result under the meter: what was cut and where the original is kept."""
        from . import theme as _theme
        if rep is None:
            self.snip_note.hide()
            return
        if rep.changed:
            text = f"✂ Snipped {rep.length:.2f} s → {rep.new_length:.2f} s"
            tip = ((f"The original is kept as {original}" if original else "The take as recorded is kept")
                   + " in Soundfiles › _Deleted recordings until the database closes.")
            colour = _theme.accent().name()
            self.flash_snip()
        else:
            text = f"✂ {rep.describe()[0].upper()}{rep.describe()[1:]}: the soundfile is as it was."
            tip = ""
            colour = _theme.muted()
        self.snip_note.setText(text)
        self.snip_note.setToolTip(tip)
        self.snip_note.setStyleSheet(f"color: {colour};")
        self.snip_note.show()

    def stop(self):
        """Stop and give back (samples, sample rate); None, after saying so, if nothing came in."""
        rec, self.recorder = self.recorder, None
        self._idle()
        if rec is None:
            return None
        samples = rec.stop()
        if len(samples) == 0:
            QMessageBox.warning(self.window(), "Record", "Nothing was recorded. Check the microphone.")
            return None
        return samples, rec.sample_rate

    def cancel(self):
        """Stop and throw the take away (the dialogue closed while recording)."""
        rec, self.recorder = self.recorder, None
        self._idle()
        if rec is not None:
            rec.stop()

    def show_level(self, samples):
        """Clipped or very quiet: said under the meter, never changed."""
        from . import levelmeter
        verdict, db = levelmeter.check(samples)
        self.level_note.setText(levelmeter.message(verdict, db))
        self.level_note.setVisible(bool(verdict))

    def _update_meter(self):
        if self.recorder:
            self.meter.set_level(self.recorder.level)
