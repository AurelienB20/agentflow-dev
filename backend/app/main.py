"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings

MAX_BODY_BYTES = 64 * 1024


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentFlow Dev API",
        description="Multi-agent orchestration (LangGraph) for software development tasks.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Session-Id", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)

    app.include_router(router)

    @app.get("/")
    async def root() -> dict:
        return {"name": "AgentFlow Dev API", "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
