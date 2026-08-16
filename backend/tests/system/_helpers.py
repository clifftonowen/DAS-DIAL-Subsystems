"""Shared helpers for Selenium system tests (not a test module)."""
import os

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Where the API is, for the direct pre-checks below. The browser reaches it through the built
# frontend's VITE_API_URL; these helpers bypass the browser, so they need it themselves.
API_URL = os.environ.get("SYSTEM_API_URL", "http://127.0.0.1:8000")


def require_endpoints(email, password, *paths, timeout=15):
    """GET each path directly and fail NOW if the API answers with an error.

    WHY THIS EXISTS: a browser wait cannot tell "slow" from "broken", and UploadView's metadata
    fetch swallows its own failure (`catch {}` at UploadView.jsx:56 — deliberately, because the
    form still works without the rubric). So when GET /assessments/semesters returned 500, the
    only symptom was a semester select stuck on "Loading…". The Selenium wait polled it for the
    full 30 seconds and then reported a message that GUESSED at the cause, three times in a row,
    for a 500 that was never going to become a 200.

    That happened for real on CI run 31787431067: a ~90-second window in which every Supabase
    data-plane call raised `httpx.RemoteProtocolError: Server disconnected`, so
    /assessments/semesters and /learners both answered 500 while /assessments/metrics (which
    touches no database) kept answering 200. Three tests spent 30s each discovering that.

    Calling the endpoint once, first, turns those 30 seconds into an immediate failure that names
    the endpoint and the status. It does not make the flake less likely — nothing here can — it
    makes it legible, and it distinguishes "the API is down" from "UC1 is broken".

    httpx rather than requests: supabase-py already depends on it, so it is guaranteed present.
    """
    import httpx

    try:
        session = httpx.post(
            f"{API_URL}/auth/login", json={"email": email, "password": password}, timeout=timeout,
        )
    except httpx.HTTPError as exc:
        pytest.fail(f"the backend at {API_URL} is not reachable: {exc!r}")
    if session.status_code != 200:
        pytest.fail(f"POST /auth/login -> {session.status_code}: {session.text[:300]}")

    headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
    for path in paths:
        try:
            response = httpx.get(f"{API_URL}{path}", headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            pytest.fail(f"GET {path} did not complete: {exc!r}")
        if response.status_code != 200:
            pytest.fail(
                f"GET {path} -> {response.status_code}, so this is an API failure rather than a "
                f"UC failure. Body: {response.text[:300]}"
            )


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


def sign_out(driver, timeout=20):
    """Open the profile menu and sign out, leaving the login form on screen.

    Selectors mirror test_profile_menu.py: the trigger's text is "<initial> My
    Profile", so it needs contains() rather than equality.
    """
    wait = WebDriverWait(driver, timeout)
    driver.find_element(By.XPATH, "//button[contains(., 'My Profile')]").click()
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//*[normalize-space()='Sign out']")
    )).click()
    wait.until(EC.presence_of_element_located((By.ID, "email")))


def signup_outcome(driver, timeout=20):
    """Wait for whichever of UC8's two success shapes the project produces.

    Returns ("signed_in", "") or (role, text) from `feedback`.

    UC8's positive branch ends differently depending on one project setting, and
    both endings satisfy the postcondition "the account exists and is usable":

    - "Confirm email" OFF -> Supabase issues a session at sign-up, so AuthView
      stores it and the therapist lands on the dashboard. No notice is rendered.
    - "Confirm email" ON  -> no session, so AuthView shows "Account is
      successfully created..." and returns to the login form, signed out.

    A test that waited only for the notice would fail on a correctly-behaving app
    whenever confirmation is disabled — which is the configuration the e2e tier
    needs, to keep sign-up off the email quota.
    """
    wait = WebDriverWait(driver, timeout)
    wait.until(lambda d: is_signed_in(d) or d.find_elements(
        By.CSS_SELECTOR, "[role='status'], [role='alert']"
    ))
    if is_signed_in(driver):
        return "signed_in", ""
    return feedback(driver, timeout=timeout)


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
