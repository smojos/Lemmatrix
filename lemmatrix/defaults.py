# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Defaults for new databases: fields, tag structure and reference categories."""

from __future__ import annotations

from .model import (CORE_ROLES, TEXTS, UTTERANCES, Database, FieldDef, Group, ListItem, Location, Metadata, Person,
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
              "Vol. 1: Methodology, p. 296. Oxford: Oxford University Press. They are the categories of "
              "the Extended African Comparative Wordlist (Smolders 2026), which also draws on the SIL "
              "Comparative African Wordlist (Snider, Keith & James Roberts. 2006. SIL Electronic Working "
              "Papers 2006-005) and Swadesh's lists (Swadesh, Morris. 1952, 1955).")

# People and places in a new database: placeholders, to be edited.
RESEARCHERS = [("RS1", "Researcher 1"), ("RS2", "Researcher 2")]
PARTICIPANTS = [("SP1", "Speaker 1"), ("SP2", "Speaker 2")]
PADE_NOTE = "Not a known location; any resemblance is coincidental."


def default_researchers() -> list[Person]:
    return [Person.researcher(c, n) for c, n in RESEARCHERS]     # Identifiable? ticked (idea 44)


def default_participants() -> list[Person]:
    return [Person(c, n) for c, n in PARTICIPANTS]


def default_locations() -> list[Location]:
    """Generic placeholder places (Josh, 23 October: "it is good to see the structure, but keep it
    generic"): two countries, each with a region and a town, to rename. Ucluelet and Pade stay only
    in the sample and test databases, as Easter eggs (easter_egg_locations)."""
    return [Location(f"L{n}", f"L{n}", "country", children=[
                Location(f"L{n} Region", f"L{n}R", "region", children=[Location(f"L{n} Town", f"L{n}T", "town")])])
            for n in (1, 2)]


def easter_egg_locations() -> list[Location]:
    """The places new databases had until 23 October: kept in the sample and test databases."""
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




def stem_types() -> list[ListItem]:
    """Stem type's list (Josh, 23 October): simple, complex, loan, flat; users can nest it."""
    return [ListItem("simple"), ListItem("complex"), ListItem("loan")]


def default_settings() -> Settings:
    s = Settings()
    s.entry_fields = [
        FieldDef("Lemma", role="lemma"),
        FieldDef("Gloss", role="gloss"),
        FieldDef("WordClass", "Word Class", role="word-class", closed=True,
                 items=[ListItem(n) for n in WORD_CLASSES]),
        # Tone Class and Inflection Class after Word Class, before Stem type (Josh, 24 October)
        FieldDef("ToneClass", "Tone Class", closed=True, items=tone_classes()),
        FieldDef("InflectionClass", "Inflection Class", closed=True, items=inflection_classes()),
        FieldDef("StemType", "Stem type", role="stem-type", closed=True, items=stem_types()),   # 22–23 October
        FieldDef("Comment", role="comment"),
    ]
    s.token_fields = [                                # abbreviations: Josh, 26 October (ideas 72, 73)
        FieldDef("Phonetic", role="phonetic", abbr="pht"),
        FieldDef("Phonemic", role="phonemic", abbr="phm"),
        FieldDef("Morphemes", role="morphemes", abbr="mph"),   # the morpheme gloss line (ideas 2 and 7)
        FieldDef("Pitch", role="pitch", abbr="pch"),
        FieldDef("Translation", role="translation", abbr="trs"),
        FieldDef("Comment", role="comment", abbr="com"),
    ]
    s.gloss_languages = ["en"]
    s.primary_gloss = "en"
    s.tags = default_tag_structure()
    s.ref_categories = [RefCategory(c[0], c[1], c[2] if len(c) > 2 else "auto")
                        for c in DEFAULT_CATEGORIES] + utterance_categories() + text_categories()
    s.text_fields = text_fields()
    s.tier_mapping = tier_mapping()
    return s


