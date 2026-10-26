# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The comparative wordlists (IDEAS.md idea 40, 22 October 2026): the lists and their mapping,
new databases built on each, format 9, the search, the export and Link to wordlists."""

import os
import re
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import defaults, storage  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402
from lemmatrix.model import SEQ, SEQUENCE, TEXTS, UTTERANCES  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"


# ---- the lists ----------------------------------------------------------
def test_the_lists_and_their_sizes():
    assert len(wl.get(wl.EACW).items) == 2556                    # the final list (23 October 2026)
    assert len(wl.get(wl.CAWL).items) == 1700
    assert len(wl.get(wl.SWADESH).items) == 207
    for lid in wl.LIST_IDS:
        nums = [i.number for i in wl.get(lid).items]
        assert len(nums) == len(set(nums)), lid
    assert [i.number for i in wl.get(wl.CAWL).items] == [f"{n:04d}" for n in range(1, 1701)]
    assert [i.number for i in wl.get(wl.SWADESH).items] == [str(n) for n in range(1, 208)]


def test_the_eacw_as_josh_set_it():
    items = wl.get(wl.EACW).items
    eacw = wl.get(wl.EACW).by_number
    assert "B001b" not in eacw and "V292b" not in eacw         # left out (Josh)
    assert eacw["C001f"].gloss == "mother" and eacw["C001m"].gloss == "father"   # female before male
    assert eacw["C045"].gloss == "white person"
    # the ethnic groups are a template (C + ISO 639-3 code), not items; nothing from Josh's data
    assert not any(re.fullmatch(r"C[A-Z]{3}[fm]?", i.number) for i in items)
    assert not any(i.gloss.lower().startswith("ethnic group") for i in items)
    assert not any(re.search(r"\b(LXX|VXX|SP\d|RS\d)\b", i.gloss) for i in items)
    assert sum(i.default for i in items) == 2274
    assert not eacw["I069f"].default and not eacw["I069m"].default     # Josh, 23 October
    # f and m are reserved for female and male: no series runs into them (J073e husk, then J073g)
    assert eacw["J073g"].gloss == "hair (of maize)" and "J073f" not in eacw
    assert eacw["D009"].taxon == "Capra hircus (Bovidae)"
    assert eacw["J022a"].clarification == "Azadirachta indica"
    assert set(eacw["I069f"].sub) == {"E", "W", "N"}
    for i in items:                                          # file-name-friendly glosses
        assert not set(i.gloss) & set('/\\:*?"<>|,'), i.number


def test_the_versions():
    """Josh, 23 October: base or expanded, and global, Africa or one region."""
    count = lambda items, region: len(wl.version_items(items, region))
    assert count(wl.EXPANDED, wl.AFRICA) == 2556 and count(wl.BASE, wl.AFRICA) == 2274
    assert count(wl.BASE, wl.GLOBAL) == 2055                # blank sub codes only
    for r in wl.REGIONS:
        assert count(wl.BASE, wl.GLOBAL) < count(wl.BASE, r) < count(wl.BASE, wl.AFRICA)
    fonio = wl.get(wl.EACW).by_number["J069"]                # W only
    assert wl.in_version(fonio, wl.BASE, "W") and not wl.in_version(fonio, wl.BASE, "E")
    assert not wl.in_version(fonio, wl.BASE, wl.GLOBAL) and wl.in_version(fonio, wl.BASE, wl.AFRICA)


def test_hidden_variants_take_their_familys_numbers():
    """Josh, 23 October: B033f female warrior, if added, goes with B033m's CAWL 0406 (in the data since
    24 October); elsewhere a hidden item takes its family's numbers, a published one keeps its own."""
    assert wl.other_numbers(wl.EACW, "B033f") == {wl.CAWL: ["0406"]}
    assert wl.other_numbers(wl.EACW, "B033") == {wl.CAWL: ["0406"]}
    assert wl.other_numbers(wl.EACW, "C001") == {wl.CAWL: ["0344", "0345"], wl.SWADESH: ["42", "43"]}   # 24 October
    hidden = [i for i in wl.get(wl.EACW).items if not i.default and i.number[0] not in "BC"
              and not wl.mapped(wl.EACW, i.number, wl.CAWL) and len(wl._gender_family(i.number)) > 1
              and any(wl.mapped(wl.EACW, n, wl.CAWL) for n in wl._gender_family(i.number))]
    assert hidden and all(wl.other_numbers(wl.EACW, i.number).get(wl.CAWL) for i in hidden)


