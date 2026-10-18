"""The fixed folder layout (format 4): sound folder, Morphemes, consent relinking, full backup."""

import datetime as dt
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from lemmatrix import layout, storage
from lemmatrix.defaults import new_database
from lemmatrix.model import Person

DATA = Path(__file__).resolve().parent / "data"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _format3(tmp_path, sound_folder="Soundfiles/Lexicon") -> Path:
    """A format 3 database whose recordings are in the old, settable sound folder."""
    text = (DATA / "Sample-format3.xml").read_text(encoding="utf-8")
    text = text.replace('<sounds folder="Soundfiles"', f'<sounds folder="{sound_folder}"')
    db_path = tmp_path / "Main" / "Old.xml"
    db_path.parent.mkdir()
    db_path.write_text(text, encoding="utf-8")
    old = db_path.parent / sound_folder
    old.mkdir(parents=True)
    for f in (SAMPLES / "Soundfiles" / "Tokens").glob("*.wav"):
        shutil.copy2(f, old / f.name)
    return db_path


def test_format_3_is_upgraded_with_morphemes_under_phonemic(tmp_path):
    db = storage.load(_format3(tmp_path))
    names = [f.name for f in db.settings.token_fields]
    assert names.index("Morphemes") == names.index("Phonemic") + 1
    assert db.settings.token_field("morphemes").name == "Morphemes"
    assert any("Morphemes" in n for n in db.load_notes) and any("Tokens" in n for n in db.load_notes)
    assert db.settings.old_sound_folder == "Soundfiles/Lexicon"
    storage.save(db, backup=False)
    text = Path(db.path).read_text(encoding="utf-8")
    assert '<database format="4">' in text and 'folder=' not in text
    again = storage.load(db.path)
    assert not again.load_notes                              # format 4: nothing to upgrade
    assert [f.name for f in again.settings.token_fields] == names


def test_new_databases_have_morphemes_and_recordings_in_tokens(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "New.xml")
    assert [f.name for f in db.settings.token_fields][:3] == ["Phonetic", "Phonemic", "Morphemes"]
    assert storage.sound_folder(db) == tmp_path / "Soundfiles" / "Tokens"
    assert storage.held_folder(db) == tmp_path / "Soundfiles" / "_Deleted recordings"
    assert storage.backup_folder(db.path) == tmp_path / "Backups"
    layout.create_layout(db.path)
    for name in ("Soundfiles/Tokens", "Documentation", "Exports"):
        assert (tmp_path / name).is_dir()


def test_the_old_lexicon_folder_is_found_and_explained(tmp_path):
    db = storage.load(_format3(tmp_path))
    old = layout.old_sound_folder(db)
    assert old is not None and old.name == "Lexicon"
    msg = layout.old_folder_message(db, old)
    assert "rename that folder to Tokens" in msg
    storage.save(db, backup=False)                         # the old setting isn't written…
    db = storage.load(db.path)
    assert layout.old_sound_folder(db).name == "Lexicon"   # …but Soundfiles/Lexicon is still found
    (old.parent / "Tokens").mkdir()
    assert layout.old_sound_folder(db) is None             # once Tokens is there, it's used


def test_recordings_directly_in_soundfiles_are_explained(tmp_path):
    db = storage.load(_format3(tmp_path, sound_folder="Soundfiles"))
    old = layout.old_sound_folder(db)
    assert old.name == "Soundfiles"
    assert "make a folder called Tokens inside Soundfiles" in layout.old_folder_message(db, old)


def test_another_database_in_the_folder(tmp_path):
    a = tmp_path / "A.xml"
    storage.save(new_database(), a, backup=False)
    assert layout.other_databases(a) == []
    (tmp_path / "notes.xml").write_text("<phon_data/>", encoding="utf-8")   # not a Lemmatrix database
    assert layout.other_databases(a) == []
    storage.save(new_database(), tmp_path / "B.xml", backup=False)
    assert [p.name for p in layout.other_databases(a)] == ["B.xml"]


