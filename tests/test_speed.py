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
from test_ui import app, win  # noqa: F401,E402  (fixtures)

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
    m.dataChanged.emit(m.index(0, 0), m.index(0, 0))
    assert proxy._hay == {}                                         # and is on any change of the table


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
