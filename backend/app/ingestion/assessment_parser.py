"""Parses uploaded DAS-format assessment reports (PDF or DOCX) into a preview
for the therapist to review before it's stored.

Expected layout (see sample_assessment.pdf):
    Assessment Date: 2026-07-24
    Task Results
    Task                    Score  Max Score
    Phoneme Segmentation    7      10
    ...
    Summary
    Confidence Score: 0.6
    Risk Score: 0.4
    Strengths: A, B, C
    Weaknesses: D, E
"""
from __future__ import annotations
import re
from datetime import date

from fastapi import UploadFile

from app.schemas.dto import AssessmentPreview, TaskResult

ALLOWED_EXTENSIONS = (".pdf", ".docx")


class InvalidFormatError(Exception):
    pass


class ParseError(Exception):
    pass


def validate_format(file: UploadFile) -> None:
    if not file or not file.filename:
        raise InvalidFormatError("No file was provided.")
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise InvalidFormatError(
            f"Unsupported file type '{file.filename}'. Please upload a PDF or DOCX report."
        )


def _extract_text(file: UploadFile, raw: bytes) -> str:
    if file.filename.lower().endswith(".pdf"):
        import fitz  # PyMuPDF — already a dependency (see ingestion/pdf_reader.py)
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            return "\n".join(page.get_text("text") for page in pdf)
    else:  # .docx
        import docx
        import io
        doc = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)


def parse_assessment_report(file: UploadFile, learner_id: str) -> AssessmentPreview:
    raw = file.file.read()
    try:
        text = _extract_text(file, raw)
    except Exception as e:
        raise ParseError(f"Could not read file contents: {e}")

    if not text.strip():
        raise ParseError("No extractable text found in the document.")

    assessment_date = _search(r"Assessment Date:\s*([\d\-/]+)", text) or date.today().isoformat()
    tasks = _extract_tasks(text)
    confidence_score = _search_float(r"Confidence Score:\s*([\d.]+)", text) or 0.0
    risk_score = _search_float(r"Risk Score:\s*([\d.]+)", text) or 0.0
    strengths = _extract_list(r"Strengths:\s*(.+)", text)
    weaknesses = _extract_list(r"Weaknesses:\s*(.+)", text)

    if not tasks and confidence_score == 0.0 and risk_score == 0.0:
        raise ParseError("Could not locate any recognizable assessment data in this report.")

    notes_match = re.search(r"Generated for demonstration purposes only\.?", text)
    notes = notes_match.group(0) if notes_match else ""

    task_results = {t.name: {"score": t.score, "max_score": t.max_score} for t in tasks}

    return AssessmentPreview(
        learner_id=learner_id,
        assessment_date=assessment_date,
        tasks=tasks,
        strengths=strengths,
        weaknesses=weaknesses,
        confidence_score=confidence_score,
        risk_score=risk_score,
        task_results=task_results,
        notes=notes,
    )


def _search(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _search_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def _extract_list(pattern: str, text: str) -> list[str]:
    m = re.search(pattern, text)
    if not m:
        return []
    return [item.strip() for item in m.group(1).split(",") if item.strip()]


def _extract_tasks(text: str) -> list[TaskResult]:
    # Matches rows like: "Phoneme Segmentation 7 10"
    # The header row "Task Score Max Score" has no digits, so it naturally won't match.
    pattern = re.compile(r"^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d+)\s*$", re.MULTILINE)
    results = []
    for name, score, max_score in pattern.findall(text):
        results.append(TaskResult(name=name.strip(), score=int(score), max_score=int(max_score)))
    return results