from fastapi.testclient import TestClient

from backend.checkpoint.store import CheckpointStore
from backend.config.settings import load_settings
from backend.main import create_app
from backend.storage.database import get_session
from backend.storage.models import AgentRunRecord, MessageRecord


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


def test_resume_unknown_run_returns_404(db_session, settings):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/missing/resume")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_resume_completed_run_returns_409(db_session, settings):
    run = AgentRunRecord(
        id="run_completed",
        status="completed",
        user_input="hello",
        answer="done",
        steps=1,
    )
    db_session.add(run)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/run_completed/resume")

    assert response.status_code == 409
    app.dependency_overrides.clear()


def test_resume_waiting_for_approval_returns_409(db_session, settings):
    run = AgentRunRecord(
        id="run_waiting",
        status="waiting_for_approval",
        user_input="hello",
        steps=1,
    )
    db_session.add(run)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/run_waiting/resume")

    assert response.status_code == 409
    assert "approval" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_resume_running_run_returns_409(db_session, settings):
    run = AgentRunRecord(
        id="run_running",
        status="running",
        user_input="hello",
        steps=1,
    )
    db_session.add(run)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/run_running/resume")

    assert response.status_code == 409
    app.dependency_overrides.clear()


def test_resume_failed_run_without_checkpoint_returns_409(db_session, settings):
    run = AgentRunRecord(
        id="run_no_checkpoint",
        status="failed",
        user_input="hello",
        answer="failed",
        steps=1,
    )
    db_session.add(run)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/run_no_checkpoint/resume")

    assert response.status_code == 409
    assert "safe checkpoint" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_resume_failed_run_with_safe_checkpoint(db_session, settings):
    run = AgentRunRecord(
        id="run_resume",
        status="failed",
        user_input="hello",
        answer="failed",
        steps=1,
    )
    db_session.add(run)
    db_session.add(
        MessageRecord(
            id="msg_resume",
            run_id=run.id,
            role="user",
            content="hello",
            raw={"role": "user", "content": "hello"},
            sequence=1,
        )
    )
    db_session.flush()
    CheckpointStore(db_session).append(
        run.id,
        step=1,
        kind="before_llm",
        run_status="running",
        message_count=1,
    )
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post("/runs/run_resume/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run_resume"
    assert payload["status"] == "completed"
    app.dependency_overrides.clear()
