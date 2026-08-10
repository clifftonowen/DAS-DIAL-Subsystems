"""SYSTEM/UI E2E — UC4 from therapist input back to therapist output."""
import os
import uuid

import pytest

pytest.importorskip("selenium")

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system


def test_therapist_submits_and_sees_a_review(
    system_creds, uc4_activity, driver, frontend_url,
):
    marker = f"UC4 browser review {uuid.uuid4().hex}"
    learner_id = os.environ["TEST_LEARNER_ID"]
    wait = WebDriverWait(driver, 20)

    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    driver.get(f"{frontend_url}/learners/{learner_id}")

    textbox = wait.until(EC.presence_of_element_located((By.ID, "review-text")))
    # Let the initial GET /reviews finish before submitting. Otherwise a slow
    # empty-list response could arrive after the POST and overwrite the newly
    # prepended review in component state.
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='No reviews yet.']")
    ))
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
    driver.get(f"{frontend_url}/learners/{learner_id}")

    textbox = wait.until(EC.presence_of_element_located((By.ID, "review-text")))
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='No reviews yet.']")
    ))
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
    driver.get(f"{frontend_url}/learners/{learner_id}")
    textbox = wait.until(EC.presence_of_element_located((By.ID, "review-text")))
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='No reviews yet.']")
    ))

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
