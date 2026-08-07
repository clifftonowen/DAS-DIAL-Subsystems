"""End-to-end generation evaluation: RAGAS metrics + the refusal contract (run from backend/).

    python -m evals.run_ragas --generator gemini --judge claude-opus-5
    python -m evals.run_ragas --generator claude --judge claude-opus-5
    python -m evals.run_ragas --generator gemini --refusal-only        # no ragas install needed

Needs requirements-eval.txt, EXCEPT for --refusal-only. Install it into a SEPARATE virtualenv:
ragas pulls the LangChain stack, and requirements.txt pins numpy==2.1.1 precisely because
langchain 0.3.0 caps numpy below 2 and broke CI at install time. Sharing one venv re-creates that.

WHY THE JUDGE IS A DIFFERENT VENDOR FROM THE GENERATOR. LLM judges systematically prefer text
from their own family, so scoring Gemini output with a Gemini judge inflates faithfulness by an
amount you cannot measure from inside the experiment. Claude judging Gemini keeps the bias out of
the comparison, and keeps historical scores meaningful when the generator changes.

WHAT IS MEASURED, and why these four:
  faithfulness                       Is every claim in the activity supported by the retrieved
                                     chunks? This is THE metric for this system — the entire
                                     design premise is "ground every step, never invent pedagogy".
  answer_relevancy                   Does the activity actually answer the request?
  LLMContextPrecisionWithoutReference Were the retrieved chunks the useful ones?
  NonLLMContextRecall                Did retrieval find the chunks the golden set says matter?
                                     Non-LLM on purpose — we have labelled reference CONTEXTS but
                                     no reference ANSWERS, and inventing reference answers to
                                     satisfy a metric would make that metric measure the invention.

The refusal check is deliberately NOT a RAGAS metric: it tests a contract RAGAS knows nothing
about. `model_refused()` matches INSUFFICIENT_CONTEXT on the FIRST LINE only, so a chattier model
that preambles before the sentinel defeats Guardrail 2 silently — the refusal is not detected and
a hallucinated activity is persisted as real curriculum. That failure is invisible to every score
above, which is exactly why it is checked separately.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

RESULTS_DIR = pathlib.Path(__file__).with_name("results")


# ── the real pipeline, one case at a time ─────────────────────────────────
def _generate(repo, llm, case, k: int, use_alt: bool) -> tuple[str, list[dict]]:
    """Retrieve + generate exactly as ActivityGenerationService does, minus the persistence.

    The gate is intentionally NOT applied here: we want the model's behaviour on thin grounding,
    which is the whole point of the refusal check.
    """
    from app.prompts.activity_prompts import SYSTEM_PROMPT, build_activity_prompt

    vector = llm.embed(case.query, is_query=True)
    chunks = repo.hybrid_match_curriculum(
        vector, case.query, band=case.band, band_group=case.band_group,
        concept=case.concept, stage=case.stage, match_count=k, use_alt=use_alt,
    )
    params = {"band": case.band_group, "concept": case.concept, "stage": case.stage}
    prompt = build_activity_prompt(chunks, {k2: v for k2, v in params.items() if v})
    return llm.complete(prompt, system=SYSTEM_PROMPT), chunks


def _context_texts(chunks: list[dict]) -> list[str]:
    """Chunks rendered EXACTLY as the prompt renders them.

    Reaching for the private _fmt_chunk rather than re-formatting here is the point: faithfulness
    asks whether the response is supported by the context, so the context handed to the judge has
    to be the text the model actually saw. Any prettier local version would score a different
    prompt than the one that ran.
    """
    from app.prompts.activity_prompts import _fmt_chunk

    return [_fmt_chunk(i, c) for i, c in enumerate(chunks, 1)]


def _reference_texts(case, corpus_index: dict) -> list[str]:
    """The chunks the golden set says SHOULD have been retrieved, rendered like the real ones."""
    from app.prompts.activity_prompts import _fmt_chunk

    rows = [corpus_index[key] for key in case.relevant if key in corpus_index]
    return [_fmt_chunk(i, r) for i, r in enumerate(rows, 1)]


# ── run ───────────────────────────────────────────────────────────────────
def cmd_ragas(args: argparse.Namespace) -> int:
    from app.core.config import settings
    from app.gateways.llm_client import LLMApiClient
    from app.prompts.activity_prompts import model_refused
    from app.repositories.curriculum_repository import CurriculumRepository
    from evals.golden import load_corpus, load_golden

    settings.llm_provider = args.generator
    settings.embedding_provider = args.embedding_provider
    LLMApiClient.use_provider(None)
    llm = LLMApiClient()

    corpus = load_corpus()
    golden = load_golden(corpus=corpus)
    corpus_index = {(str(r["source_file"]), str(r["page_start"])): r for r in corpus}
    repo = CurriculumRepository()
    use_alt = args.column != "embedding"

    generator_model = {
        "gemini": settings.gemini_model,
        "claude": settings.claude_model,
        "ollama": settings.ollama_llm_model,
    }[args.generator]
    header = {
        "generator": args.generator,
        "generator_model": generator_model,
        "judge": args.judge,
        "embedding_provider": args.embedding_provider,
        "embedding_model": llm.embedding_model,
        "column": args.column,
        "k": args.k,
        "golden_digest": golden.digest,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print("=== generation eval ===")
    for key, value in header.items():
        print(f"  {key:>18}: {value}")

    # ── 1. refusal contract ───────────────────────────────────────────────
    print("\n--- refusal contract (out-of-domain must self-refuse on line 1) ---")
    refusals, refusal_rows = 0, []
    off_domain = [c for c in golden.cases if not c.expects_hits]
    for case in off_domain:
        text, chunks = _generate(repo, llm, case, args.k, use_alt)
        detected = model_refused(text)
        refusals += detected
        first = (text or "").strip().splitlines()[0][:70] if (text or "").strip() else "(empty)"
        # An EMPTY reply is its own failure: model_refused("") is False, so on the service path an
        # empty completion is persisted as an activity with no content.
        status = "REFUSED" if detected else ("EMPTY!" if not (text or "").strip() else "answered")
        print(f"  {case.id:<28} {status:<9} first line: {first!r}")
        refusal_rows.append({"id": case.id, "detected": detected,
                             "empty": not (text or "").strip(), "first_line": first})
    rate = refusals / len(off_domain) if off_domain else None
    print(f"\n  refusal detection rate: {refusals}/{len(off_domain)}"
          + (f" ({rate:.0%})" if rate is not None else ""))

    if args.refusal_only:
        _write(header, {"refusal_rate": rate}, refusal_rows, [], args.out)
        return 0

    # ── 2. RAGAS ──────────────────────────────────────────────────────────
    samples = []
    print("\n--- generating in-domain activities for RAGAS ---")
    for case in golden.of_kind("in_domain"):
        text, chunks = _generate(repo, llm, case, args.k, use_alt)
        samples.append({
            "user_input": case.query,
            "response": text,
            "retrieved_contexts": _context_texts(chunks),
            "reference_contexts": _reference_texts(case, corpus_index),
            "_id": case.id,
        })
        print(f"  {case.id:<28} {len(text or '')} chars from {len(chunks)} chunks")

    scores = _score_with_ragas(samples, args.judge)
    print("\n--- RAGAS ---")
    for name, value in scores.items():
        print(f"  {name:>34}: {value:.4f}" if isinstance(value, float) else
              f"  {name:>34}: {value}")

    # nan means every sample for that metric errored — a judge that could not authenticate, time
    # out, or parse. It is NOT a score of zero and must never be read as one, so say so loudly
    # rather than letting it sit in a results file looking like a measurement.
    broken = [n for n, v in scores.items() if isinstance(v, float) and v != v]
    if broken:
        print(f"\n  !! NO MEASUREMENT for: {', '.join(broken)}")
        print("     Every sample errored (auth / timeout / parse). Treat these as missing, not "
              "as low scores, and re-run before drawing any conclusion.")

    summary = {"refusal_rate": rate, **scores}
    out = _write(header, summary, refusal_rows, samples, args.out)
    print(f"\nwrote {out}")
    return 0


def _score_with_ragas(samples: list[dict], judge: str) -> dict:
    from app.core.config import settings

    try:
        from langchain_anthropic import ChatAnthropic
        from ragas import EvaluationDataset, evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness, LLMContextPrecisionWithoutReference, NonLLMContextRecall,
        )
    except ImportError as exc:
        raise SystemExit(
            f"RAGAS dependencies are not installed ({exc.name}).\n"
            "  pip install -r requirements-eval.txt   (use a SEPARATE venv — see the file header)\n"
            "  or run with --refusal-only, which needs none of them."
        ) from exc

    class _NoTemperatureWrapper(LangchainLLMWrapper):
        """ragas passes `temperature` on EVERY judge call; Claude 5 rejects it with a 400.

        ragas' LangchainLLMWrapper hardcodes `temperature=...` into both generate_prompt calls
        (there is no setting for it), and the Claude 5 family treats the parameter as removed
        rather than ignored — so every judge call 400s and every LLM-scored metric returns nan.
        These two overrides mirror ragas 0.2.6's own single-completion branch exactly, including
        the reshaping of `generations`, and drop only the temperature argument.

        Delete this the day either side changes: if ragas makes temperature optional, or if the
        judge is moved to a model that still accepts one.
        """

        def generate_text(self, prompt, n=1, temperature=None, stop=None, callbacks=None):
            result = self.langchain_llm.generate_prompt(
                prompts=[prompt] * n, stop=stop, callbacks=callbacks,
            )
            result.generations = [[g[0] for g in result.generations]]
            return result

        async def agenerate_text(self, prompt, n=1, temperature=None, stop=None, callbacks=None):
            result = await self.langchain_llm.agenerate_prompt(
                prompts=[prompt] * n, stop=stop, callbacks=callbacks,
            )
            result.generations = [[g[0] for g in result.generations]]
            return result

    # The key MUST be passed explicitly. ChatAnthropic looks for ANTHROPIC_API_KEY in the process
    # environment, but this app reads .env through pydantic-settings, which never exports to
    # os.environ — so the judge authenticates as nobody and every LLM-scored metric silently
    # returns nan while the run still exits 0. A nan is not a low score; it is no measurement.
    if not settings.anthropic_api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set — the judge cannot run and every LLM metric would "
            "come back nan. Set it in backend/.env."
        )
    # max_tokens is required by the Messages API. Sized generously on purpose: faithfulness first
    # decomposes the activity into atomic statements, and a long activity yields a long JSON list.
    # Truncate it and ragas raises LLMDidNotFinishException for that sample — which nans the WHOLE
    # metric, because ragas takes a plain mean and nan propagates. One truncated verdict therefore
    # costs all 20 scores, so this is not a place to economise.
    llm = _NoTemperatureWrapper(ChatAnthropic(
        model=judge,
        api_key=settings.anthropic_api_key,
        max_tokens=8192,
        timeout=180.0,      # one slow verdict should not nan out its whole metric either
        max_retries=3,
    ))
    dataset = EvaluationDataset.from_list([
        {k: v for k, v in s.items() if not k.startswith("_")} for s in samples
    ])
    # answer_relevancy is omitted deliberately: it needs an embedding model, and pointing it at
    # the same embedder under test would let the retriever grade its own homework.
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), LLMContextPrecisionWithoutReference(), NonLLMContextRecall()],
        llm=llm,
    )
    return {k: float(v) for k, v in result._repr_dict.items()} if hasattr(result, "_repr_dict") \
        else dict(result)


def _write(header, summary, refusal_rows, samples, out: str | None) -> pathlib.Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    name = out or f"ragas_{header['generator']}_{header['judge']}.json".replace(":", "-")
    path = RESULTS_DIR / name
    path.write_text(json.dumps({
        "header": header, "summary": summary,
        "refusal_cases": refusal_rows,
        "samples": [{k: v for k, v in s.items() if k != "reference_contexts"} for s in samples],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_ragas", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--generator", default="gemini", choices=("gemini", "claude", "ollama"))
    p.add_argument("--judge", default="claude-opus-5",
                   help="judge model — keep it a DIFFERENT vendor from --generator")
    p.add_argument("--embedding-provider", default="gemini",
                   choices=("gemini", "ollama", "openai"))
    p.add_argument("--column", default="embedding_alt", choices=("embedding", "embedding_alt"))
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--refusal-only", action="store_true",
                   help="run only the refusal contract check (needs no ragas install)")
    p.add_argument("--out", help="result filename inside evals/results/")
    p.set_defaults(func=cmd_ragas)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
