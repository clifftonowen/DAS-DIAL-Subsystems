"""SYSTEM use case: "Therapist logs in and sees their dashboard".

Real browser (headless Chrome) driving the real built UI, which talks to the
real backend + Supabase test project. Requesting `system_creds` before `driver`
means the test skips (without launching Chrome) when env is absent.
"""
import pytest

pytest.importorskip("selenium")  # keep collection green when selenium isn't installed

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from tests.system._helpers import login

pytestmark = pytest.mark.system


def test_login_shows_dashboard_shell(system_creds, driver, frontend_url):
    login(driver, frontend_url, system_creds["email"], system_creds["password"])

    # The sidebar (text-only nav after the emoji cleanup) proves the shell rendered.
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//*[normalize-space()='Learners']"))
    )
    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Main" in body
    assert "Learners" in body
