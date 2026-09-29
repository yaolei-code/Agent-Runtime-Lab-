from fastapi.testclient import TestClient

from backend.config.settings import load_settings
from backend.llm.base import LLMProvider
from backend.main import create_app
from backend.runtime.actions import FinalAnswerAction, ToolCallAction
from backend.runtime.status import RunStatus
from backend.storage.database import get_session
from tests.conftest import FakeLLMProvider, make_runtime


class FailingProvider(LLMProvider):
    def complete(self, messages, tools):
        raise RuntimeError("temporary outage")


def message_contents(call):
    return [item.get("content") for item in call["messages"] if item.get("content")]


def test_second_run_receives_completed_conversation_history(db_session, settings):
    first_provider = FakeLLMProvider(
        [FinalAnswerAction(kind="final_answer", content="first answer")]
    )
    first = make_runtime(db_session, settings, first_provider).start("first question")

    second_provider = FakeLLMProvider(
        [FinalAnswerAction(kind="final_answer", content="second answer")]
    )
    second = make_runtime(db_session, settings, second_provider).start(
        "follow up",
        first.conversation_id,
    )

    contents = message_contents(second_provider.calls[0])
    assert second.conversation_id == first.conversation_id
    assert "first question" in contents
    assert "first answer" in contents
    assert "follow up" in contents


def test_different_conversations_do_not_share_messages(db_session, settings):
    first = make_runtime(
        db_session,
        settings,
        FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="private answer")]),
    ).start("private question")
    second_provider = FakeLLMProvider(
        [FinalAnswerAction(kind="final_answer", content="other answer")]
    )

    second = make_runtime(db_session, settings, second_provider).start("other question")

    contents = message_contents(second_provider.calls[0])
    assert second.conversation_id != first.conversation_id
    assert "private question" not in contents
    assert "private answer" not in contents


def test_failed_prior_run_is_excluded_from_context(db_session, settings):
    failed = make_runtime(db_session, settings, FailingProvider()).start("failed question")
    assert failed.status == RunStatus.FAILED.value
    provider = FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="recovered")])

    make_runtime(db_session, settings, provider).start(
        "new question",
        failed.conversation_id,
    )

    contents = message_contents(provider.calls[0])
    assert "failed question" not in contents
    assert "new question" in contents


def test_completed_tool_exchange_is_preserved_in_next_run_context(db_session, settings):
    tool_action = ToolCallAction(
        kind="tool_call",
        call_id="call_history",
        tool_name="calculator",
        arguments={"expression": "2 + 3"},
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_history",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": '{"expression":"2 + 3"}'},
                }
            ],
        },
    )
    first = make_runtime(
        db_session,
        settings,
        FakeLLMProvider(
            [tool_action, FinalAnswerAction(kind="final_answer", content="the result is 5")]
        ),
    ).start("calculate")
    provider = FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="continued")])

    make_runtime(db_session, settings, provider).start("continue", first.conversation_id)

    history = [item for item in provider.calls[0]["messages"] if item["role"] != "system"]
    assert [item["role"] for item in history] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert history[1]["tool_calls"][0]["id"] == "call_history"
    assert history[2]["tool_call_id"] == "call_history"


def test_chat_api_creates_and_continues_conversation(db_session, settings):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    first_response = client.post("/chat", json={"message": "hello"})
    assert first_response.status_code == 200
    first = first_response.json()
    assert first["conversation_id"].startswith("conv_")

    second_response = client.post(
        "/chat",
        json={"message": "follow up", "conversation_id": first["conversation_id"]},
    )
    assert second_response.status_code == 200
    assert second_response.json()["conversation_id"] == first["conversation_id"]

    conversations = client.get("/conversations").json()
    assert conversations[0]["conversation_id"] == first["conversation_id"]
    history = client.get(f"/conversations/{first['conversation_id']}/messages").json()
    assert [item["role"] for item in history] == ["user", "assistant", "user", "assistant"]
    app.dependency_overrides.clear()


def test_chat_api_rejects_unknown_conversation(db_session, settings):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[load_settings] = lambda: settings
    client = TestClient(app)

    response = client.post(
        "/chat",
        json={"message": "hello", "conversation_id": "conv_missing"},
    )

    assert response.status_code == 404
    app.dependency_overrides.clear()
