# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Reading and writing Lemmatrix database files (readable UTF-8 XML).

Saving is careful: the new file is written next to the old one first and only
then swapped in, and the previous version is copied into a "Backups" folder
beside the database (the 10 most recent are kept).
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from .matrix import CITATION, EXACT, MatrixConfig, Spec
from .model import (LEMMAS, TEXTS, UTTERANCES, ClipSource, Database, Entry, FieldDef, Group, ListItem,
                    Location, Metadata, Person, RefCategory, Settings, Support, Tag, TagStructure, Text,
                    Thanks, TierMapping, TierRule, Token, Utterance, is_utterance, new_id, nfc, write_atomically, xml_safe)

FORMAT_VERSION = "16"
WORDLIST_ATTRS = {"EACW": "eacw", "CAWL": "cawl", "SWADESH": "swadesh"}   # format 9 (idea 40)
# Until version 1.0 the current format is read and the formats before it upgraded, from format 5 on
# (Josh, 18 October 2026: no compatibility code for older formats; the upgrades are kept, 25 October,
# so an older backup still opens, until v1 fixes the format). When the format changes, an upgrade
# from the format before is written.
READABLE = ("5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", FORMAT_VERSION)   # 5: before texts; 6: before the workspace file;
# 7: before researchers had the Identifiable? checkbox and both checkboxes were always written; 8: before the
# comparative wordlists (format 9, 22 October: no base and no numbers yet, so nothing to change);
# 9: before the <typology> block (format 10, 23 October: an older file is tonal, as every database was);
# 10: before the EACW's version on <wordlist> (format 11, 23 October: items and region, none in an
# older file, so nothing to change); 11: before the acknowledgements and the EACW's version number
# (format 12, 24 October: none in an older file, so nothing to change); 12: before fields'
# abbreviations (format 13, 26 October: the token fields get pht, phm, mph, pch, trs, com); 13: before
# <characters> (format 14, 27 October: an older file is NFC, precomposed, as Lemmatrix always wrote);
# 14: before the EACW's Clarification left the lemma fields and the shipped glosses' editions were
# recorded (format 15, 27 October, IDEAS.md ideas 87 and 63: the Clarification field and its values
# are dropped, read from the shipped edition instead; an older file has no <glosses>); 15: before the
# Constituents tier (format 16, 28 October, IDEAS.md idea 91: the core token field Constituents
# with its tier rule cns, the <constituent-labels> list, abbreviations on list items, and the
# typology's morphology and order features, all added on opening, empty or unspecified)
BACKUPS_KEPT = 10


class FormatError(Exception):
    pass


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _text(el) -> str:
    return nfc((el.text or "").strip()) if el is not None else ""


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("yes", "true", "1", "on")


def _load_item(el) -> ListItem:
    return ListItem(nfc(el.get("name", "")), [_load_item(c) for c in el.findall("item")],
                    nfc(el.get("abbr", "")))


def _load_field(el) -> FieldDef:
    f = FieldDef(name=el.get("name", ""), label=el.get("label", ""), role=el.get("role", ""),
                 closed=_bool(el.get("closed")), abbr=nfc(el.get("abbr", "")))
    f.items = [_load_item(i) for i in el.findall("item")]
    if f.role == "word-class":
        f.closed = True
    return f


def _split(text: str | None) -> list[str]:
    return [nfc(x.strip()) for x in (text or "").split(",") if x.strip()]


def _load_group(el) -> Group:
    g = Group(name=nfc(el.get("name", "")), usual=_split(el.get("usual")),
              utterances_only=_bool(el.get("utterances-only")), description=nfc(el.get("description", "")))
    for child in el:
        if child.tag == "tag":
            g.tags.append(Tag(name=nfc(child.get("name", "")), code=nfc(child.get("code", "")),
                              default=_bool(child.get("default")),
                              description=nfc(child.get("description", ""))))
        elif child.tag == "group":
            g.groups.append(_load_group(child))
    return g


def _load_tags(el) -> TagStructure:
    return TagStructure([_load_group(g) for g in el.findall("group")] if el is not None else [])


KNOWN_SETTINGS = {"entry-fields", "token-fields", "text-fields", "tier-mapping", "glosses", "tag-structure",
                  "references", "sounds", "pitch", "playback", "display", "spelling", "characters",
                  "constituent-labels"}

# Format 14 (ideas 18 and 21, Josh, 27 October): how the transcriptions' characters are stored, written
# so that a computer or a researcher reading the file knows (Josh): NFD, no precomposed characters in
# Phonetic and Phonemic, or NFC, precomposed where Unicode has the character.
CHARACTERS_NOTE = {
    "NFD": "Phonetic and Phonemic are decomposed (Unicode NFD): they hold no precomposed characters; "
           "é is e + U+0301, so every tone mark is a character of its own.",
    "NFC": "Phonetic and Phonemic are composed (Unicode NFC): é is one character (U+00E9) where "
           "Unicode has one; other marks are characters of their own (ɛ́ is ɛ + U+0301).",
}


def _load_mapping(el) -> TierMapping:
    return TierMapping(nfc(el.get("main", "tx")),
                       [TierRule(nfc(t.get("name", "")), nfc(t.get("field", "")), t.get("lang", ""))
                        for t in el.findall("tier")])


