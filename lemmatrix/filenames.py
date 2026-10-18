"""Building sound file names from the customisable pattern.

The default pattern is

    {language}-{variety}-{speaker}_{reference}_{gloss}_{tags}

Each separator written before a placeholder belongs to that placeholder, so
when a part is empty its separator goes too:

    LXX-VXX-SP1_D009_goat_PL-GEN-xH.wav
    LXX_D009_goat.wav                      (no variety, no speaker, no tags)
"""

from __future__ import annotations

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
    lead, parts = split_pattern(pattern)
    values = placeholder_values(db, e, t)
    out = lead
    for sep, name in parts:
        if not name:                       # trailing literal
            out += sep
            continue
        value = values.get(name, "")
        if value:
            out += (sep if out else "") + value
    out = out.strip(_EDGE_SEPARATORS)
    return out + extension
