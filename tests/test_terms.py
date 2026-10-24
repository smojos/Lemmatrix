# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Lemmatrix's own terms, kept the same everywhere (DESIGN.md section 1, Terminology)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = (".py", ".pyw", ".md", ".svg", ".bat", ".sh", ".ps1", ".txt", ".cff", ".js", ".html", ".css")


def tracked_text_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        files = [ROOT / f for f in out.splitlines()]
    except (OSError, subprocess.CalledProcessError):      # not a git checkout: look at everything
        files = [p for p in ROOT.rglob("*") if ".git" not in p.parts]
    return [f for f in files if f.suffix in TEXT and f.is_file() and "data" not in f.relative_to(ROOT).parts]


def test_soundfile_is_one_word():
    """Written "soundfile(s)", never "sound file(s)" or "sound-file(s)" (Josh, 20 October)."""
    two_words = re.compile(r"\b[Ss]ound[ -]files?\b")
    found = []
    for f in tracked_text_files():
        if f.name == "test_terms.py":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if two_words.search(line):
                found.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not found, "Write soundfile as one word:\n" + "\n".join(found)


def test_tick_means_a_bug_only():
    """"Tick" is a bug (I found a tick!); a checkbox is selected or deselected (Josh, 24 October).
    Checks the program's own text (its strings, not names in the code) and the README and DESIGN.md."""
    import io
    import tokenize
    word = re.compile(r"\b(un)?tick(s|ed|ing)?\b", re.I)
    bug = re.compile(r"I found a tick!|a tick is a bug|a tick drawn in", re.I)
    found = []
    for f in tracked_text_files():
        rel = f.relative_to(ROOT)
        if f.suffix == ".py" and rel.parts[0] == "lemmatrix":
            src = f.read_text(encoding="utf-8")
            for t in tokenize.generate_tokens(io.StringIO(src).readline):
                if t.type != tokenize.STRING and t.type != getattr(tokenize, "FSTRING_MIDDLE", -1):
                    continue
                s = t.string
                if s.strip("'\"").lower() in ("tick", "ticked") or s.lstrip("rbfRBF").startswith(('"""', "'''")):
                    continue                     # an icon's or a field's name; docstrings are for coders
                if word.search(bug.sub("", s)):
                    found.append(f"{rel}:{t.start[0]}: {s.strip()[:100]}")
        elif f.name in ("README.md", "DESIGN.md"):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if word.search(bug.sub("", line)) and "A tick is a bug" not in line:
                    found.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not found, "Say selected / deselected (a tick is a bug):\n" + "\n".join(found)
