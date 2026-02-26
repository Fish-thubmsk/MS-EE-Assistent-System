"""
Pydantic schemas shared across the application.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent mode
# ---------------------------------------------------------------------------

class AgentMode(str, Enum):
    """Available agent operation modes."""
    QA = "qa"               # 问答模式 – answer subject questions
    STUDY = "study"         # 学习模式 – explain concepts with guidance
    PRACTICE = "practice"   # 练习模式 – generate & evaluate exercises
    PLANNING = "planning"   # 规划模式 – create personalised study plans


# ---------------------------------------------------------------------------
# Knowledge-base schemas
# ---------------------------------------------------------------------------

class Document(BaseModel):
    """A single knowledge document stored in either knowledge base."""
    id: Optional[str] = None
    content: str
    metadata: dict = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A retrieval result from either knowledge base."""
    document: Document
    score: float


# ---------------------------------------------------------------------------
# Dynamic KB schemas
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    subject: str
    content: str
    tags: List[str] = Field(default_factory=list)


class NoteResponse(NoteCreate):
    id: int
    created_at: str


class QARecordCreate(BaseModel):
    question: str
    answer: str
    mode: AgentMode
    subject: Optional[str] = None


class QARecordResponse(QARecordCreate):
    id: int
    created_at: str


# ---------------------------------------------------------------------------
# Agent request / response
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    mode: AgentMode = AgentMode.QA
    query: str
    subject: Optional[str] = None       # e.g. 数学, 英语, 政治, 专业课
    history: List[dict] = Field(default_factory=list)


class AgentResponse(BaseModel):
    mode: AgentMode
    answer: str
    sources: List[SearchResult] = Field(default_factory=list)
