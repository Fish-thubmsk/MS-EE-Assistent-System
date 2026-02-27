"""
Quiz Agent 单元测试

无需 LLM API Key，全部使用规则引擎测试。
覆盖：TeacherAgent（批改/解析/检索）、StudentAgent（追问）、
      QuizGraph（图编译）、run_quiz（端到端）、create_quiz_node（Router 集成）。
"""

from __future__ import annotations

import pytest

from agents.quiz_agent import (
    MOCK_MATH_QUESTIONS,
    QuizState,
    StudentAgent,
    TeacherAgent,
    create_quiz_graph,
    create_quiz_node,
    run_quiz,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_quiz_state(**overrides) -> QuizState:
    base: QuizState = {
        "messages": [{"role": "user", "content": "1"}],
        "raw_input": "1",
        "mode": "quiz",
        "sub_mode": "grading",
        "params": {},
        "intent_confidence": 1.0,
        "session_history": [],
        "multimodal_attachments": [],
        "current_question": MOCK_MATH_QUESTIONS[0],
        "user_answer": "1",
        "grade_result": None,
        "explanation": None,
        "followup_questions": [],
        "quiz_history": [],
        "knowledge_context": [],
        "dynamic_context": [],
    }
    base.update(overrides)  # type: ignore[typeddict-unknown-key]
    return base


# ---------------------------------------------------------------------------
# TeacherAgent — 批改（grade_answer）
# ---------------------------------------------------------------------------


class TestTeacherAgentGrade:
    def test_correct_answer_exact_match(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[0]  # correct_answer = "1"
        state = _make_quiz_state(current_question=q, user_answer="1")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is True
        assert result["grade_result"]["score"] == 100

    def test_correct_answer_case_insensitive(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[1]  # correct_answer = "A"
        state = _make_quiz_state(current_question=q, user_answer="a")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is True

    def test_wrong_answer(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[0]
        state = _make_quiz_state(current_question=q, user_answer="0")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is False
        assert result["grade_result"]["score"] == 0

    def test_empty_answer(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[0]
        state = _make_quiz_state(current_question=q, user_answer="")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is False
        assert result["grade_result"]["score"] == 0

    def test_no_correct_answer_in_question(self) -> None:
        teacher = TeacherAgent()
        q = {"id": 99, "content": "自定义题", "subject": "数学"}
        state = _make_quiz_state(current_question=q, user_answer="任意答案")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is None

    def test_partial_contain_match(self) -> None:
        teacher = TeacherAgent()
        q = {"id": 5, "content": "test", "correct_answer": "连续", "subject": "数学"}
        state = _make_quiz_state(current_question=q, user_answer="函数在该点是连续的")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["is_correct"] is True

    def test_state_user_answer_updated(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[1]  # correct_answer = "A"
        state = _make_quiz_state(current_question=q, user_answer="A")
        result = teacher.grade_answer(state)
        assert result["user_answer"] == "A"

    def test_feedback_not_empty(self) -> None:
        teacher = TeacherAgent()
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0], user_answer="1")
        result = teacher.grade_answer(state)
        assert result["grade_result"]["feedback"]


# ---------------------------------------------------------------------------
# TeacherAgent — 解析（explain）
# ---------------------------------------------------------------------------


class TestTeacherAgentExplain:
    def test_explanation_generated(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": True, "score": 100, "feedback": "正确"}
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0], grade_result=grade)
        result = teacher.explain(state)
        assert result["explanation"]
        assert len(result["explanation"]) > 0

    def test_explanation_contains_analysis_field(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[0]  # has "analysis" field
        grade = {"is_correct": True, "score": 100, "feedback": "正确"}
        state = _make_quiz_state(current_question=q, grade_result=grade)
        result = teacher.explain(state)
        assert "解析" in result["explanation"]

    def test_explanation_contains_knowledge_points(self) -> None:
        teacher = TeacherAgent()
        q = MOCK_MATH_QUESTIONS[0]  # has "knowledge_points"
        grade = {"is_correct": False, "score": 0, "feedback": "错误"}
        state = _make_quiz_state(current_question=q, grade_result=grade)
        result = teacher.explain(state)
        assert "知识点" in result["explanation"]

    def test_explanation_appends_assistant_message(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": False, "score": 0, "feedback": "错误"}
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0], grade_result=grade)
        result = teacher.explain(state)
        assistant_msgs = [m for m in result["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1

    def test_quiz_history_appended(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": True, "score": 90, "feedback": "正确"}
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0], grade_result=grade)
        result = teacher.explain(state)
        assert len(result["quiz_history"]) == 1
        assert result["quiz_history"][0]["grade_result"] == grade

    def test_knowledge_context_shown_in_explanation(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": False, "score": 0, "feedback": "错误"}
        ctx = [{"content": "极限的求法示例题", "id": 10}]
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            knowledge_context=ctx,
        )
        result = teacher.explain(state)
        assert "相关题目参考" in result["explanation"]

    def test_dynamic_context_shown_in_explanation(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": False, "score": 0, "feedback": "错误"}
        ctx = [{"document": "极限相关笔记内容", "id": "note-1"}]
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            dynamic_context=ctx,
        )
        result = teacher.explain(state)
        assert "相关笔记参考" in result["explanation"]

    def test_empty_question_does_not_crash(self) -> None:
        teacher = TeacherAgent()
        grade = {"is_correct": None, "score": None, "feedback": "无参考答案"}
        state = _make_quiz_state(current_question={}, grade_result=grade)
        result = teacher.explain(state)
        assert result["explanation"]


# ---------------------------------------------------------------------------
# TeacherAgent — 上下文检索（retrieve_context）
# ---------------------------------------------------------------------------


class TestTeacherAgentContext:
    def test_faiss_search_called_with_question_content(self) -> None:
        calls: list[str] = []

        def fake_faiss(query: str, top_k: int = 3) -> list[dict]:
            calls.append(query)
            return [{"content": "相关题目内容", "id": 1}]

        teacher = TeacherAgent(faiss_search_fn=fake_faiss)
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0])
        result = teacher.retrieve_context(state)
        assert len(calls) == 1
        assert len(result["knowledge_context"]) == 1

    def test_chroma_query_called(self) -> None:
        class FakeChroma:
            def query(self, text: str, n_results: int = 3) -> list[dict]:
                return [{"document": "笔记内容", "id": "abc"}]

        teacher = TeacherAgent(chroma_manager=FakeChroma())
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0])
        result = teacher.retrieve_context(state)
        assert len(result["dynamic_context"]) == 1

    def test_faiss_failure_graceful(self) -> None:
        def failing_faiss(query: str, top_k: int = 3) -> list[dict]:
            raise RuntimeError("Index not found")

        teacher = TeacherAgent(faiss_search_fn=failing_faiss)
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0])
        result = teacher.retrieve_context(state)
        assert result["knowledge_context"] == []

    def test_chroma_failure_graceful(self) -> None:
        class FailingChroma:
            def query(self, text: str, n_results: int = 3) -> list[dict]:
                raise ConnectionError("Chroma unavailable")

        teacher = TeacherAgent(chroma_manager=FailingChroma())
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0])
        result = teacher.retrieve_context(state)
        assert result["dynamic_context"] == []

    def test_no_retrieval_by_default(self) -> None:
        teacher = TeacherAgent()
        state = _make_quiz_state(current_question=MOCK_MATH_QUESTIONS[0])
        result = teacher.retrieve_context(state)
        assert result["knowledge_context"] == []
        assert result["dynamic_context"] == []

    def test_fallback_to_raw_input_when_no_question(self) -> None:
        calls: list[str] = []

        def fake_faiss(query: str, top_k: int = 3) -> list[dict]:
            calls.append(query)
            return []

        teacher = TeacherAgent(faiss_search_fn=fake_faiss)
        state = _make_quiz_state(current_question=None, raw_input="极限计算")
        teacher.retrieve_context(state)
        assert calls[0] == "极限计算"


