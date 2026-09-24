from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import approvals, chat, memory, runs, tools, traces


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Agent Hub v2", version="0.1.0")
    app.include_router(chat.router)
    app.include_router(approvals.router)
    app.include_router(memory.router)
    app.include_router(runs.router)
    app.include_router(traces.router)
    app.include_router(tools.router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
