# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
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
    return [el.Item(el.NEW, E["D035"], tok("D035")), el.Item(el.NEW, E["D035"], tok("D035", 1)),
            el.Item(el.NEW, E["J114"], tok("J114")), el.Item(el.NEW, E["J114b"], tok("J114b", 1)),
            el.Item(el.NEW, E["K220"], tok("K220", 1)), el.Item(el.NEW, E["V094"], tok("V094")),
            el.Item(el.RERECORD, E["L062"], tok("L062")), el.Item(el.RERECORD, E["L002"], tok("L002")),
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
            x = (3000 * np.sin(np.arange(rate * (1 + c.n % 3)) / (3 + c.n))).astype("<i2")
            if c.file.endswith(".flac"):
                import soundfile
                soundfile.write(str(tmp), x, rate, subtype="PCM_16", format="FLAC")
            else:
                audio.write_pcm16(tmp, x, rate)
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
    assert sorted(recorded) == ["J114b", "K002", "K220", "L002", "L062", "U001", "U002"]
    for e, t in db.all_tokens():
        if t.file:
            assert (storage.folder_for(db, e) / t.file).exists()
    sp2 = db.metadata.participant("SP2")
    assert sp2 is not None and not sp2.audio_sharing and db.metadata.participant("SP1").audio_sharing
    images = sorted(p.name for p in (TEST_DB.parent / "Images").iterdir())
    assert images == ["D035.png", "D035_PL.png", "V094.gif"]


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


def test_the_artwork_is_joshs_files_in_the_theme_colour():
    """Josh's three Inkscape files (21 October), used as drawn: only the teal follows the theme;
    the grey ɛλ and rain cloud (#b3b3b3) stay; no ɛλ in the rain cloud."""
    for kind, name in elicit_art.FILES.items():
        assert (elicit_art.FOLDER / name).exists(), name
        svg = elicit_art.svg(kind, "#123456")
        assert "#123456" in svg and elicit_art.TEAL not in svg.lower()
    assert elicit_art.GREY in elicit_art.main() and elicit_art.GREY in elicit_art.waiting()
    assert elicit_art.waiting().count("<ellipse") == 15 and "text1" not in elicit_art.waiting()
    assert "text1" in elicit_art.main() and "text1" in elicit_art.logo()
    web = (ROOT / "docs" / "elicit" / "logo.svg").read_text(encoding="utf-8")
    assert web.startswith("<svg") and "var(--accent" in web


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
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)          # message boxes built by hand
    monkeypatch.setattr(elicit_dialogs, "remind", lambda main: None)
    from lemmatrix import gdrive

    def no_sign_in(*a, **k):                                         # tests never open a browser
        raise gdrive.DriveError("no signing in during tests")
    monkeypatch.setattr(gdrive, "authorize", no_sign_in)
    w = main_window.MainWindow()
    w.prefs.google_token = {}
    w.load_database(db)
    yield w
    w.doc.undo.setClean()
    w.doc._settings_dirty = False
    w.close()


def test_the_button_sits_left_of_texts_and_utterances(win):
    lay = win.head_icons
    assert lay.itemAt(0).widget() is win.elicit_btn and lay.itemAt(6).widget() is win.texts_btn
    assert lay.itemAt(1).widget() is win.xml_btn          # the XML viewer, Cogitate, Questions, To Do between them
    assert lay.itemAt(2).widget() is win.cogitate_btn
    assert lay.itemAt(3).widget() is win.questions_btn
    assert lay.itemAt(4).widget() is win.snapshots_btn    # Snapshots between ? and To Do (24 October)
    assert lay.itemAt(5).widget() is win.todo_btn
    texts = [a.text() for a in win.elicit_menu.actions() if a.isVisible() and not a.isSeparator()]
    assert texts == ["Make ɛλicit request…", "Receive ɛλicitation…"]
    assert "remote elicitation" in win.elicit_btn.toolTip()


