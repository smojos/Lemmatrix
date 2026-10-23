# Third-party software

Lemmatrix is © 2026 Joshua A. G. Smolders and licensed under AGPL-3.0-or-later (see `LICENSE`); its artwork is not (see `ARTWORK.md`).
It doesn't include any of the libraries below: they are installed from PyPI when Lemmatrix
first runs (`requirements.txt`), each under its own licence.

| Library | Used for | Licence |
|---|---|---|
| [PySide6](https://pypi.org/project/PySide6/) (Qt for Python) | the windows and dialogues | LGPL-3.0 (or GPL-2.0 / GPL-3.0) |
| [NumPy](https://pypi.org/project/numpy/) | sound and pitch processing | BSD-3-Clause (and others) |
| [sounddevice](https://pypi.org/project/sounddevice/) | recording and playback | MIT |
| [SoundCard](https://pypi.org/project/SoundCard/) | recording computer audio | BSD-3-Clause |
| [lemminflect](https://pypi.org/project/lemminflect/) | predicted translations, spelling | MIT |
| [pyspellchecker](https://pypi.org/project/pyspellchecker/) | spelling | MIT |
| [pyzipper](https://pypi.org/project/pyzipper/) | password-protected zips (anonymous backup) | MIT |
| [praatio](https://pypi.org/project/praatio/) | reading and writing Praat TextGrids | MIT |
| [Pillow](https://pypi.org/project/pillow/) | shrinking pictures for ɛλicit requests (GIFs keep their animation) | MIT-CMU (HPND) |
| [soundfile](https://pypi.org/project/soundfile/) (with libsndfile) | reading ɛλicit's FLAC recordings | BSD-3-Clause (libsndfile: LGPL-2.1-or-later) |
| [pycountry](https://pypi.org/project/pycountry/) (with the Debian iso-codes data) | the ISO 639-3 languages for a lemma's From | LGPL-2.1-only |
| [pytest](https://pypi.org/project/pytest/) | the automated tests (development only) | MIT |

**Fonts.** Lemmatrix uses Charis SIL for IPA when it is installed; no font is included. The
splash screen's title (λemmatriχ) is stored as outlines drawn from Doulos SIL, which is
licensed under the SIL Open Font License 1.1 (https://openfontlicense.org).

**ɛλicit's web page** (`docs/elicit/`) uses no libraries: its zip files, WAV recordings and FLAC encoder
(`flac.js`, written from the FLAC specification) are its own code. The ɛλ in the ɛλicit icons (Josh's drawings, 20 October 2026) is drawn
from Arial letterforms, stored as outlines in a picture; no font is included.

**The ɛλicit test database** (`samples/Elicit test`): the recordings are Joshua A. G. Smolders'
own, under the same licence as Lemmatrix; the pictures are placeholders drawn by
`samples/make_elicit_test.py`.

**The comparative wordlists** (`lemmatrix/wordlists/`; IDEAS.md idea 40) are data, not code, and
not under the AGPL:

| List | Source | Terms |
|---|---|---|
| Extended African Comparative Wordlist (`eacw.tsv`) | Smolders, Joshua. 2026. *Extended African Comparative Wordlist.* (DOI to come) | © 2026 Joshua A. G. Smolders; its licence is set with its publication |
| SIL Comparative African Wordlist (`cawl.tsv`) | Snider, Keith & James Roberts. 2006. SIL Electronic Working Papers 2006-005. | Only the item numbers, section numbers and the mapping are included; its glosses are to be added once SIL International grants permission |
| Swadesh list, 207 items (`swadesh.tsv`) | Swadesh, Morris. 1952; 1955 (see the README's References) | the list of English glosses as commonly used |

The mapping between the three lists (the `eacw` and `cawl` columns) was drafted for Lemmatrix in
October 2026, from the lists' glosses, for Joshua A. G. Smolders to check.

**Other programs.** Lemmatrix can open recordings in [Praat](https://www.praat.org) (by Paul
Boersma and David Weenink), if it is installed; Praat isn't part of Lemmatrix.
