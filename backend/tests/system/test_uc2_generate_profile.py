"""SYSTEM use case: UC2 "Therapist generates a learner profile".

Real headless Chrome driving the real built UI against the real backend + Supabase test project —
no fakes anywhere in the stack. "Generate Profile" lives on the learner detail page, next to UC3's
"Generate Activity".

    ST-2.1  learner with sittings -> the promotion completes and the visualisation is on screen
    ST-2.2  learner with no scores -> the 409 opens UC1's upload flow instead of erroring

ONLY TWO OF THE PLAN'S FOUR ST-2 BRANCHES ARE REACHABLE, AND THE OTHER TWO ARE NOT COMING BACK.
ST-2.3 and ST-2.4 were written against `NoPatternError` and `ProfileGenerationError`. Both were
deleted with `ProfilingAlgorithm.analyse()` and the `learner_profiles` table; UC2 is now a
*promotion* — read the newest `learner_sittings` row and make it the learner's current marks — and
a promotion derives nothing, so it cannot fail to find a pattern. `NoScoresError` (409) is the one
error left. See backend/tests/README.md ("UC2 traceability") for the full void-bar table. Do not
re-add ST-2.3/ST-2.4 from the PDF: there is no code path that raises them.

WHY ST-2.2 ASSERTS AN UPLOAD MODAL RATHER THAN AN ERROR BANNER.
The amber "no assessment scores yet" banner on this page belongs to UC3, not UC2 — it is keyed off
`activityResult.status === "INSUFFICIENT_CONTEXT"`. UC2's 409 is handled separately at
`LearnerDetailPage.jsx:117-119`: a learner with no scores is not an error the therapist can retry
out of, it is the cue to upload one, so the handler opens `UploadView`. The modal's
"Upload Assessment Data" heading is therefore the observable postcondition of UC2's alternative
flow. Asserting the banner here would pass for the wrong reason (a leftover UC3 refusal) or fail
for the wrong reason (UC2 behaving correctly).

Requesting `system_creds` before `driver` means these skip (without launching Chrome) when the env
is absent. TEST_LEARNER_ID / TEST_UNSCORED_LEARNER_ID gate the two cases independently, and are the
same two learners UC3's system tests use.
"""
import os

import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system

GENERATE_BUTTON = "//button[normalize-space()='Generate Profile']"
BUSY_BUTTON = "//button[normalize-space()='Generating...']"
UPLOAD_MODAL = "//h2[normalize-space()='Upload Assessment Data']"
NO_MARKS_EMPTY_STATE = "//*[normalize-space()='No DIAL marks']"
DEFICIENCY_HEADING = "//h2[normalize-space()='Skill Deficiency Alerts']"


def _fail_on_browser_alert(driver):
    """Turn UC2's failure path into a readable assertion instead of a hung session.

    `handleGenerateProfile` reports anything that is NOT a 409 through a bare `alert()`
    (LearnerDetailPage.jsx:121). A native dialog blocks every subsequent WebDriver command, so a
    real backend failure would surface as a 20-second timeout with no clue in it. Reading the text
    and dismissing it puts the actual error in the test output.
    """
    try:
        alert = driver.switch_to.alert
    except NoAlertPresentException:
        return
    text = alert.text
    alert.accept()
    pytest.fail(f"Generate Profile raised a browser alert: {text}")


def _open_learner(driver, frontend_url, creds, learner_id):
    """Signed in and sitting on one learner's detail page, with the actions rendered."""
    login(driver, frontend_url, creds["email"], creds["password"])
    # Direct route, like test_uc3_generate_activity.py: the session survives in localStorage, so
    # main.jsx re-renders the Dashboard and BrowserRouter serves /learners/<id>.
    driver.get(f"{frontend_url}/learners/{learner_id}")
    WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, GENERATE_BUTTON))
    ).click()
    # The button reads "Generating..." while the POST is in flight. Waiting for it to settle back
    # is what proves the request COMPLETED — asserting on the page while it is still pending would
    # read the pre-click state and pass for a request that never returned.
    WebDriverWait(driver, 30).until_not(
        EC.presence_of_element_located((By.XPATH, BUSY_BUTTON))
    )
    _fail_on_browser_alert(driver)


def test_generate_profile_renders_the_visualisation(system_creds, driver, frontend_url):
    """ST-2.1: the operational flow. The therapist promotes a learner's newest sitting and the
    profile is visualised on the dashboard — the use case's stated postcondition.

    NOTE, the same caveat ST-3.1 carries: a learner who already has marks shows the radar chart
    BEFORE the click too, so the charts alone are not proof of a NEW promotion. What this pins is
    that the request resolved without the 409 branch and without an error alert, and that the page
    re-read into a scored state rather than the empty one. ST-2.2 is the sharp, deterministic half.
    """
    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner with DIAL marks in the test project")

    _open_learner(driver, frontend_url, system_creds, learner_id)
    wait = WebDriverWait(driver, 20)

    # The profile IS the four DIAL marks, so the deficiency panel — rendered only when at least one
    # metric is assessed (LearnerDetailPage.jsx:176, 295) — is the visualisation's presence check.
    wait.until(EC.presence_of_element_located((By.XPATH, DEFICIENCY_HEADING)))

    # And the negative half: the "DIAL Assessment" card is showing the chart, not its empty state.
    assert not driver.find_elements(By.XPATH, NO_MARKS_EMPTY_STATE), (
        "profile generated but the DIAL Assessment card still shows 'No DIAL marks' — "
        "the promotion did not reach the overview the page re-reads"
    )
    # A successful promotion is not the no-scores branch: UC1's modal must not have opened.
    assert not driver.find_elements(By.XPATH, UPLOAD_MODAL)


def test_generate_profile_for_an_unscored_learner_opens_the_upload_flow(
    system_creds, driver, frontend_url
):
    """ST-2.2: the alternative flow, deterministic and the reason UC1 exists. A learner with no
    sittings has nothing to promote, so `ProfilingService` raises `NoScoresError` and the router
    maps it to 409. The page turns that into UC1's upload modal rather than an error.

    409 and not 404 is load-bearing here: the learner exists and the request was well-formed, the
    resource is just not in a state that can satisfy it yet. Collapsing the two would leave the UI
    unable to tell "no such learner" from "no scores yet". See backend/tests/README.md.
    """
    learner_id = os.environ.get("TEST_UNSCORED_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_UNSCORED_LEARNER_ID to a learner that has no DIAL marks")

    _open_learner(driver, frontend_url, system_creds, learner_id)
    wait = WebDriverWait(driver, 20)

    # The postcondition: UC1's upload flow, opened on this learner and pre-selected.
    wait.until(EC.presence_of_element_located((By.XPATH, UPLOAD_MODAL)))

    # No profile was generated, so the scored-state panel must NOT have appeared. Without this the
    # test would still pass if the 409 branch AND a successful promotion both somehow ran.
    assert not driver.find_elements(By.XPATH, DEFICIENCY_HEADING)
