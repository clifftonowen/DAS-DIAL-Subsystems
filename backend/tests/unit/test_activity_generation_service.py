"""UNIT — ActivityGenerationService.build_query(), the retrieval query behind UC3.

The learner's marks ARE the input to generation: the caller sends an id and a free-text steer,
and this method decides what the activity will be about. It is the whole of the personalisation,
so it is tested as a pure function of (profile, params) — no Supabase, no embedder, no LLM.

WHAT IT MUST GET RIGHT, and why each is a clinical claim rather than a formatting detail:

  ranked on the normalised score   a percentile is norm-referenced and cannot see a weakness the
                                   learner's whole band shares; the 0-10 score is what a
                                   remediation programme should aim at
  threshold, not a fixed count     naming a fixed two invents a weakness when only one exists,
                                   and hides one when three do
  unassessed is never zero         band A never sits the writing paper; scoring them 0/10 would
                                   hand 2,084 learners a writing activity they cannot attempt
  empty stays empty                GeneratePage reads an empty query as "no scores yet" and shows
                                   a different refusal for it (GeneratePage.jsx:117-121)
"""
import pytest

from app.prompts.activity_prompts import _fmt_profile
from app.services.activity_generation_service import WEAK_THRESHOLD, ActivityGenerationService

pytestmark = pytest.mark.unit

PREFIX = "literacy activity targeting "


@pytest.fixture
def build():
    """build_query alone. The service is not instantiated: the method touches only its arguments,
    and constructing one would build four repositories and an LLM client to test arithmetic."""
    return lambda profile, **params: ActivityGenerationService.build_query(None, profile, params)


def learner(**overrides):
    """A band A learner with three marks. Writing is None because band A never sits it."""
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "pseudonym": "Aisha Binti Rahman", "student_id": "Student 0142", "tier": "Tier 2",
        "band": "A2", "band_group": "A",
        "phonics": 12.0, "word_reading_accuracy": 7.0, "word_spelling": 4.0, "writing": None,
        "phonics_pct": 22.0, "word_reading_accuracy_pct": 61.0,
        "word_spelling_pct": 35.0, "writing_pct": None,
        **overrides,
    }


# ── which skills get named ────────────────────────────────────────────────────
def test_names_every_skill_below_the_threshold_weakest_first(build):
    """Phonics 12/50 = 2.4 and spelling 4/10 = 4.0 are weak; reading 7/10 = 7.0 is not."""
    assert build(learner()) == PREFIX + "phonics 2.4/10 and word spelling 4.0/10"


def test_names_only_one_skill_when_only_one_is_weak(build):
    """The count is not fixed at two. A learner with a single weakness gets a query aimed at it,
    not one half-aimed at a skill they are already solid on."""
    out = build(learner(word_spelling=6.0))

    assert out == PREFIX + "phonics 2.4/10"


def test_names_three_skills_when_three_are_weak(build):
    """The mirror case: a fixed two would silently drop the third."""
    out = build(learner(phonics=12.0, word_reading_accuracy=4.0, word_spelling=4.5, writing=9.0))

    # writing 9/30 = 3.0 sorts above phonics 2.4 but below both 4s
    assert out == PREFIX + (
        "phonics 2.4/10 and writing 3.0/10 and word reading 4.0/10 and word spelling 4.5/10"
    )


def test_falls_back_to_the_single_lowest_when_nothing_is_weak(build):
    """A learner doing well everywhere still gets an activity, aimed at their relative weak spot.

    Naming nothing would leave an empty query, which the frontend reads as "this learner has no
    assessment scores yet" — a false statement about a learner who has four.
    """
    out = build(learner(phonics=30.0, word_reading_accuracy=8.0, word_spelling=9.0))

    assert out == PREFIX + "phonics 6.0/10"
    assert all(s >= WEAK_THRESHOLD for s in (6.0, 8.0, 9.0)), "guard: none of these are weak"


