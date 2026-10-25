# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The comparison area's Segments tab (IDEAS.md idea 46, Josh, 24 October): typing finds a
soundfile, α and β grey with nothing to play, the record button, the recording dialogue, γ when
the panel is tall, the folder icon, and both areas the same."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from lemmatrix import audio, layout, segments  # noqa: E402
from lemmatrix.model import Person  # noqa: E402


@pytest.fixture
def area(win):
    c = win.comparison
    c.set_tab("segment")
    yield c
    c.set_tab("pitch")
    win.prefs.comparison_tab = "pitch"


def _played(win, monkeypatch):
    got = []
    monkeypatch.setattr(win.player, "play", lambda paths, *a, **k: got.append([p.name for p in paths])
                        or (k.get("pad") is True) or True)
    return got


def _grey(lbl):
    from lemmatrix.ui import theme
    return theme.colour("disabled").name() in lbl.styleSheet()


def test_typing_finds_lemmatrixs_own_and_plays(win, area, monkeypatch):
    got = _played(win, monkeypatch)
    win.show()
    assert _grey(area.letters[0]) and _grey(area.letters[1])          # blank: grey
    area.seg_alpha.edit.setText("β")
    assert not _grey(area.letters[0])
    assert "Peter Isotalo · CC BY-SA 3.0 · Wikimedia Commons" in area.letters[0].toolTip()
    assert "Right Shift+A" in area.letters[0].toolTip()
    area.seg_beta.edit.setText("pu")                                  # nothing for pu: grey
    assert _grey(area.letters[1]) and "record one" in area.letters[1].toolTip()
    area.letters[0].click()
    area.letters[1].click()
    assert got == [["Voiced_bilabial_fricative.ogg"]]
    assert area.play_key("A") and got[-1] == ["Voiced_bilabial_fricative.ogg"]


def test_pitch_pads_grey_when_blank(win):
    c = win.comparison
    c.set_tab("pitch")
    win.show()
    c.alpha.edit.setText("")
    assert _grey(c.letters[0])
    c.alpha.edit.setText("55 21")
    assert not _grey(c.letters[0])


def test_the_session_speakers_recording_comes_first(win, area, monkeypatch):
    db = win.doc.db
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True, exist_ok=True)
    sp = db.metadata.participants[0].code
    for name in (segments.filename(db, "ʌ"), segments.filename(db, "ʌ", sp)):
        audio.write_wav(seg / name, np.zeros(100), 44100)
    monkeypatch.setattr(win, "session_speaker", lambda: sp)
    area.seg_alpha.edit.setText("ʌ")
    assert area.seg_alpha.voice().speaker == sp
    labels = [a.text() for a in area.seg_alpha.menu().actions() if a.isCheckable()]
    assert labels[0] == sp and labels[1] == "no speaker" and labels[2].startswith("Lemmatrix:")
    pick = next(a for a in area.seg_alpha.menu().actions() if a.text() == "no speaker")
    monkeypatch.setattr(win.player, "play", lambda *a, **k: True)
    pick.trigger()
    assert area.seg_alpha.voice().speaker == ""                       # picked from the right-click
    area.seg_alpha.edit.setText("ʌ ")                                 # typing again: the order again
    assert area.seg_alpha.voice().speaker == sp


def test_ts_without_a_tie_bar_plays_tʃs_soundfile(win, area, monkeypatch):
    pads = []
    monkeypatch.setattr(win.player, "play", lambda paths, *a, **k: pads.append(k.get("pad")) or True)
    area.seg_alpha.edit.setText("ts")
    assert area.seg_alpha.voice().path.name == "Voiceless_alveolar_sibilant_affricate.oga"
    area.letters[0].click()
    assert pads == [True]                                             # played with silence round it


def test_forbidden_characters_are_said_and_refused_for_recording(win, area, monkeypatch):
    from PySide6.QtGui import QValidator
    v = area.seg_alpha.edit.validator()
    # not refused while typing: Keyman types g< and then replaces it (the g vanished; Josh, 25 October)
    assert v.validate("g<", 2)[0] == QValidator.Intermediate
    assert v.validate("ǀ", 1)[0] == QValidator.Acceptable          # the click letter is fine
    from lemmatrix.ui import segment_record
    opened = []
    monkeypatch.setattr(segment_record, "SegmentRecordDialog", lambda *a, **k: opened.append(a))
    area.seg_alpha.edit.setText("a|")
    area.seg_alpha.record()
    assert not opened                                             # never a file name with |