def test_the_request_dialog(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    gatto = db.entry_by_ref("D035")
    acqua = db.entry_by_ref("L062")
    dlg = ed.RequestDialog(win, [acqua.tokens[0].id, gatto.tokens[0].id])
    assert dlg.l2.currentData() == "da" and dlg.speaker.currentData() == "SP1"
    assert len(dlg.model.rows) == 2                                   # only what was added (24 October)
    for r in dlg.model.rows:                                          # a soundfile means rerecord
        assert r.kind == (el.RERECORD if r.recorded else el.NEW)
    dlg.l2_name.setText("italiensk")
    kinds = [(i.kind, i.entry.ref) for i in dlg.items()]
    assert kinds == [(el.NEW, "D035"), (el.RERECORD, "L062")]         # in the database's order
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    monkeypatch.setattr(ed.SentDialog, "exec", lambda self: None)
    from lemmatrix import cloud_keys
    assert dlg.send_by.currentData() == ("drive" if cloud_keys.google_ready() else "file")
    dlg.send_by.setCurrentIndex(dlg.send_by.findData("file"))       # the zip route (no Google in tests)
    dlg._make()
    assert dlg.made is not None and dlg.made.exists()
    assert dlg.request.language_names["da"] == "italiensk"
    from lemmatrix.model import today
    notes = win.doc.notebook.session(today()).notes             # Josh, 21 October: a line in the notebook
    rs = dlg.request.researcher["name"]
    assert notes.splitlines()[-2:] == ["=====ELICIT HISTORY=====", f"{rs} sent ɛλicit request to SP1"]
    monkeypatch.setattr(ed.QFileDialog, "getOpenFileName", lambda *a, **k: (str(zp), ""))
    monkeypatch.setattr(ed.ReviewDialog, "exec", lambda self: None)
    zp = _response(el.stored_requests(db.path)[0], dlg.made.parent / "r.zip")
    ed.receive_zip(win)
    assert win.doc.notebook.session(today()).notes.splitlines()[-2:] == [
        f"{rs} sent ɛλicit request to SP1", "Received ɛλicit request from SP1"]


def test_the_request_lists_only_what_was_added(win, monkeypatch):
    """Josh, 24 October: the request's list is only what was added from the main window and Texts
    and utterances (right-click → Add to ɛλicit request); nothing is chosen in the dialogue. Right-click
    or Delete takes the selected rows out; an empty request says how to fill it; the list is kept
    until a request is made."""
    from PySide6.QtCore import QItemSelectionModel
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    gatto, pane = db.entry_by_ref("D035"), db.entry_by_ref("J114")
    dlg = ed.RequestDialog(win, win._elicit_preselect())
    assert dlg.model.rows == [] and dlg.pages.currentWidget() is dlg.empty
    assert "Add to ɛλicit request" in dlg.empty.text() and dlg.count.text() == ""
    assert not dlg.make_btn.isEnabled()
    dlg.reject()
    text, _, fn, on = win.elicit_menu_item(gatto.tokens[0])
    assert text == "Add to ɛλicit request" and on
    fn()
    win.toggle_elicit(db.utterance_by_ref("U001").token)
    win.toggle_elicit(pane.tokens[0])
    assert win.elicit_menu_item(gatto.tokens[0])[0] == "Remove from ɛλicit request"
    dlg = ed.RequestDialog(win, win._elicit_preselect())
    assert dlg.pages.currentWidget() is dlg.table
    assert {i.entry.ref for i in dlg.items()} == {"D035", "J114", "U001"}
    assert len(dlg.model.rows) == 3 and not hasattr(dlg, "ticked_only") and not hasattr(dlg, "new_table")
    dlg.search.setText("pane")                                      # the search filters the request's list
    assert dlg.proxy.rowCount() == 1
    dlg.search.clear()
    sel = dlg.table.selectionModel()                                # Ctrl+click two, then Remove
    for ref in ("J114", "U001"):
        i = next(n for n, r in enumerate(dlg.model.rows) if r.entry.ref == ref)
        sel.select(dlg.proxy.mapFromSource(dlg.model.index(i, 0)),
                   QItemSelectionModel.Select | QItemSelectionModel.Rows)
    dlg.remove_selected()
    assert [r.entry.ref for r in dlg.model.rows] == ["D035"]
    dlg.reject()                                                    # closed: the list is kept
    assert win.elicit_basket == [gatto.tokens[0].id]
    dlg = ed.RequestDialog(win, win._elicit_preselect())
    dlg.made = Path("made.zip")                                     # as if a request was made
    dlg.accept()
    assert win.elicit_basket == []
    win.toggle_elicit(gatto.tokens[0])
    win.load_database(storage.load(db.path))                        # opened again: its workspace keeps it
    assert win.elicit_basket == [gatto.tokens[0].id]


def test_review_puts_recordings_in_and_undo_takes_them_out(win, tmp_path):
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.write_request(db, req, items)
    st = el.receive(db, _response(el.stored_requests(db.path)[0], tmp_path / "r.zip", skip={3}))
    win.refresh_elicit_icon()
    assert "10 recordings waiting" in win.elicit_btn.toolTip() and win.elicit_review.isVisible()
    acqua = db.entry_by_ref("L062")
    old_name = acqua.tokens[0].file
    old_size = (storage.sound_folder(db) / old_name).stat().st_size
    n_utts = len(db.utterances)
    dlg = ed.ReviewDialog(win, st)
    dlg.autoplay.setChecked(False)
    dlg.table.setCurrentCell(4, 1)                                   # libri: rejected
    dlg.decide(el.REJECTED)
    dlg.approve_all()
    dlg.accept()
    gatto = db.entry_by_ref("D035")
    t = gatto.tokens[0]
    assert t.file == "ITA-STD_D035_cat.wav" and t.speaker == "SP1" and t.collected == "2026-10-21"
    assert (storage.sound_folder(db) / t.file).exists()
    assert db.entry_by_ref("L062").tokens[0].file == old_name       # the rerecord: the same name, the new sound
    assert (storage.sound_folder(db) / old_name).stat().st_size != old_size
    assert not db.entry_by_ref("K220").tokens[1].file                # rejected
    assert len(db.utterances) == n_utts + 1
    new_u = db.utterances[-1]
    assert new_u.ref == "U004" and new_u.label == "The sun is hot"
    assert [u.ref for u in dlg.new_utterances] == ["U004"]           # said where it went
    again_dlg = ed.ReviewDialog(win, el.load_stored(st.folder))
    assert again_dlg.table.item(10, 4).text() == "Done (utterance U004)"
    again_dlg.decisions.clear()
    again_dlg.reject()
    assert new_u.token.get("Translation", "da") == "Solen er varm."
    assert (storage.utterance_folder(db) / new_u.token.file).exists()
    st = el.load_stored(st.folder)
    assert el.waiting(db, st) == [] and st.review["5"]["decision"] == el.REJECTED
    assert "remote elicitation" in win.elicit_btn.toolTip()
    win.doc.undo.undo()                                              # one undo step takes it all out
    assert not db.entry_by_ref("D035").tokens[0].file and len(db.utterances) == n_utts
    assert (storage.sound_folder(db) / old_name).stat().st_size == old_size
    assert not (storage.sound_folder(db) / "ITA-STD_D035_cat.wav").exists()
    assert len(el.waiting(db, st)) == 9                              # waiting again (libri stays rejected)
    win.doc.undo.redo()
    assert db.entry_by_ref("D035").tokens[0].file == "ITA-STD_D035_cat.wav" and len(db.utterances) == n_utts + 1
    assert el.waiting(db, st) == []
    again = el.items_again(db, st, dlg._again_numbers())
    assert [(i.kind, i.entry.ref) for i in again] == [(el.NEW, "J114"), (el.NEW, "K220")]


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


# ---- stage 2: through Google Drive (a stand-in Drive in memory) ----------------------------

class FakeDrive:
    """What gdrive.Drive does, in memory: folders, files, shares and upload links."""

    def __init__(self):
        self.files = {}                    # id -> {name, parent, data, mime, shared}
        self.sessions = {}                 # upload link -> (name, parent)
        self.n = 0

    def _id(self):
        self.n += 1
        return f"f{self.n}"

    def find_folder(self, name):
        return next((i for i, f in self.files.items() if f["name"] == name and f["parent"] == ""), "")

    def create_folder(self, name, parent=""):
        i = self._id()
        self.files[i] = {"name": name, "parent": parent, "data": b"", "mime": "folder", "shared": False}
        return i

    def upload(self, name, data, mime, parent):
        i = self._id()
        self.files[i] = {"name": name, "parent": parent, "data": data, "mime": mime, "shared": False}
        return i

    def share_by_link(self, fid):
        self.files[fid]["shared"] = True

    def upload_link(self, name, mime, parent, origin=""):
        link = f"https://upload.example/{self._id()}"
        self.sessions[link] = (name, parent)
        return link

    def put(self, link, data):             # what the page does with an upload link
        name, parent = self.sessions.pop(link)
        return self.upload(name, data, "", parent)

    def list_folder(self, folder):
        if folder not in self.files:
            raise el.ElicitError("not found")
        return [{"id": i, "name": f["name"]} for i, f in self.files.items() if f["parent"] == folder]

    def download(self, fid):
        return self.files[fid]["data"]

    def delete(self, fid):
        for i in [i for i, f in self.files.items() if f["parent"] == fid]:
            self.delete(i)
        self.files.pop(fid, None)


def _wav_bytes(tmp_path, n=1, name=""):
    """A recording as the page sends it: FLAC when the card's file is .flac (the default)."""
    x = (3000 * np.sin(np.arange(8000) / (3 + n))).astype("<i2")
    if name.endswith(".flac"):
        import soundfile
        p = tmp_path / f"w{n}.flac"
        soundfile.write(str(p), x, 8000, subtype="PCM_16", format="FLAC")
    else:
        p = tmp_path / f"w{n}.wav"
        audio.write_pcm16(p, x, 8000)
    return p.read_bytes()


def test_a_request_through_drive(db, tmp_path):
    drive = FakeDrive()
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da", "italiensk")
    link = el.publish_drive(db, req, items, drive, "KEY")
    assert req.transport == "drive" and link == f"{el.WEB_PAGE}#d={req.drive['request']}&k=KEY"
    assert req.expires == "%s" % (__import__("datetime").date.fromisoformat(req.created[:10])
                                  + __import__("datetime").timedelta(days=7)).isoformat()
    folder = req.drive["folder"]
    top = drive.files[folder]["parent"]
    assert drive.files[top]["name"] == "ɛλicit" and not drive.files[folder]["shared"]
    shared = sorted(f["name"] for f in drive.files.values() if f["shared"])
    assert shared == ["01.png", "02.png", "06.gif", "07_original.wav", "08_original.wav", "09_original.wav",
                      "request.json"]
    sent = json.loads(drive.download(req.drive["request"]))
    assert all(c["upload"] for c in sent["cards"]) and sent["drive"]["response"] and sent["drive"]["status"]
    assert sent["cards"][0]["image_id"] and sent["cards"][6]["original_id"]
    msg = el.message_text(req)
    assert msg.endswith(link) and "Open the request file" not in msg and "Hej Speaker 1!" in msg
    st = el.outstanding_drive(db)[0]
    assert st.request.id == req.id
    # the speaker records cards 1 and 2, skips 3, and stops
    for c in st.request.cards[:2]:
        drive.put(c.upload, _wav_bytes(tmp_path, c.n, c.file))
    state = el.drive_state(drive, st)
    assert (state.finished, state.uploaded, state.summary(st.request)) == (False, 2, "2 of 11 recorded so far")
    # ... then comes back and finishes
    for c in st.request.cards[3:]:
        drive.put(c.upload, _wav_bytes(tmp_path, c.n, c.file))
    answers = [{"n": c.n, "status": "skipped"} if c.n == 3 else
               {"n": c.n, "status": "recorded", "file": c.file, "date": "2026-10-22"} for c in st.request.cards]
    drive.put(st.request.drive["response"], json.dumps({"format": el.RESPONSE_FORMAT, "request": req.id,
                                                        "speaker": "SP1", "cards": answers}).encode())
    state = el.drive_state(drive, st)
    assert state.finished and state.uploaded == 10
    got = el.receive_drive(db, st, drive, state)
    assert [c.n for c in el.waiting(db, got)] == [1, 2, 4, 5, 6, 7, 8, 9, 10, 11]
    assert el.recorded_date(got, 1) == "2026-10-22"
    assert folder not in drive.files                                  # destroyed in Drive
    assert el.outstanding_drive(db) == []


def test_unfinished_and_turned_down_drive_requests(db, tmp_path):
    drive = FakeDrive()
    items = _items(db)[:3]
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.publish_drive(db, req, items, drive, "KEY")
    st = el.outstanding_drive(db)[0]
    drive.put(st.request.cards[0].upload, _wav_bytes(tmp_path, 1, st.request.cards[0].file))
    got = el.receive_drive(db, st, drive)                            # taken as it is: the rest not reached
    assert [c.n for c in el.waiting(db, got)] == [1] and got.answer(2) is None
    req2 = el.new_request(db, items, "SP2", "RS1", "da")
    el.publish_drive(db, req2, items, drive, "KEY")
    st2 = el.outstanding_drive(db)[0]
    drive.put(st2.request.drive["status"], json.dumps({"reason": "not around"}).encode())
    assert el.drive_state(drive, st2).summary(st2.request) == "turned down on the phone (not around)"
    el.close_drive(drive, st2, "withdrawn")
    assert el.outstanding_drive(db) == [] and st2.request.drive["folder"] not in drive.files


def test_a_failed_publish_leaves_nothing_in_drive(db):
    class Broken(FakeDrive):
        def upload_link(self, *a, **k):
            raise el.ElicitError("Google Drive answered 500")
    drive = Broken()
    items = _items(db)[:2]
    req = el.new_request(db, items, "SP1", "RS1", "da")
    with pytest.raises(el.ElicitError):
        el.publish_drive(db, req, items, drive, "KEY")
    assert [f["name"] for f in drive.files.values()] == ["ɛλicit"]


def test_the_drive_client_speaks_googles_api():
    """gdrive.Drive's requests, against a stand-in for urllib (no network)."""
    from lemmatrix import gdrive
    import time
    calls = []

    class R:
        def __init__(self, status=200, body=b"{}", headers=None):
            self.status, self._b, self.headers = status, body, headers or {}

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=0):
        calls.append((req.get_method(), req.full_url, dict(req.header_items()), req.data))
        if "uploadType=resumable" in req.full_url:
            return R(200, b"{}", {"Location": "https://upload.example/s1"})
        return R(200, json.dumps({"id": "x1", "files": []}).encode())
    d = gdrive.Drive({"access_token": "A", "refresh_token": "R", "expires_at": time.time() + 999}, opener=opener)
    assert d.upload_link("01_D035.wav", "audio/wav", "F") == "https://upload.example/s1"
    method, url, headers, body = calls[-1]
    assert method == "POST" and headers["Authorization"] == "Bearer A" and headers["Origin"] == gdrive.PAGE_ORIGIN
    assert headers["X-upload-content-type"] == "audio/wav" and json.loads(body)["parents"] == ["F"]
    assert d.upload("a.json", b"{}", "application/json", "F") == "x1"
    assert b"multipart" not in calls[-1][3] and "multipart/related" in calls[-1][2]["Content-type"]
    d.share_by_link("x1")
    assert json.loads(calls[-1][3]) == {"type": "anyone", "role": "reader"}
    assert d.find_folder("ɛλicit") == ""
    with pytest.raises(gdrive.SignInNeeded):
        gdrive.Drive({}).access()


