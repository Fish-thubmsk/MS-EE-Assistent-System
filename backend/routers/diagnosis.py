"""
诊断模式 API 路由

提供以下接口：
    POST /diagnosis/run   运行学习诊断，返回薄弱点分析与推荐报告
    GET  /diagnosis/mock  使用内置 mock 数据快速体验诊断流程
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.diagnosis_agent import (
    WEAK_THRESHOLD,
    RECOMMEND_PER_POINT,
    WeakPoint,
    RecommendedQuestion,
    RecommendedNote,
    run_diagnosis,
)
from backend.database.db_manager import get_db_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class HistoryRecord(BaseModel):
    question_id: int = Field(..., description="题目 ID")
    subject: str = Field(..., description="学科")
    knowledge_point: str = Field(..., description="知识点")
    is_correct: bool = Field(..., description="是否答对")
    difficulty: Optional[str] = Field(None, description="难度")
    answered_at: Optional[str] = Field(None, description="作答时间")


class DiagnosisRequest(BaseModel):
    user_id: str = Field(default="user_001", description="用户 ID")
    subject: Optional[str] = Field(None, description="可选：限定分析学科（如 数学/政治/英语）")
    history_records: list[HistoryRecord] = Field(
        default_factory=list,
        description="做题历史记录（不传则自动读取内置 mock 数据）",
    )
    weak_threshold: float = Field(
        default=WEAK_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=f"薄弱点准确率阈值，低于此值视为薄弱（默认 {WEAK_THRESHOLD}）",
    )
    recommend_per_point: int = Field(
        default=RECOMMEND_PER_POINT,
        ge=1,
        le=10,
        description=f"每个薄弱点推荐题目数（默认 {RECOMMEND_PER_POINT}）",
    )


class WeakPointOut(BaseModel):
    knowledge_point: str
    subject: str
    accuracy: float
    total_attempts: int
    priority: str


class RecommendedQuestionOut(BaseModel):
    id: int
    subject: str
    knowledge_point: str
    content: str
    difficulty_level: Optional[str]
    correct_answer: Optional[str]


class RecommendedNoteOut(BaseModel):
    doc_id: str
    subject: str
    content_snippet: str
    note_type: str


class DiagnosisResponse(BaseModel):
    user_id: str
    subject: Optional[str]
    weak_points: list[WeakPointOut] = Field(..., description="薄弱知识点列表（按准确率升序）")
    recommended_questions: list[RecommendedQuestionOut] = Field(
        ..., description="推荐练习题"
    )
    recommended_notes: list[RecommendedNoteOut] = Field(
        ..., description="推荐参考笔记/错题"
    )
    report: str = Field(..., description="完整学习诊断报告文本")


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.post("/run", response_model=DiagnosisResponse, summary="运行学习诊断")
def run_diagnosis_api(req: DiagnosisRequest) -> DiagnosisResponse:
    """
    分析用户做题历史，识别薄弱知识点，生成个性化推荐与诊断报告。

    - 若 **history_records** 为空，优先从 userdata.db 读取该用户的真实做题记录；DB 无数据时自动使用内置 mock 数据演示。
    - 可通过 **subject** 限定分析范围（如只分析"数学"）。
    - **weak_threshold** 控制薄弱点判定准确率阈值（默认 0.6）。
    - 诊断完成后结果自动持久化到 userdata.db，可通过 GET /api/users/{user_id}/diagnosis 查询历史报告。
    """
    # 若请求中已携带 history_records，直接使用；否则从 userdata.db 读取
    if req.history_records:
        records: Optional[list[dict]] = [r.model_dump() for r in req.history_records]
    else:
        db_records = get_db_manager().get_quiz_records(
            req.user_id, subject=req.subject, limit=500
        )
        records = db_records if db_records else None

    state = run_diagnosis(
        user_id=req.user_id,
        subject=req.subject,
        history_records=records,
        weak_threshold=req.weak_threshold,
        recommend_per_point=req.recommend_per_point,
    )

    # 持久化诊断报告
    try:
        get_db_manager().save_diagnosis_report(
            user_id=state["user_id"],
            subject=state.get("subject"),
            weak_points=state["weak_points"],
            recommended_questions=state["recommended_questions"],
            recommended_notes=state["recommended_notes"],
            report_text=state["report"],
            weak_threshold=req.weak_threshold,
        )
    except Exception as exc:
        logger.warning("Failed to persist diagnosis report: %s", exc)

    return DiagnosisResponse(
        user_id=state["user_id"],
        subject=state.get("subject"),
        weak_points=[WeakPointOut(**wp) for wp in state["weak_points"]],
        recommended_questions=[
            RecommendedQuestionOut(**q) for q in state["recommended_questions"]
        ],
        recommended_notes=[
            RecommendedNoteOut(**n) for n in state["recommended_notes"]
        ],
        report=state["report"],
    )


@router.get("/mock", response_model=DiagnosisResponse, summary="使用 mock 数据体验诊断（仅供演示）")
def mock_diagnosis() -> DiagnosisResponse:
    """
    使用内置 mock 用户数据（user_001）快速体验学习诊断流程，无需传入任何参数。

    **注意**：本接口仅用于演示，使用内置 mock 数据而非真实用户做题记录。
    """
    state = run_diagnosis(user_id="user_001")

    return DiagnosisResponse(
        user_id=state["user_id"],
        subject=state.get("subject"),
        weak_points=[WeakPointOut(**wp) for wp in state["weak_points"]],
        recommended_questions=[
            RecommendedQuestionOut(**q) for q in state["recommended_questions"]
        ],
        recommended_notes=[
            RecommendedNoteOut(**n) for n in state["recommended_notes"]
        ],
        report=state["report"],
    )
