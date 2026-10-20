# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Shared test setup.

Most feature tests (renames, recordings, matrices...) were written against the prototype's tag
structure: NOUN and VERB groups, no default for Number, an Oblique case. They test the features,
not the defaults, so they keep using that structure. Tests of the defaults themselves are marked
`real_defaults` and see the structure a new database really gets.
"""

import pytest

from lemmatrix import defaults
from lemmatrix.defaults import EXAMPLES, INSTANCES, _tags
from lemmatrix.model import Group, TagStructure

REAL_TAG_STRUCTURE = defaults.default_tag_structure


def prototype_tag_structure() -> TagStructure:
    persons = ["1SG", "2SG", "3SG", "1PL", "2PL", "3PL"]
    subjects = [f"{p}.{r}" for p in persons for r in ("A", "S")]
    objects = [f"{p}.O" for p in persons]
    noun = Group("NOUN", groups=[
        Group("Number", _tags(("Singular", "SG"), ("Plural", "PL"))),
        Group("Case", _tags(("Nominative", "NOM"), ("Accusative", "ACC"), ("Ergative", "ERG"),
                            ("Absolutive", "ABS"), ("Genitive", "GEN"), ("Oblique", "OBL"))),
    ], usual=["NOUN"])
    verb = Group("VERB", groups=[
        Group("Subject", _tags(*subjects)),
        Group("Object", _tags(*objects)),
        Group("Stem", _tags("Simple", ("Passive", "PASS"), ("Antipassive", "AP"),
                            ("Causative", "CAUS"), default="Simple")),
        Group("Tense", _tags(("Past", "PST"), ("Present", "PRS"), ("Future", "FUT"))),
        Group("Aspect", _tags(("Perfective", "PFV"), ("Imperfective", "IPFV"))),
        Group("Mood", _tags("Indicative", ("Imperative", "IMP"), default="Indicative")),
        Group("Polarity", _tags("Affirmative", ("Negative", "NEG"), default="Affirmative")),
    ], usual=["VERB"])
    shared = [
        Group("Phonological", groups=[
            Group("Following tone", _tags(("before H", "xH"), ("before L", "xL"))),
            Group("Preceding tone", _tags(("after H", "Hx"), ("after L", "Lx"))),
        ]),
        Group("Syntactic", groups=[
            Group("Position vis predicate", _tags(("preverbal", "PREV"), ("postverbal", "POSTV"),
                                                  ("non-verbal predicate", "PRED"))),
            Group("Utterance position", _tags("isolation", ("utterance-initial", "INI"),
                                              ("utterance-final", "FIN"), default="isolation")),
        ]),
        Group(INSTANCES, groups=[
            Group("Frames", _tags(("Frame 1", "F1"), ("Frame 2", "F2"))),
            Group(EXAMPLES, _tags(("Example 1", "x1"), ("Example 2", "x2"))),
        ]),
    ]
    for g in (noun, verb, *shared):              # descriptions as the prototype had them: none
        for sub in g.walk():
            sub.description = ""
            for t in sub.tags:
                t.description = ""
    return TagStructure([noun, verb, *shared])


def pytest_configure(config):
    config.addinivalue_line("markers", "real_defaults: use the tag structure new databases really get")


@pytest.fixture(autouse=True)
def _prototype_tags(request, monkeypatch):
    if request.node.get_closest_marker("real_defaults") is None:
        monkeypatch.setattr(defaults, "default_tag_structure", prototype_tag_structure)
