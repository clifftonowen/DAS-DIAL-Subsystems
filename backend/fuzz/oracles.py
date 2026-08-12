"""Test oracles — the box the Week 11 pipeline draws between "Program" and "Pass / Fail".

A fuzzer without an oracle can only detect crashes. Enumerating the oracles explicitly is what
lets the report say *how* a wrong answer was recognised, not just that the process survived.

Five kinds are in use. Each target declares which ones apply to it:

  CRASH        an exception escaped that the caller is not documented to handle.
  HANG         one input took longer than a wall-clock threshold.
  INVARIANT    a property that must hold for every output (range, subset, non-null).
  ROUNDTRIP    parse(format(x)) == x, or format(parse(s)) == s.
  DIFFERENTIAL two implementations of one rule disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OracleKind(str, Enum):
    CRASH = "crash"
    HANG = "hang"
    INVARIANT = "invariant"
    ROUNDTRIP = "roundtrip"
    DIFFERENTIAL = "differential"


class OracleViolation(Exception):
    """Raised by a target when a non-crash oracle fails.

    Distinct from a crash on purpose: an invariant breach means the code returned an answer and
    the answer was wrong, which is a different (and usually worse) class of defect than raising.
    """

    def __init__(self, kind: OracleKind, message: str):
        super().__init__(message)
        self.kind = kind


def invariant(condition: bool, message: str) -> None:
    if not condition:
        raise OracleViolation(OracleKind.INVARIANT, message)


def roundtrip(condition: bool, message: str) -> None:
    if not condition:
        raise OracleViolation(OracleKind.ROUNDTRIP, message)


def differential(condition: bool, message: str) -> None:
    if not condition:
        raise OracleViolation(OracleKind.DIFFERENTIAL, message)


@dataclass
class Finding:
    """One deduplicated defect, with the smallest input that reproduces it so far."""

    kind: OracleKind
    signature: str
    message: str
    input_bytes: bytes
    input_len: int
    elapsed_ms: float = 0.0
    count: int = 1
    traceback: str = ""
    strategy: str = ""
    target: str = ""
    tags: list[str] = field(default_factory=list)

    def observe(self, data: bytes, elapsed_ms: float, message: str = "") -> None:
        """Record another hit. Keeps the SHORTEST reproducing input, which is the poor-relation
        version of Hypothesis's shrinking and costs nothing: a two-line report entry beats a
        40KB blob of garbage every time.

        The message travels WITH the input it describes. Keeping them independent was a bug: one
        bucket is a single failing assertion, but different inputs reach it for different reasons
        (a Devanagari digit and a leading zero both break the semester round trip), so a report
        pairing the first input's message with a later input's bytes describes neither.
        """
        self.count += 1
        if len(data) < self.input_len:
            self.input_bytes = data
            self.input_len = len(data)
            if message:
                self.message = message
        if self.kind is OracleKind.HANG and elapsed_ms > self.elapsed_ms:
            self.elapsed_ms = elapsed_ms
