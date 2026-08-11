"""SYSTEM use case: UC9 "Therapist views their learners".

Real browser (headless Chrome) driving the real built UI against the real
backend + Supabase test project — no fakes anywhere in the stack.

    ST-9.1  therapist views their learner list  -> cards + count render
    ST-9.2  search filters the list server-side -> matching card remains, "No learners match"
    ST-9.3  the "My caseload only" toggle       -> cohort note appears, then back to caseload

These mirror the doc's ST-9 rows. The empty-caseload and DB-failure branches are
not driven here — they need a zero-learner DB / an unreachable DB, which is
exactly what the hermetic integration tier (IT-9.2, IT-9.3) covers instead.
"""
import time

import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system

# A seeded caseload learner (infra/seed.sql) — its card is the proof the grid rendered.
SEEDED_PSEUDONYM = "Aisha Binti Rahman"
TOGGLE = "//button[normalize-space()='My caseload only']"
SEARCH_BOX = "//input[@aria-label='Search learners']"


@pytest.fixture
def learners_tab(system_creds, driver, frontend_url):
    """Signed in and sitting on the Learners tab, with the grid settled.

    Skips when the test project has no seeded learners (empty grid) — the e2e tier
    does the same, so an unseeded checkout stays green instead of timing out.
    """
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    # Direct route, like test_uc7_share.py: the session survives in localStorage,
    # so main.jsx re-renders the Dashboard and BrowserRouter serves /learners.
    driver.get(f"{frontend_url}/learners")
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.XPATH, SEARCH_BOX)))

    # Poll the body: the grid either shows a card or the empty-caseload message.
    # Skeletons during loading contain neither, so this cannot false-skip mid-fetch.
    for _ in range(40):
        body = driver.find_element(By.TAG_NAME, "body").text
        if SEEDED_PSEUDONYM in body:
            return
        if "No learners" in body:
            pytest.skip("test project has no seeded learners; seed infra/seed.sql for UC9")
        time.sleep(0.5)
    pytest.fail("Learners tab did not settle into a list or an empty state")


# ST-9.1 — the happy path: the therapist lands on their learner list.
def test_learner_cards_render(learners_tab, driver):
    wait = WebDriverWait(driver, 15)

    # A real card from the seeded caseload, proving the grid (not just the shell) rendered.
    wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//*[normalize-space()='{SEEDED_PSEUDONYM}']")))

    # The count line is the pager's "1-24 of N" — total came back from the server.
    assert driver.find_elements(By.XPATH, "//*[contains(text(), 'Showing')]")


# ST-9.2 — search runs server-side, so the grid reflects the query, not the full list.
def test_search_filters_the_list(learners_tab, driver):
    wait = WebDriverWait(driver, 15)
    search = driver.find_element(By.XPATH, SEARCH_BOX)

    # A match narrows the grid: the matching card stays, a different one disappears.
    search.send_keys("Aisha")
    wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//*[normalize-space()='{SEEDED_PSEUDONYM}']")))
    wait.until(EC.invisibility_of_element_located(
        (By.XPATH, "//*[normalize-space()='Benjamin Lim Wei']")))

    # A query with no hits renders the search-empty state, not a bare grid.
    search.clear()
    search.send_keys("zzz")
    wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'No learners match')]")))


# ST-9.3 — the assigned-vs-all toggle: off widens to the cohort, back on narrows to the caseload.
def test_caseload_toggle_reveals_the_cohort(learners_tab, driver):
    wait = WebDriverWait(driver, 15)
    toggle = driver.find_element(By.XPATH, TOGGLE)

    # Toggle off -> the "includes the anonymised DAS research cohort" note joins the count.
    # contains(., ...) not contains(text(), ...): the note shares the <p> with the count line.
    toggle.click()
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[contains(., 'includes the anonymised DAS research cohort')]")))

    # Toggle back on -> the note disappears, returning to the caseload-only view.
    toggle.click()
    wait.until(EC.invisibility_of_element_located(
        (By.XPATH, "//*[contains(., 'includes the anonymised DAS research cohort')]")))
