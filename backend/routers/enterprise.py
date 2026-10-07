import json
import re
import sqlite3
import uuid
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from backend.services.enterprise_service import (
    MAX_PROJECT_ASSET_BYTES,
    SESSION_COOKIE,
    connect,
    hash_password,
    issue_session,
    now_iso,
    record_audit,
    resolve_session,
    revoke_session,
    safe_user,
    verify_password,
)

router = APIRouter(tags=["Accounts and Projects"])


class RegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be empty")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        return normalized


class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["admin", "editor", "viewer"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class MemberRoleRequest(BaseModel):
    role: Literal["admin", "editor", "viewer"]


class ProjectAssetsRequest(BaseModel):
    analysis: dict[str, Any] | None = None
    render_settings: dict[str, Any] | None = None


def _current_user(request: Request) -> dict[str, str]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


def _session_token(request: Request) -> str | None:
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if cookie_token:
        return cookie_token
    authorization = request.headers.get("authorization", "")
    return authorization[7:].strip() if authorization.startswith("Bearer ") else None


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=604800,
        httponly=True,
        secure=os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"},
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")


def _project_role(connection: sqlite3.Connection, project_id: str, user_id: str) -> str:
    row = connection.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return row["role"]


def _require_manager(role: str) -> None:
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Project owner or admin role required")


def _project_summary(connection: sqlite3.Connection, project_id: str, role: str) -> dict[str, Any]:
    project = connection.execute(
        "SELECT id, name, created_by, created_at, updated_at FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    count = connection.execute(
        "SELECT COUNT(*) AS member_count FROM project_members WHERE project_id = ?",
        (project_id,),
    ).fetchone()["member_count"]
    return {**dict(project), "role": role, "member_count": count}


@router.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegistrationRequest, response: Response):
    user_id = str(uuid.uuid4())
    created_at = now_iso()
    try:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO users (id, email, display_name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, body.email, body.display_name, hash_password(body.password), created_at),
            )
            record_audit(connection, None, user_id, body.email, "account.registered")
            token = issue_session(connection, user_id)
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error).lower():
            raise HTTPException(status_code=409, detail="An account with this email already exists") from error
        raise
    _set_session_cookie(response, token)
    return {"user": {"id": user_id, "email": body.email, "display_name": body.display_name}}


@router.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    email = body.email.strip().lower()
    with connect() as connection:
        user_row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
        if not user_row or not verify_password(body.password, user_row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = safe_user(user_row)
        token = issue_session(connection, user["id"])
        record_audit(connection, None, user["id"], user["email"], "account.signed_in")
    _set_session_cookie(response, token)
    return {"user": user}


@router.get("/api/auth/me")
def current_account(request: Request):
    user = _current_user(request)
    return {"user": user}


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    user = getattr(request.state, "user", None)
    if user:
        with connect() as connection:
            record_audit(connection, None, user["id"], user["email"], "account.signed_out")
    revoke_session(_session_token(request))
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/api/projects")
def list_projects(request: Request):
    user = _current_user(request)
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT projects.id, project_members.role
            FROM projects JOIN project_members ON project_members.project_id = projects.id
            WHERE project_members.user_id = ? ORDER BY projects.updated_at DESC
            """,
            (user["id"],),
        ).fetchall()
        return [
            _project_summary(connection, row["id"], row["role"])
            for row in rows
        ]


@router.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectRequest, request: Request):
    user = _current_user(request)
    project_id = str(uuid.uuid4())
    created_at = now_iso()
    with connect() as connection:
        connection.execute(
            "INSERT INTO projects (id, name, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, body.name, user["id"], created_at, created_at),
        )
        connection.execute(
            "INSERT INTO project_members (project_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
            (project_id, user["id"], created_at),
        )
        record_audit(
            connection, project_id, user["id"], user["email"], "project.created", {"name": body.name}
        )
        return _project_summary(connection, project_id, "owner")


@router.get("/api/projects/{project_id}")
def get_project(project_id: str, request: Request):
    user = _current_user(request)
    with connect() as connection:
        role = _project_role(connection, project_id, user["id"])
        summary = _project_summary(connection, project_id, role)
        assets = connection.execute(
            "SELECT asset_type, value_json, updated_by, updated_at FROM project_assets WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        summary["assets"] = {
            row["asset_type"]: {
                "data": json.loads(row["value_json"]),
                "updated_by": row["updated_by"],
                "updated_at": row["updated_at"],
            }
            for row in assets
        }
        return summary


@router.patch("/api/projects/{project_id}")
def rename_project(project_id: str, body: ProjectRequest, request: Request):
    user = _current_user(request)
    with connect() as connection:
        role = _project_role(connection, project_id, user["id"])
        _require_manager(role)
        updated_at = now_iso()
        connection.execute(
            "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
            (body.name, updated_at, project_id),
        )
        record_audit(
            connection, project_id, user["id"], user["email"], "project.renamed", {"name": body.name}
        )
        return _project_summary(connection, project_id, role)


@router.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, request: Request):
    user = _current_user(request)
    with connect() as connection:
        role = _project_role(connection, project_id, user["id"])
        if role != "owner":
            raise HTTPException(status_code=403, detail="Only the project owner can delete it")
        record_audit(connection, project_id, user["id"], user["email"], "project.deleted")
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/api/projects/{project_id}/assets")
def save_project_assets(project_id: str, body: ProjectAssetsRequest, request: Request):
    user = _current_user(request)
    if body.analysis is None and body.render_settings is None:
        raise HTTPException(status_code=422, detail="Provide analysis, render_settings, or both")
    assets_to_save = {
        key: value
        for key, value in (
            ("analysis", body.analysis),
            ("render_settings", body.render_settings),
        )
        if value is not None
    }
    serialized = {key: json.dumps(value, separators=(",", ":")) for key, value in assets_to_save.items()}
    if any(len(value.encode("utf-8")) > MAX_PROJECT_ASSET_BYTES for value in serialized.values()):
        raise HTTPException(status_code=413, detail="Each project asset is limited to 5 MB")

    with connect() as connection:
        role = _project_role(connection, project_id, user["id"])
        if role == "viewer":
            raise HTTPException(status_code=403, detail="Editor role or higher required")
        updated_at = now_iso()
        for asset_type, value_json in serialized.items():
            connection.execute(
                """
                INSERT INTO project_assets (project_id, asset_type, value_json, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, asset_type) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (project_id, asset_type, value_json, user["id"], updated_at),
            )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (updated_at, project_id)
        )
        record_audit(
            connection,
            project_id,
            user["id"],
            user["email"],
            "project.assets_updated",
            {"asset_types": sorted(serialized)},
        )
        return {"saved": sorted(serialized), "updated_at": updated_at}


