# SPDX-License-Identifier: LicenseRef-Lemmatrix-Samples
# Copyright © 2026 Joshua A. G. Smolders. All rights reserved: see SAMPLES.md.
"""Build the sample database: an invented language, with short synthetic recordings.

    python samples/make_sample.py        ->  samples/Sample.xml and samples/Soundfiles/

The language (LXX, variety VXX) is made up for trying out Lemmatrix: it is not a real language.
Any resemblance to any living language is a complete coincidence.
The database uses the program's defaults (fields,
tags, lists), with invented people, places and a funder (sample_metadata); only the frames'
carrier sentences are filled in.

Phonology
  Consonants  p pʼ pʰ b ɓ t tʼ tʰ t̪ t̪ʰ t̪ʼ d̪ d ɗ c cʰ cʼ ɟ k kʼ kʰ g ʔ β s z ʃ t͡s d͡z n m ŋ ɲ l r w j ɥ
  Vowels      a i ɪ u ʊ e ɛ o ɔ ʌ ə, and long aa ii ɪɪ uu ʊʊ ee ɛɛ oo ɔɔ ʌʌ
  Tones       v́ H, v̄ M, v̀ L, v̂ HL, v̌ LH, ꜜ downstep (Phonemic only); Pitch: H 55, M 33, L 11, a downstepped H 44;
              downdrift: after an L, H is 44 then 33, M 33 then 22, never back up to 5;
              a final L falls to 10 (final lowering). A long vowel's tone is marked on its first half (áa);
              a contour on a long vowel is split between the halves (áà).
  Syllables   CVN CVVN CV CVV CVCV CVVCV CVNCV CVVNCV CVCVCV CVNCVCV; a nasal before a
              consonant shares its place.
  Phonetic    no tones, length as ː; velars are labialised before round vowels (kʷ) and
              palatalised before high front ones (kʲ); a word-final vowel after a nasal is
              nasalised (ṽ), a vowel after an aspirate breathy (v̤), after a glottal consonant
              creaky (v̰); never two of these on one syllable.

Morphology
  Pronouns  1SG mɪ̀ɪ, 2SG jɔ̀ɔ, 3SG wɛ́ɛ, 1PL tʌ́ʌn, 2PL βʊ̄ʊ, 3PL kɪ́ɪn; their first syllable is
            the prefix for subjects (verbs) and possessors (nouns): mɪ̀-dʌ́ʌm 'my goat'.
  Nouns     PL -à after a consonant (class I), -nà after a vowel (class II).
  Verbs     PRS unmarked, PST -ɛ̀ (class I) / -rɛ̀ (class II), FUT dɔ̄- after the subject;
            IMP -á / -rá, 2PL with βʊ̄-; NEG imperative: kʌ̀ before the verb.
            A full noun object (NP.O) follows the verb.
  Syntax    SVO; a full noun subject comes before the verb, which keeps its agreeing prefix
            (ŋɔ́ɔɲ wɛ́-tʌ̄ŋɛ̀ 'the lion ate'); adjectives and numbers follow the noun (dʌ́ʌmà ɓɪ̀ɪ
            'two goats'); a possessor noun comes before the possessed, unmarked (ŋɔ́ɔɲ rɪ̀ɪŋ 'lion
            meat'); an adverb starts or ends the clause; a copula clause is X (ADJ) ɗɪ̄ɪ.
  Text      T001 'The man and the lion' (TEXT_LINES), recorded by Josh, with lines 3, 4 and 10
            clipped as U001-U003.
  Frames    Frame 1: ___ ɗɪ̄ɪ 'it is a ___'; Frame 2: mɪ̀ɲɔ̄ɔ ___ 'I see the ___'.
"""

from __future__ import annotations

import shutil
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lemmatrix import audio, matrix as mx, pitch, storage, workspace  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402
from lemmatrix.defaults import new_database  # noqa: E402

RATE = 11025
SPEAKER, DATE = "DML", "2026-10-20"

# ---------------------------------------------------------------------------------------------
# The lexicon (phonemic, with tones)
# ---------------------------------------------------------------------------------------------

