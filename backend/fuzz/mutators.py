"""Mutation operators — the "flip bit, insert/delete, rearrange" of the Week 11 lecture.

A DELIBERATE OMISSION, and the reason this file has a comment at all: the token dictionary below
contains only generic fragments (single digits, a dot, a dash, whitespace, a NUL). It does NOT
contain any string we already know crashes the parser.

That restraint is the whole experiment. The plan's acceptance test is "the mutation strategy
rediscovers the `float()` crash without being told about it". Seeding the dictionary with
`b"1.2.3"` would make that claim circular and worthless. If a mutation run finds it, it found it
by duplicating a digit next to a decimal point in a seed, which is what a real fuzzer does.
"""
from __future__ import annotations

import random

# Generic fragments only. See the module docstring before adding anything here.
TOKENS: tuple[bytes, ...] = (
    b"0", b"1", b"9", b".", b"-", b"+", b" ", b"\t", b"\n", b"\r\n",
    b":", b",", b"(", b")", b"\x00", b"\xff",
)


def mutate(data: bytes, rng: random.Random, max_size: int = 65536) -> bytes:
    """Apply one randomly-chosen operator. Bounded by `max_size` so a repeat operator cannot
    grow an input without limit across generations.

    The size cap is also our hang-detection safety net: we time inputs rather than interrupting
    them (see runner.py), so the worst case has to be bounded by construction.
    """
    if not data:
        return rng.choice(TOKENS)

    op = rng.choice(_OPERATORS)
    out = op(data, rng)
    return out[:max_size] if len(out) > max_size else out


def _flip_byte(data: bytes, rng: random.Random) -> bytes:
    i = rng.randrange(len(data))
    b = bytearray(data)
    b[i] ^= 1 << rng.randrange(8)
    return bytes(b)


def _replace_byte(data: bytes, rng: random.Random) -> bytes:
    i = rng.randrange(len(data))
    b = bytearray(data)
    b[i] = rng.randrange(256)
    return bytes(b)


def _insert_token(data: bytes, rng: random.Random) -> bytes:
    i = rng.randrange(len(data) + 1)
    return data[:i] + rng.choice(TOKENS) + data[i:]


def _delete_span(data: bytes, rng: random.Random) -> bytes:
    i = rng.randrange(len(data))
    n = rng.randint(1, min(32, len(data) - i))
    return data[:i] + data[i + n:]


def _duplicate_span(data: bytes, rng: random.Random) -> bytes:
    """Copy a slice and paste it back in. This is the operator that turns `0.6` into `0.6.6`,
    and a two-digit score into a very long one. It is generic: it has no idea what a score is."""
    i = rng.randrange(len(data))
    n = rng.randint(1, min(64, len(data) - i))
    span = data[i:i + n]
    j = rng.randrange(len(data) + 1)
    return data[:j] + span + data[j:]


def _repeat_span(data: bytes, rng: random.Random) -> bytes:
    """Repeat a slice many times. Reaches the long-run cases (deep digit runs, huge headers) that
    single-byte operators would take astronomically long to build up to."""
    i = rng.randrange(len(data))
    n = rng.randint(1, min(16, len(data) - i))
    times = rng.choice((8, 64, 512, 4096))
    return data[:i] + data[i:i + n] * times + data[i + n:]


def _swap_spans(data: bytes, rng: random.Random) -> bytes:
    if len(data) < 4:
        return data
    a, b = sorted(rng.sample(range(len(data)), 2))
    n = rng.randint(1, min(16, len(data) - b))
    return data[:a] + data[b:b + n] + data[a + n:b] + data[a:a + n] + data[b + n:]


def _truncate(data: bytes, rng: random.Random) -> bytes:
    return data[:rng.randrange(len(data))]


def _splice_line(data: bytes, rng: random.Random) -> bytes:
    """Duplicate or drop a whole line. The parser is line-oriented (`re.MULTILINE`), so operators
    that respect line structure reach states byte operators mostly destroy."""
    lines = data.split(b"\n")
    if len(lines) < 2:
        return data
    i = rng.randrange(len(lines))
    if rng.random() < 0.5:
        lines.insert(i, lines[rng.randrange(len(lines))])
    else:
        del lines[i]
    return b"\n".join(lines)


_OPERATORS = (
    _flip_byte, _replace_byte, _insert_token, _delete_span,
    _duplicate_span, _repeat_span, _swap_spans, _truncate, _splice_line,
)
