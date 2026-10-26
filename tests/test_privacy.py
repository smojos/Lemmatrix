# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The audit of 25 October 2026, privacy P1–P8 (claude/AUDIT.md, section 2)."""

import datetime as dt
import io
import json
import zipfile

import pytest

from lemmatrix import anonymise, credstore, elicit as el, recode, storage, textgrid as tgmod
from lemmatrix.anonymise import ANONYMOUS, ETHICAL, Options
from lemmatrix.model import Person
from test_archives import _all_text, _db as _archive_db
from test_elicit import FakeDrive, _items, _wav_bytes, db  # noqa: F401  (fixture)


# ---------------------------------------------------------------- P1: the speaker's copy of the request

def test_the_speakers_copy_holds_only_what_the_page_reads(db):
    db.metadata.researchers[0].email = "rs1@example.org"
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    path = el.write_request(db, req, items)
    with zipfile.ZipFile(path) as zf:
        sent = json.loads(zf.read("request.json"))
    text = json.dumps(sent)
    assert "rs1@example.org" not in text and "email" not in text
    assert "code" not in sent["researcher"] and sent["speaker"]["code"] == "SP1"
    assert sent["database"] == {"language_name": db.metadata.language_name}
    for c in sent["cards"]:
        assert not {"entry", "token", "ref", "label", "target", "translations"} & set(c)
        assert c["file"] and "n" in c and "kind" in c
    own = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))   # the researcher's copy
    assert own["researcher"]["email"] == "rs1@example.org" and own["cards"][0]["entry"]


def test_the_copy_shared_by_link_in_drive_too(db):
    drive = FakeDrive()
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.publish_drive(db, req, items, drive, "KEY")
    sent = json.loads(drive.download(req.drive["request"]))
    assert set(sent["drive"]) == {"response", "status"}                # not the folder's id
    assert not {"entry", "token", "ref"} & set(sent["cards"][0])
    assert sent["cards"][0]["upload"] and sent["cards"][0]["image_id"]


# ---------------------------------------------------------------- P2: expired Drive requests

def test_an_expired_drive_request_is_no_longer_shared_by_link(db, tmp_path):
    drive = FakeDrive()
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.publish_drive(db, req, items, drive, "KEY")
    st = el.outstanding_drive(db)[0]
    c = st.request.cards[0]
    rec = drive.put(c.upload, _wav_bytes(tmp_path, c.n, c.file))                      # the speaker recorded one card
    assert not el.unshare_expired(drive, st)                           # not expired yet: nothing done
    assert any(f["shared"] for f in drive.files.values())
    st.request.expires = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    assert el.unshare_expired(drive, st)
    assert not any(f["shared"] for f in drive.files.values())          # pictures, originals, request.json
    assert rec in drive.files and req.drive["folder"] in drive.files    # the recording waits for Receive
    st2 = el.outstanding_drive(db)[0]
    assert st2.request.drive["unshared"]                               # noted in the local copy
    assert not el.unshare_expired(drive, st2)                          # once
    got = el.receive_drive(db, st2, drive)
    assert [a["n"] for a in got.response["cards"]] == [c.n]


# ---------------------------------------------------------------- P3: picture metadata

def _jpeg_with_exif(path, size):
    from PIL import Image
    im = Image.new("RGB", size, (200, 20, 20))
    exif = Image.Exif()
    exif[0x013B] = "Jo Smith"                                          # Artist
    exif[0x0112] = 6                                                   # Orientation: turned 90°
    im.save(path, "JPEG", exif=exif.tobytes())


@pytest.mark.parametrize("size", [(300, 200), (1200, 800)])
def test_pictures_leave_without_their_exif(tmp_path, size):
    from PIL import Image
    src = tmp_path / "goat.jpg"
    _jpeg_with_exif(src, size)
    data, ext = el.shrink_image(src)
    assert ext == ".jpg" and b"Jo Smith" not in data
    with Image.open(io.BytesIO(data)) as im:
        assert not len(im.getexif())
        assert im.size[1] > im.size[0]                                 # turned upright for good
        assert max(im.size) <= el.IMAGE_MAX


