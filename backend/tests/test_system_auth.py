import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.routers.enterprise import router as enterprise_router
from backend.routers import system as system_router
from backend.routers.system import verify_admin_access
from backend.services import enterprise_service
from backend.services.enterprise_auth import require_account_session


class SystemAdminAccessTests(unittest.TestCase):
    @staticmethod
    def request_for(user):
        request = Request(
            {"type": "http", "method": "POST", "path": "/api/clear-temp", "headers": []}
        )
        request.state.user = user
        return request

    def test_system_administrator_can_manage_system_without_api_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "", "CHEAT_CLIP_API_KEY": ""}):
            authorized = verify_admin_access(
                self.request_for({"is_system_admin": True}), None, None
            )

        self.assertTrue(authorized)

    def test_regular_account_cannot_manage_system_without_api_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "", "CHEAT_CLIP_API_KEY": ""}):
            with self.assertRaises(HTTPException) as raised:
                verify_admin_access(
                    self.request_for({"is_system_admin": False}), None, None
                )

        self.assertEqual(raised.exception.status_code, 403)

    def test_admin_operations_require_matching_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "admin-secret"}):
            with self.assertRaises(HTTPException) as raised:
                verify_admin_access(
                    self.request_for({"is_system_admin": False}), None, None
                )
            self.assertEqual(raised.exception.status_code, 401)

            self.assertTrue(
                verify_admin_access(
                    self.request_for({"is_system_admin": False}), "admin-secret", None
                )
            )

    def test_system_control_route_is_available_only_to_system_admin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "enterprise.sqlite3"
            with patch.object(enterprise_service, "_database_path", return_value=database_path):
                enterprise_service.initialize_database()
                app = FastAPI()
                app.middleware("http")(require_account_session)
                app.include_router(enterprise_router)
                app.include_router(system_router.router)

                with TestClient(app) as admin_client, patch.object(
                    system_router, "has_active_render_jobs", return_value=False
                ), patch.object(
                    system_router, "clear_temp_files", return_value={"cleared": True}
                ) as clear_temp:
                    admin_client.post(
                        "/api/auth/register",
                        json={
                            "email": "admin@example.com",
                            "display_name": "Admin",
                            "password": "long-password-123",
                        },
                    )
                    response = admin_client.post("/api/clear-temp")
                    self.assertEqual(response.status_code, 200)
                    clear_temp.assert_called_once()

                    with TestClient(app) as regular_client:
                        regular_client.post(
                            "/api/auth/register",
                            json={
                                "email": "regular@example.com",
                                "display_name": "Regular",
                                "password": "long-password-123",
                            },
                        )
                        denied = regular_client.post("/api/clear-temp")
                        self.assertEqual(denied.status_code, 403)
                        clear_temp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
