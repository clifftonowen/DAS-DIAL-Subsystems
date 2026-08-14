"""SYSTEM use case: UC7 "Share Learning Activity".

Real headless Chrome driving the real built UI against the real backend + Supabase test project.

    TC7a  valid address    -> "Activity sent to recipient"
    TC7b  invalid address  -> "Invalid email address, please re-enter"
    TC7c  render failure   -> "Could not export activity as PDF"
    TC7d  NOT TESTED — the email server returning a negative response needs a forced SMTP failure,
          which this tier has no way to induce. The branch is covered where it can be faked:
          UT-7.6 / UT-7.9 / UT-7.13 and IT-7.7 / IT-7.11.

These skip rather than fail without their environment, like every other system test: they need the
test-project credentials, a running backend and frontend, and the three TEST_*_ID secrets below.
TC7c additionally needs an activity that is known not to render.

A Playwright counterpart lives in frontend/e2e/share-activity.spec.js — same flow, same selectors,
so a UI change breaks both together. See frontend/e2e/README.md on the tier overlap.
"""
import os

import pytest

pytest.importorskip("selenium")  

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system

SHARE_BUTTON = "//button[normalize-space()='Share']"
SEND_BUTTON = "//button[@type='submit' and normalize-space()='Send']"
RETRY_BUTTON = "//button[@type='submit' and normalize-space()='Retry']"


# helper functions
def open_learner_with_an_activity(driver, base_url, timeout=20):
    #NOT TEST_LEARNER_ID — that secret is for UC2's profile test
    learner_id = os.environ.get("TEST_SHARE_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_SHARE_LEARNER_ID to a learner that has a generated activity")
    driver.get(f"{base_url}/learners/{learner_id}")
    wait = WebDriverWait(driver, timeout)
    share = wait.until(EC.element_to_be_clickable((By.XPATH, SHARE_BUTTON)))
    share.click()
    wait.until(EC.presence_of_element_located((By.ID, "share-email")))


def send_to(driver, address, button=SEND_BUTTON):
    driver.find_element(By.ID, "share-email").send_keys(address)
    driver.find_element(By.XPATH, button).click()


def alert_text(driver, timeout=20):
    element = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "share-error"))
    )
    return element.text



# System rejects invalid email format 
def test_an_invalid_address_prompts_re_entry(system_creds, driver, frontend_url):
    
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    open_learner_with_an_activity(driver, frontend_url)
    send_to(driver, "a@b")

    assert "Invalid email address, please re-enter" in alert_text(driver)
    # Therapist can correct it in place when the form is still there
    assert driver.find_elements(By.ID, "share-email")
    assert not driver.find_elements(
        By.XPATH, "//*[contains(text(), 'Activity sent to recipient')]")

# System handles failure to render the learning activity as PDF
def test_a_render_failure_is_reported_without_a_retry(system_creds, driver, frontend_url):
    activity_id = os.environ.get("TEST_UNRENDERABLE_ACTIVITY_ID")
    if not activity_id:
        pytest.skip("set TEST_UNRENDERABLE_ACTIVITY_ID ")
    learner_id = os.environ.get("TEST_UNRENDERABLE_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_UNRENDERABLE_LEARNER_ID")
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    driver.get(f"{frontend_url}/learners/{learner_id}")
    wait = WebDriverWait(driver, 20)
    wait.until(EC.element_to_be_clickable((By.XPATH, SHARE_BUTTON))).click()
    wait.until(EC.presence_of_element_located((By.ID, "share-email")))

    send_to(driver, "parent@example.com")

    text = alert_text(driver)
    assert "export" in text.lower()
    assert not driver.find_elements(By.XPATH, RETRY_BUTTON)
    assert not driver.find_elements(
        By.XPATH, "//*[contains(text(), 'Activity sent to recipient')]")



# Send is success
def test_a_valid_address_confirms_the_share(system_creds, driver, frontend_url):
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    open_learner_with_an_activity(driver, frontend_url)

    send_to(driver, "parent@example.com")

    WebDriverWait(driver, 20).until(EC.presence_of_element_located(
        (By.XPATH, "//*[contains(text(), 'Activity sent to recipient')]")
    ))
    # The form is replaced by the confirmation, so it cannot be sent twice.
    assert not driver.find_elements(By.XPATH, SEND_BUTTON)

