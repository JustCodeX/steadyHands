"""Instrument base class and one subclass per instrument.

Adding an instrument: subclass Instrument here, add its command word to the
config, and reference the word in a level's `needs`.
"""
from __future__ import annotations

from .base import Instrument
from .clamp import Clamp
from .forceps import Forceps
from .scalpel import Scalpel
from .swab import Swab

ALL: dict[str, type[Instrument]] = {cls.word: cls for cls in (Forceps, Swab, Clamp, Scalpel)}


def make(word: str) -> Instrument:
    try:
        return ALL[word]()
    except KeyError as exc:
        raise ValueError(f"unknown instrument: {word}") from exc


__all__ = ["Instrument", "Forceps", "Swab", "Clamp", "Scalpel", "ALL", "make"]
