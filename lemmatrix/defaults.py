"""Defaults for new databases: fields, tag structure and reference categories."""

from __future__ import annotations

from .model import (Database, FieldDef, Group, Metadata, RefCategory, Settings, Tag,
                    TagStructure, WordClass)


def _tags(*pairs, default: str | None = None) -> list[Tag]:
    out = []
    for p in pairs:
        name, code = (p, p) if isinstance(p, str) else p
        out.append(Tag(name=name, code="" if name == default else code, default=(name == default)))
    return out


def default_tag_structure() -> TagStructure:
    persons = ["1SG", "2SG", "3SG", "1PL", "2PL", "3PL"]
    subjects = [f"{p}.{r}" for p in persons for r in ("A", "S")]
    objects = [f"{p}.O" for p in persons]
    noun = WordClass("NOUN", [
        Group("Number", _tags(("Singular", "SG"), ("Plural", "PL"))),
        Group("Case", _tags(("Nominative", "NOM"), ("Accusative", "ACC"), ("Ergative", "ERG"),
                            ("Absolutive", "ABS"), ("Genitive", "GEN"), ("Oblique", "OBL"))),
    ])
    verb = WordClass("VERB", [
        Group("Subject", _tags(*subjects)),
        Group("Object", _tags(*objects)),
        Group("Stem", _tags("Simple", ("Passive", "PASS"), ("Antipassive", "AP"),
                            ("Causative", "CAUS"), default="Simple")),
        Group("Tense", _tags(("Past", "PST"), ("Present", "PRS"), ("Future", "FUT"))),
        Group("Aspect", _tags(("Perfective", "PFV"), ("Imperfective", "IPFV"))),
        Group("Mood", _tags("Indicative", ("Imperative", "IMP"), default="Indicative")),
        Group("Polarity", _tags("Affirmative", ("Negative", "NEG"), default="Affirmative")),
    ])
    others = [WordClass(n) for n in ("PRONOUN", "QUANT", "ADJECTIVE", "ADVERB")]
    all_classes = [
        Group("Phonological", groups=[
            Group("Following tone", _tags(("before H", "xH"), ("before L", "xL"))),
            Group("Preceding tone", _tags(("after H", "Hx"), ("after L", "Lx"))),
        ]),
        Group("Syntactic", groups=[
            Group("Position vis predicate", _tags(("preverbal", "PREV"), ("postverbal", "POSTV"),
                                                  ("non-verbal predicate", "PRED"))),
            Group("Utterance position", _tags("in isolation", ("utterance-initial", "INI"),
                                              ("utterance-final", "FIN"), default="in isolation")),
        ]),
        Group("Frames", _tags("f1", "f2", "f3", "f4")),
    ]
    return TagStructure([noun, verb, *others], all_classes)


DEFAULT_CATEGORIES = [
    ("A", "Human body"), ("B", "Human designations"), ("C", "Kinship terms & ethnonyms"),
    ("D", "Mammals"), ("E", "Birds"), ("F", "Fish"), ("G", "Reptiles & amphibians"),
    ("H", "Insects & other small things"), ("I", "Spiritual, disease, ceremony"),
    ("J", "Flora, food, drink"), ("K", "Cultural artifacts"), ("L", "Inanimate nature"),
    ("M", "Speech, thought"), ("N", "Space, direction, time"), ("O", "Other"),
    ("P", "Property concepts"), ("Q", "Quantifiers", "manual"), ("R", "Pronouns", "manual"),
    ("V", "Verbs"),
]


def default_settings() -> Settings:
    s = Settings()
    s.entry_fields = [
        FieldDef("Lemma", role="lemma"),
        FieldDef("Gloss", role="gloss"),
        FieldDef("WordClass", "Word Class", role="word-class", closed=True),
        FieldDef("ToneClass", "Tone Class", closed=True),
        FieldDef("InflectionClass", "Inflection Class", closed=True),
        FieldDef("Comment"),
    ]
    s.token_fields = [
        FieldDef("Phonetic", role="phonetic"),
        FieldDef("Phonemic", role="phonemic"),
        FieldDef("Pitch", role="pitch"),
        FieldDef("Translation", role="translation"),
        FieldDef("Comment"),
    ]
    s.gloss_languages = ["en"]
    s.primary_gloss = "en"
    s.tags = default_tag_structure()
    s.ref_categories = [RefCategory(c[0], c[1], c[2] if len(c) > 2 else "auto")
                        for c in DEFAULT_CATEGORIES]
    return s


def new_database() -> Database:
    return Database(metadata=Metadata(), settings=default_settings())
