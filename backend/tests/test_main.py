from fastapi.testclient import TestClient

def test_root_returns_appliction_status(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "AI Security RAG Firewall API is running",
        "status": "ok",
    }

def test_health_check_returns_healthy(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
    }

def test_openapi_schema_describes_application(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert schema["info"]["title"] == "AI Security RAG Firewall"
    assert schema["info"]["version"] == "0.1.0"
    assert "/" in schema["paths"]
    assert "/health" in schema["paths"]

def test_swagger_documentation_is_available(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]