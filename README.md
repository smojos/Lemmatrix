# Lemmatrix

A custom linguistics database program specialized for creating and storing human readable
XML paradigm information for phonological and morphological analysis: lemmas with their
tokens (transcriptions, pitch, tags and one recording each). Modelled on how Dekereke
behaves; no Dekereke code is used. The full working spec is in [DESIGN.md](DESIGN.md).

**Status:** first prototype (Stage 1, version 0.1).

## Running it on Windows

1. Pull the latest version in GitHub Desktop.
2. Double-click **`Run Lemmatrix.bat`**.
   The first run creates its own Python 3.13 environment (`py -3.13`) and installs the
   packages, which takes a few minutes. Later runs start straight away.
3. Choose **Open a copy of the sample** to try it with invented data. The copy goes to
   `Documents\Lemmatrix Sample`, so the sample in the repository stays untouched.

On Mac or Linux, run `./run_lemmatrix.sh` instead.

To run the automated tests, double-click **`Run tests.bat`** (after the first run).

If something goes wrong, a message box shows the details, and they're also written to
`lemmatrix-errors.log` in this folder. Send that to Claude.

## What works in this version

- **Database files:** open, save, save as, new database; backups of the previous version
  in a `Backups` folder beside the database (10 kept); optional autosave.
- **Lemma list:** filter button on every column, search, column choice (View menu),
  add / edit / delete entries, references suggested from the category (next free number,
  gaps never reused).
- **Matrix view**, three tabs:
  - *All data:* one row per token; Phonetic, Phonemic, Pitch, Translation and Comment can be
    edited in place (double-click or F2).
  - *Tag/Tag Paradigm:* the selected entry's paradigm, one tag group down the side and
    another across the top (Set up token display).
  - *Entry/Tag Paradigm:* tag combinations down the side, entries across the top.
  - The ⇄ button swaps rows and columns; Exactly/Includes matching; token filters, search,
    Play cell, saved views.
  - Double-click a token to edit it; double-click an empty cell to add one there.
- **Token dialogue:** live pitch drawing, tag buttons (one per group, defaults
  pre-selected), live file name, record / stop with a level meter, play, delete recording
  (to the Recycle Bin), update file name, Back / Next column by column, keyboard shortcuts
  (Ctrl+R, Ctrl+Space, Alt+← / Alt+→).
- **Sound file names** from the customisable pattern, renamed automatically when tags or
  speaker change (or by button when that setting is off); Tools → Update all sound file
  names and Check for duplicate file names. The speaker and date are written into each WAV
  file's own metadata.
- **Settings:** metadata (language, variety, participants, gloss languages), tag structure
  editor, file-name pattern, pitch display range, recording source / bit depth / sample
  rate, auto-play, confirm-before-delete, IPA font size.
- **Undo and redo** for all changes to entries and tokens.

## Not in this version yet

- CV shape filters and everything in the Analyze menu (Stage 2, the analysis engine).
- Unicode tone letters as an alternative pitch display; "Insert character".
- Converting Dekereke databases (Claude will do that with a one-off script).
- Recording has only been tested in the build environment, which has no sound card.
  Microphone and computer-audio recording need checking on a real Windows machine.

## Project layout

```
lemmatrix/            the program
  model.py            entries, tokens, tag structure (no user interface)
  storage.py          reading and writing the XML file, backups
  filenames.py        building sound file names from the pattern
  matrix.py           laying out tokens for the paradigm views
  pitch.py            pitch notation
  audio.py            recording, playback and WAV metadata
  defaults.py         default fields, tags and reference categories
  ui/                 windows and dialogues (Qt for Python)
samples/              invented sample database with synthetic recordings
tests/                automated tests
tools/screenshots.py  renders the windows to PNG files, for checking layouts
```
