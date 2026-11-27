"""Word tokens, stop words and a light suffix stemmer used for matching (not for display)."""

import re

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")

STOP_WORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have having he
    her here hers him his how i if in into is it its itself just me more most my no nor not now of off on once only
    or other our ours out over own same she should so some such than that the their theirs them then there these
    they this those through to too under until up very was we were what when where which while who whom why will
    with would you your yours introduction overview lesson chapter unit week module topic part session""".split()
)

_SUFFIXES = ("ational", "ization", "fulness", "iveness", "ations", "ation", "ments", "ment", "ness", "ities",
             "ity", "ings", "ing", "ies", "ied", "ers", "er", "ed", "es", "ly", "al", "s")


def words(text: str) -> list[str]:
    return [token.lower() for token in WORD.findall(text)]


def stem(word: str) -> str:
    word = word.lower()
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            base = word[: -len(suffix)]
            return base + "y" if suffix in ("ies", "ied", "ities") and not base.endswith("y") else base
    return word


def content_stems(text: str) -> list[str]:
    return [stem(token) for token in words(text) if token not in STOP_WORDS and len(token) > 1]
