# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Bulk edit engine: replace, shortcuts, set value, copy, clear, word class conversion, renames."""

import shutil
from pathlib import Path

import pytest

from lemmatrix import bulk, storage

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (conftest.py)


@pytest.fixture
def db(tmp_path):
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    shutil.copytree(SAMPLES / "Soundfiles", tmp_path / "Soundfiles")
    return storage.load(tmp_path / "Sample.xml")


def token_rows(db, entries=None):
    return [(e, i) for e in (entries or db.entries) for i in range(len(e.tokens))]


def disk(db):
    folder = storage.sound_folder(db)
    return folder, storage.scan_sound_folder(folder)[0]


# ---- text ------------------------------------------------------------------

def test_replace_keeps_diacritics_by_default():
    rx = bulk.compile_find("y", False, False)
    assert bulk.replace_text("ỹə̀ə̀", rx, "j") == "j̃ə̀ə̀"
    assert bulk.replace_text("ʔə̀yə́", rx, "j") == "ʔə̀jə́"
    assert bulk.replace_text("yʷɒ̀r", rx, "j") == "jʷɒ̀r"        # a modifier letter is its own letter
    assert bulk.replace_text("ý", rx, "j") == "j́"


def test_replace_without_keep_diacritics_leaves_marked_letters():
    rx = bulk.compile_find("y", False, False)
    assert bulk.replace_text("ỹəy", rx, "j", keep_diacritics=False) == "ỹəj"


def test_replace_match_case_and_regex():
    rx = bulk.compile_find("Y", False, False)
    assert bulk.replace_text("yY", rx, "j") == "jj"
    rx = bulk.compile_find("Y", False, True)
    assert bulk.replace_text("yY", rx, "j") == "yj"
    rx = bulk.compile_find(r"(ə)(ə)", True, True)
    assert bulk.replace_text("kəə", rx, r"\1ː", regex=True) == "kəː"
    with pytest.raises(bulk.BulkError):
        bulk.compile_find("(", True, False)


def test_tie_bars_only_on_affricates():
    assert bulk.add_tie_bars("tʃə dʒʊ ts") == "t͡ʃə d͡ʒʊ t͡s"
    assert bulk.add_tie_bars("t͡ʃə") == "t͡ʃə"                     # already tied
    assert bulk.add_tie_bars("tka") == "tka"
    assert bulk.remove_tie_bars("t͡ʃə k͡pə") == "tʃə k͡pə"          # labial-velars keep theirs
    assert bulk.add_tie_bars("t̪s̪") == "t̪͡s̪"


def test_pitch_shift_errors_at_the_edges():
    assert bulk.shift_pitch("21, 4:42", 1, 1, 5) == "32, 5:53"
    with pytest.raises(bulk.RowError):
        bulk.shift_pitch("55", 1, 1, 5)
    with pytest.raises(bulk.RowError):
        bulk.shift_pitch("12", -1, 1, 5)
    assert bulk.shift_pitch("23", -1, 1, 5) == "12"


# ---- plans -----------------------------------------------------------------

def test_replace_plan_changes_only_ticked_rows(db):
    goat = db.entry_by_ref("D001")
    rows = token_rows(db, [goat])
    before = [t.get("Phonetic") for t in goat.tokens]
    p = bulk.plan(db, bulk.TOKENS, rows[:1], bulk.Replace("f:Phonetic", "ɪɪ", "ææ"))
    assert p.ok
    assert [t.get("Phonetic") for t in goat.tokens] == before     # nothing changed yet
    assert all(c.row == rows[0] for c in p.changes)
    assert p.changes and p.changes[0].new == "dæær"


def test_pitch_error_cancels_the_whole_operation(db):
    rows = token_rows(db)
    tops = [r for r in rows if "5" in r[0].tokens[r[1]].get("Pitch")]
    assert tops, "the sample needs a pitch at the top of the range"
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.RunShortcut("f:Pitch", "pitch", "up"))
    assert not p.ok
    assert {bulk.row_key(pr.row) for pr in p.problems} >= {bulk.row_key(r) for r in tops}


def test_shortcut_only_on_its_fields(db):
    with pytest.raises(bulk.BulkError):
        bulk.plan(db, bulk.TOKENS, token_rows(db), bulk.RunShortcut("f:Pitch", "yj", "y>j"))


def test_add_tag_replaces_the_group_and_renames(db):
    folder, names = disk(db)
    goat = db.entry_by_ref("D001")
    i = next(i for i, t in enumerate(goat.tokens) if t.tags == ["Singular", "isolation"])
    p = bulk.plan(db, bulk.TOKENS, [(goat, i)], bulk.SetValue("tags", "Plural", bulk.ADD_TAG),
                  folder=folder, on_disk=names)
    pl = next((k for k, t in enumerate(goat.tokens) if t.tags == ["Plural", "isolation"]), None)
    if pl is not None:                       # the sample already has PL: a duplicate, so an error
        assert not p.ok
        return
    assert p.ok and p.changes[0].new == "Plural, isolation"
    assert p.renames and p.renames[0][1].name == "LXX-VXX_D001_goat_PL.wav"


def test_adding_an_unusual_tag_is_a_warning_not_an_error(db):
    verb = next(e for e in db.entries if db.word_class(e) == "VERB")
    p = bulk.plan(db, bulk.TOKENS, [(verb, 1)], bulk.SetValue("tags", "Plural"))
    assert p.ok and p.unusual == 1
    assert any("isn't usual" in line for line in bulk.summary(p, bulk.TOKENS))
    assert not any("isn't usual" in line for line in bulk.summary(p, bulk.TOKENS, warn_unusual=False))