def test_the_page_through_a_drive_link(db, tmp_path):
    """The page opens a Drive link, uploads each recording as it is good and response.json at the
    end, and tells the researcher when turned down; Google's endpoints are stood in for."""
    pw = pytest.importorskip("playwright.sync_api")
    import functools
    import http.server
    import threading
    drive = FakeDrive()
    items = _items(db)[:2] + [_items(db)[6]]                         # gatto, gatti, acqua (rerecord)
    req = el.new_request(db, items, "SP1", "RS1", "da", "italiensk")
    link = el.publish_drive(db, req, items, drive, "KEY")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "docs"))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake = tmp_path / "voice.wav"
    audio.write_wav(fake, 0.3 * np.sin(np.arange(48000 * 2) / 7), 48000, 16)
    cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"}

    def google(route):
        r = route.request
        if r.method == "OPTIONS":
            return route.fulfill(status=200, headers=cors)
        if r.url.startswith("https://upload.example/"):
            drive.put(r.url, r.post_data_buffer or b"")
            return route.fulfill(status=200, headers=cors, body="{}")
        fid = r.url.split("/files/")[1].split("?")[0]
        assert "key=KEY" in r.url and drive.files[fid]["shared"]
        return route.fulfill(status=200, headers=cors, body=drive.files[fid]["data"])
    page_link = link.replace(el.WEB_PAGE, f"http://127.0.0.1:{server.server_port}/elicit/")
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch(args=["--use-fake-ui-for-media-stream",
                                                  "--use-fake-device-for-media-stream",
                                                  f"--use-file-for-fake-audio-capture={fake}"])
            except Exception as exc:                                  # noqa: BLE001
                pytest.skip(f"no Chromium for Playwright: {exc}")
            ctx = browser.new_context()
            ctx.route("https://www.googleapis.com/**", google)
            ctx.route("https://upload.example/**", google)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(page_link)

            def click(text):
                page.locator("button", has_text=text).first.click()
            for _ in range(3):
                click("Yes")
            click("I'm ready")
            page.locator("img").first.wait_for()                          # the picture came from Drive
            for n in range(3):
                page.locator("button.rec").click()
                page.wait_for_timeout(500)
                page.locator("button.rec").click()
                click("It's good")
            click("Goodbye")
            page.get_by_text("Your recordings have reached Researcher 1").wait_for(timeout=15000)
            assert not errors, errors
            # a second request, turned down on the phone
            req2 = el.new_request(db, items[:1], "SP1", "RS1", "da")
            link2 = el.publish_drive(db, req2, items[:1], drive, "KEY")
            page.goto(link2.replace(el.WEB_PAGE, f"http://127.0.0.1:{server.server_port}/elicit/"))
            page.reload()
            click("No")
            click("is not around")
            page.get_by_text("was not around").wait_for()
            browser.close()
    finally:
        server.shutdown()
    st = next(s for s in el.outstanding_drive(db) if s.request.id == req.id)
    state = el.drive_state(drive, st)
    assert state.finished and state.uploaded == 3
    got = el.receive_drive(db, st, drive, state)
    assert [c.n for c in el.waiting(db, got)] == [1, 2, 3]
    st2 = next(s for s in el.outstanding_drive(db) if s.request.id == req2.id)
    assert el.drive_state(drive, st2).turned_down == "not around"


