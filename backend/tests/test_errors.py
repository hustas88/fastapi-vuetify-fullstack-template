"""The API's JSON error format is uniform and readable."""

from fastapi.testclient import TestClient


def _error(response) -> dict:
    """Every error is `{"error": {...}}` — nothing else."""
    assert set(response.json()) == {"error"}, response.text
    return response.json()["error"]


# ---------------------------------------------------------------------------
# Validation errors (FastAPI's default is a list of Pydantic internals)
# ---------------------------------------------------------------------------
def test_missing_field_is_explained(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "a@example.com"})

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation_error"
    assert error["message"] == "Password: This field is required."
    assert error["details"] == [{"field": "password", "message": "This field is required."}]


def test_short_password_reads_as_a_sentence(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "short"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["details"] == [
        {"field": "password", "message": "Must be at least 8 characters long."}
    ]
    assert error["message"] == "Password: Must be at least 8 characters long."


def test_multiple_errors_are_listed_per_field(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "x"})

    assert response.status_code == 422
    error = _error(response)
    assert error["message"] == "Some of the submitted values are invalid."

    fields = {detail["field"]: detail["message"] for detail in error["details"]}
    assert set(fields) == {"email", "password"}
    assert fields["password"] == "Must be at least 8 characters long."
    assert "email address" in fields["email"]

    # Pydantic's machine-oriented keys must not leak through.
    for detail in error["details"]:
        assert set(detail) == {"field", "message"}


def test_invalid_json_body_is_explained(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert _error(response)["message"] == "The request body is not valid JSON."


# ---------------------------------------------------------------------------
# HTTP and domain errors
# ---------------------------------------------------------------------------
def test_unknown_route_is_a_readable_404(client: TestClient) -> None:
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    error = _error(response)
    assert error["code"] == "not_found"
    assert error["message"] == "The requested resource could not be found."


def test_wrong_method_is_a_readable_405(client: TestClient) -> None:
    response = client.put("/api/v1/users/me")

    assert response.status_code == 405
    error = _error(response)
    assert error["code"] == "method_not_allowed"
    assert error["message"] == "This endpoint does not accept that HTTP method."


def test_401_keeps_the_www_authenticate_header(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert _error(response)["code"] == "unauthorized"
    # `HTTPException`'s own detail is preserved and punctuated.
    assert _error(response)["message"] == "Not authenticated."


def test_domain_error_code_derives_from_the_class_name(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "supersecret1"},
    )
    response = client.post(
        "/api/v1/auth/access-token",
        data={"username": "a@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "invalid_credentials"
    assert error["message"] == "Incorrect email or password."
