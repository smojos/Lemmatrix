# Lemmatrix sample databases

**© 2026 Joshua A. G. Smolders. All rights reserved.**

The sample database and the ɛλicit test database are the author's own creative work: an invented
language, its words, sentences and texts, and recordings of the author's own voice. They are
**not** under the AGPL, which covers Lemmatrix's code only (see `LICENSE` and `NOTICE.md`).
Anyone may take the program and its usefulness; nobody may take the creative work in its samples
as their own.

## How the sample language was made

The sample database's language (LXX, variety VXX) is invented, and its recordings are the
author's own voice. Any resemblance to any living language is a complete coincidence.
The ɛλicit test database is a little Italian, with the author's own recordings.

## What counts as the samples

- **The sample database:** `samples/Sample.xml`, `samples/Sample.workspace`, `samples/Sample.notebook`
  (its questions, To Dos, snapshots and hypotheses), `samples/Whiteboard/`, everything in
  `samples/Soundfiles/` (the tokens, the text *The man and the lion* with its TextGrid, and the
  utterances clipped from it) and in `samples/Documentation/` (the invented consent form);
- **the ɛλicit test database:** everything in `samples/Elicit test/` (the database, its workspace,
  its recordings and its pictures);
- **the scripts that build them,** `samples/make_sample.py` and `samples/make_elicit_test.py`,
  because they hold the samples' content (the invented language's sounds, words, grammar and
  texts, and the ɛλicit test's words and instructions); their SPDX line is
  `LicenseRef-Lemmatrix-Samples`;
- **anything new the author adds to these files and folders,** as soon as it is there;
- **the samples' content itself,** in any form: the invented language (its lexicon, its
  morphology and the texts written in it), the selection and wording of the entries, and the
  recordings, whether copied, rebuilt from the scripts, transcribed or re-recorded.

**Not covered:** the large test database (`samples/Test-300.xml` and `samples/make_test_database.py`)
and the automated tests in `tests/` are ordinary AGPL code and data. So is the program code that
opens the samples (for example Help → Sample databases).

## What you may do

- **Share Lemmatrix as it is.** Copies of Lemmatrix exactly as the author released them (from
  https://github.com/smojos/Lemmatrix or https://doi.org/10.5281/zenodo.23512411) may be copied
  and shared freely, samples included, unchanged.
- **Use the samples to learn and try out Lemmatrix,** and change your own copies of them, on
  your own computers.
- **Show the samples in Lemmatrix** (screenshots, demonstrations, teaching, reviews), crediting
  *Lemmatrix sample data © Joshua A. G. Smolders*.

## What you may not do

- Use the samples or their content outside Lemmatrix, or change them and pass them on.
- Distribute a **modified version** of Lemmatrix, or another program, with any of the samples or
  their content in it, including by running the scripts that build them. A modified version must
  remove them and make sample data of its own (and the tests that use them must use its own data
  too).
- Present the invented language, its texts or the recordings as anyone else's work.

To ask about any other use, write to lemmatrix.support@gmail.com.
