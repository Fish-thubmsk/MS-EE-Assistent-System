"""
用户数据库管理器

封装 userdata.db 的所有 CRUD 操作，提供统一的数据库接入层。
上层路由模块通过 get_db_manager() 获取单例实例。

设计原则：
  - userdata.db 仅存储用户行为数据（quiz_records、chat_sessions、diagnosis_reports、users）
  - knowledge_base.db 保持只读，仅供 Agent 查询题目/知识点
  - 使用 SQLAlchemy 2.x ORM，避免各路由模块散落的原始 sqlite3 调用
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.models import Base, ChatSession, DiagnosisReport, QuizRecord, User

logger = logging.getLogger(__name__)


class DatabaseManager:
    """统一数据库管理器，负责 userdata.db 的初始化与 CRUD 操作。"""

    def __init__(self, db_url: str) -> None:
        """
        初始化数据库连接。

        Args:
            db_url: SQLAlchemy 连接字符串，如 "sqlite:///userdata.db"
                    传入 "sqlite:///:memory:" 时自动启用 StaticPool 以支持内存数据库多连接共享。
        """
        is_memory = db_url == "sqlite:///:memory:"
        engine_kwargs: dict = {
            "connect_args": {"check_same_thread": False},
            "echo": False,
        }
        if is_memory:
            engine_kwargs["poolclass"] = StaticPool

        self._engine = create_engine(db_url, **engine_kwargs)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._init_db()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """创建所有表（若不存在则建表，幂等）。"""
        Base.metadata.create_all(self._engine)
        logger.info("userdata database initialised")

    def get_session(self) -> Session:
        """返回一个新的 SQLAlchemy Session（调用方负责关闭）。"""
        return self._session_factory()

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def get_or_create_user(self, user_id: str, display_name: Optional[str] = None) -> User:
        """获取用户，不存在则自动创建。"""
        with self._session_factory() as session:
            user = session.scalar(select(User).where(User.user_id == user_id))
            if user is None:
                user = User(user_id=user_id, display_name=display_name)
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.debug("Created new user: %s", user_id)
            return user

    def get_user(self, user_id: str) -> Optional[User]:
        """按 user_id 查询用户，不存在返回 None。"""
        with self._session_factory() as session:
            return session.scalar(select(User).where(User.user_id == user_id))

    # ------------------------------------------------------------------
    # QuizRecord CRUD
    # ------------------------------------------------------------------

    def save_quiz_record(
        self,
        user_id: str,
        question: dict[str, Any],
        is_correct: Optional[bool],
        *,
        difficulty: Optional[str] = None,
        time_spent_seconds: Optional[int] = None,
    ) -> QuizRecord:
        """
        保存一条做题记录。

        Args:
            user_id:             用户业务 ID
            question:            当前题目字典（含 id、subject、knowledge_points 等）
            is_correct:          是否答对（None 代表主观题待判断）
            difficulty:          题目难度（可选）
            time_spent_seconds:  作答耗时（可选，单位秒）
        """
        self.get_or_create_user(user_id)  # 确保用户存在

        kps: list[str] = question.get("knowledge_points") or []
        knowledge_point = kps[0] if kps else question.get("knowledge_point", "")

        record = QuizRecord(
            user_id=user_id,
            question_id=question.get("id"),
            subject=question.get("subject", ""),
            knowledge_point=knowledge_point or None,
            is_correct=is_correct,
            difficulty=difficulty or question.get("difficulty"),
            time_spent_seconds=time_spent_seconds,
            answered_at=datetime.now(timezone.utc),
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def get_quiz_records(
        self,
        user_id: str,
        subject: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """
        查询用户的做题历史。

        Args:
            user_id: 用户业务 ID
            subject: 可选学科过滤
            limit:   最多返回条数（默认 200）

        Returns:
            字典列表，每条记录包含完整字段，兼容 diagnosis_agent 期望的格式。
        """
        stmt = (
            select(QuizRecord)
            .where(QuizRecord.user_id == user_id)
            .order_by(QuizRecord.answered_at.desc())
            .limit(limit)
        )
        if subject:
            stmt = stmt.where(QuizRecord.subject == subject)

        with self._session_factory() as session:
            records = session.scalars(stmt).all()

        return [
            {
                "question_id": r.question_id,
                "subject": r.subject or "",
                "knowledge_point": r.knowledge_point or "",
                "is_correct": bool(r.is_correct) if r.is_correct is not None else None,
                "difficulty": r.difficulty,
                "answered_at": r.answered_at.isoformat() if r.answered_at else None,
            }
            for r in records
        ]

    def get_quiz_stats(self, user_id: str) -> dict[str, Any]:
        """
        返回用户的做题统计摘要。

        Returns:
            dict with keys: total, correct, by_subject
        """
        records = self.get_quiz_records(user_id, limit=10_000)
        total = len(records)
        correct = sum(1 for r in records if r["is_correct"] is True)
        by_subject: dict[str, dict[str, int]] = {}
        for r in records:
            subj = r["subject"] or "未知"
            stats = by_subject.setdefault(subj, {"total": 0, "correct": 0})
            stats["total"] += 1
            if r["is_correct"] is True:
                stats["correct"] += 1
        return {"total": total, "correct": correct, "by_subject": by_subject}

    # ------------------------------------------------------------------
    # ChatSession CRUD
    # ------------------------------------------------------------------

    def upsert_chat_session(
        self,
        session_id: str,
        user_id: str,
        mode: str = "qa",
        subject: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
    ) -> ChatSession:
        """
        创建或更新一条会话记录。

        Args:
            session_id: 前端传入的唯一会话 ID
            user_id:    所属用户
            mode:       会话模式（qa / quiz / diagnosis）
            subject:    可选学科范围
            messages:   消息列表（可选，用于历史存档）
        """
        self.get_or_create_user(user_id)
        messages_json = json.dumps(messages, ensure_ascii=False) if messages else None

        with self._session_factory() as session:
            existing = session.scalar(
                select(ChatSession).where(ChatSession.session_id == session_id)
            )
            if existing is None:
                chat = ChatSession(
                    session_id=session_id,
                    user_id=user_id,
                    mode=mode,
                    subject=subject,
                    messages_json=messages_json,
                )
                session.add(chat)
            else:
                existing.mode = mode
                if subject is not None:
                    existing.subject = subject
                if messages_json is not None:
                    existing.messages_json = messages_json
                existing.updated_at = datetime.now(timezone.utc)
                chat = existing
            session.commit()
            session.refresh(chat)
        return chat

    def get_chat_sessions(
        self,
        user_id: str,
        mode: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询用户的历史会话列表（不含完整消息内容）。"""
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        if mode:
            stmt = stmt.where(ChatSession.mode == mode)

        with self._session_factory() as session:
            sessions = session.scalars(stmt).all()

        return [
            {
                "session_id": s.session_id,
                "mode": s.mode,
                "subject": s.subject,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]

    # ------------------------------------------------------------------
    # DiagnosisReport CRUD
    # ------------------------------------------------------------------

    def save_diagnosis_report(
        self,
        user_id: str,
        subject: Optional[str],
        weak_points: list[dict[str, Any]],
        recommended_questions: list[dict[str, Any]],
        recommended_notes: list[dict[str, Any]],
        report_text: str,
        weak_threshold: Optional[float] = None,
    ) -> DiagnosisReport:
        """持久化一次完整的诊断报告。"""
        self.get_or_create_user(user_id)

        report = DiagnosisReport(
            user_id=user_id,
            subject=subject,
            weak_points_json=json.dumps(weak_points, ensure_ascii=False),
            recommended_questions_json=json.dumps(recommended_questions, ensure_ascii=False),
            recommended_notes_json=json.dumps(recommended_notes, ensure_ascii=False),
            report_text=report_text,
            weak_threshold=weak_threshold,
            created_at=datetime.now(timezone.utc),
        )
        with self._session_factory() as session:
            session.add(report)
            session.commit()
            session.refresh(report)
        return report

    def get_diagnosis_reports(
        self,
        user_id: str,
        subject: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """查询用户的历史诊断报告列表。"""
        stmt = (
            select(DiagnosisReport)
            .where(DiagnosisReport.user_id == user_id)
            .order_by(DiagnosisReport.created_at.desc())
            .limit(limit)
        )
        if subject:
            stmt = stmt.where(DiagnosisReport.subject == subject)

        with self._session_factory() as session:
            reports = session.scalars(stmt).all()

        result = []
        for r in reports:
            result.append(
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "subject": r.subject,
                    "weak_points": json.loads(r.weak_points_json or "[]"),
                    "recommended_questions": json.loads(
                        r.recommended_questions_json or "[]"
                    ),
                    "recommended_notes": json.loads(r.recommended_notes_json or "[]"),
                    "report_text": r.report_text,
                    "weak_threshold": r.weak_threshold,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return result


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_db_manager: Optional[DatabaseManager] = None


def init_db_manager(db_url: str) -> DatabaseManager:
    """初始化全局数据库管理器（应用启动时调用一次）。"""
    global _db_manager
    _db_manager = DatabaseManager(db_url)
    return _db_manager


def get_db_manager() -> DatabaseManager:
    """
    返回全局数据库管理器单例。

    若尚未通过 init_db_manager() 初始化（如测试环境），则按默认路径创建。
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager("sqlite:///userdata.db")
    return _db_manager
