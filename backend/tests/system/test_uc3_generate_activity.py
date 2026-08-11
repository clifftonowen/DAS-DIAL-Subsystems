"""SYSTEM use case: UC3 "Therapist generates an adaptive learning activity" (includes UC5 retrieval).

Real headless Chrome driving the real built UI against the real backend + Supabase test project —
no fakes anywhere in the stack. Generation now lives on the learner detail page (the standalone
Generate tab was removed), so this drives the "Generate Activity" button there.

    ST-3.1  request an activity   -> the system reaches a valid outcome (activity OR a refusal)
    ST-3.2  learner with no scores -> refused before the LLM, with the "no scores" message

WHY ST-3.1 ASSERTS "A VALID OUTCOME" RATHER THAN A SPECIFIC ACTIVITY.
The system tier drives a SEPARATE backend process, so it cannot swap in a deterministic LLM the way
the in-process e2e tier does (LLMApiClient.use_provider). A real generated activity needs a real
model (Ollama), absent in CI. Both UC3 endings are correct per the use case — a VALIDATED activity,
or a documented refusal — so ST-3.1 proves the request resolved to one of them rather than crashing.
ST-3.2 is the deterministic half: with no DIAL marks the service refuses BEFORE retrieval or the
model, so it needs no LLM at all — the CI-friendly proof.

UC5 (Retrieve Instructional Strategy) has no UI of its own — its trigger is "UC3 reaches the
retrieval step" — so it is exercised implicitly inside generation here, not as a separate ST case.

Requesting `system_creds` before `driver` means these skip (without launching Chrome) when the env
is absent. TEST_LEARNER_ID / TEST_UNSCORED_LEARNER_ID gate the two cases independently.
"""
import os

import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system

GENERATE_BUTTON = "//button[normalize-space()='Generate Activity']"
REFUSAL_TEXT = (
    "//*[contains(text(),'no assessment scores yet') "
    "or contains(text(),'Not enough curriculum grounding') "
    "or contains(text(),'Could not generate activity')]"
)


def test_generate_activity_reaches_a_valid_outcome(system_creds, driver, frontend_url):
    """ST-3.1: the operational flow. Requesting an activity resolves to a valid UC3 outcome — a
    validated activity (its ReviewSection renders #review-text) OR a documented refusal — never a
    crash or a silent nothing.

    NOTE: if the learner already has an activity on file, #review-text is present before the click,
    so this is a smoke check that generation runs and the page stays healthy, not proof of a NEW
    activity. The deterministic, sharper assertion is ST-3.2.
    """
    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner with marks + a band")

    wait = WebDriverWait(driver, 30)
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    driver.get(f"{frontend_url}/learners/{learner_id}")

    wait.until(EC.element_to_be_clickable((By.XPATH, GENERATE_BUTTON))).click()

    # A validated activity renders the review box; a refusal renders one of the refusal banners.
    wait.until(lambda d: d.find_elements(By.ID, "review-text")
                         or d.find_elements(By.XPATH, REFUSAL_TEXT))


def test_generate_refuses_for_a_learner_with_no_scores(system_creds, driver, frontend_url):
    """ST-3.2: alternative flow, deterministic and LLM-free. With no DIAL marks the query is empty,
    so generation refuses BEFORE retrieval or the model — the "no scores" message appears and no
    activity is produced."""
    learner_id = os.environ.get("TEST_UNSCORED_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_UNSCORED_LEARNER_ID to a learner that has no DIAL marks")

    wait = WebDriverWait(driver, 20)
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    driver.get(f"{frontend_url}/learners/{learner_id}")

    wait.until(EC.element_to_be_clickable((By.XPATH, GENERATE_BUTTON))).click()

    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='This learner has no assessment scores yet']")
    ))
    # A refusal is not an activity: no review box appears for a learner who has never had one.
    assert not driver.find_elements(By.ID, "review-text")
