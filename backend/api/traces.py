from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.storage.database import get_session
from backend.trace.store import TraceStore

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/{run_id}")
def get_trace(run_id: str, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return TraceStore(session).list_for_run(run_id)
