# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The Anonymous archive and the Ethical archive (IDEAS.md idea 44), and format 8."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from lemmatrix import anonymise, defaults, notebook as nbmod, storage, textgrid as tgmod  # noqa: E402
from lemmatrix.anonymise import ANONYMOUS, ETHICAL, Options  # noqa: E402
from lemmatrix.model import Person, Text  # noqa: E402

from test_ui import app, win  # noqa: F401,E402 (fixtures)

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _db(tmp_path):
    """A copy of the sample with real-looking people, a text with a TextGrid, comments and a
    notebook (all invented: nothing here is anyone's data)."""
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "LXX-VXX_Lexicon.xml")
    shutil.copytree(SAMPLES / "Soundfiles", tmp_path / "Soundfiles", ignore=shutil.ignore_patterns("Texts", "Utterances"))
    db = storage.load(tmp_path / "LXX-VXX_Lexicon.xml")
    db.texts.clear()                    # the sample's own text and clips: this fixture makes its own
    db.utterances.clear()
    md = db.metadata
    md.language_name, md.variety_name = "Sample language", "Hill"
    md.participants = [Person("KDB", "Kuku Dabi", "a farmer", "Consent/KDB.pdf", identifiable=True,
                              audio_sharing=True),
                       Person("HMA", "Hana Mali", "a teacher", "Consent/HMA.pdf")]
    md.researchers = [Person.researcher("JS", "Jo Smith", email="jo@example.org"),
                      Person("AB", "Ann Bell", "assistant", email="ann@example.org")]
    md.author = "Jo Smith"
    (tmp_path / "Consent").mkdir()
    (tmp_path / "Consent" / "KDB.pdf").write_bytes(b"%PDF KDB")
    (tmp_path / "Consent" / "HMA.pdf").write_bytes(b"%PDF HMA")
    for i, e in enumerate(db.entries):
        for t in e.tokens:
            t.speaker = "KDB" if i % 2 == 0 else "HMA"
    db.entries[0].tokens[0].set("Comment", "Kuku said this twice; ask Hana Mali and KDB again")
    db.entries[1].tokens[0].set("Translation", "Hana's goat", "en")
    db.settings.tags.leaf_groups()[0][1].tags[0].description = "as Kuku says it"
    texts = tmp_path / "Soundfiles" / "Texts"
    texts.mkdir(parents=True)
    tgmod.write_example(texts / "LXX-VXX_T001_Kuku_story.TextGrid",
                        {"tx@KDB": [(0.0, 1.0, "dabuuba")], "ft@KDB": [(0.0, 1.0, "Kuku told Hana")]}, 2.0)
    (texts / "LXX-VXX_T001_Kuku_story.wav").write_bytes(b"RIFF")
    db.texts.append(Text("T001", file_label="Kuku story", participants=["KDB"], researchers=["JS"],
                         file="LXX-VXX_T001_Kuku_story.wav", textgrid="LXX-VXX_T001_Kuku_story.TextGrid",
                         values={"Title": "Kuku's story"}))
    book = nbmod.Notebook()
    s = book.add_session("2026-10-01")
    s.participants, s.researchers, s.notes = ["KDB", "HMA"], ["JS"], "Paid Hana for five sessions. H1 looks good."
    return db, book


def _all_text(folder: Path) -> str:
    out = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".xml", ".notebook", ".workspace", ".textgrid"):
            out.append(f.read_text(encoding="utf-8", errors="replace"))
        out.append(f.name)
    return "\n".join(out)


# ---------------------------------------------------------------- format 8

def test_format_8_ticks_researchers_and_writes_both_ticks(tmp_path):
    p = tmp_path / "Old.xml"
    text = (SAMPLES / "Sample.xml").read_text(encoding="utf-8")
    text = text.replace(f'format="{storage.FORMAT_VERSION}"', 'format="7"')
    text = text.replace(' identifiable="yes"', "").replace(' identifiable="no"', "").replace(' audio-sharing="no"', "")
    text = text.replace(' audio-sharing="yes"', "")
    p.write_text(text, encoding="utf-8")
    db = storage.load(p)
    assert db.upgraded
    assert all(r.identifiable for r in db.metadata.researchers)         # ticked on opening
    assert not any(x.identifiable or x.audio_sharing for x in db.metadata.participants)
    storage.save(db, p, backup=False)
    saved = p.read_text(encoding="utf-8")
    assert f'<database format="{storage.FORMAT_VERSION}">' in saved
    assert '<researcher code="JJA" name="Joshua J Alexander" identifiable="yes" />' in saved
    assert ('<participant code="DML" name="Dzosho Mofo Lakanoro" consent="Documentation/DML consent form.pdf" '
            'identifiable="no" audio-sharing="no" />') in saved
    again = storage.load(p)
    assert not again.upgraded and again.metadata.researchers[0].identifiable


