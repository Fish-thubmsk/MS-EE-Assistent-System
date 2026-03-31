"""FastAPI 后端入口"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database.db_manager import init_db_manager
from backend.routers.answer import router as answer_router
from backend.routers.chat import router as chat_router
from backend.routers.diagnosis import router as diagnosis_router
from backend.routers.notes import router as notes_router
from backend.routers.practice import router as practice_router
from backend.routers.users import router as users_router

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 应用生命周期：启动时初始化用户数据库
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用启动时初始化用户数据库，关闭时无需额外清理。"""
    init_db_manager(f"sqlite:///{settings.userdata_db_path}")
    logger.info("userdata database ready at %s", settings.userdata_db_path)
    yield


app = FastAPI(
    title=settings.app_title,
    description=(
        "基于 FastAPI + LangGraph + ChromaDB + SiliconFlow 的考研智能辅导系统。\n\n"
        "支持 SSE 流式输出、RAG 问答、刷题批改与学习诊断。"
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS 中间件
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------
app.include_router(notes_router)
app.include_router(chat_router)
app.include_router(diagnosis_router)
app.include_router(answer_router)
app.include_router(practice_router)
app.include_router(users_router)


# ---------------------------------------------------------------------------
# 根路由 & 健康检查
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health", tags=["health"])
def health_detail() -> dict[str, str]:
    """返回服务版本和运行状态。"""
    return {"status": "ok", "version": settings.app_version}
