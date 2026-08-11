"""SYSTEM use case: UC1 "Upload Assessment Data"

The use-case flows driven through a real browser against the running app.

    ST-1.1  a valid assessment file          -> parsed, confirmed, stored
    ST-1.2  an invalid / corrupted file      -> an error, and nothing stored
    ST-1.3  a mark outside the rubric        -> blocked before the request is sent

ST-1.3 DEPARTS FROM THE PLAN, deliberately. PM3 words it as a database storage failure, which
needs the database forced down mid-run — there is no way to do that from a browser without
tearing down the shared test project for whoever else is using it. The out-of-range mark is the
same tier of the same use case (an error the therapist sees and recovers from), it exercises a
boundary that now exists in the code, and it is reachable. The storage-failure branch is covered
where it can be forced honestly: `test_ut_1_2b` and `test_it_1_2`.

These tests WRITE. Each registers what it created so the sitting does not linger and change
which semester is "latest" for the seeded learner on the next run.

Needs the app running (backend :8000, built frontend :4173) and the test project's credentials —
see backend/tests/README.md. Skips rather than fails without them.
"""
import io
import os
import uuid

import pytest

pytest.importorskip("selenium")

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.system._helpers import login

pytestmark = pytest.mark.system

UPLOAD_BUTTON = "//button[normalize-space()='Upload Assessment']"
PARSE_BUTTON = "//button[normalize-space()='Parse report']"
CONFIRM_BUTTON = "//button[normalize-space()='Confirm & save']"

# Far past the workbook's range (2022 Sem 1 - 2026 Sem 1), so an upload from this suite is always
# the learner's newest sitting and never collides with seeded data.
SYSTEM_SEMESTER = "2099 Sem 1"

REPORT_TEXT = """Assessment Date: 2026-07-24
Phoneme Segmentation 7 10
Confidence Score: 0.6
Risk Score: 0.4
Strengths: blending
Weaknesses: segmentation
"""


@pytest.fixture
def report_file(tmp_path):
    """A real .docx on disk — Selenium's file input needs a path, not bytes."""
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for line in REPORT_TEXT.splitlines():
        document.add_paragraph(line)
    path = tmp_path / "report.docx"
    document.save(str(path))
    return str(path)


@pytest.fixture
def corrupt_file(tmp_path):
    """A .docx extension over bytes that are not a document.

    Gets past `validate_format`, which checks the extension only, and fails in extraction — the
    "corrupted file" branch of the use case rather than the "wrong file type" one.
    """
    path = tmp_path / "corrupt.docx"
    path.write_bytes(b"this is not a docx")
    return str(path)


@pytest.fixture
def uploaded_sitting(supabase_env):
    """Deletes the sitting a test created, in teardown.

    Left behind, a 2099 sitting is permanently the learner's newest — so UC2's system tests would
    promote it forever after and fail for reasons unrelated to their own code.
    """
    from supabase import create_client

    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner in the test project")
    yield learner_id
    sb = create_client(supabase_env["url"], supabase_env["key"])
    try:
        (sb.table("learner_sittings").delete()
           .eq("learner_id", learner_id).eq("semester", SYSTEM_SEMESTER).execute())
    except Exception:
        pass


def open_upload_form(driver, base_url, timeout=20):
    """From the learners list to the upload modal, as a therapist reaches it."""
    wait = WebDriverWait(driver, timeout)
    driver.get(f"{base_url}/learners")
    wait.until(EC.element_to_be_clickable((By.XPATH, UPLOAD_BUTTON))).click()
    wait.until(EC.presence_of_element_located((By.ID, "upload-file")))
    return wait


