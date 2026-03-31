"""
刷题（Practice）API 路由模块

提供以下接口：
    POST /api/practice          提交答案并获取批改结果与解析
    POST /api/practice/stream   SSE 流式返回解析内容
    GET  /api/practice/question 从数据库随机获取题目（支持学科筛选）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.quiz_agent import MOCK_MATH_QUESTIONS, run_quiz
from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/practice", tags=["practice"])

# ---------------------------------------------------------------------------
# 数据库路径（与 diagnosis_agent 保持一致，支持环境变量覆盖）
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", os.getcwd()))
_DB_PATH = Path(
    os.path.abspath(
        os.environ.get(
            "KNOWLEDGE_DB_PATH",
            str(_REPO_ROOT / "datebase" / "knowledge_base.db"),
        )
    )
)

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
    options: Optional[dict[str, str]] = Field(None, description="选项 {A:..., B:..., C:..., D:...}")
    correct_answer: Optional[str] = Field(None, description="正确答案")
    analysis: Optional[str] = Field(None, description="解析")
    passage_text: Optional[str] = Field(None, description="英语阅读文章原文")
    knowledge_points: list[str] = Field(default_factory=list, description="涉及知识点")


class GradeResultOut(BaseModel):
    is_correct: Optional[bool] = Field(None, description="是否答对（None 表示需人工判断）")
    score: Optional[int] = Field(None, description="得分 0–100")
    feedback: str = Field(..., description="批改意见")


class PracticeRequest(BaseModel):
    user_id: str = Field(default="guest", description="用户 ID")
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
# 内部工具：quiz_records 持久化
# ---------------------------------------------------------------------------

_quiz_records_table_ensured: bool = False


def _ensure_quiz_records_table() -> None:
    """确保 quiz_records 表存在于题库数据库中（每个进程生命周期内只建一次）。"""
    global _quiz_records_table_ensured
    if _quiz_records_table_ensured or not _DB_PATH.exists():
        return
    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    question_id INTEGER,
                    subject TEXT,
                    knowledge_point TEXT,
                    is_correct INTEGER,
                    answered_at TEXT
                )
                """
            )
            conn.commit()
        _quiz_records_table_ensured = True
    except sqlite3.Error as exc:
        logger.warning("Failed to ensure quiz_records table: %s", exc)


def _save_quiz_record(
    user_id: str,
    question: dict[str, Any],
    is_correct: Optional[bool],
) -> None:
    """将一条做题结果保存到 quiz_records 表。"""
    if not _DB_PATH.exists():
        return
    try:
        _ensure_quiz_records_table()
        kps: list[str] = question.get("knowledge_points") or []
        knowledge_point = kps[0] if kps else question.get("knowledge_point", "")
        # is_correct 为 None 时以 NULL 存储，区别于明确答错（0）
        is_correct_val: Optional[int] = None if is_correct is None else (1 if is_correct else 0)
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO quiz_records"
                "(user_id, question_id, subject, knowledge_point, is_correct, answered_at)"
                " VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    user_id,
                    question.get("id"),
                    question.get("subject", ""),
                    knowledge_point,
                    is_correct_val,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("Failed to save quiz record: %s", exc)


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


@router.get("/question", response_model=QuestionOut, summary="随机获取题目（支持学科筛选）")
async def get_practice_question(
    subject: Optional[str] = Query(None, description="学科筛选（数学/政治/英语），不传则全库随机"),
    question_type: Optional[str] = Query(None, description="题型筛选，不传则不限"),
) -> QuestionOut:
    """
    从知识库数据库随机抽取一道题目。支持按学科和题型筛选。
    若数据库不可用或无匹配题目，降级返回内置 mock 题目。
    """
    import random

    row = _fetch_random_question_from_db(subject=subject, question_type=question_type)
    if row:
        return row

    # 降级：从 mock 数据中随机选取（可按学科筛选）
    pool = MOCK_MATH_QUESTIONS
    if subject:
        pool = [q for q in MOCK_MATH_QUESTIONS if q.get("subject") == subject]
    if not pool:
        pool = MOCK_MATH_QUESTIONS
    q = random.choice(pool)
    return QuestionOut(
        id=q["id"],
        subject=q["subject"],
        year=q.get("year"),
        question_type=q.get("question_type"),
        content=q["content"],
        options=q.get("options"),
        correct_answer=q.get("correct_answer"),
        analysis=q.get("analysis"),
        passage_text=None,
        knowledge_points=q.get("knowledge_points", []),
    )


def _fetch_random_question_from_db(
    subject: Optional[str] = None,
    question_type: Optional[str] = None,
) -> Optional[QuestionOut]:
    """从 SQLite 数据库随机抽取一道激活的题目，失败时返回 None。"""
    if not _DB_PATH.exists():
        return None

    conditions = ["q.is_active = 1"]
    params: list[Any] = []
    if subject:
        conditions.append("q.subject = ?")
        params.append(subject)
    if question_type:
        conditions.append("q.question_type = ?")
        params.append(question_type)

    # `conditions` contains only hardcoded literal SQL fragments; user values are
    # always bound via parameterised placeholders (`params`) to prevent SQL injection.
    where_clause = " AND ".join(conditions)
    sql = (
        "SELECT q.id, q.subject, q.year, q.question_type, q.content, "
        "q.options, q.correct_answer, q.analysis, q.knowledge_structure, "
        "q.passage_id, p.passage_text "
        "FROM questions q "
        "LEFT JOIN passages p ON p.id = q.passage_id "
        f"WHERE {where_clause} ORDER BY RANDOM() LIMIT 1"
    )

    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
    except sqlite3.Error as exc:
        logger.warning("DB query failed, falling back to mock questions: %s", exc)
        return None

    if not row:
        return None

    (
        db_id, db_subject, db_year, db_question_type, db_content,
        db_options_raw, db_correct_answer, db_analysis,
        db_ks, db_passage_id, db_passage_text,
    ) = row

    knowledge_points: list[str] = []
    if db_ks:
        try:
            ks = json.loads(db_ks)
            if isinstance(ks, dict):
                if ks.get("primary"):
                    knowledge_points.append(ks["primary"])
                knowledge_points.extend(ks.get("secondary") or [])
        except (json.JSONDecodeError, TypeError):
            pass

    options: Optional[dict[str, str]] = None
    if db_options_raw:
        try:
            parsed = json.loads(db_options_raw)
            if isinstance(parsed, dict) and parsed:
                options = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            pass

    return QuestionOut(
        id=db_id,
        subject=db_subject,
        year=db_year,
        question_type=db_question_type,
        content=db_content,
        options=options,
        correct_answer=db_correct_answer or None,
        analysis=db_analysis or None,
        passage_text=db_passage_text or None,
        knowledge_points=knowledge_points,
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
    _save_quiz_record(req.user_id, question, grade.get("is_correct"))
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
