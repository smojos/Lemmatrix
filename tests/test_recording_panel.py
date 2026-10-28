# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""One recording panel for the token, utterance and segment dialogues (the audit, section 8,
step 3): each recording still goes into its own dialogue's folder, under its own name."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

from lemmatrix import audio, segments, storage  # noqa: E402


class FakeRecorder:
    sample_rate = 44100
    level = 0.25

    def __init__(self, source="microphone", rate=44100):
        self.source = source

    def start(self):
        pass

    def stop(self):
        return np.full(4410, 0.1, dtype=np.float32)


def _record_and_stop(dlg, monkeypatch):
    monkeypatch.setattr(audio, "Recorder", FakeRecorder)
    dlg._record()
    assert dlg.recorder is not None and not dlg.meter.isHidden()
    (dlg._stop_recording if hasattr(dlg, "_stop_recording") else dlg._stop)()
    assert dlg.recorder is None


def test_a_token_records_into_soundfiles_tokens(win, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    e = db.entries[1]
    dlg = TokenDialog(win, [Slot(e, 0)], 0)                      # over its own recording (asked: Yes)
    path = storage.sound_folder(db) / dlg._expected()
    before = path.read_bytes() if path.exists() else b""
    _record_and_stop(dlg, monkeypatch)
    t = dlg.token
    assert t.file == path.name and path.read_bytes() != before
    assert not (storage.utterance_folder(db) / t.file).exists()
    dlg.reject()


def test_an_utterance_records_into_soundfiles_utterances(win, monkeypatch):
    from lemmatrix.model import Token, Utterance
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    db = win.doc.db
    win.open_utterances()
    uw = win.utterances_window
    u = Utterance(ref="U900", file_gloss="the hare ran", tokens=[Token()])
    win.doc.add_entry(u)
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    _record_and_stop(dlg, monkeypatch)
    f = dlg.token.file
    assert f and (storage.utterance_folder(db) / f).exists()
    assert not (storage.sound_folder(db) / f).exists()
    dlg.reject()
    uw.close()


def test_a_segment_records_into_soundfiles_segments(win, monkeypatch):
    from lemmatrix.ui.segment_record import SegmentRecordDialog
    db = win.doc.db
    dlg = SegmentRecordDialog(win, "ʌ")
    _record_and_stop(dlg, monkeypatch)
    assert dlg.file is not None and dlg.file.parent == segments.folder(db) and dlg.file.exists()
    dlg.reject()


def test_the_source_choice_is_this_computers_in_all_three(win, monkeypatch):
    from lemmatrix.ui.segment_record import SegmentRecordDialog
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    old = win.prefs.record_source
    other = "computer" if old != "computer" else "microphone"
    for make in (lambda: TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0),
                 lambda: SegmentRecordDialog(win, "ʌ")):
        dlg = make()
        dlg.source_box.setCurrentIndex(dlg.source_box.findData(other))
        assert win.prefs.record_source == other
        dlg.source_box.setCurrentIndex(dlg.source_box.findData(old))
        dlg.reject()
    win.prefs.record_source = old


def test_a_new_matrix_cell_shows_the_fields_in_josh_s_order():
    """Josh, 25 October: Phonetic, Phonemic, Morphemes, Translation, Comment (under the drawing)."""
    from lemmatrix import defaults, matrix as mx
    assert mx.DEFAULT_CELL == ["drawing", "Phonetic", "Phonemic", "Morphemes", "Translation", "Comment"]
    names = [f.name for f in defaults.new_database().settings.token_fields if f.name != "Pitch"]
    assert names == ["Phonetic", "Phonemic", "Morphemes", "Constituents", "Translation", "Comment"]   # Constituents: hidden (idea 91)
    assert mx.MatrixConfig().cell == mx.DEFAULT_CELL
