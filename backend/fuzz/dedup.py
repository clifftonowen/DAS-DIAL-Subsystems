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

    label = kind.value if isinstance(exc, OracleViolation) else type(exc).__name__

    if isinstance(exc, OracleViolation):
        frame = _deepest_frame(exc, (_TARGETS_ROOT,))
    else:
        # THE LIBRARY TIER EXISTS BECAUSE OF A MISLABELLED REPORT. The http_api target found a
        # real 500 - the app accepts `Infinity` into a float field, then starlette cannot encode
        # its own response - but NO app/ frame appears in that traceback, because the failure
        # happens above our code in the framework's response renderer. The old two-tier fallback
        # therefore blamed the fuzz target's own call site, and the finding read as a bug in the
        # fuzzer. A framework frame is not our code, but it is a truthful and stable bucket key,
        # and it is strictly better than pointing at ourselves.
        #
        # Still not the deepest frame overall: that would be json/encoder.py, which is where every
        # unrelated serialisation failure in the process also dies, so it would merge bugs the
        # framework frame keeps apart.
        frame = _deepest_frame(exc, (_APP_ROOT,)) or _deepest_library_frame(exc) \
            or _deepest_frame(exc, (_TARGETS_ROOT,))

    where = f"{frame[0]}:{frame[1]}" if frame else "outside-app"
    return f"{kind.value}:{label}:{where}"


def _deepest_library_frame(exc: BaseException) -> tuple[str, int] | None:
    """Deepest third-party frame, named `<package>/<file>:<line>` so starlette and httpx are
    distinguishable rather than both collapsing to a bare `responses.py`."""
    found = None
    for frame in traceback.extract_tb(exc.__traceback__):
        path = Path(frame.filename)
        parts = path.parts
        if "site-packages" not in parts:
            continue
        index = parts.index("site-packages")
        package = parts[index + 1] if len(parts) > index + 1 else "?"
        found = (f"{package}/{path.name}", frame.lineno)
    return found


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
