"""FastAPI 后端入口"""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database.db_manager import init_db
from backend.routers.answer import router as answer_router
from backend.routers.auth import router as auth_router
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
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(chat_router)
app.include_router(diagnosis_router)
app.include_router(answer_router)
app.include_router(practice_router)

# 管理路由（同步新闻等）
try:
    from backend.routers.admin import router as admin_router
    app.include_router(admin_router)
except ImportError:
    logger.warning("admin 路由不可用")



# ---------------------------------------------------------------------------
# 自动启动笔记监控 (Note Watcher)
# ---------------------------------------------------------------------------

def _start_note_watcher() -> None:
    """在后台线程中启动笔记监控。"""
    try:
        from knowledge_base.note_watcher import watch
        
        logger.info("启动笔记文件监控后台线程...")
        watcher_thread = threading.Thread(
            target=watch,
            kwargs={
                "notes_dir": None,  # 使用环境变量或默认值
                "persist_dir": None,  # 使用环境变量或默认值
                "once": False,  # 持续监控
            },
            daemon=True,
        )
        watcher_thread.start()
    except ImportError:
        logger.warning("note_watcher 模块不可用，跳过笔记监控")
    except Exception as exc:
        logger.error("启动笔记监控失败: %s", exc)


def _sync_github_news() -> None:
    """在后台线程中同步 GitHub 新闻。"""
    try:
        from utils.github_news_spider import GitHubNewsSpider
        
        logger.info("开始同步 GitHub 新闻...")
        spider = GitHubNewsSpider()
        result = spider.download_all_news(resume=True)
        
        logger.info(
            f"GitHub 新闻同步完成: "
            f"总数={result['total']}, "
            f"成功={result['success']}, "
            f"失败={result['failed']}, "
            f"跳过={result['skipped']}"
        )
    except ImportError:
        logger.warning("github_news_spider 模块不可用，跳过新闻同步")
    except Exception as exc:
        logger.error("同步 GitHub 新闻失败: %s", exc)


@app.on_event("startup")
def startup_event() -> None:
    """应用启动事件处理。"""
    _start_note_watcher()
    
    # 在后台线程中同步 GitHub 新闻（非阻塞）
    news_sync_thread = threading.Thread(
        target=_sync_github_news,
        daemon=True,
    )
    news_sync_thread.start()


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