def _save_mapping(parent, tag: str, m: TierMapping):
    el = ET.SubElement(parent, tag, main=m.main)
    for r in m.rules:
        a = {"name": r.tier, "field": r.field}
        if r.lang:
            a["lang"] = r.lang
        ET.SubElement(el, "tier", a)

def _load_specs(el, tag: str) -> list[Spec]:
    out = []
    for c in el.findall(tag):
        match = c.get("match", EXACT)
        tags = frozenset(nfc(t.strip()) for t in (c.get("tags") or "").split(",") if t.strip())
        out.append(Spec(frozenset() if match == CITATION else tags, match))
    return out


def save_matrices(parent, matrices, tags):
    """Saved matrices as <matrix> elements (in the workspace file since format 7)."""
    for m in matrices:
        mel = ET.SubElement(parent, "matrix", {"name": m.name, "kind": m.kind, "cell": " ".join(m.cell)})
        for axis, specs in (("y", m.y), ("x", m.x)):
            for sp in specs:
                a = {"match": sp.match}
                if sp.tags:
                    a["tags"] = ", ".join(tags.sort(list(sp.tags)))
                ET.SubElement(mel, axis, a)


def _load_matrices(el) -> list[MatrixConfig]:
    out = []
    if el is None:
        return out
    for m in el.findall("matrix"):
        cfg = MatrixConfig(name=nfc(m.get("name", "")), kind=m.get("kind", "lemma-tag"))
        cfg.y = _load_specs(m, "y")
        cfg.x = _load_specs(m, "x")
        if m.get("cell") is not None:
            cfg.cell = m.get("cell").split()
        out.append(cfg)
    return out


def _load_settings(el) -> Settings:
    s = Settings()
    if el is None:
        return s
    if (x := el.find("entry-fields")) is not None:
        s.entry_fields = [_load_field(f) for f in x.findall("field")]
    if (x := el.find("token-fields")) is not None:
        s.token_fields = [_load_field(f) for f in x.findall("field")]
    if (x := el.find("text-fields")) is not None:
        s.text_fields = [_load_field(f) for f in x.findall("field")]
    if (x := el.find("tier-mapping")) is not None:
        s.tier_mapping = _load_mapping(x)
    if (x := el.find("glosses")) is not None:
        s.gloss_languages = (x.get("languages") or "en").split()
        s.primary_gloss = x.get("primary") or s.gloss_languages[0]
    s.tags = _load_tags(el.find("tag-structure"))
    if (x := el.find("references")) is not None:
        s.ref_scheme = x.get("scheme", "categories")
        s.ref_digits = int(x.get("digits", "3") or 3)
        s.ref_categories = [RefCategory(c.get("letter", ""), _text(c), c.get("numbering", "auto"),
                                        c.get("for") if c.get("for") in (UTTERANCES, TEXTS) else LEMMAS)
                            for c in x.findall("category")]
    if (x := el.find("sounds")) is not None:
        s.filename_pattern = x.get("pattern", s.filename_pattern)
        s.utterance_pattern = x.get("utterance-pattern", s.utterance_pattern)
        s.text_pattern = x.get("text-pattern", s.text_pattern)
        s.clip_padding = int(x.get("clip-padding", s.clip_padding) or 0)
        s.tag_separator = x.get("tag-separator", s.tag_separator)
        s.auto_update_names = _bool(x.get("auto-update-names"), True)
    if (x := el.find("pitch")) is not None:
        lo, _, hi = (x.get("display-range") or "1-5").partition("-")
        s.pitch_low, s.pitch_high = int(lo or 1), int(hi or 5)
        s.pitch_style = x.get("style", "contours")
    if (x := el.find("playback")) is not None:
        s.play_cell_on_click = _bool(x.get("play-cell-on-click"))
    s.matrices = _load_matrices(el.find("display"))
    if (x := el.find("spelling")) is not None:
        s.spelling_words = [w for w in (nfc(_text(w)).strip() for w in x.findall("word")) if w]
    if (x := el.find("constituent-labels")) is not None:        # format 16 (idea 91)
        s.constituent_labels = [_load_item(i) for i in x.findall("item")]
    if (x := el.find("characters")) is not None:
        s.decomposed = (x.get("transcriptions") or "").upper() == "NFD"
    s.extra = [child for child in el if child.tag not in KNOWN_SETTINGS]
    return s


def _load_values(el, target, multilingual_names: set[str], skip=("token",)):
    for child in el:
        if child.tag in skip:
            continue
        lang = child.get("lang")
        if lang is not None or child.tag in multilingual_names:
            target.multi.setdefault(child.tag, {})[lang or ""] = _text(child)
        else:
            target.values[child.tag] = _text(child)
            if child.get("changed"):
                target.changed[child.tag] = child.get("changed")


