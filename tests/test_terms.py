# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
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
