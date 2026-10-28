# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The database's typological features (IDEAS.md ideas 56 and 91, Josh, 28 October), kept in the
metadata's <typology> block, one <feature id value/> each, so a person reads them near the top
and a machine finds them by one tag. They describe the language: data, in both archives.

- tone: the pitch kind (pitchkind.py; idea 9);
- morphology: segmental (concatenative), non-concatenative, both, root-and-pattern, unspecified;
- order: the canonical constituent order, WALS 81A's values, OV and VO (WALS 83A), topic-initial,
  unspecified; stored with its WALS feature where it has one (wals="81A"), so compilations line up.

Settings → Typology edits morphology and order (the pitch kind too, kept in step with
Edit → Metadata). No Qt here."""

from __future__ import annotations

TONE, MORPHOLOGY, ORDER = "tone", "morphology", "order"
UNSPECIFIED = "unspecified"

MORPHOLOGIES = [("segmental", "segmental (concatenative)"), ("non-concatenative", "non-concatenative"),
                ("both", "both"), ("root-and-pattern", "root-and-pattern"), (UNSPECIFIED, "unspecified")]

ORDERS = [("SOV", "SOV"), ("SVO", "SVO"), ("VSO", "VSO"), ("VOS", "VOS"), ("OVS", "OVS"), ("OSV", "OSV"),
          ("no dominant order", "no dominant order"), ("OV", "OV (verb-final)"), ("VO", "VO (verb-initial)"),
          ("topic-initial", "topic-initial"), (UNSPECIFIED, "unspecified")]

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


def normalised(typology: dict) -> dict:
    """The typology with every feature Lemmatrix knows (unspecified when not set), tone first."""
    out = {TONE: (typology or {}).get(TONE) or "tonal"}
    for k in (MORPHOLOGY, ORDER):
        v = (typology or {}).get(k) or UNSPECIFIED
        out[k] = v
    for k, v in (typology or {}).items():         # features of later versions, kept as they are
        out.setdefault(k, v)
    return out


def wals(feature: str, val: str) -> str:
    return WALS.get(val, "") if feature == ORDER else ""
