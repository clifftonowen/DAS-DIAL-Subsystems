"""Shared helpers for Selenium system tests (not a test module)."""
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
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[normalize-space()='My Profile']")
    ))
