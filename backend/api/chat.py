"""启动 Agent Run 的 Chat API 入口。

这个模块刻意保持很薄：校验 HTTP 请求，按请求作用域组装 runtime，
启动 run，然后把 runtime 结果映射成 API response。真正的 Agent 行为
放在 runtime 层，而不是 API 层。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.bootstrap import build_runtime
from backend.config.settings import Settings, load_settings
from backend.llm.base import LLMProviderError
from backend.runtime.state import AgentRunResult
from backend.storage.database import get_session

router = APIRouter()


class ChatRequest(BaseModel):
    """POST /chat 的请求体。"""

    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """run 完成、失败或暂停时返回给前端的公开响应结构。"""

    run_id: str
    status: str
    answer: str | None = None
    approval_id: str | None = None
    trace: list[dict[str, Any]]


def to_response(result: AgentRunResult) -> ChatResponse:
    """把 API schema 和 runtime 内部结果对象隔离开。"""

    return ChatResponse(
        run_id=result.run_id,
        status=result.status,
        answer=result.answer,
        approval_id=result.approval_id,
        trace=result.trace,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(load_settings),
) -> ChatResponse:
    """根据用户消息启动一个新的 run。

    FastAPI 会注入 SQLAlchemy session 和从环境变量读取的 settings。
    这个路由只处理 HTTP 层事务；build_runtime() 负责依赖装配，
    AgentRuntime.start() 负责真正的 harness loop。
    """

    try:
        runtime = build_runtime(session, settings)
        return to_response(runtime.start(request.message))
    except LLMProviderError as exc:
        # 请求本身合法，但当前配置的模型 provider 无法使用。
        raise HTTPException(status_code=500, detail=str(exc)) from exc