def test_every_mapped_number_exists():
    eacw = wl.get(wl.EACW).by_number
    cawl = wl.get(wl.CAWL).by_number
    for lid in (wl.CAWL, wl.SWADESH):
        for i in wl.get(lid).items:
            assert all(e in eacw for e in i.eacw), (lid, i.number)
            assert all(c in cawl for c in i.cawl), (lid, i.number)


def test_the_mapping_both_ways():
    assert wl.other_numbers(wl.EACW, "C001f") == {wl.CAWL: ["0345"], wl.SWADESH: ["42"]}
    assert wl.other_numbers(wl.CAWL, "0345") == {wl.EACW: ["C001", "C001f"], wl.SWADESH: ["42"]}   # the generic too
    assert wl.other_numbers(wl.SWADESH, "42") == {wl.EACW: ["C001", "C001f"], wl.CAWL: ["0345"]}
    # one number on several lemmas: CAWL brother (elder/younger)
    assert len(wl.mapped(wl.CAWL, "0346", wl.EACW)) > 1


def test_numbers_as_typed():
    assert wl.canon(wl.CAWL, "345") == "0345"
    assert wl.canon(wl.SWADESH, "042") == "42"
    assert wl.canon(wl.EACW, "c001F") == "C001f"
    assert wl.canon(wl.CAWL, "9999") is None
    assert wl.search_term("CAWL 345") == (wl.CAWL, "0345", False)
    assert wl.search_term("swadesh") == (wl.SWADESH, None, False)
    assert wl.search_term("-Swadesh") == (wl.SWADESH, None, True)
    assert wl.search_term("- EACW") == (wl.EACW, None, True)
    assert wl.search_term("Joshua") == wl.search_term("josh") == (wl.EACW, "V139", False)
    assert wl.search_term("cawl 9999")[0] == wl.CAWL        # a wordlist search that finds nothing
    assert wl.search_term("mother") is None


# ---- new databases --------------------------------------------------------
def test_a_new_database_on_the_eacw():
    db = defaults.new_database(wl.EACW)
    assert db.metadata.wordlist_base == wl.EACW
    assert (db.metadata.wordlist_items, db.metadata.wordlist_region) == (wl.BASE, wl.AFRICA)
    assert len(db.entries) == 2274                             # the base list, all of Africa
    e = db.entry_by_ref("C001f")
    assert db.gloss(e) == "mother" and db.word_class(e) == "NOUN"
    assert e.lists == {wl.CAWL: ["0345"], wl.SWADESH: ["42"]}
    assert len(e.tokens) == 1 and not e.tokens[0].tags       # its citation token
    assert db.settings.ref_scheme != SEQUENCE                  # the A–V categories stay
    assert wl.numbers(db, e, wl.EACW) == ["C001f"]
    s = db.settings                                            # Clarification and Taxon, the list's classes
    assert s.entry_field(wl.CLARIFICATION).name == "Clarification" and s.entry_field(wl.TAXON).name == "Taxon"
    assert {"DEM", "CONJ", "INTERROG", "NEG", "PREP", "INTERJ"} <= set(s.word_classes())
    assert db.entry_by_ref("D009").get("Taxon") == "Capra hircus (Bovidae)"
    assert db.word_class(db.entry_by_ref("R3SGDPRX")) == "DEM"
    assert db.entry_by_ref("I069f") is None                    # hidden
    full = defaults.new_database(wl.EACW, wl.EXPANDED, "E")
    assert len(full.entries) == len(wl.version_items(wl.EXPANDED, "E"))
    assert full.entry_by_ref("I069f") is not None and full.entry_by_ref("J069") is None   # fonio: West


