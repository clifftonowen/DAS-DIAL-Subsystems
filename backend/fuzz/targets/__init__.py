"""Fuzz targets — one module per unit under test.

A target wraps the program so the engine does not need to know anything about it: it supplies
seeds, declares which exceptions mean "correctly rejected", and runs one input while checking
whatever oracles apply to it.
"""
from __future__ import annotations

from fuzz.targets.base import Target, REGISTRY, register  # noqa: F401
from fuzz.targets import (  # noqa: F401,E402
    t_assessment_parser,
    t_http_api,
    t_normalise,
    t_parse_verdict,
    t_percentiles,
    t_semesters,
)


def get(name: str) -> Target:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(f"unknown target {name!r}. Known: {', '.join(sorted(REGISTRY))}")


def all_targets() -> list[Target]:
    return [REGISTRY[name] for name in sorted(REGISTRY)]
