from fastapi.testclient import TestClient

from backend.main import create_app


def test_tools_endpoint_lists_registered_tools():
    client = TestClient(create_app())

    response = client.get("/tools")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"calculator", "read_file", "search_files", "approval_demo"} <= names
