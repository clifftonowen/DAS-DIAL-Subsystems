"""The target protocol.

`allowed` is the contract being tested and deserves care. It lists the exceptions the *caller* is
documented to handle, so raising one is correct behaviour, not a finding. For the assessment
parser that list comes straight from the router:

    routers/assessments.py:37
        except InvalidFormatError -> 400
        except ParseError         -> 422

Anything else escaping is, by construction, an unhandled 500. That is the crash oracle, and it is
derived from the production code rather than guessed.
"""
from __future__ import annotations

from typing import Callable

REGISTRY: dict[str, "Target"] = {}


class Target:
    #: identifier used by `--target`
    name: str = ""
    #: exceptions that mean "the input was correctly rejected"
    allowed: tuple[type[BaseException], ...] = ()
    #: oracle kinds this target exercises, for the report's process table
    oracles: tuple[str, ...] = ("crash", "hang")
    #: cap on generated input size, in bytes
    max_size: int = 65536
    #: package the feedback-guided strategy measures coverage of, as a MODULE name.
    #:
    #: This has to be per-target, and getting it wrong fails silently in the worst way: coverage
    #: collects nothing, every generation looks like it found no new arcs, none are kept, and the
    #: "coverage" strategy quietly degrades into plain mutation while still reporting itself as
    #: guided. A target must name the package its unit actually lives in. See cov_feedback.py for
    #: why this is a module name and not a path.
    measured: str = "app.ingestion"
    #: Inputs per generation for the feedback-guided strategy. None means the module default in
    #: cov_feedback.SUITE_SIZE, which was tuned against microsecond-scale string functions. A
    #: target whose single execution costs milliseconds needs a smaller suite: the generation
    #: itself takes proportionally longer, and the per-input attribution pass that follows a
    #: winning generation scales with the suite size too.
    suite_size: int | None = None
    #: BNF for the target's input language, used by the generation-based strategy. Optional:
    #: a target without one falls back to random generation, and the runner says so.
    grammar: dict | None = None
    grammar_start: str = "<start>"

    def seeds(self) -> list[bytes]:
        """Valid inputs to start mutation from. Must be non-empty for the mutation strategy to
        mean anything: the lecture's stated con for mutation-based fuzzing is that it "requires
        good seed coverage"."""
        raise NotImplementedError

    def run(self, data: bytes) -> None:
        """Exercise the unit once. Return normally on success, raise on failure."""
        raise NotImplementedError


def register(cls: type[Target]) -> type[Target]:
    instance = cls()
    if not instance.name:
        raise ValueError(f"{cls.__name__} has no name")
    REGISTRY[instance.name] = instance
    return cls


def as_text(data: bytes) -> str:
    """Decode for targets whose unit takes `str`.

    `errors="replace"` rather than `"ignore"`: dropping undecodable bytes silently shrinks the
    input and would hide length-dependent behaviour, which is exactly what the hang oracle is
    looking for. Replacement keeps the length honest.
    """
    return data.decode("utf-8", errors="replace")
