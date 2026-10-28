# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The EACW's edition 2026-10-27 in Lemmatrix (Josh, 27 October 2026): the first edition that
renumbers items (H, O and P) and deletes some, brought into a database on 2026-10-24 by the editions
notice's Update; the Clarification read from the list as an (i) (format 15, IDEAS.md idea 87); and
the shipped glosses in French, Arabic and Amharic (idea 63)."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import newdb, storage  # noqa: E402
from lemmatrix import wordlist_check as wc  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402
from lemmatrix.model import Token  # noqa: E402

OLD = "2026-10-24"


def _old_db(tmp_path=None):
    """An EACW database on edition 2026-10-24, with its old numbers: what Josh's database is."""
    db = newdb.make(newdb.Choices(base=wl.EACW, items=wl.BASE, region=wl.AFRICA))
    keep = {"A001", "D009", "C001f"}
    db.entries = [e for e in db.entries if e.ref in keep]
    db.metadata.wordlist_version = OLD
    rows = [("H055", "snail", False), ("H056", "tree snail", False),        # now hidden H055b
            ("H057", "ground snail", True),                                  # now H055c, with data
            ("H059", "shell (of snail)", True),                              # now H056
            ("O010", "many", True),                                          # deleted, with data
            ("O011", "some", False),                                         # now O010
            ("P095", "be ill", False),                                       # deleted, empty
            ("P001", "be big", False),                                       # (be) big
            ("P002", "small", False),                                        # a gloss of one's own
            ("D040", "anteater", True),                                      # redesignated, with data
            ("H012", "black jacket", False),                                 # redesignated, empty
            ("P096", "be strong", False), ("P096e", "muscle power", True),   # one's own under P096
            ("O016", "my own", True)]                                        # one's own, past the list
    for ref, gloss, data in rows:
        e = db.new_entry(ref, gloss=gloss)
        if data:
            e.tokens[0].values["Phonetic"] = "ba" + ref
        db.entries.append(e)
    return db


def _by_ref(db):
    return {e.ref: e for e in db.entries}


def test_the_edition_and_its_conversion():
    ed = wl.edition("2026-10-27")
    assert ed is not None and wl.EACW_VERSION == "2026-10-27" and ed.doi == "10.5281/zenodo.23704436"
    conv = wl.conversion_since(OLD)
    assert conv["H056"] == "H055b" and conv["H059"] == "H056" and conv["O011"] == "O010"
    assert conv["O010"] == conv["P095"] == conv["P024b"] == "-"
    assert wl.conversion_since("2026-10-27") == {}
    assert wl.conversion_since("") == conv                       # the first edition too
    assert len(wl.get(wl.EACW).items) == 2553 and sum(i.default for i in wl.get(wl.EACW).items) == 2268
    assert set(conv.values()) - {"-"} <= set(wl.get(wl.EACW).by_number)   # every target is an item


def test_renumbering_an_old_database():
    db = _old_db()
    assert wl.renumber_pending(db)
    rn = wc.renumbering(db)
    after = {e.ref: a for e, a in rn.pairs}
    assert after["H056"].ref == "H055b" and after["H057"].ref == "H055c" and after["H059"].ref == "H056"
    assert after["O011"].ref == "O010"
    assert [e.ref for e in rn.removed] == ["P095"]                     # empty: deleted with its item
    moved = dict(rn.moved_own)
    assert moved["O010"] == "O017"                                     # with data: after O016, one's own
    assert moved["D040"].startswith("D") and after["D040"].ref == moved["D040"]   # anteater keeps its meaning
    assert db.gloss(after["D040"]) == "anteater"
    assert "H012" in after and after["H012"].ref == "H012" and db.gloss(after["H012"]) == "mud wasp"
    assert after["P096e"].ref == "P095e"                               # one's own follows its item
    assert db.gloss(after["P001"]) == "(be) big" and after["P001"].file_gloss == "(be) big"
    assert "P002" not in after                                         # "small" isn't the old list's gloss
    assert "O016" not in after                                         # one's own, nothing takes it
    refs = [a.ref for a in after.values()]
    assert len(refs) == len(set(refs))


