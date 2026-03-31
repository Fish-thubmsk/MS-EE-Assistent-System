"""
用户数据 API 路由

提供以下接口：
    GET  /api/users/{user_id}               获取用户基本信息（不存在则自动创建）
    GET  /api/users/{user_id}/history       查询做题历史记录
    GET  /api/users/{user_id}/stats         查询做题统计摘要
    GET  /api/users/{user_id}/sessions      查询历史会话列表
    GET  /api/users/{user_id}/diagnosis     查询历史诊断报告
    POST /api/users/{user_id}/sessions      创建或更新一条会话记录
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database.db_manager import get_db_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    user_id: str
    display_name: Optional[str]
    created_at: Optional[str]


class QuizRecordOut(BaseModel):
    question_id: Optional[int]
    subject: Optional[str]
    knowledge_point: Optional[str]
    is_correct: Optional[bool]
    difficulty: Optional[str]
    answered_at: Optional[str]


class QuizStatsOut(BaseModel):
    total: int = Field(..., description="总答题数")
    correct: int = Field(..., description="答对数")
    by_subject: dict[str, dict[str, int]] = Field(..., description="按学科统计（total / correct）")


class SessionOut(BaseModel):
    session_id: str
    mode: str
    subject: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class DiagnosisReportOut(BaseModel):
    id: int
    user_id: str
    subject: Optional[str]
    weak_points: list[dict[str, Any]]
    recommended_questions: list[dict[str, Any]]
    recommended_notes: list[dict[str, Any]]
    report_text: Optional[str]
    weak_threshold: Optional[float]
    created_at: Optional[str]


class UpsertSessionRequest(BaseModel):
    session_id: str = Field(..., description="前端生成的唯一会话 ID（如 UUID）")
    mode: str = Field(default="qa", description="会话模式：qa / quiz / diagnosis")
    subject: Optional[str] = Field(None, description="学科范围（可选）")
    messages: Optional[list[dict[str, str]]] = Field(None, description="消息列表（可选存档）")


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=UserOut, summary="获取用户信息（不存在则自动创建）")
def get_user(user_id: str) -> UserOut:
    """
    查询用户档案。若该 user_id 尚未注册，则自动创建并返回新用户。
    """
    user = get_db_manager().get_or_create_user(user_id)
    return UserOut(
        user_id=user.user_id,
        display_name=user.display_name,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.get("/{user_id}/history", response_model=list[QuizRecordOut], summary="查询做题历史")
def get_quiz_history(
    user_id: str,
    subject: Optional[str] = Query(None, description="按学科过滤（数学/政治/英语）"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
) -> list[QuizRecordOut]:
    """
    返回指定用户的做题历史记录（按答题时间倒序）。

    - 通过 **subject** 参数可过滤特定学科的记录。
    - 通过 **limit** 控制返回数量（最多 500 条）。
    """
    records = get_db_manager().get_quiz_records(user_id, subject=subject, limit=limit)
    return [QuizRecordOut(**r) for r in records]


@router.get("/{user_id}/stats", response_model=QuizStatsOut, summary="查询做题统计摘要")
def get_quiz_stats(user_id: str) -> QuizStatsOut:
    """
    返回用户整体做题统计，包含：总答题数、答对数及各学科分项统计。
    """
    stats = get_db_manager().get_quiz_stats(user_id)
    return QuizStatsOut(**stats)


@router.get("/{user_id}/sessions", response_model=list[SessionOut], summary="查询历史会话列表")
def get_sessions(
    user_id: str,
    mode: Optional[str] = Query(None, description="按模式过滤（qa / quiz / diagnosis）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
) -> list[SessionOut]:
    """
    返回用户的历史会话列表（按最近更新时间倒序，不含完整消息内容）。
    """
    sessions = get_db_manager().get_chat_sessions(user_id, mode=mode, limit=limit)
    return [SessionOut(**s) for s in sessions]


@router.post("/{user_id}/sessions", response_model=SessionOut, summary="创建或更新会话记录")
def upsert_session(user_id: str, req: UpsertSessionRequest) -> SessionOut:
    """
    创建新会话或更新已有会话的消息内容。

    前端应在每次新建对话时生成唯一 session_id（如 UUID），并在会话结束后
    调用本接口将消息存档，以便后续历史回溯。
    """
    session = get_db_manager().upsert_chat_session(
        session_id=req.session_id,
        user_id=user_id,
        mode=req.mode,
        subject=req.subject,
        messages=req.messages,
    )
    return SessionOut(
        session_id=session.session_id,
        mode=session.mode,
        subject=session.subject,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
    )


@router.get(
    "/{user_id}/diagnosis",
    response_model=list[DiagnosisReportOut],
    summary="查询历史诊断报告",
)
def get_diagnosis_reports(
    user_id: str,
    subject: Optional[str] = Query(None, description="按学科过滤"),
    limit: int = Query(10, ge=1, le=50, description="返回条数上限"),
) -> list[DiagnosisReportOut]:
    """
    返回用户的历史学习诊断报告（按创建时间倒序）。

    每次调用 POST /diagnosis/run 完成的诊断均会自动持久化，可通过本接口查询历史记录。
    """
    reports = get_db_manager().get_diagnosis_reports(user_id, subject=subject, limit=limit)
    return [DiagnosisReportOut(**r) for r in reports]
