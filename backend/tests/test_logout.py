from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_logout_without_token():
    """POST /auth/logout without a Bearer token → 403."""
    r = TestClient(app).post("/auth/logout")
    assert r.status_code == 403


def test_logout_with_token():
    """POST /auth/logout with a Bearer token → 204."""
    patch_target = "app.gateways.auth_gateway.get_supabase"
    with patch(patch_target) as mock_get:
        mock_get.return_value.auth.admin.sign_out = Mock()
        r = TestClient(app).post(
            "/auth/logout",
            headers={"Authorization": "Bearer dummy-token"},
        )
        assert r.status_code == 204
        mock_get.return_value.auth.admin.sign_out.assert_called_once_with(
            "dummy-token"
        )
