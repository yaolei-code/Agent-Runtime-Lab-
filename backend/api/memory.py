from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.memory.store import MemoryStore
from backend.storage.database import get_session

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def list_memory(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return MemoryStore(session).list()


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, session: Session = Depends(get_session)) -> dict[str, bool]:
    deleted = MemoryStore(session).delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found.")
    session.commit()
    return {"deleted": True}
