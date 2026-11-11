from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"data": {"message": "ok"}}


def test_old_health_path_is_gone(client: TestClient) -> None:
    assert client.get("/api/v1/utils/health-check/").status_code == 404


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["data"]["docs"] == "/docs"
