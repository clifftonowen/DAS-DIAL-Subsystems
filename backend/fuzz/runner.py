"""The campaign runner.

    python -m fuzz.runner --strategy mutation --target assessment_text --seconds 30

The two things that make this a fuzzer rather than a test suite:

  1. It runs to a WALL-CLOCK BUDGET (`--seconds` / `--hours`), not to a fixed number of cases.
  2. It KEEPS GOING past the first failure, bucketing crashes by signature, so one overnight run
     reports "4 distinct defects" instead of stopping on the first one.

ON HANG DETECTION. A pure-Python fuzzer cannot interrupt a regex mid-backtrack: `signal.alarm`
does not exist on Windows and CPython will not deliver a signal to a thread stuck in the regex
engine anyway. So hangs are detected AFTER the fact by timing each input, and the worst case is
bounded instead by capping generated input size (`Target.max_size`). This is a real limitation
and is stated in the write-up rather than papered over.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fuzz import targets as target_registry
from fuzz.corpus import Corpus
from fuzz.dedup import FindingSet, format_traceback, signature
from fuzz.oracles import Finding, OracleKind, OracleViolation
from fuzz.strategies import GrammarStrategy, MutationStrategy, RandomStrategy, Strategy
from fuzz.targets.base import Target

FUZZ_ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = FUZZ_ROOT / "findings"
DEFAULT_CORPUS = FUZZ_ROOT / "corpus"

#: `coverage` is not a different generator, it is a different SELECTION rule wrapped around the
#: mutation generator, so it maps to the same class and is dispatched separately in `Campaign.go`.
STRATEGIES: dict[str, type[Strategy]] = {
    "random": RandomStrategy,
    "mutation": MutationStrategy,
    "grammar": GrammarStrategy,
    "coverage": MutationStrategy,
}


class Campaign:
    def __init__(
        self,
        target: Target,
        strategy_name: str,
        *,
        seed: int,
        hang_ms: float,
        corpus_root: Path,
    ):
        self.target = target
        self.strategy_name = strategy_name
        self.hang_ms = hang_ms
        self.rng = random.Random(seed)
        self.seed = seed

        self.corpus = Corpus(corpus_root / target.name)
        self.corpus.seed(target.seeds())

        strategy_cls = STRATEGIES[strategy_name]
        self.strategy = strategy_cls(target, self.corpus, self.rng)

        self.findings = FindingSet()
        self.execs = 0
        self.rejected = 0
        self.slowest_ms = 0.0
        self.generations = 0
        self.kept_generations = 0
        self.arcs_total: int | None = None

    def go(self, budget_seconds: float, progress_every: float = 10.0) -> None:
        """Dispatch to the right loop for the strategy."""
        if self.strategy_name == "coverage":
            self.run_coverage_guided(budget_seconds, progress_every)
        else:
            self.run(budget_seconds, progress_every)

    def run_one(self, data: bytes) -> tuple[bool, float]:
        """Execute one input. Returns (interesting, elapsed_ms)."""
        self.execs += 1
        started = time.perf_counter()
        exc: BaseException | None = None
        kind: OracleKind | None = None
        message = ""

        try:
            self.target.run(data)
        except OracleViolation as violation:
            exc, kind, message = violation, violation.kind, str(violation)
        except self.target.allowed:
            # The documented rejection path. Correct behaviour, not a finding.
            self.rejected += 1
        except Exception as crash:  # noqa: BLE001 - catching broadly IS the crash oracle
            exc, kind, message = crash, OracleKind.CRASH, f"{type(crash).__name__}: {crash}"

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.slowest_ms = max(self.slowest_ms, elapsed_ms)

        interesting = False
        if kind is not None:
            interesting |= self._record(kind, exc, message, data, elapsed_ms)

        # The hang oracle is independent of the outcome: an input that returns the right answer
        # after nine seconds is still a denial-of-service finding.
        if elapsed_ms >= self.hang_ms:
            interesting |= self._record(
                OracleKind.HANG,
                None,
                f"took {elapsed_ms:.0f} ms on {len(data)} bytes",
                data,
                elapsed_ms,
            )

        return interesting, elapsed_ms

    def _record(
        self,
        kind: OracleKind,
        exc: BaseException | None,
        message: str,
        data: bytes,
        elapsed_ms: float,
    ) -> bool:
        finding = Finding(
            kind=kind,
            signature=signature(kind, exc, self.target.name),
            message=message,
            input_bytes=data,
            input_len=len(data),
            elapsed_ms=elapsed_ms,
            traceback=format_traceback(exc) if exc is not None else "",
            strategy=self.strategy_name,
            target=self.target.name,
        )
        return self.findings.record(finding)

    def run_coverage_guided(self, budget_seconds: float, progress_every: float = 10.0) -> None:
        """Generate -> Execute -> Collect Feedback -> repeat, scoring a whole suite at a time.

        A generation is `SUITE_SIZE` mutated inputs. If the generation reached branch arcs no
        earlier generation reached, its inputs are promoted into the corpus, so later generations
        mutate from material that is known to explore new code. If it did not, the generation is
        discarded and the corpus is unchanged.

        See cov_feedback.py for why the unit of selection is a suite rather than an input; the
        short version is that per-input tracing measured 1344x slower.
        """
        from fuzz.cov_feedback import SUITE_SIZE, ArcTracker

        tracker = ArcTracker()
        deadline = time.perf_counter() + budget_seconds
        next_report = time.perf_counter() + progress_every
        started = time.perf_counter()
        self.generations = 0
        self.kept_generations = 0

        while time.perf_counter() < deadline:
            suite = [self.strategy.next() for _ in range(SUITE_SIZE)]
            keepers: list[tuple[bytes, float]] = []

            def run_suite() -> None:
                # The deadline is checked INSIDE the suite, not just between generations. A
                # generation is 1000 inputs, and on a target with a quadratic regex a handful of
                # them take tens of seconds each, so a purely per-generation check overshot a
                # 40-second budget by minutes when this was first written. Cutting a generation
                # short only makes its coverage sample smaller, which is harmless.
                for data in suite:
                    if time.perf_counter() >= deadline:
                        return
                    interesting, elapsed_ms = self.run_one(data)
                    if interesting and elapsed_ms < self.hang_ms:
                        keepers.append((data, elapsed_ms))

            arcs = tracker.measure(run_suite)
            self.generations += 1

            if tracker.new_arcs(arcs) > 0:
                self.kept_generations += 1
                wanted = arcs - tracker.seen
                tracker.absorb(arcs)
                # Promote only the inputs that actually reached the new arcs, not the whole
                # generation. See ArcTracker.attribute for why: bulk promotion poisoned the
                # corpus and made the guided run perform worse than the unguided one.
                def replay(data: bytes) -> None:
                    # Attribution re-runs inputs purely to see which lines they touch. Findings
                    # were already recorded on the first pass, so exceptions are swallowed here;
                    # letting one escape would abort the campaign at its most productive moment.
                    try:
                        self.target.run(data)
                    except Exception:  # noqa: BLE001
                        pass

                for data in tracker.attribute(suite, replay, wanted):
                    self.corpus.add(data)
            else:
                # Nothing new explored, so only the outright findings are worth keeping.
                for data, _ in keepers:
                    self.corpus.add(data)

            now = time.perf_counter()
            if now >= next_report:
                self._progress(now - started, arcs_total=tracker.total)
                next_report = now + progress_every

        self.arcs_total = tracker.total
        self._progress(time.perf_counter() - started, final=True, arcs_total=tracker.total)

    def run(self, budget_seconds: float, progress_every: float = 10.0) -> None:
        deadline = time.perf_counter() + budget_seconds
        next_report = time.perf_counter() + progress_every
        started = time.perf_counter()

        while time.perf_counter() < deadline:
            data = self.strategy.next()
            interesting, elapsed_ms = self.run_one(data)
            self.strategy.observe(data, interesting)

            # NEVER promote a slow input into the corpus, even though it is interesting.
            # Corpus entries are re-mutated forever, so admitting one 30-second input would make
            # every later generation drag it along and the campaign would grind to a halt. This
            # is the classic "slow unit" problem; AFL solves it by killing the child, which we
            # cannot do in-process, so we solve it by refusing to breed from it. The finding is
            # already recorded either way.
            if interesting and elapsed_ms < self.hang_ms:
                self.corpus.add(data)

            now = time.perf_counter()
            if now >= next_report:
                self._progress(now - started)
                next_report = now + progress_every

        self._progress(time.perf_counter() - started, final=True)

    def _progress(self, elapsed: float, final: bool = False, arcs_total: int | None = None) -> None:
        rate = self.execs / elapsed if elapsed else 0.0
        prefix = "done " if final else "     "
        extra = ""
        if arcs_total is not None:
            extra = (f" arcs={arcs_total} gens={self.kept_generations}/{self.generations} kept")
        print(
            f"{prefix}{self.target.name:16} {self.strategy_name:9} "
            f"execs={self.execs:>10,} {rate:>9,.0f}/s "
            f"rejected={self._rejected_pct():5.1f}% "
            f"findings={len(self.findings)} corpus={len(self.corpus)}{extra}",
            flush=True,
        )

    def _rejected_pct(self) -> float:
        return 100.0 * self.rejected / self.execs if self.execs else 0.0

    def summary(self, elapsed: float) -> dict:
        return {
            "target": self.target.name,
            "strategy": self.strategy_name,
            "seed": self.seed,
            "elapsed_seconds": round(elapsed, 2),
            "execs": self.execs,
            "execs_per_second": round(self.execs / elapsed, 1) if elapsed else 0.0,
            "rejected_pct": round(self._rejected_pct(), 2),
            "slowest_input_ms": round(self.slowest_ms, 1),
            "distinct_findings": len(self.findings),
            "corpus_size": len(self.corpus),
            "generations": self.generations,
            "generations_kept": self.kept_generations,
            "branch_arcs_reached": self.arcs_total,
            "findings": [
                {
                    "kind": f.kind.value,
                    "signature": f.signature,
                    "message": f.message,
                    "hits": f.count,
                    "shortest_input_bytes": f.input_len,
                    "shortest_input": f.input_bytes.decode("utf-8", errors="replace"),
                    "slowest_ms": round(f.elapsed_ms, 1),
                }
                for f in self.findings.findings
            ],
        }


def _write_artifacts(campaign: Campaign, out_dir: Path, summary: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    (out_dir / f"run-{campaign.target.name}-{campaign.strategy_name}-{stamp}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    inputs_dir = out_dir / "inputs"
    inputs_dir.mkdir(exist_ok=True)
    for finding in campaign.findings.findings:
        safe = finding.signature.replace(":", "_").replace("/", "_")
        (inputs_dir / f"{safe}.bin").write_bytes(finding.input_bytes)
        if finding.traceback:
            (inputs_dir / f"{safe}.trace.txt").write_text(finding.traceback, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fuzz.runner", description="DAS D.I.A.L fuzzer")
    parser.add_argument("--strategy", default="mutation", choices=sorted(STRATEGIES))
    parser.add_argument("--target", default="assessment_text",
                        help="target name, or 'all' to sweep every registered target")
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--hours", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed; omit for a time-based seed (printed, so runs are replayable)")
    parser.add_argument("--hang-ms", type=float, default=1000.0,
                        help="an input taking at least this long is reported as a hang")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.hours is not None:
        budget = args.hours * 3600.0
    elif args.seconds is not None:
        budget = args.seconds
    else:
        budget = 30.0

    seed = args.seed if args.seed is not None else random.randrange(2**31)
    chosen = target_registry.all_targets() if args.target == "all" else [target_registry.get(args.target)]

    print(f"seed={seed}  budget={budget:.0f}s  strategy={args.strategy}  "
          f"targets={', '.join(t.name for t in chosen)}", flush=True)

    per_target = budget / len(chosen)
    exit_code = 0
    for index, target in enumerate(chosen):
        campaign = Campaign(
            target,
            args.strategy,
            seed=seed + index,
            hang_ms=args.hang_ms,
            corpus_root=args.corpus,
        )
        started = time.perf_counter()
        campaign.go(per_target, progress_every=1e9 if args.quiet else 10.0)
        summary = campaign.summary(time.perf_counter() - started)
        _write_artifacts(campaign, args.out, summary)

        if summary["findings"]:
            exit_code = 1
            print(f"\n{target.name}: {len(summary['findings'])} distinct finding(s)")
            for item in summary["findings"]:
                print(f"  [{item['kind']:11}] {item['signature']}")
                print(f"                {item['message']}")
                print(f"                x{item['hits']} hits, shortest input "
                      f"{item['shortest_input_bytes']} bytes: {item['shortest_input'][:120]!r}")

    print(f"\nartifacts written to {args.out}", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
