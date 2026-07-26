"""SYSTEM use case: UC8 "Therapist signs up".

Real headless Chrome driving the real built UI. Both tests CREATE a real account in
the Supabase test project, so both register the address with `cleanup_emails`.

UC8's positive branch has two legitimate endings, decided by one project setting,
and both satisfy the postcondition "the account exists and the therapist can use
it" — see `_helpers.signup_outcome`:

  "Confirm email" OFF -> a session is issued, so the therapist lands on the dashboard
  "Confirm email" ON  -> a notice is shown and they stay signed out until they confirm

These tests accept either, rather than hard-coding the one the project happens to
use today.
"""
import pytest

pytest.importorskip("selenium")

from selenium.webdriver.common.by import By

from tests.system._helpers import (
    is_signed_in,
    login,
    sign_out,
    sign_up,
    signup_outcome,
    skip_if_rate_limited,
)

pytestmark = pytest.mark.system

PASSWORD = "Passw0rd!123"


def test_sign_up_creates_an_account_the_therapist_can_use(
    system_creds, throwaway_email, cleanup_emails, driver, frontend_url
):
    """ST-8.1: the operational flow, end to end in a browser."""
    cleanup_emails(throwaway_email)

    sign_up(driver, frontend_url, throwaway_email, PASSWORD)
    role, text = signup_outcome(driver)
    skip_if_rate_limited(role, text)

    if role == "signed_in":
        # A session came back with the sign-up, so UC8's postcondition is already
        # demonstrated: the account exists and is authenticated.
        assert is_signed_in(driver)
        return

    assert role == "status", f"expected a success notice, got {role}: {text!r}"
    assert "successfully created" in text.lower()
    # Still signed out, so exercise the postcondition by logging in — UC8 feeding UC6.
    login(driver, frontend_url, throwaway_email, PASSWORD)
    assert is_signed_in(driver)


def test_signing_up_twice_with_the_same_email_is_refused(
    system_creds, throwaway_email, cleanup_emails, driver, frontend_url
):
    """ST-8.2: alternative flow — the second attempt shows an error, the form stays
    put, and no dashboard is reached."""
    cleanup_emails(throwaway_email)

    sign_up(driver, frontend_url, throwaway_email, PASSWORD)
    role, text = signup_outcome(driver)
    skip_if_rate_limited(role, text)
    assert role in ("signed_in", "status"), f"first sign-up failed: {text!r}"

    # The sign-up form is only reachable while signed out, and the first attempt may
    # have established a session.
    if is_signed_in(driver):
        sign_out(driver)

    sign_up(driver, frontend_url, throwaway_email, PASSWORD)
    role, text = signup_outcome(driver)
    skip_if_rate_limited(role, text)

    assert role == "alert", f"expected a duplicate-email error, got {role}: {text!r}"
    assert text.strip()
    assert not is_signed_in(driver)
    # The form remains mounted.
    assert driver.find_elements(By.ID, "email")