def test_the_button_rains_when_recordings_are_ready_in_drive(win, monkeypatch):
    """Josh, 21 October: a finished request in Google Drive makes the button rain (looked at in the
    background on opening and every 10 minutes, when signed in)."""
    from lemmatrix import cloud_keys, gdrive
    from PySide6.QtWidgets import QApplication
    import time
    db = win.doc.db
    drive = FakeDrive()
    items = _items(db)[:2]
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.publish_drive(db, req, items, drive, "KEY")
    monkeypatch.setattr(cloud_keys, "google_ready", lambda: True)
    monkeypatch.setattr(gdrive, "Drive", lambda token, on_token=None: drive)
    win.prefs.google_token = {"refresh_token": "R"}
    win.elicit_drive_ready = {}
    win.check_elicit_drive()
    for _ in range(100):
        QApplication.processEvents()
        if not win._elicit_checking:
            break
        time.sleep(0.02)
    assert win.elicit_drive_ready == {} and "1 request out" in win.elicit_btn.toolTip()
    st = el.outstanding_drive(db)[0]
    drive.put(st.request.cards[0].upload, b"RIFF")
    drive.put(st.request.drive["response"], json.dumps({"request": req.id, "cards": []}).encode())
    win.check_elicit_drive()
    for _ in range(100):
        QApplication.processEvents()
        if not win._elicit_checking:
            break
        time.sleep(0.02)
    assert req.id in win.elicit_drive_ready
    assert "SP1 has finished: 1 recording in Google Drive" in win.elicit_btn.toolTip()
    el.close_drive(drive, st)                                        # received or withdrawn: no more rain
    win.refresh_elicit_icon()
    assert "has finished" not in win.elicit_btn.toolTip()
    win.prefs.google_token = {}