# ---------------------------------------------------------------------------
# StudentAgent — 追问生成（generate_followup）
# ---------------------------------------------------------------------------


class TestStudentAgent:
    def test_followup_generated_on_wrong_answer(self) -> None:
        student = StudentAgent()
        grade = {"is_correct": False, "score": 0, "feedback": "错误"}
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            explanation="解析内容",
        )
        result = student.generate_followup(state)
        assert len(result["followup_questions"]) > 0

    def test_followup_generated_on_correct_answer(self) -> None:
        student = StudentAgent()
        grade = {"is_correct": True, "score": 100, "feedback": "正确"}
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            explanation="解析内容",
        )
        result = student.generate_followup(state)
        assert len(result["followup_questions"]) > 0

    def test_followup_questions_are_non_empty_strings(self) -> None:
        student = StudentAgent()
        grade = {"is_correct": False, "score": 30, "feedback": "部分"}
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[1],
            grade_result=grade,
            explanation="导数解析",
        )
        result = student.generate_followup(state)
        for q in result["followup_questions"]:
            assert isinstance(q, str)
            assert len(q) > 0

    def test_followup_with_empty_grade(self) -> None:
        student = StudentAgent()
        state = _make_quiz_state(grade_result={}, explanation="")
        result = student.generate_followup(state)
        assert isinstance(result["followup_questions"], list)

    def test_followup_low_score_asks_for_explanation(self) -> None:
        student = StudentAgent()
        grade = {"is_correct": False, "score": 20, "feedback": "错误"}
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            explanation="",
        )
        result = student.generate_followup(state)
        # Low score → student asks for help / retry questions
        questions_text = " ".join(result["followup_questions"])
        assert any(kw in questions_text for kw in ["步骤", "练习", "解题", "概念"])

    def test_followup_correct_suggests_harder_question(self) -> None:
        student = StudentAgent()
        grade = {"is_correct": True, "score": 100, "feedback": "正确"}
        state = _make_quiz_state(
            current_question=MOCK_MATH_QUESTIONS[0],
            grade_result=grade,
            explanation="",
        )
        result = student.generate_followup(state)
        questions_text = " ".join(result["followup_questions"])
        assert any(kw in questions_text for kw in ["解法", "综合", "易错", "题"])


