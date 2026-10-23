# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Lemmatrix's own Google Cloud project, for ɛλicit through Google Drive (IDEAS.md idea 19, stage 2).

These are public on purpose. A desktop app's OAuth "client secret" can't be kept secret (anyone
can read it out of the program), and Google doesn't treat it as one; what protects a researcher's
Drive is their own sign-in. The API key only lets the ɛλicit page (and nothing else: it is
restricted to https://smojos.github.io/ and the Drive API) read the files a request shares by link.

Registered by Josh on 21 October 2026 (Google Cloud project "lemmatrix"). With these empty, requests can only
be sent as zip files.
"""

GOOGLE_CLIENT_ID = "735873789478-fishtbb78nhqmn7puq99kpeobpe3bvgr.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
GOOGLE_API_KEY = "AIzaSyDeSFwuG1pKnG4D1nuaEe0PA-H8SFsWgz8"


def google_ready() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_API_KEY)
