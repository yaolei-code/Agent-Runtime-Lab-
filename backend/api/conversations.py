"""Conversation 列表及其持久化消息历史 API。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.conversation.store import ConversationStore
from backend.storage.database import get_session

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationMessage(BaseModel):
    id: str
    run_id: str
    role: str
    content: str | None
    tool_call_id: str | None
    tool_name: str | None
    sequence: int
    created_at: datetime


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    request: ConversationCreate,
    session: Session = Depends(get_session),
) -> ConversationSummary:
    conversation = ConversationStore(session).create(request.title)
    session.commit()
    return ConversationSummary(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[ConversationSummary]:
    return [
        ConversationSummary(
            conversation_id=item.id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in ConversationStore(session).list_recent(limit)
    ]


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessage])
def list_conversation_messages(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> list[ConversationMessage]:
    store = ConversationStore(session)
    try:
        messages = store.list_messages(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        ConversationMessage(
            id=item.id,
            run_id=item.run_id,
            role=item.role,
            content=item.content,
            tool_call_id=item.tool_call_id,
            tool_name=item.tool_name,
            sequence=item.sequence,
            created_at=item.created_at,
        )
        for item in messages
    ]
