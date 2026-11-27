"""Lesson language by function-word ratio. English drives the full generator; Filipino and Taglish get fewer questions."""

import re

ENGLISH = frozenset(
    "the of and to in is are was were a an that for it as with on by this be or from which at not have has "
    "can their its these they also such but other into than more when may each".split()
)
FILIPINO = frozenset(
    "ang ng mga sa na at ay ito si ni kung para hindi siya sila kanyang kanilang ating natin ko mo din rin "
    "lamang lang po ba pa nang dahil upang kapag habang".split()
)
WORD = re.compile(r"[a-zA-Z]+")
MIN_WORDS = 30


def detect_language(text: str) -> str:
    words = [word.lower() for word in WORD.findall(text[:200_000])]
    if len(words) < MIN_WORDS:
        return "unknown"
    english = sum(1 for word in words if word in ENGLISH) / len(words)
    filipino = sum(1 for word in words if word in FILIPINO) / len(words)
    if english < 0.08 and filipino < 0.08:
        return "unknown"
    if min(english, filipino) >= 0.08 and min(english, filipino) / max(english, filipino) >= 0.3:
        return "mixed"
    return "en" if english > filipino else "tl"
