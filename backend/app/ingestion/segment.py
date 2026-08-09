"""The universal segmenter — written ONCE, called by both parsers.

A chunk boundary is a change in the key a parser derives from each page. Both layouts reduce to
this single state machine; only the key function differs:

    project_read.py -> key_of=lambda p: (p.concept, p.stage, p.sequence_no)
    band_book.py    -> key_of=lambda p: p.current_activity_name

Pure and deterministic: same pages + same key_of -> identical grouping. Consecutive pages that
share a key stay together; the run flushes when the key changes.
"""
from __future__ import annotations
from typing import Callable, TypeVar

T = TypeVar("T")
K = TypeVar("K")


def segment(pages: list[T], key_of: Callable[[T], K]) -> list[list[T]]:
    """Group consecutive pages into runs that share the same key_of(page)."""
    groups: list[list[T]] = []
    current: list[T] = []
    key: K | None = None
    for page in pages:
        k = key_of(page)
        if k != key and current:
            groups.append(current)
            current = []
        current.append(page)
        key = k
    if current:
        groups.append(current)
    return groups