def test_a_small_png_with_text_chunks_is_cleaned_and_a_clean_one_left_alone(tmp_path):
    from PIL import Image, PngImagePlugin
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "Jo Smith")
    Image.new("RGB", (40, 30)).save(tmp_path / "a.png", pnginfo=meta)
    data, _ = el.shrink_image(tmp_path / "a.png")
    assert b"Jo Smith" not in data
    Image.new("RGB", (40, 30)).save(tmp_path / "b.png")
    assert el.shrink_image(tmp_path / "b.png")[0] == (tmp_path / "b.png").read_bytes()


# ---------------------------------------------------------------- P4–P6: the archives

def test_the_languages_own_ethnic_group_hides_the_code(tmp_path):
    db, book = _archive_db(tmp_path)
    db.metadata.language_code = "BDI"
    e = db.entries[0]
    e.ref = "CBDI"
    for t in e.tokens:
        t.file = "BDI_CBDI_x.wav"
    opts = Options.for_kind(ANONYMOUS)
    opts.hide_language_code = True
    out, _ = anonymise.anonymise(db, book, opts, anonymise.Report())
    assert out.entries[0].ref == "CLXX"
    assert all("BDI" not in t.file for t in out.entries[0].tokens)
    assert ("reference", "CBDI", "CLXX") in anonymise.plan(db, book, opts).key     # in the key
    opts.hide_language_code = False                                   # not hidden: the reference stays
    out, _ = anonymise.anonymise(db, book, opts, anonymise.Report())
    assert out.entries[0].ref == "CBDI"


def test_the_ethical_archive_scrubs_support_too(tmp_path):
    from lemmatrix.model import Support
    db, book = _archive_db(tmp_path)
    db.metadata.support = [Support("Fund", "G-1", "Hana Mali's travel")]
    opts = Options.for_kind(ETHICAL)
    out, _ = anonymise.anonymise(db, book, opts, anonymise.Report())
    assert "Hana" not in out.metadata.support[0].funded and "HMA" in out.metadata.support[0].funded


def test_short_and_capital_name_parts_and_the_report(tmp_path):
    db, book = _archive_db(tmp_path)
    db.metadata.participants.append(Person("LNG", "Li Ng", "a singer"))
    db.metadata.participants.append(Person("VDB", "Ana van der Berg"))
    db.metadata.participants.append(Person("JKR", "J. K. Rowe"))
    db.entries[2].tokens[0].set("Comment", "Ng sang; HANA MALI and HANA came; van der Berg and Rowe")
    opts = Options.for_kind(ANONYMOUS)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    text = _all_text(tmp_path / "out")
    assert "Ng sang" not in text and "HANA" not in text and "Rowe" not in text
    summary = anonymise.summary(rep, opts)
    assert "Not replaced on their own" in summary and "“van”" in summary and "“J”" in summary


# ---------------------------------------------------------------- P7: renamed codes in Edit → Lists

def test_renamed_codes_follow_into_textgrids_clips_and_requests(db, tmp_path):
    from lemmatrix.model import Text
    texts = storage.text_folder(db)
    texts.mkdir(parents=True, exist_ok=True)
    tgmod.write_example(texts / "T.TextGrid", {"tx@SP1": [(0.0, 1.0, "aa")], "ft": [(0.0, 1.0, "ah")]}, 2.0)
    text = Text("T009", textgrid="T.TextGrid")
    db.texts.append(text)
    u = db.utterances[0]
    from lemmatrix.model import ClipSource
    u.source = ClipSource(text.id, 0.0, 1.0, copied={"tx@SP1": "aa", "ft": "ah"})
    items = _items(db)
    el.write_request(db, el.new_request(db, items, "SP1", "RS1", "da"), items)
    res = recode.follow(db, {"SP1": "SP7"})
    assert (res.textgrids, res.utterances, res.requests, res.failed) == (1, 1, 1, [])
    assert [t.name for t in tgmod.tiers(texts / "T.TextGrid")] == ["tx@SP7", "ft"]
    assert list(u.source.copied) == ["tx@SP7", "ft"]
    assert el.stored_requests(db.path)[0].request.speaker["code"] == "SP7"
    assert recode.follow(db, {"SP1": "SP7"}).textgrids == 0          # nothing left to rename


