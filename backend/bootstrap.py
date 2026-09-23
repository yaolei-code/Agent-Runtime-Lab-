from sqlalchemy.orm import Session

from backend.approval.manager import ApprovalManager
from backend.config.settings import Settings
from backend.llm.base import LLMProvider
from backend.llm.fake import FakeRuleBasedProvider
from backend.llm.openai_compatible import OpenAICompatibleProvider
from backend.memory.extractor import MemoryExtractor
from backend.memory.retrieval import SQLAlchemyMemoryRetriever
from backend.memory.store import MemoryStore
from backend.runtime.loop import AgentRuntime
from backend.tools.builtin.approval_demo import ApprovalDemoTool
from backend.tools.builtin.calculator import CalculatorTool
from backend.tools.builtin.files import ReadFileTool, SearchFilesTool
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy
from backend.tools.registry import ToolRegistry
from backend.trace.store import TraceStore


def build_tool_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(ReadFileTool(settings.workspace_dir))
    registry.register(SearchFilesTool(settings.workspace_dir))
    registry.register(ApprovalDemoTool())
    return registry


def build_runtime(
    session: Session,
    settings: Settings,
    provider: LLMProvider | None = None,
) -> AgentRuntime:
    registry = build_tool_registry(settings)
    trace_store = TraceStore(session)
    memory_store = MemoryStore(session)
    provider = provider or build_llm_provider(settings)
    return AgentRuntime(
        session=session,
        llm_provider=provider,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry),
        tool_policy=ToolPolicy(),
        approval_manager=ApprovalManager(session),
        trace_store=trace_store,
        memory_retriever=SQLAlchemyMemoryRetriever(session),
        memory_extractor=MemoryExtractor(memory_store, trace_store),
        max_steps=settings.max_steps,
    )


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeRuleBasedProvider()
    return OpenAICompatibleProvider(settings)