def test_the_update_renames_recordings_and_runs_once(tmp_path):
    db = _old_db()
    db.path = str(tmp_path / "Old.xml")
    tokens = tmp_path / "Soundfiles" / "Tokens"
    tokens.mkdir(parents=True)
    for e in db.entries:
        t = e.tokens[0]
        if t.values.get("Phonetic"):
            t.file = db.expected_filename(e, t)
            (tokens / t.file).write_bytes(b"RIFF" + e.ref.encode())
    old_names = {e.ref: e.tokens[0].file for e in db.entries if e.tokens[0].file}
    n, problems = wc.update_file(db)
    assert not problems and n > 0
    assert db.metadata.wordlist_version == wl.EACW_VERSION and not wl.renumber_pending(db)
    by = _by_ref(db)
    e = by["H056"]                                                     # was H059 shell (of snail)
    assert e.get("Phonetic", None) or e.tokens[0].values["Phonetic"] == "baH059"
    assert (tokens / e.tokens[0].file).read_bytes() == b"RIFFH059"
    assert not (tokens / old_names["H059"]).exists() or old_names["H059"] == e.tokens[0].file
    assert "H055b" not in by                                           # empty and now hidden: removed
    assert db.gloss(by["P095"]) == "(be) strong" and "O017" in by      # old P095 (be) ill went, P096 moved up
    assert not any(db.gloss(e) == "be ill" for e in db.entries)
    before = [(e.ref, e.id) for e in db.entries]
    assert wc.renumbering(db) is None                                  # never twice
    p = tmp_path / "Old.xml"
    storage.save(db, p, backup=False)
    back = storage.load(p)
    assert [(e.ref, e.id) for e in back.entries] == before and back.metadata.wordlist_version == "2026-10-27"


def test_the_wordlist_tools_wait_while_numbers_are_old():
    db = _old_db()
    assert wl.gloss_items(db, "shell (of snail)") == [] and wl.unused_item(db, "H058") is None
    assert wl.clarification_for(db, db.entry_by_ref("A001"), "en") == ""
    db.metadata.wordlist_version = wl.EACW_VERSION
    assert wl.clarification_for(db, db.entry_by_ref("A001"), "en") == wl.get(wl.EACW).by_number["A001"].clarification


# ---- idea 87: the Clarification as an (i), format 15 -----------------------------------------
def test_a_format_14_file_loses_its_clarification_field(tmp_path):
    db = newdb.make(newdb.Choices(base=wl.EACW))
    from lemmatrix.model import FieldDef
    db.settings.entry_fields.append(FieldDef("Clarification", role="clarification"))
    db.entry_by_ref("A001").values["Clarification"] = "my own note"
    p = tmp_path / "C.xml"
    storage.save(db, p, backup=False)
    text = p.read_text(encoding="utf-8").replace(f'format="{storage.FORMAT_VERSION}"', 'format="14"')
    assert "my own note" in text
    p.write_text(text, encoding="utf-8")
    back = storage.load(p)
    assert back.settings.entry_field("clarification") is None and back.upgraded
    assert "Clarification" not in back.entry_by_ref("A001").values and back.dropped_fields == ["Clarification"]
    storage.save(back, p, backup=False)
    assert "my own note" not in p.read_text(encoding="utf-8") and f'format="{storage.FORMAT_VERSION}"' in p.read_text(encoding="utf-8")


