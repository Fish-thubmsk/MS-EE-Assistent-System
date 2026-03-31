"""
用户数据 SQLAlchemy ORM 模型

本模块定义所有用户相关的数据库表，存储于独立的 userdata.db 文件中，
与只读的知识库 knowledge_base.db 相互分离。

表设计概览：
    users               — 用户档案（user_id 为业务主键）
    quiz_records        — 做题历史（每次答题记录）
    chat_sessions       — 会话历史（问答/刷题/诊断各模式）
    diagnosis_reports   — 诊断报告（每次诊断的完整结果快照）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""


# ---------------------------------------------------------------------------
# users 表
# ---------------------------------------------------------------------------


class User(Base):
    """用户档案表。

    每位用户在首次使用系统时自动创建（或由前端显式注册）。
    user_id 是业务层唯一标识（如 "user_001"、"alice" 等），与数据库自增主键分离。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User user_id={self.user_id!r}>"


# ---------------------------------------------------------------------------
# quiz_records 表
# ---------------------------------------------------------------------------


class QuizRecord(Base):
    """做题历史记录表。

    每次用户通过 POST /api/practice 提交答案后，均在此表插入一条记录。
    保留了原始 sqlite3 建表中的字段，并补充了 difficulty 和 time_spent_seconds 字段。

    字段说明：
        user_id         — 用户业务 ID（与 users.user_id 逻辑关联，但不设 FK 以保持轻量）
        question_id     — 对应 knowledge_base.db 中 questions 表的主键
        subject         — 学科（数学/政治/英语）
        knowledge_point — 答题涉及的主要知识点
        is_correct      — 是否答对（None 表示主观题需人工判断）
        difficulty      — 题目难度（简单/中等/困难）
        time_spent_seconds — 作答耗时（可选，前端传入）
        answered_at     — 作答时间
    """

    __tablename__ = "quiz_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    knowledge_point: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<QuizRecord user={self.user_id!r} q={self.question_id}"
            f" correct={self.is_correct}>"
        )


# ---------------------------------------------------------------------------
# chat_sessions 表
# ---------------------------------------------------------------------------


class ChatSession(Base):
    """会话历史表。

    记录每个对话会话的元数据（不存储完整对话消息流水；消息列表由前端/客户端维护，
    服务端可按需序列化后写入 messages_json 字段）。

    字段说明：
        session_id      — 前端生成的唯一会话 ID（如 UUID）
        user_id         — 所属用户
        mode            — 会话模式：qa（问答）/ quiz（刷题）/ diagnosis（诊断）
        subject         — 可选的学科范围（如 "数学"）
        messages_json   — 完整消息列表的 JSON 序列化（可选，用于历史回溯）
        created_at      — 会话创建时间
        updated_at      — 最近一次更新时间（新消息进入时更新）
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="qa")
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatSession session={self.session_id!r} user={self.user_id!r} mode={self.mode!r}>"


# ---------------------------------------------------------------------------
# diagnosis_reports 表
# ---------------------------------------------------------------------------


class DiagnosisReport(Base):
    """学习诊断报告持久化表。

    每次用户调用 POST /diagnosis/run 完成诊断后，将完整结果快照写入此表，
    方便后续通过 GET /api/users/{user_id}/diagnosis 检索历史报告。

    字段说明：
        user_id                   — 所属用户
        subject                   — 本次诊断的学科范围（None 表示全科）
        weak_points_json          — 薄弱知识点列表（JSON 序列化的 list[WeakPoint]）
        recommended_questions_json — 推荐题目列表（JSON 序列化的 list[RecommendedQuestion]）
        recommended_notes_json    — 推荐笔记列表（JSON 序列化的 list[RecommendedNote]）
        report_text               — 完整诊断报告文本
        weak_threshold            — 本次使用的薄弱点阈值
        created_at                — 报告生成时间
    """

    __tablename__ = "diagnosis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weak_points_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_questions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    weak_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DiagnosisReport user={self.user_id!r} subject={self.subject!r}>"