NOUNS = [   # reference letter, gloss, form, the object it is (for verbs' NP objects)
    ("A", "head", "tʊ́ʊm"), ("A", "eye", "ɲɪ̀n"), ("A", "mouth", "ɓʌ̄ŋ"), ("A", "tooth", "cɔ́kà"),
    ("A", "hand", "dàmbɛ́"), ("A", "foot", "pʰúrʊ̀"),
    ("B", "person", "ʔɪ́ɪn"), ("B", "man", "gàanà"), ("B", "woman", "dɛ̄nzɪ́"), ("B", "child", "tʰʊ̀ŋ"),
    ("C", "mother", "mʌ̀ʌ"), ("C", "father", "βɔ́ɔ"),
    ("D", "goat", "dʌ́ʌm"), ("D", "lion", "ŋɔ́ɔɲ"), ("D", "sheep", "pɛ́ɛ"), ("D", "cow", "ŋʊ̀ʊŋ"),
    ("D", "dog", "ɟɪ̀ŋ"), ("D", "elephant", "ʃɔ̀mbɔ́rɔ̀"),
    ("E", "duck", "kʊ́kʊ̀"), ("E", "eagle", "ɗɪ́ꜜɗɪ́"), ("E", "ostrich", "ɓʊ̀ʊndʊ́"),
    ("F", "fish", "ɲɛ́ɛm"), ("F", "catfish", "kʰʌ̀nt̪ʌ́"),
    ("G", "snake", "t͡sɔ́ɔ"), ("G", "crocodile", "ŋàŋkáꜜrá"), ("G", "frog", "ɓɛ̀ɓɛ̄"),
    ("H", "fly", "ʃɪ̀ɪn"), ("H", "bee", "dɔ́ŋ"), ("H", "termite", "zʌ̀mbʌ̀"),
    ("I", "god", "jʊ́ʊ"),
    ("J", "tree", "jɛ́ɛn"), ("J", "leaf", "pàlàtá"), ("J", "food", "kʊ́ndɛ̀"), ("J", "water", "ɲʊ́ʊ̀"),
    ("J", "meat", "rɪ̀ɪŋ"), ("J", "sorghum", "d͡zàmá"), ("J", "milk", "cʰʌ̀ʌ"), ("J", "honey", "ʃáꜜsá"),
    ("K", "house", "kʊ̀ʊn"), ("K", "pot", "dɪ́ɪɗɪ̀"), ("K", "spear", "bɛ̄ɛŋ"), ("K", "rope", "lʊ́ŋgʊ̀"),
    ("K", "knife", "t͡sɪ̀mpɪ́"), ("K", "basket", "ʃɛ̀nzɛ̀"),
    ("L", "sun", "cɔ̀ɔŋ"), ("L", "moon", "pʼɛ̄ɛ"), ("L", "rain", "ɓʊ́ʊ"), ("L", "fire", "d̪ɔ́ɔɲ"),
    ("L", "stone", "kɔ̀ɔlɔ́"), ("L", "river", "wɔ̄ɔn"),
]

VERBS = [   # gloss, root, past tense of the gloss, its object (a noun's gloss)
    ("eat", "tʌ̄ŋ", "ate", "food"), ("drink", "mʊ̀ʊn", "drank", "water"), ("see", "ɲɔ̄ɔ", "saw", "lion"),
    ("hit", "pʼɪ́", "hit", "dog"), ("take", "jàn", "took", "knife"), ("carry", "ɓɛ́ɛŋ", "carried", "pot"),
    ("cook", "t͡sʊ̀mbà", "cooked", "meat"), ("build", "ɟɛ̀ɛ", "built", "house"),
    ("cut", "kʼɔ́tà", "cut", "rope"), ("kill", "rɛ̀ɛm", "killed", "snake"),
    ("hold", "gʊ́ʊ", "held", "spear"), ("call", "lɔ̄ɔlɛ̀", "called", "child"),
    ("hear", "pʰɪ̀ɪ", "heard", "rain"), ("know", "d͡zɪ́ɪn", "knew", "person"),
    ("catch", "ŋɪ́mbɪ̀", "caught", "fish"), ("throw", "βàdá", "threw", "stone"),
    ("plant", "sɪ̀ndʊ́", "planted", "sorghum"), ("find", "ɥɛ̂n", "found", "goat"),
    ("wash", "t̪ɔ̀ɔŋkɔ́", "washed", "hand"), ("sell", "cʼàlàmá", "sold", "milk"),
]

PRONOUNS = [   # tag stem, form, English (subject, object, possessive)
    ("1SG", "mɪ̀ɪ", "I", "my"), ("2SG", "jɔ̀ɔ", "you (sg)", "your (sg)"), ("3SG", "wɛ́ɛ", "he", "his"),
    ("1PL", "tʌ́ʌn", "we", "our"), ("2PL", "βʊ̄ʊ", "you (pl)", "your (pl)"), ("3PL", "kɪ́ɪn", "they", "their"),
]

NUMBERS = [("one", "ʔɔ́n", "one"), ("two", "ɓɪ̀ɪ", "two"), ("three", "sàdɛ́", "three"),
           ("four", "ŋʊ̂ŋ", "four"), ("five", "t̪ʰʌ́ʌn", "five"), ("six", "t̪ʰʌ́ʌn ʔɔ́n", "five one"),
           ("seven", "t̪ʰʌ́ʌn ɓɪ̀ɪ", "five two"), ("eight", "t̪ʰʌ́ʌn sàdɛ́", "five three"),
           ("nine", "t̪ʰʌ́ʌn ŋʊ̂ŋ", "five four"), ("ten", "ɟɔ̌", "ten")]