def test_the_request_is_remembered_until_reset(win, monkeypatch):
    """Closing Make ɛλicit request keeps its list and details (Josh, 21 October); Reset request puts
    everything to zero: the list emptied, the details back to their defaults (Josh, 24 October)."""
    from lemmatrix.ui import elicit_dialogs as ed, widgets
    db = win.doc.db
    gatto = db.entry_by_ref("D035")
    dlg = ed.RequestDialog(win, [gatto.tokens[0].id], draft=win.elicit_draft)
    defaults = dlg.draft()
    dlg.l2.setCurrentIndex(dlg.l2.findData(""))                       # no second language
    dlg.repeat.setChecked(False)
    dlg.speaker.setCurrentIndex(dlg.speaker.findData("SP2"))
    dlg.audio.setCurrentIndex(dlg.audio.findData("wav"))
    dlg.reject()
    dlg = ed.RequestDialog(win, win._elicit_preselect(), draft=win.elicit_draft)
    assert dlg.l2.currentData() == "" and not dlg.repeat.isChecked() and dlg.speaker.currentData() == "SP2"
    assert [i.kind for i in dlg.items()] == [el.NEW]
    monkeypatch.setattr(widgets, "ask", lambda *a, **k: False)        # Cancel: nothing changes
    dlg.reset_request()
    assert len(dlg.items()) == 1 and dlg.speaker.currentData() == "SP2"
    monkeypatch.setattr(widgets, "ask", lambda *a, **k: True)
    dlg.reset_request()
    assert dlg.items() == [] and dlg.pages.currentWidget() is dlg.empty
    assert dlg.draft() == defaults                                    # every detail back to its default
    dlg.reject()
    assert win.elicit_basket == [] and win.elicit_draft == defaults
    dlg = ed.RequestDialog(win, [gatto.tokens[0].id], draft=win.elicit_draft)
    dlg.speaker.setCurrentIndex(dlg.speaker.findData("SP2"))
    dlg.made = Path("made")                                          # a request made: the details stay
    dlg.accept()
    assert win.elicit_basket == [] and win.elicit_draft["speaker"] == "SP2"


