"""SYSTEM use case: UC6 "Therapist logs in" — alternative flows.

Real headless Chrome driving the real built UI against the real backend and the
Supabase test project. Derived from the UC6 use case document: alternative flows
3a (wrong password) and 1a (incomplete form).

ST-6.1, the operational flow, is already covered by
`test_login_and_dashboard.py::test_login_shows_dashboard_shell` — not duplicated
here.

Requesting `system_creds` BEFORE `driver` means the test skips without launching
Chrome when the env is absent.
"""
import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.webdriver.common.by import By

from tests.system._helpers import feedback, is_signed_in

pytestmark = pytest.mark.system


def test_wrong_password_keeps_the_therapist_signed_out(system_creds, driver, frontend_url):
    """ST-6.2: an error is visible, the profile menu never appears, and the app
    stays on the login view."""
    driver.get(frontend_url)
    driver.find_element(By.ID, "email").send_keys(system_creds["email"])
    driver.find_element(By.ID, "password").send_keys("definitely-wrong")
    driver.find_element(
        By.XPATH, "//button[@type='submit' and normalize-space()='Log in']"
    ).click()

    role, text = feedback(driver)

    assert role == "alert"
    assert text.strip()
    assert not is_signed_in(driver)
    # Still the login view: the form is still mounted.
    assert driver.find_elements(By.ID, "password")


def test_submitting_without_an_email_does_not_sign_in(system_creds, driver, frontend_url):
    """ST-6.3: alternative flow 1a. AuthView sets `noValidate`, so the browser
    does NOT block submission — the request goes out and AuthController rejects it
    with 422. Either way the observable outcome is the same and is what UC6
    specifies: an error, and the therapist remains signed out."""
    driver.get(frontend_url)
    driver.find_element(By.ID, "password").send_keys(system_creds["password"])
    driver.find_element(
        By.XPATH, "//button[@type='submit' and normalize-space()='Log in']"
    ).click()

    role, text = feedback(driver)

    assert role == "alert"
    # Proves api.js unpacked FastAPI's 422 `detail` list instead of rendering
    # "[object Object]" — see lib/api.js errorMessage().
    assert "object" not in text.lower()
    assert not is_signed_in(driver)
