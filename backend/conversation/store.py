"""Conversation 生命周期和多 Run 消息历史查询。"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.conversation.models import ConversationRecord
from backend.runtime.status import RunStatus
from backend.storage.models import AgentRunRecord, MessageRecord, new_id


class ConversationStore:
    """将 Conversation 数据访问从 Agent Loop 中隔离出来。"""

    def __init__(self, session: Session, history_run_limit: int = 6) -> None:
        self.session = session
        self.history_run_limit = max(1, history_run_limit)

    def create(self, first_message: str) -> ConversationRecord:
        title = " ".join(first_message.split())[:80] or "New conversation"
        conversation = ConversationRecord(id=new_id("conv"), title=title)
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def get(self, conversation_id: str) -> ConversationRecord | None:
        return self.session.get(ConversationRecord, conversation_id)

    def require(self, conversation_id: str) -> ConversationRecord:
        conversation = self.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")
        return conversation

    def touch(self, conversation: ConversationRecord) -> None:
        conversation.updated_at = datetime.utcnow()
        self.session.flush()

    def list_recent(self, limit: int = 50) -> list[ConversationRecord]:
        safe_limit = max(1, min(limit, 100))
        return self.session.scalars(
            select(ConversationRecord)
            .order_by(ConversationRecord.updated_at.desc())
            .limit(safe_limit)
        ).all()

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        self.require(conversation_id)
        return self.session.scalars(
            select(MessageRecord)
            .join(AgentRunRecord, MessageRecord.run_id == AgentRunRecord.id)
            .where(AgentRunRecord.conversation_id == conversation_id)
            .order_by(
                AgentRunRecord.created_at,
                AgentRunRecord.id,
                MessageRecord.sequence,
            )
        ).all()

    def context_messages(
        self,
        conversation_id: str,
        current_run_id: str,
    ) -> list[dict[str, Any]]:
        """加载最近已完成 Run 与当前 Run，排除残缺的历史执行。"""

        prior_run_ids = list(
            self.session.scalars(
                select(AgentRunRecord.id)
                .where(
                    AgentRunRecord.conversation_id == conversation_id,
                    AgentRunRecord.id != current_run_id,
                    AgentRunRecord.status == RunStatus.COMPLETED.value,
                )
                .order_by(AgentRunRecord.created_at.desc(), AgentRunRecord.id.desc())
                .limit(self.history_run_limit)
            ).all()
        )
        included_run_ids = [current_run_id, *prior_run_ids]
        records = self.session.scalars(
            select(MessageRecord)
            .join(AgentRunRecord, MessageRecord.run_id == AgentRunRecord.id)
            .where(
                AgentRunRecord.conversation_id == conversation_id,
                AgentRunRecord.id.in_(included_run_ids),
            )
            .order_by(
                AgentRunRecord.created_at,
                AgentRunRecord.id,
                MessageRecord.sequence,
            )
        ).all()
        return [record.raw or self._message_to_dict(record) for record in records]

    @staticmethod
    def _message_to_dict(record: MessageRecord) -> dict[str, Any]:
        message: dict[str, Any] = {"role": record.role, "content": record.content}
        if record.tool_call_id:
            message["tool_call_id"] = record.tool_call_id
        if record.tool_name:
            message["name"] = record.tool_name
        return message