MASS = {"water", "meat", "milk", "honey", "food", "sorghum", "fire", "rain"}

ADJECTIVES = [("big", "dʊ́ŋ"), ("small", "cɪ̀cɪ̀"), ("good", "ɲɛ̄ɛ"), ("bad", "kʼʌ̀ʌn"), ("red", "mɔ̄ɔɲ"),
              ("white", "pɛ̀pɛ́"), ("black", "d̪ʊ̀ʊ"), ("long", "lʌ̀ʌŋgʌ́"), ("short", "kʊ́tʊ́"),
              ("hot", "ʃʊ́ʊ")]

ADVERBS = [("today", "ɲàmá"), ("here", "dɛ̀ɛ́")]

COPULA, SEE_1SG = "ɗɪ̄ɪ", "mɪ̀ɲɔ̄ɔ"
FRAMES = {"Frame 1": "___ ɗɪ̄ɪ ‘it is a ___’", "Frame 2": "mɪ̀ɲɔ̄ɔ ___ ‘I see the ___’"}

# Lemmas recorded in full (every token); the others have a recording of the citation form only.
RECORDED_IN_FULL = {"goat", "house", "eat", "drink"}

# ---------------------------------------------------------------------------------------------
# Phonology: segments, Phonetic forms, Pitch
# ---------------------------------------------------------------------------------------------

VOWELS = set("aiɪuʊeɛoɔʌə")
ROUND, HIGH_FRONT = set("uʊoɔ"), set("iɪ")
CONSONANTS = sorted("p pʼ pʰ b ɓ t tʼ tʰ t̪ t̪ʰ t̪ʼ d̪ d ɗ c cʰ cʼ ɟ k kʼ kʰ g ʔ β s z ʃ t͡s d͡z n m ŋ ɲ l r w j ɥ"
                    .split(), key=len, reverse=True)
NASALS = set("mnŋɲ")
VELARS = {"k", "kʼ", "kʰ", "g"}
GLOTTAL = {"ʔ", "ɓ", "ɗ", "pʼ", "tʼ", "t̪ʼ", "cʼ", "kʼ"}
HOMORGANIC = {"m": set("pbɓβ") | {"pʼ", "pʰ"}, "n": {"t", "tʼ", "tʰ", "d", "ɗ", "s", "z", "l", "r", "t̪", "t̪ʰ",
                                                    "t̪ʼ", "d̪", "t͡s", "d͡z"},
              "ɲ": {"c", "cʰ", "cʼ", "ɟ", "ʃ"}, "ŋ": {"k", "kʼ", "kʰ", "g"}}
TONES = {"́": "H", "̀": "L", "̄": "M", "̂": "HL", "̌": "LH"}
LEVEL = {"H": 5, "M": 3, "L": 1}
DOWNSTEP = "ꜜ"
BREATHY, CREAKY, NASAL = "̤", "̰", "̃"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def segments(word: str) -> list[tuple[str, str]]:
    """A phonemic word as (segment, tones) pairs; tones only on vowels (H, L, M, HL, LH, or '!H'
    for a downstepped H)."""
    s = unicodedata.normalize("NFD", word)
    out, i, down = [], 0, False
    while i < len(s):
        if s[i] == DOWNSTEP:
            down, i = True, i + 1
            continue
        if s[i] in VOWELS:
            v, i = s[i], i + 1
            tone = ""
            while i < len(s) and unicodedata.combining(s[i]):
                tone = TONES.get(s[i], tone)
                i += 1
            out.append((v, ("!" if down and "H" in tone else "") + tone))
            continue
        c = next((c for c in CONSONANTS if s.startswith(unicodedata.normalize("NFD", c), i)), None)
        if c is None:
            raise ValueError(f"not in the inventory: {s[i]!r} in {word}")
        out.append((c, ""))
        i += len(unicodedata.normalize("NFD", c))
    return out


def check(word: str):
    """Raise if a word breaks the phonotactics (inventory, syllable shapes, homorganic NC)."""
    segs = [s for s, _ in segments(word)]
    shape = "".join("V" if s in VOWELS else "C" for s in segs)
    allowed = {"CVC", "CVVC", "CV", "CVV", "CVCV", "CVVCV", "CVCCV", "CVVCCV", "CVCVCV", "CVCCVCV"}
    assert shape in allowed, (word, shape)
    for a, b in zip(segs, segs[1:]):
        if a in NASALS and b not in VOWELS:
            assert b in HOMORGANIC[a], (word, a, b)
    if shape.endswith("C"):
        assert segs[-1] in NASALS, word


