# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The database's typological features (IDEAS.md ideas 56 and 91, Josh, 28 October), kept in the
metadata's <typology> block, one <feature id value/> each, so a person reads them near the top
and a machine finds them by one tag. They describe the language: data, in both archives.

- tone: the pitch kind (pitchkind.py; idea 9);
- morphology: segmental (concatenative), non-concatenative, root-and-pattern;
- order: the canonical constituent order, WALS 81A's values, OV and VO (WALS 83A), topic-initial;
  stored with its WALS feature where it has one (wals="81A"), so compilations line up.

Morphology and order take **any number of values** (Josh, 28 October: chips, so no "both"): one
<feature> element per value, the same id repeated; none chosen is written as value="unspecified".
In memory a feature's values are one string joined by "; " (values() and set_values() read and
write it). An older file's morphology "both" opens as segmental and non-concatenative.

Settings → Typology edits morphology and order as chips under Pitch, Morphology and Syntax; the
pitch kind is shown there fixed (changed in Settings → Pitch). No Qt here."""

from __future__ import annotations

TONE, MORPHOLOGY, ORDER = "tone", "morphology", "order"
UNSPECIFIED = "unspecified"

SEP = "; "                    # several values of one feature, in memory

MORPHOLOGIES = [("segmental", "segmental (concatenative)"), ("non-concatenative", "non-concatenative"),
                ("root-and-pattern", "root-and-pattern")]
OLD_VALUES = {MORPHOLOGY: {"both": ["segmental", "non-concatenative"]}}   # before chips (28 October)

ORDERS = [("SOV", "SOV"), ("SVO", "SVO"), ("VSO", "VSO"), ("VOS", "VOS"), ("OVS", "OVS"), ("OSV", "OSV"),
          ("no dominant order", "no dominant order"), ("OV", "OV (verb-final)"), ("VO", "VO (verb-initial)"),
          ("topic-initial", "topic-initial")]

CHOICES = {MORPHOLOGY: MORPHOLOGIES, ORDER: ORDERS}       # the chips each feature offers

WALS = {**{v: "81A" for v in ("SOV", "SVO", "VSO", "VOS", "OVS", "OSV", "no dominant order")},
        "OV": "83A", "VO": "83A"}

CITATIONS = ("Dryer, Matthew S. 2013. Order of Subject, Object and Verb. In Dryer, Matthew S. & "
             "Haspelmath, Martin (eds.), The World Atlas of Language Structures Online. Leipzig: Max Planck "
             "Institute for Evolutionary Anthropology. (WALS feature 81A.) https://wals.info/chapter/81\n"
             "Dryer, Matthew S. 2013. Order of Object and Verb. In Dryer, Matthew S. & Haspelmath, Martin "
             "(eds.), The World Atlas of Language Structures Online. Leipzig: Max Planck Institute for "
             "Evolutionary Anthropology. (WALS feature 83A.) https://wals.info/chapter/83")

ORDER_TIP = ("The language's canonical (dominant) order of subject, object and verb: what the "
             "Constituents tier will be compared with to find non-canonical orders (v2 Analyze).")
MORPHOLOGY_TIP = "What kind of morphology the language has, so the parsers (v2) know what to look for."


def value(db, feature: str) -> str:
    return (db.metadata.typology or {}).get(feature) or (UNSPECIFIED if feature != TONE else "tonal")


def values(db_or_typology, feature: str) -> list[str]:
    """The feature's chosen values (none: unspecified), in their order, without repeats."""
    ty = db_or_typology if isinstance(db_or_typology, dict) else (db_or_typology.metadata.typology or {})
    raw = ty.get(feature) or ""
    out = []
    for v in raw.split(";"):
        v = v.strip()
        for w in OLD_VALUES.get(feature, {}).get(v, [v]):
            if w and w != UNSPECIFIED and w not in out:
                out.append(w)
    return out


def set_values(typology: dict, feature: str, vals) -> None:
    vals = [v for v in dict.fromkeys(vals) if v and v != UNSPECIFIED]
    typology[feature] = SEP.join(vals) if vals else UNSPECIFIED


def label(feature: str, val: str) -> str:
    return dict(CHOICES.get(feature, [])).get(val, val)


def normalised(typology: dict) -> dict:
    """The typology with every feature Lemmatrix knows (unspecified when not set), tone first."""
    out = {TONE: (typology or {}).get(TONE) or "tonal"}
    for k in (MORPHOLOGY, ORDER):
        out[k] = SEP.join(values(typology or {}, k)) or UNSPECIFIED
    for k, v in (typology or {}).items():         # features of later versions, kept as they are
        out.setdefault(k, v)
    return out


def wals(feature: str, val: str) -> str:
    return WALS.get(val, "") if feature == ORDER else ""