def test_edit_lists_follows_people_renames(monkeypatch):
    from lemmatrix.ui import main_window
    calls = {}

    class Doc:
        db = None
        _settings_dirty = False

        class dirtyChanged:
            @staticmethod
            def emit(v):
                calls["dirty"] = v

    fake = type("W", (), {"doc": Doc(), "elicit_draft": {"speaker": "SP1", "researcher": "RS1",
                                                           "l2_people": {"da|SP1": "Søren"}}})()
    monkeypatch.setattr(recode, "follow", lambda db, people: recode.Result(utterances=1))
    main_window.MainWindow._follow_people_renames(fake, {"SP1": "SP7"})
    assert fake.elicit_draft == {"speaker": "SP7", "researcher": "RS1", "l2_people": {"da|SP7": "Søren"}}
    assert calls["dirty"] is True


# ---------------------------------------------------------------- P8: the Google sign-in

class FakeVault:
    def __init__(self):
        self.store = {}

    def install(self, monkeypatch):
        monkeypatch.setattr(credstore, "available", lambda: True)
        monkeypatch.setattr(credstore, "read", lambda t: self.store.get(t))
        monkeypatch.setattr(credstore, "write", lambda t, s: self.store.__setitem__(t, s))
        monkeypatch.setattr(credstore, "delete", lambda t: self.store.pop(t, None))


def test_the_sign_in_goes_to_the_credential_manager(monkeypatch, app):
    from lemmatrix.ui.prefs import Prefs
    vault = FakeVault()
    vault.install(monkeypatch)
    p = Prefs()
    p.q.setValue("elicit/google_token", json.dumps({"refresh_token": "OLD"}))   # from before
    assert p.google_token == {"refresh_token": "OLD"}
    assert p.q.value("elicit/google_token", "") in ("", None)                  # moved, not copied
    assert json.loads(next(iter(vault.store.values()))) == {"refresh_token": "OLD"}
    p.google_token = {"refresh_token": "NEW"}
    assert p.google_token == {"refresh_token": "NEW"} and not p.q.value("elicit/google_token", "")
    p.google_token = {}
    assert p.google_token == {} and not vault.store


def test_without_the_credential_manager_the_settings_as_before(monkeypatch, app):
    from lemmatrix.ui.prefs import Prefs
    monkeypatch.setattr(credstore, "available", lambda: False)
    p = Prefs()
    p.google_token = {"refresh_token": "X"}
    assert json.loads(p.q.value("elicit/google_token")) == {"refresh_token": "X"}
    assert p.google_token == {"refresh_token": "X"}
    p.google_token = {}


def test_a_refusing_credential_manager_falls_back(monkeypatch, app):
    from lemmatrix.ui.prefs import Prefs
    monkeypatch.setattr(credstore, "available", lambda: True)
    monkeypatch.setattr(credstore, "read", lambda t: None)

    def refuse(*a):
        raise credstore.CredError("no")
    monkeypatch.setattr(credstore, "write", refuse)
    monkeypatch.setattr(credstore, "delete", refuse)
    p = Prefs()
    p.google_token = {"refresh_token": "Y"}
    assert p.google_token == {"refresh_token": "Y"}
    p.google_token = {}


def test_the_credential_manager_is_windows_only():
    import sys
    if sys.platform != "win32":
        assert not credstore.available()
