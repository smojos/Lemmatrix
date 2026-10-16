"""Starts Lemmatrix without a console window (used by the desktop shortcut).

If the packages need installing or updating, it hands over to
"Run Lemmatrix.bat" instead, which shows its progress and then starts Lemmatrix.
"""

import filecmp
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
stamp = ROOT / ".venv" / "requirements.installed"
if not stamp.exists() or not filecmp.cmp(ROOT / "requirements.txt", stamp, shallow=False):
    os.startfile(str(ROOT / "Run Lemmatrix.bat"))
    sys.exit(0)
sys.path.insert(0, str(ROOT))
from lemmatrix.__main__ import main  # noqa: E402

sys.exit(main())
