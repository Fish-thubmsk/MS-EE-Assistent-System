"""
SQLAlchemy ORM 模型定义

定义 userdata.db 中的三张核心用户数据表：
  - User             用户账号（users）
  - QuizRecord       答题记录（quiz_records）
  - DiagnosisReport  诊断报告（diagnosis_reports）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""


class User(Base):
    """用户账号表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    quiz_records: Mapped[list[QuizRecord]] = relationship(
        "QuizRecord", back_populates="user", cascade="all, delete-orphan"
    )
    diagnosis_reports: Mapped[list[DiagnosisReport]] = relationship(
        "DiagnosisReport", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class QuizRecord(Base):
    """答题记录表。"""

    __tablename__ = "quiz_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 允许存储匿名用户（字符串形式），与旧代码兼容
    user_id_str: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    knowledge_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped[User | None] = relationship("User", back_populates="quiz_records")

    def __repr__(self) -> str:
        return (
            f"<QuizRecord id={self.id} user_id_str={self.user_id_str!r}"
            f" question_id={self.question_id} subject={self.subject!r}"
            f" is_correct={self.is_correct}>"
        )


class DiagnosisReport(Base):
    """诊断报告表。"""

    __tablename__ = "diagnosis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 允许存储匿名用户（字符串形式）
    user_id_str: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # JSON 格式存储完整分析结果
    analysis_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped[User | None] = relationship("User", back_populates="diagnosis_reports")

    def __repr__(self) -> str:
        return (
            f"<DiagnosisReport id={self.id} user_id_str={self.user_id_str!r}"
            f" report_date={self.report_date}>"
        )
