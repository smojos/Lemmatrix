# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Safe writing (the audit, section 5, 25 October 2026): every file Lemmatrix writes over an older
one is written under a temporary name, put on the disk (fsync) and only then swapped in, as the
database always was. Recordings above all; also ɛλicit's review, request zips and received
recordings, Full backups and the TextGrids Lemmatrix writes."""

import json
import os
import wave

import numpy as np
import pytest

from lemmatrix import audio, elicit as el, layout, model, textgrid as tgmod
from lemmatrix.lines import Buffer


class Synced:
    """Which files were put on the disk (each fsync, by its file's identity, which a rename keeps:
    the temporary file synced is the file swapped in). Works on Windows and Linux alike."""

    def __init__(self):
        self.ids = []

    def __len__(self):
        return len(self.ids)

    def has(self, path) -> bool:
        st = os.stat(path)
        return (st.st_dev, st.st_ino) in self.ids


@pytest.fixture
def synced(monkeypatch):
    out = Synced()
    real = os.fsync

    def spy(fd):
        st = os.fstat(fd)
        out.ids.append((st.st_dev, st.st_ino))
        return real(fd)
    monkeypatch.setattr(os, "fsync", spy)
    return out


def _frames(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes()


def test_the_helper_puts_the_file_on_the_disk_before_the_swap(tmp_path, synced):
    p = tmp_path / "a.wav"
    model.write_bytes_safely(p, b"new")
    assert p.read_bytes() == b"new" and synced.has(p) and len(synced) == 1
    assert not (tmp_path / "a.wav.part").exists()


def test_a_failed_swap_leaves_the_old_file_whole(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    p.write_bytes(b"old recording")

    def power_cut(*a):
        raise OSError("the battery died")
    monkeypatch.setattr(os, "replace", power_cut)
    with pytest.raises(OSError):
        model.write_bytes_safely(p, b"new recording")
    assert p.read_bytes() == b"old recording"


def test_recordings_are_put_on_the_disk(tmp_path, synced):
    x = (3000 * np.sin(np.arange(8000) / 3)).astype("<i2")
    audio.write_pcm16(tmp_path / "t.wav", x, 8000)
    audio.write_wav(tmp_path / "u.wav", x.astype(np.float32) / 32768, 8000)
    assert synced.has(tmp_path / "t.wav") and synced.has(tmp_path / "u.wav")
    assert _frames(tmp_path / "t.wav") == 8000 and _frames(tmp_path / "u.wav") == 8000   # whole


def test_flac_from_elicit_is_put_on_the_disk(tmp_path, synced):
    soundfile = pytest.importorskip("soundfile")
    x = (3000 * np.sin(np.arange(8000) / 3)).astype("<i2")
    soundfile.write(str(tmp_path / "r.flac"), x, 8000, subtype="PCM_16", format="FLAC")
    audio.flac_to_wav(tmp_path / "r.flac", tmp_path / "r.wav")
    assert synced.has(tmp_path / "r.wav") and _frames(tmp_path / "r.wav") == 8000


def test_the_review_is_written_safely(tmp_path, synced, monkeypatch):
    st = el.Stored(tmp_path, None, review={"1": {"decision": "approved"}})
    st.save_review()
    assert synced.has(tmp_path / "review.json")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("crash")))
    st.review = {"1": {"decision": "rejected"}}
    with pytest.raises(OSError):
        st.save_review()
    assert json.loads((tmp_path / "review.json").read_text())["1"]["decision"] == "approved"   # was cut


def test_textgrids_lemmatrix_writes_are_put_on_the_disk(tmp_path, synced):
    p = tmp_path / "T.TextGrid"
    tgmod.write_example(p, {"tx": [(0.0, 1.0, "aa")]}, 2.0)
    synced.ids.clear()
    b = Buffer(p)

    class Db:                                     # backup_textgrid needs only the database's path
        path = str(tmp_path / "LXX.xml")
    b.write(Db())
    assert synced.has(p)


def test_the_full_backup_is_put_on_the_disk(tmp_path, synced):
    main = tmp_path / "main"
    main.mkdir()
    (main / "LXX.xml").write_text("<database/>")
    layout.full_backup(main / "LXX.xml", tmp_path / "backup.zip")
    assert synced.has(tmp_path / "backup.zip")


# ---------------------------------------------------------------- ɛλicit's zips and received recordings

from test_elicit import FakeDrive, _items, _wav_bytes, db  # noqa: E402,F401  (fixture and helpers)


def test_the_request_zip_is_put_on_the_disk(db, synced):
    items = _items(db)
    path = el.write_request(db, el.new_request(db, items, "SP1", "RS1", "da"), items)
    assert synced.has(path)


def test_received_recordings_are_on_the_disk_before_drive_lets_them_go(db, tmp_path, synced):
    drive = FakeDrive()
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "da")
    el.publish_drive(db, req, items, drive, "KEY")
    st = el.outstanding_drive(db)[0]
    c = st.request.cards[0]
    drive.put(c.upload, _wav_bytes(tmp_path, c.n, c.file))
    synced.ids.clear()
    got = el.receive_drive(db, st, drive)
    wav = got.recording(c.n)
    assert wav is not None and synced.has(wav)                  # the WAV made from it
    assert req.drive["folder"] not in drive.files                  # and only then was Drive's copy deleted
