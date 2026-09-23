from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.approval.manager import ApprovalManager
from backend.approval import models as approval_models  # noqa: F401
from backend.config.settings import Settings
from backend.llm.base import LLMProvider
from backend.memory import models as memory_models  # noqa: F401
from backend.memory.extractor import MemoryExtractor
from backend.memory.retrieval import SQLAlchemyMemoryRetriever
from backend.memory.store import MemoryStore
from backend.runtime.actions import AgentAction
from backend.runtime.loop import AgentRuntime
from backend.storage import models as storage_models  # noqa: F401
from backend.storage.database import Base
from backend.tools.builtin.approval_demo import ApprovalDemoTool
from backend.tools.builtin.calculator import CalculatorTool
from backend.tools.builtin.files import ReadFileTool, SearchFilesTool
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy
from backend.tools.registry import ToolRegistry
from backend.trace import models as trace_models  # noqa: F401
from backend.trace.store import TraceStore


class FakeLLMProvider(LLMProvider):
    def __init__(self, actions: list[AgentAction]) -> None:
        self.actions = actions
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentAction:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.actions:
            raise RuntimeError("No fake LLM actions left.")
        return self.actions.pop(0)


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite://",
        llm_provider="fake",
        llm_base_url=None,
        llm_api_key="test",
        llm_model="test-model",
        workspace_dir=tmp_path,
        max_steps=8,
    )


def make_registry(workspace: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(ReadFileTool(workspace))
    registry.register(SearchFilesTool(workspace))
    registry.register(ApprovalDemoTool())
    return registry


def make_runtime(
    session: Session,
    settings: Settings,
    provider: FakeLLMProvider,
    policy: ToolPolicy | None = None,
    max_steps: int | None = None,
) -> AgentRuntime:
    registry = make_registry(settings.workspace_dir)
    trace_store = TraceStore(session)
    memory_store = MemoryStore(session)
    return AgentRuntime(
        session=session,
        llm_provider=provider,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry),
        tool_policy=policy or ToolPolicy(),
        approval_manager=ApprovalManager(session),
        trace_store=trace_store,
        memory_retriever=SQLAlchemyMemoryRetriever(session),
        memory_extractor=MemoryExtractor(memory_store, trace_store),
        max_steps=max_steps or settings.max_steps,
    )
