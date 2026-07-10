from fastapi.testclient import TestClient


def test_health_endpoint_returns_healthy(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv(
        "KEYCLOAK_ISSUER",
        "https://auth.test/realms/devops-lvlup",
    )
    monkeypatch.setenv(
        "KEYCLOAK_JWKS_URL",
        ("https://auth.test/realms/devops-lvlup/protocol/openid-connect/certs"),
    )

    from main import app

    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