# ---------------------------------------------------------------------------
# Quiz Graph 编译
# ---------------------------------------------------------------------------


class TestQuizGraph:
    def test_graph_compiles(self) -> None:
        graph = create_quiz_graph()
        assert graph is not None

    def test_graph_compiles_with_mock_faiss(self) -> None:
        def mock_faiss(query: str, top_k: int = 3) -> list[dict]:
            return []

        graph = create_quiz_graph(faiss_search_fn=mock_faiss)
        assert graph is not None

    def test_graph_compiles_with_mock_chroma(self) -> None:
        class MockChroma:
            def query(self, text: str, n_results: int = 3) -> list[dict]:
                return []

        graph = create_quiz_graph(chroma_manager=MockChroma())
        assert graph is not None


# ---------------------------------------------------------------------------
# run_quiz — 端到端测试
# ---------------------------------------------------------------------------


class TestRunQuiz:
    def test_basic_run_returns_required_fields(self) -> None:
        result = run_quiz(user_input="1", current_question=MOCK_MATH_QUESTIONS[0])
        assert result["mode"] == "quiz"
        assert result["grade_result"] is not None
        assert result["explanation"] is not None
        assert isinstance(result["followup_questions"], list)

    def test_correct_answer_graded_correctly(self) -> None:
        q = MOCK_MATH_QUESTIONS[0]  # correct_answer = "1"
        result = run_quiz(user_input="1", current_question=q)
        assert result["grade_result"]["is_correct"] is True

    def test_wrong_answer_graded_correctly(self) -> None:
        q = MOCK_MATH_QUESTIONS[0]
        result = run_quiz(user_input="0", current_question=q)
        assert result["grade_result"]["is_correct"] is False

    def test_multiple_choice_correct(self) -> None:
        q = MOCK_MATH_QUESTIONS[1]  # correct_answer = "A"
        result = run_quiz(user_input="A", current_question=q)
        assert result["grade_result"]["is_correct"] is True

    def test_messages_contain_assistant_reply(self) -> None:
        result = run_quiz(user_input="A", current_question=MOCK_MATH_QUESTIONS[1])
        assert any(m["role"] == "assistant" for m in result["messages"])

    def test_quiz_history_has_one_entry_after_first_round(self) -> None:
        result = run_quiz(user_input="1/3", current_question=MOCK_MATH_QUESTIONS[2])
        assert len(result["quiz_history"]) == 1

    def test_multi_round_history_accumulates(self) -> None:
        result1 = run_quiz(user_input="1", current_question=MOCK_MATH_QUESTIONS[0])
        result2 = run_quiz(
            user_input="A",
            current_question=MOCK_MATH_QUESTIONS[1],
            quiz_history=result1["quiz_history"],
        )
        assert len(result2["quiz_history"]) == 2

    def test_params_passed_through(self) -> None:
        result = run_quiz(
            user_input="1",
            current_question=MOCK_MATH_QUESTIONS[0],
            params={"subject": "数学"},
        )
        assert result["params"]["subject"] == "数学"

    def test_no_question_provided_does_not_crash(self) -> None:
        result = run_quiz(user_input="这道题答案是1")
        assert "grade_result" in result
        assert "explanation" in result

    def test_faiss_context_retrieved(self) -> None:
        def mock_faiss(query: str, top_k: int = 3) -> list[dict]:
            return [{"content": "极限计算参考题", "id": 1}]

        result = run_quiz(
            user_input="1",
            current_question=MOCK_MATH_QUESTIONS[0],
            faiss_search_fn=mock_faiss,
        )
        assert len(result["knowledge_context"]) > 0

    def test_chroma_context_retrieved(self) -> None:
        class MockChroma:
            def query(self, text: str, n_results: int = 3) -> list[dict]:
                return [{"document": "极限笔记", "id": "note-1"}]

        result = run_quiz(
            user_input="1",
            current_question=MOCK_MATH_QUESTIONS[0],
            chroma_manager=MockChroma(),
        )
        assert len(result["dynamic_context"]) > 0

    def test_session_history_preserved(self) -> None:
        history = [{"mode": "qa", "sub_mode": None, "params": {}}]
        result = run_quiz(
            user_input="1",
            current_question=MOCK_MATH_QUESTIONS[0],
            session_history=history,
        )
        assert any(h["mode"] == "qa" for h in result["session_history"])

    def test_multimodal_attachments_preserved(self) -> None:
        attachment = {"type": "image", "url": "http://example.com/img.png"}
        result = run_quiz(
            user_input="1",
            current_question=MOCK_MATH_QUESTIONS[0],
            multimodal_attachments=[attachment],
        )
        assert attachment in result["multimodal_attachments"]

    def test_followup_questions_generated_after_wrong(self) -> None:
        result = run_quiz(user_input="wrong", current_question=MOCK_MATH_QUESTIONS[0])
        assert len(result["followup_questions"]) > 0

    def test_followup_questions_generated_after_correct(self) -> None:
        result = run_quiz(user_input="1", current_question=MOCK_MATH_QUESTIONS[0])
        assert len(result["followup_questions"]) > 0


