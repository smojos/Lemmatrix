# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""A text's TextGrid made from its speech, archiving a TextGrid, and full screen (Josh, 28 October;
DESIGN.md 3.11, 5.1): no Praat needed; tiers cns pht phm mph trs com, translate me in trs, trs the
main tier; name.archiveN.TextGrid beside it, then blank or a working copy."""

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import audio, autogrid, textgrid as tgmod  # noqa: E402

RATE = 16000


def _speech(path, bursts=((0.5, 1.5), (2.6, 3.6), (4.7, 5.5)), seconds=6.5):
    """Three 'utterances': a voiced buzz with a little room noise everywhere."""
    rng = np.random.default_rng(1)
    t = np.arange(int(RATE * seconds)) / RATE
    x = 0.002 * rng.standard_normal(len(t))
    for a, b in bursts:
        m = (t >= a) & (t < b)
        x[m] += 0.3 * np.sin(2 * np.pi * 180 * t[m]) * np.sin(2 * np.pi * 3 * t[m]) ** 2 + 0.05 * np.sin(2 * np.pi * 900 * t[m])
    audio.write_wav(path, x.astype(np.float32), RATE, 16)
    return path


def test_speech_spans_pad_and_merge(tmp_path):
    s, r = audio.read_wav(_speech(tmp_path / "a.wav"))
    spans = autogrid.speech_spans(s, r)
    assert len(spans) == 3
    for (a, b), (sa, sb) in zip(((0.5, 1.5), (2.6, 3.6), (4.7, 5.5)), spans):
        assert sa <= a - 0.15 and sb >= b + 0.1 and sa >= a - 0.45, (a, b, sa, sb)   # about 0.25 s of room
    close = autogrid.speech_spans(*audio.read_wav(_speech(tmp_path / "b.wav", ((0.5, 1.5), (1.9, 2.9)), 3.5)))
    assert len(close) == 1                         # 0.4 s apart: the padding makes one


def test_the_tiers_and_the_main_tier(win):
    tiers = autogrid.tiers_for(win.doc.db)
    assert [t.name for t in tiers][:2] == ["cns", "pht"] and "trs" in [t.name for t in tiers]
    assert autogrid.main_tier(tiers, win.doc.db) == "trs"


def _add_made(win, tmp_path, monkeypatch):
    from lemmatrix.ui import texts as tx
    wav = _speech(tmp_path / "story.wav")
    made = {}

    def fake_exec(dlg):
        dlg.new_wav = wav
        dlg._show_files()
        assert dlg.auto_btn.isEnabled()
        assert dlg.make_from_speech()
        made["dir"] = dlg._auto_dir
        assert dlg.chosen()[0] == "trs"            # the main tier: the translation
        dlg.fields["Title"].setText("Made")
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw = win.open_utterances()
    uw.tabs.setCurrentIndex(0)
    uw.texts.add()
    return uw, win.doc.db.texts[-1], made["dir"]


def test_make_from_the_speech_adds_a_text_with_its_lines(win, tmp_path, monkeypatch):
    uw, t, tmp = _add_made(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    grid = folder / t.textgrid
    assert grid.exists() and (folder / t.file).exists() and t.textgrid.endswith("_Made.TextGrid")
    assert not tmp.exists()                        # the temporary folder went
    names = [i.name for i in tgmod.tiers(grid)]
    assert names[:2] == ["cns", "pht"] and "trs" in names and "com" in names
    assert t.tiers is not None and t.tiers.main == "trs"
    lines = uw.texts.lines_of(t)
    assert len(lines) == 3 and all(ln.values.get("Translation:en") == "translate me" for ln in lines)
    assert win.doc.db.settings.tier_mapping.rule("pht").field == "Phonetic"     # learned for next texts
    assert win.doc.db.settings.tier_mapping.main == "tx"                          # the database's unchanged


def test_right_click_makes_it_for_a_text_without_one(win, tmp_path, monkeypatch):
    from lemmatrix.ui import texts as tx
    from lemmatrix.model import Text
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True, exist_ok=True)
    t = Text(ref="T009")
    t.file_label = "Bare"
    t.file = "LXX-VXX_T009_Bare.wav"
    _speech(folder / t.file)
    win.doc.add_entry(t)
    uw = win.open_utterances()
    uw.tabs.setCurrentIndex(0)
    uw.texts.select(t)
    monkeypatch.setattr(tx.TextDialog, "exec", lambda dlg: 1)
    uw.texts.make_textgrid()
    t = next(x for x in win.doc.db.texts if x.ref == "T009")
    assert t.textgrid and (folder / t.textgrid).exists()
    assert len(uw.texts.lines_of(t)) == 3


def test_a_chosen_textgrid_starts_with_its_translation_as_main(win, tmp_path, monkeypatch):
    from lemmatrix.ui import texts as tx
    from tests.test_texts import _grid, _recording
    wav = _recording(tmp_path / "f.wav")
    _grid(tmp_path / "f.TextGrid")
    seen = {}

    def fake_exec(dlg):
        dlg.new_wav, dlg.new_grid = wav, tmp_path / "f.TextGrid"
        dlg._show_files()
        seen["main"] = dlg.chosen()[0]
        dlg.fields["Title"].setText("Flex")
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw = win.open_utterances()
    uw.texts.add()
    assert seen["main"] == "ft"


def test_archive_and_keep_a_working_copy(win, tmp_path, monkeypatch):
    uw, t, _ = _add_made(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    grid = folder / t.textgrid
    before = grid.read_bytes()
    uw.texts.select(t)
    assert uw.texts.archive_textgrid(keep=True)
    a1 = grid.with_name(grid.name[:-len(".TextGrid")] + ".archive1.TextGrid")
    assert a1.exists() and a1.read_bytes() == before and grid.read_bytes() == before
    assert uw.texts.archive_textgrid(keep=True)
    assert a1.with_name(a1.name.replace("archive1", "archive2")).exists()
    assert len(uw.texts.lines_of(t)) == 3


def test_archive_and_start_blank(win, tmp_path, monkeypatch):
    uw, t, _ = _add_made(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    grid = folder / t.textgrid
    before = grid.read_bytes()
    uw.texts.select(t)
    assert uw.texts.archive_textgrid(keep=False)
    arch = autogrid.archive_path(grid).with_name(grid.name[:-len(".TextGrid")] + ".archive1.TextGrid")
    assert arch.read_bytes() == before
    assert [i.name for i in tgmod.tiers(grid)] == [i.name for i in tgmod.tiers(arch)]   # the same tiers
    assert all(i.count == 0 for i in tgmod.tiers(grid))                               # no segments
    assert uw.texts.lines_of(t) == []
    assert autogrid.is_archive(arch) and not autogrid.is_archive(grid)


def test_full_screen_in_the_main_window(win):
    win.show()
    left = win.main_split.widget(0)
    assert left.isVisible() and not win.panels_hidden()
    win.full_btn.click()
    assert win.full_screen() and not left.isVisible() and win.panels_hidden()
    win.full_btn.click()
    assert not win.full_screen() and left.isVisible() and not win.panels_hidden()
    win.toggle_panels()                            # panels hidden first: they stay hidden afterwards
    win.full_btn.click()
    win.full_btn.click()
    assert left.isVisible() and win.panels_hidden()
    win.toggle_panels()


def test_full_screen_in_texts_and_utterances(win):
    uw = win.open_utterances()
    uw.show()
    uw.tabs.setCurrentIndex(0)
    outer, inner = uw.split.sizes(), uw.texts.page.sizes()
    uw.full_btn.click()
    assert uw.full_screen() and uw.split.sizes()[1] == 0 and uw.texts.page.sizes()[0] == 0
    uw.full_btn.click()
    assert not uw.full_screen() and uw.split.sizes() == outer and uw.texts.page.sizes() == inner


def test_the_full_screen_icons_differ(app):
    from lemmatrix.ui import icons
    a = icons.icon("fullscreen", 32, "#198583").pixmap(32, 32).toImage()
    b = icons.icon("fullscreen-exit", 32, "#198583").pixmap(32, 32).toImage()
    assert a != b and a.pixelColor(6, 6).alpha() > 0
