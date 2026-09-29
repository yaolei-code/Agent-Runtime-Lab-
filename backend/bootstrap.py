"""应用依赖装配辅助函数。

runtime 刻意由多个小协作者组装而成，而不是在内部自己创建所有对象。
这样可以让 Agent Loop 更容易测试，也避免 provider、storage、tool、
policy、memory、trace 等职责塌缩成一个巨大的类。
"""

from sqlalchemy.orm import Session

from backend.approval.manager import ApprovalManager
from backend.checkpoint.store import CheckpointStore
from backend.config.settings import Settings
from backend.conversation.store import ConversationStore
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
from backend.tools.execution_store import ToolExecutionStore
from backend.tools.policy import ToolPolicy
from backend.tools.registry import ToolRegistry
from backend.trace.store import TraceStore


def build_tool_registry(settings: Settings) -> ToolRegistry:
    """注册当前内置工具集合。

    文件类工具在这里拿到 workspace 边界，因此 runtime 不需要知道文件系统
    策略细节。
    """

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
    """为一次请求/session 作用域创建 AgentRuntime。

    调用方可以注入 provider，测试就是通过这个方式在没有真实 LLM 的情况下
    跑完整 loop。所有依赖持久化的协作者共享同一个 SQLAlchemy session，
    这样一次 run 的状态转换可以在同一事务上下文中提交。
    """

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
        checkpoint_store=CheckpointStore(session),
        conversation_store=ConversationStore(session, settings.conversation_history_runs),
        tool_execution_store=ToolExecutionStore(session),
        memory_retriever=SQLAlchemyMemoryRetriever(session),
        memory_extractor=MemoryExtractor(memory_store, trace_store),
        max_steps=settings.max_steps,
    )


def build_llm_provider(settings: Settings) -> LLMProvider:
    """根据配置选择 LLM provider 实现。"""

    if settings.llm_provider == "fake":
        return FakeRuleBasedProvider()
    return OpenAICompatibleProvider(settings)
