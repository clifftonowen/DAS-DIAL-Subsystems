"""Generation-based fuzzing — a small BNF expander.

Week 11's third strategy: "find a formal grammar to represent valid input set, generate random
inputs from the formal grammar". Pro: higher coverage. Con: higher setup cost.

WHY THIS EXISTS WHEN MUTATION ALREADY WORKS. Measured, not assumed: byte-mutating the semester
seeds found three defects in 20 seconds but could not reach the Unicode-digit defect at all,
because every seed is ASCII and no byte operator invents a U+0660. A grammar whose digit
alphabet includes non-ASCII decimal digits reaches it on the first try. The two strategies are
not redundant; each finds a class the other structurally cannot.

A NOTE ON HONESTY. The grammars below model the *language the code claims to accept*, taken from
its own regexes, not the bugs we already know about. `<score-chars>` is `[\d.]+` because that is
literally the character class in `assessment_parser.py`'s `Confidence Score:` pattern. Writing
`"1.2.3"` into the grammar as a literal would be encoding the answer, which would make the
result meaningless.

Slide 14's warning is honoured by `max_depth`: recursive alternatives are dropped once the
expansion gets too deep, so `<tasks> ::= <task> <tasks>` terminates.
"""
from __future__ import annotations

import random
from typing import Callable, Sequence

#: A production is a sequence of symbols; a symbol is either a non-terminal key, a literal
#: string, or a callable that produces a literal from the rng.
Symbol = str | Callable[[random.Random], str]
Grammar = dict[str, Sequence[Sequence[Symbol]]]

# Decimal digits that Python's `\d` matches but that `int()` and ASCII-only ranges treat
# differently. This is the alphabet that makes the semester defect reachable.
UNICODE_DIGITS = (
    "٠١٢٣٤٥٦٧٨٩"  # Arabic-Indic
    "०१२३४५६७८९"  # Devanagari
    "０１２３４５６７８９"  # Fullwidth
)


def ascii_digit(rng: random.Random) -> str:
    return rng.choice("0123456789")


def any_digit(rng: random.Random) -> str:
    """A digit from the full set Python's `\\d` accepts, ASCII-weighted.

    Weighted rather than uniform so most generated input still looks like real data; a grammar
    that emitted Devanagari 90% of the time would never exercise the ordinary paths.
    """
    return ascii_digit(rng) if rng.random() < 0.75 else rng.choice(UNICODE_DIGITS)


def letters(rng: random.Random) -> str:
    length = rng.randint(1, 12)
    return "".join(rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                   for _ in range(length))


def expand(
    grammar: Grammar,
    symbol: Symbol,
    rng: random.Random,
    depth: int = 0,
    max_depth: int = 12,
) -> str:
    if callable(symbol):
        return symbol(rng)
    if symbol not in grammar:
        return symbol

    alternatives = grammar[symbol]
    if depth >= max_depth:
        # Slide 14: "do not over expand with the recursive alternative". Past the depth limit,
        # prefer the shortest production, which is the base case in a well-formed grammar.
        alternatives = [min(alternatives, key=len)]

    production = rng.choice(list(alternatives))
    return "".join(expand(grammar, part, rng, depth + 1, max_depth) for part in production)
