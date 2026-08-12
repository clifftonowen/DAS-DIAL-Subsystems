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
import os

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

# NO FIXED SEMESTER CONSTANT. These tests take whichever semester the form offers first, which
# `GET /assessments/semesters` guarantees is a LOOKAHEAD one (on-record plus the next two), so it
# is always past the workbook's range and never collides with seeded data — without hardcoding a
# value the form has no option for. See select_semester.

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


class _Created:
    """What a test wrote, so teardown can undo exactly that and nothing else."""

    def __init__(self, learner_id):
        self.learner_id = learner_id
        self.semesters = set()


@pytest.fixture
def uploaded_sitting(supabase_env):
    """Deletes the sittings a test created, in teardown.

    The semesters are RECORDED rather than hardcoded because `select_semester` reads whichever
    lookahead semester the API is currently offering — which moves as the workbook grows, and
    would silently stop matching a constant here.

    Left behind, a lookahead sitting is permanently the learner's newest, so UC2's system tests
    would promote it forever after and fail for reasons unrelated to their own code.
    """
    from supabase import create_client

    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner in the test project")
    created = _Created(learner_id)
    yield created
    sb = create_client(supabase_env["url"], supabase_env["key"])
    for semester in created.semesters:
        try:
            (sb.table("learner_sittings").delete()
               .eq("learner_id", learner_id).eq("semester", semester).execute())
        except Exception:
            pass


def open_upload_form(driver, base_url, timeout=30):
    """From the learners list to the upload modal, with its SERVED METADATA already in.

    THE WAIT ON THE LAST LINE IS LOAD-BEARING; every failure of this file's first CI run was its
    absence. The modal renders the instant it opens, but the rubric and the semester list arrive
    from two API calls behind one `Promise.all` in UploadView, and `/assessments/semesters` pages
    the whole `learner_sittings` table (~23 round trips, ~2s from a laptop and slower from a
    runner). Until both land, `metricSpecs` is `[]`, and the form is in a DIFFERENT STATE than
    the one under test:

      * labels read `phonics_score`, not "Phonics"
      * the hint reads "Valid range: 0–…", so ST-1.3's ceiling message does not exist yet
      * the semester select holds only a "Loading…" placeholder, so there is nothing real to pick
        and `handleSubmit` bails on its `!semester` guard

    Waiting on the phonics hint covers both calls: they sit behind one `Promise.all`, so they
    resolve together or not at all.

    The condition tests for the ABSENCE OF THE PLACEHOLDER rather than the presence of "0–50".
    Waiting for a specific number would couple every test in this file to one ceiling, and a
    rubric change would express itself as four 30-second timeouts instead of one clear assertion
    failure in ST-1.3, which is where the number actually belongs.
    """
    wait = WebDriverWait(driver, timeout)
    driver.get(f"{base_url}/learners")
    wait.until(EC.element_to_be_clickable((By.XPATH, UPLOAD_BUTTON))).click()
    wait.until(EC.presence_of_element_located((By.ID, "upload-file")))
    wait.until(
        lambda d: "0–…" not in d.find_element(By.ID, "upload-phonics_score-hint").text,
        "the served rubric never arrived — GET /assessments/metrics or /semesters failed",
    )
    # The LEARNER list is a third async source, and a separate one: it belongs to LearnersPage,
    # which mounts this modal on click and may still be fetching. Its options must exist before
    # anything is submitted, or `learnerId` is empty and handleParse refuses.
    #
    # Do not be tempted to check the select's VALUE here. A <select> whose React value is ""
    # matches no option, so the browser displays the first one anyway — the control reads
    # correctly while the state behind it is empty. Count the options instead.
    wait.until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "#upload-learner option")) > 0,
        "the learner list never populated — the therapist's caseload may be empty",
    )
    return wait


