# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The sample databases are all rights reserved (SAMPLES.md), stated wherever they ship."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESERVED = ("samples/make_sample.py", "samples/make_elicit_test.py")


def test_the_scripts_that_build_the_samples_are_reserved():
    for name in RESERVED:
        head = (ROOT / name).read_text(encoding="utf-8").splitlines()[:2]
        assert head[0] == "# SPDX-License-Identifier: LicenseRef-Lemmatrix-Samples", name
        assert "All rights reserved: see SAMPLES.md." in head[1], name
    test_db = (ROOT / "samples/make_test_database.py").read_text(encoding="utf-8")
    assert test_db.startswith("# SPDX-License-Identifier: AGPL-3.0-or-later")     # Test-300 stays AGPL


def test_samples_md_names_everything_it_covers():
    text = (ROOT / "SAMPLES.md").read_text(encoding="utf-8")
    assert "All rights reserved" in text
    for name in RESERVED + ("samples/Sample.xml", "samples/Elicit test/", "LicenseRef-Lemmatrix-Samples"):
        assert name in text, name


def test_the_terms_are_pointed_to_where_the_licence_is_stated():
    for name in ("NOTICE.md", "README.md", "THIRD-PARTY.md", "DESIGN.md"):
        assert "SAMPLES.md" in (ROOT / name).read_text(encoding="utf-8"), name
    z = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert "SAMPLES.md" in z["notes"]
    from lemmatrix.ui.main_window import about_text
    assert "SAMPLES.md" in about_text()
