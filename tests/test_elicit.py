# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""ɛλicit, stage 1 (IDEAS.md idea 19): requests, the speaker's recordings coming back, and the
review, on the Italian test database (samples/Elicit test)."""

import json
import os
import shutil
import string
import zipfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import audio, elicit as el, elicit_art, elicit_prompts, storage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = ROOT / "samples" / "Elicit test" / "ITA-STD_Elicit_Test.xml"


@pytest.fixture
def db(tmp_path):
    shutil.copytree(TEST_DB.parent, tmp_path / "Elicit test")
    return storage.load(tmp_path / "Elicit test" / TEST_DB.name)


def _items(db):
    E = {e.ref: e for e in db.entries}
    U = {u.ref: u for u in db.utterances}

    def tok(ref, i=0):
        return E[ref].tokens[i]
    return [el.Item(el.NEW, E["D001"], tok("D001")), el.Item(el.NEW, E["D001"], tok("D001", 1)),
            el.Item(el.NEW, E["J002"], tok("J002")), el.Item(el.NEW, E["J003"], tok("J003", 1)),
            el.Item(el.NEW, E["K002"], tok("K002", 1)), el.Item(el.NEW, E["V001"], tok("V001")),
            el.Item(el.RERECORD, E["J001"], tok("J001")), el.Item(el.RERECORD, E["L001"], tok("L001")),
            el.Item(el.RERECORD, U["U001"], U["U001"].token), el.Item(el.NEW, U["U003"], U["U003"].token),
            el.Item(el.NEW_UTTERANCE, translations={"en": "The sun is hot.", "da": "Solen er varm."})]


def _response(st, path, skip=(), rate=8000, date="2026-10-21"):
    """A zip like the one the web page gives back."""
    cards = []
    with zipfile.ZipFile(path, "w") as zf:
        for c in st.request.cards:
            if c.n in skip:
                cards.append({"n": c.n, "status": "skipped"})
                continue
            tmp = path.parent / c.file
            audio.write_wav(tmp, 0.1 * np.sin(np.arange(rate * (1 + c.n % 3)) / (3 + c.n)), rate, 16)
            zf.write(tmp, "recordings/" + c.file)
            cards.append({"n": c.n, "status": "recorded", "file": c.file, "recorded": date + "T10:00:00Z",
                          "date": date, "seconds": 1.0, "rate": rate})
        zf.writestr("response.json", json.dumps({"format": el.RESPONSE_FORMAT, "version": 1,
                                                 "request": st.request.id, "speaker": "SP1", "cards": cards}))
    return path


# ---- the test database ------------------------------------------------------------

def test_the_test_database_has_every_case(db):
    assert db.settings.gloss_languages == ["en", "da"]
    assert len(db.entries) == 12 and len(db.utterances) == 3
    recorded = [e.ref for e, t in db.all_tokens() if t.file]
    assert sorted(recorded) == ["J001", "J003", "K001", "K002", "L001", "U001", "U002"]
    for e, t in db.all_tokens():
        if t.file:
            assert (storage.folder_for(db, e) / t.file).exists()
    sp2 = db.metadata.participant("SP2")
    assert sp2 is not None and not sp2.audio_sharing and db.metadata.participant("SP1").audio_sharing
    images = sorted(p.name for p in (TEST_DB.parent / "Images").iterdir())
    assert images == ["D001.png", "D001_PL.png", "V001.gif"]


# ---- prompts and artwork -------------------------------------------------------------

def test_every_built_in_language_has_every_prompt_with_the_same_placeholders():
    names = lambda text: {f for _, f, _, _ in string.Formatter().parse(text) if f}   # noqa: E731
    en = elicit_prompts.PROMPTS["en"]
    assert set(en) == set(elicit_prompts.KEYS)
    for lang, p in elicit_prompts.PROMPTS.items():
        assert set(p) == set(en), lang
        for k, text in p.items():
            assert names(text) == names(en[k]), (lang, k)
    for lang in ("da", "it", "nl", "ar", "am", "fr", "sw"):         # Danish and Italian join; Dutch stays
        assert elicit_prompts.built_in(lang)
    assert elicit_prompts.prompts("ar-SD") is elicit_prompts.PROMPTS["ar"]


def test_the_artwork_is_svg_in_the_colours_asked_for():
    svg = elicit_art.main("#123456", "#ffffff")
    assert svg.startswith("<svg") and "#123456" in svg and "#ffffff" in svg
    w = elicit_art.waiting("#4d4d4d", "#000000", "#abcdef")
    assert w.count("<ellipse") == len(elicit_art.DROPS) == 15 and "#abcdef" in w
    assert "clipPath" in elicit_art.logo("#198583", "#1b1b1b")


# ---- requests ----------------------------------------------------------------------

def test_warnings_before_sending(db):
    items = _items(db)
    assert [el.item_label(db, i) for i in items if el.missing_translation(db, i)] == \
        [el.item_label(db, items[4])]                                 # libri: no Translation
    ethics = [el.ethics_problem(db, i) for i in items]
    assert [i for i, why in enumerate(ethics) if why] == [7] and "audio sharing" in ethics[7]   # sole, SP2
    assert 0 < el.estimated_size(db, items) < el.SIZE_WARNING


def test_a_request_and_its_zip(db):
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da", "italiensk", accent="#198583")
    assert req.languages == ["en", "da"] and req.language_names == {"en": "Italian", "da": "italiensk"}
    assert set(req.prompts) == {"en", "da"} and req.speaker["name"] == "Speaker 1"
    c = {x.n: x for x in req.cards}
    assert (c[1].show, c[1].texts) == ("gloss", {"en": "cat", "da": "kat"}) and c[1].repeat
    assert (c[2].show, c[2].texts) == ("translation", {"en": "cats", "da": "katte"})
    assert c[5].texts == {"en": "book (Plural)", "da": "bog (Plural)"}            # the fallback
    assert c[7].kind == el.RERECORD and c[7].texts == {} and not c[7].repeat
    assert c[10].texts == {"en": "the dog is eating", "da": "hunden spiser"} and not c[10].repeat
    assert c[11].kind == el.NEW_UTTERANCE and c[11].translations["da"] == "Solen er varm."
    path = el.write_request(db, req, items)
    assert path.name == "Elicit_request_SP1_" + req.created[:10] + ".zip"
    with zipfile.ZipFile(path) as zf:
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())    # the page reads stored zips
        names = zf.namelist()
        back = json.loads(zf.read("request.json"))
        assert back["format"] == el.FORMAT and len(back["cards"]) == 11
        assert {"media/01.png", "media/02.png", "media/06.gif", "media/07_original.wav",
                "media/08_original.wav", "media/09_original.wav"} == set(names) - {"request.json"}
        from PIL import Image
        import io
        assert max(Image.open(io.BytesIO(zf.read("media/01.png"))).size) == el.IMAGE_MAX
        gif = Image.open(io.BytesIO(zf.read("media/06.gif")))
        assert max(gif.size) == el.IMAGE_MAX and gif.n_frames == 4                  # still animated
    st = el.stored_requests(db.path)
    assert len(st) == 1 and st[0].request.id == req.id and st[0].response is None
    msg = el.message_text(req)
    assert el.WEB_PAGE in msg and "Hej Speaker 1!" in msg


def test_a_language_without_built_in_prompts_gets_english(db):
    db.settings.gloss_languages = ["en", "xx"]
    req = el.new_request(db, _items(db)[:1], "SP1", "RS1", "xx")
    assert set(req.prompts) == {"en"} and req.languages == ["en", "xx"]


# ---- receiving and reviewing -----------------------------------------------------------

def test_receiving_checks_the_request(db, tmp_path):
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.write_request(db, req, items)
    st = el.stored_requests(db.path)[0]
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("response.json", json.dumps({"format": el.RESPONSE_FORMAT, "request": "nope", "cards": []}))
    with pytest.raises(el.ElicitError):
        el.receive(db, bad)
    with zipfile.ZipFile(tmp_path / "x.zip", "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(el.ElicitError):
        el.receive(db, tmp_path / "x.zip")
    st = el.receive(db, _response(st, tmp_path / "r.zip", skip={3}))
    assert len(el.waiting(db, st)) == 10 and [c.n for c in el.skipped(st)] == [3]
    assert el.waiting_reviews(db)[0][1] == 10


@pytest.fixture
def win(tmp_path, monkeypatch, db):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from lemmatrix.ui import elicit_dialogs, main_window
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(elicit_dialogs, "remind", lambda main: None)
    w = main_window.MainWindow()
    w.load_database(db)
    yield w
    w.doc.undo.setClean()
    w.doc._settings_dirty = False
    w.close()


def test_the_button_sits_left_of_texts_and_utterances(win):
    lay = win.head_icons
    assert lay.itemAt(0).widget() is win.elicit_btn and lay.itemAt(1).widget() is win.texts_btn
    texts = [a.text() for a in win.elicit_menu.actions() if a.isVisible()]
    assert texts == ["Make ɛλicit request…", "Receive ɛλicitation…"]
    assert "remote elicitation" in win.elicit_btn.toolTip()


def test_the_request_dialog(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    gatto = db.entry_by_ref("D001")
    dlg = ed.RequestDialog(win, [gatto.tokens[0].id])
    assert dlg.l2.currentData() == "da" and dlg.speaker.currentData() == "SP1"
    assert [i.token.id for i in dlg.items()] == [gatto.tokens[0].id]
    acqua = next(i for i, r in enumerate(dlg.model.rows) if r.entry.ref == "J001")
    dlg.model.toggle_kind(acqua)                                     # double-click on Card: Rerecord
    dlg._add_new_row({"en": "I read a book.", "da": "Jeg læser en bog."})
    dlg.l2_name.setText("italiensk")
    kinds = [(i.kind, i.entry.ref if i.entry else "") for i in dlg.items()]
    assert kinds == [(el.NEW, "D001"), (el.RERECORD, "J001"), (el.NEW_UTTERANCE, "")]
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    monkeypatch.setattr(ed.SentDialog, "exec", lambda self: None)
    dlg._make()
    assert dlg.made is not None and dlg.made.exists()
    assert dlg.request.cards[2].translations == {"en": "I read a book.", "da": "Jeg læser en bog."}
    assert dlg.request.language_names["da"] == "italiensk"


def test_review_puts_recordings_in_and_undo_takes_them_out(win, tmp_path):
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.write_request(db, req, items)
    st = el.receive(db, _response(el.stored_requests(db.path)[0], tmp_path / "r.zip", skip={3}))
    win.refresh_elicit_icon()
    assert "10 recordings waiting" in win.elicit_btn.toolTip() and win.elicit_review.isVisible()
    acqua = db.entry_by_ref("J001")
    old_name = acqua.tokens[0].file
    old_size = (storage.sound_folder(db) / old_name).stat().st_size
    n_utts = len(db.utterances)
    dlg = ed.ReviewDialog(win, st)
    dlg.autoplay.setChecked(False)
    dlg.table.setCurrentCell(4, 1)                                   # libri: rejected
    dlg.decide(el.REJECTED)
    dlg.approve_all()
    dlg.accept()
    gatto = db.entry_by_ref("D001")
    t = gatto.tokens[0]
    assert t.file == "ITA-STD_D001_cat.wav" and t.speaker == "SP1" and t.collected == "2026-10-21"
    assert (storage.sound_folder(db) / t.file).exists()
    assert db.entry_by_ref("J001").tokens[0].file == old_name       # the rerecord: the same name, the new sound
    assert (storage.sound_folder(db) / old_name).stat().st_size != old_size
    assert not db.entry_by_ref("K002").tokens[1].file                # rejected
    assert len(db.utterances) == n_utts + 1
    new_u = db.utterances[-1]
    assert new_u.ref == "U004" and new_u.label == "The sun is hot"
    assert new_u.token.get("Translation", "da") == "Solen er varm."
    assert (storage.utterance_folder(db) / new_u.token.file).exists()
    st = el.load_stored(st.folder)
    assert el.waiting(db, st) == [] and st.review["5"]["decision"] == el.REJECTED
    assert "remote elicitation" in win.elicit_btn.toolTip()
    win.doc.undo.undo()                                              # one undo step takes it all out
    assert not db.entry_by_ref("D001").tokens[0].file and len(db.utterances) == n_utts
    assert (storage.sound_folder(db) / old_name).stat().st_size == old_size
    assert not (storage.sound_folder(db) / "ITA-STD_D001_cat.wav").exists()
    assert len(el.waiting(db, st)) == 9                              # waiting again (libri stays rejected)
    win.doc.undo.redo()
    assert db.entry_by_ref("D001").tokens[0].file == "ITA-STD_D001_cat.wav" and len(db.utterances) == n_utts + 1
    assert el.waiting(db, st) == []
    again = el.items_again(db, st, dlg._again_numbers())
    assert [(i.kind, i.entry.ref) for i in again] == [(el.NEW, "J002"), (el.NEW, "K002")]


def test_undecided_recordings_wait_for_later(win, tmp_path):
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    items = _items(db)[:3]
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.write_request(db, req, items)
    st = el.receive(db, _response(el.stored_requests(db.path)[0], tmp_path / "r.zip"))
    dlg = ed.ReviewDialog(win, st)
    dlg.autoplay.setChecked(False)
    dlg.decide(el.APPROVED)                                          # the first only
    dlg.accept()
    assert [c.n for c in el.waiting(db, el.load_stored(st.folder))] == [2, 3]


# ---- the web page (when a browser is at hand) ---------------------------------------------

def test_the_web_page_files_are_there():
    page = ROOT / "docs" / "elicit"
    for name in ("index.html", "elicit.js", "elicit.css", "favicon.svg", "logo.svg", "icon-180.png"):
        assert (page / name).exists(), name
    js = (page / "elicit.js").read_text(encoding="utf-8")
    assert el.RESPONSE_FORMAT in js and el.FORMAT in js
    assert "echoCancellation: false" in js and "noiseSuppression: false" in js and "autoGainControl: false" in js
    import re
    used = set(re.findall(r'\b(?:say|btn|text)\("(\w+)"', js))
    assert used and used <= set(elicit_prompts.KEYS), used - set(elicit_prompts.KEYS)


def test_the_whole_loop_through_the_web_page(db, tmp_path):
    """Lemmatrix makes a request, the page (in Chromium, with a fake microphone) answers it,
    Lemmatrix receives the zip. Skipped where Playwright and its Chromium aren't installed."""
    pw = pytest.importorskip("playwright.sync_api")
    import functools
    import http.server
    import threading
    items = _items(db)[:3] + [_items(db)[6]]                         # gatto, gatti, pane, acqua (rerecord)
    req = el.new_request(db, items, "SP1", "RS1", "da", "italiensk")
    zpath = el.write_request(db, req, items)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "docs"))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake = tmp_path / "voice.wav"
    audio.write_wav(fake, 0.3 * np.sin(np.arange(48000 * 2) / 7), 48000, 16)
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch(args=["--use-fake-ui-for-media-stream",
                                                  "--use-fake-device-for-media-stream",
                                                  f"--use-file-for-fake-audio-capture={fake}"])
            except Exception as exc:                                  # noqa: BLE001
                pytest.skip(f"no Chromium for Playwright: {exc}")
            page = browser.new_context(accept_downloads=True).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/elicit/")
            page.set_input_files("input[type=file]", str(zpath))

            def click(text):
                page.locator("button", has_text=text).first.click()
            for _ in range(3):
                click("Yes")                                          # who, agreement, language
            click("I'm ready")
            assert page.locator(".word").first.inner_text() == "cat"
            for n in range(4):
                if n == 2:
                    click("I can't say this one")
                    continue
                page.locator("button.rec").click()
                page.wait_for_timeout(600)
                page.locator("button.rec").click()
                click("It's good")
            click("Goodbye")
            with page.expect_download() as d:
                click("Save the file")
            d.value.save_as(tmp_path / "back.zip")
            browser.close()
            assert not errors, errors
    finally:
        server.shutdown()
    st = el.receive(db, tmp_path / "back.zip")
    assert [c.n for c in el.waiting(db, st)] == [1, 2, 4] and [c.n for c in el.skipped(st)] == [3]
    samples, rate = audio.read_wav(st.recording(1))
    assert len(samples) > rate * 0.3 and audio.read_info(st.recording(1))["IART"] == "SP1"
