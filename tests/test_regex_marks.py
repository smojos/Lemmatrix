# SPDX-License-Identifier: AGPL-3.0-or-later
"""Filter for… → RegeX sees the text as it is, marks and all (Josh, 27 October)."""

from lemmatrix.filters import TextFilter, REGEX, ANYWHERE


def test_regex_finds_length_and_modifiers():
    assert TextFilter("aː", REGEX).matches("baːt")
    assert not TextFilter("aː", REGEX).matches("bat")
    assert TextFilter("ː", REGEX).matches("baːt")
    assert not TextFilter("ː", REGEX).matches("bat")
    assert TextFilter("tʰ$", REGEX).matches("dɪɪtʰ")
    assert not TextFilter("tʰ$", REGEX).matches("dɪɪt")


def test_regex_sees_marks_apart_from_letters():
    assert TextFilter("́", REGEX).matches("bá")           # the acute alone
    assert not TextFilter("́", REGEX).matches("bà")
    assert TextFilter("á", REGEX).matches("bá")                # typed precomposed or not
    assert TextFilter("á", REGEX).matches("bá")
    assert TextFilter("a", REGEX).matches("bá")                # the letter under it
    assert TextFilter("^b.$", REGEX).matches("ba") and not TextFilter("^b.$", REGEX).matches("bá")


def test_regex_case_and_plain_unchanged():
    assert TextFilter("BAː", REGEX).matches("baːt")
    assert not TextFilter("BAː", REGEX, match_case=True).matches("baːt")
    assert TextFilter("deet", ANYWHERE).matches("deetʰ")         # plain still folds
    assert TextFilter("aː", ANYWHERE, match_diacritics=True).matches("baːt")


def test_dialog_label_and_greyed_for_regex(app):
    from lemmatrix.ui.filter_dialogs import FilterForDialog
    d = FilterForDialog(None, "Phonetic")
    assert d.diacritics.text() == "Maːtcʰ &Fûnkỹ stṵff"
    assert d.diacritics.isEnabled()
    d.radios[REGEX].setChecked(True)
    assert not d.diacritics.isEnabled()
    d.radios[ANYWHERE].setChecked(True)
    assert d.diacritics.isEnabled()
