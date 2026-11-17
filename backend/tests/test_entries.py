from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.models import Organization, User, UserRole

URL = "/api/v1/entries"


def _ts(days_ago: float = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _quick(note: str = "Felt calm today.", days_ago: float = 0, **extra: Any) -> dict[str, Any]:
    return {"kind": "quick", "occurred_at": _ts(days_ago), "note": note, **extra}


async def _create(http: AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    response = await http.post(URL, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- Create ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        _quick(details={"mood": 3}),
        _quick(details={"mood": 2, "sleep_hours": 6.5}),
        {
            "kind": "panic",
            "occurred_at": _ts(1),
            "details": {
                "intensity": 7,
                "duration_minutes": 10,
                "symptoms": ["racing heart"],
                "trigger": "metro",
            },
        },
        {
            "kind": "medication",
            "occurred_at": _ts(1),
            "details": {"medication_name": "Medication A", "taken": True},
        },
        {
            "kind": "avoidance",
            "occurred_at": _ts(2),
            "note": "Stayed home.",
            "details": {"situation": "dinner", "avoided": True, "anxiety": 6},
        },
    ],
    ids=["quick", "quick-sleep", "panic", "medication", "avoidance"],
)
async def test_create_each_kind(http, acting, client_a: User, body: dict[str, Any]) -> None:
    acting.user = client_a
    created = await _create(http, body)
    assert created["kind"] == body["kind"]
    assert created["details"].items() >= body.get("details", {}).items()

    fetched = await http.get(f"{URL}/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"kind": "panic", "occurred_at": _ts()}, "missing details"),
        ({"kind": "panic", "occurred_at": _ts(), "details": {"intensity": 11}}, "out of range"),
        (_quick(details={"sleep_hours": 25}), "sleep out of range"),
        (_quick(details={"sleep_hours": 6.3}), "sleep not in half hours"),
        (
            {
                "kind": "panic",
                "occurred_at": _ts(),
                "details": {"medication_name": "x", "taken": 1},
            },
            "details of another kind",
        ),
        ({"kind": "unknown", "occurred_at": _ts()}, "unknown kind"),
        (_quick(note=""), "quick entry without note"),
        (_quick(note="   "), "whitespace-only note"),
        (_quick(days_ago=-1), "future timestamp"),
        ({"kind": "quick", "occurred_at": "2026-01-01T10:00:00", "note": "x"}, "naive datetime"),
        (_quick(client_id="00000000-0000-0000-0000-000000000000"), "owner in body"),
        (_quick(note="x" * 5001), "note too long"),
    ],
)
async def test_create_rejects_invalid_input(
    http, acting, client_a: User, body: dict[str, Any], reason: str
) -> None:
    acting.user = client_a
    response = await http.post(URL, json=body)
    assert response.status_code == 422, reason


# --- List ------------------------------------------------------------------------------


async def test_list_is_newest_first_with_pagination(http, acting, client_a: User) -> None:
    acting.user = client_a
    for days_ago in (3, 1, 2):
        await _create(http, _quick(note=f"day -{days_ago}", days_ago=days_ago))

    page = (await http.get(URL, params={"limit": 2})).json()
    assert page["total"] == 3
    assert [e["note"] for e in page["items"]] == ["day -1", "day -2"]

    page = (await http.get(URL, params={"limit": 2, "offset": 2})).json()
    assert [e["note"] for e in page["items"]] == ["day -3"]


async def test_list_filters_by_kind_and_time_range(http, acting, client_a: User) -> None:
    acting.user = client_a
    await _create(http, _quick(days_ago=5))
    recent = await _create(http, _quick(days_ago=1))
    await _create(
        http,
        {
            "kind": "medication",
            "occurred_at": _ts(1),
            "details": {"medication_name": "A", "taken": False},
        },
    )

    page = (await http.get(URL, params={"kind": "quick", "from": _ts(2)})).json()
    assert [e["id"] for e in page["items"]] == [recent["id"]]

    page = (await http.get(URL, params={"to": _ts(2)})).json()
    assert page["total"] == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_rejects_bad_pagination(http, acting, client_a: User, params) -> None:
    acting.user = client_a
    assert (await http.get(URL, params=params)).status_code == 422


