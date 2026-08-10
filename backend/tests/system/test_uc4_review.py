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
