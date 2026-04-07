"""
刷题（Practice）API 路由模块

提供以下接口：
    GET  /api/practice/subjects          返回科目列表
    GET  /api/practice/types/{subject}   返回该科目的题型列表
    GET  /api/practice/years/{subject}   返回该科目有数据的年份列表
    GET  /api/practice/question          随机获取题目（支持科目+题型+年份筛选）
    POST /api/practice                   提交答案并获取批改结果与解析
    POST /api/practice/stream            SSE 流式返回解析内容
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
from backend.database.db_manager import get_userdata_db_path, init_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/practice", tags=["practice"])


def _build_llm(settings: Settings) -> Any:
    """配置了 SiliconFlow API Key 时，构建 LangChain ChatOpenAI 实例。

    不传 API Key 时返回 None，让 Quiz Agent 降级为规则批改。
    """
    if not settings.siliconflow_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI  # pylint: disable=import-outside-toplevel

        return ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.siliconflow_api_key,
            openai_api_base=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to build LLM for quiz grading: %s", exc)
        return None

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
# 科目 / 题型配置（与 reference quiz_app.py 对齐）
# ---------------------------------------------------------------------------

_SUBJECTS = [
    {"id": "politics", "name": "政治",  "icon": "🏛️"},
    {"id": "math",     "name": "数学",  "icon": "📐"},
    {"id": "english",  "name": "英语",  "icon": "📚"},
]

_TYPES: dict[str, list[dict[str, str]]] = {
    "politics": [
        {"id": "单选题",   "name": "单选题"},
        {"id": "多选题",   "name": "多选题"},
        {"id": "材料分析题", "name": "材料分析题"},
    ],
    "math": [
        {"id": "single_choice", "name": "单选题"},
        {"id": "fill_blank",    "name": "填空题"},
        {"id": "subjective",    "name": "解答题"},
    ],
    "english": [
        {"id": "cloze",         "name": "完形填空"},
        {"id": "reading",       "name": "阅读理解"},
        {"id": "new_type",      "name": "新题型"},
        {"id": "translation",   "name": "翻译"},
        {"id": "writing_small", "name": "小作文"},
        {"id": "writing_large", "name": "大作文"},
    ],
}

# Maps English frontend type id → question_number range in questions_english
_ENGLISH_Q_NUMBER: dict[str, tuple[int, int]] = {
    "cloze":         (1, 1),
    "reading":       (2, 5),
    "new_type":      (6, 6),
    "translation":   (7, 7),
    "writing_small": (8, 8),
    "writing_large": (9, 9),
}


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class QuestionOut(BaseModel):
    id: int = Field(..., description="题目 ID")
    subject: str = Field(..., description="学科")
    year: Optional[int] = Field(None, description="年份")
    question_type: Optional[str] = Field(None, description="题型")
    content: str = Field(..., description="题目内容（或小题标签）")
    options: Optional[dict[str, str]] = Field(None, description="选项 {A:..., B:..., C:..., D:...}")
    correct_answer: Optional[str] = Field(None, description="正确答案")
    analysis: Optional[str] = Field(None, description="解析")
    passage_text: Optional[str] = Field(None, description="英语阅读文章原文")
    knowledge_points: list[str] = Field(default_factory=list, description="涉及知识点（预留）")
    sub_questions: list[dict[str, Any]] = Field(
        default_factory=list, description="子问题列表（材料分析题）"
    )


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
# 内部工具：quiz_records 持久化（写入 userdata.db）
# ---------------------------------------------------------------------------

# userdata.db 路径（由 db_manager 统一管理，支持环境变量覆盖）
_USERDATA_DB_PATH: Optional[Path] = None


def _get_userdata_db_path() -> Path:
    """获取 userdata.db 路径，并在首次调用时初始化数据库表。"""
    global _USERDATA_DB_PATH
    if _USERDATA_DB_PATH is None:
        try:
            init_db()
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to initialize userdata.db: %s", exc)
        _USERDATA_DB_PATH = Path(get_userdata_db_path())
    return _USERDATA_DB_PATH


def _save_quiz_record(
    user_id: str,
    question: dict[str, Any],
    is_correct: Optional[bool],
    user_answer: Optional[str] = None,
    score: Optional[float] = None,
    feedback: Optional[str] = None,
) -> None:
    """将一条做题结果保存到 userdata.db 的 quiz_records 表。"""
    db_path = _get_userdata_db_path()
    if not db_path.exists():
        # 尝试再次初始化
        try:
            init_db()
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to initialize userdata.db on save: %s", exc)
            return
    try:
        kps: list[str] = question.get("knowledge_points") or []
        knowledge_point = kps[0] if kps else question.get("knowledge_point", "")
        is_correct_val: Optional[int] = None if is_correct is None else (1 if is_correct else 0)
        year_val: Optional[int] = question.get("year")
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "INSERT INTO quiz_records"
                " (user_id_str, question_id, subject, year, knowledge_point,"
                "  is_correct, score, user_answer, feedback, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    user_id,
                    question.get("id"),
                    question.get("subject", ""),
                    year_val,
                    knowledge_point,
                    is_correct_val,
                    score,
                    user_answer,
                    feedback,
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
# 内部工具：按新 schema 查询题目
# ---------------------------------------------------------------------------

def _db_connect() -> Optional[sqlite3.Connection]:
    if not _DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_politics_question(
    question_type: Optional[str],
    year: Optional[int],
) -> Optional[QuestionOut]:
    """随机抽一道政治题（单选/多选/材料分析）。"""
    conn = _db_connect()
    if conn is None:
        return None
    try:
        conditions = ["qp.question_type = ?"]
        params: list[Any] = [question_type or "单选题"]
        if year:
            conditions.append("qp.year = ?")
            params.append(year)

        where = " AND ".join(conditions)

        if question_type == "材料分析题":
            # For analysis questions return material + first sub-question
            sql = f"""
                SELECT qp.id, qp.year, qp.stem, qp.question_type,
                       qp.correct_answer, qp.analysis
                FROM questions_politics qp
                WHERE {where}
                ORDER BY RANDOM() LIMIT 1
            """
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            # Fetch sub-questions
            sq_cur = conn.execute(
                "SELECT sub_question_number, stem, answer FROM sub_questions "
                "WHERE subject_type='politics' AND question_id=? ORDER BY sub_question_number",
                (row["id"],),
            )
            sub_qs = sq_cur.fetchall()
            sub_list = [
                {"number": sq["sub_question_number"], "stem": sq["stem"], "answer": sq["answer"]}
                for sq in sub_qs
            ]
            return QuestionOut(
                id=row["id"],
                subject="政治",
                year=row["year"],
                question_type=row["question_type"],
                content=row["stem"],
                options=None,
                correct_answer=None,
                analysis=None,
                passage_text=None,
                sub_questions=sub_list,
            )
        else:
            # single/multiple choice: join sub_questions + options
            sql = f"""
                SELECT qp.id, qp.year, qp.stem, qp.question_type,
                       qp.correct_answer, qp.analysis,
                       MAX(CASE WHEN o.option_key='A' THEN o.option_text END) AS optA,
                       MAX(CASE WHEN o.option_key='B' THEN o.option_text END) AS optB,
                       MAX(CASE WHEN o.option_key='C' THEN o.option_text END) AS optC,
                       MAX(CASE WHEN o.option_key='D' THEN o.option_text END) AS optD
                FROM questions_politics qp
                JOIN sub_questions sq ON sq.question_id=qp.id AND sq.subject_type='politics'
                LEFT JOIN options o ON o.sub_question_id=sq.id AND o.subject_type='politics'
                WHERE {where}
                GROUP BY qp.id
                ORDER BY RANDOM() LIMIT 1
            """
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            opts: dict[str, str] = {}
            for k, col in [("A", "optA"), ("B", "optB"), ("C", "optC"), ("D", "optD")]:
                if row[col]:
                    opts[k] = row[col]
            return QuestionOut(
                id=row["id"],
                subject="政治",
                year=row["year"],
                question_type=row["question_type"],
                content=row["stem"],
                options=opts or None,
                correct_answer=row["correct_answer"],
                analysis=row["analysis"] or None,
                passage_text=None,
            )
    except sqlite3.Error as exc:
        logger.warning("Politics DB query failed: %s", exc)
        return None
    finally:
        conn.close()


def _fetch_math_question(
    question_type: Optional[str],
    year: Optional[int],
) -> Optional[QuestionOut]:
    """随机抽一道数学题。"""
    conn = _db_connect()
    if conn is None:
        return None
    try:
        # Map frontend type to DB question_type
        db_type = question_type or "single_choice"

        conditions = ["qm.question_type = ?"]
        params: list[Any] = [db_type]

        year_join = ""
        if year:
            # paper_title starts with year for most papers
            conditions.append("CAST(SUBSTR(p.paper_title,1,4) AS INTEGER) = ?")
            params.append(year)
            year_join = "LEFT JOIN papers p ON p.id=qm.paper_id"
        else:
            year_join = "LEFT JOIN papers p ON p.id=qm.paper_id"

        where = " AND ".join(conditions)

        sql = f"""
            SELECT qm.id, qm.question_type, qm.stem,
                   s.subject_name AS math_type,
                   CAST(SUBSTR(p.paper_title,1,4) AS INTEGER) AS year,
                   MAX(CASE WHEN o.option_key='A' THEN o.option_text END) AS optA,
                   MAX(CASE WHEN o.option_key='B' THEN o.option_text END) AS optB,
                   MAX(CASE WHEN o.option_key='C' THEN o.option_text END) AS optC,
                   MAX(CASE WHEN o.option_key='D' THEN o.option_text END) AS optD,
                   sq.answer
            FROM questions_math qm
            {year_join}
            LEFT JOIN subjects s ON s.subject_code=p.subject_code
            LEFT JOIN sub_questions sq ON sq.question_id=qm.id AND sq.subject_type='math'
            LEFT JOIN options o ON o.sub_question_id=sq.id AND o.subject_type='math'
            WHERE {where}
            GROUP BY qm.id
            ORDER BY RANDOM() LIMIT 1
        """
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        opts: dict[str, str] = {}
        for k, col in [("A", "optA"), ("B", "optB"), ("C", "optC"), ("D", "optD")]:
            if row[col]:
                opts[k] = row[col]

        # year from paper_title might not be a valid year
        db_year: Optional[int] = None
        try:
            y = int(row["year"])
            if 2000 <= y <= 2030:
                db_year = y
        except (TypeError, ValueError):
            pass

        return QuestionOut(
            id=row["id"],
            subject=f"数学（{row['math_type']}）" if row["math_type"] else "数学",
            year=db_year,
            question_type=row["question_type"],
            content=row["stem"],
            options=opts or None,
            correct_answer=row["answer"] or None,
            analysis=None,
            passage_text=None,
        )
    except sqlite3.Error as exc:
        logger.warning("Math DB query failed: %s", exc)
        return None
    finally:
        conn.close()


def _fetch_english_question(
    qtype_id: Optional[str],
    year: Optional[int],
) -> Optional[QuestionOut]:
    """随机抽一道英语题（按 question_number 范围区分题型）。"""
    conn = _db_connect()
    if conn is None:
        return None
    try:
        qtype_id = qtype_id or "reading"
        qnum_range = _ENGLISH_Q_NUMBER.get(qtype_id, (2, 5))
        q_lo, q_hi = qnum_range

        conditions = ["qe.question_number BETWEEN ? AND ?"]
        params: list[Any] = [q_lo, q_hi]
        if year:
            conditions.append("qe.year = ?")
            params.append(year)
        where = " AND ".join(conditions)

        if qtype_id in ("translation", "writing_small", "writing_large"):
            # No sub-questions / options for writing and translation
            sql = f"""
                SELECT qe.id, qe.year, qe.question_number, qe.question_type, qe.content
                FROM questions_english qe
                WHERE {where}
                ORDER BY RANDOM() LIMIT 1
            """
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            return QuestionOut(
                id=row["id"],
                subject="英语",
                year=row["year"],
                question_type=row["question_type"],
                content=row["content"],
                options=None,
                correct_answer=None,
                analysis=None,
                passage_text=None,
            )

        # For reading, cloze, new_type: pick a random sub-question
        sql = f"""
            SELECT qe.id, qe.year, qe.question_number, qe.question_type,
                   qe.content AS article,
                   sq.id AS sub_q_id, sq.sub_question_number, sq.answer, sq.analysis,
                   MAX(CASE WHEN o.option_key='A' THEN o.option_text END) AS optA,
                   MAX(CASE WHEN o.option_key='B' THEN o.option_text END) AS optB,
                   MAX(CASE WHEN o.option_key='C' THEN o.option_text END) AS optC,
                   MAX(CASE WHEN o.option_key='D' THEN o.option_text END) AS optD
            FROM questions_english qe
            JOIN sub_questions sq ON sq.question_id=qe.id AND sq.subject_type='english'
            LEFT JOIN options o ON o.sub_question_id=sq.id AND o.subject_type='english'
            WHERE {where}
            GROUP BY sq.id
            ORDER BY RANDOM() LIMIT 1
        """
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        opts: dict[str, str] = {}
        for k, col in [("A", "optA"), ("B", "optB"), ("C", "optC"), ("D", "optD")]:
            if row[col]:
                opts[k] = row[col]
        sub_num = row["sub_question_number"]
        content_label = f"第 {sub_num} 题" if sub_num else "本篇小题"
        return QuestionOut(
            id=row["sub_q_id"],
            subject="英语",
            year=row["year"],
            question_type=row["question_type"],
            content=content_label,
            options=opts or None,
            correct_answer=row["answer"] or None,
            analysis=row["analysis"] or None,
            passage_text=row["article"] or None,
        )
    except sqlite3.Error as exc:
        logger.warning("English DB query failed: %s", exc)
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.get("/subjects", summary="获取科目列表")
async def get_subjects() -> list[dict]:
    return _SUBJECTS


@router.get("/types/{subject}", summary="获取科目的题型列表")
async def get_subject_types(subject: str) -> list[dict]:
    types = _TYPES.get(subject)
    if types is None:
        raise HTTPException(status_code=404, detail=f"Unknown subject: {subject}")
    return types


@router.get("/years/{subject}", summary="获取科目有数据的年份列表")
async def get_years(subject: str) -> list[int]:
    conn = _db_connect()
    if conn is None:
        return []
    try:
        if subject == "politics":
            cur = conn.execute(
                "SELECT DISTINCT year FROM questions_politics WHERE year IS NOT NULL ORDER BY year DESC"
            )
        elif subject == "english":
            cur = conn.execute(
                "SELECT DISTINCT year FROM questions_english WHERE year IS NOT NULL ORDER BY year DESC"
            )
        elif subject == "math":
            cur = conn.execute(
                """
                SELECT DISTINCT CAST(SUBSTR(p.paper_title,1,4) AS INTEGER) AS y
                FROM papers p
                WHERE CAST(SUBSTR(p.paper_title,1,4) AS INTEGER) BETWEEN 2000 AND 2030
                ORDER BY y DESC
                """
            )
        else:
            return []
        return [int(r[0]) for r in cur.fetchall() if r[0]]
    except sqlite3.Error as exc:
        logger.warning("Years query failed: %s", exc)
        return []
    finally:
        conn.close()


@router.get("/question", response_model=QuestionOut, summary="随机获取题目（支持科目/题型/年份筛选）")
async def get_practice_question(
    subject: Optional[str] = Query(None, description="科目：politics / math / english"),
    question_type: Optional[str] = Query(None, description="题型 ID（各科不同）"),
    year: Optional[int] = Query(None, description="年份，不传则全库随机"),
) -> QuestionOut:
    """
    从知识库数据库随机抽取一道题目。
    若数据库不可用或无匹配题目，降级返回内置 mock 题目。
    """
    import random

    row: Optional[QuestionOut] = None
    if subject == "politics":
        row = _fetch_politics_question(question_type, year)
    elif subject == "math":
        row = _fetch_math_question(question_type, year)
    elif subject == "english":
        row = _fetch_english_question(question_type, year)
    else:
        # No subject specified: pick randomly from any subject
        import random as _rnd
        fn = _rnd.choice([
            lambda: _fetch_politics_question("单选题", None),
            lambda: _fetch_math_question("single_choice", None),
            lambda: _fetch_english_question("reading", None),
        ])
        row = fn()

    if row:
        return row

    # Fallback to mock data
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
        llm = _build_llm(settings)
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_quiz(
                req.user_input,
                current_question=question,
                user_answer=req.user_answer or req.user_input,
                messages=req.messages or None,
                quiz_history=req.quiz_history or None,
                params=req.params or None,
                llm=llm,
            ),
        )
    except Exception as exc:
        logger.exception("Quiz agent failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"刷题处理失败：{exc}") from exc

    grade = state.get("grade_result") or {}
    _save_quiz_record(
        req.user_id,
        question,
        grade.get("is_correct"),
        user_answer=req.user_answer or req.user_input,
        score=grade.get("score"),
        feedback=grade.get("feedback"),
    )
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
        llm = _build_llm(settings)
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_quiz(
                req.user_input,
                current_question=question,
                user_answer=req.user_answer or req.user_input,
                messages=req.messages or None,
                quiz_history=req.quiz_history or None,
                params=req.params or None,
                llm=llm,
            ),
        )
    except Exception as exc:
        logger.exception("Quiz agent stream failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"刷题处理失败：{exc}") from exc

    grade = state.get("grade_result") or {}
    explanation = state.get("explanation") or ""
    followups = state.get("followup_questions") or []
    _save_quiz_record(
        req.user_id,
        question,
        grade.get("is_correct"),
        user_answer=req.user_answer or req.user_input,
        score=grade.get("score"),
        feedback=grade.get("feedback"),
    )

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
