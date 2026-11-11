"""The collection contract: `data` + `meta`, paging, search and sort."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import User

PASSWORD = "supersecret123"


def register(client: TestClient, email: str) -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def admin_headers(client: TestClient, session: Session, email: str = "admin@example.com") -> dict:
    user = register(client, email)
    row = session.get(User, uuid.UUID(user["id"]))
    assert row is not None
    row.is_superuser = True
    session.add(row)
    session.commit()

    response = client.post(
        "/api/v1/auth/access-token", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_collection_is_wrapped_in_data_and_meta(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)

    response = client.get("/api/v1/users/", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert set(body["meta"]) == {
        "total_count",
        "page",
        "per_page",
        "total_pages",
        "has_next",
        "has_previous",
    }
    assert body["meta"] == {
        "total_count": 1,
        "page": 1,
        "per_page": 25,
        "total_pages": 1,
        "has_next": False,
        "has_previous": False,
    }
    # Convenience header, same number as `meta.total_count`.
    assert response.headers["x-total-count"] == "1"


def test_paging_splits_the_collection(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)
    for index in range(4):
        register(client, f"user{index}@example.com")

    first = client.get("/api/v1/users/?page=1&per_page=2", headers=headers).json()
    second = client.get("/api/v1/users/?page=2&per_page=2", headers=headers).json()

    assert first["meta"] == {
        "total_count": 5,
        "page": 1,
        "per_page": 2,
        "total_pages": 3,
        "has_next": True,
        "has_previous": False,
    }
    assert second["meta"]["has_previous"] is True
    assert len(first["data"]) == 2
    # Pages must not overlap, and paging is stable thanks to the `id` tiebreak.
    first_ids = {row["id"] for row in first["data"]}
    second_ids = {row["id"] for row in second["data"]}
    assert first_ids.isdisjoint(second_ids)


def test_page_beyond_the_end_is_empty_but_reports_totals(
    client: TestClient, session: Session
) -> None:
    headers = admin_headers(client, session)

    body = client.get("/api/v1/users/?page=9&per_page=25", headers=headers).json()

    assert body["data"] == []
    assert body["meta"]["total_count"] == 1


def test_search_matches_email_and_full_name(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "zoe@acme.example.com", "password": PASSWORD, "full_name": "Zoe Admin"},
    )
    assert created.status_code == 201

    by_email = client.get("/api/v1/users/?q=acme", headers=headers).json()
    assert [row["email"] for row in by_email["data"]] == ["zoe@acme.example.com"]
    assert by_email["meta"]["total_count"] == 1

    by_name = client.get("/api/v1/users/?q=Zoe", headers=headers).json()
    assert [row["email"] for row in by_name["data"]] == ["zoe@acme.example.com"]

    assert client.get("/api/v1/users/?q=nobody", headers=headers).json()["data"] == []


def test_search_treats_wildcards_literally(client: TestClient, session: Session) -> None:
    """A `%` from a client must not match everything."""
    headers = admin_headers(client, session)

    body = client.get("/api/v1/users/?q=%25", headers=headers).json()

    assert body["data"] == []
    assert body["meta"]["total_count"] == 0


def test_sort_ascending_and_descending(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)
    for email in ("b@example.com", "c@example.com"):
        register(client, email)

    ascending = client.get("/api/v1/users/?sort=email", headers=headers).json()
    descending = client.get("/api/v1/users/?sort=-email", headers=headers).json()

    emails = [row["email"] for row in ascending["data"]]
    assert emails == sorted(emails)
    assert [row["email"] for row in descending["data"]] == sorted(emails, reverse=True)


def test_unknown_sort_field_is_rejected(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)

    response = client.get("/api/v1/users/?sort=s.password", headers=headers)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_sort_field"
    assert "email" in error["message"]  # lists the allowed fields


def test_per_page_is_capped(client: TestClient, session: Session) -> None:
    headers = admin_headers(client, session)

    assert client.get("/api/v1/users/?per_page=101", headers=headers).status_code == 422
    assert client.get("/api/v1/users/?per_page=0", headers=headers).status_code == 422
    assert client.get("/api/v1/users/?page=0", headers=headers).status_code == 422
