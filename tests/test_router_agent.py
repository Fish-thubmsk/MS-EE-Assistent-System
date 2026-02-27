"""
Router Agent 单元测试

无需 LLM API Key，全部使用关键词规则引擎测试。
"""

from __future__ import annotations

import pytest

from agents.router_agent import (
    DiagnosisSubMode,
    Mode,
    QASubMode,
    QuizSubMode,
    RouterAgent,
    RouterState,
    _extract_params,
    _keyword_classify,
    create_router_graph,
    register_mode,
    run_router,
)


# ---------------------------------------------------------------------------
# _keyword_classify
# ---------------------------------------------------------------------------


class TestKeywordClassify:
    def test_quiz_keywords(self) -> None:
        mode, _, conf = _keyword_classify("帮我做一道数学题，需要解题步骤")
        assert mode == Mode.QUIZ
        assert conf > 0

    def test_qa_keywords(self) -> None:
        mode, _, conf = _keyword_classify("什么是极限？请解释一下概念")
        assert mode == Mode.QA
        assert conf > 0

    def test_diagnosis_keywords(self) -> None:
        mode, _, conf = _keyword_classify("分析我的薄弱知识点，给出学习诊断")
        assert mode == Mode.DIAGNOSIS
        assert conf > 0

    def test_unknown_input(self) -> None:
        mode, sub, conf = _keyword_classify("你好")
        assert mode == Mode.UNKNOWN
        assert conf == 0.0
        assert sub is None

    def test_confidence_range(self) -> None:
        _, _, conf = _keyword_classify("做题批改讲解解析")
        assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# 子模式识别
# ---------------------------------------------------------------------------


class TestSubModeDetection:
    def test_quiz_grading(self) -> None:
        _, sub, _ = _keyword_classify("帮我批改这道题，对不对？")
        assert sub == QuizSubMode.GRADING

    def test_quiz_follow_up(self) -> None:
        _, sub, _ = _keyword_classify("针对上一题追问一下")
        assert sub == QuizSubMode.FOLLOW_UP

    def test_quiz_explanation_default(self) -> None:
        _, sub, _ = _keyword_classify("做题，解析一下解题步骤")
        assert sub == QuizSubMode.EXPLANATION

    def test_qa_with_notes(self) -> None:
        _, sub, _ = _keyword_classify("结合我的笔记，解释一下这个知识点")
        assert sub == QASubMode.WITH_NOTES

    def test_qa_concept(self) -> None:
        _, sub, _ = _keyword_classify("什么是导数的定义？")
        assert sub == QASubMode.CONCEPT

    def test_qa_knowledge_default(self) -> None:
        _, sub, _ = _keyword_classify("如何理解微积分的应用？")
        assert sub == QASubMode.KNOWLEDGE

    def test_diagnosis_weak_analysis(self) -> None:
        _, sub, _ = _keyword_classify("分析我的弱项，哪些知识点不足")
        assert sub == DiagnosisSubMode.WEAK_ANALYSIS

    def test_diagnosis_trajectory_default(self) -> None:
        _, sub, _ = _keyword_classify("查看我的学习轨迹和学情")
        assert sub == DiagnosisSubMode.TRAJECTORY


# ---------------------------------------------------------------------------
# 参数提取
# ---------------------------------------------------------------------------


class TestExtractParams:
    def test_subject_extraction(self) -> None:
        params = _extract_params("请给我一道数学题")
        assert params.get("subject") == "数学"

    def test_difficulty_extraction(self) -> None:
        params = _extract_params("来一道中等难度的题目")
        assert params.get("difficulty") == "中等"

    def test_year_extraction(self) -> None:
        params = _extract_params("2023年的真题解析")
        assert params.get("year") == "2023"

    def test_knowledge_point_extraction(self) -> None:
        params = _extract_params("关于极限定义的知识点")
        assert params.get("knowledge_point") is not None

    def test_no_params(self) -> None:
        params = _extract_params("你好，请帮助我")
        assert params == {}

    def test_multiple_params(self) -> None:
        params = _extract_params("2022年数学困难题目")
        assert params.get("subject") == "数学"
        assert params.get("year") == "2022"
        assert params.get("difficulty") == "困难"


# ---------------------------------------------------------------------------
# RouterAgent 节点
# ---------------------------------------------------------------------------