def _load_person(el, researcher: bool = False) -> Person:
    """<participant code="SP1" name="..." identifiable="no" audio-sharing="no">description</participant>;
    researchers have identifiable= too, and can have an email="...". Since format 8 (22 October,
    idea 44) the checkboxes are always written, yes or no; a checkbox that isn't there (an older file) is
    the default: a researcher is identifiable, a participant isn't, and nobody has agreed to
    audio sharing."""
    ident = el.get("identifiable")
    return Person(nfc(el.get("code", "")), nfc(el.get("name", "")), _text(el), nfc(el.get("consent", "")),
                  email=(el.get("email") or "").strip(),
                  identifiable=(ident == "yes") if ident is not None else researcher,
                  audio_sharing=el.get("audio-sharing") == "yes")


def _load_location(el) -> Location:
    return Location(nfc(el.get("name", "")), nfc(el.get("code", "")), _text(el.find("description")),
                    [_load_location(c) for c in el.findall("location")])


def _load_metadata(m) -> Metadata:
    md = Metadata()
    if m is None:
        return md
    if (x := m.find("language")) is not None:
        md.language_code, md.language_name = nfc(x.get("code", "")), _text(x)
    if (x := m.find("variety")) is not None:
        md.variety_code, md.variety_name = nfc(x.get("code", "")), _text(x)
    md.typology = {"tone": "tonal"}             # format 10; an older database is tonal (Josh, 23 October)
    if (t := m.find("typology")) is not None:
        for f in t.findall("feature"):
            if f.get("id"):
                md.typology[f.get("id")] = (f.get("value") or "").strip()
    md.name = _text(m.find("name"))
    md.author = _text(m.find("author"))
    md.researchers = [_load_person(r, researcher=True) for r in m.findall("researcher")]
    md.participants = [_load_person(p) for p in m.findall("participant")]
    md.locations = [_load_location(x) for x in m.findall("location")]
    md.description = _text(m.find("description"))
    if (x := m.find("wordlist")) is not None:     # format 9: the list the references are numbers of
        md.wordlist_base = (x.get("base") or "").upper()
        md.wordlist_items = (x.get("items") or "").strip()      # format 11: base or expanded
        md.wordlist_region = (x.get("region") or "").strip()    # format 11: global, africa, N W E S C
        md.wordlist_version = (x.get("version") or "").strip()  # format 12: the EACW's version
        md.wordlist_glosses = {g.get("lang", ""): (g.get("edition") or "").strip()   # format 15 (idea 63)
                               for g in x.findall("glosses") if g.get("lang")}
    if (a := m.find("acknowledgements")) is not None:            # format 12 (idea 59)
        md.support = [Support(nfc(x.get("organisation", "")), nfc(x.get("grant", "")), _text(x))
                      for x in a.findall("support")]
        md.thanks = [Thanks(nfc(x.get("who", "")), _text(x)) for x in a.findall("thanks")]
    return md


def _unique_ids(db: Database):
    """Every entry and token gets an id, and no two share one (copies made outside Lemmatrix)."""
    seen = set()
    for e in db.items():
        for obj in [e, *e.tokens]:
            if not obj.id or obj.id in seen:
                obj.id = new_id()
            seen.add(obj.id)



def _origin_to_stem_type(db: Database):
    """Origin (22 October) became Stem type the next morning (Josh, 23 October): its role, its
    name and label if unchanged, the lemmas' values under the new name, and the first default list
    (root; complex › …; loan) replaced by the new one (simple, complex, loan). Provisional, for a
    database saved in between."""
    for f in db.settings.entry_fields:
        if f.role != "origin":
            continue
        f.role = "stem-type"
        if f.name == "Origin":
            f.name, f.label = "StemType", ("Stem type" if f.label in ("", "Origin") else f.label)
            for e in db.entries:
                if "Origin" in e.values:
                    e.values["StemType"] = e.values.pop("Origin")
        old = [(i.name, [c.name for c in i.children]) for i in f.items]
        if old == [("root", []), ("complex", ["compound", "derived", "reduplicated"]), ("loan", [])]:
            from .defaults import stem_types
            f.items = stem_types()
            for e in db.entries:
                if e.values.get(f.name) == "root":
                    e.values[f.name] = "simple"
                elif e.values.get(f.name) in ("compound", "derived", "reduplicated"):
                    e.values[f.name] = "complex"
        db.upgraded = True

def _drop_clarification(db: Database):
    """Format 15 (IDEAS.md idea 87, Josh, 27 October): the EACW's Clarification was a lemma field,
    filled from the list; it is now read from the shipped edition and shown as an (i) beside the
    gloss, so the field and its values go (Josh: overwritten, a clarification of one's own too)."""
    s = db.settings
    gone = [f for f in s.entry_fields if f.role == "clarification"]
    if not gone:
        return
    names = {f.name for f in gone}
    s.entry_fields = [f for f in s.entry_fields if f.role != "clarification"]
    from . import wordlists as wl
    own = []
    for e in db.entries:
        for n in names:
            v = e.values.pop(n, None) or next(iter((e.multi.pop(n, None) or {}).values()), "")
            item = wl.get(wl.EACW).by_number.get(wl.canon(wl.EACW, e.ref) or "") if v else None
            if v and (item is None or item.clarification != v):
                own.append(f"{e.ref}: {v}")
    db.dropped_fields = [f.title for f in gone]
    if own:                              # said in the upgrade's message, so nothing goes unseen
        db.load_notes = list(db.load_notes) + [
            "The Clarification field is gone: the EACW's clarifications now come from the list itself, as an "
            "ⓘ beside each gloss. These clarifications differed from the list's present wording (an earlier edition's, or one of your own) and are no longer kept:\n"
            + "\n".join(own[:30]) + (f"\n… and {len(own) - 30} more" if len(own) > 30 else "")]
    db.upgraded = True