def test_consent_forms_moved_into_documentation_are_relinked(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "Lex.xml")
    db.metadata.participants = [Person("SP1", consent="Consent/SP1 form.pdf"),
                                Person("SP2", consent="SP2.pdf"),
                                Person("ABC", consent="nowhere.pdf")]
    (tmp_path / "SP2.pdf").write_text("x")                 # where its link says: left alone
    doc = tmp_path / "Documentation" / "Consent forms"
    doc.mkdir(parents=True)
    (doc / "SP1 form.pdf").write_text("x")
    assert layout.relink_consent(db) == ["SP1"]
    sp1 = db.metadata.participant("SP1")
    assert Path(sp1.consent) == Path("Documentation") / "Consent forms" / "SP1 form.pdf"
    assert layout.consent_full_path(db, sp1.consent).exists()
    assert db.metadata.participant("SP2").consent == "SP2.pdf"
    assert db.metadata.participant("ABC").consent == "nowhere.pdf"
    assert layout.relink_consent(db) == []                 # nothing more to do


def test_full_backup_zips_the_main_folder(tmp_path):
    main = tmp_path / "Main"
    shutil.copytree(SAMPLES / "Soundfiles", main / "Soundfiles")
    shutil.copy2(SAMPLES / "Sample.xml", main / "Sample.xml")
    (main / "Documentation").mkdir()
    (main / "Documentation" / "SP1.pdf").write_text("consent")
    (main / ".Sample.xml.lemmatrix-lock").write_text("marker")
    assert layout.full_backup_name(main / "Sample.xml", dt.date(2026, 10, 18)) == "Sample 2026-10-18.zip"
    with pytest.raises(ValueError):
        layout.full_backup(main / "Sample.xml", main / "Exports" / "x.zip")     # not inside itself
    target = tmp_path / "Cloud" / "Sample 2026-10-18.zip"
    target.parent.mkdir()
    seen = []
    n = layout.full_backup(main / "Sample.xml", target, lambda d, t, name: seen.append(name))
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        assert "Main/Sample.xml" in names and "Main/Documentation/SP1.pdf" in names
        assert any(x.startswith("Main/Soundfiles/Tokens/") and x.endswith(".wav") for x in names)
        assert not any("lemmatrix-lock" in x for x in names)
        wav = next(i for i in zf.infolist() if i.filename.endswith(".wav"))
        assert wav.compress_type == zipfile.ZIP_STORED
        assert zf.testzip() is None
    assert n == len(names) and seen[-1] == ""


def test_a_cancelled_full_backup_leaves_nothing(tmp_path):
    main = tmp_path / "Main"
    shutil.copytree(SAMPLES / "Soundfiles", main / "Soundfiles")
    shutil.copy2(SAMPLES / "Sample.xml", main / "Sample.xml")
    target = tmp_path / "b.zip"

    def stop(done, total, name):
        if done == 3:
            raise layout.Cancelled()
    with pytest.raises(layout.Cancelled):
        layout.full_backup(main / "Sample.xml", target, stop)
    assert not target.exists() and not list(tmp_path.glob("*.part"))


def test_full_backup_reminder():
    day = dt.date(2026, 10, 18)
    assert not layout.reminder_due("", "", "", day)                     # never seen: not yet
    assert not layout.reminder_due("", "", "2026-10-15", day)          # seen 3 days ago
    assert layout.reminder_due("", "", "2026-10-11", day)              # seen a week ago, no backup
    assert not layout.reminder_due("2026-10-12", "", "2026-01-01", day)
    assert layout.reminder_due("2026-10-11", "", "2026-01-01", day)
    assert not layout.reminder_due("2026-10-01", "2026-10-20", "", day)   # put off for 7 days
    assert layout.reminder_due("2026-10-01", "2026-10-18", "", day)
