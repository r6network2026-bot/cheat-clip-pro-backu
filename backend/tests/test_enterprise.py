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
