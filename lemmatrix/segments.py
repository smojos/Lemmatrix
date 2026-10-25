# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The segment scratchpad's soundfiles (IDEAS.md idea 46, designed with Josh 24 October).

Whatever is typed in a Segments pad is a **sequence**, and any string is a sequence of its own
(Josh: questions of segmental equivalency belong to the analysis phase), normalised (NFC) and
trimmed; the exceptions are the tie bar (t͡s and ts call the same thing; Josh, 24 October) and a few
easily typed alternatives (g calls ɡ; ALTERNATIVES, Josh, 25 October). Two kinds of soundfile answer to a sequence:

- **The database's own**, recorded in the phonetics scratchpad into `Soundfiles/Segments` and found by
  their names alone (like Images: nothing in the database file), named
  `{language}-{variety}-{speaker}_{sequence}.wav` (`LXX-VXX-SP1_ʌ.wav`; with no speaker
  `LXX-VXX_ʌ.wav`). A participant's are data; a researcher's survive a Full backup but go into no
  archive (Josh).
- **Lemmatrix's own** (`lemmatrix/ipa/`): the 126 soundfiles of Wikimedia Commons' General
  phonetics page, unchanged, each under its own licence (`credits.tsv`, LICENSE-IPA.md). Never
  copied into a database or an archive.

The order a pad plays them in: the Current Session speaker's recording, then one with no speaker,
then any other speaker's (participants in the lists' order, then researchers), then Lemmatrix's own.
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import layout
from .model import FORBIDDEN_CHARS, forbidden_in, nfc

NATIVE_FOLDER = Path(__file__).parent / "ipa"
EXTENSIONS = (".wav", ".flac", ".ogg", ".oga")
COMMONS = "Wikimedia Commons"


@dataclass(frozen=True)
class Voice:
    """One soundfile for a sequence."""
    path: Path
    sequence: str
    speaker: str = ""          # a participant's or researcher's code; "" for none
    native: bool = False       # Lemmatrix's own (Commons)
    credit: str = ""           # Lemmatrix's own: "Peter Isotalo · CC BY-SA 3.0 · Wikimedia Commons"
    name: str = ""             # Lemmatrix's own: the sound's name ("Voiced bilabial fricative")

    def label(self) -> str:
        """How the voice is named in the pad's menu and hover."""
        if self.native:
            return f"Lemmatrix: {self.credit}"
        return self.speaker or "no speaker"


def norm(text: str) -> str:
    """A sequence as typed, made comparable: NFC, trimmed; nothing else."""
    return nfc((text or "").strip())


TIE_BARS = "\u0361\u035c"      # ◌͡◌ above and ◌͜◌ below: t͡s and ts call the same thing (Josh, 24 October)


# Characters typed for an IPA one that is hard to type: each calls the same soundfiles as its IPA
# symbol, in Lemmatrix's own and in recordings named either way (Josh, 25 October: hardly any
# linguist types the IPA's ɡ, U+0261, so the ordinary g, U+0067, calls it). Names keep what was typed.
ALTERNATIVES = {
    "g": "\u0261",            # g → ɡ
}


def key(text: str) -> str:
    """What a sequence is looked up by: as typed (normalised), but with tie bars left out, so
    `ts` finds Lemmatrix's `t͡s` and a recording named either way (Josh: the tie bar doesn't type
    easily), and each ALTERNATIVES character as its IPA symbol (`g` finds `ɡ`). Names keep what
    was typed."""
    return "".join(ALTERNATIVES.get(c, c) for c in norm(text) if c not in TIE_BARS)


def problem(text: str) -> str:
    """The characters a sequence can't have (they can't be in file names); "" if none."""
    return forbidden_in(text or "")