# --- Update / delete -------------------------------------------------------------------


async def test_update_note_and_details(http, acting, client_a: User) -> None:
    acting.user = client_a
    entry = await _create(
        http,
        {"kind": "panic", "occurred_at": _ts(1), "details": {"intensity": 5}},
    )
    response = await http.patch(
        f"{URL}/{entry['id']}",
        json={"note": "It passed.", "details": {"intensity": 8, "symptoms": ["dizziness"]}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["note"] == "It passed."
    assert body["details"]["intensity"] == 8
    assert body["occurred_at"] == entry["occurred_at"]


@pytest.mark.parametrize(
    "patch",
    [
        {"details": {"medication_name": "A", "taken": True}},  # details of another kind
        {"details": {"intensity": -1}},
        {"details": None},
        {"occurred_at": None},
        {"kind": "quick"},  # kind is immutable
        {"occurred_at": _ts(-2)},
    ],
)
async def test_update_rejects_invalid_changes(http, acting, client_a: User, patch) -> None:
    acting.user = client_a
    entry = await _create(
        http, {"kind": "panic", "occurred_at": _ts(1), "details": {"intensity": 5}}
    )
    response = await http.patch(f"{URL}/{entry['id']}", json=patch)
    assert response.status_code == 422, patch
    unchanged = (await http.get(f"{URL}/{entry['id']}")).json()
    assert unchanged["details"]["intensity"] == 5


async def test_quick_entry_note_cannot_be_cleared(http, acting, client_a: User) -> None:
    acting.user = client_a
    entry = await _create(http, _quick())
    response = await http.patch(f"{URL}/{entry['id']}", json={"note": None})
    assert response.status_code == 422


async def test_delete(http, acting, client_a: User) -> None:
    acting.user = client_a
    entry = await _create(http, _quick())
    assert (await http.delete(f"{URL}/{entry['id']}")).status_code == 204
    assert (await http.get(f"{URL}/{entry['id']}")).status_code == 404
    assert (await http.delete(f"{URL}/{entry['id']}")).status_code == 404


# --- Ownership and organization isolation ----------------------------------------------


@pytest.fixture
async def other_users(make_user, org_a: Organization, org_b: Organization) -> dict[str, User]:
    return {
        "same_org_client": await make_user(org_a, UserRole.CLIENT, "client-a2"),
        "other_org_client": await make_user(org_b, UserRole.CLIENT, "client-b"),
    }


@pytest.mark.parametrize("who", ["same_org_client", "other_org_client"])
async def test_entries_are_invisible_to_other_clients(
    http, acting, client_a: User, other_users: dict[str, User], who: str
) -> None:
    acting.user = client_a
    entry = await _create(http, _quick(note="private"))
    entry_url = f"{URL}/{entry['id']}"

    acting.user = other_users[who]
    assert (await http.get(URL)).json()["total"] == 0
    assert (await http.get(entry_url)).status_code == 404
    assert (await http.patch(entry_url, json={"note": "hijacked"})).status_code == 404
    assert (await http.delete(entry_url)).status_code == 404

    acting.user = client_a
    still_there = await http.get(entry_url)
    assert still_there.status_code == 200
    assert still_there.json()["note"] == "private"


@pytest.mark.parametrize("role", [UserRole.CLINICIAN, UserRole.ORG_ADMIN])
async def test_non_clients_cannot_access_entries(
    http, acting, make_user, org_a: Organization, client_a: User, role: UserRole
) -> None:
    acting.user = client_a
    entry = await _create(http, _quick())

    acting.user = await make_user(org_a, role, f"staff-{role}")
    assert (await http.get(URL)).status_code == 403
    assert (await http.get(f"{URL}/{entry['id']}")).status_code == 403
    assert (await http.post(URL, json=_quick())).status_code == 403
