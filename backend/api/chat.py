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
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None = None
    approval_id: str | None = None
    trace: list[dict[str, Any]]


def to_response(result: AgentRunResult) -> ChatResponse:
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
    try:
        runtime = build_runtime(session, settings)
        return to_response(runtime.start(request.message))
    except LLMProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