def test_a_researcher_unticked_stays_unticked(tmp_path):
    db = storage.load(SAMPLES / "Sample.xml")
    db.metadata.researchers.append(Person.researcher("RS2"))     # the sample has one researcher
    db.metadata.researchers[1].identifiable = False
    storage.save(db, tmp_path / "S.xml", backup=False)
    back = storage.load(tmp_path / "S.xml")
    assert [r.identifiable for r in back.metadata.researchers] == [True, False]


def test_new_researchers_are_identifiable_new_participants_not():
    assert all(p.identifiable for p in defaults.default_researchers())
    assert not any(p.identifiable for p in defaults.default_participants())
    assert Person.researcher("RS9").identifiable and not Person("SP9").identifiable


def test_the_lists_add_a_ticked_researcher(win):
    from PySide6.QtCore import Qt
    from lemmatrix.ui.lists_dialog import PeopleEditor
    ed = PeopleEditor(win.doc.db, [], False, lambda c: 0)
    ed._add_row(Person.researcher("RS7", "New one"))
    it = ed.table.item(0, ed.col("identifiable"))
    assert it.checkState() == Qt.Checked
    it.setCheckState(Qt.Unchecked)
    assert not ed.people()[0].identifiable


# ---------------------------------------------------------------- the anonymous archive

def test_the_anonymous_archive_names_nobody_and_renumbers_every_code(tmp_path):
    import pyzipper
    db, book = _db(tmp_path)
    opts = Options.for_kind(ANONYMOUS)
    opts.notebook, opts.consent_password = True, "pw"
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    md = out.metadata
    assert [(p.code, p.name, p.description, p.consent) for p in md.participants] == [
        ("SP1", "", "", ""), ("SP2", "", "", "")]
    assert [(p.code, p.name, p.email) for p in md.researchers] == [("RS1", "", ""), ("RS2", "", "")]
    assert md.author == "RS1"
    assert md.language_name == "LXX" and md.variety_name == "VXX"            # names become codes
    assert {t.speaker for e in out.entries for t in e.tokens} == {"SP1", "SP2"}
    assert out.entries[0].tokens[0].get("Comment") == "SP1 said this twice; ask SP2 and SP1 again"
    assert out.entries[1].tokens[0].get("Translation", "en") == "SP2's goat"
    t = out.texts[0]
    assert t.participants == ["SP1"] and t.researchers == ["RS1"] and t.get("Title") == "SP1's story"
    assert "Kuku" not in t.textgrid and "Kuku" not in t.file
    grid = tmp_path / "out" / "Soundfiles" / "Texts" / t.textgrid
    tiers = tgmod.tiers(grid)
    assert sorted(x.name for x in tiers) == ["ft@SP1", "tx@SP1"]
    assert "SP1 told SP2" in grid.read_text(encoding="utf-8")
    assert not list((tmp_path / "out").rglob("*.wav"))                        # no recordings at all
    back = nbmod.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).notebook").session("2026-10-01")
    assert back.participants == ["SP1", "SP2"] and back.researchers == ["RS1"]
    assert back.notes.startswith("Paid SP2 for five sessions.")
    everything = _all_text(tmp_path / "out")
    for gone in ("Kuku", "Dabi", "Hana", "Mali", "Jo Smith", "Ann Bell", "KDB", "HMA", "jo@example.org",
                 "farmer", "Consent/"):
        assert gone not in everything, gone
    with pyzipper.AESZipFile(tmp_path / "out" / "LXX-VXX_Lexicon consent forms (password).zip") as zf:
        zf.setpassword(b"pw")
        assert zf.read("SP1/consent.pdf") == b"%PDF KDB"
        key = zf.read("key.csv").decode("utf-8-sig")
        assert sorted(zf.namelist()) == ["SP1/consent.pdf", "SP2/consent.pdf", "key.csv"]   # names readable without the password
    assert "participant,KDB,SP1" in key and "researcher,AB,RS2" in key
    assert rep.key_written and "key" in anonymise.summary(rep, opts)
    assert db.metadata.participants[0].name == "Kuku Dabi"                     # the original is untouched
    assert db.entries[0].tokens[0].speaker == "KDB"


