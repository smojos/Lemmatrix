# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Defaults for new databases: fields, tag structure and reference categories."""

from __future__ import annotations

from .model import (TEXTS, UTTERANCES, Database, FieldDef, Group, ListItem, Location, Metadata, Person,
                    RefCategory, Settings, Tag, TagStructure, TierMapping, TierRule)
from .tagdefs import tag_description

WORD_CLASSES = ["NOUN", "VERB", "PRONOUN", "QUANT", "ADJECTIVE", "ADVERB"]
INSTANCES = "Instances"          # top-level group: Frames and Examples
EXAMPLES = "Examples"            # Example 1 = X1 …: tells apart tokens that would share a file name


def _tags(*pairs, default: str | None = None) -> list[Tag]:
    """Tags from names or (name, code) pairs. A group's default has no code: file names leave it out."""
    out = []
    for p in pairs:
        name, code = (p, p) if isinstance(p, str) else p
        out.append(Tag(name=name, code="" if name == default else code, default=(name == default),
                       description=tag_description(name)))
    return out


def _group(name: str, tags=(), groups=(), usual=()) -> Group:
    return Group(name, list(tags), list(groups), list(usual), description=tag_description(name))


PERSONS = ["1SG", "2SG", "3SG", "1PL", "2PL", "3PL"]


def default_tag_structure() -> TagStructure:
    subjects = [f"{p}.{r}" for p in PERSONS + ["NP"] for r in ("A", "S")]
    objects = [f"{p}.O" for p in PERSONS + ["NP"]]
    possessors = [f"{p}.POSS" for p in PERSONS]
    nominal = _group("Nominal", groups=[
        _group("Number", _tags(("Singular", "SG"), ("Plural", "PL"), default="Singular")),
        _group("Case", _tags(("Nominative", "NOM"), ("Accusative", "ACC"), ("Ergative", "ERG"),
                             ("Absolutive", "ABS"), ("Genitive", "GEN"), ("Pertensive", "PER"),
                             ("Locative", "LOC"), default="Nominative")),
        _group("Possession", _tags(*possessors)),
    ], usual=["NOUN"])
    verbal = _group("Verbal", groups=[
        _group("Subject", _tags(*subjects)),
        _group("Object", _tags(*objects)),
        _group("Stem", _tags("Simple", ("Infinitive", "INF"), ("Passive", "PASS"), ("Antipassive", "AP"),
                             ("Causative", "CAUS"), default="Simple")),
        _group("Tense", _tags(("Present", "PRS"), ("Past", "PST"), ("Future", "FUT"), default="Present")),
        _group("Aspect", _tags(("Perfective", "PFV"), ("Imperfective", "IPFV"), default="Perfective")),
        _group("Mood", _tags("Indicative", ("Imperative", "IMP"), ("Interrogative", "INT"),
                             default="Indicative")),
        _group("Polarity", _tags("Affirmative", ("Negative", "NEG"), default="Affirmative")),
    ], usual=["VERB"])
    shared = [                                  # no hint: usual for every lemma
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
        Group(INSTANCES, groups=[            # the same form said again: in a frame, or another example
            Group("Frames", _tags(("Frame 1", "F1"), ("Frame 2", "F2"))),
            Group(EXAMPLES, _tags(("Example 1", "x1"), ("Example 2", "x2"))),   # lowercase: Josh's convention for a non-linguistic gloss
        ]),
    ]
    return TagStructure([nominal, verbal, *shared])


DEFAULT_CATEGORIES = [
    ("A", "Human body"), ("B", "Human designations"), ("C", "Kinship terms & ethnonyms"),
    ("D", "Mammals"), ("E", "Birds"), ("F", "Fish"), ("G", "Reptiles & amphibians"),
    ("H", "Insects & other small things"), ("I", "Spiritual, disease, ceremony"),
    ("J", "Flora, food, drink"), ("K", "Cultural artifacts"), ("L", "Inanimate nature"),
    ("M", "Speech, thought"), ("N", "Space, direction, time"), ("O", "Other"),
    ("P", "Property concepts"), ("Q", "Quantifiers", "manual"), ("R", "Pronouns", "manual"),
    ("V", "Verbs"),
]

# Utterances (one-off sentences and phrases with no lemma): U for those not sorted yet, and
# W, X, Y, Z for categories of the user's own (renamed in Edit → Lists → Reference categories).
UTTERANCE_CATEGORIES = [
    ("U", "Unorganised"), ("W", "Own category W"), ("X", "Own category X"),
    ("Y", "Own category Y"), ("Z", "Own category Z"),
]


def utterance_categories() -> list[RefCategory]:
    return [RefCategory(letter, name, "auto", UTTERANCES) for letter, name in UTTERANCE_CATEGORIES]


# Texts and songs (idea 7, stage 3): catalogue records with a recording and a Praat TextGrid.
TEXT_CATEGORIES = [("T", "Texts"), ("S", "Songs")]

GENRES = [ListItem("narrative", [ListItem("personal narrative"), ListItem("folktale"), ListItem("history")]),
          ListItem("procedural"), ListItem("hortatory"), ListItem("expository"), ListItem("conversation"),
          ListItem("song"), ListItem("prayer"), ListItem("elicited"), ListItem("other")]