def load(path: str | os.PathLike) -> Database:
    path = str(path)
    repaired = False
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        root = _parse_repaired(path, exc)     # invisible characters a paste brought in, say
        repaired = True
    if root.tag != "database":
        raise FormatError("This isn't a Lemmatrix database (the top element should be <database>).")
    version = root.get("format", FORMAT_VERSION)
    if version not in READABLE:
        raise FormatError(f"This database uses format {root.get('format')}; this version of Lemmatrix "
                          f"reads formats {READABLE[0]} to {FORMAT_VERSION}.")

    md = _load_metadata(root.find("metadata"))

    settings = _load_settings(root.find("settings"))
    entry_multi = {f.name for f in settings.entry_fields if f.multilingual}
    token_multi = {f.name for f in settings.token_fields if f.multilingual}

    db = Database(metadata=md, settings=settings, path=path)

    def load_token(tel) -> Token:
        tags = [nfc(t.strip()) for t in (tel.get("tags") or "").split(",") if t.strip()]
        t = Token(tags=tags, speaker=nfc(tel.get("speaker", "")),
                  collected=tel.get("collected", ""), file=nfc(tel.get("file", "")),
                  rerecord=tel.get("rerecord") == "yes", id=tel.get("id", ""))
        _load_values(tel, t, token_multi, skip=())
        return t

    for el in root.findall("entry"):
        e = Entry(ref=nfc(el.get("ref", "")), file_gloss=nfc(el.get("file-gloss", "")),
                  id=el.get("id", ""), from_lemmas=(el.get("from-lemmas") or "").split(),
                  from_languages=[nfc(x.strip()) for x in (el.get("from-languages") or "").split(";")
                                  if x.strip()])
        for lid, attr in WORDLIST_ATTRS.items():     # format 9: the other wordlists' numbers
            if el.get(attr):
                e.lists[lid] = el.get(attr).split()
        _load_values(el, e, entry_multi)
        for tel in el.findall("token"):
            e.tokens.append(load_token(tel))
        db.entries.append(e)
    if (ul := root.find("utterances")) is not None:
        for el in ul.findall("utterance"):
            u = Utterance(ref=nfc(el.get("ref", "")), file_gloss=nfc(el.get("file-label", "")),
                          id=el.get("id", ""), lemmas=(el.get("lemmas") or "").split())
            tels = el.findall("token")
            u.tokens = [load_token(tels[0])] if tels else [Token()]
            if (src := el.find("source")) is not None:
                u.source = ClipSource(src.get("text", ""), float(src.get("start", 0) or 0),
                                      float(src.get("end", 0) or 0),
                                      {nfc(c.get("tier", "")): _text(c) for c in src.findall("copied")},
                                      src.get("modified", ""))
            db.utterances.append(u)
    if (tl := root.find("texts")) is not None:
        for el in tl.findall("text"):
            t = Text(ref=nfc(el.get("ref", "")), file_label=nfc(el.get("file-label", "")),
                     date=el.get("date", ""), participants=(el.get("participants") or "").split(),
                     researchers=(el.get("researchers") or "").split(),
                     locations=_split(el.get("locations")), file=nfc(el.get("file", "")),
                     textgrid=nfc(el.get("textgrid", "")), id=el.get("id", "") or new_id())
            for child in el:
                if child.tag == "tiers":
                    t.tiers = _load_mapping(child)
                else:
                    t.values[child.tag] = _text(child)
                    if child.get("changed"):
                        t.changed[child.tag] = child.get("changed")
            db.texts.append(t)
    _unique_ids(db)
    _origin_to_stem_type(db)
    from .defaults import ensure_core_fields
    restored = ensure_core_fields(db.settings, skip_roles=() if md.typology.get("tone") != "unspecified"
                                  else ("pitch",))       # an unspecified database has no Pitch (idea 9)
    from .model import NEW_ROLES
    added = [f.title for f in db.settings.entry_fields if f.role in NEW_ROLES and f.title in restored]
    restored = [t for t in restored if t not in added]
    if added:                            # quietly (a status-bar note), so saving writes it
        db.added_fields = added
        db.upgraded = True
    if restored:
        db.load_notes = list(db.load_notes) + [
            f"Restored the field{'s' if len(restored) > 1 else ''} {', '.join(restored)}: other features "
            "need it, so it can be renamed or moved in Edit → Fields but not deleted. It's empty."]
    if version == "5":
        _upgrade_5_to_6(db)
    if version in ("5", "6"):            # format 7 (21 October): the working state moves to the workspace
        db.workspace_from_file = True
    if version != FORMAT_VERSION:        # format 13 (26 October): the token fields' abbreviations
        from .fieldkeys import give_defaults
        give_defaults(db.settings.token_fields)
    if version != FORMAT_VERSION:        # format 8 (22 October): researchers selected Identifiable?, read
                                         # above; format 9: wordlist numbers, none in an older file;
        db.upgraded = True               # above; quietly, so saving writes the new format
    if version in READABLE[:READABLE.index("15")]:   # format 15 (idea 87): the Clarification leaves the fields
        _drop_clarification(db)
    if version in READABLE[:READABLE.index("16")]:   # format 16 (idea 91): the Constituents tier
        _upgrade_to_16(db)
    if db.settings.decomposed:           # format 14: anything precomposed (a file edited by hand) decomposed
        from .decompose import fix_database
        fix_database(db, "NFD")
    if repaired:
        db.load_notes = list(db.load_notes) + [REPAIRED_NOTE]
    return db


