from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.approval.manager import ApprovalManager
from backend.bootstrap import build_runtime
from backend.config.settings import Settings, load_settings
from backend.llm.base import LLMProviderError
from backend.storage.database import get_session
from backend.api.chat import ChatResponse, to_response

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("")
def list_approvals(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return ApprovalManager(session).list_pending()


@router.post("/{approval_id}/approve", response_model=ChatResponse)
def approve(
    approval_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(load_settings),
) -> ChatResponse:
    try:
        runtime = build_runtime(session, settings)
        return to_response(runtime.resume_from_approval(approval_id, approved=True))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{approval_id}/reject", response_model=ChatResponse)
def reject(
    approval_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(load_settings),
) -> ChatResponse:
    try:
        runtime = build_runtime(session, settings)
        return to_response(runtime.resume_from_approval(approval_id, approved=False))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
