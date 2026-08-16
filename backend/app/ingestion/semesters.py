"""Semester strings — the shape, the sequence, and the list the upload form offers.

`learner_sittings.semester` is the load-bearing string in this system. It is half of the table's
natural key `(learner_id, semester)`, and it is the SORT KEY that decides which sitting is the
learner's latest — which is the one ProfilingService promotes onto their profile. Postgres stores
it as plain `text` with no constraint, so nothing but this module stands between a typo and a
sitting that silently never becomes current.

Format: `'<4-digit year> Sem <1|2>'`, e.g. '2026 Sem 1'. Zero-padded year plus a fixed-width
suffix is what makes TEXT ordering equal chronological ordering — '2022 Sem 2' < '2023 Sem 1' as
plain strings, which `latest_for_learner` and the workbook's reduction both rely on.

PANDAS-FREE, and separate from `dial_workbook` for the same reason `dial_features` is: the
workbook module imports pandas, which is an analysis-only dependency. The running API needs to
validate and offer semesters on every upload, so that logic cannot live there.

WHY THERE IS NO date -> semester FUNCTION HERE. It would need DAS's academic calendar boundary —
which month Sem 2 starts in — and that is recorded nowhere in the schema, the workbook or the
parsed reports. Guessing it would misfile marks silently. The therapist picks the semester
instead, defaulting to the newest one already on record.
"""
from __future__ import annotations

import re

# Anchored by the caller with `fullmatch`. Two digits for the year would break text ordering
# ('99 Sem 1' > '2026 Sem 1'), hence exactly four.
SEMESTER_RE = re.compile(r"(\d{4}) Sem ([12])")

# How many unseen semesters the form offers past the newest on record. Two is a full year ahead:
# enough that the list cannot go stale between ingests, few enough that the default stays the
# semester the therapist is most likely to mean.
LOOKAHEAD = 2


def parse(semester: str) -> tuple[int, int]:
    """'2026 Sem 1' -> (2026, 1). Raises ValueError on anything else."""
    match = SEMESTER_RE.fullmatch(semester.strip())
    if not match:
        raise ValueError(f"semester must look like '2026 Sem 1' (got {semester!r})")
    year, half = match.groups()
    return int(year), int(half)


def format_semester(year: int, half: int) -> str:
    """(2026, 1) -> '2026 Sem 1'."""
    return f"{year} Sem {half}"


def next_semester(semester: str) -> str:
    """The semester after this one. '2026 Sem 1' -> '2026 Sem 2' -> '2027 Sem 1'.

    Pure string arithmetic over the sequence, which is why the form's list can extend forward
    forever without anyone knowing when the academic year actually turns over.
    """
    year, half = parse(semester)
    return format_semester(year + 1, 1) if half == 2 else format_semester(year, 2)


def option_list(on_record: list[str], lookahead: int = LOOKAHEAD) -> list[str]:
    """The semesters the upload form offers: everything on record, plus the next few.

    NEWEST FIRST, so the form's default (the first option) is the newest semester already on
    record — the one an assessment being uploaded today is most likely to belong to, rather than
    a future semester nobody has sat yet.

    The lookahead is what stops the list going stale. Without it, the first upload of a new
    semester would have nothing to select: the list is built from what has been stored, and
    nothing has been stored for a semester that has just begun.

    Unparseable values already in the table are dropped rather than raised on — this list is a
    convenience for the form, and one bad legacy row should not make the endpoint 500. The
    validator on the way back in is what keeps new rows well-formed.
    """
    valid = set()
    for value in on_record:
        try:
            parse(value)
        except (ValueError, AttributeError):
            continue
        valid.add(value.strip())

    if not valid:
        return []

    cursor = max(valid)          # text order == chronological order, which is the whole point
    for _ in range(lookahead):
        cursor = next_semester(cursor)
        valid.add(cursor)

    return sorted(valid, reverse=True)
