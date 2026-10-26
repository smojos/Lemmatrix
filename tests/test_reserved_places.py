# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's artwork and samples stay reserved (Josh, 26 October 2026).

ARTWORK.md and SAMPLES.md reserve folders and modules, so anything new put there is covered at
once. This test makes sure nothing slips outside them: every image, recording, PDF or TextGrid in
the repository must sit in a reserved place, or in one of the few places with terms of their own.
If it fails, move the file into a reserved folder; never widen OTHER_TERMS to let it through
(that would put the file under the AGPL)."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARTWORK = ("lemmatrix/resources/", "docs/elicit/")                       # ARTWORK.md
SAMPLES = ("samples/Soundfiles/", "samples/Documentation/", "samples/Whiteboard/",
           "samples/Elicit test/")                                         # SAMPLES.md
OTHER_TERMS = {
    "lemmatrix/ipa/": "Wikimedia Commons recordings, each under its own licence (LICENSE-IPA.md)",
    "tests/data/": "the prototype's synthetic test data (hums), AGPL",
}
MEDIA = {".svg", ".png", ".ico", ".gif", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
         ".wav", ".flac", ".mp3", ".ogg", ".oga", ".m4a", ".aac", ".opus", ".pdf", ".textgrid"}
SKIP = {".git", ".venv", "venv", "env", "__pycache__", "Backups", "build", "dist", "screenshots",
        ".pytest_cache", ".ruff_cache", ".mypy_cache"}

ARTWORK_CODE = {"lemmatrix/ui/icons.py", "lemmatrix/ui/whiteboard_art.py"}
SAMPLE_CODE = {"samples/make_sample.py", "samples/make_elicit_test.py"}


def _files() -> list[str]:
    """The repository's files, committed or not yet (ignored ones left out): git's list where git
    is at hand, else a walk of the folder."""
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return [line.strip().strip('"') for line in out.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    for folder, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in names:
            found.append(Path(folder, name).relative_to(ROOT).as_posix())
    return found


def test_every_image_and_recording_is_in_a_reserved_place():
    places = ARTWORK + SAMPLES + tuple(OTHER_TERMS)
    stray = [f for f in _files() if Path(f).suffix.lower() in MEDIA and not f.startswith(places)]
    assert not stray, ("Not covered by ARTWORK.md or SAMPLES.md (it would fall under the AGPL): "
                       + ", ".join(stray) + ". Move it into one of: " + ", ".join(ARTWORK + SAMPLES))


def test_the_terms_name_every_reserved_place():
    artwork = (ROOT / "ARTWORK.md").read_text(encoding="utf-8")
    samples = (ROOT / "SAMPLES.md").read_text(encoding="utf-8")
    for place in ARTWORK + tuple(ARTWORK_CODE):
        assert place in artwork, place
    for place in SAMPLES + tuple(SAMPLE_CODE):
        assert place in samples, place


def test_reserved_code_carries_its_header_and_is_named_in_its_terms():
    marks = {"LicenseRef-Lemmatrix-Artwork": ("ARTWORK.md", ARTWORK_CODE),
             "LicenseRef-Lemmatrix-Samples": ("SAMPLES.md", SAMPLE_CODE)}
    for mark, (doc, known) in marks.items():
        terms = (ROOT / doc).read_text(encoding="utf-8")
        for name in known:                      # the header can't quietly disappear
            first = (ROOT / name).read_text(encoding="utf-8").splitlines()[0]
            assert first == f"# SPDX-License-Identifier: {mark}", name
        for name in _files():                   # and a new reserved module must be named in the terms
            if name.endswith(".py") and not name.startswith("tests/"):
                path = ROOT / name
                if path.exists() and path.read_text(encoding="utf-8").startswith(f"# SPDX-License-Identifier: {mark}"):
                    assert name in terms, f"{name} is marked {mark} but {doc} doesn't name it"