def test_new_references_skip_the_lists_numbers():
    """A lemma of one's own never takes a number a hidden EACW item has."""
    db = defaults.new_database(wl.EACW)
    last = max(i.number[:4] for i in wl.get(wl.EACW).items if re.fullmatch(r"O\d{3}[a-z]?", i.number))
    assert db.suggest_reference("O") == f"O{int(last[1:]) + 1:03d}"


def test_reserved_letters_and_hidden_items():
    db = defaults.new_database(wl.EACW)
    assert wl.reserved("D123f") == ("D123", "f") and wl.reserved("D123b") is None
    assert wl.next_letter(db, "J073") == "J073i"               # b–e, g, h taken; f and m skipped
    e = db.entry_by_ref("I069")
    assert e is None
    item = wl.unused_item(db, "I069f")
    assert item is not None and item.gloss == "excision"
    assert [i.number for i in wl.gloss_items(db, "excision")] == ["I069f"]
    assert wl.unused_item(db, "C001f") is None                 # the database has it
    b = db.entry_by_ref("B033m")
    assert [i.number for i in wl.missing_family(db, b)] == ["B033", "B033f"]
    tip = wl.peek(db, b)
    assert "B033f  female warrior  (hidden)" in tip and tip.startswith("EACW B033m · CAWL 0406")


def test_insert_position_and_order():
    db = defaults.new_database(wl.EACW)
    k = wl.insert_position(db.entries, "B033f")
    assert db.entries[k - 1].ref == "B033m" or db.entries[k - 1].ref < "B033f"
    shuffled = list(reversed(db.entries))
    assert [e.ref for e in wl.eacw_order(shuffled)] == [e.ref for e in db.entries]


@pytest.mark.parametrize("base, first, after", [(wl.CAWL, "0001", "1701"), (wl.SWADESH, "001", "208")])
def test_a_new_database_on_cawl_or_swadesh_has_no_categories(base, first, after):
    db = defaults.new_database(base)
    s = db.settings
    assert s.ref_scheme == SEQUENCE and not s.ref_categories     # Josh: the reference system is removed
    assert db.entries[0].ref == first
    # utterances and texts take the next number, one sequence with the lemmas
    for kind in (UTTERANCES, TEXTS):
        cats = s.categories(kind)
        assert [c.letter for c in cats] == [SEQ] and cats[0].label == "Next number"
        assert db.suggest_utterance_reference(SEQ) == after
    assert db.suggest_reference(SEQ) == after
    assert s.category(first) is None and s.ref_prefix(SEQ) == ""


def test_a_cawl_database_glosses_and_word_classes():
    db = defaults.new_database(wl.CAWL)
    e = db.entry_by_ref("0345")
    assert e.lists == {wl.EACW: ["C001", "C001f"], wl.SWADESH: ["42"]}
    assert db.gloss(e) == "mother"            # the EACW's gloss until SIL allows the CAWL's own
    assert db.word_class(e) == "NOUN"
    assert db.word_class(db.entry_by_ref("0140")) == "VERB"     # eat
    assert all(not set(x.file_gloss) & set('/\\:*?"<>|') for x in db.entries)


def test_format_9_round_trip(tmp_path):
    db = defaults.new_database(wl.SWADESH)
    p = tmp_path / "S.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    text = p.read_text(encoding="utf-8")
    assert f'<database format="{storage.FORMAT_VERSION}">' in text and '<wordlist base="SWADESH"' in text
    assert re.search(r'<entry ref="042"[^>]* eacw="C001 C001f" cawl="0345"', text)
    assert '<references scheme="sequence" digits="3"' in text
    back = storage.load(p)
    assert back.metadata.wordlist_base == wl.SWADESH
    assert back.entry_by_ref("042").lists == {wl.EACW: ["C001", "C001f"], wl.CAWL: ["0345"]}
    assert not back.upgraded


