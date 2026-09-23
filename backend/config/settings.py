from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_provider: str
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    workspace_dir: Path
    max_steps: int


def load_settings() -> Settings:
    workspace = Path(os.getenv("WORKSPACE_DIR", ".")).resolve()
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/agent.db"),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_base_url=os.getenv("LLM_BASE_URL"),
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_model=os.getenv("LLM_MODEL"),
        workspace_dir=workspace,
        max_steps=int(os.getenv("AGENT_MAX_STEPS", "8")),
    )