# ---------------------------------------------------------------------------
# create_quiz_node — Router 集成
# ---------------------------------------------------------------------------


class TestCreateQuizNode:
    def test_quiz_node_is_callable(self) -> None:
        node = create_quiz_node()
        assert callable(node)

    def test_quiz_node_runs_with_minimal_router_state(self) -> None:
        node = create_quiz_node()
        router_state = {
            "messages": [{"role": "user", "content": "答案是1"}],
            "raw_input": "答案是1",
            "mode": "quiz",
            "sub_mode": "grading",
            "params": {"subject": "数学"},
            "intent_confidence": 0.9,
            "session_history": [],
            "multimodal_attachments": [],
            "current_question": MOCK_MATH_QUESTIONS[0],
        }
        result = node(router_state)
        assert "messages" in result
        assert any(m["role"] == "assistant" for m in result["messages"])

    def test_quiz_node_preserves_router_mode_and_params(self) -> None:
        node = create_quiz_node()
        router_state = {
            "messages": [{"role": "user", "content": "A"}],
            "raw_input": "A",
            "mode": "quiz",
            "sub_mode": None,
            "params": {"subject": "数学", "difficulty": "中等"},
            "intent_confidence": 0.8,
            "session_history": [{"mode": "qa"}],
            "multimodal_attachments": [],
        }
        result = node(router_state)
        assert result["mode"] == "quiz"
        assert result["params"]["subject"] == "数学"
        assert result["params"]["difficulty"] == "中等"

    def test_quiz_node_preserves_session_history(self) -> None:
        node = create_quiz_node()
        prev_history = [{"mode": "qa", "sub_mode": None, "params": {}}]
        router_state = {
            "messages": [{"role": "user", "content": "1/3"}],
            "raw_input": "1/3",
            "mode": "quiz",
            "sub_mode": None,
            "params": {},
            "intent_confidence": 0.9,
            "session_history": prev_history,
            "multimodal_attachments": [],
        }
        result = node(router_state)
        assert result["session_history"] == prev_history

    def test_quiz_node_with_mock_faiss(self) -> None:
        def mock_faiss(query: str, top_k: int = 3) -> list[dict]:
            return [{"content": "相关题目", "id": 1}]

        node = create_quiz_node(faiss_search_fn=mock_faiss)
        router_state = {
            "messages": [{"role": "user", "content": "1"}],
            "raw_input": "1",
            "mode": "quiz",
            "sub_mode": None,
            "params": {},
            "intent_confidence": 1.0,
            "session_history": [],
            "multimodal_attachments": [],
            "current_question": MOCK_MATH_QUESTIONS[0],
        }
        result = node(router_state)
        assert any(m["role"] == "assistant" for m in result["messages"])
