# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""A database's pitch kind (IDEAS.md idea 9; DESIGN.md 3.5): tonal, intonational or unspecified.

The kind is **data** about the language (Josh, 23 October): it is kept in the metadata's
``<typology>`` block (``<feature id="tone" value="tonal"/>``, format 10) and goes into both archives.
*Show the pitch system* is a tool, a view setting in the workspace (``pitchview``).

    | kind         | lemma tokens' Pitch | utterances' Pitch | Pitch field | Tone Class | scratchpads |
    | tonal        | yes                 | yes               | yes         | yes        | yes         |
    | intonational | no                  | yes               | yes         | no         | no          |
    | unspecified  | no                  | no                | no          | no         | no          |

Converting adds what a kind needs, empty, and never loses data unasked: a field that holds data
stays in the file, hidden by the kind, unless the researcher selects it for deleting (after the
question about a full backup). Emptied fields go, so the XML is clean. No Qt here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Database, FieldDef

FEATURE = "tone"                      # the typology feature's id
TONAL, INTONATIONAL, UNSPECIFIED = "tonal", "intonational", "unspecified"
KINDS = (TONAL, INTONATIONAL, UNSPECIFIED)
LABELS = {TONAL: "Tonal", INTONATIONAL: "Intonational", UNSPECIFIED: "Unspecified"}
TIPS = {
    TONAL: "Pitch on lemma tokens and utterances, the Tone Class field and the pitch scratchpads",
    INTONATIONAL: "Pitch on utterances only: no pitch on lemma tokens, no Tone Class, no pitch scratchpads",
    UNSPECIFIED: "No pitch: no Pitch field, no Tone Class, no pitch scratchpads",
}
CONVERT_NOTE = ("The pitch kind can be changed at any time (Edit → Metadata). Nothing is lost by "
                "converting: data a kind doesn't show stays in the file, hidden, unless you choose to delete it.")
DEFAULT = TONAL                       # Josh, 23 October: a new database is tonal

# the parts of the pitch system each kind has (pitchview.TOKENS, UTTERANCES, SCRATCHPADS)
PARTS = {TONAL: {"tokens", "utterances", "scratchpads"}, INTONATIONAL: {"utterances"}, UNSPECIFIED: set()}

TOKEN_PITCH, UTTERANCE_PITCH, TONE_CLASS = "token-pitch", "utterance-pitch", "tone-class"


def kind(db: Database) -> str:
    k = (db.metadata.typology or {}).get(FEATURE, DEFAULT)
    return k if k in KINDS else DEFAULT


def has_pitch_field(k: str) -> bool:
    return k != UNSPECIFIED


def has_tone_class(k: str) -> bool:
    return k == TONAL


def pitch_field(db: Database) -> FieldDef | None:
    return next((f for f in db.settings.token_fields if f.role == "pitch"), None)


def tone_class_field(db: Database) -> FieldDef | None:
    """Tone Class: an ordinary closed lemma field, found by its name (it has no role)."""
    return next((f for f in db.settings.entry_fields
                 if f.name == "ToneClass" or f.title.replace(" ", "").lower() == "toneclass"), None)


@dataclass
class Holding:
    """Data a kind wouldn't show: kept hidden, or deleted when selected."""
    key: str                          # TOKEN_PITCH, UTTERANCE_PITCH, TONE_CLASS
    label: str                        # "Pitch on 1,048 lemma tokens"
    count: int


def _counts(db: Database) -> dict[str, int]:
    pf, tc = pitch_field(db), tone_class_field(db)
    out = {TOKEN_PITCH: 0, UTTERANCE_PITCH: 0, TONE_CLASS: 0}
    if pf is not None:
        for e in db.entries:
            out[TOKEN_PITCH] += sum(1 for t in e.tokens if t.get(pf.name).strip())
        for u in db.utterances:
            out[UTTERANCE_PITCH] += sum(1 for t in u.tokens if t.get(pf.name).strip())
    if tc is not None:
        out[TONE_CLASS] = sum(1 for e in db.entries if e.get(tc.name).strip())
    return out