class TestRouterAgentNode:
    def _make_state(self, user_input: str) -> RouterState:
        return RouterState(
            messages=[{"role": "user", "content": user_input}],
            raw_input=user_input,
            mode=Mode.UNKNOWN.value,
            sub_mode=None,
            params={},
            intent_confidence=0.0,
            session_history=[],
            multimodal_attachments=[],
        )

    def test_recognize_intent_quiz(self) -> None:
        agent = RouterAgent()
        state = self._make_state("帮我做一道计算题")
        new_state = agent.recognize_intent(state)
        assert new_state["mode"] == Mode.QUIZ
        assert new_state["intent_confidence"] > 0

    def test_recognize_intent_qa(self) -> None:
        agent = RouterAgent()
        state = self._make_state("什么是极限的定义？")
        new_state = agent.recognize_intent(state)
        assert new_state["mode"] == Mode.QA

    def test_recognize_intent_diagnosis(self) -> None:
        agent = RouterAgent()
        state = self._make_state("帮我诊断学习薄弱点")
        new_state = agent.recognize_intent(state)
        assert new_state["mode"] == Mode.DIAGNOSIS

    def test_sub_mode_in_params(self) -> None:
        agent = RouterAgent()
        state = self._make_state("批改这道题对不对")
        new_state = agent.recognize_intent(state)
        assert new_state["params"].get("sub_mode") == QuizSubMode.GRADING

    def test_session_history_updated_on_mode_switch(self) -> None:
        agent = RouterAgent()
        # 第一轮：quiz
        state = RouterState(
            messages=[{"role": "user", "content": "做题"}],
            raw_input="做题",
            mode=Mode.QUIZ.value,
            sub_mode=QuizSubMode.EXPLANATION.value,
            params={},
            intent_confidence=0.8,
            session_history=[],
            multimodal_attachments=[],
        )
        # 第二轮：qa（模式切换）
        state["raw_input"] = "什么是极限？"
        new_state = agent.recognize_intent(state)
        # 历史中保存了上一轮的 quiz
        assert any(h["mode"] == Mode.QUIZ for h in new_state["session_history"])

    def test_route_function_returns_mode(self) -> None:
        state = RouterState(
            messages=[],
            raw_input="",
            mode=Mode.QA.value,
            sub_mode=None,
            params={},
            intent_confidence=0.5,
            session_history=[],
            multimodal_attachments=[],
        )
        assert RouterAgent.route(state) == Mode.QA.value


# ---------------------------------------------------------------------------
# LangGraph 完整流程
# ---------------------------------------------------------------------------


class TestRouterGraph:
    def test_graph_compiles(self) -> None:
        graph = create_router_graph()
        assert graph is not None

    def test_run_quiz_mode(self) -> None:
        result = run_router("帮我出一道数学计算题")
        assert result["mode"] == Mode.QUIZ
        assert result["params"].get("subject") == "数学"

    def test_run_qa_mode(self) -> None:
        result = run_router("什么是极限？请解释定义")
        assert result["mode"] == Mode.QA

    def test_run_diagnosis_mode(self) -> None:
        result = run_router("分析我最近的学习薄弱点")
        assert result["mode"] == Mode.DIAGNOSIS

    def test_run_unknown_mode(self) -> None:
        result = run_router("你好")
        assert result["mode"] == Mode.UNKNOWN
        assert result["intent_confidence"] == 0.0

    def test_messages_contain_assistant_reply(self) -> None:
        result = run_router("做一道英语题目")
        assert any(m["role"] == "assistant" for m in result["messages"])

    def test_multimodal_attachments_preserved(self) -> None:
        attachment = {"type": "image", "url": "http://example.com/img.png"}
        result = run_router(
            "这道题怎么解",
            multimodal_attachments=[attachment],
        )
        assert attachment in result["multimodal_attachments"]

    def test_session_history_passed_through(self) -> None:
        history = [{"mode": Mode.QA.value, "sub_mode": None, "params": {}}]
        result = run_router("做一道数学题", session_history=history)
        # 传入的历史被保留（新一轮的历史可能追加条目）
        assert any(h["mode"] == Mode.QA.value for h in result["session_history"])


# ---------------------------------------------------------------------------
# 可扩展模式注册表
# ---------------------------------------------------------------------------


class TestModeRegistry:
    def test_register_new_mode(self) -> None:
        register_mode("writing", ["draft", "review"], "写作辅助模式")
        from agents.router_agent import MODE_REGISTRY

        assert "writing" in MODE_REGISTRY
        assert MODE_REGISTRY["writing"]["sub_modes"] == ["draft", "review"]

    def test_existing_modes_present(self) -> None:
        from agents.router_agent import MODE_REGISTRY

        for mode in (Mode.QUIZ, Mode.QA, Mode.DIAGNOSIS):
            assert mode.value in MODE_REGISTRY