def phonetic_word(word: str) -> str:
    segs = segments(word)
    out = []
    i = 0
    while i < len(segs):
        seg, _ = segs[i]
        if seg not in VOWELS:
            nxt = segs[i + 1][0] if i + 1 < len(segs) else ""
            if seg in VELARS and nxt in ROUND | HIGH_FRONT:
                mark = "ʷ" if nxt in ROUND else "ʲ"
                seg = seg[0] + mark + seg[1:]
            out.append(seg)
            i += 1
            continue
        long = i + 1 < len(segs) and segs[i + 1][0] == seg
        onset = segs[i - 1][0] if i > 0 and segs[i - 1][0] not in VOWELS else ""
        last = i + (2 if long else 1) >= len(segs)
        mark = ""
        if "ʰ" in onset:
            mark = BREATHY
        elif onset in GLOTTAL:
            mark = CREAKY
        elif last and onset in NASALS:
            mark = NASAL
        out.append(seg + mark + ("ː" if long else ""))
        i += 2 if long else 1
    return "".join(out)


def phonetic(form: str) -> str:
    return nfc(" ".join(phonetic_word(w) for w in form.split()))


class Register:
    """Downdrift across an utterance (Josh, 25 October): pitch never rises from a low back to the
    top. H starts at 5 and M at 3; each H or M that follows an L, and each downstep, lowers the
    register a step: H 5 > 4 > 3, M 3 > 3 > 2 (never lower). L is always 1."""

    def __init__(self):
        self.drops = 0
        self.after_low = False

    def level(self, tone: str) -> int:
        down = tone.startswith("!")
        tone = tone.lstrip("!")
        if tone == "L":
            self.after_low = True
            return LEVEL["L"]
        if self.after_low or down:
            self.drops = min(2, self.drops + 1)
            self.after_low = False
        high = LEVEL["H"] - self.drops
        return high if tone == "H" else (LEVEL["M"] if self.drops < 2 else LEVEL["M"] - 1)


def vowel_tones(tone: str) -> list[str]:
    """One vowel's tone as a list of levels' names: H, L, M, '!H', or a contour (HL, LH)."""
    down = tone.startswith("!")
    t = tone.lstrip("!")
    parts = [t] if t in LEVEL else [t[0], t[1]]
    if down:
        parts[0] = "!" + parts[0]
    return parts


def pitch_of(form: str) -> str:
    """The Pitch field from the tones: one syllable per vowel nucleus, with downdrift."""
    reg = Register()
    sylls = []
    for word in form.split():
        segs = segments(word)
        i = 0
        while i < len(segs):
            seg, tone = segs[i]
            if seg not in VOWELS:
                i += 1
                continue
            tones = [tone]
            if i + 1 < len(segs) and segs[i + 1][0] == seg:
                tones.append(segs[i + 1][1])
                i += 1
            i += 1

            if len(tones) == 2:                      # a long vowel: a long step between its halves
                first = vowel_tones(tones[0])
                second = vowel_tones(tones[1]) if tones[1] else [first[-1].lstrip("!")]
                a = reg.level(first[0])
                if len(first) == 2:
                    reg.level(first[1])
                b = reg.level(second[-1])
                sylls.append(f"{a}:{b}")
            else:
                sylls.append("".join(str(reg.level(x)) for x in vowel_tones(tone)))
    return phonetic_pitch(pitch.normalise(" ".join(sylls)))


def phonetic_pitch(text: str) -> str:
    """Josh's phonetic detail (25 October): a short syllable's level is written twice (5 -> 55),
    and an utterance ending on a low (1 or 2) falls a step further at the end (1 -> 10, 2 -> 21)."""
    sylls = text.split()
    for i, s in enumerate(sylls):
        if s.isdigit() and len(s) == 1:
            sylls[i] = s * 2
    if sylls and sylls[-1][-1] in "12":
        last = sylls[-1]
        if len(last) == 2 and last[0] == last[1]:           # a doubled level: the fall replaces the copy
            last = last[0]
        sylls[-1] = last + str(int(last[-1]) - 1)
    return " ".join(sylls)


def tone_melody(form: str) -> str:
    """H, L, LH or HL from the tones (None if there's an M or another melody)."""
    seq = []
    for word in form.split():
        for seg, t in segments(word):
            for x in (t.lstrip("!") if t not in ("HL", "LH") else list(t)):
                if x and (not seq or seq[-1] != x):
                    seq.append(x)
    melody = "".join(seq)
    return melody if melody in ("H", "L", "LH", "HL") else None


# ---------------------------------------------------------------------------------------------
# Morphology
# ---------------------------------------------------------------------------------------------

def ends_in_vowel(form: str) -> bool:
    return segments(form.split()[-1])[-1][0] in VOWELS


def prefix(person: str) -> str:
    """The pronoun's first syllable (CV, with its tone)."""
    form = dict((p, f) for p, f, *_ in PRONOUNS)[person]
    segs = unicodedata.normalize("NFD", form)
    cut = next(i for i, ch in enumerate(segs) if ch in VOWELS)
    end = cut + 1
    while end < len(segs) and unicodedata.combining(segs[end]):
        end += 1
    return nfc(segs[:end])


