"""FastAPI application entrypoint for the Manufacturing Agent API."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing the runtime initializes the heavy resources (Chroma / SQLite /
    # the compiled LangGraph). Do this once at startup so the first request is
    # not penalized. No LLM call happens at import time.
    import manufacturing_agent.runtime  # noqa: F401

    yield


app = FastAPI(title="Manufacturing Agent API", lifespan=lifespan)

# CORS: 프론트엔드(Vite dev: 5173, Next dev: 3000) 호출 허용.
# 사내/게이트웨이 뒤 단일 서비스이므로 dev origin 허용 + 환경변수로 확장 가능.
_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
from api.routers.chat import router as chat_router  # noqa: E402
from api.routers.health import router as health_router  # noqa: E402
from api.routers.history import router as history_router  # noqa: E402
from api.routers.users import router as users_router  # noqa: E402
from api.routers.usage import router as usage_router  # noqa: E402

app.include_router(users_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(history_router)
app.include_router(usage_router)


@app.get("/")
def root():
    return {"service": "Manufacturing Agent API"}
