# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Speed at full size (the audit, section 3, 25 October 2026): measured on an invented database
of 2,316 lemmas and 58,499 tokens with a soundfile each. These tests check that each speed-up
gives the same answers as before and is never out of date, not the timings themselves."""

import copy
import os
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from lemmatrix import filters as fl, layout, storage  # noqa: E402
from lemmatrix.model import Group, Tag, TagStructure  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


# ---------------------------------------------------------------- the tag structure's cached index

def _structure():
    return TagStructure([Group("Number", [Tag("Singular", "SG", default=True), Tag("Plural", "PL")]),
                         Group("Case", groups=[Group("Core", [Tag("Nominative", "NOM"), Tag("Genitive", "GEN")])])])


def test_lookups_are_built_once_and_follow_every_change():
    ts = _structure()
    i = ts._index()
    for _ in range(100):
        assert ts.find("Plural")[0].code == "PL"
    assert ts._index() is i                                         # not rebuilt for each question
    assert ts.sort(["Genitive", "Plural"]) == ["Plural", "Genitive"]
    ts.groups[0].tags.append(Tag("Dual", "DU"))                     # a tag added in place
    assert ts.find("Dual") and ts.sort(["Dual", "Plural"]) == ["Plural", "Dual"]
    ts.find("Plural")[0].name = "Plurals"                           # a tag renamed in place
    assert ts.find("Plural") is None and ts.find("Plurals")
    ts.groups[1].groups[0].tags.remove(ts.find("Genitive")[0])      # removed
    assert ts.find("Genitive") is None
    ts.groups.insert(0, Group("Frame", [Tag("f1", "f1")]))          # a group added
    assert ts.tags()[0][0].name == "f1"
    ts.groups[1].tags = [Tag("Paucal", "PAU")]                      # a group's list replaced
    assert ts.find("Paucal") and ts.find("Singular") is None
    ts.groups[0].utterances_only = True                             # a rule changed
    assert ts.only_map()[id(ts.groups[0])] is True
    ts.groups[1].usual.append("NOUN")                               # a usual-for hint added
    assert ts.usual_map()[id(ts.groups[1])] == ("NOUN",)


def test_a_copy_has_its_own_index():
    ts = _structure()
    ts.find("Plural")
    c = copy.deepcopy(ts)
    assert c == ts and c.find("Plural")[0] is not ts.find("Plural")[0]
    c.groups[0].tags.append(Tag("Dual", "DU"))
    assert c.find("Dual") and ts.find("Dual") is None


def test_a_whole_new_structure_is_used_at_once():
    db = storage.load(SAMPLES / "Sample.xml")
    db.settings.tags.find("Plural")
    db.settings.tags = _structure()
    db.settings.tags.groups[0].tags[1].code = "PLX"
    assert db.settings.tags.file_codes(["Plural"]) == ["PLX"]


# ---------------------------------------------------------------- folders, folding, search

def test_folders_are_remembered_per_database_and_never_for_an_unsaved_one(tmp_path, monkeypatch):
    p = tmp_path / "LXX.xml"
    assert layout.tokens_folder(p) is layout.tokens_folder(str(p))
    assert layout.tokens_folder(p) == tmp_path / "Soundfiles" / "Tokens"
    monkeypatch.chdir(tmp_path)
    assert layout.tokens_folder("") == tmp_path / "Soundfiles" / "Tokens"   # the current folder, asked each time


def _old_fold(text):
    import unicodedata
    out = [ch for ch in unicodedata.normalize("NFD", text)
           if not unicodedata.combining(ch) and unicodedata.category(ch) != "Lm"]
    return unicodedata.normalize("NFC", "".join(out))


@pytest.mark.parametrize("text", ["goat", "Goat's", "ɗæ̀ær", "kʰàbá", "ŋ́", "Éé", "", "x́ʷ", "İstanbul"])
def test_folding_gives_what_it_always_gave(text):
    assert fl.fold_diacritics(text) == _old_fold(text)
    assert fl.search_form(text) == _old_fold(text).casefold()


def test_the_search_follows_new_rows_and_edited_cells(win):
    proxy = win.all_table.proxy
    m = win.all_table.model_
    proxy.set_search("zzqx")
    assert proxy.rowCount() == 0
    e = win.doc.db.entries[0]
    tr = win.doc.db.settings.token_field("translation").name
    win.doc.edit_entry(e, lambda x: x.tokens[0].set(tr, "zzqx found", win.doc.db.settings.primary_gloss))
    win.refresh()
    proxy.set_search("zzqx")
    assert proxy.rowCount() == 1                                    # the cached text was let go
    proxy._hay[0], proxy._hay[1] = ["stale"], ["kept"]
    m.dataChanged.emit(m.index(0, 0), m.index(0, 0))
    assert proxy._hay.get(0) != ["stale"]                           # a changed row's text is let go
    assert proxy._hay[1] == ["kept"]                                # (and read again), the others' kept
    m.set_rows(list(m.rows))                                        # (section 8); all of it when the
    assert ["kept"] not in proxy._hay.values()                      # table starts again


# ---------------------------------------------------------------- the soundfile folder

def test_the_folder_is_listed_again_only_when_something_changed(win, monkeypatch):
    calls = []
    real = storage.scan_sound_folder
    monkeypatch.setattr(storage, "scan_sound_folder", lambda f: (calls.append(1), real(f))[1])
    win.refresh()
    win.refresh()
    assert len(calls) <= 1                                          # every refresh listed it before
    n = len(calls)
    folder = storage.sound_folder(win.doc.db)
    (folder / "LXX-VXX_new.wav").write_bytes(b"RIFF")              # a file added (a recording)
    win.refresh()
    assert len(calls) == n + 1 and "LXX-VXX_new.wav" in win.sound_files
    win._scan_key = None                                            # back from another program
    win.refresh()
    assert len(calls) == n + 2


# ---------------------------------------------------------------- writing the file

def test_the_faster_writer_writes_the_same_bytes(tmp_path):
    for p in [SAMPLES / "Sample.xml", SAMPLES / "Test-300.xml"]:
        root = storage.to_element(storage.load(p))
        ET.indent(root, space="  ")
        assert storage._tostring(root) == ET.tostring(root, encoding="unicode")
    odd = ET.Element("database", {"a": 'x & "y" <z>\n\tq'})
    ET.SubElement(odd, "e").text = "1 < 2 & 3 > 2"
    ET.SubElement(odd, "empty")
    ET.indent(odd)
    assert storage._tostring(odd) == ET.tostring(odd, encoding="unicode")
    odd.append(ET.Comment("a comment"))                             # anything unusual: ElementTree's own
    assert storage._tostring(odd) == ET.tostring(odd, encoding="unicode")


def test_saving_still_reproduces_the_file(tmp_path):
    src = SAMPLES / "Sample.xml"
    db = storage.load(src)
    assert storage.to_string(db) == src.read_text(encoding="utf-8")


# ---------------------------------------------------------------- the XML viewer

def test_the_xml_viewer_colours_the_lines_in_view(win, app):
    v = win.open_xml_viewer()
    v.show()
    app.processEvents()
    v.text.viewport().repaint()
    h = v.highlighter
    first = v.text.firstVisibleBlock()
    assert first.blockNumber() in h.done
    assert len(first.layout().formats()) == len(h.ranges(first.text()))
    assert len(h.done) < v.text.blockCount()                        # not every line at once
    v.text.verticalScrollBar().setValue(v.text.blockCount() // 2)
    v.text.viewport().repaint()
    assert v.text.firstVisibleBlock().blockNumber() in h.done       # scrolled to: coloured too
    h.restyle()
    assert not h.done                                               # a theme change: coloured again
    v.close()


# ---------------------------------------------------------------- Bulk edit's Fill predicted

def test_fill_predicted_checks_the_database_once(monkeypatch):
    from lemmatrix import bulk, predict
    db = storage.load(SAMPLES / "Test-300.xml")
    tr = db.settings.token_field("translation").name
    for e in db.entries[:40]:
        for t in e.tokens[1:]:
            t.set(tr, "", db.settings.primary_gloss)
    rows = [(e, i) for e in db.entries for i in range(len(e.tokens))]
    before = bulk.plan(db, bulk.TOKENS, rows, bulk.FillPredicted(bulk.predicted_target(db)))
    calls = []
    real = predict.Predictor.refresh
    monkeypatch.setattr(predict.Predictor, "refresh", lambda self, d: (calls.append(1), real(self, d))[1])
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.FillPredicted(bulk.predicted_target(db)))
    assert len(calls) == 1                                          # once per run, not once per token
    assert [(c.row, c.new) for c in p.changes] == [(c.row, c.new) for c in before.changes]
    assert p.changes                                                # it did suggest something


# ---------------------------------------------------------------- the EACW's order

def test_remembered_places_are_the_places():
    from lemmatrix import wordlists as wl
    fresh = wl._places.__wrapped__()
    refs = [i.number for i in wl.get(wl.EACW).items][::7] + ["B001b", "A002c", "CBDI", "RC3", "Z9", "", "xyz"]
    for r in refs:
        assert wl.place(r) == wl._place_in(r, fresh), r


# ---------------------------------------------------------------- stage 1 (25 October, evening)

def test_a_lines_segments_are_found_as_before():
    import random
    from lemmatrix import textgrid as tg
    rnd = random.Random(3)
    for _ in range(200):
        t, entries = 0.0, []
        for _ in range(rnd.randint(0, 40)):
            a = t + rnd.choice([0, 0, 0.0005, rnd.random()])
            b = a + rnd.choice([0.0, 0.0004, rnd.random(), 2 * rnd.random()])
            entries.append((a, b, "x"))
            t = b
        idx = tg._TierIndex(entries)
        for _ in range(30):
            s = rnd.random() * (t + 1) - 0.5
            e = s + rnd.choice([0, 0.0003, rnd.random() * 3])
            assert idx.within(s, e) == tg.segments_in(entries, s, e)
    shuffled = [(2.0, 3.0, "b"), (0.0, 1.0, "a")]                  # out of order: the slow way, same answer
    assert tg._TierIndex(shuffled).within(0.0, 3.0) == tg.segments_in(shuffled, 0.0, 3.0)


def test_the_predictor_is_built_once_in_a_database_with_no_translations(monkeypatch):
    from lemmatrix import predict
    db = storage.load(SAMPLES / "Test-300.xml")
    tr = db.settings.token_field("translation").name
    for e in db.entries:
        for t in e.tokens:
            t.set(tr, "", db.settings.primary_gloss)
    p = predict.Predictor()
    p.refresh(db)
    rebuilt = []
    real = predict.Predictor._rebuild
    monkeypatch.setattr(predict.Predictor, "_rebuild", lambda self: (rebuilt.append(1), real(self))[1])
    for e in db.entries[:50]:
        p.suggest(db, e, e.tokens[0].tags, refresh=False)
    assert rebuilt == []                                            # an empty index is still built


def test_segment_recordings_are_listed_again_only_when_something_changed(win, monkeypatch):
    from lemmatrix import segments
    db = win.doc.db
    d = segments.folder(db)
    d.mkdir(parents=True, exist_ok=True)
    (d / segments.filename(db, "pu", "SP1")).write_bytes(b"RIFF")
    first = segments.recordings(db)
    calls = []
    real = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda self: (calls.append(1), real(self))[1])
    assert segments.recordings(db) == first and calls == []         # remembered
    (d / segments.filename(db, "ʌ", "SP1")).write_bytes(b"RIFF")    # a new recording: listed again
    assert {v.sequence for v in segments.recordings(db)} >= {"pu", "ʌ"} and calls


def test_a_line_edit_lays_the_lines_out_once(win, monkeypatch):
    from lemmatrix import textgrid as tg
    from lemmatrix.model import Text
    db = win.doc.db
    folder = storage.text_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    tg.write_example(folder / "T.TextGrid", {"tx": [(0.0, 1.0, "aa"), (1.0, 2.0, "bb")]}, 2.0)
    db.texts.append(Text("T009", textgrid="T.TextGrid"))
    win.open_utterances()
    texts = win.utterances_window.texts
    texts.refresh()
    texts.table.select_row(db.texts[-1])
    shown = []
    real = texts._show_lines
    monkeypatch.setattr(texts, "_show_lines", lambda: (shown.append(1), real())[1])
    t = texts.current()
    texts._lines_edited(t.id)                                       # what a line edit sends first…
    win.utterances_window.refresh()                                 # …then the change everyone hears
    assert len(shown) == 1
    win.utterances_window.close()


def test_the_matrix_finds_the_same_tokens_as_checking_every_pair():
    from lemmatrix import matrix as mx
    db = storage.load(SAMPLES / "Test-300.xml")
    specs = mx.auto_specs(db, db.entries)
    loose = [mx.Spec(frozenset([n]), mx.LOOSE) for n in sorted({n for s in specs[:6] for n in s.tags})]
    cfg = mx.MatrixConfig(x=specs + loose + [mx.Spec.citation()])
    lay = mx.lemma_tag_layout(db, db.entries, cfg)
    defaults = mx.default_names(db)
    order = mx.global_order(db)
    for r, row in enumerate(lay.rows):
        for c, col in enumerate(lay.cols):
            hits = [(row.entry, t) for t in row.entry.tokens if mx.fits(t.tags, col.spec, defaults)]
            want = mx._sorted_hits(hits, order, defaults) if hits else None
            assert lay.cells.get((r, c)) == want, (row.entry.ref, col.spec)


def test_the_matrix_measures_the_same_with_its_memory(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window as mw
    db = win.doc.db
    lay = mx.lemma_tag_layout(db, db.entries, mx.MatrixConfig(x=mx.auto_specs(db, db.entries)))
    v = win.lt_view
    d = v.delegate
    v.model_.set_layout(lay)
    plain = {(r, c): (d.cell_width(r, c, h), d.cell_height(r, c, h)) for (r, c), h in lay.cells.items()}
    d.begin_pass()
    remembered = {(r, c): (d.cell_width(r, c, h), d.cell_height(r, c, h)) for (r, c), h in lay.cells.items()}
    d.end_pass()
    assert remembered == plain and d._memo is None
    assert mw.LEMMA_TAG is not None


# ---------------------------------------------------------------- section 8, step 1 (25 October)
# An edit redraws only the rows of the lemmas it changed; the Lemma/Tag matrix measures only
# their cells again. The same answers as starting again, and never out of date.

def _resets(model):
    seen = []
    model.modelReset.connect(lambda: seen.append(1))
    return seen


def _edit(win, entry, text):
    tr = win.doc.db.settings.token_field("translation").name
    lang = win.doc.db.settings.primary_gloss
    win.doc.edit_entry(entry, lambda x: x.tokens[0].set(tr, text, lang), "Edit")


def _after_edit(win):
    """What the refresh timer does after an edit (its timeout, at once)."""
    assert win._refresh_timer.isActive()
    win._refresh_timer.stop()
    win.refresh(after_edit=True)


def test_an_edit_redraws_only_its_rows_in_all_data(win):
    from lemmatrix.ui.main_window import ALL_DATA
    db = win.doc.db
    win.tabs.setCurrentIndex(ALL_DATA)
    win.refresh()
    t = win.all_table
    t.set_multi_select(True)
    picked = [r for r in t.visible_rows() if r.entry is db.entries[3]][:1] + \
             [r for r in t.visible_rows() if r.entry is db.entries[5]][:1]
    t.select_rows(picked)
    resets = _resets(t.model_)
    changed = []
    t.model_.dataChanged.connect(lambda a, b, *_: changed.append((a.row(), b.row())))
    _edit(win, db.entries[3], "zzqx edited")
    _after_edit(win)
    assert not resets                                               # started again before
    rows = {r for a, b in changed for r in range(a, b + 1)}
    assert rows and all(t.model_.rows[r].entry is db.entries[3] for r in rows)
    assert len(t.selected_rows()) == 2                              # the selection is untouched
    shown = [t.model_.data(t.model_.index(r, c)) for r in rows for c in range(t.model_.columnCount())]
    assert any("zzqx edited" in (x or "") for x in shown)
    win.doc.undo.undo()                                             # undo: the same
    _after_edit(win)
    assert not resets
    # a token added changes the rows: the table starts again
    win.doc.edit_entry(db.entries[3], lambda x: x.tokens.append(x.tokens[0].copy()), "Add token")
    _after_edit(win)
    assert resets


def test_the_search_drops_an_edited_row_that_no_longer_matches(win):
    from lemmatrix.ui.main_window import ALL_DATA
    db = win.doc.db
    win.tabs.setCurrentIndex(ALL_DATA)
    _edit(win, db.entries[2], "zzqx one")
    _after_edit(win)
    proxy = win.all_table.proxy
    proxy.set_search("zzqx")
    assert proxy.rowCount() == 1
    _edit(win, db.entries[2], "something else")
    _after_edit(win)
    assert proxy.rowCount() == 0                                    # filtered again, without a reset
    _edit(win, db.entries[4], "zzqx two")
    _after_edit(win)
    assert proxy.rowCount() == 1


def test_an_edit_redraws_only_its_row_in_the_lemma_list(win):
    from lemmatrix.model import Entry
    db = win.doc.db
    resets = _resets(win.lemmas.model_)
    win.doc.edit_entry(db.entries[4], lambda x: x.set("Gloss", "edited", "en"), "Edit")
    assert not resets
    win.doc.undo.undo()
    assert not resets
    win.doc.add_entry(Entry(ref="D998"))                            # a lemma added: started again
    assert resets
    assert len(win.lemmas.model_.rows) == len(db.entries)


def test_a_lemma_naming_the_edited_one_in_from_is_redrawn_too(win):
    db = win.doc.db
    a, b = db.entries[1], db.entries[4]
    b.from_lemmas = [a.id]
    assert win._with_dependants(frozenset([id(a)])) == frozenset([id(a), id(b)])
    assert win._with_dependants(None) is None


def test_other_changes_still_redraw_everything(win):
    from lemmatrix.ui.main_window import ALL_DATA
    win.tabs.setCurrentIndex(ALL_DATA)
    win.refresh()
    t = win.all_table
    changed = []
    t.model_.dataChanged.connect(lambda a, b, *_: changed.append((a.row(), b.row())))
    win.doc.changed.emit()                                          # a settings change, a list…
    _after_edit(win)
    assert (0, t.model_.rowCount() - 1) in changed


def _matrix(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    db = win.doc.db
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = mx.auto_specs(db, db.entries)[:6]
    win.refresh()
    return win.lt_view


def _sizes(v):
    hh, vh = v.horizontalHeader(), v.verticalHeader()
    return ([hh.sectionSize(i) for i in range(hh.count())], [vh.sectionSize(i) for i in range(vh.count())])


def test_lemma_tag_measures_only_the_edited_lemma_again(win, monkeypatch):
    v = _matrix(win)
    db = win.doc.db
    lay = v.model_.layout_
    r0 = next(r for (r, c) in lay.cells)
    entry = lay.rows[r0].entry
    measured = []
    real = type(v.delegate).cell_width
    monkeypatch.setattr(type(v.delegate), "cell_width",
                        lambda d, r, c, hits: (measured.append(v.model_.layout_.rows[r].entry), real(d, r, c, hits))[1])
    tr = db.settings.token_field("translation").name
    long = "a much longer translation than any other in the sample database " * 3
    win.doc.edit_entry(entry, lambda x: x.tokens[0].set(tr, long, db.settings.primary_gloss), "Edit")
    _after_edit(win)
    assert measured and all(e is entry for e in measured)          # every lemma measured again before
    after_edit = _sizes(v)
    measured.clear()
    win.refresh()                                                   # measured from scratch
    assert len({id(e) for e in measured}) > 1
    assert _sizes(v) == after_edit                                  # the same sizes as starting again
    win.doc.undo.undo()
    _after_edit(win)
    undone = _sizes(v)
    win.refresh()
    assert _sizes(v) == undone


def test_lemma_tag_measures_everything_when_its_look_changes(win, monkeypatch):
    v = _matrix(win)
    db = win.doc.db
    measured = []
    real = type(v.delegate).cell_width
    monkeypatch.setattr(type(v.delegate), "cell_width",
                        lambda d, r, c, hits: (measured.append(r), real(d, r, c, hits))[1])
    v.set_zoom(1.5)                                                 # zoom: every cell again
    n = len(measured)
    assert n == len(v.model_.layout_.cells)
    measured.clear()
    win.doc.edit_entry(db.entries[0], lambda x: x.set("Gloss", "edited", "en"), "Edit")
    _after_edit(win)
    assert len(measured) < n                                        # zoomed sizes kept for the rest
    v.set_zoom(1.0)
