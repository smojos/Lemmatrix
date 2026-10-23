# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""A crash inside Qt closes Lemmatrix with no message box; lemmatrix-crash.log keeps where it was
(Josh, 23 October: it closed silently while opening the sample database)."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def test_a_native_crash_is_written_to_the_crash_log(tmp_path):
    code = (f"import sys; sys.path.insert(0, {str(HERE)!r})\n"
            "from pathlib import Path\n"
            "import faulthandler, lemmatrix.__main__ as m\n"
            f"m._install_crash_log(Path({str(tmp_path / 'lemmatrix-errors.log')!r}))\n"
            "def opening_the_sample():\n"
            "    faulthandler._sigsegv()\n"
            "opening_the_sample()\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode != 0
    text = (tmp_path / "lemmatrix-crash.log").read_text(encoding="utf-8")
    assert "Segmentation fault" in text and "opening_the_sample" in text


def test_the_crash_log_starts_afresh(tmp_path):
    import lemmatrix.__main__ as m
    (tmp_path / "lemmatrix-crash.log").write_text("an old crash", encoding="utf-8")
    import faulthandler
    try:
        m._install_crash_log(tmp_path / "lemmatrix-errors.log")
        assert (tmp_path / "lemmatrix-crash.log").read_text(encoding="utf-8") == ""
    finally:
        faulthandler.enable()                  # back to the terminal, as pytest had it
        m._install_crash_log.file.close()
