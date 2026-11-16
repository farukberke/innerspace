"""Authentication, RBAC, organization isolation, invitations, summaries sharing, audit log."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import create_engine
from app.core.security import JWT_ALGORITHM, TokenType, create_token
from app.models import AuditLog, CareAssignment, Invitation, Organization, User, UserRole
from tests.conftest import TEST_JWT_SECRET, TEST_PASSWORD

API = "/api/v1"
NEW_PASSWORD = "a-brand-new-password"  # noqa: S105


@dataclass
class World:
    org_a: Organization
    org_b: Organization
    admin_a: User
    clin_a: User  # assigned to client_a
    clin_a2: User  # same org, assigned to nobody
    client_a: User
    client_a2: User  # unassigned
    admin_b: User
    clin_b: User
    client_b: User


@pytest.fixture
async def w(make_org, make_user, db_session: AsyncSession) -> World:
    org_a, org_b = await make_org("org-a"), await make_org("org-b")
    world = World(
        org_a=org_a,
        org_b=org_b,
        admin_a=await make_user(org_a, UserRole.ORG_ADMIN, "admin-a"),
        clin_a=await make_user(org_a, UserRole.CLINICIAN, "clin-a"),
        clin_a2=await make_user(org_a, UserRole.CLINICIAN, "clin-a2"),
        client_a=await make_user(org_a, UserRole.CLIENT, "client-a"),
        client_a2=await make_user(org_a, UserRole.CLIENT, "client-a2"),
        admin_b=await make_user(org_b, UserRole.ORG_ADMIN, "admin-b"),
        clin_b=await make_user(org_b, UserRole.CLINICIAN, "clin-b"),
        client_b=await make_user(org_b, UserRole.CLIENT, "client-b"),
    )
    db_session.add(
        CareAssignment(
            organization_id=org_a.id, clinician_id=world.clin_a.id, client_id=world.client_a.id
        )
    )
    await db_session.flush()
    return world


async def _login(http: AsyncClient, email: str, password: str = TEST_PASSWORD):
    return await http.post(f"{API}/auth/login", json={"email": email, "password": password})


async def _audit_actions(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))


# --- Authentication --------------------------------------------------------------------


async def test_login_and_me(http: AsyncClient, w: World) -> None:
    response = await _login(http, w.client_a.email.upper())  # e-mail is case-insensitive
    assert response.status_code == 200
    tokens = response.json()
    me = await http.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(w.client_a.id)
    assert "password" not in me.text


async def test_password_is_stored_hashed(w: World) -> None:
    assert w.client_a.password_hash is not None
    assert w.client_a.password_hash.startswith("$argon2")
    assert TEST_PASSWORD not in w.client_a.password_hash


@pytest.mark.parametrize("case", ["wrong_password", "unknown_email", "inactive", "no_password"])
async def test_login_failures_are_uniform_and_audited(
    http: AsyncClient, w: World, db_session: AsyncSession, case: str
) -> None:
    email, password = w.client_a.email, TEST_PASSWORD
    if case == "wrong_password":
        password = "wrong-password-123"
    elif case == "unknown_email":
        email = "nobody@nowhere.test"
    elif case == "inactive":
        w.client_a.is_active = False
    else:
        w.client_a.password_hash = None
    await db_session.flush()
    response = await _login(http, email, password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    log = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed"))
    ).one()
    assert email not in str(log.detail)


async def test_successful_login_is_audited(http: AsyncClient, w: World, db_session) -> None:
    await _login(http, w.client_a.email)
    log = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.login"))).one()
    assert log.actor_id == w.client_a.id and log.organization_id == w.org_a.id


async def test_refresh_issues_new_tokens(http: AsyncClient, w: World) -> None:
    tokens = (await _login(http, w.client_a.email)).json()
    response = await http.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new = response.json()
    me = await http.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"}
    )
    assert me.status_code == 200


async def test_refresh_rejects_access_token_and_inactive_user(
    http: AsyncClient, w: World, db_session: AsyncSession
) -> None:
    tokens = (await _login(http, w.client_a.email)).json()
    bad = await http.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert bad.status_code == 401
    w.client_a.is_active = False
    await db_session.flush()
    gone = await http.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert gone.status_code == 401


PROTECTED = [
    ("GET", "/auth/me"),
    ("GET", "/entries"),
    ("POST", "/entries"),
    ("GET", f"/entries/{uuid.uuid4()}"),
    ("PATCH", f"/entries/{uuid.uuid4()}"),
    ("DELETE", f"/entries/{uuid.uuid4()}"),
    ("GET", "/summaries"),
    ("GET", f"/summaries/{uuid.uuid4()}"),
    ("POST", f"/summaries/{uuid.uuid4()}/unshare"),
    ("POST", "/summaries"),
    ("POST", f"/summaries/{uuid.uuid4()}/share"),
    ("GET", "/clinician/clients"),
    ("GET", "/clinician/summaries"),
    ("GET", f"/clinician/summaries/{uuid.uuid4()}"),
    ("GET", "/admin/users"),
    ("GET", "/admin/assignments"),
    ("POST", "/admin/assignments"),
    ("DELETE", f"/admin/assignments/{uuid.uuid4()}"),
    ("PATCH", f"/admin/users/{uuid.uuid4()}"),
    ("POST", "/invitations"),
]


def _forge(settings_secret: str, user_id: uuid.UUID, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    claims.update(overrides)
    return jwt.encode(claims, settings_secret, algorithm=JWT_ALGORITHM)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_protected_endpoints_reject_bad_tokens(
    http: AsyncClient, w: World, test_settings: Settings, method: str, path: str
) -> None:
    uid = w.client_a.id
    expired = _forge(TEST_JWT_SECRET, uid, exp=datetime.now(UTC) - timedelta(seconds=5))
    candidates: dict[str, str | None] = {
        "none": None,
        "garbage": "not-a-jwt",
        "expired": expired,
        "refresh_as_access": create_token(test_settings, uid, TokenType.REFRESH),
        "wrong_secret": _forge("x" * 40, uid),
        "alg_none": jwt.encode({"sub": str(uid), "type": "access"}, None, algorithm="none"),
        "no_exp": jwt.encode(
            {"sub": str(uid), "type": "access", "iat": 1}, TEST_JWT_SECRET, "HS256"
        ),
        "unknown_user": _forge(TEST_JWT_SECRET, uuid.uuid4()),
    }
    for name, token in candidates.items():
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = await http.request(method, f"{API}{path}", headers=headers, json={})
        assert response.status_code == 401, name


async def test_deactivated_user_token_stops_working(
    http: AsyncClient, w: World, acting, db_session
):
    acting.user = w.client_a
    assert (await http.get(f"{API}/auth/me")).status_code == 200
    w.client_a.is_active = False
    await db_session.flush()
    assert (await http.get(f"{API}/auth/me")).status_code == 401


# --- Privacy: raw records and summaries ------------------------------------------------


async def _entry(http: AsyncClient, acting, client: User) -> str:
    acting.user = client
    response = await http.post(
        f"{API}/entries",
        json={"kind": "quick", "occurred_at": datetime.now(UTC).isoformat(), "note": "private"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_only_the_client_sees_raw_entries(http: AsyncClient, acting, w: World) -> None:
    entry_id = await _entry(http, acting, w.client_a)
    for viewer in (w.clin_a, w.admin_a, w.clin_b, w.admin_b, w.client_a2, w.client_b):
        acting.user = viewer
        listing = await http.get(f"{API}/entries")
        detail = await http.get(f"{API}/entries/{entry_id}")
        patch = await http.patch(f"{API}/entries/{entry_id}", json={"note": "tampered"})
        delete = await http.delete(f"{API}/entries/{entry_id}")
        if viewer.role == UserRole.CLIENT:
            assert listing.status_code == 200 and listing.json()["total"] == 0
            assert detail.status_code == 404  # other client, also other org
            assert patch.status_code == 404 and delete.status_code == 404
        else:
            assert listing.status_code == 403
            assert detail.status_code == 403
            assert patch.status_code == 403 and delete.status_code == 403
        assert "private" not in listing.text + detail.text
    acting.user = w.client_a
    assert (await http.get(f"{API}/entries/{entry_id}")).json()["note"] == "private"


async def _summary(http: AsyncClient, acting, client: User) -> str:
    acting.user = client
    response = await http.post(f"{API}/summaries", json={"title": "Week", "body": "Synthetic text"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_summary_sharing_lifecycle(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    sid = await _summary(http, acting, w.client_a)
    url = f"{API}/clinician/summaries/{sid}"

    # Not shared yet: the assigned clinician sees nothing.
    acting.user = w.clin_a
    assert (await http.get(url)).status_code == 404
    assert (await http.get(f"{API}/clinician/summaries")).json() == []

    # Client approves sharing.
    acting.user = w.client_a
    assert (await http.post(f"{API}/summaries/{sid}/share")).json()["shared_at"] is not None

    acting.user = w.clin_a
    assert (await http.get(url)).status_code == 200
    assert [s["id"] for s in (await http.get(f"{API}/clinician/summaries")).json()] == [sid]

    # Unassigned clinician (same org), foreign clinician, admins and other clients: no access.
    for other in (w.clin_a2, w.clin_b):
        acting.user = other
        assert (await http.get(url)).status_code == 404
        assert (await http.get(f"{API}/clinician/summaries")).json() == []
    for other in (w.admin_a, w.admin_b, w.client_a2, w.client_b):
        acting.user = other
        assert (await http.get(url)).status_code == 403
        assert (await http.get(f"{API}/summaries/{sid}")).status_code in (403, 404)

    # Revoked: the assigned clinician loses access again.
    acting.user = w.client_a
    assert (await http.post(f"{API}/summaries/{sid}/unshare")).json()["shared_at"] is None
    acting.user = w.clin_a
    assert (await http.get(url)).status_code == 404

    actions = await _audit_actions(db_session)
    assert {"summary.share", "summary.unshare", "summary.view"} <= set(actions)


async def test_clinician_loses_access_when_assignment_removed(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    sid = await _summary(http, acting, w.client_a)
    await http.post(f"{API}/summaries/{sid}/share")
    await db_session.execute(
        CareAssignment.__table__.delete().where(CareAssignment.client_id == w.client_a.id)
    )
    acting.user = w.clin_a
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 404


async def test_client_cannot_touch_other_clients_summaries(
    http: AsyncClient, acting, w: World
) -> None:
    sid = await _summary(http, acting, w.client_a)
    for other in (w.client_a2, w.client_b):
        acting.user = other
        assert (await http.get(f"{API}/summaries/{sid}")).status_code == 404
        assert (await http.post(f"{API}/summaries/{sid}/share")).status_code == 404
        assert (await http.get(f"{API}/summaries")).json() == []


async def test_clinician_sees_only_assigned_clients(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.clin_a
    clients = (await http.get(f"{API}/clinician/clients")).json()
    assert [c["id"] for c in clients] == [str(w.client_a.id)]
    assert set(clients[0]) == {"id", "display_name"}
    acting.user = w.clin_a2
    assert (await http.get(f"{API}/clinician/clients")).json() == []
    acting.user = w.client_a
    assert (await http.get(f"{API}/clinician/clients")).status_code == 403


# --- Org admin: users and assignments --------------------------------------------------


async def test_admin_endpoints_are_admin_only(http: AsyncClient, acting, w: World) -> None:
    for user in (w.clin_a, w.client_a):
        acting.user = user
        assert (await http.get(f"{API}/admin/users")).status_code == 403
        assert (await http.get(f"{API}/admin/assignments")).status_code == 403
        body = {"clinician_id": str(w.clin_a2.id), "client_id": str(w.client_a2.id)}
        assert (await http.post(f"{API}/admin/assignments", json=body)).status_code == 403
        r = await http.patch(f"{API}/admin/users/{w.client_a.id}", json={"is_active": False})
        assert r.status_code == 403


async def test_admin_lists_only_own_org_and_no_clinical_content(
    http: AsyncClient, acting, w: World
) -> None:
    await _entry(http, acting, w.client_a)
    await _summary(http, acting, w.client_a)
    acting.user = w.admin_a
    users = (await http.get(f"{API}/admin/users")).json()
    assert {u["id"] for u in users} == {
        str(u.id) for u in (w.admin_a, w.clin_a, w.clin_a2, w.client_a, w.client_a2)
    }
    only_clinicians = (await http.get(f"{API}/admin/users", params={"role": "clinician"})).json()
    assert len(only_clinicians) == 2
    for path in ("/entries", "/summaries", "/clinician/summaries", "/clinician/clients"):
        assert (await http.get(f"{API}{path}")).status_code == 403


async def test_assignment_management_and_audit(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.admin_a
    body = {"clinician_id": str(w.clin_a2.id), "client_id": str(w.client_a2.id)}
    created = await http.post(f"{API}/admin/assignments", json=body)
    assert created.status_code == 201
    assert (await http.post(f"{API}/admin/assignments", json=body)).status_code == 409
    assert len((await http.get(f"{API}/admin/assignments")).json()) == 2

    # The new clinician can now see the client.
    acting.user = w.clin_a2
    assert len((await http.get(f"{API}/clinician/clients")).json()) == 1

    acting.user = w.admin_a
    aid = created.json()["id"]
    assert (await http.delete(f"{API}/admin/assignments/{aid}")).status_code == 204
    assert (await http.delete(f"{API}/admin/assignments/{aid}")).status_code == 404
    actions = await _audit_actions(db_session)
    assert "assignment.create" in actions and "assignment.delete" in actions


async def test_assignment_requires_clinician_and_client_roles(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.admin_a
    swapped = {"clinician_id": str(w.client_a2.id), "client_id": str(w.clin_a2.id)}
    assert (await http.post(f"{API}/admin/assignments", json=swapped)).status_code == 404
    admin_as_clinician = {"clinician_id": str(w.admin_a.id), "client_id": str(w.client_a2.id)}
    assert (await http.post(f"{API}/admin/assignments", json=admin_as_clinician)).status_code == 404


async def test_admin_cannot_cross_organizations(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.admin_b
    ids = {u["id"] for u in (await http.get(f"{API}/admin/users")).json()}
    assert ids == {str(w.admin_b.id), str(w.clin_b.id), str(w.client_b.id)}

    # Foreign users and assignments look non-existent.
    r = await http.patch(f"{API}/admin/users/{w.client_a.id}", json={"is_active": False})
    assert r.status_code == 404
    foreign = {"clinician_id": str(w.clin_a2.id), "client_id": str(w.client_a2.id)}
    assert (await http.post(f"{API}/admin/assignments", json=foreign)).status_code == 404
    mixed = {"clinician_id": str(w.clin_b.id), "client_id": str(w.client_a2.id)}
    assert (await http.post(f"{API}/admin/assignments", json=mixed)).status_code == 404
    acting.user = w.admin_a
    existing = (await http.get(f"{API}/admin/assignments")).json()[0]["id"]
    acting.user = w.admin_b
    assert (await http.delete(f"{API}/admin/assignments/{existing}")).status_code == 404
    assert (await http.get(f"{API}/admin/assignments")).json() == []


async def test_admin_can_deactivate_but_not_self(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.admin_a
    r = await http.patch(f"{API}/admin/users/{w.clin_a.id}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await _login(http, w.clin_a.email)).status_code == 401
    r = await http.patch(f"{API}/admin/users/{w.admin_a.id}", json={"is_active": False})
    assert r.status_code == 409


# --- Invitations -----------------------------------------------------------------------


async def _invite(http: AsyncClient, **body):
    return await http.post(f"{API}/invitations", json=body)


async def _accept(http: AsyncClient, token: str, password: str = NEW_PASSWORD):
    return await http.post(
        f"{API}/auth/accept-invitation",
        json={"token": token, "password": password, "display_name": "New Person"},
    )


async def test_clinician_invites_client_who_is_assigned_to_them(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.clin_a2
    created = await _invite(http, email="New.Client@Org-A.test")
    assert created.status_code == 201
    token = created.json()["token"]

    # Only a hash of the token is stored.
    invitation = (await db_session.scalars(select(Invitation))).one()
    assert invitation.token_hash != token and token not in invitation.token_hash

    acting.user = None  # public endpoint
    accepted = await _accept(http, token)
    assert accepted.status_code == 201
    user = accepted.json()
    assert user["role"] == "client"
    assert user["organization_id"] == str(w.org_a.id)
    assert user["email"] == "new.client@org-a.test"

    assignment = await db_session.scalar(
        select(CareAssignment).where(CareAssignment.client_id == uuid.UUID(user["id"]))
    )
    assert assignment is not None and assignment.clinician_id == w.clin_a2.id
    assert (await _login(http, "new.client@org-a.test", NEW_PASSWORD)).status_code == 200
    assert {"invitation.create", "invitation.accept"} <= set(await _audit_actions(db_session))


async def test_invitation_is_single_use(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.clin_a
    token = (await _invite(http, email="once@org-a.test")).json()["token"]
    acting.user = None
    assert (await _accept(http, token)).status_code == 201
    assert (await _accept(http, token)).status_code == 400


async def test_invitation_expires(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.clin_a
    token = (await _invite(http, email="late@org-a.test")).json()["token"]
    await db_session.execute(
        update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    acting.user = None
    assert (await _accept(http, token)).status_code == 400
    assert await db_session.scalar(select(User).where(User.email == "late@org-a.test")) is None


async def test_invitation_rejects_unknown_token_and_weak_password(
    http: AsyncClient, acting, w: World
) -> None:
    assert (await _accept(http, "does-not-exist")).status_code == 400
    acting.user = w.clin_a
    token = (await _invite(http, email="weak@org-a.test")).json()["token"]
    acting.user = None
    assert (await _accept(http, token, password="short")).status_code == 422
    assert (await _accept(http, token)).status_code == 201  # token was not consumed by the 422


async def test_invitation_role_rules(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.client_a
    assert (await _invite(http, email="x@org-a.test")).status_code == 403
    acting.user = w.clin_a
    r = await _invite(http, email="doc@org-a.test", role="clinician")
    assert r.status_code == 403
    r = await _invite(http, email="adm@org-a.test", role="org_admin")
    assert r.status_code == 403
    acting.user = w.admin_a
    assert (await _invite(http, email="adm@org-a.test", role="org_admin")).status_code == 403
    r = await _invite(http, email="doc@org-a.test", role="clinician")
    assert r.status_code == 201 and r.json()["role"] == "clinician"


async def test_invitation_cannot_target_another_org_or_existing_email(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.admin_a
    # Foreign clinician id: looks non-existent. (There is no way to name another org.)
    r = await _invite(http, email="n@org-a.test", clinician_id=str(w.clin_b.id))
    assert r.status_code == 404
    r = await _invite(http, email=w.client_b.email)  # already registered somewhere
    assert r.status_code == 409
    acting.user = w.clin_a
    # A clinician cannot choose a different clinician to assign to.
    token = (await _invite(http, email="n2@org-a.test", clinician_id=str(w.clin_a2.id))).json()[
        "token"
    ]
    acting.user = None
    user = (await _accept(http, token)).json()
    acting.user = w.clin_a
    assert user["id"] in {c["id"] for c in (await http.get(f"{API}/clinician/clients")).json()}


async def test_admin_invites_clinician_and_preassigns_client(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.admin_a
    token = (await _invite(http, email="pre@org-a.test", clinician_id=str(w.clin_a2.id))).json()[
        "token"
    ]
    doc_token = (await _invite(http, email="newdoc@org-a.test", role="clinician")).json()["token"]
    acting.user = None
    client = (await _accept(http, token)).json()
    doc = (await _accept(http, doc_token)).json()
    assert doc["role"] == "clinician" and doc["organization_id"] == str(w.org_a.id)
    pair = await db_session.scalar(
        select(CareAssignment).where(CareAssignment.client_id == uuid.UUID(client["id"]))
    )
    assert pair is not None and pair.clinician_id == w.clin_a2.id


async def test_audit_log_never_stores_email_or_passwords(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.clin_a
    token = (await _invite(http, email="secret.person@org-a.test")).json()["token"]
    acting.user = None
    await _accept(http, token)
    await _login(http, "secret.person@org-a.test", "wrong-password-123")
    dump = str([(r.action, r.detail) for r in await db_session.scalars(select(AuditLog))])
    for forbidden in ("secret.person", token, NEW_PASSWORD, "wrong-password-123"):
        assert forbidden not in dump


# --- Security review fixes -------------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "replace-with-a-random-string-of-at-least-32-chars",
        "change-me-" * 5,
        "My-Example-Secret-" * 3,
    ],
)
def test_placeholder_jwt_secret_is_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", database_url="postgresql+asyncpg://x/y", jwt_secret=secret)


def test_env_example_secret_is_rejected() -> None:
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    placeholder = next(
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("JWT_SECRET=")
    )
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+asyncpg://x/y", jwt_secret=placeholder)


def test_engine_hides_statement_parameters() -> None:
    engine = create_engine("postgresql+asyncpg://u:p@localhost/db")
    assert engine.sync_engine.hide_parameters is True


async def test_integrity_errors_become_409_and_400(
    http: AsyncClient, acting, w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    acting.user = w.clin_a
    token = (await _invite(http, email="race@org-a.test")).json()["token"]
    acting.user = w.admin_a
    body = {"clinician_id": str(w.clin_a2.id), "client_id": str(w.client_a2.id)}

    async def _boom(self, *args, **kwargs):
        raise IntegrityError("stmt", {}, Exception("dup"))

    monkeypatch.setattr(AsyncSession, "flush", _boom)
    assert (await http.post(f"{API}/admin/assignments", json=body)).status_code == 409
    acting.user = None
    assert (await _accept(http, token)).status_code == 400


async def test_clinician_list_has_no_body_and_view_is_audited(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    sid = await _summary(http, acting, w.client_a)
    await http.post(f"{API}/summaries/{sid}/share")
    acting.user = w.clin_a
    items = (await http.get(f"{API}/clinician/summaries")).json()
    assert [i["id"] for i in items] == [sid]
    assert "body" not in items[0] and "Synthetic text" not in str(items)
    assert "summary.view" not in await _audit_actions(db_session)
    detail = await http.get(f"{API}/clinician/summaries/{sid}")
    assert detail.json()["body"] == "Synthetic text"
    assert "summary.view" in await _audit_actions(db_session)


async def test_deactivated_client_summaries_hidden_from_clinician(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    sid = await _summary(http, acting, w.client_a)
    await http.post(f"{API}/summaries/{sid}/share")
    w.client_a.is_active = False
    await db_session.flush()
    acting.user = w.clin_a
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 404
    assert (await http.get(f"{API}/clinician/summaries")).json() == []


@pytest.mark.parametrize("who", ["inviter", "assigned_clinician"])
async def test_invitation_invalid_if_sponsor_deactivated(
    http: AsyncClient, acting, w: World, db_session: AsyncSession, who: str
) -> None:
    acting.user = w.admin_a
    invite = await _invite(http, email="orphan@org-a.test", clinician_id=str(w.clin_a2.id))
    token = invite.json()["token"]
    (w.admin_a if who == "inviter" else w.clin_a2).is_active = False
    await db_session.flush()
    acting.user = None
    assert (await _accept(http, token)).status_code == 400
    assert await db_session.scalar(select(User).where(User.email == "orphan@org-a.test")) is None
