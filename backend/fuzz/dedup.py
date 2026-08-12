"""Crash bucketing.

Without this a 24-hour campaign reports "3.1 million failures" and is useless. With it the same
campaign reports "4 distinct defects", which is the number that belongs in the report.

The signature is (oracle kind, exception type, deepest frame inside our own source tree). Taking
the DEEPEST APPLICATION frame rather than the topmost frame matters: every crash in the parser
enters through the same target wrapper, so keying on the top frame would collapse unrelated bugs
into one bucket, and keying on the true deepest frame would split one bug across every stdlib
call site it happens to die in.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from fuzz.oracles import Finding, OracleKind

# Frames under these roots count as "ours" when picking the signature frame, in priority order.
#
# `app/` comes first because a crash should be identified by where the PRODUCTION code died. But
# an OracleViolation is raised by the target's own assertion, so its deepest app frame is the last
# line of application code that ran, which is the same for every invariant in a target and would
# collapse them all into one bucket. Falling back to `fuzz/targets/` keys each violation on the
# specific check that failed instead.
_APP_ROOT = Path(__file__).resolve().parent.parent / "app"
_TARGETS_ROOT = Path(__file__).resolve().parent / "targets"


def signature(kind: OracleKind, exc: BaseException | None, target: str) -> str:
    if exc is None:
        return f"{kind.value}:{target}"

    from fuzz.oracles import OracleViolation

    roots = (_TARGETS_ROOT,) if isinstance(exc, OracleViolation) else (_APP_ROOT, _TARGETS_ROOT)
    frame = _deepest_frame(exc, roots)
    where = f"{frame[0]}:{frame[1]}" if frame else "outside-app"
    label = kind.value if isinstance(exc, OracleViolation) else type(exc).__name__
    return f"{kind.value}:{label}:{where}"


def _deepest_frame(exc: BaseException, roots: tuple[Path, ...]) -> tuple[str, int] | None:
    """Last frame in the traceback under the first root that matches anything."""
    for root in roots:
        found = None
        for frame in traceback.extract_tb(exc.__traceback__):
            try:
                path = Path(frame.filename).resolve()
                path.relative_to(root)
            except (ValueError, OSError):
                continue
            found = (path.name, frame.lineno)
        if found:
            return found
    return None


class FindingSet:
    """Deduplicating collection of findings, ordered by first appearance."""

    def __init__(self) -> None:
        self._by_signature: dict[str, Finding] = {}

    def record(self, finding: Finding) -> bool:
        """Add or merge. Returns True if this signature had not been seen before."""
        existing = self._by_signature.get(finding.signature)
        if existing is None:
            self._by_signature[finding.signature] = finding
            return True
        existing.observe(finding.input_bytes, finding.elapsed_ms, finding.message)
        return False

    def __len__(self) -> int:
        return len(self._by_signature)

    @property
    def findings(self) -> list[Finding]:
        return list(self._by_signature.values())


def format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
