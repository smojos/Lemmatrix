# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Lemmatrix's own Google Cloud project, for ɛλicit through Google Drive (IDEAS.md idea 19, stage 2).

These are public on purpose. A desktop app's OAuth "client secret" can't be kept secret (anyone
can read it out of the program), and Google doesn't treat it as one; what protects a researcher's
Drive is their own sign-in. The API key only lets the ɛλicit page (and nothing else: it is
restricted to https://smojos.github.io/ and the Drive API) read the files a request shares by link.

Empty until Josh registers the project: then requests can only be sent as zip files.
"""

GOOGLE_CLIENT_ID = ""
GOOGLE_CLIENT_SECRET = ""
GOOGLE_API_KEY = ""


def google_ready() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_API_KEY)