def test_removing_a_tag_that_would_make_duplicates_is_an_error(db):
    goat = db.entry_by_ref("D001")
    rows = token_rows(db, [goat])
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.SetValue("tags", "Singular", bulk.REMOVE_TAG))
    sg = [t for t in goat.tokens if "Singular" in t.tags]
    plain = [t for t in goat.tokens if set(t.tags) == set(sg[0].tags) - {"Singular"}] if sg else []
    if plain:
        assert not p.ok and "would both be" in p.problems[0].message


def test_copy_and_clear(db):
    rows = token_rows(db)
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.CopyField("f:Phonetic", "f:Phonemic", bulk.ONLY_EMPTY))
    assert p.ok
    assert all(c.old == "" for c in p.changes)
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.ClearField("f:Comment"))
    assert p.ok
    with pytest.raises(bulk.BulkError):
        bulk.plan(db, bulk.TOKENS, rows, bulk.ClearField("tags"))


def test_comment_dates_are_an_option(db):
    rows = token_rows(db)
    op = bulk.SetValue("f:Comment", "checked")
    assert not bulk.plan(db, bulk.TOKENS, rows, op).comment_dates
    assert bulk.plan(db, bulk.TOKENS, rows, op, bulk.Options(update_comment_dates=True)).comment_dates


def test_rename_off_leaves_names_out_of_date(db):
    folder, names = disk(db)
    goat = db.entry_by_ref("D001")
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue("file_gloss", "she-goat"),
                  bulk.Options(rename_files=False), folder, names)
    assert p.ok and not p.renames and p.stale == sum(1 for t in goat.tokens if t.file)
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue("file_gloss", "she-goat"),
                  folder=folder, on_disk=names)
    assert len(p.renames) == sum(1 for t in goat.tokens if t.file in names)
    assert all("she-goat" in new.name for _, new in p.renames)


def test_rename_onto_an_existing_file_is_an_error(db):
    folder, names = disk(db)
    goat = db.entry_by_ref("D001")
    recorded = next(t for t in goat.tokens if t.file in names)
    other = next(e for e in db.entries if e is not goat and any(t.file in names for t in e.tokens))
    # give the goat the other lemma's reference-free name parts so a name collides
    (folder / db.expected_filename(goat, recorded).replace("goat", "taken")).write_bytes(b"x")
    names = storage.scan_sound_folder(folder)[0]
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue("file_gloss", "taken"),
                  folder=folder, on_disk=names)
    assert not p.ok and "already in the sound folder" in p.problems[0].message
    assert other is not None


def test_forbidden_characters_are_refused(db):
    goat = db.entry_by_ref("D001")
    with pytest.raises(bulk.BulkError):
        bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue("file_gloss", "a/b"))
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.Replace("file_gloss", "goat", "go?at"))
    assert not p.ok


# ---- word class ----------------------------------------------------------------

def test_word_class_change_keeps_the_tags(db):
    goat = db.entry_by_ref("D001")
    wcf = db.settings.entry_field("word-class").name
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue(wcf, "VERB"))
    assert p.ok
    _, after = p.pairs[0]
    assert [t.tags for t in after.tokens] == [t.tags for t in goat.tokens]
    assert p.unusual == sum(1 for t in goat.tokens if db.settings.tags.unusual(["VERB"], t.tags))


def test_a_new_word_class_is_added_to_the_list(db):
    goat = db.entry_by_ref("D001")
    wcf = db.settings.entry_field("word-class").name
    p = bulk.plan(db, bulk.LEMMAS, [(goat, None)], bulk.SetValue(wcf, "NOMINAL"))
    assert p.ok and (wcf, "NOMINAL") in p.new_values


# ---- predicted translations ------------------------------------------------------

def test_fill_predicted_translations(db):
    lion, eat = db.entry_by_ref("D002"), db.entry_by_ref("V001")
    pl_gen = next(i for i, t in enumerate(lion.tokens) if set(t.tags) >= {"Plural", "Genitive"})
    lion.tokens[pl_gen].set("Translation", "", "en")
    odd = next(i for i, t in enumerate(eat.tokens) if "1SG.O" in t.tags)   # tags no one else has
    eat.tokens[odd].set("Translation", "", "en")
    key = bulk.predicted_target(db)
    assert key == "f:Translation"
    rows = token_rows(db)
    p = bulk.plan(db, bulk.TOKENS, rows, bulk.FillPredicted(key))
    assert p.ok
    assert [(c.row, c.old, c.new) for c in p.changes] == [((lion, pl_gen), "", "of the lions")]
    assert p.unpredicted == 1
    assert p.kept == len(rows) - 2 - sum(1 for e, i in rows if not e.tokens[i].get("Translation", "en")
                                         and (e, i) not in ((lion, pl_gen), (eat, odd)))
    assert any("no suggestion" in x for x in bulk.summary(p, bulk.TOKENS))
    assert lion.tokens[pl_gen].get("Translation", "en") == ""      # nothing changed yet
    after = next(a for e, a in p.pairs if e is lion)
    assert after.tokens[pl_gen].get("Translation", "en") == "of the lions"


def test_fill_predicted_only_for_english_tokens(db):
    with pytest.raises(bulk.BulkError):
        bulk.plan(db, bulk.LEMMAS, [(e, None) for e in db.entries], bulk.FillPredicted("f:Translation"))
    with pytest.raises(bulk.BulkError):
        bulk.plan(db, bulk.TOKENS, token_rows(db), bulk.FillPredicted("f:Phonetic"))
