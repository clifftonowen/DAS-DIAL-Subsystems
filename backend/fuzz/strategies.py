"""The Test Generator box of the Week 11 pipeline.

Four strategies, matching the lecture's taxonomy one for one. Each is a generator of inputs; none
of them knows anything about oracles or about what counts as a failure.

    random     completely random bytes. The lecture's stated con is that modern input validation
               rejects these early, so we EXPECT it to find almost nothing. Measuring that is the
               point: it is the baseline the other three are justified against.
    mutation   start from a valid seed, apply one operator. Efficient near-valid inputs.
    grammar    generation-based: build a syntactically valid report from a small BNF, then let a
               few productions go wrong on purpose. Higher coverage, higher setup cost.
    coverage   feedback-guided: keep an input if the suite containing it reached new branches.
"""
from __future__ import annotations

import random

from fuzz import grammar as grammar_mod
from fuzz import mutators
from fuzz.corpus import Corpus
from fuzz.targets.base import Target


class Strategy:
    name = ""

    def __init__(self, target: Target, corpus: Corpus, rng: random.Random):
        self.target = target
        self.corpus = corpus
        self.rng = rng

    def next(self) -> bytes:
        raise NotImplementedError

    def observe(self, data: bytes, interesting: bool) -> None:
        """Called after every input. Only the feedback-guided strategy uses it."""


class RandomStrategy(Strategy):
    """Uniform random bytes, plus a printable-ASCII variant.

    Both are kept because they fail differently: raw bytes mostly die at the decode/format layer,
    while printable noise gets far enough to reach the regexes. Reporting them separately would
    be more precise, but the headline number the report needs is simply "random found N".
    """

    name = "random"

    def next(self) -> bytes:
        size = self.rng.randrange(0, 512)
        if self.rng.random() < 0.5:
            return bytes(self.rng.randrange(256) for _ in range(size))
        printable = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .:,-\n"
        return "".join(self.rng.choice(printable) for _ in range(size)).encode()


class MutationStrategy(Strategy):
    """Pick something known-interesting, change one thing about it.

    The corpus is seeded from the target's valid examples and grows as the campaign finds inputs
    worth keeping, so a long run drifts steadily further from the seeds without ever losing them.
    """

    name = "mutation"

    #: How many operators to stack on one input. AFL calls this the "havoc" stage, and skipping
    #: it was a real bug in the first version of this file: with exactly one operator per input,
    #: every candidate is a pristine seed plus one edit, so the search CANNOT compound. Measured
    #: on the `normalise` target, single-operator mutation found nothing in 95,000 executions,
    #: because reaching a 4,300-digit run takes several edits and no intermediate step is
    #: interesting enough to be kept. Stacking fixes that without needing coverage feedback.
    #: Powers of two, weighted towards the small end: most inputs stay near-valid (which is the
    #: whole point of mutation-based fuzzing) while a minority drift far enough to find the
    #: length-dependent defects.
    STACK_CHOICES = (1, 1, 1, 2, 2, 4, 8, 16, 32)

    def next(self) -> bytes:
        base = self.rng.choice(self.corpus.entries) if self.corpus else b""
        data = base
        for _ in range(self.rng.choice(self.STACK_CHOICES)):
            data = mutators.mutate(data, self.rng, max_size=self.target.max_size)
        return data


class GrammarStrategy(Strategy):
    """Generation-based: expand the target's BNF into a fresh input each time.

    Produces syntactically well-formed input by construction, so it gets past the guards that
    reject random noise and reaches the conversion logic underneath on nearly every execution.
    That is the "higher coverage" the lecture claims for it, and the grammar itself is the
    "higher setup cost".

    Falls back to random generation for a target that declares no grammar, so `--strategy grammar
    --target all` still runs rather than erroring out; the runner prints which targets fell back.
    """

    name = "grammar"

    def __init__(self, target: Target, corpus: Corpus, rng: random.Random):
        super().__init__(target, corpus, rng)
        self._fallback = RandomStrategy(target, corpus, rng) if target.grammar is None else None

    @property
    def using_grammar(self) -> bool:
        return self._fallback is None

    def next(self) -> bytes:
        if self._fallback is not None:
            return self._fallback.next()
        text = grammar_mod.expand(self.target.grammar, self.target.grammar_start, self.rng)
        return text.encode("utf-8")[: self.target.max_size]
