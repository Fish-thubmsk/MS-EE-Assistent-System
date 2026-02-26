"""
FastAPI application entry point.
================================
Exposes a REST API for the AI 考研 辅助系统.

Endpoints
---------
POST /agent/chat          – run the multi-mode agent
GET  /kb/notes            – list user notes
POST /kb/notes            – add a note
DELETE /kb/notes/{id}     – delete a note
GET  /kb/qa-records       – list Q&A history
POST /kb/documents        – add documents to the static KB (admin/offline)
GET  /health              – liveness probe
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from agents import AgentWorkflow
from knowledge_base.static_kb import StaticKnowledgeBase
from knowledge_base.dynamic_kb import DynamicKnowledgeBase
from models.schemas import (
    AgentRequest, AgentResponse,
    Document, NoteCreate, NoteResponse, QARecordResponse,
)


# ---------------------------------------------------------------------------
# Application lifespan – initialise shared singletons once
# ---------------------------------------------------------------------------

_workflow: AgentWorkflow | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _workflow
    _workflow = AgentWorkflow()
    yield
    _workflow = None


app = FastAPI(
    title="AI 考研辅助系统",
    description=(
        "采用动静分离的双知识库架构 + 多模式 Agent 工作流，"
        "为考研学生提供智能问答、学习辅导、练习出题和备考规划服务。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def _get_workflow() -> AgentWorkflow:
    if _workflow is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return _workflow


# ---------------------------------------------------------------------------
# Agent endpoint
# ---------------------------------------------------------------------------

@app.post("/agent/chat", response_model=AgentResponse, tags=["Agent"])
async def chat(request: AgentRequest):
    """
    Run the multi-mode agent.

    Select `mode` to control behaviour:
    - **qa** – 问答模式
    - **study** – 学习模式
    - **practice** – 练习模式
    - **planning** – 规划模式
    """
    wf = _get_workflow()
    return wf.run(request)


# ---------------------------------------------------------------------------
# Notes endpoints
# ---------------------------------------------------------------------------

@app.post("/kb/notes", response_model=NoteResponse, tags=["Dynamic KB"])
async def create_note(note: NoteCreate):
    """Add a study note to the dynamic knowledge base."""
    return _get_workflow().dynamic_kb.add_note(note)


@app.get("/kb/notes", response_model=List[NoteResponse], tags=["Dynamic KB"])
async def list_notes(subject: Optional[str] = Query(default=None)):
    """List study notes, optionally filtered by subject."""
    return _get_workflow().dynamic_kb.get_notes(subject=subject)


@app.delete("/kb/notes/{note_id}", tags=["Dynamic KB"])
async def delete_note(note_id: int):
    """Delete a note by ID."""
    deleted = _get_workflow().dynamic_kb.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": note_id}


# ---------------------------------------------------------------------------
# Q&A history endpoints
# ---------------------------------------------------------------------------

@app.get("/kb/qa-records", response_model=List[QARecordResponse], tags=["Dynamic KB"])
async def list_qa_records(
    subject: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List Q&A interaction history from the dynamic knowledge base."""
    return _get_workflow().dynamic_kb.get_qa_records(subject=subject, limit=limit)


# ---------------------------------------------------------------------------
# Static KB management (offline / admin use)
# ---------------------------------------------------------------------------

class DocumentsPayload(BaseModel):
    documents: List[Document]
    save: bool = False


@app.post("/kb/documents", tags=["Static KB"])
async def add_documents(payload: DocumentsPayload):
    """
    Add documents to the static FAISS knowledge base.

    Set `save=true` to persist the updated index to disk.
    """
    wf = _get_workflow()
    wf.static_kb.add_documents(payload.documents)
    if payload.save:
        wf.static_kb.save()
    return {"added": len(payload.documents), "saved": payload.save}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}
