"""Targets for `app/ingestion/assessment_parser.py` — named in our PM3 plan as a fuzzing target.

Two targets, on purpose:

  assessment_text   the regex/conversion layer, taking `str` directly. Microseconds per input, so
                    this is what a long campaign actually runs.
  assessment_docx   the real `parse_assessment_report` on a real .docx. Milliseconds per input,
                    but it proves a finding is reachable by a therapist uploading a file, which
                    is the claim the report has to be able to make.

Anything `assessment_text` finds must be confirmed through `assessment_docx` before it is written
up as user-reachable. The fast target is for search; the slow one is for proof.
"""
from __future__ import annotations

import io
import math

from app.ingestion.assessment_parser import (
    InvalidFormatError,
    ParseError,
    _extract_list,
    _extract_tasks,
    _search,
    _search_float,
    parse_assessment_report,
)
from app.schemas.dto import AssessmentPreview
from fuzz.grammar import ascii_digit, letters
from fuzz.oracles import invariant
from fuzz.targets.base import Target, as_text, register

LEARNER_ID = "00000000-0000-0000-0000-000000000001"

# BNF for the report layout, taken from the parser's own regexes rather than from any defect we
# already know about. In particular `<score-chars>` is `[\d.]+` because that is verbatim the
# character class in the `Confidence Score:` and `Risk Score:` patterns, and `<date-chars>` is
# `[\d\-/]+` for the same reason. Generating the language the code SAYS it accepts is the whole
# technique; planting a known-bad literal like "1.2.3" would make the result circular.
REPORT_GRAMMAR = {
    "<start>": [
        ["<date-line>", "\n", "<tasks>", "<summary>"],
        ["<date-line>", "\n", "<summary>"],
        ["<tasks>", "<summary>"],
        ["<summary>"],
    ],
    "<date-line>": [["Assessment Date: ", "<date-chars>"]],
    "<date-chars>": [["<date-char>"], ["<date-char>", "<date-chars>"]],
    "<date-char>": [[ascii_digit], ["-"], ["/"]],
    "<tasks>": [["<task-line>", "\n"], ["<task-line>", "\n", "<tasks>"]],
    "<task-line>": [[letters, " ", "<int>", " ", "<int>"]],
    "<int>": [[ascii_digit], [ascii_digit, "<int>"]],
    "<summary>": [
        ["Confidence Score: ", "<score-chars>", "\nRisk Score: ", "<score-chars>", "\n"],
        ["Confidence Score: ", "<score-chars>", "\n"],
        ["Risk Score: ", "<score-chars>", "\n"],
    ],
    "<score-chars>": [["<score-char>"], ["<score-char>", "<score-chars>"]],
    "<score-char>": [[ascii_digit], ["."]],
}

# The layout documented in assessment_parser.py's own docstring. This is the mutation seed, and
# it is deliberately a *valid* report: mutation-based fuzzing is defined by starting from valid
# input, and the lecture's stated con for it is that it needs good seed coverage.
SEED_REPORT = b"""Assessment Date: 2026-07-24
Task Results
Task Score Max Score
Phoneme Segmentation 7 10
Letter Sound Knowledge 18 26
Word Reading 9 10
Summary
Confidence Score: 0.6
Risk Score: 0.4
Strengths: Alphabet knowledge, Oracy
Weaknesses: Phonemic awareness, Spelling
Generated for demonstration purposes only.
"""

# Variants that exercise branches the main seed does not: the "no tasks at all" path, the
# guard at assessment_parser.py:73, and a report with only a summary block.
SEED_VARIANTS = [
    SEED_REPORT,
    b"Assessment Date: 2026-01-02\nConfidence Score: 0.9\nRisk Score: 0.1\n",
    b"Task Results\nPhoneme Segmentation 0 10\n",
    b"Strengths: A\nWeaknesses: B\nConfidence Score: 0.5\nRisk Score: 0.5\n",
    b"",
]


def _check_parsed(preview: AssessmentPreview) -> None:
    """Invariant oracles over a successfully parsed report.

    These are properties the domain requires but that NOTHING in the code enforces: `TaskResult`
    has no validator, and `confidence_score` / `risk_score` are plain floats.
    """
    for task in preview.tasks:
        invariant(
            task.max_score >= 0,
            f"negative max_score {task.max_score} for task {task.name!r}",
        )
        invariant(
            0 <= task.score <= task.max_score,
            f"task {task.name!r} scored {task.score} out of {task.max_score}",
        )

    for label, value in (
        ("confidence_score", preview.confidence_score),
        ("risk_score", preview.risk_score),
    ):
        invariant(
            math.isfinite(value),
            f"{label} is {value!r}, which cannot be serialised as JSON",
        )