def ensure_core_fields(s: Settings, skip_roles: tuple = ()) -> list[str]:
    """Give every list its core fields (CORE_ROLES), which can't be deleted. A Comment field
    without a role (older files) gets it quietly; a core field that's missing (deleted before it
    was protected) comes back, empty, where it is in a new database. Returns the restored
    fields' titles. skip_roles: core roles this database doesn't have (Pitch in a database whose
    pitch kind is unspecified, idea 9)."""
    defaults = default_settings()
    restored = []
    for attr in ("entry_fields", "token_fields", "text_fields"):
        have, want = getattr(s, attr), getattr(defaults, attr)
        if attr == "text_fields" and not have:
            continue                                    # (a database without texts' fields yet)
        for pos, d in enumerate(want):
            if d.role not in CORE_ROLES:                # Tone Class, Description…: deletable, never
                continue                                # brought back (the audit, 25 October)
            if any(f.role == d.role for f in have) or d.role in skip_roles:
                continue
            if d.role == "comment":
                plain = [f for f in have if f.is_comment and not f.role]
                hit = next((f for f in plain if f.name.lower() == "comment"), plain[0] if plain else None)
            else:
                hit = next((f for f in have if f.name == d.name and not f.role), None)
            if hit is not None:                         # the field is there, without its role
                hit.role = d.role
                if d.role in ("word-class", "stem-type"):
                    hit.closed = True
                continue
            have.insert(min(pos, len(have)), d)
            restored.append(d.title)
    return restored


def default_metadata() -> Metadata:
    return Metadata(researchers=default_researchers(), participants=default_participants(),
                    locations=default_locations())


def new_database(base: str = "", items: str = "", region: str = "") -> Database:
    """A new database, empty or built on a comparative wordlist (IDEAS.md idea 40, Josh, 22 October):
    "EACW" (references C001f…, Lemmatrix's reference categories), "CAWL" or "SWADESH" (the list's
    own numbers as references, 0345 or 042, with no categories: utterances and texts take the next
    number). Every lemma gets the list's gloss and a word class, and the other lists' numbers.
    The EACW comes in versions (Josh, 23 October): items base (its default items) or expanded (its
    hidden items too), and region global, africa or one region (N W E S C)."""
    db = Database(metadata=default_metadata(), settings=default_settings())
    if base:
        fill_from_wordlist(db, base, items, region)
    return db


def fill_from_wordlist(db: Database, base: str, items: str = "", region: str = ""):
    from . import wordlists as wl
    from .model import FORBIDDEN_CHARS, SEQUENCE
    base = wl.list_id(base)
    if not base:
        return
    db.metadata.wordlist_base = base
    s = db.settings
    if base != wl.EACW:                  # Josh: "the classificatory reference system is removed"
        s.ref_scheme = SEQUENCE
        s.ref_digits = wl.DIGITS[base]
        s.ref_categories = []
        chosen = wl.get(base).items
    else:                                # the version chosen, the Clarification and Taxon fields,
        items = items or wl.BASE         # and the list's word classes (DEM, CONJ…)
        region = region or wl.AFRICA
        db.metadata.wordlist_items, db.metadata.wordlist_region = items, region
        db.metadata.wordlist_version = wl.EACW_VERSION      # format 12: up to date with the shipped list
        chosen = wl.version_items(items, region)
        wl.ensure_fields(db)
        wl.ensure_word_classes(db)
    classes = set(s.word_classes())
    for item in chosen:
        gloss = wl.item_gloss(base, item)
        wc = wl.word_class_for(base, item)
        e = db.new_entry(wl.display(base, item.number), gloss=gloss,
                         word_class=wc if wc in classes else "")
        e.file_gloss = "".join(ch for ch in e.file_gloss if ch not in FORBIDDEN_CHARS).strip()
        e.lists = wl.other_numbers(base, item.number)
        if base == wl.EACW:
            for role in (wl.CLARIFICATION, wl.TAXON):
                if (value := getattr(item, role)) and (f := s.entry_field(role)) is not None:
                    e.set(f.name, value)
        db.entries.append(e)
