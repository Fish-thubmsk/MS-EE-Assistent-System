"""
刷题（Practice）API 路由模块

提供以下接口：
    POST /api/practice          提交答案并获取批改结果与解析
    POST /api/practice/stream   SSE 流式返回解析内容
    GET  /api/practice/question 随机获取一道 mock 题目
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.quiz_agent import MOCK_MATH_QUESTIONS, run_quiz
from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/practice", tags=["practice"])

SettingsDep = Annotated[Settings, Depends(get_settings)]

# Delay between streamed characters to simulate a typing effect (seconds)
_STREAM_CHAR_DELAY = 0.01


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class QuestionOut(BaseModel):
    id: int = Field(..., description="题目 ID")
    subject: str = Field(..., description="学科")
    year: Optional[int] = Field(None, description="年份")
    question_type: Optional[str] = Field(None, description="题型")
    content: str = Field(..., description="题目内容")
    knowledge_points: list[str] = Field(default_factory=list, description="涉及知识点")


class GradeResultOut(BaseModel):
    is_correct: Optional[bool] = Field(None, description="是否答对（None 表示需人工判断）")
    score: Optional[int] = Field(None, description="得分 0–100")
    feedback: str = Field(..., description="批改意见")


class PracticeRequest(BaseModel):
    user_input: str = Field(..., description="用户答案或输入文本")
    current_question: Optional[dict[str, Any]] = Field(
        None,
        description="当前题目（含 content、correct_answer、analysis、knowledge_points 等字段）",
    )
    user_answer: Optional[str] = Field(
        None, description="明确指定的用户答案（不传则取 user_input）"
    )
    messages: list[dict[str, str]] = Field(
        default_factory=list, description="历史对话消息"
    )
    quiz_history: list[dict[str, Any]] = Field(
        default_factory=list, description="历史刷题记录"
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="路由参数（subject / difficulty 等）"
    )


class PracticeResponse(BaseModel):
    grade_result: GradeResultOut = Field(..., description="判题批改结果")
    explanation: str = Field(..., description="详细解析")
    followup_questions: list[str] = Field(default_factory=list, description="追问建议")
    messages: list[dict[str, str]] = Field(..., description="更新后的消息列表")
    quiz_history: list[dict[str, Any]] = Field(..., description="更新后的刷题历史")


# ---------------------------------------------------------------------------
# 内部工具：SSE
# ---------------------------------------------------------------------------


async def _stream_explanation(explanation: str) -> AsyncGenerator[str, None]:
    """逐字符流式发送解析内容（模拟打字机效果）。"""
    for char in explanation:
        yield f"event: token\ndata: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(_STREAM_CHAR_DELAY)
    yield f"event: done\ndata: {json.dumps({'status': 'done'}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.get("/question", response_model=QuestionOut, summary="随机获取 mock 题目")
async def get_mock_question() -> QuestionOut:
    """
    随机返回一道内置 mock 数学题，供前端演示使用。
    """
    import random

    q = random.choice(MOCK_MATH_QUESTIONS)
    return QuestionOut(
        id=q["id"],
        subject=q["subject"],
        year=q.get("year"),
        question_type=q.get("question_type"),
        content=q["content"],
        knowledge_points=q.get("knowledge_points", []),
    )


@router.post("", response_model=PracticeResponse, summary="提交答案并批改")
async def practice(req: PracticeRequest, settings: SettingsDep) -> PracticeResponse:
    """
    提交用户答案，运行 Quiz Agent 批改并返回解析与追问建议。

    - **current_question** 为空时，自动选取一道 mock 数学题作为当前题目演示。
    - 若 **SILICONFLOW_API_KEY** 已配置，将使用 LLM 进行智能批改和解析。
    """
    question = req.current_question
    if not question:
        # 默认使用第一道 mock 题演示
        question = MOCK_MATH_QUESTIONS[0]

    try:
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_quiz(
                req.user_input,
                current_question=question,
                user_answer=req.user_answer or req.user_input,
                messages=req.messages or None,
                quiz_history=req.quiz_history or None,
                params=req.params or None,
            ),
        )
    except Exception as exc:
        logger.exception("Quiz agent failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"刷题处理失败：{exc}") from exc

    grade = state.get("grade_result") or {}
    return PracticeResponse(
        grade_result=GradeResultOut(
            is_correct=grade.get("is_correct"),
            score=grade.get("score"),
            feedback=grade.get("feedback", ""),
        ),
        explanation=state.get("explanation") or "",
        followup_questions=state.get("followup_questions") or [],
        messages=state["messages"],
        quiz_history=state.get("quiz_history") or [],
    )


@router.post("/stream", summary="SSE 流式返回解析内容")
async def practice_stream(req: PracticeRequest, settings: SettingsDep) -> StreamingResponse:
    """
    先同步运行 Quiz Agent 批改，然后以 SSE 流式返回解析文字。

    **事件类型：**
    - `event: meta`  — 首帧，携带批改结果摘要 `{"grade_result": {...}, "followup_questions": [...]}`
    - `event: token` — 解析文字逐字符，`{"token": "..."}`
    - `event: done`  — 流式结束，`{"status": "done"}`
    """
    question = req.current_question or MOCK_MATH_QUESTIONS[0]

    try:
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_quiz(
                req.user_input,
                current_question=question,
                user_answer=req.user_answer or req.user_input,
                messages=req.messages or None,
                quiz_history=req.quiz_history or None,
                params=req.params or None,
            ),
        )
    except Exception as exc:
        logger.exception("Quiz agent stream failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"刷题处理失败：{exc}") from exc

    grade = state.get("grade_result") or {}
    explanation = state.get("explanation") or ""
    followups = state.get("followup_questions") or []

    async def _generate() -> AsyncGenerator[str, None]:
        # 首帧：批改元数据
        meta = {
            "grade_result": {
                "is_correct": grade.get("is_correct"),
                "score": grade.get("score"),
                "feedback": grade.get("feedback", ""),
            },
            "followup_questions": followups,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

        # 流式解析内容
        async for chunk in _stream_explanation(explanation):
            yield chunk

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
