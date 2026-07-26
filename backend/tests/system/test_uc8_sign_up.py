"""SYSTEM use case: UC8 "Therapist signs up".

Real headless Chrome driving the real built UI. Both tests CREATE a real account
in the Supabase test project, so both register the address with `cleanup_emails`
for teardown.

TEST-ENVIRONMENT NOTE: with "Confirm email" enabled, UC8 correctly ends with the
therapist still signed out and a notice telling them to confirm. ST-8.1 detects
that from the notice text and skips the follow-up log-in rather than failing on a
project setting.
"""
import pytest

pytest.importorskip("selenium")

from selenium.webdriver.common.by import By

from tests.system._helpers import (
    feedback,
    is_signed_in,
    login,
    sign_up,
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
    role, text = feedback(driver)

    skip_if_rate_limited(role, text)
    assert role == "status", f"expected a success notice, got {role}: {text!r}"
    assert "successfully created" in text.lower()

    if "confirm" in text.lower():
        pytest.skip(
            "test project has 'Confirm email' enabled, so the account cannot log "
            "in yet; disable it on the TEST project to exercise the log-in half"
        )

    # UC8's postcondition feeds UC6's precondition, in the same browser session.
    login(driver, frontend_url, throwaway_email, PASSWORD)
    assert is_signed_in(driver)


def test_signing_up_twice_with_the_same_email_is_refused(
    system_creds, throwaway_email, cleanup_emails, driver, frontend_url
):
    """ST-8.2: alternative flow — the second attempt shows an error, the form
    stays put, and no dashboard is reached."""
    cleanup_emails(throwaway_email)

    sign_up(driver, frontend_url, throwaway_email, PASSWORD)
    first_role, first_text = feedback(driver)
    skip_if_rate_limited(first_role, first_text)
    assert first_role == "status", f"expected a success notice, got {first_text!r}"

    sign_up(driver, frontend_url, throwaway_email, PASSWORD)
    role, text = feedback(driver)

    assert role == "alert"
    assert text.strip()
    assert not is_signed_in(driver)
    # The form remains mounted.
    assert driver.find_elements(By.ID, "email")