def select_semester(driver, semester=SYSTEM_SEMESTER):
    """Pick the semester, adding the option if the list does not carry it.

    The dropdown offers what is on record plus the next two, so a far-future semester is not
    normally there. Injecting the option keeps these tests independent of whatever data the
    project happens to hold, which is the same reason they use 2099 at all.
    """
    driver.execute_script(
        """
        const select = document.getElementById('upload-semester');
        if (![...select.options].some(o => o.value === arguments[0])) {
            select.add(new Option(arguments[0], arguments[0]));
        }
        select.value = arguments[0];
        select.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        semester,
    )


def error_text(driver, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "upload-error"))
    ).text


# ST-1.1 — the operational flow
def test_st_1_1_therapist_uploads_an_assessment(
    system_creds, driver, frontend_url, report_file, uploaded_sitting,
):
    """A valid file is parsed, previewed, confirmed and stored."""
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    wait = open_upload_form(driver, frontend_url)

    select_semester(driver)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("30")
    # Writing is left BLANK on purpose: band A never sits it, and blank has to mean "not
    # assessed" rather than a mark of zero. A zero would rank as the learner's weakest skill.
    driver.find_element(By.ID, "upload-file").send_keys(report_file)
    wait.until(EC.element_to_be_clickable((By.XPATH, PARSE_BUTTON))).click()

    # The preview card echoes what will be stored, including the distinction blank carries.
    wait.until(EC.element_to_be_clickable((By.XPATH, CONFIRM_BUTTON)))
    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Not assessed" in body
    driver.find_element(By.XPATH, CONFIRM_BUTTON).click()

    wait.until(lambda d: "Data saved successfully" in d.find_element(By.TAG_NAME, "body").text)


def test_st_1_1b_the_upload_reaches_the_learners_profile(
    system_creds, driver, frontend_url, report_file, uploaded_sitting,
):
    """The postcondition, seen the way a therapist sees it.

    "Associated with the selected learner" is only observable through UC2 — upload, then open the
    learner and generate their profile. This is the flow that used to end in "no assessment
    scores on record" despite the upload having succeeded.
    """
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    wait = open_upload_form(driver, frontend_url)

    select_semester(driver)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("30")
    driver.find_element(By.ID, "upload-file").send_keys(report_file)
    wait.until(EC.element_to_be_clickable((By.XPATH, PARSE_BUTTON))).click()
    wait.until(EC.element_to_be_clickable((By.XPATH, CONFIRM_BUTTON))).click()
    wait.until(lambda d: "Data saved successfully" in d.find_element(By.TAG_NAME, "body").text)

    driver.get(f"{frontend_url}/learners/{uploaded_sitting}")
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Generate Profile']")
    )).click()

    # No "no assessment scores yet" prompt: the profile has marks now.
    wait.until(lambda d: "2099 Sem 1" in d.find_element(By.TAG_NAME, "body").text
                         or "Phonics" in d.find_element(By.TAG_NAME, "body").text)
    assert "no assessment scores" not in driver.find_element(By.TAG_NAME, "body").text.lower()


# ST-1.2 — an invalid or corrupted file
def test_st_1_2_a_corrupted_file_is_reported_and_stores_nothing(
    system_creds, driver, frontend_url, corrupt_file,
):
    """The extension passes, the content does not — the therapist sees why, and no row is made."""
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    wait = open_upload_form(driver, frontend_url)

    select_semester(driver)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("30")
    driver.find_element(By.ID, "upload-file").send_keys(corrupt_file)
    wait.until(EC.element_to_be_clickable((By.XPATH, PARSE_BUTTON))).click()

    message = error_text(driver)
    assert message.strip()
    # The detail has to survive the API client, not arrive as "[object Object]" — FastAPI sends
    # a list-shaped detail for a 422, which is exactly what apiForm used to stringify raw.
    assert "[object Object]" not in message
    # Never reached the preview, so there is nothing to confirm and nothing was stored.
    assert driver.find_elements(By.XPATH, CONFIRM_BUTTON) == []


# ST-1.3 — a mark outside the rubric
def test_st_1_3_an_out_of_range_mark_blocks_the_upload(
    system_creds, driver, frontend_url, report_file,
):
    """The form refuses before any request is sent, and says what the valid range is.

    Client-side because a rejection the therapist can see while typing beats one that arrives
    after a round trip — but the API enforces the same ceiling, from the same served number.
    """
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    wait = open_upload_form(driver, frontend_url)

    select_semester(driver)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("51")   # ceiling is 50
    driver.find_element(By.ID, "upload-file").send_keys(report_file)

    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Must be between 0 and 50" in body
    assert not driver.find_element(By.XPATH, PARSE_BUTTON).is_enabled()