def _upgrade_to_16(db: Database):
    """Format 16 (IDEAS.md idea 91, Josh, 28 October): the Constituents field itself comes in as a
    core field (ensure_core_fields, above); here its tier rule (cns, unless a rule already uses that
    tier name), and the default Constituent labels. The Word Class list is left exactly as it is:
    its labels are never written over (Josh: "that would annoy a researcher")."""
    from . import constituents as cons
    s = db.settings
    f = s.token_field(cons.ROLE)
    if f is not None and s.tier_mapping.rule(cons.TIER) is None and s.tier_mapping.rules:
        from .model import TierRule
        s.tier_mapping.rules.append(TierRule(cons.TIER, f.name))
    if not s.constituent_labels:
        s.constituent_labels = cons.default_labels()
    db.upgraded = True


def _upgrade_5_to_6(db: Database):
    """Provisional, for Josh's database (18 October 2026): texts and songs. Taken out again once
    his database has been saved in format 6."""
    from .defaults import text_categories, text_fields, tier_mapping
    s = db.settings
    taken = {c.letter for c in s.ref_categories}
    s.ref_categories += [c for c in text_categories() if c.letter not in taken]
    if not s.text_fields:
        s.text_fields = text_fields()
    if not s.tier_mapping.rules:
        s.tier_mapping = tier_mapping()
    lowered = []
    for _, g in s.tags.leaf_groups():                 # Example codes lowercase (x1, x2): Josh's convention
        if g.name.lower() == "examples":
            for t in g.tags:
                if t.code and t.code[:1] == "X" and t.code[1:].isdigit():
                    lowered.append(t.code)
                    t.code = "x" + t.code[1:]
    note = ("This database can now hold texts and songs (T and S references, View → Texts and "
            "utterances → Texts), each with its recording and Praat TextGrid.")
    if lowered:
        note += f" The Example tags' codes are now lowercase ({', '.join(c.lower() for c in lowered)})."
    db.load_notes = list(db.load_notes) + [note]


REPAIRED_NOTE = ("This file had invisible characters in it (from a paste, perhaps) that made it unreadable. "
                 "They have been taken out; saving writes the repaired file (a backup of the old one is kept).")


