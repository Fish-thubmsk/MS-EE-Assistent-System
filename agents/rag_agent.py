"""
RAG QA Agent — LangGraph RAG 问答模式

实现检索增强生成（RAG）问答流程：
  1. 从 FAISS（静态知识库/题库）检索相关内容
  2. 从 Chroma（动态用户笔记/错题）检索相关内容（可选）
  3. 融合召回结果，去重排序
  4. 调用 LLM（DeepSeek-R1 via SiliconFlow，或任意 LangChain LLM）生成带引用的答案
  5. 返回答案、溯源引用及相似推荐

支持：
  * 混合检索（FAISS 优先，Chroma 可选）
  * 答案溯源引用（[1] 来源: …）
  * 相似题目/知识点推荐
  * LLM 不可用时提供基于检索结果的模板回复
  * 兼容 RouterAgent 路由（mode=qa 时接入）
  * 多 LLM 接入（通过 api_key / base_url 切换，模型由环境变量 LLM_MODEL 配置）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import httpx
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from utils.sf_retry import call_with_retry, get_sf_timeout

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SILICONFLOW_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_N_FAISS = int(os.getenv("DEFAULT_N_FAISS", "5"))
DEFAULT_N_CHROMA = int(os.getenv("DEFAULT_N_CHROMA", "3"))

# ---------------------------------------------------------------------------
# RAG 状态定义
# ---------------------------------------------------------------------------


class RAGState(TypedDict):
    """RAG QA Agent 的完整 LangGraph 状态。"""

    # 输入
    messages: list[dict[str, str]]       # 对话历史
    raw_input: str                       # 当前用户问题
    params: dict[str, Any]              # 来自 RouterAgent 的参数（subject 等）

    # 检索配置
    use_faiss: bool                      # 是否检索 FAISS 静态知识库
    use_chroma: bool                     # 是否检索 Chroma 动态笔记库
    n_faiss_results: int                 # FAISS 返回结果数
    n_chroma_results: int                # Chroma 返回结果数
    chroma_filter: Optional[dict[str, str]]  # Chroma 元数据过滤（如 subject）

    # 检索结果
    faiss_results: list[dict[str, Any]]
    chroma_results: list[dict[str, Any]]
    fused_context: list[dict[str, Any]]  # 融合后的上下文（含 citation_index）

    # 输出
    answer: str
    citations: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# 检索结果统一格式
# ---------------------------------------------------------------------------

def _normalize_faiss_result(r: dict[str, Any], idx: int) -> dict[str, Any]:
    """将 FAISS 搜索结果转换为统一格式。"""
    return {
        "citation_index": idx,
        "source": "faiss",
        "doc_id": str(r.get("id", "")),
        "content": r.get("content", ""),
        "metadata": {
            "subject": r.get("subject", ""),
            "year": str(r.get("year", "")),
            "question_type": r.get("question_type", ""),
            "correct_answer": r.get("correct_answer", ""),
        },
        "score": float(r.get("score", 0.0)),
    }


def _normalize_chroma_result(r: dict[str, Any], idx: int) -> dict[str, Any]:
    """将 Chroma 查询结果转换为统一格式（距离转相似度）。"""
    distance = r.get("distance")
    # cosine distance → similarity: similarity = 1 - distance（chromadb 返回 cosine distance）
    score = (1.0 - float(distance)) if distance is not None else 0.0
    meta = r.get("metadata") or {}  # 防御 None 值，转为空字典
    return {
        "citation_index": idx,
        "source": "chroma",
        "doc_id": str(r.get("id", "")),
        "content": r.get("document", ""),
        "metadata": meta,
        "score": score,
    }


# ---------------------------------------------------------------------------
# LLM 调用（SiliconFlow OpenAI-compatible API，支持任意 LangChain LLM）
# ---------------------------------------------------------------------------

_ANSWER_PROMPT_TEMPLATE = """你是一个专业的学习助手，请根据以下检索到的参考资料，为用户的问题提供清晰、准确的答案。

参考资料：
{context}

用户问题：{question}

要求：
1. 答案中需引用参考资料，用 [序号] 标注（如 [1]、[2]）
2. 若参考资料中有题目，可附上正确答案
3. 如有相关知识点，可适当补充说明
4. 支持中英文混合回答
5. 若参考资料不足以回答问题，请说明并给出基于已有知识的回答

