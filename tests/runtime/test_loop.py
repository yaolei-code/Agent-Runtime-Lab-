import pytest
from sqlalchemy import select

from backend.checkpoint.models import RunCheckpointRecord
from backend.checkpoint.store import CheckpointStore
from backend.llm.base import LLMProvider
from backend.runtime.actions import FinalAnswerAction, ToolCallAction
from backend.runtime.events import TraceEventType
from backend.runtime.status import RunStatus
from backend.storage.models import AgentRunRecord, MessageRecord
from backend.tools.base import RiskLevel
from backend.tools.execution_models import ToolExecutionRecord, ToolExecutionStatus
from backend.tools.execution_store import ToolExecutionStore
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


class FailingProvider(LLMProvider):
    def complete(self, messages, tools):
        raise RuntimeError("temporary outage")


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
    execution = db_session.scalar(
        select(ToolExecutionRecord).where(ToolExecutionRecord.run_id == result.run_id)
    )
    assert execution.status == ToolExecutionStatus.COMPLETED.value
    assert execution.result_content == "56088"


def test_duplicate_tool_call_id_reuses_completed_result(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "2 + 3"}, "call_same"),
            tool_call("calculator", {"expression": "2 + 3"}, "call_same"),
            FinalAnswerAction(kind="final_answer", content="5"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("calculate once")

    assert result.status == RunStatus.COMPLETED.value
    assert event_types(result).count(TraceEventType.TOOL_STARTED.value) == 1
    assert TraceEventType.TOOL_RESULT_REUSED.value in event_types(result)
    tool_messages = db_session.scalars(
        select(MessageRecord).where(
            MessageRecord.run_id == result.run_id,
            MessageRecord.role == "tool",
            MessageRecord.tool_call_id == "call_same",
        )
    ).all()
    assert len(tool_messages) == 1


def test_duplicate_tool_call_id_with_different_arguments_fails(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "2 + 3"}, "call_conflict"),
            tool_call("calculator", {"expression": "8 + 9"}, "call_conflict"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("conflicting call")

    assert result.status == RunStatus.FAILED.value
    assert "does not match" in result.answer
    assert event_types(result).count(TraceEventType.TOOL_STARTED.value) == 1


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


def test_checkpoints_are_created_for_tool_run(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("calculator", {"expression": "123 * 456"}),
            FinalAnswerAction(kind="final_answer", content="123 * 456 = 56088"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    result = runtime.start("calculate")

    checkpoints = db_session.scalars(
        select(RunCheckpointRecord)
        .where(RunCheckpointRecord.run_id == result.run_id)
        .order_by(RunCheckpointRecord.sequence)
    ).all()
    kinds = [checkpoint.kind for checkpoint in checkpoints]

    assert "run_started" in kinds
    assert "before_llm" in kinds
    assert "after_llm" in kinds
    assert "after_tool" in kinds


def test_resume_failed_run_uses_latest_safe_checkpoint(db_session, settings):
    failing_runtime = make_runtime(db_session, settings, FailingProvider())
    failed = failing_runtime.start("hello")

    assert failed.status == RunStatus.FAILED.value
    assert CheckpointStore(db_session).latest_safe_for_run(failed.run_id).kind == "before_llm"

    provider = FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="recovered")])
    runtime = make_runtime(db_session, settings, provider)
    resumed = runtime.resume_run(failed.run_id)

    assert resumed.status == RunStatus.COMPLETED.value
    assert resumed.answer == "recovered"
    assert TraceEventType.RUN_RESUMED.value in event_types(resumed)


def test_resume_rejects_checkpoint_when_messages_diverged(db_session, settings):
    failing_runtime = make_runtime(db_session, settings, FailingProvider())
    failed = failing_runtime.start("hello")
    db_session.add(
        MessageRecord(
            id="msg_diverged",
            run_id=failed.run_id,
            role="assistant",
            content="uncommitted later state",
            raw={"role": "assistant", "content": "uncommitted later state"},
            sequence=2,
        )
    )
    db_session.commit()

    runtime = make_runtime(
        db_session,
        settings,
        FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="should not run")]),
    )

    with pytest.raises(ValueError, match="diverged"):
        runtime.resume_run(failed.run_id)


