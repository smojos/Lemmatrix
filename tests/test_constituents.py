# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The Constituents tier, Settings → Typology and lower-case word classes (IDEAS.md idea 91,
designed with Josh, 28 October; format 16)."""

import shutil
from pathlib import Path

import pytest

from lemmatrix import constituents as cons
from lemmatrix import defaults, storage, typology
from lemmatrix import wordlists as wl
from lemmatrix.model import ListItem

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


# ---- the notation ---------------------------------------------------------------------------
def test_nesting_floating_labels_and_words_outside():
    p = cons.parse("[_ [ADJ]MOD]NP V [_ _]NP _")
    assert [s.label for s in p.slots] == ["", "ADJ", "V", "", "", ""]
    assert [(x.label, x.start, x.end, x.depth) for x in p.phrases] == \
        [("MOD", 1, 1, 1), ("NP", 0, 1, 0), ("NP", 3, 4, 0)]
    assert p.depth == 2 and not p.errors
    assert p.labels() == ["ADJ", "V", "MOD", "NP"]


def test_an_empty_word_level_segment_is_a_plain_word():
    assert [s.label for s in cons.parse("[{} V]VP").slots] == ["", "V"]


def test_spaces_round_brackets_are_optional():
    a, b = cons.parse("[_[ADJ]MOD]NP V[_ _]NP"), cons.parse("[_ [ADJ]MOD]NP V [_ _]NP")
    assert [(s.index, s.label) for s in a.slots] == [(s.index, s.label) for s in b.slots]
    assert [(x.label, x.start, x.end) for x in a.phrases] == [(x.label, x.start, x.end) for x in b.phrases]


def test_problems_are_said_never_refused():
    assert cons.problem("", 3) == ""
    assert "not closed" in cons.problem("[_ _", 2)
    assert "no [" in cons.problem("_ ]NP", 1)
    assert "empty" in cons.problem("[]NP _", 1)
    assert cons.problem("[_ _]NP V", 3) == ""
    assert cons.problem("[_ _]NP V", 4) == "3 words here, 4 in the line it lines up with"
    assert cons.problem("[_ _]NP V", None) == ""            # nothing to line up with


def test_unknown_labels_are_marked():
    s = defaults.default_settings()
    assert cons.unknown(s, "[_ [ADJ]MOD]NP V [_ _]NP") == ["MOD"]      # MOD: no list has it
    assert cons.unknown(s, "[N]NP V [_]OBL TOP FOC") == []            # N, V from the Word Class list


def test_latex_brackets_with_the_words_put_in():
    out = cons.to_brackets("[_ [ADJ]MOD]NP V", ["kʊ̀ʊn", "rɪ̀ɪŋ", "tʌ́"])
    assert out.startswith("[$_{\\textsc{np}}$ kʊ̀ʊn [$_{\\textsc{mod}}$ ")
    assert out.count("[") == out.count("]") and "_" not in out.replace("$_{", "")
    assert cons.to_brackets("[_ _", ["a", "b"]) == "a b"               # unreadable: the words only


# ---- the field, the tier, the labels, the word classes: a new database --------------------------
def test_a_new_database_has_the_core_field_hidden_tier_and_labels():
    db = defaults.new_database()
    s = db.settings
    names = [f.name for f in s.token_fields]
    assert names.index("Constituents") == names.index("Morphemes") + 1
    f = s.token_field("constituents")
    assert f.abbr == "cns" and f.builtin                               # renamable, not deletable
    assert s.tier_mapping.rule("cns").field == "Constituents"
    assert [g.name for g in s.constituent_labels] == ["Relations", "Phrases", "Topic and focus"]
    assert {i.abbr for g in s.constituent_labels for i in g.children} >= {"S", "A", "O", "V", "OBL", "NP",
                                                                        "VP", "ADVP", "TOP", "FOC"}


@pytest.mark.real_defaults
def test_new_databases_have_lower_case_word_classes_with_caps_abbreviations():
    db = defaults.new_database()
    wc = db.settings.entry_field("word-class")
    assert [(i.name, i.abbr) for i in wc.items] == [("noun", "N"), ("verb", "V"), ("pronoun", "PRO"),
                                                    ("quant", "QUANT"), ("adjective", "ADJ"), ("adverb", "ADV")]
    usual = {g.name: g.usual for g in db.settings.tags.groups}
    assert usual["Nominal"] == ["noun"] and usual["Verbal"] == ["verb"]


def test_round_trip_format_16(tmp_path):
    db = defaults.new_database()
    db.metadata.typology = {"tone": "tonal", "morphology": "root-and-pattern", "order": "VSO"}
    db.settings.constituent_labels.append(ListItem("Mine", [ListItem("left dislocation", abbr="LD")]))
    p = tmp_path / "x.xml"
    storage.save(db, p)
    text = p.read_text(encoding="utf-8")
    assert 'format="16"' in text
    assert '<feature id="order" value="VSO" wals="81A" />' in text
    assert '<feature id="morphology" value="root-and-pattern" />' in text
    assert '<item name="noun" abbr="N" />' in text
    back = storage.load(p)
    assert back.metadata.typology["order"] == "VSO" and not back.upgraded
    assert back.settings.constituent_labels[-1].children[0].abbr == "LD"
    assert back.settings.entry_field("word-class").items[0].abbr == "N"


def test_order_values_and_wals():
    assert typology.wals("order", "SVO") == "81A" and typology.wals("order", "OV") == "83A"
    assert typology.wals("order", "topic-initial") == "" and typology.wals("tone", "tonal") == ""
    assert [v for v, _ in typology.ORDERS][-1] == "unspecified"
    assert "Dryer" in typology.CITATIONS and "81A" in typology.CITATIONS and "83A" in typology.CITATIONS


def _format_15(tmp_path, xml: str) -> Path:
    """A database as format 15 wrote it: no Constituents field, rule or labels; NOUN and VERB."""
    p = tmp_path / "old.xml"
    for a, b in (('format="16"', 'format="15"'),):
        xml = xml.replace(a, b)
    import re
    xml = re.sub(r'\s*<field name="Constituents"[^>]*/>', "", xml)
    xml = re.sub(r'\s*<tier name="cns"[^>]*/>', "", xml)
    xml = re.sub(r"\s*<constituent-labels>.*?</constituent-labels>", "", xml, flags=re.S)
    xml = re.sub(r'\s*<feature id="(morphology|order)"[^>]*/>', "", xml)
    xml = xml.replace('<item name="noun" abbr="N" />', '<item name="NOUN" />')
    p.write_text(xml, encoding="utf-8")
    return p


def test_an_older_database_gets_the_field_rule_and_labels_but_keeps_its_word_classes(tmp_path):
    db = defaults.new_database()
    e = db.new_entry("D009", "dʌ́ʌm", "goat", "")
    e.set("WordClass", "NOUN")
    db.entries.append(e)
    p = _format_15(tmp_path, storage.to_string(db))
    old = p.read_text(encoding="utf-8")
    assert "Constituents" not in old and "NOUN" in old
    back = storage.load(p)
    assert back.upgraded
    f = back.settings.token_field("constituents")
    assert f is not None and f.name == "Constituents" and f.abbr == "cns"
    assert back.settings.tier_mapping.rule("cns").field == "Constituents"
    assert back.settings.constituent_labels                         # the defaults
    assert back.settings.word_classes()[0] == "NOUN"                # never written over (Josh)
    assert back.word_class(back.entry_by_ref("D009")) == "NOUN"
    assert typology.value(back, "order") == "unspecified"
    storage.save(back, p)
    assert 'format="16"' in p.read_text(encoding="utf-8")


def test_the_tier_rule_is_not_added_over_an_existing_cns_rule(tmp_path):
    db = defaults.new_database()
    p = _format_15(tmp_path, storage.to_string(db))
    p.write_text(p.read_text(encoding="utf-8").replace(
        '<tier name="mb" field="" />', '<tier name="mb" field="" />\n      <tier name="cns" field="Comment" />'),
        encoding="utf-8")
    back = storage.load(p)
    assert [r.field for r in back.settings.tier_mapping.rules if r.tier == "cns"] == ["Comment"]


# ---- the EACW: NOUN = noun -------------------------------------------------------------------
def test_a_new_eacw_database_takes_the_classes_in_lower_case():
    db = defaults.new_database("EACW")
    classes = db.settings.word_classes()
    assert "noun" in classes and "NOUN" not in classes and "dem" in classes
    wc = db.settings.entry_field("word-class")
    assert next(i for i in wc.items if i.name == "dem").abbr == "DEM"
    used = {db.word_class(e) for e in db.entries}
    assert "noun" in used and "verb" in used and not {c for c in used if c and c != c.lower()}


def test_an_old_caps_database_matches_and_adds_in_its_own_style():
    db = defaults.new_database()
    wc = db.settings.entry_field("word-class")
    wc.items = [ListItem(n) for n in ("NOUN", "VERB", "PRONOUN")]
    added = wl.ensure_word_classes(db)
    assert "DEM" in added and "dem" not in db.settings.word_classes()
    item = next(i for i in wl.get(wl.EACW).items if i.word_class == "NOUN" and i.default)
    e = db.new_entry(item.number, gloss=item.gloss, word_class=db.settings.word_class_named(item.word_class))
    wl.fill_item(db, e, item)
    assert db.word_class(e) == "NOUN"
    assert db.settings.word_class_named("noun") == "NOUN"
    assert db.settings.word_class_named("nonsense") == ""


# ---- the samples are converted (Josh: "you convert the two sample databases") -------------------
@pytest.mark.parametrize("path", [SAMPLES / "Sample.xml", SAMPLES / "Elicit test" / "ITA-STD_Elicit_Test.xml"])
def test_the_samples_are_lower_case_and_format_16(path):
    text = path.read_text(encoding="utf-8")
    assert 'format="16"' in text and 'role="constituents"' in text and "<constituent-labels>" in text
    db = storage.load(path)
    assert not db.upgraded
    classes = db.settings.word_classes()
    assert "noun" in classes and not [c for c in classes if c != c.lower()]
    assert all(db.word_class(e) == db.word_class(e).lower() for e in db.entries)
    hints = [h for g in db.settings.tags.all_groups() for h in g.usual]
    assert all(h == h.lower() for h in hints)


# ---- archives: the notation is never scrubbed ----------------------------------------------------
def test_the_notation_is_left_alone_in_archives():
    from lemmatrix import anonymise
    assert "constituents" in anonymise._TRANSCRIPTION_ROLES


# ---- the window ---------------------------------------------------------------------------------
def _db_with_line():
    db = defaults.new_database()
    e = db.new_entry("V001", "tʌ́", "to see", "verb")
    t = e.tokens[0]
    t.set("Phonemic", "kʊ̀ʊn rɪ̀ɪŋ tʌ́ ŋɔ́ɔɲ ɲàmá")
    t.set("Morphemes", "man big saw lion DEF")
    t.set("Constituents", "[_ [ADJ]MOD]NP V [_ _]NP")
    db.entries.append(e)
    return db


def test_hidden_by_default_in_all_data_and_the_utterances(make_win):
    win = make_win(_db_with_line())
    assert "f:Constituents" not in win._default_all_keys()
    assert "f:Constituents" in [c.key for c in win._all_columns()]      # offered in Configure columns
    win.open_utterances()
    assert "f:Constituents" not in win.utterances_window._default_keys()


def test_the_token_dialogue_has_it_under_more_with_a_warning(make_win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    win = make_win(_db_with_line())
    win.prefs.set_value("dialogs/token_more", False)
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    assert dlg.more_btn is not None and not dlg.more_btn.isChecked()
    assert dlg.cons_edit is dlg.edits["Constituents"] and not dlg.cons_edit.isVisibleTo(dlg)
    assert "1 filled" in dlg.more_btn.text()
    dlg.more_btn.setChecked(True)
    assert dlg.cons_edit.isVisibleTo(dlg)
    assert "not in Edit → Lists: MOD" in dlg.cons_note.text()
    dlg.edits["Phonemic"].setText("kʊ̀ʊn rɪ̀ɪŋ tʌ́")
    assert "5 words here, 3 in the line" in dlg.cons_note.text()
    dlg.cons_edit.setText("[_ _]NP V")
    assert dlg.cons_note.text() == ""
    assert win.prefs.get_bool("dialogs/token_more", False)          # remembered on this computer
    dlg.reject()


def test_edit_fields_chooses_what_goes_under_more(make_win):
    from lemmatrix.ui.dialogs import TOKEN_MORE_KEY, token_more_fields
    from lemmatrix.ui.fields_dialog import FieldsDialog
    win = make_win(_db_with_line())
    dlg = FieldsDialog(win, win.doc.db)
    assert dlg.token_more_names() == ["Constituents"]
    i = next(i for i, f in enumerate(dlg.lists["token"]) if f.name == "Comment")
    dlg.lists["token"][i]._more = True
    assert dlg.token_more_names() == ["Constituents", "Comment"]
    win.doc.ws_set(TOKEN_MORE_KEY, dlg.token_more_names())
    assert token_more_fields(win, win.doc.db) == {"Constituents", "Comment"}


def test_settings_typology_sets_the_features(make_win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    win = make_win(_db_with_line())
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert dlg.typ_order.currentData() == "unspecified" and dlg.typ_kind.currentData() == "tonal"
    dlg.typ_order.setCurrentIndex(dlg.typ_order.findData("SOV"))
    dlg.typ_morph.setCurrentIndex(dlg.typ_morph.findData("both"))
    dlg.apply()
    assert typology.value(win.doc.db, "order") == "SOV" and typology.value(win.doc.db, "morphology") == "both"
    assert '<feature id="order" value="SOV" wals="81A" />' in storage.to_string(win.doc.db)
    assert dlg.kind_requested == "tonal"                                # unchanged: no conversion


def test_edit_lists_has_the_labels_and_word_class_abbreviations(make_win):
    from lemmatrix.ui.lists_dialog import CONSTITUENTS, ListsDialog
    win = make_win(_db_with_line())
    dlg = ListsDialog(win, win.doc.db, win.doc.notebook, CONSTITUENTS)
    items = dlg.constituents.items()
    assert items[0].name == "Relations" and items[0].children[0].abbr == "S"
    dlg.constituents.tree.topLevelItem(0).child(0).setText(1, "SBJ")
    assert dlg.class_list.items()[0].abbr == "N"
    dlg.apply()
    assert win.doc.db.settings.constituent_labels[0].children[0].abbr == "SBJ"


def test_drawn_as_brackets_over_the_lined_up_words(app):
    from lemmatrix.textgrid import Line
    from lemmatrix.ui.lines_view import FieldSpec, LinesView
    v = LinesView()
    v.resize(900, 300)
    specs = [FieldSpec("Constituents", "Constituents", role="constituents"),
             FieldSpec("Phonemic", "Phonemic", ipa=True, aligned=True, role="phonemic"),
             FieldSpec("Morphemes", "Morphemes", aligned=True, role="morphemes")]
    v.set_fields(specs, "")
    ln = Line(0.0, 1.0, values={"Constituents": "[_ [ADJ]MOD]NP V [_ _]NP",
                                "Phonemic": "kʊ̀ʊn rɪ̀ɪŋ tʌ́ ŋɔ́ɔɲ ɲàmá", "Morphemes": "man big saw lion DEF"})
    plain = Line(1.0, 2.0, values={"Phonemic": "kʊ̀ʊn rɪ̀ɪŋ tʌ́ ŋɔ́ɔɲ ɲàmá", "Morphemes": "man big saw lion DEF"})
    v.set_lines([ln, plain])
    rows = {s.key: h for s, _, h in v._cells[0].rows}
    assert rows["Constituents"] > rows["Morphemes"] * 1.5               # two levels and the floating labels
    assert len(v._cells[0].cols) == 5                                   # Constituents adds no columns
    assert v.grab().width() > 0                                         # paints
    v.edit_mode = True
    v._relayout()
    rows = {s.key: h for s, _, h in v._cells[0].rows}
    assert rows["Constituents"] <= rows["Morphemes"] + 4                # editing: the notation, one line


def test_small_caps_for_the_labels_under_conventions():
    from lemmatrix.ui import conventions
    c = conventions.Conventions()
    c.on, c.small_caps = True, True
    assert conventions.small_caps_on("constituents", c) and conventions.small_caps_on("morphemes", c)
    c.on = False
    assert not conventions.small_caps_on("constituents", c)


def test_the_matrix_cell_is_taller_with_brackets(make_win):
    from lemmatrix import matrix as mx
    win = make_win(_db_with_line())
    view = win.lt_view
    view.cell_fields = ["Phonemic", "Morphemes", "Constituents"]
    view.aligned = {"Phonemic", "Morphemes"}
    d = view.delegate
    e = win.doc.db.entries[0]
    hits = [(e, e.tokens[0])]
    with_brackets = d._line_h("Constituents", hits)
    assert with_brackets > d._line_h("Morphemes", hits) * 1.5
    view.aligned = set()                                    # nothing lined up: shown as typed
    assert d._line_h("Constituents", hits) == d._line_h("Morphemes", hits)
    assert mx.cell_text(win.doc.db, e.tokens[0], "Constituents").startswith("[_")


# ---- written into Praat as a tier (Josh, 28 October) -------------------------------------------
def test_the_cns_tier_is_read_and_written_and_praat_reads_it(tmp_path):
    from lemmatrix import lines as lmod
    from lemmatrix import textgrid as tgmod
    from lemmatrix.model import Text
    db = defaults.new_database()
    db.path = str(tmp_path / "Lex.xml")
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True)
    grid = folder / "t.TextGrid"
    tgmod.write_example(grid, {"tx": [(0.5, 1.5, "kʊ̀ʊn tʌ́ ŋɔ́ɔɲ")],
                               "cns": [(0.5, 1.5, "[_]NP V [_]NP")]}, 2.0)
    t = Text(ref="T001", textgrid="t.TextGrid")
    db.texts.append(t)
    buf = lmod.Buffer(grid)
    ln = buf.lines(db, t)[0]
    assert ln.values["Constituents"] == "[_]NP V [_]NP"                # read through the cns rule
    buf.apply(lmod.plan_edit(buf, db, t, ln, "Constituents", "[_]A V [_]O"))
    buf.write(db)
    assert tgmod.read_lines(grid, db.mapping_for(t))[0].values["Constituents"] == "[_]A V [_]O"
    try:
        import parselmouth
    except ImportError:
        return
    out = parselmouth.praat.run(f'Read from file: "{grid}"\nn = Get number of tiers\nappendInfoLine: n\n'
                                'name$ = Get tier name: 2\nappendInfoLine: name$\n', capture_output=True)[1].split()
    assert out == ["2", "cns"]


def test_a_new_tier_is_made_for_a_line_typed_in_lemmatrix(tmp_path):
    from lemmatrix import lines as lmod
    from lemmatrix import textgrid as tgmod
    from lemmatrix.model import Text
    db = defaults.new_database()
    db.path = str(tmp_path / "Lex.xml")
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True)
    grid = folder / "t.TextGrid"
    tgmod.write_example(grid, {"tx": [(0.5, 1.5, "kʊ̀ʊn tʌ́")]}, 2.0)
    t = Text(ref="T001", textgrid="t.TextGrid")
    db.texts.append(t)
    buf = lmod.Buffer(grid)
    edits = lmod.plan_edit(buf, db, t, buf.lines(db, t)[0], "Constituents", "[_]NP V")
    assert edits[0].created and edits[0].tier == "cns"
