"""Descriptions of the default tags and tag groups, with their sources.

Each description is one or two sentences, with the page it is based on. Both sites cite their
own sources for their definitions; those are given in the README's References.

  SIL Glossary of Linguistic Terms: https://glossary.sil.org/
  Grammaticon: https://grammaticon.clld.org/
"""

from __future__ import annotations

# name -> (description, source title, URL)
DEFINITIONS: dict[str, tuple[str, str, str]] = {}


def tag_description(name: str) -> str:
    """The default description of a tag or group: the text, then where it comes from."""
    d = DEFINITIONS.get(name)
    if d is None:
        return ""
    text, title, url = d
    return f"{text}\nSource: {title}, {url}"
