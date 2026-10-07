import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.enterprise import router
from backend.services import enterprise_service
from backend.services.enterprise_auth import require_account_session


class EnterpriseAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "enterprise.sqlite3"
        self.database_patch = patch.object(
            enterprise_service, "_database_path", return_value=database_path
        )
        self.database_patch.start()
        enterprise_service.initialize_database()

        app = FastAPI()
        app.middleware("http")(require_account_session)
        app.include_router(router)
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.database_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def register(client, email, display_name):
        return client.post(
            "/api/auth/register",
            json={"email": email, "display_name": display_name, "password": "long-password-123"},
        )

    def test_accounts_create_owner_projects_and_authenticate_api_routes(self):
        self.assertEqual(self.client.get("/api/projects").status_code, 401)

        response = self.register(self.client, "owner@example.com", "Owner")

        self.assertEqual(response.status_code, 201)
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        first_session = self.client.cookies.get(enterprise_service.SESSION_COOKIE)
        self.assertTrue(enterprise_service.resolve_session(first_session)["is_system_admin"])

        with TestClient(self.client.app) as second_account:
            second_response = self.register(second_account, "editor@example.com", "Editor")
            second_session = second_account.cookies.get(enterprise_service.SESSION_COOKIE)
            self.assertFalse(enterprise_service.resolve_session(second_session)["is_system_admin"])
            self.assertNotIn("is_system_admin", second_response.json()["user"])

        project = self.client.post("/api/projects", json={"name": "Launch clips"}).json()
        self.assertEqual(project["role"], "owner")

        saved = self.client.put(
            f"/api/projects/{project['id']}/assets",
            json={"analysis": {"title": "Launch video", "clips": [{"title": "Hook"}]}},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["saved"], ["analysis"])
        details = self.client.get(f"/api/projects/{project['id']}").json()
        self.assertEqual(details["assets"]["analysis"]["data"]["title"], "Launch video")

        audit = self.client.get(f"/api/audit?project_id={project['id']}")
        self.assertEqual(audit.status_code, 200)
        self.assertIn("project.assets_updated", [event["action"] for event in audit.json()])

    def test_existing_database_promotes_oldest_account_to_system_admin(self):
        database_path = Path(self.temp_dir.name) / "legacy-enterprise.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO users (id, email, display_name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("older", "older@example.com", "Older", "hash", "2026-01-01T00:00:00+00:00"),
                    ("newer", "newer@example.com", "Newer", "hash", "2026-01-02T00:00:00+00:00"),
                ],
            )

        with patch.object(
            enterprise_service, "_database_path", return_value=database_path
        ):
            enterprise_service.initialize_database()
            with enterprise_service.connect() as connection:
                accounts = connection.execute(
                    "SELECT email, is_system_admin FROM users ORDER BY created_at"
                ).fetchall()

        self.assertEqual(
            [(row["email"], row["is_system_admin"]) for row in accounts],
            [("older@example.com", 1), ("newer@example.com", 0)],
        )

    def test_viewer_can_read_but_cannot_write_or_read_project_audit(self):
        self.register(self.client, "owner@example.com", "Owner")
        project = self.client.post("/api/projects", json={"name": "Shared clips"}).json()

        with TestClient(self.client.app) as teammate:
            self.register(teammate, "viewer@example.com", "Viewer")
            invited = self.client.post(
                f"/api/projects/{project['id']}/members",
                json={"email": "viewer@example.com", "role": "viewer"},
            )
            self.assertEqual(invited.status_code, 201)
            self.client.put(
                f"/api/projects/{project['id']}/assets",
                json={"analysis": {"title": "Shared result"}},
            )

            self.assertEqual(teammate.get(f"/api/projects/{project['id']}").status_code, 200)
            self.assertEqual(
                teammate.put(
                    f"/api/projects/{project['id']}/assets",
                    json={"analysis": {"title": "Unauthorized edit"}},
                ).status_code,
                403,
            )
            self.assertEqual(
                teammate.get(f"/api/audit?project_id={project['id']}").status_code,
                403,
            )
            self.assertEqual(teammate.get("/api/projects").json()[0]["role"], "viewer")

    def test_nonmembers_cannot_discover_projects_and_owner_cannot_be_demoted(self):
        self.register(self.client, "owner@example.com", "Owner")
        project = self.client.post("/api/projects", json={"name": "Private"}).json()

        with TestClient(self.client.app) as stranger:
            self.register(stranger, "stranger@example.com", "Stranger")
            self.assertEqual(stranger.get(f"/api/projects/{project['id']}").status_code, 404)
            self.assertEqual(
                self.client.patch(
                    f"/api/projects/{project['id']}/members/{project['created_by']}",
                    json={"role": "viewer"},
                ).status_code,
                409,
            )

    def test_registration_validates_password_and_prevents_duplicate_accounts(self):
        invalid = self.client.post(
            "/api/auth/register",
            json={"email": "weak@example.com", "display_name": "Weak", "password": "short"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.register(self.client, "owner@example.com", "Owner").status_code, 201)

        duplicate = self.register(self.client, "OWNER@example.com", "Duplicate")
        self.assertEqual(duplicate.status_code, 409)

    def test_unregistered_member_email_is_rejected(self):
        self.register(self.client, "owner@example.com", "Owner")
        project = self.client.post("/api/projects", json={"name": "Team"}).json()
        response = self.client.post(
            f"/api/projects/{project['id']}/members",
            json={"email": "pending@example.com", "role": "editor"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