def test_a_format_8_database_opens_without_numbers(tmp_path):
    p = tmp_path / "Old.xml"
    shutil.copy2(SAMPLES / "Sample.xml", p)
    text = re.sub(r'<database format="\d+">', '<database format="8">', p.read_text(encoding="utf-8"))
    p.write_text(text, encoding="utf-8")
    db = storage.load(p)
    assert db.upgraded and not db.metadata.wordlist_base
    assert not any(e.lists for e in db.entries)


# ---- search, export, linking (no Qt) --------------------------------------
def _eacw_db_with_forms():
    db = defaults.new_database(wl.EACW)
    for ref, form in (("C001f", "mar"), ("C001m", "baba"), ("A001", "gum")):
        db.entry_by_ref(ref).set("Lemma", form)
    return db


def test_search_matches():
    db = _eacw_db_with_forms()
    e = db.entry_by_ref("C001f")
    assert wl.search_match(db, e, "CAWL 345") is True
    assert wl.search_match(db, e, "swadesh 42") is True
    assert wl.search_match(db, e, "SWADESH") is True
    assert wl.search_match(db, e, "eacw c001f") is True
    assert wl.search_match(db, e, "CAWL 1") is False
    assert wl.search_match(db, e, "mother") is None
    assert wl.describe(db, e) == "EACW C001f · CAWL 0345 · Swadesh 42"


def test_export_every_item_in_order_with_blanks():
    db = _eacw_db_with_forms()
    header, rows = wl.table(db, wl.SWADESH, template="{Lemma>Phonetic>Phonemic}")
    assert header == ["Swadesh", "Lemma", "Gloss"]
    assert len(rows) == 207 and [r[0] for r in rows] == [str(n) for n in range(1, 208)]
    assert rows[41] == ["42", "mar", "mother"]
    assert rows[0][1] == ""                                  # I: no form yet, a blank row
    text = wl.tsv(header, rows)
    assert text.splitlines()[42] == "42\tmar\tmother"


def test_gloss_matches_for_lemmas_of_ones_own():
    """Josh's case: a database started from Swadesh, with lemmas of his own added later."""
    db = defaults.new_database(wl.SWADESH)
    e = db.new_entry("208", lemma="kʊɲ", gloss="Mother")       # his own, no numbers
    db.entries.append(e)
    db.entry_by_ref("042").set("Lemma", "mar")
    m = wl.gloss_matches(db, wl.EACW)
    assert ("C001f", e) not in m                   # 042 carries C001f already
    db.entry_by_ref("042").lists = {}
    m = wl.gloss_matches(db, wl.EACW)
    assert ("C001f", e) in m
    header, rows = wl.table(db, wl.EACW, [("C001f", e)], template="{Lemma>Phonetic>Phonemic}")
    row = next(r for r in rows if r[0] == "C001f")
    assert row[1] == "kʊɲ"


def test_link_plan_for_an_existing_eacw_database():
    db = defaults.new_database("")
    for ref, gloss in (("C001f", "mother"), ("D099", "not in the list really"), ("Z999", "x")):
        db.entries.append(db.new_entry(ref, gloss=gloss))
    plan = dict((e.ref, new) for e, new in wl.link_plan(db, wl.EACW))
    assert plan["C001f"] == {wl.CAWL: ["0345"], wl.SWADESH: ["42"]}
    assert "Z999" not in plan


# ---- the windows ------------------------------------------------------------
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QMessageBox  # noqa: E402


@pytest.fixture
def win(make_win, tmp_path):
    """An EACW database with forms (the shared window factory, conftest.py)."""
    db = _eacw_db_with_forms()
    db.path = str(tmp_path / "W.xml")
    storage.save(db, db.path, backup=False)
    return make_win(storage.load(db.path))


def _search(win, text):
    win.lemma_search.setText(text)
    win._search_timers["lemma"].timeout.emit()
    return win.lemmas.visible_rows()


