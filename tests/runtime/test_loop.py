from backend.runtime.actions import FinalAnswerAction, ToolCallAction
from backend.runtime.events import TraceEventType
from backend.tools.base import RiskLevel
from backend.tools.policy import ToolPolicy
from tests.conftest import FakeLLMProvider, make_runtime


def tool_call(name: str, arguments: dict, call_id: str = "call_1") -> ToolCallAction:
    return ToolCallAction(
        kind="tool_call",
        call_id=call_id,
        tool_name=name,
        arguments=arguments,
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": "{}"},
                }
            ],
        },
    )


def event_types(result):
    return [item["type"] for item in result.trace]


def test_final_answer(db_session, settings):
    provider = FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="done")])
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("hello")

    assert result.status == "completed"
    assert result.answer == "done"
    assert TraceEventType.RUN_COMPLETED.value in event_types(result)


def test_single_tool_call(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "123 * 456"}),
            FinalAnswerAction(kind="final_answer", content="123 * 456 = 56088"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("calculate")

    assert result.status == "completed"
    assert result.answer == "123 * 456 = 56088"
    assert TraceEventType.TOOL_COMPLETED.value in event_types(result)


def test_multi_tool_call(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "2 + 3"}, "call_1"),
            tool_call("calculator", {"expression": "5 * 4"}, "call_2"),
            FinalAnswerAction(kind="final_answer", content="20"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("two steps")

    assert result.status == "completed"
    assert event_types(result).count(TraceEventType.TOOL_COMPLETED.value) == 2


def test_unknown_tool_does_not_crash(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("missing_tool", {"x": 1}),
            FinalAnswerAction(kind="final_answer", content="could not use missing tool"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("unknown")

    assert result.status == "completed"
    assert TraceEventType.TOOL_FAILED.value in event_types(result)


def test_tool_exception_becomes_tool_failed(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "__import__('os')"}),
            FinalAnswerAction(kind="final_answer", content="tool failed"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("bad calc")

    assert result.status == "completed"
    assert TraceEventType.TOOL_FAILED.value in event_types(result)


def test_max_steps_stops_loop(db_session, settings):
    provider = FakeLLMProvider([tool_call("calculator", {"expression": "1 + 1"})])
    runtime = make_runtime(db_session, settings, provider, max_steps=1)

    result = runtime.start("loop")

    assert result.status == "failed"
    assert "max_steps" in result.answer


def test_policy_approval_pause(db_session, settings):
    provider = FakeLLMProvider([tool_call("approval_demo", {"reason": "demo"})])
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("needs approval")

    assert result.status == "waiting_for_approval"
    assert result.approval_id is not None
    assert TraceEventType.APPROVAL_REQUESTED.value in event_types(result)


def test_policy_block(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("approval_demo", {"reason": "demo"}),
            FinalAnswerAction(kind="final_answer", content="blocked"),
        ]
    )
    policy = ToolPolicy(approvals_required=set(), blocked={RiskLevel.WRITE})
    runtime = make_runtime(db_session, settings, provider, policy=policy)

    result = runtime.start("blocked")

    assert result.status == "completed"
    assert TraceEventType.TOOL_FAILED.value in event_types(result)


def test_approval_resume(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("approval_demo", {"reason": "demo"}),
            FinalAnswerAction(kind="final_answer", content="approved and finished"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    paused = runtime.start("needs approval")
    resumed = runtime.resume_from_approval(paused.approval_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.answer == "approved and finished"
    assert TraceEventType.APPROVAL_RESOLVED.value in event_types(resumed)