def select_semester(driver, wait, created=None):
    """Select the NEWEST semester the form offers, and return it.

    WHY NOT A FIXED FAR-FUTURE SEMESTER. The first version of this file injected a `2099 Sem 1`
    option with `select.add()` and dispatched a native change event. That cannot work, and it is
    what made ST-1.1 fail: `<select>` here is a CONTROLLED component whose children are rendered
    from the `semesters` array, which never contains 2099. React strips the foreign option on the
    next reconciliation — and every keystroke into a metric field triggers one. The selection goes
    with it, `handleSubmit` bails on its `!semester` guard (`UploadView.jsx:102`), and the click
    on "Parse report" silently does nothing. The test then times out on a preview that was never
    going to appear, several steps from the actual cause.

    The newest OFFERED option gives the same isolation without fighting the framework. The
    endpoint serves on-record semesters plus the next two, so index 0 is always a lookahead
    semester no seeded sitting uses — currently `2027 Sem 1` against a workbook ending at
    `2026 Sem 1`. It is a real option, so React keeps it.

    Pass `created` (the `uploaded_sitting` record) from any test that CONFIRMS, so teardown knows
    which row to delete. Reading the value rather than hardcoding it is what makes that possible.
    """
    from selenium.webdriver.support.ui import Select

    def first_real_option(d):
        """Re-find the element every poll: React re-renders this select, and a handle held
        across a render raises StaleElementReferenceException. Falsy until a real option
        exists — before the fetch lands the only child is `<option value="">Loading…</option>`."""
        options = Select(d.find_element(By.ID, "upload-semester")).options
        return options and options[0].get_attribute("value")

    semester = wait.until(first_real_option, "the semester list never populated")

    select = Select(driver.find_element(By.ID, "upload-semester"))
    select.select_by_value(semester)

    # The form already defaults to this option; selecting it explicitly asserts that default and,
    # more importantly, tells us WHICH semester the run is about to write.
    wait.until(
        lambda d: d.find_element(By.ID, "upload-semester").get_attribute("value") == semester,
        f"the form did not accept the semester {semester!r}",
    )
    if created is not None:
        created.semesters.add(semester)
    return semester


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

    select_semester(driver, wait, uploaded_sitting)
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

    semester = select_semester(driver, wait, uploaded_sitting)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("30")
    driver.find_element(By.ID, "upload-file").send_keys(report_file)
    wait.until(EC.element_to_be_clickable((By.XPATH, PARSE_BUTTON))).click()
    wait.until(EC.element_to_be_clickable((By.XPATH, CONFIRM_BUTTON))).click()
    wait.until(lambda d: "Data saved successfully" in d.find_element(By.TAG_NAME, "body").text)

    driver.get(f"{frontend_url}/learners/{uploaded_sitting.learner_id}")
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Generate Profile']")
    )).click()

    # The promoted sitting is the one just uploaded — `semester`, not a hardcoded constant, so
    # this still means something when the lookahead moves.
    wait.until(lambda d: semester in d.find_element(By.TAG_NAME, "body").text
                         or "Phonics" in d.find_element(By.TAG_NAME, "body").text)
    # No "no assessment scores yet" prompt: the profile has marks now.
    assert "no assessment scores" not in driver.find_element(By.TAG_NAME, "body").text.lower()


# ST-1.2 — an invalid or corrupted file
def test_st_1_2_a_corrupted_file_is_reported_and_stores_nothing(
    system_creds, driver, frontend_url, corrupt_file,
):
    """The extension passes, the content does not — the therapist sees why, and no row is made."""
    login(driver, frontend_url, system_creds["email"], system_creds["password"])
    wait = open_upload_form(driver, frontend_url)

    select_semester(driver, wait)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("30")
    driver.find_element(By.ID, "upload-file").send_keys(corrupt_file)
    wait.until(EC.element_to_be_clickable((By.XPATH, PARSE_BUTTON))).click()

    message = error_text(driver)
    assert message.strip()
    # The detail has to survive the API client, not arrive as "[object Object]" — FastAPI sends
    # a list-shaped detail for a 422, which is exactly what apiForm used to stringify raw.
    assert "[object Object]" not in message
    # And it must be the PARSER's complaint, not the form's own precondition guard. That guard
    # now writes into the same box, so a half-filled form would satisfy the assertions above
    # while never reaching the parser at all — this test would pass for the wrong reason.
    assert "Pick a learner" not in message
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

    select_semester(driver, wait)
    driver.find_element(By.ID, "upload-phonics_score").send_keys("51")   # ceiling is 50
    driver.find_element(By.ID, "upload-file").send_keys(report_file)

    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Must be between 0 and 50" in body
    assert not driver.find_element(By.XPATH, PARSE_BUTTON).is_enabled()
