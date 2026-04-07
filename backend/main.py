"""FastAPI 后端入口"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database.db_manager import init_db
from backend.routers.answer import router as answer_router
from backend.routers.chat import router as chat_router
from backend.routers.diagnosis import router as diagnosis_router
from backend.routers.notes import router as notes_router
from backend.routers.practice import router as practice_router

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# 初始化用户数据库（幂等，已存在不重建）
try:
    init_db()
except Exception as _db_exc:  # pragma: no cover
    logger.warning("userdata.db initialization failed: %s", _db_exc)

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
