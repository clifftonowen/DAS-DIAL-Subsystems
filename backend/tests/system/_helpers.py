"""Shared helpers for Selenium system tests (not a test module)."""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def login(driver, base_url, email, password, timeout=20):
    """Drive the real AuthView login form, then wait for the dashboard.

    Selectors come straight from AuthView.jsx (#email, #password, the "Log in"
    submit button) and the authenticated shell ("My Profile" in the header).
    """
    driver.get(base_url)
    wait = WebDriverWait(driver, timeout)

    wait.until(EC.presence_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(
        By.XPATH, "//button[@type='submit' and normalize-space()='Log in']"
    ).click()

    # Dashboard shell renders the profile menu once the session is established.
    # The trigger is a <button> that also holds the avatar initial, so its full
    # text is e.g. "O My Profile" — match with contains(), not exact equality.
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//button[contains(., 'My Profile')]")
    ))


def sign_up(driver, base_url, email, password, timeout=20):
    """Drive the real AuthView sign-up form (UC8).

    AuthView starts in login mode; the ghost button flips it to sign-up, after
    which the submit button reads "Sign up". Does NOT wait for a dashboard: with
    email confirmation enabled UC8 ends with the therapist still signed out.
    """
    driver.get(base_url)
    wait = WebDriverWait(driver, timeout)

    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Need an account? Sign up']")
    )).click()

    wait.until(EC.presence_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(
        By.XPATH, "//button[@type='submit' and normalize-space()='Sign up']"
    ).click()


def feedback(driver, timeout=20):
    """Wait for AuthView's outcome message and return (role, text).

    AuthView renders a success notice as role="status" and a failure as
    role="alert" — the two outcomes of the `alt` fragment in both diagrams.
    """
    wait = WebDriverWait(driver, timeout)
    element = wait.until(
        lambda d: next(
            iter(d.find_elements(By.CSS_SELECTOR, "[role='status'], [role='alert']")), None
        )
    )
    return element.get_attribute("role"), element.text


def is_signed_in(driver):
    """True when the authenticated shell rendered (the profile menu trigger)."""
    return bool(driver.find_elements(By.XPATH, "//button[contains(., 'My Profile')]"))


def skip_if_rate_limited(role, text):
    """Skip when the error on screen is Supabase's quota rather than a real refusal.

    The browser counterpart of tests/e2e/_helpers.py::skip_if_rate_limited — see
    that docstring for the causes and the real fix. Sign-up surfaces the quota as an
    ordinary error alert, so without this a spent quota looks like a genuine failure.
    """
    if role == "alert" and "rate limit" in text.lower():
        pytest.skip(
            f"Supabase rejected sign-up on quota: {text!r}. Turn OFF 'Confirm email' "
            "on the test project, or raise the limit under Authentication -> Rate "
            "Limits. See tests/e2e/_helpers.py::skip_if_rate_limited."
        )
