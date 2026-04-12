"""
RAG QA Agent 单元测试

所有测试完全离线：
- FAISS 检索使用 mock 函数（无需 API Key 或索引文件）
- Chroma 检索使用 mock ChromaManager
- LLM 生成使用 mock 对象
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.rag_agent import (
    DEFAULT_N_CHROMA,
    DEFAULT_N_FAISS,
    RAGAgent,
    RAGState,
    _build_context_text,
    _normalize_chroma_result,
    _normalize_faiss_result,
    create_rag_graph,
    run_rag,
)


# ---------------------------------------------------------------------------
# Mock 数据
# ---------------------------------------------------------------------------

_FAISS_RESULT_1 = {
    "id": 1,
    "subject": "数学",
    "year": 2023,
    "question_type": "选择题",
    "content": "极限 lim(x→0) sin(x)/x 的值是多少？",
    "correct_answer": "1",
    "score": 0.92,
    "vector_id": 0,
}

_FAISS_RESULT_2 = {
    "id": 2,
    "subject": "数学",
    "year": 2022,
    "question_type": "填空题",
    "content": "e 的定义：lim(x→∞)(1+1/x)^x",
    "correct_answer": "e ≈ 2.718",
    "score": 0.78,
    "vector_id": 1,
}

_CHROMA_RESULT_1 = {
    "id": "note_math_001",
    "document": "极限是微积分的基础概念，描述函数在某一点附近的趋势。",
    "metadata": {"subject": "数学", "type": "note", "chapter": "极限"},
    "distance": 0.1,  # cosine distance → similarity ≈ 0.9
}


def _mock_faiss_searcher(query: str, top_k: int) -> list[dict]:
    return [_FAISS_RESULT_1, _FAISS_RESULT_2][:top_k]


def _mock_faiss_searcher_empty(query: str, top_k: int) -> list[dict]:
    return []


def _make_state(
    raw_input: str = "什么是极限？",
    use_faiss: bool = True,
    use_chroma: bool = False,
    faiss_results: list | None = None,
    chroma_results: list | None = None,
) -> RAGState:
    return RAGState(
        messages=[{"role": "user", "content": raw_input}],
        raw_input=raw_input,
        params={},
        use_faiss=use_faiss,
        use_chroma=use_chroma,
        use_rrf=False,
        rrf_k=60,
        use_rerank=False,
        rerank_model="Pro/BAAI/bge-reranker-v2-m3",
        rerank_top_n=5,
        n_faiss_results=DEFAULT_N_FAISS,
        n_chroma_results=DEFAULT_N_CHROMA,
        chroma_filter=None,
        faiss_results=faiss_results or [],
        chroma_results=chroma_results or [],
        fused_context_before_rerank=[],
        fused_context=[],
        answer="",
        citations=[],
        recommendations=[],
    )


# ---------------------------------------------------------------------------
# _normalize_faiss_result / _normalize_chroma_result
# ---------------------------------------------------------------------------


class TestNormalizeResults:
    def test_faiss_result_fields(self) -> None:
        result = _normalize_faiss_result(_FAISS_RESULT_1, idx=1)
        assert result["source"] == "faiss"
        assert result["citation_index"] == 1
        assert result["doc_id"] == "1"
        assert "极限" in result["content"]
        assert result["score"] == pytest.approx(0.92)
        assert result["metadata"]["subject"] == "数学"
        assert result["metadata"]["year"] == "2023"

    def test_chroma_result_fields(self) -> None:
        result = _normalize_chroma_result(_CHROMA_RESULT_1, idx=1)
        assert result["source"] == "chroma"
        assert result["citation_index"] == 1
        assert result["doc_id"] == "note_math_001"
        assert "极限" in result["content"]
        # distance=0.1 → score ≈ 0.9
        assert result["score"] == pytest.approx(0.9)

    def test_chroma_result_no_distance(self) -> None:
        result = _normalize_chroma_result({"id": "x", "document": "test", "metadata": {}}, idx=2)
        assert result["score"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _build_context_text
# ---------------------------------------------------------------------------


class TestBuildContextText:
    def test_empty_context(self) -> None:
        text = _build_context_text([])
        assert "暂无" in text

    def test_includes_citation_index(self) -> None:
        items = [
            {
                "citation_index": 1,
                "source": "faiss",
                "content": "测试内容",
                "metadata": {"subject": "数学", "year": "2023"},
                "score": 0.9,
            }
        ]
        text = _build_context_text(items)
        assert "[1]" in text
        assert "数学" in text
        assert "测试内容" in text


# ---------------------------------------------------------------------------
# RAGAgent 节点：retrieve_faiss
# ---------------------------------------------------------------------------


class TestRetrieveFaiss:
    def test_retrieves_results(self) -> None:
        agent = RAGAgent(faiss_searcher=_mock_faiss_searcher)
        state = _make_state(use_faiss=True)
        new_state = agent.retrieve_faiss(state)
        assert len(new_state["faiss_results"]) > 0

    def test_skips_when_disabled(self) -> None:
        agent = RAGAgent(faiss_searcher=_mock_faiss_searcher)
        state = _make_state(use_faiss=False)
        new_state = agent.retrieve_faiss(state)
        assert new_state["faiss_results"] == []

    def test_handles_searcher_exception(self) -> None:
        def bad_searcher(q, k):
            raise RuntimeError("index not found")

        agent = RAGAgent(faiss_searcher=bad_searcher)
        state = _make_state(use_faiss=True)
        new_state = agent.retrieve_faiss(state)
        assert new_state["faiss_results"] == []


# ---------------------------------------------------------------------------
# RAGAgent 节点：retrieve_chroma
# ---------------------------------------------------------------------------


class TestRetrieveChroma:
    def test_skips_when_disabled(self) -> None:
        mock_mgr = MagicMock()
        agent = RAGAgent(chroma_manager=mock_mgr)
        state = _make_state(use_chroma=False)
        new_state = agent.retrieve_chroma(state)
        assert new_state["chroma_results"] == []
        mock_mgr.query.assert_not_called()

    def test_skips_when_no_manager(self) -> None:
        agent = RAGAgent(chroma_manager=None)
        state = _make_state(use_chroma=True)
        new_state = agent.retrieve_chroma(state)
        assert new_state["chroma_results"] == []

    def test_retrieves_from_chroma(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.query.return_value = [_CHROMA_RESULT_1]
        agent = RAGAgent(chroma_manager=mock_mgr)
        state = _make_state(use_chroma=True)
        new_state = agent.retrieve_chroma(state)
        assert len(new_state["chroma_results"]) == 1
        mock_mgr.query.assert_called_once()

    def test_handles_chroma_exception(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.query.side_effect = RuntimeError("chroma error")
        agent = RAGAgent(chroma_manager=mock_mgr)
        state = _make_state(use_chroma=True)
        new_state = agent.retrieve_chroma(state)
        assert new_state["chroma_results"] == []

    def test_passes_chroma_filter(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.query.return_value = []
        agent = RAGAgent(chroma_manager=mock_mgr)
        state = _make_state(use_chroma=True)
        state["chroma_filter"] = {"subject": "数学"}
        agent.retrieve_chroma(state)
        _, kwargs = mock_mgr.query.call_args
        assert kwargs.get("where") == {"subject": "数学"}


# ---------------------------------------------------------------------------
# RAGAgent 节点：fuse_results
# ---------------------------------------------------------------------------


class TestFuseResults:
    def test_fuses_faiss_and_chroma(self) -> None:
        state = _make_state(
            faiss_results=[_FAISS_RESULT_1],
            chroma_results=[_CHROMA_RESULT_1],
        )
        new_state = RAGAgent.fuse_results(state)
        fused = new_state["fused_context"]
        assert len(fused) == 2

    def test_citation_indices_start_at_one(self) -> None:
        state = _make_state(faiss_results=[_FAISS_RESULT_1, _FAISS_RESULT_2])
        new_state = RAGAgent.fuse_results(state)
        indices = [item["citation_index"] for item in new_state["fused_context"]]
        assert indices[0] == 1
        assert indices == list(range(1, len(indices) + 1))

    def test_deduplicates_same_content(self) -> None:
        dup = dict(_FAISS_RESULT_1)
        state = _make_state(faiss_results=[_FAISS_RESULT_1, dup])
        new_state = RAGAgent.fuse_results(state)
        assert len(new_state["fused_context"]) == 1

    def test_empty_results(self) -> None:
        state = _make_state()
        new_state = RAGAgent.fuse_results(state)
        assert new_state["fused_context"] == []
        assert new_state["recommendations"] == []

    def test_sorted_by_score_descending(self) -> None:
        state = _make_state(faiss_results=[_FAISS_RESULT_2, _FAISS_RESULT_1])
        new_state = RAGAgent.fuse_results(state)
        scores = [item["score"] for item in new_state["fused_context"]]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_mode_reorders_by_rank_fusion(self) -> None:
        state = _make_state(
            faiss_results=[_FAISS_RESULT_1, _FAISS_RESULT_2],
            chroma_results=[_CHROMA_RESULT_1],
            use_chroma=True,
        )
        state["use_rrf"] = True
        state["rrf_k"] = 10
        new_state = RAGAgent.fuse_results(state)
        assert len(new_state["fused_context"]) >= 1
        # RRF 模式下 score 为融合分值，通常较小但应为正数
        assert all(item["score"] > 0 for item in new_state["fused_context"])

    def test_recommendations_include_faiss_items(self) -> None:
        state = _make_state(faiss_results=[_FAISS_RESULT_1])
        new_state = RAGAgent.fuse_results(state)
        assert len(new_state["recommendations"]) >= 1
        assert "content_snippet" in new_state["recommendations"][0]


# ---------------------------------------------------------------------------
# RAGAgent 节点：generate_answer
# ---------------------------------------------------------------------------


class TestGenerateAnswer:
    def _state_with_context(self) -> RAGState:
        state = _make_state(
            faiss_results=[_FAISS_RESULT_1],
            chroma_results=[_CHROMA_RESULT_1],
        )
        return RAGAgent.fuse_results(state)

    def test_fallback_answer_when_no_llm_and_no_key(self) -> None:
        agent = RAGAgent(faiss_searcher=_mock_faiss_searcher, api_key="")
        state = self._state_with_context()
        new_state = agent.generate_answer(state)
        assert new_state["answer"] != ""
        assert len(new_state["citations"]) > 0

    def test_fallback_answer_when_no_context(self) -> None:
        agent = RAGAgent(api_key="")
        state = _make_state()  # no faiss/chroma results, fused = []
        fused_state = RAGAgent.fuse_results(state)
        new_state = agent.generate_answer(fused_state)
        assert "未能" in new_state["answer"] or "抱歉" in new_state["answer"]

    def test_uses_langchain_llm(self) -> None:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这是 LLM 的答案 [1]"
        mock_llm.invoke.return_value = mock_response

        agent = RAGAgent(api_key="", llm=mock_llm)
        state = self._state_with_context()
        new_state = agent.generate_answer(state)
        assert new_state["answer"] == "这是 LLM 的答案 [1]"
        mock_llm.invoke.assert_called_once()

    def test_falls_back_to_api_when_llm_fails(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM error")

        agent = RAGAgent(llm=mock_llm, api_key="fake-key")
        state = self._state_with_context()
        with patch("agents.rag_agent._call_siliconflow_llm", return_value="API 答案") as mock_api:
            new_state = agent.generate_answer(state)
        assert new_state["answer"] == "API 答案"
        mock_api.assert_called_once()

    def test_citations_match_fused_context(self) -> None:
        agent = RAGAgent(api_key="")
        state = self._state_with_context()
        new_state = agent.generate_answer(state)
        assert len(new_state["citations"]) == len(new_state["fused_context"])
        for citation in new_state["citations"]:
            assert "index" in citation
            assert "source" in citation
            assert "doc_id" in citation
            assert "content_snippet" in citation

    def test_appends_assistant_message(self) -> None:
        agent = RAGAgent(api_key="")
        state = self._state_with_context()
        new_state = agent.generate_answer(state)
        roles = [m["role"] for m in new_state["messages"]]
        assert "assistant" in roles


class TestRerankResults:
    def test_skips_when_disabled(self) -> None:
        state = _make_state(faiss_results=[_FAISS_RESULT_1, _FAISS_RESULT_2], use_faiss=True)
        fused_state = RAGAgent.fuse_results(state)
        agent = RAGAgent(api_key="", rerank_api_key="")
        out = agent.rerank_results(fused_state)
        assert out["fused_context_before_rerank"] == fused_state["fused_context"]
        assert out["fused_context"] == fused_state["fused_context"]

    def test_reorders_when_enabled(self) -> None:
        state = _make_state(faiss_results=[_FAISS_RESULT_1, _FAISS_RESULT_2], use_faiss=True)
        state["use_rerank"] = True
        fused_state = RAGAgent.fuse_results(state)
        # 假设 rerank 偏好原索引 1（第二条）
        with patch(
            "agents.rag_agent._call_siliconflow_rerank",
            return_value=[
                {"index": 1, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.88},
            ],
        ):
            agent = RAGAgent(api_key="", rerank_api_key="fake")
            out = agent.rerank_results(fused_state)
        assert out["fused_context_before_rerank"][0]["doc_id"] == "1"
        assert out["fused_context"][0]["doc_id"] == "2"
        assert out["fused_context"][0]["citation_index"] == 1


# ---------------------------------------------------------------------------
# 完整 LangGraph 流程
# ---------------------------------------------------------------------------


class TestRAGGraph:
    def test_graph_compiles(self) -> None:
        graph = create_rag_graph(faiss_searcher=_mock_faiss_searcher)
        assert graph is not None

    def test_run_rag_no_llm(self) -> None:
        result = run_rag(
            "什么是极限？",
            faiss_searcher=_mock_faiss_searcher,
            api_key="",
        )
        assert result["answer"] != ""
        assert isinstance(result["citations"], list)
        assert isinstance(result["recommendations"], list)

    def test_run_rag_with_chroma(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.query.return_value = [_CHROMA_RESULT_1]
        result = run_rag(
            "什么是极限？",
            faiss_searcher=_mock_faiss_searcher,
            chroma_manager=mock_mgr,
            api_key="",
            use_chroma=True,
        )
        assert len(result["fused_context"]) >= 1
        mock_mgr.query.assert_called_once()

    def test_run_rag_empty_faiss(self) -> None:
        result = run_rag(
            "无关问题",
            faiss_searcher=_mock_faiss_searcher_empty,
            api_key="",
        )
        # Should still return a sensible answer (fallback)
        assert isinstance(result["answer"], str)
        assert result["fused_context"] == []

    def test_run_rag_with_langchain_llm(self) -> None:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "极限的定义是 [1]"
        mock_llm.invoke.return_value = mock_response

        result = run_rag(
            "什么是极限？",
            faiss_searcher=_mock_faiss_searcher,
            llm=mock_llm,
            api_key="",
        )
        assert result["answer"] == "极限的定义是 [1]"

    def test_run_rag_messages_preserved(self) -> None:
        history = [{"role": "user", "content": "上一个问题"}]
        result = run_rag(
            "什么是导数？",
            faiss_searcher=_mock_faiss_searcher,
            api_key="",
            messages=history + [{"role": "user", "content": "什么是导数？"}],
        )
        assert any(m["role"] == "user" and "上一个问题" in m["content"] for m in result["messages"])

    def test_run_rag_with_params(self) -> None:
        result = run_rag(
            "什么是极限？",
            faiss_searcher=_mock_faiss_searcher,
            api_key="",
            params={"subject": "数学"},
        )
        assert result["params"].get("subject") == "数学"

    def test_run_rag_chroma_filter(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.query.return_value = []
        run_rag(
            "极限",
            faiss_searcher=_mock_faiss_searcher,
            chroma_manager=mock_mgr,
            api_key="",
            use_chroma=True,
            chroma_filter={"subject": "数学"},
        )
        _, kwargs = mock_mgr.query.call_args
        assert kwargs.get("where") == {"subject": "数学"}