def test_the_clarification_can_be_switched_off():
    class WS:
        def __init__(self, on):
            self.on = on

        def get_bool(self, key, default):
            return self.on if key == wl.CLARIFICATIONS_KEY else default
    db = newdb.make(newdb.Choices(base=wl.EACW))
    e = db.entry_by_ref("J022a")
    assert wl.clarification_for(db, e, "en", WS(True)) == "Azadirachta indica"
    assert wl.clarification_for(db, e, "en", WS(False)) == ""
    blank = newdb.make(newdb.Choices(base=""))
    blank.entries.append(blank.new_entry("J022a", gloss="neem tree"))
    assert wl.clarification_for(blank, blank.entries[-1], "en") == ""      # no EACW, no (i)
    assert "Clarification: Azadirachta indica" in wl.peek(db, e)


# ---- idea 63: the shipped glosses -----------------------------------------------------------
def test_a_new_eacw_database_takes_the_shipped_glosses(tmp_path):
    db = newdb.make(newdb.Choices(base=wl.EACW, gloss_languages=["en", "fr", "am"]))
    e = db.entry_by_ref("A001")
    assert e.get("Gloss", "fr") == "corps" and e.get("Gloss", "am")
    assert db.metadata.wordlist_glosses == {"fr": wl.GLOSS_EDITION, "am": wl.GLOSS_EDITION}
    assert wl.gloss_status("fr") == "French: machine audited only"
    assert wl.gloss_status("am").startswith("Amharic: partially")
    assert wl.gloss_file("ar-SD") == "arb" and wl.gloss_file("sw") == ""
    p = tmp_path / "G.xml"
    storage.save(db, p, backup=False)
    assert '<glosses lang="fr" edition="2026-10-27" />' in p.read_text(encoding="utf-8")
    assert storage.load(p).metadata.wordlist_glosses == db.metadata.wordlist_glosses


def test_filling_a_language_later_leaves_ones_own():
    db = newdb.make(newdb.Choices(base=wl.EACW))
    db.settings.gloss_languages = ["en", "fr"]
    a, d = db.entry_by_ref("A001"), db.entry_by_ref("D009")
    d.set("Gloss", "nanny", "en", True)                  # re-glossed: its item may not be what it names
    a.set("Gloss", "mon corps", "fr", True)              # filled already: never replaced
    plan = dict((e.ref, v) for e, v in wl.gloss_fill_plan(db, ["fr"]))
    assert "A001" not in plan and "D009" not in plan and plan["A002"] == {"fr": "peau"}


def test_the_notices_update_is_one_undo_step_with_the_recordings(make_win, tmp_path):
    """Opening a database on 2026-10-24: Update renumbers, renames the recordings, removes the empty
    lemmas of deleted and newly hidden items and records the edition; one Ctrl+Z puts it all back."""
    from PySide6.QtWidgets import QApplication
    db = _old_db()
    p = tmp_path / "Old.xml"
    db.path = str(p)
    tokens = tmp_path / "Soundfiles" / "Tokens"
    tokens.mkdir(parents=True)
    for e in db.entries:
        t = e.tokens[0]
        if t.values.get("Phonetic"):
            t.file = db.expected_filename(e, t)
            (tokens / t.file).write_bytes(b"x" + e.ref.encode())
    storage.save(db, p, backup=False)
    w = make_win(storage.load(p))
    box = getattr(w, "_wordlist_notice", None)
    assert box is not None and "renumbers items" in box.text()
    before = sorted((e.ref, e.id) for e in w.doc.db.entries)
    files_before = sorted(x.name for x in tokens.iterdir())
    next(b for b in box.buttons() if b.text() == "Update").click()
    for _ in range(5):
        QApplication.processEvents()
    d = w.doc.db
    assert d.metadata.wordlist_version == wl.EACW_VERSION
    shell = next(e for e in d.entries if e.tokens[0].values.get("Phonetic") == "baH059")
    assert shell.ref == "H056" and (tokens / shell.tokens[0].file).read_bytes() == b"xH059"
    assert sorted(x.name for x in tokens.iterdir()) != files_before
    w.doc.undo.undo()
    assert sorted((e.ref, e.id) for e in d.entries) == before and d.metadata.wordlist_version == OLD
    assert sorted(x.name for x in tokens.iterdir()) == files_before
    box.close()