def suffix(root: str, after_c: str, after_v: str) -> str:
    return root + (after_v if ends_in_vowel(root) else after_c)


def inflection_class(root: str) -> str:
    return "II" if ends_in_vowel(root) else "I"


# ---------------------------------------------------------------------------------------------
# The text, its clipped utterances and the consent form (Josh, 25 October)
# ---------------------------------------------------------------------------------------------

TEXT_TITLE = "The man and the lion"
TEXT_DATE = "2026-10-25"
# Josh's recording and TextGrid (Soundfiles/Texts), one line per interval: Phonemic, Morphemes, Translation
TEXT_LINES = [
    ("ɲàmá gàanà wɛ́jànɛ̀ bɛ̄ɛŋ", "today man 3SG.A-take-PST spear", "Today the man took a spear."),
    ("wɛ́ɲɔ̄ɔrɛ̀ ŋɔ́ɔɲ dɛ̀ɛ́", "3SG.A-see-PST lion here", "He saw a lion here."),
    ("ŋɔ́ɔɲ dʊ́ŋ ɗɪ̄ɪ", "lion big COP", "It was a big lion."),
    ("ŋɔ́ɔɲ wɛ́tʌ̄ŋɛ̀ dʌ́ʌmà ɓɪ̀ɪ", "lion 3SG.A-eat-PST goat-PL two", "The lion ate two goats."),
    ("gàanà wɛ́lɔ̄ɔlɛ̀rɛ̀ tʰʊ̀ŋà", "man 3SG.A-call-PST child-PL", "The man called the children."),
    ("tʰʊ̀ŋà kɪ́ɓɛ́ɛŋɛ̀ kɔ̀ɔlɔ́nà", "child-PL 3PL.A-carry-PST stone-PL", "The children carried stones."),
    ("gàanà wɛ́βàdárɛ̀ kɔ̀ɔlɔ́", "man 3SG.A-throw-PST stone", "The man threw a stone."),
    ("wɛ́rɛ̀ɛmɛ̀ ŋɔ́ɔɲ", "3SG.A-kill-PST lion", "He killed the lion."),
    ("dɛ̄nzɪ́ wɛ́t͡sʊ̀mbàrɛ̀ rɪ̀ɪŋ", "woman 3SG.A-cook-PST meat", "The woman cooked the meat."),
    ("tʌ́dɔ̄tʌ̄ŋ ŋɔ́ɔɲ rɪ̀ɪŋ ɲàmá", "1PL.A-FUT-eat lion meat today", "“We will eat lion meat today.”"),
]
# lines clipped as utterances (1-based), with the lemmas (by gloss) each is linked to
CLIPS = {3: ["lion", "big"], 4: ["lion", "eat", "goat", "two"], 10: ["eat", "lion", "meat", "today"]}
TIERS = ["Phonetic", "Phonemic", "Pitch", "Morphemes", "Translation", "Comment"]
CONSENT = "Documentation/DML consent form.pdf"


def add_text(db) -> bool:
    """T001, Josh's recording of the text with its TextGrid, and its lines 3, 4 and 10 clipped as
    utterances (as Clip as utterance does). Nothing is added unless both files are in Soundfiles/Texts."""
    from lemmatrix import textgrid as tgmod
    from lemmatrix.model import ClipSource, Text, TierMapping, TierRule
    if db.text_by_ref("T001"):
        return False
    text = Text(ref="T001", file_label=TEXT_TITLE, date=TEXT_DATE, participants=[SPEAKER],
                researchers=["JJA"], locations=["NOWH"])
    text.set("Title", TEXT_TITLE)
    text.set("Genre", "folktale")
    text.set("Status", "analyzed")
    text.tiers = TierMapping("Phonetic", [TierRule(n, n, "en" if n == "Translation" else "") for n in TIERS])
    text.file = db.expected_text_name(text, ".wav")
    text.textgrid = db.expected_text_name(text, ".TextGrid")
    folder = storage.text_folder(db)
    wav, grid = folder / text.file, folder / text.textgrid
    if not (wav.exists() and grid.exists()):
        return False
    db.texts.append(text)
    lines = tgmod.read_lines(grid, text.tiers, SPEAKER)
    modified = tgmod.modified(grid)
    out = storage.utterance_folder(db)
    out.mkdir(parents=True, exist_ok=True)
    pad = db.settings.clip_padding / 1000.0
    length = audio.duration(wav)
    by_gloss = {e.multi.get("Gloss", {}).get("en"): e for e in db.entries}
    for number, glosses in CLIPS.items():
        ln = lines[number - 1]
        words = ln.values.get("Translation:en", "")
        u = db.new_utterance(db.suggest_utterance_reference("U"),
                             " ".join(words.strip("“”.").split()[:6]), SPEAKER, TEXT_DATE)
        for key, value in ln.values.items():
            name, _, lang = key.partition(":")
            f = db.settings.token_field(name)
            if f is not None:
                u.token.set(name, value, (lang or "en") if f.multilingual else None, f.multilingual)
        u.source = ClipSource(text.id, ln.start, ln.end, dict(ln.copied), modified)
        u.lemmas = [by_gloss[g].id for g in glosses]
        u.token.file = db.expected_filename(u, u.token)
        if not (out / u.token.file).exists():
            audio.clip_wav(wav, out / u.token.file, max(0.0, ln.start - pad), min(length, ln.end + pad),
                           SPEAKER, TEXT_DATE)
        db.utterances.append(u)
    return True


