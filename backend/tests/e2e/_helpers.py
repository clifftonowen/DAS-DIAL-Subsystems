"""Shared helpers for e2e tests (not a test module)."""
import pytest


def skip_if_rate_limited(resp):
    """Skip when Supabase refused the request on quota rather than on merit.

    Sign-up returns 400 "email rate limit exceeded" once the project's email quota
    is spent. That is an environment condition, exactly like "Confirm email" being
    enabled — not a defect in the code under test — so failing the build on it makes
    CI red for a reason no commit can fix.

    The skip is deliberately loud, and CI runs with `-rs`, because a permanently
    skipped test is a false pass. If you see this in a run, fix the cause rather
    than the test:

      1. Authentication -> Providers -> Email -> turn OFF "Confirm email" on the
         TEST project. With confirmations off no email is sent, so the email quota
         is never consumed. This is the real fix.
      2. Authentication -> Rate Limits -> raise the email / sign-up limits.
      3. Stop the workflow running twice per commit (`push` and `pull_request` both
         fire), which doubles the sign-ups competing for the same quota.
    """
    if resp.status_code == 400 and "rate limit" in resp.text.lower():
        pytest.skip(
            "Supabase rejected sign-up on quota: "
            f"{resp.text}. Turn OFF 'Confirm email' on the test project so no "
            "email is sent, or raise the limit under Authentication -> Rate Limits. "
            "See tests/e2e/_helpers.py::skip_if_rate_limited."
        )