def test_flac_from_the_page_is_lossless_and_becomes_wav(db, tmp_path):
    """The page's own FLAC encoder (docs/elicit/flac.js, run in Node) against libsndfile, on Josh's
    speech; and a request asking for FLAC comes in as WAV, sample for sample."""
    import shutil as _sh
    import subprocess
    import soundfile
    if not _sh.which("node"):
        pytest.skip("no Node.js")
    wavs = sorted((TEST_DB.parent / "Soundfiles" / "Utterances").glob("*.wav"))
    x, rate = soundfile.read(str(wavs[0]), dtype="int16")
    raw = tmp_path / "x.raw"
    raw.write_bytes(np.asarray(x, "<i2").tobytes())
    js = tmp_path / "enc.js"
    js.write_text("const {encodeFlac}=require(process.argv[2]);const fs=require('fs');"
                  "const b=fs.readFileSync(process.argv[3]);"
                  "const s=new Int16Array(b.buffer,b.byteOffset,b.length/2);"
                  "fs.writeFileSync(process.argv[4],encodeFlac(s,+process.argv[5]));")
    out = tmp_path / "x.flac"
    subprocess.run(["node", str(js), str(ROOT / "docs" / "elicit" / "flac.js"), str(raw), str(out), str(rate)],
                   check=True)
    y, r = soundfile.read(str(out), dtype="int16")
    assert r == rate and np.array_equal(y, x)
    assert out.stat().st_size < 0.75 * raw.stat().st_size
    # a FLAC request: the cards' files are .flac; received, they are WAVs with the same samples
    items = _items(db)[:2]
    req = el.new_request(db, items, "SP1", "RS1", "da", audio="flac")
    assert all(c.file.endswith(".flac") for c in req.cards)
    el.write_request(db, req, items)
    st = el.stored_requests(db.path)[0]
    zpath = tmp_path / "back.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(out, "recordings/" + st.request.cards[0].file)
        zf.writestr("response.json", json.dumps({"format": el.RESPONSE_FORMAT, "request": req.id, "speaker": "SP1",
                                                 "cards": [{"n": 1, "status": "recorded", "date": "2026-10-21",
                                                            "file": st.request.cards[0].file}]}))
    got = el.receive(db, zpath)
    wav = got.recording(1)
    assert wav.suffix == ".wav" and not list(got.received.glob("*.flac"))
    back, rate2 = soundfile.read(str(wav), dtype="int16")
    assert rate2 == rate and np.array_equal(back, x)
    assert audio.read_info(wav) == {"IART": "SP1", "ICRD": "2026-10-21"}
    wreq = el.new_request(db, items, "SP1", "RS1", "da", audio="wav")
    assert all(c.file.endswith(".wav") for c in wreq.cards)
    assert el.estimated_size(db, items, "flac") < el.estimated_size(db, items, "wav")


