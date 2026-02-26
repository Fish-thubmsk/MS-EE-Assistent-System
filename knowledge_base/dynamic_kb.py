"""
Dynamic Knowledge Base
======================
SQLite-backed store for *mutable* runtime data:

* User notes / bookmarks
* Q&A interaction history (for personalisation & review)
* Study progress records

Because this data changes frequently it is kept separate from the static
FAISS index so the two concerns never interfere with each other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings
from models.schemas import (
    NoteCreate, NoteResponse,
    QARecordCreate, QARecordResponse,
)


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class NoteModel(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(128), nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(String(512), default="")           # comma-separated
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class QARecordModel(Base):
    __tablename__ = "qa_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    mode = Column(String(32), nullable=False)
    subject = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class DynamicKnowledgeBase:
    """SQLite-backed store for user-generated and session data."""

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or settings.dynamic_kb_db_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def add_note(self, note: NoteCreate) -> NoteResponse:
        with self._Session() as session:
            obj = NoteModel(
                subject=note.subject,
                content=note.content,
                tags=",".join(note.tags),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return self._note_to_schema(obj)

    def get_notes(self, subject: Optional[str] = None) -> List[NoteResponse]:
        with self._Session() as session:
            q = session.query(NoteModel)
            if subject:
                q = q.filter(NoteModel.subject == subject)
            return [self._note_to_schema(n) for n in q.all()]

    def delete_note(self, note_id: int) -> bool:
        with self._Session() as session:
            obj = session.get(NoteModel, note_id)
            if obj is None:
                return False
            session.delete(obj)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Q&A records
    # ------------------------------------------------------------------

    def add_qa_record(self, record: QARecordCreate) -> QARecordResponse:
        with self._Session() as session:
            obj = QARecordModel(
                question=record.question,
                answer=record.answer,
                mode=record.mode.value,
                subject=record.subject,
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return self._qa_to_schema(obj)

    def get_qa_records(self, subject: Optional[str] = None,
                       limit: int = 50) -> List[QARecordResponse]:
        with self._Session() as session:
            q = session.query(QARecordModel).order_by(
                QARecordModel.created_at.desc()
            )
            if subject:
                q = q.filter(QARecordModel.subject == subject)
            return [self._qa_to_schema(r) for r in q.limit(limit).all()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _note_to_schema(obj: NoteModel) -> NoteResponse:
        return NoteResponse(
            id=obj.id,
            subject=obj.subject,
            content=obj.content,
            tags=[t for t in obj.tags.split(",") if t] if obj.tags else [],
            created_at=obj.created_at.isoformat(),
        )

    @staticmethod
    def _qa_to_schema(obj: QARecordModel) -> QARecordResponse:
        from models.schemas import AgentMode
        return QARecordResponse(
            id=obj.id,
            question=obj.question,
            answer=obj.answer,
            mode=AgentMode(obj.mode),
            subject=obj.subject,
            created_at=obj.created_at.isoformat(),
        )
