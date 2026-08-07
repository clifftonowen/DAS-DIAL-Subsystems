"""Load and validate the golden retrieval set.

The single most dangerous failure mode in an eval harness is a ground truth that silently does
not match the corpus: a typo'd filename does not raise, it just makes every metric worse and
sends you optimising the retriever for a bug in the labels. So `load_golden` resolves every
reference against the live corpus and REFUSES to return a set with unresolved entries.
"""
from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field

GOLDEN_PATH = pathlib.Path(__file__).with_name("golden_queries.yaml")

IN_DOMAIN = "in_domain"
OUT_OF_DOMAIN = "out_of_domain"
EMPTY_EXPECTED = "empty_expected"


@dataclass
class Case:
    id: str
    query: str
    kind: str
    band_group: str | None = None
    band: str | None = None
    concept: str | None = None
    stage: str | None = None
    relevant: list[tuple[str, str]] = field(default_factory=list)   # (source_file, page_start)

    @property
    def expects_hits(self) -> bool:
        return self.kind == IN_DOMAIN


@dataclass
class Golden:
    cases: list[Case]
    digest: str          # identifies WHICH golden set produced a result file

    def of_kind(self, kind: str) -> list[Case]:
        return [c for c in self.cases if c.kind == kind]


def _key(source_file, page_start) -> tuple[str, str]:
    """Chunks are identified by (source_file, page_start) as strings — page_start is text in the
    schema (printed page labels are not always numeric), so normalise both sides the same way."""
    return (str(source_file).strip(), str(page_start).strip())


def load_golden(path: pathlib.Path | None = None, corpus: list[dict] | None = None) -> Golden:
    """Parse the YAML and, when `corpus` is given, verify every `relevant` entry resolves.

    Passing `corpus` is strongly recommended — it is the check that turns a silent labelling
    error into a loud one.
    """
    try:
        import yaml
    except ImportError as exc:                                    # pragma: no cover
        raise SystemExit(
            "PyYAML is required to read the golden set — pip install -r requirements-eval.txt"
        ) from exc

    path = path or GOLDEN_PATH
    raw = path.read_bytes()
    body = yaml.safe_load(raw.decode("utf-8"))

    cases: list[Case] = []
    for entry in body["cases"]:
        cases.append(Case(
            id=entry["id"],
            query=entry["query"],
            kind=entry.get("kind", IN_DOMAIN),
            band_group=entry.get("band_group"),
            band=entry.get("band"),
            concept=entry.get("concept"),
            stage=entry.get("stage"),
            relevant=[_key(r["source_file"], r["page_start"]) for r in entry.get("relevant") or []],
        ))

    _check_shape(cases)
    if corpus is not None:
        _check_against_corpus(cases, corpus, body)

    return Golden(cases=cases, digest=hashlib.sha256(raw).hexdigest()[:12])


def _check_shape(cases: list[Case]) -> None:
    ids = [c.id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"golden set has duplicate case ids: {sorted(dupes)}")
    for c in cases:
        if c.expects_hits and not c.relevant:
            raise SystemExit(
                f"case {c.id!r} is kind=in_domain but lists no relevant chunks. An in-domain case "
                f"with no ground truth scores 0 recall no matter how good retrieval is — mark it "
                f"out_of_domain/empty_expected, or give it relevant chunks."
            )
        if not c.expects_hits and c.relevant:
            raise SystemExit(f"case {c.id!r} is kind={c.kind} but lists relevant chunks.")


def _check_against_corpus(cases: list[Case], corpus: list[dict], body: dict) -> None:
    """Every referenced chunk must exist, and its recorded title should still match."""
    index = {_key(r.get("source_file"), r.get("page_start")): r for r in corpus}

    missing: list[str] = []
    drifted: list[str] = []
    for entry, case in zip(body["cases"], cases):
        for ref in entry.get("relevant") or []:
            key = _key(ref["source_file"], ref["page_start"])
            row = index.get(key)
            if row is None:
                missing.append(f"  {case.id}: {key[0]!r} p.{key[1]}")
                continue
            want = (ref.get("title") or "").strip().lower()
            got = (row.get("activity_title") or "").strip().lower()
            # `title` is documentation, so drift is a warning — but it is exactly the signal that
            # the corpus was re-parsed and the labels may no longer mean what they did.
            if want and not got.startswith(want[:40]):
                drifted.append(f"  {case.id}: {key[0]!r} p.{key[1]}\n"
                               f"      golden: {want[:70]!r}\n      corpus: {got[:70]!r}")

    if drifted:
        print("WARNING — golden titles drifted from the corpus (matching still used "
              "source_file+page_start):")
        print("\n".join(drifted))

    if missing:
        raise SystemExit(
            "golden set references chunks that are NOT in the corpus:\n"
            + "\n".join(missing)
            + "\n\nFix the references (or re-ingest). Refusing to score against a ground truth "
              "that does not match the corpus — every metric would be quietly wrong."
        )


def load_corpus() -> list[dict]:
    """All lesson_plan chunks, for resolving golden references. Needs live Supabase."""
    from app.core.supabase_client import get_supabase

    rows, start, page = [], 0, 1000
    while True:
        batch = (
            get_supabase().table("curriculum_chunks")
            .select("id,band,concept,stage,activity_title,source_file,page_start,content_md")
            .eq("doc_type", "lesson_plan")
            .range(start, start + page - 1)
            .execute()
            .data
        )
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page
