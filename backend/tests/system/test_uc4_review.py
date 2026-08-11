"""SYSTEM/UI E2E — UC4 from therapist input back to therapist output."""
import os
import uuid

import pytest

pytest.importorskip("selenium")

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system


def open_fixture_activity(driver, wait, frontend_url, learner_id, activity):
    """Open the learner page and prove the page is showing THIS run's activity.

    Every test here reviews "the activity on screen", which LearnerDetailPage picks as the
    learner's newest — true only while this run is the sole writer to the shared test project.
    When it is not (two CI runs once overlapped and each inserted an activity for the same
    learner), the tests below review or delete the wrong row and then wait 20s for an outcome
    that cannot arrive. Asserting the marker here converts that into an immediate failure that
    names the cause, instead of a bare TimeoutException pointing at an innocent line.
    """
    driver.get(f"{frontend_url}/learners/{learner_id}")
    textbox = wait.until(EC.presence_of_element_located((By.ID, "review-text")))
    try:
        wait.until(
            lambda current: activity["marker"] in current.find_element(By.TAG_NAME, "body").text
        )
    except TimeoutException:
        pytest.fail(
            f"the page is not showing this test's activity ({activity['id']}). Another writer "
            f"added a newer activity for learner {learner_id} in the shared test project — "
            f"check for a concurrent CI run or a stale row."
        )
    # Let the initial GET /reviews finish before submitting. Otherwise a slow empty-list
    # response could arrive after the POST and overwrite the newly prepended review.
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='No reviews yet.']")
    ))
    return textbox


def test_therapist_submits_and_sees_a_review(
    system_creds, uc4_activity, driver, frontend_url,
):
    marker = f"UC4 browser review {uuid.uuid4().hex}"
    learner_id = os.environ["TEST_LEARNER_ID"]
    wait = WebDriverWait(driver, 20)

    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    textbox = open_fixture_activity(driver, wait, frontend_url, learner_id, uc4_activity)

    textbox.send_keys(marker)
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Upload']")
    )).click()

    wait.until(lambda current: marker in current.find_element(By.TAG_NAME, "body").text)
    wait.until(lambda _current: textbox.get_attribute("value") == "")

    # Prove the result came back from the real database rather than only from
    # ReviewSection's local POST state.
    driver.refresh()
    wait.until(lambda current: marker in current.find_element(By.TAG_NAME, "body").text)


def test_therapist_approval_survives_a_page_refresh(
    system_creds, uc4_activity, driver, frontend_url,
):
    marker = f"UC4 browser approval {uuid.uuid4().hex}"
    learner_id = os.environ["TEST_LEARNER_ID"]
    wait = WebDriverWait(driver, 20)

    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    textbox = open_fixture_activity(driver, wait, frontend_url, learner_id, uc4_activity)

    textbox.send_keys(marker)
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Approve']")
    )).click()

    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='Therapist approved']")
    ))
    driver.refresh()
    wait.until(lambda current: marker in current.find_element(By.TAG_NAME, "body").text)
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='Therapist approved']")
    ))


def test_failed_database_submission_shows_an_error_and_no_review(
    system_creds, supabase_env, uc4_activity, driver, frontend_url,
):
    """TC4a: delete the loaded activity so the real FK rejects its review."""
    from supabase import create_client

    marker = f"UC4 browser rejected write {uuid.uuid4().hex}"
    learner_id = os.environ["TEST_LEARNER_ID"]
    wait = WebDriverWait(driver, 20)

    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    # Confirm the page is showing THIS activity before deleting it — the whole test rests on the
    # row the browser holds being the row that disappears. Deleting one the page never loaded
    # leaves the review to succeed against someone else's activity, and the assertion below then
    # waits for an error that is never coming. That is exactly how this failed in CI.
    textbox = open_fixture_activity(driver, wait, frontend_url, learner_id, uc4_activity)

    sb = create_client(supabase_env["url"], supabase_env["key"])
    sb.table("learning_activities").delete().eq(
        "id", uc4_activity["id"],
    ).execute()

    textbox.send_keys(marker)
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Upload']")
    )).click()

    wait.until(EC.text_to_be_present_in_element(
        (By.CSS_SELECTOR, "[role='alert']"), "Review could not be saved",
    ))
    assert driver.find_elements(By.XPATH, f"//li[contains(., '{marker}')]") == []