def consent_form(db) -> None:
    """Dzosho Mofo Lakanoro's (invented) signed consent form, as a PDF in Documentation."""
    path = Path(db.path).parent / CONSENT
    db.metadata.participant(SPEAKER).consent = CONSENT
    if path.exists():
        return
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841 (fonts need an application)
    path.parent.mkdir(parents=True, exist_ok=True)
    box = "&#9746;"
    html = f"""
<div style="font-family:'DejaVu Serif'; font-size:10.5pt">
<p style="text-align:center; color:#a33; font-size:9pt"><b>SAMPLE DATA. Invented for the Lemmatrix sample
database: no real person, place or institution.</b></p>
<h2 style="text-align:center; margin-bottom:0">University of Wagandha</h2>
<p style="text-align:center; margin-top:2px">Department of Language Documentation</p>
<h3 style="text-align:center">Informed consent: recording the Sample language (LXX, Sample variety VXX)</h3>
<p><b>Researcher:</b> Joshua J Alexander (JJA)<br><b>Participant:</b> Dzosho Mofo Lakanoro (DML)<br>
<b>Place:</b> Nowhero, Whero State, Wagandha<br><b>Funded by:</b> University of Wagandha</p>
<p>The researcher has explained, in a language I understand, that this project records words, sentences
and stories in my language so that they can be studied and kept for the future. I understand that taking
part is my choice, that I may stop at any time, and that I may ask for my recordings to be withdrawn.</p>
<p>{box} I agree to be recorded saying words, sentences and stories.<br>
{box} I agree that my name may be given with the recordings and the data (<i>identifiable</i>).<br>
{box} I agree that my recordings may be shared with other researchers and in an archive (<i>audio sharing</i>).<br>
{box} I agree that the transcriptions and translations may be published.</p>
<br>
<table width="100%" cellpadding="4">
<tr><td width="50%">Participant's signature:<br><span style="font-family:'DejaVu Serif'; font-style:italic;
font-size:20pt; color:#1d3b8f">Dzosho M. Lakanoro</span><br>Date: 20 October 2026</td>
<td width="50%">Researcher's signature:<br><span style="font-family:'DejaVu Serif'; font-style:italic;
font-size:20pt; color:#1d3b8f">J. J. Alexander</span><br>Date: 20 October 2026</td></tr></table>
<br><p style="font-size:8pt; color:#666">Lemmatrix sample data © 2026 Joshua A. G. Smolders, all rights
reserved (SAMPLES.md). Any resemblance to any real person, place or institution is a complete coincidence.</p>
</div>"""
    writer = QPdfWriter(str(path))
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(20, 20, 20, 20),
                                     QPageLayout.Millimeter))
    writer.setResolution(96)
    writer.setTitle("Consent form: Dzosho Mofo Lakanoro (sample data)")
    writer.setCreator("Lemmatrix sample (samples/make_sample.py)")
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print_(writer)


# ---------------------------------------------------------------------------------------------
# Building the database
# ---------------------------------------------------------------------------------------------

def hum(pitch_text: str) -> np.ndarray:
    """A short hum following the pitch, so playback has something to play."""
    out = []
    step = 0.09
    for item in pitch.parse(pitch_text) or pitch.parse("33"):
        if item == pitch.PAUSE:
            out.append(np.zeros(int(RATE * 0.1)))
            continue
        times = np.concatenate([[0], np.cumsum(item.steps)]) * step
        n = max(1, int(RATE * times[-1]))
        levels = np.interp(np.linspace(0, times[-1], n), times, item.points)
        freq = 110 * 2 ** ((levels - 1) / 8)
        phase = 2 * np.pi * np.cumsum(freq) / RATE
        env = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (RATE * 0.015))
        out.append(0.3 * env * (np.sin(phase) + 0.3 * np.sin(2 * phase)))
        out.append(np.zeros(int(RATE * 0.025)))
    return np.concatenate(out)


