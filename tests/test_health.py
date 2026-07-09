import os

from fastapi.testclient import TestClient


def test_health_endpoint_returns_healthy():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    from main import app

    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}