"""
问答（RAG）API 路由模块

提供以下接口：
    POST /api/answer          同步 RAG 问答，返回完整答案
    POST /api/answer/stream   SSE 流式 RAG 问答，逐 token 返回 LLM 生成内容
    GET  /api/answer/mock     使用 mock 数据快速体验问答
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Annotated, Any, AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.rag_agent import (
    DEFAULT_N_CHROMA,
    DEFAULT_N_FAISS,
    SILICONFLOW_BASE_URL,
    _ANSWER_PROMPT_TEMPLATE,
    run_rag,
)
from backend.config import Settings, get_settings
from backend.routers.notes import get_manager as _get_notes_chroma_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/answer", tags=["answer"])

SettingsDep = Annotated[Settings, Depends(get_settings)]

# Maximum number of historical messages included in streaming prompt context
_MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "6"))
# Delay between streamed characters in mock mode (seconds)
_STREAM_CHAR_DELAY = float(os.getenv("STREAM_CHAR_DELAY", "0.01"))


def get_optional_chroma_manager() -> Optional[Any]:
    """
    答案端点专用的 ChromaManager 可选依赖。

    委托给 notes 路由中的单例工厂；若初始化失败（例如无 SiliconFlow API Key
    或 LLM_MODEL 未配置的测试环境），静默返回 None，RAG 流程将跳过 Chroma 检索。
    """
    # NOTE: We deliberately catch all Exception subclasses (not BaseException) so that
    # any realistic failure mode (ValidationError, RuntimeError, OSError, etc.) during
    # ChromaManager/settings initialization is handled gracefully.  KeyboardInterrupt
    # and SystemExit are BaseException subclasses and are intentionally NOT caught here.
    try:
        return _get_notes_chroma_manager()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("ChromaManager 初始化失败，Chroma 检索将不可用: %s", exc)
        return None


OptionalChromaManagerDep = Annotated[Optional[Any], Depends(get_optional_chroma_manager)]


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class AnswerRequest(BaseModel):
    user_input: str = Field(..., description="用户问题")
    messages: list[dict[str, str]] = Field(
        default_factory=list, description="历史对话消息列表"
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="路由参数（如 subject、year 等）"
    )
    use_faiss: bool = Field(default=True, description="是否检索 FAISS 静态知识库")
    use_chroma: bool = Field(default=False, description="是否检索 Chroma 动态笔记库")
    n_faiss_results: int = Field(
        default=DEFAULT_N_FAISS, ge=1, le=20, description="FAISS 返回结果数"
    )
    n_chroma_results: int = Field(
        default=DEFAULT_N_CHROMA, ge=1, le=10, description="Chroma 返回结果数"
    )
    chroma_filter: Optional[dict[str, str]] = Field(
        None, description="Chroma 元数据过滤（如 {subject: 数学}）"
    )


class CitationOut(BaseModel):
    index: int
    source: str
    doc_id: str
    content_snippet: str
    metadata: dict[str, Any]


class RecommendationOut(BaseModel):
    doc_id: str
    content_snippet: str
    subject: Optional[str] = None
    year: Optional[str] = None
    score: float


class AnswerResponse(BaseModel):
    answer: str = Field(..., description="LLM 生成的答案（含引用标注）")
    citations: list[CitationOut] = Field(default_factory=list, description="答案溯源引用")
    recommendations: list[RecommendationOut] = Field(
        default_factory=list, description="相似题目推荐"
    )
    messages: list[dict[str, str]] = Field(..., description="更新后的消息列表")


# ---------------------------------------------------------------------------
# 内部工具：SSE 格式化 & SiliconFlow 流式调用
# ---------------------------------------------------------------------------


def _sse_event(data: str, event: str = "message") -> str:
    """将数据格式化为 SSE 事件字符串。"""
    return f"event: {event}\ndata: {data}\n\n"


async def _stream_siliconflow(
    prompt: str,
    api_key: str,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    citations: Optional[list[dict[str, Any]]] = None,
    recommendations: Optional[list[dict[str, Any]]] = None,
) -> AsyncGenerator[str, None]:
    """
    调用 SiliconFlow OpenAI-compatible Streaming API，逐 chunk yield SSE 事件。

    事件序列：
    1. ``event: metadata`` — 发送引用和推荐信息
    2. ``event: token`` — 逐个发送 token
    3. ``event: done`` — 生成完毕

    Args:
        citations: 可选的引用列表，将在流开始时发送
        recommendations: 可选的推荐列表，将在流开始时发送
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    # 首先发送元数据（引用和推荐）
    if citations or recommendations:
        yield _sse_event(
            json.dumps(
                {
                    "citations": citations or [],
                    "recommendations": recommendations or [],
                },
                ensure_ascii=False,
            ),
            event="metadata",
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield _sse_event(
                    json.dumps(
                        {"error": f"LLM API 错误 {response.status_code}: {error_body.decode()}"},
                        ensure_ascii=False,
                    ),
                    event="error",
                )
                return

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw.strip() == "[DONE]":
                    yield _sse_event(json.dumps({"status": "done"}, ensure_ascii=False), event="done")
                    return
                try:
                    chunk = json.loads(raw)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield _sse_event(
                            json.dumps({"token": content}, ensure_ascii=False),
                            event="token",
                        )
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def _stream_mock(question: str) -> AsyncGenerator[str, None]:
    """
    无需 API Key 的 mock 流式输出，用于演示 SSE 链路。
    """
    mock_answer = (
        f"**Mock 流式回答**\n\n"
        f"您的问题是：{question}\n\n"
        "这是一个 mock 流式响应示例。\n"
        "实际生产环境请配置 `SILICONFLOW_API_KEY` 以启用真实 LLM 输出。\n\n"
        "知识点提示：\n"
        "- 配置 `.env` 文件并填入 `SILICONFLOW_API_KEY`\n"
        "- 可通过 `LLM_MODEL` 环境变量切换模型\n"
        "- SSE 流式响应使用 `event: token` 逐 chunk 传输\n"
    )
    for char in mock_answer:
        yield _sse_event(json.dumps({"token": char}, ensure_ascii=False), event="token")
        await asyncio.sleep(_STREAM_CHAR_DELAY)
    yield _sse_event(json.dumps({"status": "done"}, ensure_ascii=False), event="done")


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.post("", response_model=AnswerResponse, summary="RAG 同步问答")
async def answer(
    req: AnswerRequest,
    settings: SettingsDep,
    _chroma_manager: OptionalChromaManagerDep,
) -> AnswerResponse:
    """
    接收用户问题，通过 RAG 流程（FAISS + Chroma 检索 + LLM 生成）返回完整答案。

    - 若 **SILICONFLOW_API_KEY** 未配置，降级为基于检索结果的模板答案。
    - 通过 **use_chroma** 参数控制是否融合 Chroma 个人笔记。
    """
    # 仅在 use_chroma=True 时将 ChromaManager 实例传入 RAG 流程
    chroma_mgr = _chroma_manager if req.use_chroma else None

    try:
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_rag(
                req.user_input,
                api_key=settings.siliconflow_api_key,
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_temperature=settings.llm_temperature,
                llm_max_tokens=settings.llm_max_tokens,
                messages=req.messages or None,
                params=req.params or None,
                use_faiss=req.use_faiss,
                use_chroma=req.use_chroma,
                chroma_manager=chroma_mgr,
                n_faiss_results=req.n_faiss_results,
                n_chroma_results=req.n_chroma_results,
                chroma_filter=req.chroma_filter,
            ),
        )
    except Exception as exc:
        logger.exception("RAG answer failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"问答处理失败：{exc}") from exc

    return AnswerResponse(
        answer=state["answer"],
        citations=[CitationOut(**c) for c in state.get("citations", [])],
        recommendations=[
            RecommendationOut(
                doc_id=r["doc_id"],
                content_snippet=r["content_snippet"],
                subject=r.get("metadata", {}).get("subject") if isinstance(r.get("metadata"), dict) else None,
                year=r.get("metadata", {}).get("year") if isinstance(r.get("metadata"), dict) else None,
                score=r["score"],
            )
            for r in state.get("recommendations", [])
        ],
        messages=state["messages"],
    )


@router.post("/stream", summary="RAG SSE 流式问答")
async def answer_stream(
    req: AnswerRequest, settings: SettingsDep, _chroma_manager: OptionalChromaManagerDep
) -> StreamingResponse:
    """
    SSE 流式返回 LLM 生成内容，同时使用 RAG 增强。

    **流程：**
    1. 同步执行 RAG（检索 FAISS + Chroma，融合上下文）
    2. 流式调用 LLM 生成答案（带完整 RAG context）

    **SSE 事件类型：**
    - `event: metadata` — 引用来源和相似推荐（JSON），第一个事件发送
    - `event: token` — 单个 token 或文本片段，`data` 为 `{"token": "..."}`
    - `event: done`  — 生成完毕，`data` 为 `{"status": "done"}`
    - `event: error` — 发生错误，`data` 为 `{"error": "..."}`

    如未配置 `SILICONFLOW_API_KEY`，返回 mock 流式演示内容。
    """
    api_key = settings.siliconflow_api_key

    if not api_key:
        # Mock 演示模式
        return StreamingResponse(
            _stream_mock(req.user_input),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # 阶段 1：同步执行 RAG（检索 + context 构建）
    chroma_mgr = _chroma_manager if req.use_chroma else None
    
    # 如果需要推荐，请求更多 FAISS 结果（citations + 额外推荐用）
    n_faiss = req.n_faiss_results
    # 默认情况：citations 用 5 个，推荐用额外 3 个，所以总共请求 8 个
    if req.use_faiss and n_faiss <= 5:
        n_faiss = 8
    
    try:
        state = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_rag(
                req.user_input,
                api_key="",  # 禁用同步 RAG 的 LLM 调用（我们在流式中调用）
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_temperature=settings.llm_temperature,
                llm_max_tokens=settings.llm_max_tokens,
                messages=req.messages or None,
                params=req.params or None,
                use_faiss=req.use_faiss,
                use_chroma=req.use_chroma,
                chroma_manager=chroma_mgr,
                n_faiss_results=n_faiss,
                n_chroma_results=req.n_chroma_results,
                chroma_filter=req.chroma_filter,
            ),
        )
    except Exception as exc:
        logger.exception("RAG 检索失败: %s", exc)
        # 降级：无上下文的流式回答
        state = {
            "fused_context": [],
            "citations": [],
            "recommendations": [],
        }

    # 阶段 2：用 RAG context 构建完整 prompt
    from agents.rag_agent import _build_context_text  # noqa: PLC0415

    fused_context = state.get("fused_context", [])
    context_text = _build_context_text(fused_context)
    prompt = _ANSWER_PROMPT_TEMPLATE.format(
        context=context_text,
        question=req.user_input,
    )

    # 为了兼容历史消息（optional）
    if req.messages:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in req.messages[-_MAX_HISTORY_MESSAGES:]
        )
        prompt = f"对话历史：\n{history_text}\n\n{prompt}"

    # 阶段 3：流式调用 LLM，同时发送引用信息
    return StreamingResponse(
        _stream_siliconflow(
            prompt=prompt,
            api_key=api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
            citations=state.get("citations", []),
            recommendations=state.get("recommendations", []),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mock", response_model=AnswerResponse, summary="Mock 问答演示")
async def answer_mock() -> AnswerResponse:
    """
    使用内置 mock 数据快速体验问答流程，无需任何配置。
    """
    mock_question = "什么是极限？"
    state = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_rag(
            mock_question,
            api_key="",
            use_faiss=True,
            use_chroma=False,
        ),
    )
    return AnswerResponse(
        answer=state["answer"],
        citations=[CitationOut(**c) for c in state.get("citations", [])],
        recommendations=[RecommendationOut(**r) for r in state.get("recommendations", [])],
        messages=state["messages"],
    )
