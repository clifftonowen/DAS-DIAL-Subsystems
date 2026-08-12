"""Target for `app/ingestion/semesters.py`.

Included beyond the two targets PM3 named because it demonstrates a *different oracle kind*. The
parser targets are found by crash and hang oracles; this one is found by a round-trip oracle,
where the code returns an answer and the answer is wrong. Oracle variety is what the lecture's
Test-Oracle framing rewards, and it costs one small module.

Both properties asserted here are quoted from the module's OWN docstring, not invented:

    "Zero-padded year plus a fixed-width suffix is what makes TEXT ordering equal chronological
     ordering - '2022 Sem 2' < '2023 Sem 1' as plain strings, which `latest_for_learner` and the
     workbook's reduction both rely on."

So a value that parses but does not round-trip, or that sorts out of order, breaks a contract the
authors wrote down and two call sites depend on.
"""
from __future__ import annotations

from app.ingestion.semesters import (
    SEMESTER_RE,
    format_semester,
    next_semester,
    option_list,
    parse,
)
from fuzz.grammar import any_digit, ascii_digit
from fuzz.oracles import invariant, roundtrip
from fuzz.targets.base import Target, as_text, register

# The language `SEMESTER_RE = r"(\d{4}) Sem ([12])"` claims to accept, written out as BNF.
#
# `<digit>` uses the FULL set Python's `\d` matches, because that is what the regex actually
# accepts - the four-digit year group is `\d{4}`, which is Unicode-aware. The half group is
# `[12]`, which is not. That asymmetry is a property of the production code, and writing the
# grammar faithfully is what exposes it; it is not a hint planted here.
SEMESTER_GRAMMAR = {
    "<start>": [
        ["<year>", " Sem ", "<half>"],
        ["<pad>", "<year>", " Sem ", "<half>", "<pad>"],
        ["<year>", "<sep>", "Sem", "<sep>", "<half>"],
        ["<digits>", " Sem ", "<half>"],
    ],
    "<year>": [["<digit>", "<digit>", "<digit>", "<digit>"]],
    "<digits>": [["<digit>"], ["<digit>", "<digits>"]],
    "<digit>": [[any_digit]],
    "<half>": [["1"], ["2"], ["3"], ["0"], [ascii_digit]],
    "<sep>": [[" "], ["  "], ["\t"], [""]],
    "<pad>": [[" "], ["\n"], [""]],
}

SEED_SEMESTERS = [
    b"2026 Sem 1",
    b"2026 Sem 2",
    b"2022 Sem 1",
    b"1999 Sem 2",
    b"  2024 Sem 1  ",
    b"2026 Sem 3",      # invalid half: must be rejected
    b"26 Sem 1",        # invalid year width: must be rejected
    b"2026 sem 1",      # wrong case: must be rejected
]


@register
class SemesterTarget(Target):
    name = "semesters"
    allowed = (ValueError,)
    oracles = ("crash", "hang", "roundtrip", "invariant")
    max_size = 4096
    grammar = SEMESTER_GRAMMAR

    def seeds(self) -> list[bytes]:
        return list(SEED_SEMESTERS)

    def run(self, data: bytes) -> None:
        raw = as_text(data)

        # `parse` raising ValueError is the correct answer for a malformed semester, and the
        # engine treats it as a rejection rather than a finding.
        year, half = parse(raw)
        stripped = raw.strip()

        # ORACLE 1 - round trip. If the module accepted this string, it must be able to write it
        # back unchanged. Anything else means what got stored is not what was validated.
        rebuilt = format_semester(year, half)
        roundtrip(
            rebuilt == stripped,
            f"accepted {stripped!r} but reformats it as {rebuilt!r}",
        )

        # ORACLE 2 - the ordering contract the docstring names. The next semester must sort
        # after this one as plain text, because `latest_for_learner` orders on text.
        following = next_semester(stripped)
        invariant(
            following > stripped,
            f"next_semester({stripped!r}) == {following!r}, which does not sort after it",
        )

        # ORACLE 3 - the form's option list stays sorted, deduplicated, and self-consistent.
        options = option_list([stripped, "2022 Sem 1", "2023 Sem 2"])
        invariant(
            options == sorted(set(options), reverse=True),
            f"option_list returned {options!r}, which is not sorted-descending and unique",
        )
        invariant(
            all(SEMESTER_RE.fullmatch(option) for option in options),
            f"option_list returned a value it would itself reject: {options!r}",
        )
