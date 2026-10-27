# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Building soundfile names from the customisable pattern.

The default pattern is

    {language}-{variety}-{speaker}_{reference}_{gloss}_{tags}

Each separator written before a placeholder belongs to that placeholder, so
when a part is empty its separator goes too:

    LXX-VXX-SP1_D009_goat_PL-GEN-xH.wav
    LXX_D009_goat.wav                      (no variety, no speaker, no tags)
    LXX-VXX_D010_big_dog.wav               (spaces and punctuation as Praat writes them)

A placeholder may name several things with `>`, the first one that isn't empty being used
(`{Phonemic>Phonetic}`: the Phonemic, else the Phonetic), and a field by its element name, its
label or its abbreviation, in any case, with or without spaces (`{Tone Class}`, `{toneclass}`,
`{tnc}`; IDEAS.md ideas 71–73, Josh, 26 October). The same notation serves the Wordlist export.
"""

from __future__ import annotations

import unicodedata

import re

from .model import Database, Entry, Token

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_EDGE_SEPARATORS = "-_. "


def split_pattern(pattern: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a pattern into a leading literal and (separator, placeholder) pairs."""
    parts = []
    pos = 0
    lead = ""
    for i, m in enumerate(_PLACEHOLDER.finditer(pattern)):
        literal = pattern[pos:m.start()]
        if i == 0:
            lead, literal = literal, ""
        parts.append((literal, m.group(1).strip()))
        pos = m.end()
    tail = pattern[pos:]
    if tail:
        parts.append((tail, ""))
    return lead, parts


def render(pattern: str, value_of) -> str:
    """A pattern filled in: value_of(name) gives one name's value ("" when it has none). A
    separator written before a placeholder goes with it when it is empty; `a>b>c` takes the first
    of them that isn't empty."""
    lead, parts = split_pattern(pattern)
    out = lead
    for sep, name in parts:
        if not name:                       # trailing literal
            out += sep
            continue
        value = ""
        for alt in name.split(">"):
            value = value_of(alt.strip()) if alt.strip() else ""
            if value:
                break
        if value:
            out += (sep if out else "") + value
    return out


def lookup(values: dict, fields: list) -> "callable":
    """value_of for render: the template's own words and the values by element name exactly (as
    patterns always worked), else a field by anything it answers to (fieldkeys)."""
    from . import fieldkeys
    folded = {}
    for k in values:
        folded.setdefault(fieldkeys.fold(k), k)

    def value_of(name: str) -> str:
        if name in values:
            return values[name] or ""
        f = fieldkeys.find(fields, name)
        if f is not None and f.name in values:
            return values[f.name] or ""
        k = folded.get(fieldkeys.fold(name))
        return (values.get(k) or "") if k is not None else ""
    return value_of


def placeholder_values(db: Database, e: Entry, t: Token) -> dict[str, str]:
    md = db.metadata
    s = db.settings
    values = {
        "language": md.language_code,
        "variety": md.variety_code,
        "speaker": t.speaker,
        "reference": e.ref,
        "gloss": e.file_gloss,
        "label": e.file_gloss,          # an utterance's file label (a lemma's: its gloss in file names)
        "tags": s.tag_separator.join(s.tags.file_codes(t.tags)),
        "date": t.collected,
    }
    # Any entry or token field by name (first language for multilingual ones).
    for name in list(e.values) + list(e.multi):
        values.setdefault(name, e.get(name))
    for name in list(t.values) + list(t.multi):
        values.setdefault(name, t.get(name))
    return values


def build_filename(db: Database, e: Entry, t: Token, extension: str = ".wav") -> str:
    """The name a token's recording should have; utterances have a pattern of their own."""
    from .model import is_utterance
    pattern = db.settings.utterance_pattern if is_utterance(e) else db.settings.filename_pattern
    s = db.settings
    out = render(pattern, lookup(placeholder_values(db, e, t), list(s.entry_fields) + list(s.token_fields)))
    # Written as Praat names it (D009_big_dog, not D009_big dog), so saving an edited recording in
    # Praat with the name it suggests overwrites this file instead of making a second one (19 October).
    return praat_name(out.strip(_EDGE_SEPARATORS)) + extension


def praat_name(stem: str) -> str:
    """The name Praat gives an object read from a file with this name: spaces and ASCII
    punctuation other than + - = _ become underscores (checked against Praat 6.1, 18 October).
    Praat's Save suggests that name, so a TextGrid named this way is saved over itself. Always NFC
    (composed), whatever the transcriptions' form (format 14): é is one character in a file name."""
    stem = unicodedata.normalize("NFC", stem)
    return "".join(c if (c.isalnum() or c in "+-=_" or ord(c) > 127) else "_" for c in stem)


def build_text_filename(db: Database, text, extension: str = ".wav") -> str:
    """A text's recording (and TextGrid) name: {language}-{variety}_{reference}_{title} by default,
    the title being the file label copied when the text was added, written as Praat would name
    it (LXX-VXX_T001_Hyena_and_Hare), so saving the TextGrid in Praat overwrites this file."""
    md = db.metadata
    values = {"language": md.language_code, "variety": md.variety_code, "reference": text.ref,
              "title": text.file_label, "label": text.file_label, "date": text.date}
    for name, v in text.values.items():
        values.setdefault(name, v)
    out = render(db.settings.text_pattern, lookup(values, list(db.settings.text_fields)))
    return praat_name(out.strip(_EDGE_SEPARATORS)) + extension


# --------------------------------------------------------------------------
# Images (idea 19, ɛλicit): a token's picture is found by name in the main folder's Images
# folder, never shown in Lemmatrix and never stored in the database.
# --------------------------------------------------------------------------

def image_stem(db: Database, e: Entry, t: Token) -> str:
    """The name (without extension) a token's image has: its reference, then its tag codes as in
    soundfile names, written as Praat would name it. D001 for the citation token, D001_PL for
    the plural, D001_PL-1SG_POSS for "my goats". A token without an image of its own has none:
    there is no falling back on the lemma's (a picture of one goat is not one of three)."""
    s = db.settings
    tags = s.tag_separator.join(s.tags.file_codes(t.tags))
    return praat_name(e.ref + ("_" + tags if tags else ""))


def find_image(db: Database, e: Entry, t: Token):
    """The token's image in Images (JPG, PNG or GIF, any case), or None."""
    from pathlib import Path
    from . import layout
    folder = layout.images_folder(db.path)
    if not db.path or not folder.is_dir():
        return None
    stem = image_stem(db, e, t).lower()
    for p in sorted(Path(folder).iterdir()):
        if p.is_file() and p.stem.lower() == stem and p.suffix.lower() in layout.IMAGE_EXTENSIONS:
            return p
    return None
