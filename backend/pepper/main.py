"""FastAPI app. Run with: uvicorn pepper.main:app"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pepper import db
from pepper.api import cases, decisions, devices, health, integrations, ot_lists, threads, webhooks
from pepper.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    db.configure(settings.database_url)
    await db.create_all()
    yield
    await db.dispose()


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="Pepper", version="2.0.0", lifespan=lifespan)
    origins = get_settings().cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        )
    for module in (health, devices, threads, decisions, integrations, cases, ot_lists, webhooks):
        app.include_router(module.router)
    return app


app = create_app()