@router.get("/api/projects/{project_id}/members")
def list_members(project_id: str, request: Request):
    user = _current_user(request)
    with connect() as connection:
        _project_role(connection, project_id, user["id"])
        rows = connection.execute(
            """
            SELECT users.id, users.email, users.display_name, project_members.role, project_members.joined_at
            FROM project_members JOIN users ON users.id = project_members.user_id
            WHERE project_members.project_id = ? ORDER BY
                CASE project_members.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                users.email
            """,
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@router.post("/api/projects/{project_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(project_id: str, body: MemberRequest, request: Request):
    actor = _current_user(request)
    with connect() as connection:
        actor_role = _project_role(connection, project_id, actor["id"])
        _require_manager(actor_role)
        target = connection.execute(
            "SELECT id, email, display_name FROM users WHERE email = ? COLLATE NOCASE",
            (body.email,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Create an account for this email before adding it")
        if target["id"] == actor["id"]:
            raise HTTPException(status_code=409, detail="You are already a project member")
        if actor_role == "admin" and body.role == "admin":
            raise HTTPException(status_code=403, detail="Only the owner can grant admin access")
        joined_at = now_iso()
        try:
            connection.execute(
                "INSERT INTO project_members (project_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (project_id, target["id"], body.role, joined_at),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="This user is already a project member") from error
        record_audit(
            connection,
            project_id,
            actor["id"],
            actor["email"],
            "project.member_added",
            {"email": target["email"], "role": body.role},
        )
        return {**dict(target), "role": body.role, "joined_at": joined_at}


@router.patch("/api/projects/{project_id}/members/{member_id}")
def update_member_role(
    project_id: str, member_id: str, body: MemberRoleRequest, request: Request
):
    actor = _current_user(request)
    with connect() as connection:
        actor_role = _project_role(connection, project_id, actor["id"])
        _require_manager(actor_role)
        target_role = _project_role(connection, project_id, member_id)
        if target_role == "owner":
            raise HTTPException(status_code=409, detail="The project owner role cannot be changed")
        if actor_role == "admin" and (target_role == "admin" or body.role == "admin"):
            raise HTTPException(status_code=403, detail="Only the owner can manage admin roles")
        connection.execute(
            "UPDATE project_members SET role = ? WHERE project_id = ? AND user_id = ?",
            (body.role, project_id, member_id),
        )
        target = connection.execute(
            "SELECT email FROM users WHERE id = ?", (member_id,)
        ).fetchone()
        record_audit(
            connection,
            project_id,
            actor["id"],
            actor["email"],
            "project.member_role_changed",
            {"email": target["email"], "role": body.role},
        )
        return {"user_id": member_id, "email": target["email"], "role": body.role}


@router.delete("/api/projects/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(project_id: str, member_id: str, request: Request):
    actor = _current_user(request)
    with connect() as connection:
        actor_role = _project_role(connection, project_id, actor["id"])
        target_role = _project_role(connection, project_id, member_id)
        if target_role == "owner":
            raise HTTPException(status_code=409, detail="Transfer ownership before removing the owner")
        if member_id == actor["id"]:
            connection.execute(
                "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
                (project_id, member_id),
            )
            action = "project.member_left"
        else:
            _require_manager(actor_role)
            if actor_role == "admin" and target_role == "admin":
                raise HTTPException(status_code=403, detail="Only the owner can remove admins")
            connection.execute(
                "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
                (project_id, member_id),
            )
            action = "project.member_removed"
        target = connection.execute("SELECT email FROM users WHERE id = ?", (member_id,)).fetchone()
        record_audit(
            connection,
            project_id,
            actor["id"],
            actor["email"],
            action,
            {"email": target["email"]},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/audit")
def list_audit_events(
    request: Request,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    user = _current_user(request)
    with connect() as connection:
        if project_id:
            role = _project_role(connection, project_id, user["id"])
            _require_manager(role)
            rows = connection.execute(
                """
                SELECT id, project_id, actor_id, actor_email, action, details_json, created_at
                FROM audit_events WHERE project_id = ? ORDER BY id DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, project_id, actor_id, actor_email, action, details_json, created_at
                FROM audit_events WHERE actor_id = ? ORDER BY id DESC LIMIT ?
                """,
                (user["id"], limit),
            ).fetchall()
        return [
            {
                **dict(row),
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]