def holdings(db: Database, new: str) -> list[Holding]:
    """What holds data that the new kind doesn't show (nothing for a kind with more pitch)."""
    parts = PARTS[new]
    c = _counts(db)
    out = []
    if "tokens" not in parts and c[TOKEN_PITCH]:
        out.append(Holding(TOKEN_PITCH, f"Pitch on {c[TOKEN_PITCH]:,} lemma token{'s' if c[TOKEN_PITCH] != 1 else ''}",
                           c[TOKEN_PITCH]))
    if "utterances" not in parts and c[UTTERANCE_PITCH]:
        out.append(Holding(UTTERANCE_PITCH, f"Pitch on {c[UTTERANCE_PITCH]:,} utterance"
                           f"{'s' if c[UTTERANCE_PITCH] != 1 else ''}", c[UTTERANCE_PITCH]))
    if not has_tone_class(new) and c[TONE_CLASS]:
        out.append(Holding(TONE_CLASS, f"Tone Class on {c[TONE_CLASS]:,} lemma{'s' if c[TONE_CLASS] != 1 else ''}",
                           c[TONE_CLASS]))
    return out


def added(db: Database, new: str) -> list[str]:
    """The fields converting to the new kind adds (their titles)."""
    out = []
    if has_pitch_field(new) and pitch_field(db) is None:
        out.append("Pitch")
    if has_tone_class(new) and tone_class_field(db) is None:
        out.append("Tone Class")
    return out


def convert(db: Database, new: str, delete: set | frozenset = frozenset()) -> list[str]:
    """Make the database the new kind. delete: the Holding keys whose data goes (TOKEN_PITCH…);
    everything else is kept. A field is added where the kind needs it and is missing, and removed
    where the kind doesn't have it and nothing holds data in it any more. Returns what was done,
    in words, for the status bar."""
    from . import defaults
    if new not in KINDS:
        raise ValueError(new)
    s = db.settings
    done = []
    pf = pitch_field(db)
    if TOKEN_PITCH in delete and pf is not None:
        n = 0
        for e in db.entries:
            for t in e.tokens:
                if t.get(pf.name):
                    t.values.pop(pf.name, None)
                    n += 1
        if n:
            done.append(f"Pitch deleted from {n:,} lemma tokens")
    if UTTERANCE_PITCH in delete and pf is not None:
        n = 0
        for u in db.utterances:
            for t in u.tokens:
                if t.get(pf.name):
                    t.values.pop(pf.name, None)
                    n += 1
        if n:
            done.append(f"Pitch deleted from {n:,} utterances")
    tc = tone_class_field(db)
    if TONE_CLASS in delete and tc is not None:
        n = 0
        for e in db.entries:
            if e.get(tc.name):
                e.values.pop(tc.name, None)
                n += 1
        if n:
            done.append(f"Tone Class deleted from {n:,} lemmas")
    db.metadata.typology = dict(db.metadata.typology or {})
    db.metadata.typology[FEATURE] = new
    c = _counts(db)
    # fields the kind needs: added, empty, in their usual places
    if has_pitch_field(new) and pf is None:
        names = [f.name for f in s.token_fields]
        at = names.index("Morphemes") + 1 if "Morphemes" in names else min(3, len(names))
        s.token_fields.insert(at, FieldDef("Pitch", role="pitch"))
        if not (0 <= s.pitch_low < s.pitch_high <= 9):
            s.pitch_low, s.pitch_high = 1, 5
        done.append("Pitch added")
    if has_tone_class(new) and tc is None:
        names = [f.role for f in s.entry_fields]
        at = next((i + 1 for i, r in enumerate(names) if r == "word-class"), len(names))   # before Stem type
        s.entry_fields.insert(at, FieldDef("ToneClass", "Tone Class", closed=True, items=defaults.tone_classes()))
        done.append("Tone Class added")
    # fields the kind doesn't have: removed once nothing holds data in them
    if not has_pitch_field(new) and pf is not None and not (c[TOKEN_PITCH] or c[UTTERANCE_PITCH]):
        s.token_fields.remove(pf)
        done.append("Pitch field removed")
    if not has_tone_class(new) and tc is not None and not c[TONE_CLASS]:
        s.entry_fields.remove(tc)
        done.append("Tone Class field removed")
    return done