def sample_metadata(md) -> None:
    """The sample's invented people, places and funder (Josh, 25 October): none of them is real."""
    from lemmatrix.model import Location, Person, Support
    md.author = "Joshua J Alexander"
    md.researchers = [Person.researcher("JJA", "Joshua J Alexander")]
    md.participants = [Person("DML", "Dzosho Mofo Lakanoro", identifiable=True, audio_sharing=True)]
    md.locations = [
        Location("Canada", "CA", children=[
            Location("British Columbia", "BC", children=[Location("Langley", "LANG")])]),
        Location("Wagandha", "WG", NOT_REAL, children=[
            Location("Whero State", "WHS", NOT_REAL, children=[Location("Nowhero", "NOWH", NOT_REAL)])])]
    md.support = [Support("University of Wagandha", "", "the sample language's documentation")]


NOT_REAL = "Not a real place; any resemblance is coincidental."


class Builder:
    def __init__(self):
        self.db = db = new_database()
        md = db.metadata
        sample_metadata(md)
        md.language_code, md.language_name = "LXX", "Sample language"
        md.variety_code, md.variety_name = "VXX", "Sample variety"
        md.name = "Sample"
        md.description = ("Invented sample data for trying out Lemmatrix: not a real language. "
                          "Any resemblance to any living language is a complete coincidence. "
                          "© Joshua A. G. Smolders, all rights reserved (SAMPLES.md). "
                          "Built by samples/make_sample.py.")
        for name, carrier in FRAMES.items():
            db.settings.tags.tag(name).description = carrier
        self.folder = HERE / "Soundfiles" / "Tokens"
        db.path = str(HERE / "Sample.xml")
        self.nouns = {g: f for _, g, f in NOUNS}
        # Built on the EACW (Josh, 23 October: the samples too, to try its tools on): each lemma takes
        # the item its gloss names, or the next own reference in its section where the list has none
        md.wordlist_base = wl.EACW
        self.taken: set[str] = set()

    def ref(self, gloss, letter, verb=None):
        return wl.sample_reference(self.db, gloss, letter, self.taken, verb)

    def token(self, e, tags, form, morphemes, translation, record):
        t = self.db.new_token(e, tags, speaker=SPEAKER, date=DATE) if tags else e.tokens[0]
        t.set("Phonetic", phonetic(form))
        t.set("Phonemic", nfc(form))
        t.set("Pitch", pitch_of(form))
        t.set("Morphemes", morphemes)
        t.set("Translation", translation, "en")
        if tags:
            e.tokens.append(t)
        if record:
            t.file = self.db.expected_filename(e, t)
            if not (self.folder / t.file).exists():   # Josh's own recordings are kept; a hum only fills a gap
                audio.write_wav(self.folder / t.file, hum(t.get("Pitch")), RATE, 16, artist=t.speaker, date=t.collected)
        return t

    def entry(self, ref, form, gloss, wc, classes=True):
        for w in form.split():
            check(w)
        e = self.db.new_entry(ref, nfc(form), gloss, wc, speaker=SPEAKER, date=DATE)
        if classes:
            if (m := tone_melody(form)):
                e.set("ToneClass", m)
        self.db.entries.append(e)
        return e

    def noun(self, letter, gloss, form):
        e = self.entry(self.ref(gloss, letter, False), form, gloss, "NOUN")
        e.set("InflectionClass", inflection_class(form))
        rec = gloss in RECORDED_IN_FULL
        pl = suffix(form, "à", "nà")
        pl_m = f"{gloss}-PL"
        plural = gloss if gloss in ("sheep", "fish") else ("people" if gloss == "person" else
                                                          {"man": "men", "woman": "women", "child": "children",
                                                           "tooth": "teeth", "foot": "feet", "knife": "knives",
                                                           "leaf": "leaves", "catfish": "catfish"}.get(gloss, gloss + "s"))
        self.token(e, [], form, gloss, gloss, True)
        self.token(e, ["Plural"], pl, pl_m, plural, rec)
        art = "" if gloss in MASS else ("an " if gloss[0] in "aeiou" else "a ")
        self.token(e, ["Frame 1"], f"{form} {COPULA}", f"{gloss} COP", f"it is {art}{gloss}", rec)
        self.token(e, ["Frame 2"], f"{SEE_1SG} {form}", f"1SG.A-see {gloss}", f"I see the {gloss}", rec)
        for number, stem, m_stem, eng in (("Singular", form, gloss, gloss), ("Plural", pl, pl_m, plural)):
            for person, _, _, poss in PRONOUNS:
                self.token(e, [number, f"{person}.POSS"], prefix(person) + stem, f"{person}.POSS-{m_stem}",
                           f"{poss} {eng}", rec)

    def verb(self, gloss, root, past, obj):
        e = self.entry(self.ref(gloss, "V", True), root, gloss, "VERB")
        e.set("InflectionClass", inflection_class(root))
        rec = gloss in RECORDED_IN_FULL
        self.token(e, [], root, gloss, f"to {gloss}", True)
        imp = suffix(root, "á", "rá")
        for neg in (False, True):
            for person, pre, eng in (("2SG", "", "(sg)"), ("2PL", prefix("2PL"), "(pl)")):
                form = ("kʌ̀ " if neg else "") + pre + imp
                morph = ("NEG " if neg else "") + (f"{person}.A-" if pre else "") + f"{gloss}-IMP"
                tr = (f"don't {gloss}! {eng}" if neg else f"{gloss}! {eng}")
                self.token(e, ["Imperative", f"{person}.A"] + (["Negative"] if neg else []), form, morph, tr, rec)
        o = self.nouns[obj]
        for person, _, subj, _ in [p for p in PRONOUNS if p[0] in ("3SG", "3PL")]:
            pre = prefix(person)
            s3 = "s" if person == "3SG" else ""
            third = gloss
            if person == "3SG":
                third = (gloss[:-1] + "ies" if gloss.endswith("y") else
                         gloss + ("es" if gloss.endswith(("sh", "ch", "ss")) else s3))
            for tense, form, morph, tr in (
                    ("Present", pre + root, f"{person}.A-{gloss}", f"{subj} {third} the {obj}"),
                    ("Past", pre + suffix(root, "ɛ̀", "rɛ̀"), f"{person}.A-{gloss}-PST", f"{subj} {past} the {obj}"),
                    ("Future", pre + "dɔ̄" + root, f"{person}.A-FUT-{gloss}", f"{subj} will {gloss} the {obj}")):
                self.token(e, [tense, f"{person}.A", "NP.O"], f"{form} {o}", f"{morph} {obj}", tr, rec)

    def simple(self, letter, gloss, form, wc, ref=None, morphemes=None):
        e = self.entry(ref or self.ref(gloss, letter, False), form, gloss, wc, classes=False)
        self.token(e, [], form, morphemes or gloss, gloss, True)
        return e

    def matrices(self):
        s = self.db.settings

        def S(*tags):
            return mx.Spec(frozenset(tags))
        poss = [f"{p}.POSS" for p, *_ in PRONOUNS]
        s.matrices = [
            mx.MatrixConfig("Nouns: citation, plural and frames", mx.LEMMA_TAG,
                            x=[mx.Spec.citation(), S("Plural"), S("Frame 1"), S("Frame 2")]),
            mx.MatrixConfig("Nouns: number and possession", mx.TAG_TAG,
                            y=[S("Singular"), S("Plural")], x=[S(p) for p in poss]),
            mx.MatrixConfig("Verbs: imperatives", mx.LEMMA_TAG,
                            x=[mx.Spec.citation(), S("Imperative", "2SG.A"), S("Imperative", "2PL.A"),
                               S("Imperative", "2SG.A", "Negative"), S("Imperative", "2PL.A", "Negative")]),
            mx.MatrixConfig("Verbs: person and tense", mx.TAG_TAG,
                            y=[S("3SG.A", "NP.O"), S("3PL.A", "NP.O")],
                            x=[S("Present"), S("Past"), S("Future")]),
        ]

    def build(self):
        # Soundfiles/ is never deleted: it holds Josh's recordings of the sample (SAMPLES.md)
        for letter, gloss, form in NOUNS:
            self.noun(letter, gloss, form)
        for v in VERBS:
            self.verb(*v)
        for i, (person, form, eng, _) in enumerate(PRONOUNS):
            self.simple("R", eng, form, "PRONOUN", ref=f"R{person}")
        for i, (gloss, form, morphemes) in enumerate(NUMBERS):
            self.simple("Q", gloss, form, "QUANT", ref=f"Q{i + 1:03d}", morphemes=morphemes)   # Q + the number
        for gloss, form in ADJECTIVES:
            self.simple("P", gloss, form, "ADJECTIVE")
        for gloss, form in ADVERBS:
            self.simple("N", gloss, form, "ADVERB")
        wl.link_as_eacw(self.db)
        add_text(self.db)
        consent_form(self.db)
        self.matrices()
        storage.save(self.db, HERE / "Sample.xml", backup=False)
        if not workspace.path_for(HERE / "Sample.xml").exists():    # Josh's own setup is kept (25 October)
            workspace.save(workspace.Workspace(), self.db)
        shutil.rmtree(HERE / "Backups", ignore_errors=True)
        return self.db


def main():
    db = Builder().build()
    tokens = sum(len(e.tokens) for e in db.entries)
    print(f"Wrote {HERE / 'Sample.xml'}: {len(db.entries)} lemmas, {tokens} tokens, "
          f"{len(list((HERE / 'Soundfiles' / 'Tokens').glob('*.wav')))} recordings.")


if __name__ == "__main__":
    main()