def test_the_lemma_lists_search(win):
    rows = _search(win, "CAWL 351")                       # father's sister: C014f, and C014 is hidden
    assert [e.ref for e in rows] == ["C014f"]
    assert win.lemmas.current_row() is rows[0]              # selected, so the matrix follows
    assert len(_search(win, "SWADESH")) == sum(1 for e in win.doc.db.entries if e.lists.get(wl.SWADESH))
    assert sorted(e.ref for e in _search(win, "SWADESH 42, CAWL 1")) == ["A001", "C001", "C001f"]
    assert _search(win, "CAWL 9999") == []
    assert [e.ref for e in _search(win, "mother")][0] == "C001f"    # plain searches as before
    assert len(_search(win, "")) == 2274


def test_the_reference_tooltip(win):
    col = next(c for c in win._lemma_columns() if c.key == "ref")
    assert col.tooltip(win.doc.db.entry_by_ref("C001f")).startswith("EACW C001f · CAWL 0345 · Swadesh 42")


def test_export_dialog_remembers_ticked_matches(win, monkeypatch):
    from PySide6.QtGui import QGuiApplication
    from lemmatrix.ui.wordlist_dialogs import WordlistExportDialog
    db = win.doc.db
    own = db.new_entry("C900", lemma="nyaŋ", gloss="crocodile (big)")
    db.entries.append(own)
    d = WordlistExportDialog(win)
    d.which.setCurrentIndex(d.which.findData(wl.SWADESH))
    d.preset.setCurrentIndex(d.preset.findData("{Lemma>Phonetic>Phonemic}"))
    d._preset_chosen(d.preset.currentIndex())                  # the Lemma field first (the old rule)
    d.copy()
    text = QGuiApplication.clipboard().text()
    assert text.splitlines()[0] == "Swadesh\tLemma\tGloss" and "42\tmar\tmother" in text
    # nothing for Swadesh to match here; the CAWL by its EACW glosses
    d.which.setCurrentIndex(d.which.findData(wl.CAWL))
    assert d.table.rowCount() == len(d.matches)


def test_export_pdf(win, tmp_path):
    from lemmatrix.ui.wordlist_dialogs import write_pdf
    header, rows = wl.table(win.doc.db, wl.SWADESH, template="{Lemma>Phonetic>Phonemic}")
    p = tmp_path / "s.pdf"
    write_pdf(str(p), win.doc.db, wl.SWADESH, header, rows)
    assert p.read_bytes()[:4] == b"%PDF" and p.stat().st_size > 2000


def test_link_to_wordlists_is_one_undo_step(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from lemmatrix.ui import main_window, wordlist_dialogs
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    db = defaults.new_database("")
    for ref, gloss in (("C001f", "mother"), ("A001", "body")):
        db.entries.append(db.new_entry(ref, gloss=gloss))
    db.path = str(tmp_path / "L.xml")
    storage.save(db, db.path, backup=False)
    w = main_window.MainWindow()
    w.load_database(storage.load(db.path))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][0], True))
    wordlist_dialogs.link_to_wordlists(w)
    d = w.doc.db
    assert d.metadata.wordlist_base == wl.EACW
    assert d.entry_by_ref("C001f").lists == {wl.CAWL: ["0345"], wl.SWADESH: ["42"]}
    w.doc.undo.undo()
    assert not d.metadata.wordlist_base and not d.entry_by_ref("C001f").lists
    w.doc.undo.setClean()
    w.close()


def test_the_wordlist_choice_hovers(app):
    """The New database window's lists give their citations on hover (the old start-list box,
    removed 25 October as dead code, had this test)."""
    from lemmatrix.ui.wordlist_dialogs import WordlistChoice
    d = WordlistChoice()
    assert d.choice() == wl.EACW                                 # recommended
    tips = {b.property("list"): b.toolTip() for b in d.group.buttons()}
    assert tips[wl.EACW].startswith("Smolders, Joshua. 2026. The Extended African Comparative Wordlist: A digital lexical organization system for field linguists.")
    assert "Snider" in tips[wl.CAWL] and "Swadesh" in tips[wl.SWADESH]
