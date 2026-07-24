"""SYSTEM use case: "Therapist opens the profile menu and signs out".

Covers the top-right ProfileMenu ported from the skylar branch: the dropdown
shows the signed-in email, and Sign out returns to the auth screen.
"""
import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from tests.system._helpers import login

pytestmark = pytest.mark.system


def test_profile_dropdown_shows_email_and_signs_out(system_creds, driver, frontend_url):
    email = system_creds["email"]
    login(driver, frontend_url, email, system_creds["password"])
    wait = WebDriverWait(driver, 15)

    # Open the dropdown and confirm it reveals the signed-in email.
    driver.find_element(By.XPATH, "//*[normalize-space()='My Profile']").click()
    wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//*[contains(text(), '{email}')]")
    ))

    # Sign out -> back to the login form (#email reappears).
    driver.find_element(By.XPATH, "//*[normalize-space()='Sign out']").click()
    wait.until(EC.presence_of_element_located((By.ID, "email")))
