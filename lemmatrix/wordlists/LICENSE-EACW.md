# Extended African Comparative Wordlist: licence

**© 2026 Joshua A. G. Smolders.**

The **Extended African Comparative Wordlist (EACW)** in this folder is licensed under the
**Creative Commons Attribution 4.0 International licence (CC BY 4.0)**:
https://creativecommons.org/licenses/by/4.0/

It is data, not code, and is **not** under the AGPL that covers Lemmatrix's code (see `LICENSE`
and `NOTICE.md` at the top of the repository).

## What this covers

- `eacw.tsv`: the EACW itself (its references, glosses, word classes, default and sub codes,
  clarifications and taxa);
- `glosses/`: the EACW's glosses in French, Arabic and Amharic, with their clarifications and status
  (machine translated and audited, October 2026; checked by a person where marked);
- `conversions/`: the tables that bring a database from one edition's references to the next;
- the EACW's links to the other two lists: the `eacw` column of `cawl.tsv` and of `swadesh.tsv`
  (the correspondences drafted and audited for the EACW, October 2026).

It does **not** cover the SIL Comparative African Wordlist's own item and section numbers, or the
Swadesh list's glosses: see `THIRD-PARTY.md` for those.

## Using it

You may share and adapt the EACW for any purpose, including in other wordlists, compilations and
software, as long as you give credit, link to the licence and say if you changed it. Credit it as:

> Smolders, Joshua A. G. 2026. *The Extended African Comparative Wordlist (EACW)* [dataset]. Zenodo.
> https://doi.org/10.5281/zenodo.23677135. Licensed under CC BY 4.0.

That DOI covers all editions and always points to the newest; each edition also has its own
(2026-10-24: https://doi.org/10.5281/zenodo.23677136).

## Where the EACW lives

The EACW's own home is **https://github.com/smojos/EACW**, archived on Zenodo. The files in this
folder are copies of one of its editions (the newest in `wordlists.EDITIONS`), shipped so that
Lemmatrix works offline; corrections and suggestions go to that repository.