STATUSES = ["untranscribed", "transcribed", "translated", "analyzed", "finished"]
TONE_CLASSES = ["H", "L", "LH", "HL"]
INFLECTION_CLASSES = [("Nominal", ["I", "II"]), ("Verbal", ["I", "II"])]

# Reference categories (lemmas): inspired by Dixon (2010: 296).
DIXON_NOTE = ("The default categories are inspired by Dixon, R. M. W. 2010. Basic Linguistic Theory, "
              "Vol. 1: Methodology, p. 296. Oxford: Oxford University Press.")

# People and places in a new database: placeholders, to be edited.
RESEARCHERS = [("RS1", "Researcher 1"), ("RS2", "Researcher 2")]
PARTICIPANTS = [("SP1", "Speaker 1"), ("SP2", "Speaker 2")]
PADE_NOTE = "Not a known location; any resemblance is coincidental."


def default_researchers() -> list[Person]:
    return [Person.researcher(c, n) for c, n in RESEARCHERS]     # Identifiable? ticked (idea 44)


def default_participants() -> list[Person]:
    return [Person(c, n) for c, n in PARTICIPANTS]


def default_locations() -> list[Location]:
    return [Location("Canada", "CA", children=[
                Location("British Columbia", "BC", children=[Location("Ucluelet", "UCL-V")])]),
            Location("Ethiopia", "ET", children=[
                Location("Gambella Regional State", "GBRS", children=[Location("Pade", "PADE", PADE_NOTE)])])]


def tone_classes() -> list[ListItem]:
    return [ListItem(x) for x in TONE_CLASSES]


def inflection_classes() -> list[ListItem]:
    return [ListItem(top, [ListItem(x) for x in subs]) for top, subs in INFLECTION_CLASSES]


def text_categories() -> list[RefCategory]:
    return [RefCategory(letter, name, "auto", TEXTS) for letter, name in TEXT_CATEGORIES]


def text_fields() -> list[FieldDef]:
    import copy
    return [
        FieldDef("Title", role="title"),
        FieldDef("Genre", role="genre", closed=True, items=copy.deepcopy(GENRES)),
        FieldDef("Status", "Transcription status", role="status", closed=True,
                 items=[ListItem(x) for x in STATUSES]),
        FieldDef("Description"),
        FieldDef("Comment", role="comment"),
    ]


def tier_mapping() -> TierMapping:
    """Toolbox and FLEx tier names: tx the text (the lines), ge the glosses, ft the free translation;
    mb (morpheme breaks) is ignored."""
    return TierMapping("tx", [TierRule("tx", "Phonetic"), TierRule("ge", "Morphemes"),
                              TierRule("ft", "Translation", "en"), TierRule("mb", "")])


def default_settings() -> Settings:
    s = Settings()
    s.entry_fields = [
        FieldDef("Lemma", role="lemma"),
        FieldDef("Gloss", role="gloss"),
        FieldDef("WordClass", "Word Class", role="word-class", closed=True,
                 items=[ListItem(n) for n in WORD_CLASSES]),
        FieldDef("ToneClass", "Tone Class", closed=True, items=tone_classes()),
        FieldDef("InflectionClass", "Inflection Class", closed=True, items=inflection_classes()),
        FieldDef("Comment", role="comment"),
    ]
    s.token_fields = [
        FieldDef("Phonetic", role="phonetic"),
        FieldDef("Phonemic", role="phonemic"),
        FieldDef("Morphemes", role="morphemes"),      # the morpheme gloss line (ideas 2 and 7)
        FieldDef("Pitch", role="pitch"),
        FieldDef("Translation", role="translation"),
        FieldDef("Comment", role="comment"),
    ]
    s.gloss_languages = ["en"]
    s.primary_gloss = "en"
    s.tags = default_tag_structure()
    s.ref_categories = [RefCategory(c[0], c[1], c[2] if len(c) > 2 else "auto")
                        for c in DEFAULT_CATEGORIES] + utterance_categories() + text_categories()
    s.text_fields = text_fields()
    s.tier_mapping = tier_mapping()
    return s


def ensure_core_fields(s: Settings) -> list[str]:
    """Give every list its core fields (CORE_ROLES), which can't be deleted. A Comment field
    without a role (older files) gets it quietly; a core field that's missing (deleted before it
    was protected) comes back, empty, where it is in a new database. Returns the restored
    fields' titles."""
    defaults = default_settings()
    restored = []
    for attr in ("entry_fields", "token_fields", "text_fields"):
        have, want = getattr(s, attr), getattr(defaults, attr)
        if attr == "text_fields" and not have:
            continue                                    # (a database without texts' fields yet)
        for pos, d in enumerate(want):
            if any(f.role == d.role for f in have):
                continue
            if d.role == "comment":
                plain = [f for f in have if f.is_comment and not f.role]
                hit = next((f for f in plain if f.name.lower() == "comment"), plain[0] if plain else None)
            else:
                hit = next((f for f in have if f.name == d.name and not f.role), None)
            if hit is not None:                         # the field is there, without its role
                hit.role = d.role
                if d.role == "word-class":
                    hit.closed = True
                continue
            have.insert(min(pos, len(have)), d)
            restored.append(d.title)
    return restored


def default_metadata() -> Metadata:
    return Metadata(researchers=default_researchers(), participants=default_participants(),
                    locations=default_locations())


def new_database() -> Database:
    return Database(metadata=default_metadata(), settings=default_settings())
