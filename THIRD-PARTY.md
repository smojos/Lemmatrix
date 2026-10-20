# Third-party software

Lemmatrix is © 2026 Joshua A. G. Smolders and licensed under GPL-3.0-or-later (see `LICENSE`).
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
| [pytest](https://pypi.org/project/pytest/) | the automated tests (development only) | MIT |

**Fonts.** Lemmatrix uses Charis SIL for IPA when it is installed; no font is included. The
splash screen's title (λemmatriχ) is stored as outlines drawn from Doulos SIL, which is
licensed under the SIL Open Font License 1.1 (https://openfontlicense.org).

**Other programs.** Lemmatrix can open recordings in [Praat](https://www.praat.org) (by Paul
Boersma and David Weenink), if it is installed; Praat isn't part of Lemmatrix.