@lru_cache(maxsize=1)
def native_index() -> dict[str, Voice]:
    """Lemmatrix's own soundfiles by sequence (their IPA symbol), from credits.tsv."""
    out: dict[str, Voice] = {}
    tsv = NATIVE_FOLDER / "credits.tsv"
    if not tsv.exists():
        return out
    with open(tsv, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            seq = norm(row["ipa"])
            path = NATIVE_FOLDER / row["soundfile"]
            if seq and key(seq) not in out and path.exists():
                out[key(seq)] = Voice(path, seq, native=True,
                                 credit=f"{row['recorded_by']} · {row['licence']} · {COMMONS}",
                                 name=row["commons_title"].rsplit(".", 1)[0])
    return out


def native(sequence: str) -> Voice | None:
    return native_index().get(key(sequence))


@lru_cache(maxsize=1)
def callers() -> dict[str, str]:
    """The alternative callers (`ipa/alternatives.tsv`, Josh's list of 25 October): an easily typed
    sequence (its key) → the IPA symbol it calls: `sh` → ʃ, `b'` → ɓ, `!` → ǃ."""
    out: dict[str, str] = {}
    tsv = NATIVE_FOLDER / "alternatives.tsv"
    if not tsv.exists():
        return out
    with open(tsv, encoding="utf-8", newline="") as f:
        rows = csv.DictReader((ln for ln in f if not ln.startswith("#")), delimiter="\t")
        for row in rows:
            ipa, alt = norm(row.get("ipa", "")), norm(row.get("alternative", ""))
            if ipa and alt and key(alt) != key(ipa):
                out.setdefault(key(alt), ipa)
    return out


def called(sequence: str) -> str:
    """The IPA symbol a sequence typed on its own stands for (`sh` → `ʃ`), or "" when it is none.
    Only the whole sequence counts: `sha` calls nothing of ʃ's (Josh, 25 October)."""
    return callers().get(key(sequence), "")


def folder(db) -> Path:
    """The database's `Soundfiles/Segments`."""
    return layout.segments_folder(db.path)


def prefix(db) -> str:
    """The language and variety codes that start a segment soundfile's name (LXX-VXX)."""
    md = db.metadata
    return "-".join(c for c in (md.language_code, md.variety_code) if c)


def filename(db, sequence: str, speaker: str = "") -> str:
    """`{language}-{variety}-{speaker}_{sequence}.wav`; empty parts drop their separator."""
    head = "-".join(c for c in (prefix(db), speaker) if c)
    seq = norm(sequence)
    return (f"{head}_{seq}" if head else seq) + ".wav"


def _people(db) -> list[str]:
    return [p.code for p in db.metadata.participants] + [p.code for p in db.metadata.researchers]


def parse(db, name: str, extra: tuple = ()) -> tuple[str, str] | None:
    """(sequence, speaker) for a file name in Segments; None if it isn't a soundfile.

    The name's start is the database's codes, then an optional -{speaker} known to the lists, then
    _ and the sequence. A name with other codes in front (the language's code was changed) still
    gives its speaker when the last part before the _ is a known code; any other soundfile there
    counts as a sequence of its own name, with no speaker."""
    p = Path(name)
    if p.suffix.lower() not in EXTENSIONS:
        return None
    stem = nfc(p.stem)
    people = _people(db) + list(extra)          # extra: codes just renamed away
    pre = prefix(db)
    if "_" in stem:
        head, seq = stem.split("_", 1)
        if seq:
            if pre and head == pre:
                return seq, ""
            if pre and head.startswith(pre + "-") and head[len(pre) + 1:] in people:
                return seq, head[len(pre) + 1:]
            if not pre and head in people:
                return seq, head
            last = head.rsplit("-", 1)[-1]
            if "-" in head and last in people:
                return seq, last
            if pre:                                 # codes of their own in front: no speaker
                return seq, ""
    return stem, ""


_LISTED: dict = {}                          # what recordings() found, by everything it depends on


def recordings(db, extra: tuple = ()) -> list[Voice]:
    """The database's segment soundfiles (extra: other speaker codes to recognise). Remembered
    until the folder, the codes or the people change: the phonetics scratchpad asked several
    times per keystroke, listing the folder each time (the audit, 25 October)."""
    out = []
    if not db.path:
        return out
    d = folder(db)
    try:
        key = (str(d), d.stat().st_mtime_ns, prefix(db), tuple(_people(db)), tuple(extra))
    except OSError:
        return out
    hit = _LISTED.get(key)
    if hit is not None:
        return list(hit)
    try:
        files = sorted(d.iterdir())
    except OSError:
        return out
    for f in files:
        if not f.is_file():
            continue
        got = parse(db, f.name, extra)
        if got:
            out.append(Voice(f, norm(got[0]), got[1]))
    if len(_LISTED) > 32:
        _LISTED.clear()
    _LISTED[key] = list(out)
    return out


def voices(db, sequence: str, session_speaker: str = "") -> list[Voice]:
    """Every soundfile for a sequence, in the order a pad plays them: the session speaker's,
    one with no speaker, the other speakers' (participants in the lists' order, then
    researchers, then anyone else), then Lemmatrix's own."""
    seq = key(sequence)
    if not seq:
        return []
    own = [v for v in recordings(db) if key(v.sequence) == seq]
    order = {c: i for i, c in enumerate(_people(db))}

    def rank(v: Voice):
        if session_speaker and v.speaker == session_speaker:
            return (0, 0, v.path.name)
        if not v.speaker:
            return (1, 0, v.path.name)
        return (2, order.get(v.speaker, len(order)), v.path.name)
    out = sorted(own, key=rank)
    # An alternative caller (`sh`) also calls the IPA symbol's soundfiles (ʃ), after any recording
    # of the sequence as typed: a recording named `th` (an aspirated t) is never taken for θ.
    ipa = called(sequence)
    if ipa:
        out += sorted((v for v in recordings(db) if key(v.sequence) == key(ipa)), key=rank)
    nat = native(seq) or (native(ipa) if ipa else None)
    if nat is not None:
        out.append(nat)
    return out


def best(db, sequence: str, session_speaker: str = "") -> Voice | None:
    found = voices(db, sequence, session_speaker)
    return found[0] if found else None


def archived(db, v: Voice) -> bool:
    """Whether a segment soundfile goes into the Ethical archive: a participant's, with Audio
    sharing? selected. A researcher's isn't data (Josh: it survives a backup but not an archive),
    and one with no speaker can't be checked, so neither goes in."""
    p = db.metadata.participant(v.speaker) if v.speaker else None
    return bool(p and p.audio_sharing)


def rename_speakers(db, renames: dict[str, str]) -> list[tuple[str, str]]:
    """A person's code renamed in Edit → Lists: their segment soundfiles follow. Returns the
    (old, new) names; a name already taken is left as it is."""
    done = []
    if not renames or not db.path:
        return done
    for v in recordings(db, tuple(renames)):
        if v.speaker in renames and renames[v.speaker] != v.speaker:
            new = v.path.with_name(filename(db, v.sequence, renames[v.speaker]))
            if new.exists():
                continue
            try:
                v.path.rename(new)
            except OSError:
                continue
            done.append((v.path.name, new.name))
    return done


def copy_shared(db, target_folder: Path) -> tuple[int, int]:
    """The Ethical archive's segment soundfiles: participants' with Audio sharing?, into
    target_folder (Soundfiles/Segments of the archive). Returns (copied, left out)."""
    copied = left = 0
    for v in recordings(db):
        if archived(db, v):
            target_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(v.path, target_folder / v.path.name)
            copied += 1
        else:
            left += 1
    return copied, left


__all__ = ["Voice", "norm", "problem", "native", "native_index", "folder", "filename", "parse",
           "recordings", "voices", "best", "archived", "rename_speakers", "copy_shared",
           "FORBIDDEN_CHARS"]
