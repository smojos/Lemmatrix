# SPDX-License-Identifier: AGPL-3.0-or-later
"""Edit → Metadata's gloss languages as chips (Josh, 28 October): a search offering only the supported
languages (English, French, Arabic, Amharic for v1), English fixed (a chip with no ✕), a language the
database already has but Lemmatrix doesn't offer kept and removable, not added again; the gloss field
itself is built in, never deleted."""

import pytest

pytest.importorskip("PySide6")

from lemmatrix import wordlists  # noqa: E402


def test_the_supported_languages():
    assert list(wordlists.supported_gloss_languages()) == ["en", "fr", "ar", "am"]
    assert all(wordlists.gloss_file(c) for c in ("fr", "ar", "am"))   # each reads its shipped glosses


def test_the_chips(win):
    from lemmatrix.ui.glossbox import GlossLanguagesBox
    box = GlossLanguagesBox(["en", "da"])                 # da: the ɛλicit test database's, kept
    assert box.languages() == ["en", "da"]
    assert set(box.offered().values()) == {"fr", "ar", "am"}
    assert not box.remove("en") and box.languages()[0] == "en"           # English fixed
    chips = [box.flow.itemAt(i).widget() for i in range(box.flow.count())]
    assert "✕" not in chips[0].text() and "✕" in chips[1].text()
    assert not box.add("da") and not box.add("sw") and not box.add("xx")   # only the supported
    box._chosen("Amharic")
    assert box.languages() == ["en", "da", "am"]
    box._chosen("ar")                                   # by code, too
    assert box.languages()[-1] == "ar"
    assert box.remove("da") and not box.add("da")       # removed: not offered again
    assert box.languages() == ["en", "am", "ar"]


def test_metadata_writes_the_chips_and_the_gloss_field_stays(win):
    from lemmatrix.ui.dialogs import MetadataDialog
    db = win.doc.db
    dlg = MetadataDialog(win, db)
    dlg.glosses.add("fr")
    dlg.apply()
    assert db.settings.gloss_languages[0] == db.settings.primary_gloss and "fr" in db.settings.gloss_languages
    g = db.settings.entry_field("gloss")
    assert g is not None and g.builtin                   # Edit → Fields refuses to delete it
    dlg.reject()