def test_no_key_without_the_zip(tmp_path):
    db, book = _db(tmp_path)
    opts = Options.for_kind(ANONYMOUS)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    assert not rep.key_written and not list((tmp_path / "out").glob("*.zip"))
    assert "can't be undone" in anonymise.summary(rep, opts)
    assert "KDB" not in _all_text(tmp_path / "out")


def test_hiding_the_language_and_variety_codes(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.language_code, db.metadata.variety_code = "BDI", "MGJ"
    for e in db.entries:
        for t in e.tokens:
            if t.file:
                t.file = t.file.replace("LXX-VXX", "BDI-MGJ")
    db.path = str(tmp_path / "BDI-MGJ_Lexicon.xml")
    opts = Options.for_kind(ANONYMOUS)
    opts.hide_language_code = opts.hide_variety_code = True
    anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    md = out.metadata
    assert (md.language_code, md.language_name, md.variety_code, md.variety_name) == ("LXX", "LXX", "VXX", "VXX")
    assert all("BDI" not in t.file and "MGJ" not in t.file for e in out.entries for t in e.tokens)
    assert "BDI" not in _all_text(tmp_path / "out") and "Hill" not in _all_text(tmp_path / "out")


def test_only_the_language_code_hidden(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.language_code, db.metadata.variety_code = "BDI", "MGJ"
    opts = Options.for_kind(ANONYMOUS)
    opts.hide_language_code = True
    out, _ = anonymise.anonymise(db, book, opts, anonymise.Report())
    assert (out.metadata.language_code, out.metadata.variety_code) == ("LXX", "MGJ")


# ---------------------------------------------------------------- the ethical archive

def test_the_ethical_archive_names_only_the_identifiable(tmp_path):
    db, book = _db(tmp_path)
    opts = Options.for_kind(ETHICAL)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (ethical).xml")
    kdb, hma = out.metadata.participants
    assert (kdb.code, kdb.name, kdb.description, kdb.consent) == ("KDB", "Kuku Dabi", "a farmer", "")
    assert (hma.code, hma.name, hma.description, hma.consent) == ("HMA", "", "", "")
    js, ab = out.metadata.researchers
    assert (js.name, js.email) == ("Jo Smith", "jo@example.org")               # identifiable: email kept
    assert (ab.name, ab.email, ab.description) == ("", "", "")
    assert out.metadata.author == "Jo Smith" and out.metadata.language_name == "Sample language"
    assert out.entries[0].tokens[0].get("Comment") == "Kuku said this twice; ask HMA and KDB again"
    assert out.entries[1].tokens[0].get("Translation", "en") == "HMA's goat"
    # recordings: only Kuku's (he agreed to audio sharing); Hana's are left out
    copied = {f.name for f in (tmp_path / "out" / "Soundfiles" / "Tokens").glob("*.wav")}
    kuku = {t.file for e in db.entries for t in e.tokens if t.file and t.speaker == "KDB"}
    hana = {t.file for e in db.entries for t in e.tokens if t.file and t.speaker == "HMA"}
    assert copied and copied <= kuku and not copied & hana
    assert rep.withheld_recordings == sum(1 for e in db.entries for t in e.tokens if t.file and t.speaker == "HMA")
    assert (tmp_path / "out" / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.wav").exists()
    grid = (tmp_path / "out" / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.TextGrid").read_text(encoding="utf-8")
    assert "Kuku told HMA" in grid and "tx@KDB" in grid                        # codes stay
    assert "Hana" not in _all_text(tmp_path / "out")
    assert "identifiable people kept their names" in anonymise.summary(rep, opts)


def test_an_unidentifiable_owner_becomes_their_code(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.author = "Ann Bell"
    out, _ = anonymise.anonymise(db, book, Options.for_kind(ETHICAL), anonymise.Report())
    assert out.metadata.author == "AB"


def test_a_text_with_a_speaker_who_did_not_agree_keeps_its_recording_back(tmp_path):
    db, book = _db(tmp_path)
    db.texts[0].participants = ["KDB", "HMA"]
    rep = anonymise.export(db, book, tmp_path / "out", Options.for_kind(ETHICAL))
    texts = tmp_path / "out" / "Soundfiles" / "Texts"
    assert not list(texts.glob("*.wav")) and list(texts.glob("*.TextGrid"))
    assert rep.withheld_recordings >= 1


# ---------------------------------------------------------------- the researcher's own work stays out

@pytest.mark.parametrize("kind", [ANONYMOUS, ETHICAL])
def test_the_notebook_and_workspace_stay_out_by_default(tmp_path, kind):
    """Josh, 22 October: the notebook, Cogitate and the workspace are the researcher's own work,
    not archive data: both archives leave the notebook out unless it is ticked, and the workspace
    is always blank."""
    db, book = _db(tmp_path)
    opts = Options.for_kind(kind)
    assert not opts.notebook
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    assert not list((tmp_path / "out").glob("*.notebook")) and not rep.notebook
    ws = next((tmp_path / "out").glob("*.workspace")).read_text(encoding="utf-8")
    assert "<matrix" not in ws and "session" not in ws
    assert "your own work" in anonymise.summary(rep, opts)


def test_the_defaults_of_each_archive():
    a, e = Options.for_kind(ANONYMOUS), Options.for_kind(ETHICAL)
    assert (a.notebook, a.with_recordings, a.place_levels) == (False, False, 1)
    assert (e.notebook, e.with_recordings, e.place_levels) == (False, True, 0)


# ---------------------------------------------------------------- the dialogue

def test_the_dialogue_switches_its_defaults(win):
    from lemmatrix.ui.export_dialog import ArchiveExportDialog
    d = ArchiveExportDialog(win, ANONYMOUS)
    assert "anonymous archive" in d.windowTitle() and d.ai_note.isVisibleTo(d)
    assert not d.notebook.isChecked() and not d.recordings.isEnabled() and d.places.currentData() == 1
    assert "anonymous archive" in d.folder.text()
    o = d.options()
    assert o.kind == ANONYMOUS and not o.with_recordings
    d.kind_buttons[ETHICAL].setChecked(True)
    assert d.kind == ETHICAL and not d.ai_note.isVisibleTo(d) and not d.codes_row.isVisibleTo(d)
    assert d.recordings.isEnabled() and d.recordings.isChecked() and d.places.currentData() == 0
    assert "ethical archive" in d.folder.text()
    assert not d.options().hide_language_code


def test_the_menu_has_both_archives(win):
    from PySide6.QtWidgets import QMenu
    texts = [a.text().replace("&", "") for m in win.menuBar().findChildren(QMenu) for a in m.actions()]
    assert "Anonymous archive…" in texts and "Ethical archive…" in texts
    assert not any("Anonymous backup" in t for t in texts)


# ---------------------------------------------------------------- the independent check's cases (22 October)

def _anon(tmp_path, db, book, **kw):
    opts = Options.for_kind(ANONYMOUS)
    for k, v in kw.items():
        setattr(opts, k, v)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    return rep, _all_text(tmp_path / "out")


def test_the_zip_names_hold_no_original_file_name(tmp_path):
    import zipfile
    db, book = _db(tmp_path)
    (tmp_path / "Consent" / "Kuku Dabi consent.pdf").write_bytes(b"%PDF")
    db.metadata.participants[0].consent = "Consent/Kuku Dabi consent.pdf"
    anonymise.export(db, book, tmp_path / "out", Options(kind=ETHICAL, consent_password="pw"))
    with zipfile.ZipFile(next((tmp_path / "out").glob("*.zip"))) as zf:   # no password needed to list
        names = zf.namelist()
    assert names == ["KDB/consent.pdf", "HMA/consent.pdf"] and not any("Kuku" in n for n in names)


def test_an_archive_needs_a_new_or_empty_folder(tmp_path):
    db, book = _db(tmp_path)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "old.notebook").write_text("from before")
    with pytest.raises(anonymise.ArchiveError):
        anonymise.export(db, book, tmp_path / "out", Options.for_kind(ETHICAL))
    with pytest.raises(anonymise.ArchiveError):                 # nor the database's own folders
        anonymise.check_folder(db, tmp_path / "Soundfiles" / "x")


def test_closed_fields_deleted_fields_and_unknown_settings(tmp_path):
    import xml.etree.ElementTree as ET
    from lemmatrix.model import FieldDef, ListItem
    db, book = _db(tmp_path)
    db.settings.token_fields.append(FieldDef("Consultant", closed=True, items=[ListItem("Kuku Dabi"),
                                                                               ListItem("KDB")]))
    db.entries[0].tokens[0].set("Consultant", "Kuku Dabi")
    db.entries[0].tokens[1].values["OldSpeaker"] = "Hana Mali (HMA)"        # a field since deleted
    db.settings.extra = [ET.Element("analysis", note="checked with Kuku Dabi (KDB)")]
    db.settings.ref_categories[0].name = "Kuku's words"
    rep, everything = _anon(tmp_path, db, book)
    for gone in ("Kuku", "Hana", "KDB", "HMA"):
        assert gone not in everything, gone
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    assert out.entries[0].tokens[0].get("Consultant") == "SP1"
    assert [i.name for i in out.settings.token_field("Consultant").items] == ["SP1", "SP1"]
    assert rep.extra_settings == 1


def test_snapshots_and_codes_joined_by_underscores(tmp_path):
    from lemmatrix import hypotheses as hy
    db, book = _db(tmp_path)
    db.entries[0].tokens[1].set("Comment", "see LXX-VXX-KDB_D001_goat.wav and Kuku_story; mail jo@example.org")
    h = hy.make(book, hy.Journal(book), "2026-10-01", "tone", "")
    h.links.append(hy.Link("snapshot", view={"search": "Kuku", "filters": {"selected": ["KDB", "HMA"]}}))
    _, everything = _anon(tmp_path, db, book, notebook=True)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    assert out.entries[0].tokens[1].get("Comment") == "see LXX-VXX-SP1_D001_goat.wav and SP1_story; mail RS1"
    for gone in ("Kuku", "KDB", "HMA"):
        assert gone not in everything, gone


def test_codes_only_a_tier_knows_and_tier_mappings_follow(tmp_path):
    from lemmatrix.model import TierRule
    db, book = _db(tmp_path)
    grid = tmp_path / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.TextGrid"
    tgmod.write_example(grid, {"tx@QQQ": [(0.0, 1.0, "dabuuba")], "Hana": [(0.0, 1.0, "a note")]}, 2.0)
    db.settings.tier_mapping.rules.append(TierRule("Hana", "Comment"))
    _, everything = _anon(tmp_path, db, book)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    assert "QQQ" not in everything and "Hana" not in everything
    assert out.settings.tier_mapping.rule("SP2") is not None          # Hana Mali, HMA, is SP2
    names = sorted(x.name for x in tgmod.tiers(tmp_path / "out" / "Soundfiles" / "Texts" / out.texts[0].textgrid))
    assert names == ["SP2", "tx@SP3"]


def test_the_ethical_archive_cleans_what_it_keeps(tmp_path):
    db, book = _db(tmp_path)
    db.path = str(tmp_path / "Hana_Dabi_words.xml")
    db.metadata.participants[0].description = "a farmer, cousin of Hana Mali"
    db.metadata.author = "Dr Ann Bell"
    db.metadata.participants[0].name = "Kuku Dabi"
    db.metadata.participants[1].name = "Hana Dabi"
    db.entries[0].tokens[0].set("Comment", "Kuku Dabi and Hana Dabi came")
    anonymise.export(db, book, tmp_path / "out", Options.for_kind(ETHICAL))
    out = storage.load(next((tmp_path / "out").glob("* (ethical).xml")))
    assert Path(out.path).name == "HMA_words (ethical).xml"
    assert out.metadata.participants[0].description == "a farmer, cousin of HMA Mali"
    assert out.metadata.author == "Dr AB"
    assert out.entries[0].tokens[0].get("Comment") == "Kuku Dabi and HMA came"


def test_transcriptions_are_never_touched(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.language_name, db.metadata.variety_name = "Opo", "Hill"
    grid = tmp_path / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.TextGrid"
    tgmod.write_example(grid, {"tx@KDB": [(0.0, 1.0, "opo Kuku")], "ft@KDB": [(0.0, 1.0, "up the hill")]}, 2.0)
    db.entries[0].tokens[0].set("Phonetic", "Kuku opo")
    _anon(tmp_path, db, book)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    assert out.entries[0].tokens[0].get("Phonetic") == "Kuku opo"
    text = (tmp_path / "out" / "Soundfiles" / "Texts" / out.texts[0].textgrid).read_text(encoding="utf-8")
    assert "opo Kuku" in text and "up the hill" in text


def test_names_without_capitals_and_people_in_both_lists(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.participants[1].name = "ተስፋዬ ገብሬ"
    db.entries[0].tokens[0].set("Comment", "ask ተስፋዬ; SP1 said so")       # a stray SP1: no one's code now
    db.metadata.researchers.append(Person.researcher("KDB", "Kuku Dabi"))   # also a participant
    rep, everything = _anon(tmp_path, db, book)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    assert out.entries[0].tokens[0].get("Comment") == "ask SP2; SP? said so"
    assert [r.code for r in out.metadata.researchers] == ["RS1", "RS2", "RS3"]
    assert ("researcher", "KDB", "RS3") in rep.key and ("participant", "KDB", "SP1") in rep.key