def test_the_wordlist_tools_offer_the_update_first(make_win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import wordlist_dialogs as wd
    w = make_win(_old_db())
    getattr(w, "_wordlist_notice").close()
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    wd.insert_eacw_items(w)
    wd.check_reference_order(w)
    w.convert_references()
    assert len(shown) == 3 and all("renumbered items" in s for s in shown)


def test_conversions_chain_whatever_their_order():
    """The review: an upward shift, a table's row order, and two renumbering editions in a row."""
    from dataclasses import replace
    import lemmatrix.wordlists as w
    base = w.EDITIONS[0]

    def chain(*tables):
        eds = [base] + [replace(base, version=f"2027-01-0{k}", renumbered=f"t{k}") for k in range(1, len(tables) + 1)]
        saved = w.EDITIONS, w._conversion
        w.EDITIONS = tuple(eds)
        w._conversion = lambda name: tables[int(name[1:]) - 1]
        try:
            return w.conversion_since(base.version)
        finally:
            w.EDITIONS, w._conversion = saved
    assert chain({"P096": "P097", "P097": "P098"}) == {"P096": "P097", "P097": "P098"}
    assert chain({"P096": "P095", "P095": "-"}) == chain({"P095": "-", "P096": "P095"}) == {"P096": "P095", "P095": "-"}
    assert chain({"A": "B", "B": "-"}, {"B": "C", "C": "D"}) == {"A": "C", "B": "-", "C": "D"}


def test_the_lemma_dialogue_never_fills_from_old_numbers():
    db = _old_db()
    from lemmatrix.wordlist_check import has_data
    assert wl.renumber_pending(db)
    assert wl.peek(db, db.entry_by_ref("H055")).count("Not in this database") == 0
    lone = db.new_entry("P094", gloss="be sick")
    lone.set("Gloss", wl.item_gloss_in("P094", "fr"), "fr", True)   # a shipped gloss isn't the researcher's
    db.metadata.wordlist_version = wl.EACW_VERSION
    assert not has_data(db, lone)


def test_a_researchers_own_clarification_is_named_on_upgrade(tmp_path):
    db = newdb.make(newdb.Choices(base=wl.EACW))
    from lemmatrix.model import FieldDef
    db.settings.entry_fields.append(FieldDef("Clarification", role="clarification"))
    db.entry_by_ref("A001").values["Clarification"] = "my own note"
    db.entry_by_ref("J022a").values["Clarification"] = "Azadirachta indica"     # the list's: not named
    p = tmp_path / "C.xml"
    storage.save(db, p, backup=False)
    p.write_text(p.read_text(encoding="utf-8").replace(f'format="{storage.FORMAT_VERSION}"', 'format="14"'),
                 encoding="utf-8")
    notes = "\n".join(storage.load(p).load_notes)
    assert "A001: my own note" in notes and "J022a" not in notes


def test_a_second_language_gloss_with_a_clarification_opens_in_the_lemma_dialogue(make_win):
    """Josh, 27 October: A040 diastema and A008 vein wouldn't open in the lemma dialogue. Their French
    or Arabic gloss has a clarification, so its field is wrapped with the (i), and the + button's count
    of filled glosses read the wrapper's text."""
    from lemmatrix.ui.dialogs import EntryDialog
    db = newdb.make(newdb.Choices(base=wl.EACW, items=wl.BASE, region=wl.AFRICA,
                                  gloss_languages=["en", "ar", "fr", "am"]))
    win = make_win(db)
    refs = _by_ref(db)
    for ref in ("A008", "A039", "A040"):
        dlg = EntryDialog(win, db, refs[ref])
        assert "3 filled" in dlg.others_btn.toolTip()
        assert dlg.fields[("Gloss", "fr")].text() == refs[ref].get("Gloss", "fr")
        dlg.reject()