def test_send_again_puts_the_cards_back_on_the_request(win, monkeypatch):
    """Send again (the review): the tokens and utterances join the request's list; new sentences
    can't be sent again, since requests have none any more (Josh, 24 October)."""
    from types import SimpleNamespace
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    gatto, pane = db.entry_by_ref("D035"), db.entry_by_ref("J114")
    win.elicit_basket = [pane.tokens[0].id]
    items = [el.Item(el.NEW, gatto, gatto.tokens[0]), el.Item(el.NEW_UTTERANCE, translations={"en": "Hi."})]
    monkeypatch.setattr(el, "items_again", lambda *a: items)
    opened = []
    monkeypatch.setattr(ed.RequestDialog, "exec", lambda self: opened.append(self) or 0)
    fake = SimpleNamespace(main=win, db=db, st=SimpleNamespace(request=SimpleNamespace(speaker={"code": "SP2"})),
                           _again_numbers=lambda: [1, 2], accept=lambda: None)
    ed.ReviewDialog.send_again(fake)
    dlg = opened[0]
    assert {r.entry.ref for r in dlg.model.rows} == {"D035", "J114"} and dlg.speaker.currentData() == "SP2"
    assert set(win.elicit_basket) == {pane.tokens[0].id, gatto.tokens[0].id}