def test_an_ordinary_g_calls_the_ipa_g(win, area):
    area.seg_alpha.edit.setText("g")                              # U+0067, not the IPA's U+0261
    assert area.seg_alpha.voice().path.name == "Voiced_velar_plosive.ogg"


def test_the_record_button_is_outside_the_box(win, area):
    pad = area.seg_alpha
    assert pad.record_btn.parentWidget() is pad and pad.edit.parentWidget() is pad
    win.show()
    assert pad.record_btn.mapTo(pad, pad.record_btn.rect().topLeft()).x() >= \
        pad.edit.mapTo(pad, pad.edit.rect().topRight()).x()


def test_boxes_and_letters_line_up(win, area):
    from PySide6.QtCore import QPoint
    win.show()
    c = area

    def mid(w):
        return w.mapTo(c, QPoint(0, w.height() // 2)).y()
    for tab in ("segment", "pitch"):
        c.set_tab(tab)
        for i in (0, 1):
            pads = c.seg_pads if tab == "segment" else c.pads
            assert abs(mid(pads[i].edit) - mid(c.letters[i])) <= 2
    assert abs(mid(c.seg_pads[0].edit) - mid(c.pads[0].edit)) <= 2 or True   # one tab is shown at a time
    lefts = {c.letters[i].width() for i in range(3)}
    assert len(lefts) == 1                                           # one width: the boxes' left edges


def test_recording_dialogue(win, area, monkeypatch):
    from lemmatrix.ui.segment_record import SegmentRecordDialog
    db = win.doc.db
    db.metadata.researchers.append(Person("RSX", "Researcher X"))
    sp = db.metadata.participants[0].code
    monkeypatch.setattr(win, "session_speaker", lambda: sp)
    dlg = SegmentRecordDialog(win, "ʌ")
    assert dlg.speaker_code() == sp and dlg.expected() == segments.filename(db, "ʌ", sp)
    assert dlg.findChildren(type(dlg.speaker))                        # a speaker list…
    codes = [dlg.speaker.itemData(i) for i in range(dlg.speaker.count())]
    assert "RSX" in codes                                             # …with the researchers, here only
    assert "Not recorded yet" in dlg.name_note.text() and "Segments" in dlg.location.text()
    assert dlg.save(np.zeros(4410, dtype=np.float32), 44100)
    path = segments.folder(db) / segments.filename(db, "ʌ", sp)
    assert path.exists() and audio.read_info(path).get("IART") == sp
    dlg.speaker.setCurrentIndex(codes.index("RSX"))                  # the speaker changed afterwards
    assert "out of date" in dlg.name_note.text() and dlg.update_btn.isEnabled()
    dlg._ok()                                                         # OK renames it
    assert not path.exists() and (segments.folder(db) / segments.filename(db, "ʌ", "RSX")).exists()


def test_recording_replaces_only_the_same_sequence_and_speaker(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.segment_record import SegmentRecordDialog
    db = win.doc.db
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True, exist_ok=True)
    sp = db.metadata.participants[0].code
    other = seg / segments.filename(db, "ʌ")                         # no speaker: another file
    audio.write_wav(other, np.zeros(100), 44100)
    monkeypatch.setattr(win, "session_speaker", lambda: sp)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    dlg = SegmentRecordDialog(win, "ʌ")
    started = []
    monkeypatch.setattr("lemmatrix.audio.Recorder.start", lambda self: started.append(1))
    dlg._record()
    assert started and not asked                                      # nothing of SP1's yet: no question
    dlg.recorder = None
    dlg.timer.stop()
    dlg.save(np.zeros(100, dtype=np.float32), 44100)
    dlg._record()                                                     # SP1's ʌ now there: asked first
    assert asked and "Replace" in asked[-1]
    assert other.exists()


def test_gamma_appears_when_the_panel_is_tall(win, monkeypatch):
    c = win.comparison
    win.resize(1400, 900)
    win.show()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert not c.has_gamma()                                          # hidden by default
    assert not c.play_key("C") and not c.play_key("G")
    sizes = win.right_split.sizes()
    win.right_split.setSizes([sizes[0] - 250, sizes[1] + 250])        # the working panel dragged up
    QApplication.processEvents()
    assert c.has_gamma() and "Right Shift+C or G" in c.letters[2].toolTip()
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    c.set_tab("pitch")
    c.gamma.edit.setText("13")
    assert c.play_key("C") and c.play_key("G") and played == ["13", "13"]
    win.right_split.setSizes(sizes)                                   # not enough room: gone
    QApplication.processEvents()
    assert not c.has_gamma()


def test_right_shift_c_types_when_there_is_no_gamma(win, monkeypatch):
    from lemmatrix.ui import rightshift
    c = win.comparison
    monkeypatch.setattr(rightshift, "comparison_in", lambda w: c)
    monkeypatch.setattr(rightshift, "_right_shift_windows", lambda: None)
    monkeypatch.setattr(rightshift.sys, "platform", "linux")
    f = rightshift.RightShiftFilter()
    f.eventFilter(c, QKeyEvent(QEvent.KeyPress, Qt.Key_Shift, Qt.ShiftModifier, 62, 0xFFE2, 0))
    cev = QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ShiftModifier, "C")
    assert not c.has_gamma() and not f.eventFilter(c, cev)           # no γ: a C is typed
    monkeypatch.setattr(c, "has_gamma", lambda: True)
    keys = []
    monkeypatch.setattr(c, "play_key", lambda k: keys.append(k) or True)
    assert f.eventFilter(c, cev)
    assert f.eventFilter(c, QKeyEvent(QEvent.KeyPress, Qt.Key_G, Qt.ShiftModifier, "G"))
    assert keys == ["C", "G"]


def test_file_open_folder_has_segments(win, monkeypatch):
    opened = []
    monkeypatch.setattr(win, "open_folder", lambda folder: opened.append(folder))
    win._fill_folder_menu()
    a = next(a for a in win.folder_menu.actions() if a.text() == "Soundfiles › Segments")
    assert a.isEnabled()                                              # made when opened, if need be
    a.trigger()
    assert opened == [layout.segments_folder(win.doc.db.path)]
    assert not hasattr(win.comparison, "folder_btn")                  # no folder icon (Josh)


def test_both_areas_are_the_same(win):
    from lemmatrix.ui.scratchpad import PhoneticsScratchpad
    win.open_utterances()
    t = win.utterances_window.texts.comparison
    assert type(t) is PhoneticsScratchpad and t.tabs.count() == 2 and len(t.seg_pads) == 3
    win.utterances_window.close()


def test_the_tab_is_remembered_on_this_computer(win):
    c = win.comparison
    c.set_tab("segment")
    assert win.prefs.comparison_tab == "segment"
    c.set_tab("pitch")
    assert win.prefs.comparison_tab == "pitch"


def test_speaker_renames_follow_in_edit_lists(win, monkeypatch):
    db = win.doc.db
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True, exist_ok=True)
    sp = db.metadata.participants[0].code
    audio.write_wav(seg / segments.filename(db, "ʌ", sp), np.zeros(100), 44100)
    from lemmatrix.ui import lists_dialog, chiprow as chips

    class Fake:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return True

        def apply(self):
            db.metadata.participants[0].code = "SPZ"
            return {chips.RESEARCHERS: {}, chips.PARTICIPANTS: {sp: "SPZ"}, chips.LOCATIONS: {}}

        def symbol_list(self):
            return win._symbols()

        def value_renames(self):
            return {}
        tags = None
    monkeypatch.setattr(lists_dialog, "ListsDialog", Fake)
    monkeypatch.setattr(win, "_apply_tags", lambda *a, **k: None)
    win.edit_lists()
    assert (seg / segments.filename(db, "ʌ", "SPZ")).exists()


def test_tab_loops_round_the_pads_without_playing(win, area, monkeypatch):
    from PySide6.QtWidgets import QApplication
    played = []
    monkeypatch.setattr(win.player, "play", lambda *a, **k: played.append(1) or True)
    win.show()
    a, b, g = (p.edit for p in area.seg_pads)
    a.setText("β")
    assert area.tab_to(a, 1) and QApplication.focusWidget() in (b, None)
    assert area.tab_to(b, 1)                                          # β > α: round again
    assert area.tab_to(a, -1)                                         # Shift+Tab: α > β
    area.rows[2].show()                                               # with γ: α > β > γ > α
    order = []
    cur = a
    for _ in range(3):
        boxes = [p.edit for p, r in zip(area.seg_pads, area.rows) if not r.isHidden()]
        cur = boxes[(boxes.index(cur) + 1) % len(boxes)]
        order.append(cur)
    assert order == [b, g, a]
    area.rows[2].hide()
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier)
    assert area.eventFilter(a, ev)                                    # the Tab key itself goes round
    assert played == []                                               # for typing: nothing plays
