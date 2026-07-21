"""Offline curriculum ingestion pipeline (Subsystem 3).

Batch package — invoked by scripts/ingest_curriculum.py, NOT request-scoped. It uses the
CurriculumRepository and the embedding gateway rather than bypassing them. No LLM in the
chunking path: same PDF in -> identical chunks out.
"""
