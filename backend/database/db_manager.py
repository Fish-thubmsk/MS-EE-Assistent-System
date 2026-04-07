"""
数据库管理模块

负责 userdata.db 的路径配置、引擎创建和表初始化。

使用方式：
    from backend.database.db_manager import init_db, get_engine, get_userdata_db_path

    # 应用启动时初始化（幂等，可重复调用）
    init_db()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径配置（支持环境变量覆盖）
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", os.getcwd()))

_DEFAULT_USERDATA_DB = str(_REPO_ROOT / "datebase" / "userdata.db")


def get_userdata_db_path() -> str:
    """返回 userdata.db 的绝对路径（可通过 USERDATA_DB_PATH 环境变量覆盖）。"""
    return os.path.abspath(
        os.environ.get("USERDATA_DB_PATH", _DEFAULT_USERDATA_DB)
    )


# ---------------------------------------------------------------------------
# 引擎 & 会话工厂
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """返回全局 SQLAlchemy Engine（延迟初始化，首次调用时创建）。"""
    global _engine
    if _engine is None:
        db_path = get_userdata_db_path()
        # 确保父目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # 为每个 SQLite 连接启用外键约束
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def get_session_factory() -> sessionmaker:
    """返回全局 sessionmaker 工厂（线程安全）。"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal


def get_db() -> Session:
    """
    返回一个新的数据库会话。

    调用方应在使用完毕后手动关闭（``session.close()``），
    或配合 ``with`` 语句使用。
    """
    return get_session_factory()()


# ---------------------------------------------------------------------------
# 初始化：创建所有表
# ---------------------------------------------------------------------------


def init_db() -> None:
    """
    初始化 userdata.db：创建所有 ORM 模型对应的表（幂等，已存在不重建），
    并插入演示用户（若不存在）。

    建议在应用启动时调用一次。
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("userdata.db initialized at %s", get_userdata_db_path())
    _seed_demo_users()


# ---------------------------------------------------------------------------
# 演示用户种子数据
# ---------------------------------------------------------------------------

_DEMO_USERS = [
    {"username": "user_001", "password": "exam2024", "display_name": "同学甲"},
    {"username": "user_002", "password": "exam2024", "display_name": "同学乙"},
    {"username": "user_003", "password": "exam2024", "display_name": "同学丙"},
]


def _seed_demo_users() -> None:
    """插入演示账号（若数据库中尚不存在）。密码使用 bcrypt 哈希存储。"""
    try:
        import bcrypt as _bcrypt  # lazy import to avoid hard dep at module load

        from backend.database.models import User

        session = get_session_factory()()
        try:
            for demo in _DEMO_USERS:
                exists = session.query(User).filter(User.username == demo["username"]).first()
                if not exists:
                    password_hash = _bcrypt.hashpw(
                        demo["password"].encode(), _bcrypt.gensalt()
                    ).decode()
                    session.add(
                        User(
                            username=demo["username"],
                            password_hash=password_hash,
                            display_name=demo["display_name"],
                        )
                    )
            session.commit()
            logger.info("Demo users seeded (or already present).")
        finally:
            session.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("Demo user seeding failed: %s", exc)
