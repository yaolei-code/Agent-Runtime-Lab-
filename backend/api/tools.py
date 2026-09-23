from fastapi import APIRouter, Depends

from backend.bootstrap import build_tool_registry
from backend.config.settings import Settings, load_settings

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools(settings: Settings = Depends(load_settings)) -> list[dict]:
    return build_tool_registry(settings).public_tools()