def test_resume_rejects_uncertain_tool_execution(db_session, settings):
    failing_runtime = make_runtime(db_session, settings, FailingProvider())
    failed = failing_runtime.start("hello")
    execution_store = ToolExecutionStore(db_session)
    execution = execution_store.begin(
        failed.run_id,
        "call_uncertain",
        "calculator",
        {"expression": "1 + 1"},
    )
    db_session.commit()

    runtime = make_runtime(db_session, settings, FakeLLMProvider([]))

    with pytest.raises(ValueError, match="unknown outcome"):
        runtime.resume_run(failed.run_id)

    db_session.refresh(execution)
    assert execution.status == ToolExecutionStatus.UNKNOWN.value


def test_resume_after_max_steps_gets_fresh_attempt_budget(db_session, settings):
    first_runtime = make_runtime(
        db_session,
        settings,
        FakeLLMProvider([tool_call("calculator", {"expression": "1 + 1"})]),
        max_steps=1,
    )
    failed = first_runtime.start("calculate")
    assert failed.status == RunStatus.FAILED.value

    resumed_runtime = make_runtime(
        db_session,
        settings,
        FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="2")]),
        max_steps=1,
    )
    resumed = resumed_runtime.resume_run(failed.run_id)

    assert resumed.status == RunStatus.COMPLETED.value
    assert resumed.answer == "2"
    assert db_session.get(AgentRunRecord, failed.run_id).steps == 2


def test_completed_run_cannot_resume(db_session, settings):
    provider = FakeLLMProvider([FinalAnswerAction(kind="final_answer", content="done")])
    runtime = make_runtime(db_session, settings, provider)
    result = runtime.start("hello")

    with pytest.raises(ValueError, match="Completed"):
        runtime.resume_run(result.run_id)


def test_running_run_cannot_resume(db_session, settings):
    run = AgentRunRecord(
        id="run_running",
        status=RunStatus.RUNNING.value,
        user_input="hello",
        steps=0,
    )
    db_session.add(run)
    db_session.commit()
    runtime = make_runtime(db_session, settings, FakeLLMProvider([]))

    with pytest.raises(ValueError, match="Running"):
        runtime.resume_run(run.id)


def test_resume_requires_safe_checkpoint(db_session, settings):
    run = AgentRunRecord(
        id="run_without_checkpoint",
        status=RunStatus.FAILED.value,
        user_input="hello",
        answer="failed",
        steps=1,
    )
    db_session.add(run)
    db_session.add(
        MessageRecord(
            id="msg_without_checkpoint",
            run_id=run.id,
            role="user",
            content="hello",
            raw={"role": "user", "content": "hello"},
            sequence=1,
        )
    )
    db_session.commit()
    runtime = make_runtime(db_session, settings, FakeLLMProvider([]))

    with pytest.raises(ValueError, match="no safe checkpoint"):
        runtime.resume_run(run.id)


def test_approval_pause_checkpoint_does_not_break_approval_resume(db_session, settings):
    provider = FakeLLMProvider(
        [
            tool_call("approval_demo", {"reason": "demo"}),
            FinalAnswerAction(kind="final_answer", content="approved and finished"),
        ]
    )
    runtime = make_runtime(db_session, settings, provider)

    paused = runtime.start("needs approval")
    checkpoints = db_session.scalars(
        select(RunCheckpointRecord).where(RunCheckpointRecord.run_id == paused.run_id)
    ).all()
    assert "approval_pause" in [checkpoint.kind for checkpoint in checkpoints]

    resumed = runtime.resume_from_approval(paused.approval_id, approved=True)

    assert resumed.status == RunStatus.COMPLETED.value
    assert resumed.answer == "approved and finished"