@register
class AssessmentTextTarget(Target):
    """The conversion layer, driven directly.

    MIRRORS `parse_assessment_report` lines 66-94. It calls the real module functions, so only
    the ORDER is reproduced here, not the logic. If that function's body changes, this needs
    reviewing; the `assessment_docx` target below is the guard that would catch the drift.
    """

    name = "assessment_text"
    allowed = (InvalidFormatError, ParseError)
    oracles = ("crash", "hang", "invariant")
    grammar = REPORT_GRAMMAR

    def seeds(self) -> list[bytes]:
        return list(SEED_VARIANTS)

    def run(self, data: bytes) -> None:
        text = as_text(data)
        if not text.strip():
            raise ParseError("No extractable text found in the document.")

        assessment_date = _search(r"Assessment Date:\s*([\d\-/]+)", text) or "2026-01-01"
        tasks = _extract_tasks(text)
        confidence_score = _search_float(r"Confidence Score:\s*([\d.]+)", text) or 0.0
        risk_score = _search_float(r"Risk Score:\s*([\d.]+)", text) or 0.0
        strengths = _extract_list(r"Strengths:\s*(.+)", text)
        weaknesses = _extract_list(r"Weaknesses:\s*(.+)", text)

        if not tasks and confidence_score == 0.0 and risk_score == 0.0:
            raise ParseError("Could not locate any recognizable assessment data in this report.")

        preview = AssessmentPreview(
            learner_id=LEARNER_ID,
            assessment_date=assessment_date,
            tasks=tasks,
            strengths=strengths,
            weaknesses=weaknesses,
            confidence_score=confidence_score,
            risk_score=risk_score,
            task_results={t.name: {"score": t.score, "max_score": t.max_score} for t in tasks},
        )
        _check_parsed(preview)


#: C0 control characters XML 1.0 forbids. Tab, newline and carriage return are legal and stay.
_XML_FORBIDDEN = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}
_XML_FORBIDDEN[0x0B] = None  # vertical tab: below 0x20 already, listed for the reader
_XML_FORBIDDEN[0x0C] = None  # form feed: same


def _xml_safe(text: str) -> str:
    """Drop characters a `.docx` cannot physically contain.

    NOT the fuzzer going easy on the parser - the opposite. `python-docx` raises "All strings must
    be XML compatible" when ASKED TO WRITE these, so the failure happens in the harness building
    its input, several steps before `parse_assessment_report` is called. It was reported as a
    crash finding, and it is not one: a Word document is a zip of XML, XML 1.0 cannot represent a
    NUL or a bare 0x01, so no real upload can carry one either.

    Leaving it in would spend the docx target's budget rediscovering a limitation of the document
    format. The bytes are still fuzzed everywhere they can actually appear - `assessment_text`
    drives the same parser directly with no format to satisfy, and `http_api` puts them on the
    wire percent-encoded.
    """
    return text.translate(_XML_FORBIDDEN)


class _UploadShim:
    """The two attributes `parse_assessment_report` actually touches: `.filename` and `.file`."""

    def __init__(self, filename: str, raw: bytes):
        self.filename = filename
        self.file = io.BytesIO(raw)


@register
class AssessmentDocxTarget(Target):
    """The whole documented path: bytes -> .docx -> `parse_assessment_report`.

    Slower by roughly three orders of magnitude, so it is not where a campaign spends its budget.
    Its job is to answer "could a therapist actually trigger this by uploading a file?", which is
    the difference between a finding and a curiosity.
    """

    name = "assessment_docx"
    allowed = (InvalidFormatError, ParseError)
    oracles = ("crash", "hang", "invariant")
    max_size = 16384
    grammar = REPORT_GRAMMAR

    def seeds(self) -> list[bytes]:
        return list(SEED_VARIANTS)

    def run(self, data: bytes) -> None:
        import docx  # python-docx, already a runtime dependency

        document = docx.Document()
        for line in _xml_safe(as_text(data)).split("\n"):
            document.add_paragraph(line)
        buffer = io.BytesIO()
        document.save(buffer)

        preview = parse_assessment_report(
            _UploadShim("fuzz.docx", buffer.getvalue()), LEARNER_ID
        )
        _check_parsed(preview)