答案："""


def _build_context_text(fused_context: list[dict[str, Any]]) -> str:
    """将融合上下文格式化为 LLM 提示文本。"""
    parts = []
    for item in fused_context:
        idx = item["citation_index"]
        content = item["content"][:500]  # 截断过长内容
        meta = item.get("metadata") or {}  # 防御 None 值
        source_label = "知识库题目" if item["source"] == "faiss" else "个人笔记/错题"
        subject = meta.get("subject", "") if isinstance(meta, dict) else ""
        year = meta.get("year", "") if isinstance(meta, dict) else ""
        prefix = f"[{idx}] ({source_label}"
        if subject:
            prefix += f" | {subject}"
        if year:
            prefix += f" | {year}"
        prefix += ")"
        parts.append(f"{prefix}\n{content}")
    return "\n\n".join(parts) if parts else "（暂无相关参考资料）"


def _call_siliconflow_llm(
    prompt: str,
    api_key: str,
    model: str,
    base_url: str = SILICONFLOW_BASE_URL,
    timeout: Optional[int] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    直接调用 SiliconFlow OpenAI-compatible Chat Completions API。

    Args:
        prompt: 用户提示文本。
        api_key: SiliconFlow API Key。
        model: 模型名称，必须显式传入（通过 LLM_MODEL 环境变量或调用方指定）。
        base_url: API 基础 URL。
        timeout: 超时秒数；为 None 时读取环境变量 SF_API_TIMEOUT（默认 30）。
        temperature: 采样温度；为 None 时读取环境变量 LLM_TEMPERATURE（默认 0.3）。
        max_tokens: 最大生成 token 数；为 None 时读取环境变量 LLM_MAX_TOKENS（默认 2048）。

    Returns:
        LLM 生成的答案文本。

    Raises:
        httpx.HTTPStatusError: API 请求失败。
        ValueError: API Key 未配置。
    """
    if not api_key:
        raise ValueError(
            "SiliconFlow API Key 未配置，请设置环境变量 SILICONFLOW_API_KEY。"
        )
    if not model:
        raise ValueError(
            "LLM 模型名称未配置，请设置环境变量 LLM_MODEL（推荐：deepseek-ai/DeepSeek-V3）。"
        )
    _timeout = timeout if timeout is not None else get_sf_timeout()
    if temperature is not None:
        _temperature = temperature
    else:
        _raw_temp = os.environ.get("LLM_TEMPERATURE", "0.3")
        try:
            _temperature = float(_raw_temp)
        except (ValueError, TypeError):
            logger.warning(
                "LLM_TEMPERATURE 的值 %r 无效（应为浮点数），使用默认值 0.3。", _raw_temp
            )
            _temperature = 0.3
    if max_tokens is not None:
        _max_tokens = max_tokens
    else:
        _raw_mt = os.environ.get("LLM_MAX_TOKENS", "2048")
        try:
            _max_tokens = int(_raw_mt)
            if _max_tokens <= 0:
                raise ValueError("must be positive")
        except (ValueError, TypeError):
            logger.warning(
                "LLM_MAX_TOKENS 的值 %r 无效（应为正整数），使用默认值 2048。", _raw_mt
            )
            _max_tokens = 2048
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": _temperature,
        "max_tokens": _max_tokens,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    response = call_with_retry(
        lambda: httpx.post(url, json=payload, headers=headers, timeout=_timeout)
    )
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_langchain_llm(prompt: str, llm: Any) -> str:
    """调用 LangChain LLM 实例生成答案。"""
    response = llm.invoke(prompt)
    return getattr(response, "content", str(response)).strip()


# ---------------------------------------------------------------------------
# RAG Agent
# ---------------------------------------------------------------------------


