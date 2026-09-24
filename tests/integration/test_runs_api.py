from fastapi.testclient import TestClient

from backend.main import create_app
from backend.storage.database import get_session
from backend.storage.models import AgentRunRecord


def test_list_runs_returns_recent_runs(db_session):
    run = AgentRunRecord(
        id="run_test",
        status="completed",
        user_input="hello",
        answer="world",
        steps=2,
    )
    db_session.add(run)
    db_session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["run_id"] == "run_test"
    assert payload[0]["status"] == "completed"
    app.dependency_overrides.clear()


def test_get_run_returns_detail(db_session):
    run = AgentRunRecord(
        id="run_detail",
        status="failed",
        user_input="bad",
        answer="failed",
        steps=1,
    )
    db_session.add(run)
    db_session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/runs/run_detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run_detail"
    assert payload["pending_approval"] is None
    app.dependency_overrides.clear()


def test_get_unknown_run_returns_404(db_session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)

    response = client.get("/runs/missing")

    assert response.status_code == 404
    app.dependency_overrides.clear()
