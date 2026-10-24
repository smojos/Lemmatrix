# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Help → I found a tick! and Request a feature: an email to Lemmatrix's support address.

Only the version and the operating system go into the message; nothing from the database. The
researcher may choose to attach the database's setup (setup_export.py: no data at all)."""

from __future__ import annotations

import platform
from urllib.parse import quote

from . import __version__

SUPPORT_EMAIL = "lemmatrix.support@gmail.com"


def system() -> str:
    return f"Lemmatrix {__version__}, {platform.system()} {platform.release()}, Python {platform.python_version()}"


def mailto(kind: str, attachment: str = "") -> str:
    """The mailto: link for a bug report ("bug") or a feature request ("feature"); attachment: the
    database's setup file to attach by hand (idea 50), named in the message so it isn't forgotten."""
    if kind == "bug":
        subject = f"Lemmatrix {__version__}: I found a tick!"
        body = ("What happened:\n\n\nWhat I was doing just before:\n\n\nWhat I expected:\n\n\n"
                f"---\n{system()}\n")
    else:
        subject = f"Lemmatrix {__version__}: feature request"
        body = ("What I'd like Lemmatrix to do:\n\n\nWhy it would help:\n\n\n"
                f"---\n{system()}\n")
    if attachment:
        body = body.replace("---\n", f"Attached: {attachment} (my database's setup: no data)\n\n---\n", 1)
    return f"mailto:{SUPPORT_EMAIL}?subject={quote(subject)}&body={quote(body)}"