class RAGAgent:
    """
    LangGraph RAG 问答 Agent。

    Args:
        faiss_searcher: 可调用对象，签名 (query: str, top_k: int) -> list[dict]。
                        默认使用 knowledge_base.search_demo.search。
        chroma_manager: ChromaManager 实例；若为 None 则跳过 Chroma 检索。
        llm: LangChain LLM 实例（优先使用）。
        api_key: SiliconFlow API Key（llm 未提供时使用）；默认读取环境变量。
        llm_model: LLM 模型名称；未传入时读取环境变量 LLM_MODEL。
        llm_base_url: LLM API 基础 URL，默认 SiliconFlow。
        llm_temperature: LLM 采样温度；未传入时读取环境变量 LLM_TEMPERATURE（默认 0.3）。
        llm_max_tokens: LLM 最大生成 token 数；未传入时读取环境变量 LLM_MAX_TOKENS（默认 2048）。
    """

    def __init__(
        self,
        faiss_searcher: Optional[Any] = None,
        chroma_manager: Optional[Any] = None,
        llm: Optional[Any] = None,
        api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: str = SILICONFLOW_BASE_URL,
        llm_temperature: Optional[float] = None,
        llm_max_tokens: Optional[int] = None,
    ) -> None:
        self._faiss_searcher = faiss_searcher or _default_faiss_searcher
        self._chroma_manager = chroma_manager
        self._llm = llm
        self._api_key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
        self._llm_model = llm_model or os.environ.get("LLM_MODEL", "")
        self._llm_base_url = llm_base_url
        self._llm_temperature = llm_temperature
        self._llm_max_tokens = llm_max_tokens

    # ------------------------------------------------------------------
    # LangGraph 节点
    # ------------------------------------------------------------------

    def retrieve_faiss(self, state: RAGState) -> RAGState:
        """从 FAISS 静态知识库检索相关内容。"""
        if not state.get("use_faiss", True):
            return {**state, "faiss_results": []}

        query = state["raw_input"]
        n = state.get("n_faiss_results", DEFAULT_N_FAISS)
        try:
            results = self._faiss_searcher(query, n)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("FAISS 检索失败：%s", exc)
            results = []
        return {**state, "faiss_results": results}

    def retrieve_chroma(self, state: RAGState) -> RAGState:
        """从 Chroma 动态笔记库检索相关内容（可选）。"""
        if not state.get("use_chroma", False) or self._chroma_manager is None:
            return {**state, "chroma_results": []}

        query = state["raw_input"]
        n = state.get("n_chroma_results", DEFAULT_N_CHROMA)
        where = state.get("chroma_filter")
        try:
            results = self._chroma_manager.query(query, n_results=n, where=where)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Chroma 检索失败：%s", exc)
            results = []
        return {**state, "chroma_results": results}

    @staticmethod
    def fuse_results(state: RAGState) -> RAGState:
        """
        融合 FAISS 与 Chroma 检索结果：
        - FAISS 结果优先（得分高）排列在前
        - 按 content 去重（保留得分较高的版本）
        - 为每个结果分配 citation_index（从 1 开始，最多 5 个）
        - 推荐从剩余未使用的 FAISS 结果中取（去重，最多 3 个）
        """
        MAX_CITATIONS = 5
        MAX_RECOMMENDATIONS = 3
        
        faiss_raw = state.get("faiss_results", [])
        chroma_raw = state.get("chroma_results", [])

        normalized: list[dict[str, Any]] = []
        # FAISS 先放入（优先）
        for r in faiss_raw:
            normalized.append(_normalize_faiss_result(r, 0))
        for r in chroma_raw:
            normalized.append(_normalize_chroma_result(r, 0))

        # 按 score 降序排列
        normalized.sort(key=lambda x: x["score"], reverse=True)

        # 去重（基于内容前 100 字符）
        seen_contents: set[str] = set()
        fused: list[dict[str, Any]] = []
        for item in normalized:
            key = item["content"][:100].strip()
            if key and key not in seen_contents:
                seen_contents.add(key)
                item["citation_index"] = len(fused) + 1
                fused.append(item)
                # 最多 MAX_CITATIONS 个用于引用
                if len(fused) >= MAX_CITATIONS:
                    break

        # 推荐：从原始 FAISS 结果中取，排除已在 citations 中的内容
        recommendations = []
        for item in faiss_raw:
            # 检查这个 FAISS 结果是否已被加入 fused
            content_key = item.get("content", "")[:100].strip()
            if content_key and content_key not in seen_contents:
                recommendations.append({
                    "doc_id": item.get("doc_id", ""),
                    "source": item.get("source", "faiss"),  # 添加来源标识
                    "content_snippet": item.get("content", "")[:300],
                    "metadata": item.get("metadata", {}),  # 添加完整元数据
                    "score": item.get("score", 0),
                })
                # 最多 MAX_RECOMMENDATIONS 个推荐
                if len(recommendations) >= MAX_RECOMMENDATIONS:
                    break

        return {**state, "fused_context": fused, "recommendations": recommendations}

    def generate_answer(self, state: RAGState) -> RAGState:
        """
        使用 LLM 生成带引用的答案；若 LLM 不可用，返回结构化模板答案。
        """
        fused = state.get("fused_context", [])
        question = state["raw_input"]

        context_text = _build_context_text(fused)
        prompt = _ANSWER_PROMPT_TEMPLATE.format(
            context=context_text,
            question=question,
        )

        answer = ""
        # 1. 优先使用 LangChain LLM
        if self._llm is not None:
            try:
                answer = _call_langchain_llm(prompt, self._llm)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("LangChain LLM 调用失败：%s", exc)

        # 2. 退回到直接 API 调用
        if not answer and self._api_key:
            try:
                answer = _call_siliconflow_llm(
                    prompt,
                    api_key=self._api_key,
                    model=self._llm_model,
                    base_url=self._llm_base_url,
                    temperature=self._llm_temperature,
                    max_tokens=self._llm_max_tokens,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("SiliconFlow LLM API 调用失败：%s", exc)

        # 3. 最终降级：基于检索结果的模板答案
        if not answer:
            if fused:
                snippets = "\n".join(
                    f"[{item['citation_index']}] {item['content'][:200]}"
                    for item in fused[:3]
                )
                answer = (
                    f"根据知识库检索结果，以下是与您问题相关的内容：\n\n{snippets}\n\n"
                    "（提示：配置 SILICONFLOW_API_KEY 后可获得 LLM 生成的详细解答。）"
                )
            else:
                answer = (
                    "抱歉，未能在知识库中找到与您问题直接相关的内容。"
                    "请尝试换一种提问方式，或确认知识库已正确建立索引。"
                )

        # 构建引用列表
        citations = [
            {
                "index": item["citation_index"],
                "source": item["source"],
                "doc_id": item["doc_id"],
                "content_snippet": item["content"][:500],  # 增加到 500 字符，保留更多内容
                "metadata": item["metadata"],
            }
            for item in fused
        ]

        # 将 assistant 回复追加到消息列表
        messages = list(state.get("messages", []))
        messages.append({"role": "assistant", "content": answer})

        return {
            **state,
            "answer": answer,
            "citations": citations,
            "messages": messages,
        }


# ---------------------------------------------------------------------------
# 默认 FAISS 检索器（惰性导入，避免循环依赖）
# ---------------------------------------------------------------------------


def _default_faiss_searcher(query: str, top_k: int) -> list[dict[str, Any]]:
    """
    默认 FAISS 检索器，使用 knowledge_base.search_demo.search。
    FAISS 索引不存在时静默返回空列表。
    """
    try:
        from knowledge_base.search_demo import search  # noqa: PLC0415

        return search(query, top_k=top_k)
    except FileNotFoundError:
        logger.warning(
            "FAISS 索引文件不存在，跳过检索。"
            "请先运行 `python knowledge_base/build_faiss_index.py` 构建索引。"
        )
        return []
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("FAISS 检索异常：%s", exc)
        return []


# ---------------------------------------------------------------------------
# Graph 工厂
# ---------------------------------------------------------------------------


def create_rag_graph(
    faiss_searcher: Optional[Any] = None,
    chroma_manager: Optional[Any] = None,
    llm: Optional[Any] = None,
    api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: str = SILICONFLOW_BASE_URL,
    llm_temperature: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
) -> Any:
    """
    构建并编译 RAG QA Agent 的 LangGraph 工作流。

    Graph 结构：
        START
          │
        retrieve_faiss
          │
        retrieve_chroma
          │
        fuse_results
          │
        generate_answer
          │
        END

    Args:
        faiss_searcher: 可调用对象，签名 (query, top_k) -> list[dict]。
        chroma_manager: ChromaManager 实例（为 None 时跳过 Chroma）。
        llm: LangChain LLM 实例（优先使用）。
        api_key: SiliconFlow API Key；未提供时读取环境变量。
        llm_model: LLM 模型名称；未传入时读取环境变量 LLM_MODEL。
        llm_base_url: LLM API 基础 URL。
        llm_temperature: LLM 采样温度；未传入时读取环境变量 LLM_TEMPERATURE（默认 0.3）。
        llm_max_tokens: LLM 最大生成 token 数；未传入时读取环境变量 LLM_MAX_TOKENS（默认 2048）。

    Returns:
        编译后的 CompiledGraph 对象。
    """
    agent = RAGAgent(
        faiss_searcher=faiss_searcher,
        chroma_manager=chroma_manager,
        llm=llm,
        api_key=api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )

    graph = StateGraph(RAGState)

    graph.add_node("retrieve_faiss", agent.retrieve_faiss)
    graph.add_node("retrieve_chroma", agent.retrieve_chroma)
    graph.add_node("fuse_results", RAGAgent.fuse_results)
    graph.add_node("generate_answer", agent.generate_answer)

    graph.add_edge(START, "retrieve_faiss")
    graph.add_edge("retrieve_faiss", "retrieve_chroma")
    graph.add_edge("retrieve_chroma", "fuse_results")
    graph.add_edge("fuse_results", "generate_answer")
    graph.add_edge("generate_answer", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 便捷调用接口
# ---------------------------------------------------------------------------


def run_rag(
    user_input: str,
    *,
    faiss_searcher: Optional[Any] = None,
    chroma_manager: Optional[Any] = None,
    llm: Optional[Any] = None,
    api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: str = SILICONFLOW_BASE_URL,
    llm_temperature: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
    messages: Optional[list[dict[str, str]]] = None,
    params: Optional[dict[str, Any]] = None,
    use_faiss: bool = True,
    use_chroma: bool = False,
    n_faiss_results: int = DEFAULT_N_FAISS,
    n_chroma_results: int = DEFAULT_N_CHROMA,
    chroma_filter: Optional[dict[str, str]] = None,
) -> RAGState:
    """
    单次调用 RAG QA Agent，返回更新后的状态。

    Args:
        user_input: 当前用户问题。
        faiss_searcher: 自定义 FAISS 检索函数，默认使用内置实现。
        chroma_manager: ChromaManager 实例（启用 Chroma 检索时需提供）。
        llm: LangChain LLM 实例。
        api_key: SiliconFlow API Key。
        llm_model: LLM 模型名称；未传入时读取环境变量 LLM_MODEL。
        llm_base_url: LLM API 基础 URL。
        llm_temperature: LLM 采样温度；未传入时读取环境变量 LLM_TEMPERATURE（默认 0.3）。
        llm_max_tokens: LLM 最大生成 token 数；未传入时读取环境变量 LLM_MAX_TOKENS（默认 2048）。
        messages: 历史消息列表。
        params: RouterAgent 传来的参数（subject 等）。
        use_faiss: 是否检索 FAISS，默认 True。
        use_chroma: 是否检索 Chroma，默认 False。
        n_faiss_results: FAISS 返回结果数。
        n_chroma_results: Chroma 返回结果数。
        chroma_filter: Chroma 元数据过滤条件。

    Returns:
        更新后的 RAGState（包含 answer、citations、recommendations）。
    """
    compiled = create_rag_graph(
        faiss_searcher=faiss_searcher,
        chroma_manager=chroma_manager,
        llm=llm,
        api_key=api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )

    initial: RAGState = {
        "messages": list(messages or [{"role": "user", "content": user_input}]),
        "raw_input": user_input,
        "params": dict(params or {}),
        "use_faiss": use_faiss,
        "use_chroma": use_chroma,
        "n_faiss_results": n_faiss_results,
        "n_chroma_results": n_chroma_results,
        "chroma_filter": chroma_filter,
        "faiss_results": [],
        "chroma_results": [],
        "fused_context": [],
        "answer": "",
        "citations": [],
        "recommendations": [],
    }

    result: RAGState = compiled.invoke(initial)
    return result