# ── the scale ─────────────────────────────────────────────────────────────────
def test_scores_each_rubric_against_its_own_rounded_ceiling(build):
    """4/10 spelling and 12/30 writing are the same achievement and must read the same.

    This is the whole point of normalising: before it, sorting raw marks put every learner
    weakest at whichever paper had the smallest denominator.
    """
    out = build(learner(phonics=45.0, word_reading_accuracy=9.0, word_spelling=4.0, writing=12.0))

    assert "word spelling 4.0/10" in out
    assert "writing 4.0/10" in out


def test_a_full_phonics_paper_reads_below_ten(build):
    """46/46 is a perfect paper but scores 9.2, because the ceiling is rounded up to 50.

    Documented rather than fixed: the rounding is deliberate, and this is what it costs.
    """
    out = build(learner(phonics=46.0, word_reading_accuracy=10.0, word_spelling=10.0))

    assert out == PREFIX + "phonics 9.2/10", "the rounded ceiling costs a perfect paper 0.8"


def test_a_mark_above_the_rounded_ceiling_clamps_to_ten(build):
    """Nothing may exceed the scale the threshold is expressed on."""
    out = build(learner(phonics=60.0, word_reading_accuracy=9.0, word_spelling=9.5))

    assert out == PREFIX + "word reading 9.0/10", "phonics clamped to 10.0, so it is not lowest"


# ── what counts as assessed ───────────────────────────────────────────────────
def test_an_unassessed_metric_is_omitted_not_scored_zero(build):
    """Writing is None for every band A learner. Zero would make it the weakest skill every time
    and aim the activity at a paper they have never sat."""
    out = build(learner())

    assert "writing" not in out


def test_a_mark_with_no_percentile_is_still_scored(build):
    """Ingests predating the percentile columns left real marks with a null `_pct`. Ranking on
    the mark rather than the percentile brings those learners back in."""
    out = build(learner(phonics_pct=None, word_reading_accuracy_pct=None,
                        word_spelling_pct=None))

    assert out == PREFIX + "phonics 2.4/10 and word spelling 4.0/10"


def test_no_marks_at_all_returns_an_empty_query(build):
    """The signal GeneratePage uses to say "no assessment scores yet" rather than "not enough
    curriculum grounding". It must stay empty, not become a generic stub."""
    bare = {k: None for k in ("phonics", "word_reading_accuracy", "word_spelling", "writing")}

    assert build(bare) == ""
    assert build(None) == ""


def test_a_steer_alone_still_builds_a_query_without_marks(build):
    """A therapist who typed something gets it honoured even for an unscored learner."""
    assert build(None, notes="rhyming games") == "rhyming games"


# ── the caller's steer ────────────────────────────────────────────────────────
def test_objective_and_notes_append_after_the_marks_in_order(build):
    out = build(learner(), literacy_objective="short vowels", notes="rhyming games")

    assert out == PREFIX + (
        "phonics 2.4/10 and word spelling 4.0/10 — short vowels — rhyming games"
    )


def test_empty_steers_add_no_separator(build):
    """A blank notes box must not leave a trailing em dash on the stored query."""
    out = build(learner(), literacy_objective="", notes="")

    assert out.endswith("word spelling 4.0/10")


# ── the prompt agrees with the query ──────────────────────────────────────────
def test_the_prompt_states_the_same_scores_the_query_ranked_on(build):
    """Two denominators for one learner in one request would be incoherent to the model."""
    line = _fmt_profile(learner())

    assert "Phonics 12/46 = 2.4/10 (22 pct)" in line
    assert "Word Spelling 4/10 = 4.0/10 (35 pct)" in line
    assert "2.4/10" in build(learner())


def test_the_prompt_profile_stays_a_whitelist_of_marks(build):
    """`learners` carries 26 columns and completions go to a hosted model. Only the four marks
    and the band group may leave the machine."""
    line = _fmt_profile(learner())

    assert "Aisha" not in line
    assert "Student 0142" not in line
    assert "Tier 2" not in line
    assert "band A" in line


def test_the_prompt_omits_a_metric_with_no_mark(build):
    assert "Writing" not in _fmt_profile(learner())
    assert _fmt_profile({"phonics": None, "band_group": "A"}) == ""