def _parse_repaired(path, exc):
    """The file without the characters XML can't hold, parsed; FormatError if it still won't read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return ET.fromstring(xml_safe(fh.read()))
    except (ET.ParseError, OSError):
        raise FormatError(f"This file isn't readable XML: {exc}") from exc


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

def _yes(b: bool) -> str:
    return "yes" if b else "no"


def _save_item(parent, item: ListItem):
    el = ET.SubElement(parent, "item", name=item.name)
    if item.abbr:
        el.set("abbr", item.abbr)
    for c in item.children:
        _save_item(el, c)


def _save_field(parent, f: FieldDef):
    el = ET.SubElement(parent, "field", name=f.name)
    if f.label:
        el.set("label", f.label)
    if f.role:
        el.set("role", f.role)
    if f.abbr:
        el.set("abbr", f.abbr)
    if f.closed:
        el.set("closed", "yes")
        for item in f.items:
            _save_item(el, item)


def _save_group(parent, g: Group):
    el = ET.SubElement(parent, "group", name=g.name)
    if g.usual:
        el.set("usual", ", ".join(g.usual))
    if g.utterances_only:
        el.set("utterances-only", "yes")
    if g.description:
        el.set("description", g.description)
    for t in g.tags:
        tel = ET.SubElement(el, "tag", name=t.name)
        if t.code and not t.default:
            tel.set("code", t.code)
        if t.default:
            tel.set("default", "yes")
        if t.description:
            tel.set("description", t.description)
    for sub in g.groups:
        _save_group(el, sub)


def _save_values(el, obj, field_order: list[FieldDef], languages: list[str]):
    names = [f.name for f in field_order]
    extra = sorted((set(obj.values) | set(obj.multi)) - set(names))
    for name in names + extra:
        if name in obj.multi:
            d = obj.multi[name]
            langs = [l for l in languages if l in d] + sorted(l for l in d if l not in languages)
            for lang in langs:
                if d[lang]:
                    child = ET.SubElement(el, name)
                    if lang:
                        child.set("lang", lang)
                    child.text = d[lang]
        elif obj.values.get(name):
            child = ET.SubElement(el, name)
            child.text = obj.values[name]
            if obj.changed.get(name):
                child.set("changed", obj.changed[name])


def to_element(db: Database) -> ET.Element:
    from .decompose import fix_database  # the promise kept whatever wrote the values (format 14):
    fix_database(db)                     # NFD or NFC, as <characters> says
    root = ET.Element("database", format=FORMAT_VERSION)
    md = db.metadata
    m = ET.SubElement(root, "metadata")
    if md.language_code or md.language_name:
        ET.SubElement(m, "language", code=md.language_code).text = md.language_name or None
    if md.variety_code or md.variety_name:
        ET.SubElement(m, "variety", code=md.variety_code).text = md.variety_name or None
    # format 10 (ideas 9 and 56): typological features, right after the language, always written
    ty = ET.SubElement(m, "typology")
    from . import typology as typ                 # format 16 (idea 91): morphology and order too, with WALS
    for fid, value in typ.normalised(md.typology).items():
        a = {"id": fid, "value": value}
        if (w := typ.wals(fid, value)):
            a["wals"] = w
        ET.SubElement(ty, "feature", a)
    if md.name:
        ET.SubElement(m, "name").text = md.name
    if md.author:
        ET.SubElement(m, "author").text = md.author
    for tag, people in (("researcher", md.researchers), ("participant", md.participants)):
        for p in people:
            a = {"code": p.code, "name": p.name}
            if p.consent:
                a["consent"] = p.consent
            if p.email:
                a["email"] = p.email
            a["identifiable"] = "yes" if p.identifiable else "no"     # always written (format 8)
            if tag == "participant":
                a["audio-sharing"] = "yes" if p.audio_sharing else "no"
            ET.SubElement(m, tag, a).text = p.description or None
    def location(parent, loc: Location):
        a = {"name": loc.name}
        if loc.code:
            a["code"] = loc.code
        el = ET.SubElement(parent, "location", a)
        if loc.description:
            ET.SubElement(el, "description").text = loc.description
        for c in loc.children:
            location(el, c)
    for loc in md.locations:
        location(m, loc)
    if md.description:
        ET.SubElement(m, "description").text = md.description
    if md.wordlist_base:                          # format 9 (idea 40): EACW, CAWL or SWADESH
        a = {"base": md.wordlist_base}
        if md.wordlist_items:                     # format 11: the EACW's version (Josh, 23 October)
            a["items"] = md.wordlist_items
        if md.wordlist_region:
            a["region"] = md.wordlist_region
        if md.wordlist_version:                   # format 12: the EACW's version it is up to date with
            a["version"] = md.wordlist_version
        w = ET.SubElement(m, "wordlist", a)
        for lang, ed in md.wordlist_glosses.items():   # format 15 (idea 63): the shipped glosses' edition
            if lang:
                ET.SubElement(w, "glosses", {"lang": lang, "edition": ed})
    if md.support or md.thanks:                   # format 12 (idea 59): <support organisation=".." grant="..">
        ack = ET.SubElement(m, "acknowledgements")   # what it funded</support>, <thanks who="..">what for</thanks>
        for x in md.support:
            a = {"organisation": x.organisation}
            if x.grant:
                a["grant"] = x.grant
            ET.SubElement(ack, "support", a).text = x.funded or None
        for x in md.thanks:
            ET.SubElement(ack, "thanks", {"who": x.who}).text = x.what_for or None

    s = db.settings
    st = ET.SubElement(root, "settings")
    x = ET.SubElement(st, "entry-fields")
    for f in s.entry_fields:
        _save_field(x, f)
    x = ET.SubElement(st, "token-fields")
    for f in s.token_fields:
        _save_field(x, f)
    x = ET.SubElement(st, "text-fields")
    for f in s.text_fields:
        _save_field(x, f)
    from .decompose import ROLES
    form = "NFD" if s.decomposed else "NFC"
    names = list(dict.fromkeys(f.name for f in (*s.entry_fields, *s.token_fields, *s.text_fields)
                               if f.role in ROLES))
    ET.SubElement(st, "characters", {"transcriptions": form, "fields": ", ".join(names)}).text = \
        CHARACTERS_NOTE[form]
    _save_mapping(st, "tier-mapping", s.tier_mapping)
    x = ET.SubElement(st, "constituent-labels")   # format 16 (idea 91): the Constituents tier's labels
    for item in s.constituent_labels:
        _save_item(x, item)
    ET.SubElement(st, "glosses", languages=" ".join(s.gloss_languages), primary=s.primary_gloss)
    x = ET.SubElement(st, "tag-structure")
    for g in s.tags.groups:
        _save_group(x, g)
    x = ET.SubElement(st, "references", scheme=s.ref_scheme, digits=str(s.ref_digits))
    for c in s.ref_categories:
        cel = ET.SubElement(x, "category", letter=c.letter)
        if c.numbering != "auto":
            cel.set("numbering", c.numbering)
        if c.kind in (UTTERANCES, TEXTS):
            cel.set("for", c.kind)
        cel.text = c.name
    ET.SubElement(st, "sounds", {"pattern": s.filename_pattern, "utterance-pattern": s.utterance_pattern,
                                 "text-pattern": s.text_pattern, "clip-padding": str(s.clip_padding),
                                 "tag-separator": s.tag_separator,
                                 "auto-update-names": _yes(s.auto_update_names)})
    # how to read the pitch digits; the display style, saved matrices and the spelling list are
    # working state, kept in the workspace file since format 7 (workspace.py)
    if db.metadata.typology.get("tone") != "unspecified":   # an unspecified database has no pitch (idea 9)
        ET.SubElement(st, "pitch", {"display-range": f"{s.pitch_low}-{s.pitch_high}"})
    for extra in s.extra:
        st.append(extra)

    langs = s.gloss_languages

    def save_token(parent, t: Token):
        tattrs = {}
        if t.tags:
            tattrs["tags"] = ", ".join(s.tags.sort(t.tags))
        for key, val in (("speaker", t.speaker), ("collected", t.collected), ("file", t.file)):
            if val:
                tattrs[key] = val
        tattrs["id"] = t.id
        tel = ET.SubElement(parent, "token", tattrs)
        _save_values(tel, t, s.token_fields, langs)

    for e in db.entries:
        attrs = {"ref": e.ref}
        if e.file_gloss:
            attrs["file-gloss"] = e.file_gloss
        attrs["id"] = e.id
        if e.from_lemmas:                         # From (22 October): lemmas by id, languages by code
            attrs["from-lemmas"] = " ".join(e.from_lemmas)
        if e.from_languages:
            attrs["from-languages"] = "; ".join(e.from_languages)
        for lid, attr in WORDLIST_ATTRS.items():   # format 9 (idea 40): hidden, readable here
            if e.lists.get(lid):
                attrs[attr] = " ".join(e.lists[lid])
        el = ET.SubElement(root, "entry", attrs)
        _save_values(el, e, s.entry_fields, langs)
        for t in e.tokens:
            save_token(el, t)
    if db.utterances:                         # one-off sentences and phrases, after the entries
        ul = ET.SubElement(root, "utterances")
        for u in db.utterances:
            attrs = {"ref": u.ref}
            if u.file_gloss:
                attrs["file-label"] = u.file_gloss
            if u.lemmas:
                attrs["lemmas"] = " ".join(u.lemmas)
            attrs["id"] = u.id
            el = ET.SubElement(ul, "utterance", attrs)
            save_token(el, u.token)
            if u.source is not None:              # clipped from a text's line
                sp = u.source
                src = ET.SubElement(el, "source", {"text": sp.text, "start": f"{sp.start:.4f}",
                                                    "end": f"{sp.end:.4f}"})
                if sp.modified:
                    src.set("modified", sp.modified)
                for tier, text in sp.copied.items():
                    ET.SubElement(src, "copied", tier=tier).text = text or None
    if db.texts:                              # texts and songs, last
        tl = ET.SubElement(root, "texts")
        for t in db.texts:
            attrs = {"ref": t.ref}
            for key, val in (("file-label", t.file_label), ("date", t.date),
                             ("participants", " ".join(t.participants)),
                             ("researchers", " ".join(t.researchers)),
                             ("locations", ", ".join(t.locations)),
                             ("file", t.file), ("textgrid", t.textgrid)):
                if val:
                    attrs[key] = val
            attrs["id"] = t.id
            el = ET.SubElement(tl, "text", attrs)
            names = [f.name for f in s.text_fields]
            for name in names + sorted(set(t.values) - set(names)):
                if t.values.get(name):
                    c = ET.SubElement(el, name)
                    c.text = t.values[name]
                    if t.changed.get(name):
                        c.set("changed", t.changed[name])
            if t.tiers is not None:
                _save_mapping(el, "tiers", t.tiers)
    return root


def to_string(db: Database) -> str:
    root = to_element(db)
    ET.indent(root, space="  ")
    text = '<?xml version="1.0" encoding="utf-8"?>\n' + _tostring(root) + "\n"
    return xml_safe(text)                 # a pasted control character would make the file unreadable


def _tostring(root) -> str:
    """ET.tostring(root, encoding="unicode"), byte for byte, about twice as fast (25 October: at
    58,000 tokens the general writer, which also looks for namespaces Lemmatrix never uses, took
    most of every save and autosave). It uses ElementTree's own escaping; a tree with anything
    unusual in it (a comment, a namespace, a non-text tag) goes to ElementTree itself."""
    esc_text, esc_attr = ET._escape_cdata, ET._escape_attrib
    out: list[str] = []
    write = out.append

    def ser(elem):
        tag = elem.tag
        if not isinstance(tag, str) or tag.startswith("{"):
            raise _Unusual
        write("<" + tag)
        for k, v in elem.items():
            if not isinstance(k, str) or not isinstance(v, str) or k.startswith("{"):
                raise _Unusual
            write(f' {k}="{esc_attr(v)}"')
        text = elem.text
        if text or len(elem):
            write(">")
            if text:
                write(esc_text(text))
            for child in elem:
                ser(child)
            write("</" + tag + ">")
        else:
            write(" />")
        if elem.tail:
            write(esc_text(elem.tail))
    try:
        ser(root)
    except _Unusual:
        return ET.tostring(root, encoding="unicode")
    return "".join(out)


class _Unusual(Exception):
    pass


def backup_folder(path: str | os.PathLike) -> Path:
    """Where the automatic backups of a database go: always "Backups" in its main folder."""
    from . import layout
    return layout.backups_folder(path)


def make_backup(path: str | os.PathLike, keep: int = BACKUPS_KEPT) -> Path | None:
    """Copy the current file into the Backups folder and prune old copies."""
    p = Path(path)
    if not p.exists():
        return None
    folder = backup_folder(p)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = folder / f"{p.stem}_{stamp}{p.suffix}"
    n = 1
    while target.exists():
        n += 1
        target = folder / f"{p.stem}_{stamp}_{n}{p.suffix}"
    shutil.copy2(p, target)
    from .layout import backup_name_pattern
    pattern = backup_name_pattern(p.stem, (p.suffix,))
    mine = [f for f in folder.glob(f"{p.stem}_*{p.suffix}") if pattern.match(f.name)]   # not X_old's
    keepers = backups_to_keep(mine, keep)
    for f in mine:
        if f not in keepers:
            try:
                f.unlink()
            except OSError:
                pass
    return target


def backups_to_keep(files, recent: int = BACKUPS_KEPT, today: _dt.date | None = None) -> set:
    """Which backups to keep: the most recent ones, and older ones spread out in time.

    By the date each version was saved: the `recent` newest; the newest of each of the last
    seven days (so yesterday and the day before, and one that will be a week old); the newest
    of each of the four weeks before that (so one that will be a month old); and the newest
    one at least a month old.
    """
    today = today or _dt.date.today()
    dated = []
    for f in files:
        try:
            dated.append((f.stat().st_mtime, f))
        except OSError:
            pass
    dated.sort(key=lambda x: x[0], reverse=True)              # newest first
    keep = {f for _, f in dated[:recent]}
    seen_day, seen_week, month = set(), set(), False
    for mtime, f in dated:
        age = (today - _dt.date.fromtimestamp(mtime)).days
        if 1 <= age <= 7 and age not in seen_day:
            seen_day.add(age)
            keep.add(f)
        elif 7 < age < 35 and age // 7 not in seen_week:
            seen_week.add(age // 7)
            keep.add(f)
        if age >= 30 and not month:
            month = True
            keep.add(f)
    return keep


def save(db: Database, path: str | os.PathLike | None = None, backup: bool = True) -> None:
    """Write the database (atomically). The previous version goes to the Backups folder
    next to it."""
    path = str(path or db.path)
    if not path:
        raise ValueError("No file name given")
    text = to_string(db)
    tmp = write_atomically(path, text)
    if backup:
        make_backup(path)
    os.replace(tmp, path)
    db.path = path


# Windows marks files that OneDrive (or another cloud service) keeps online only:
_RECALL_ON_DATA_ACCESS = 0x00400000
_RECALL_ON_OPEN = 0x00040000
_OFFLINE = 0x00001000
_MAC_DATALESS = 0x40000000          # macOS SF_DATALESS (iCloud / OneDrive "online only")


def is_cloud_only(entry) -> bool:
    """True if a file (an os.DirEntry or a path) is online-only: reading it needs a download."""
    try:
        st = entry.stat() if hasattr(entry, "stat") and not isinstance(entry, (str, Path)) \
            else os.stat(entry)
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & (_RECALL_ON_DATA_ACCESS | _RECALL_ON_OPEN | _OFFLINE):
        return True
    return bool(getattr(st, "st_flags", 0) & _MAC_DATALESS)


def scan_sound_folder(folder: Path) -> tuple[set[str], set[str]]:
    """(names of the files in the folder, names of those that are online-only)."""
    names, cloud = set(), set()
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                names.add(entry.name)
                if is_cloud_only(entry):
                    cloud.add(entry.name)
    except OSError:
        pass
    return names, cloud


def same_file(a: Path, b: Path) -> bool:
    """True if two paths are one file (e.g. names differing only in case on Windows)."""
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def in_folder(path: Path, folder: Path) -> bool:
    """True if the file is directly in the folder (it can be renamed there, not copied in)."""
    try:
        return folder.exists() and os.path.samefile(Path(path).parent, folder)
    except OSError:
        return False




def held_folder(db: Database) -> Path:
    """Where a deleted token's recording waits (Soundfiles/_Deleted recordings), so undo can bring
    it back. It goes to the Recycle Bin when the database is closed."""
    from . import layout
    return layout.held_folder(db.path)


def held_folders(db: Database) -> list[Path]:
    return [held_folder(db)]


def sound_folder(db: Database) -> Path:
    """The lemma tokens' recordings: always Soundfiles/Tokens next to the database."""
    from . import layout
    return layout.tokens_folder(db.path)


def text_folder(db: Database) -> Path:
    """The texts' and songs' recordings and TextGrids: Soundfiles/Texts."""
    from . import layout
    return layout.texts_folder(db.path)


def utterance_folder(db: Database) -> Path:
    """The utterances' recordings: Soundfiles/Utterances."""
    from . import layout
    return layout.utterances_folder(db.path)


def folder_for(db: Database, item) -> Path:
    """Where the recordings of an entry's tokens, or of an utterance, are."""
    return utterance_folder(db) if is_utterance(item) else sound_folder(db)
