"""
Quiz Agent — LangGraph 刷题模式 Student-Teacher Agent

实现：
  - Teacher Agent：自动判题批改、详细解析（结合 analysis 字段与知识点分层）、纠错建议
  - Student Agent：追问生成、自查提示
  - 多轮交互状态管理（QuizState）
  - FAISS 结构化知识库检索（可选）
  - Chroma 动态知识库检索（可选）
  - 底层 LLM 可切换（默认规则降级，可传入 LangChain LLM 实例）

联调：
  - 通过 create_quiz_node() 提供兼容 RouterState 的节点函数供 Router Agent 集成
"""

from __future__ import annotations

import json
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Mock 数据（供测试和链路验证使用）
# ---------------------------------------------------------------------------

MOCK_MATH_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": 1,
        "subject": "数学",
        "year": 2024,
        "question_type": "计算题",
        "content": "求极限 lim(x→0) (sin x)/x 的值。",
        "correct_answer": "1",
        "analysis": (
            "利用重要极限 lim(x→0) sin(x)/x = 1，这是基本极限公式。"
            "注意此处 x→0 但 x≠0，分子分母同趋于 0，属于 0/0 型不定式，"
            "需利用等价无穷小或重要极限直接得出结论。"
        ),
        "knowledge_points": ["极限", "重要极限", "等价无穷小"],
    },
    {
        "id": 2,
        "subject": "数学",
        "year": 2023,
        "question_type": "选择题",
        "content": "函数 f(x) = x² 在 x=0 处的导数是多少？\nA. 0  B. 1  C. 2  D. -1",
        "correct_answer": "A",
        "analysis": (
            "f'(x) = 2x，代入 x=0 得 f'(0) = 0。"
            "导数定义：f'(x₀) = lim(Δx→0) [f(x₀+Δx) - f(x₀)] / Δx。"
        ),
        "knowledge_points": ["导数", "求导法则", "多项式求导"],
    },
    {
        "id": 3,
        "subject": "数学",
        "year": 2024,
        "question_type": "填空题",
        "content": "∫(0→1) x² dx = ___",
        "correct_answer": "1/3",
        "analysis": (
            "∫x² dx = x³/3 + C，故定积分 ∫(0→1) x² dx = [x³/3]₀¹ = 1/3 - 0 = 1/3。"
            "利用牛顿-莱布尼茨公式：∫(a→b) f(x)dx = F(b) - F(a)。"
        ),
        "knowledge_points": ["定积分", "牛顿-莱布尼茨公式", "不定积分"],
    },
]


# ---------------------------------------------------------------------------
# Quiz State
# ---------------------------------------------------------------------------


class QuizState(TypedDict):
    """Quiz Agent 完整状态，兼容 RouterState 共享字段。"""

    # 与 RouterState 共享的字段
    messages: list[dict[str, str]]           # 消息历史
    raw_input: str                           # 当前用户原始输入
    mode: str                                # 当前主模式（"quiz"）
    sub_mode: Optional[str]                  # 子模式：grading / explanation / follow_up
    params: dict[str, Any]                   # 路由参数（subject 等）
    intent_confidence: float                 # 意图置信度
    session_history: list[dict[str, Any]]    # 跨模式会话历史
    multimodal_attachments: list[dict[str, Any]]  # 多模态附件预留

    # Quiz 专属字段
    current_question: Optional[dict[str, Any]]   # 当前题目
    user_answer: Optional[str]                    # 用户答案
    grade_result: Optional[dict[str, Any]]        # 判题结果
    explanation: Optional[str]                    # 详细解析
    followup_questions: list[str]                 # 学生追问列表
    quiz_history: list[dict[str, Any]]            # 多轮刷题历史
    knowledge_context: list[dict[str, Any]]       # FAISS 检索结果
    dynamic_context: list[dict[str, Any]]         # Chroma 检索结果


# ---------------------------------------------------------------------------
# Helper: robust JSON extraction from LLM output
# ---------------------------------------------------------------------------


def _try_parse_json(text: str) -> Optional[dict[str, Any]]:
    """尝试从 LLM 输出中提取 JSON 对象，支持多种格式。

    策略（按优先级）：
    1. 直接解析整个文本
    2. 提取 Markdown 代码块中的 JSON
    3. 使用 json.JSONDecoder.raw_decode 找到第一个完整 JSON 对象
    """
    # Strategy 1: try the whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code block
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find the first valid JSON object using raw_decode
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)

    return None


# ---------------------------------------------------------------------------
# Teacher Agent
# ---------------------------------------------------------------------------


class TeacherAgent:
    """
    Teacher Agent：负责判题批改、详细解析和学习建议。

    Args:
        llm: 可选 LangChain LLM 实例；不传则使用规则降级。
        faiss_search_fn: 可选 FAISS 检索函数，签名 (query: str, top_k: int) -> list[dict]。
        chroma_manager: 可选 ChromaManager 实例，用于动态知识库检索。
    """

    def __init__(
        self,
        llm: Any = None,
        faiss_search_fn: Any = None,
        chroma_manager: Any = None,
    ) -> None:
        self._llm = llm
        self._faiss_search = faiss_search_fn
        self._chroma = chroma_manager

    # --- LangGraph 节点 ---

    def retrieve_context(self, state: QuizState) -> QuizState:
        """从 FAISS 和 Chroma 检索相关知识（可选）。"""
        question = state.get("current_question") or {}
        query = question.get("content", "") or state["raw_input"]

        knowledge_context: list[dict[str, Any]] = []
        dynamic_context: list[dict[str, Any]] = []

        if self._faiss_search and query:
            try:
                knowledge_context = self._faiss_search(query, top_k=3)
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("FAISS retrieval failed: %s", exc)

        if self._chroma and query:
            try:
                dynamic_context = self._chroma.query(query, n_results=3)
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Chroma retrieval failed: %s", exc)

        return {**state, "knowledge_context": knowledge_context, "dynamic_context": dynamic_context}

    def grade_answer(self, state: QuizState) -> QuizState:
        """判题批改节点：将用户答案与参考答案对比，给出评分和反馈。"""
        question = state.get("current_question") or {}
        user_answer = (
            state["user_answer"]
            if state.get("user_answer") is not None
            else state["raw_input"]
        )

        grade_result = self._grade(question, user_answer)
        return {**state, "grade_result": grade_result, "user_answer": user_answer}

    def explain(self, state: QuizState) -> QuizState:
        """详细解析节点：结合 analysis 字段、知识点分层和检索上下文生成解析。"""
        question = state.get("current_question") or {}
        grade_result = state.get("grade_result") or {}
        knowledge_context = state.get("knowledge_context", [])
        dynamic_context = state.get("dynamic_context", [])

        explanation = self._explain(question, grade_result, knowledge_context, dynamic_context)

        messages = list(state.get("messages", []))
        messages.append({"role": "assistant", "content": explanation})

        history = list(state.get("quiz_history", []))
        history.append(
            {
                "question": question,
                "user_answer": state.get("user_answer"),
                "grade_result": grade_result,
                "explanation": explanation,
            }
        )

        return {**state, "explanation": explanation, "messages": messages, "quiz_history": history}

    # --- 内部方法 ---

    def _grade(self, question: dict[str, Any], user_answer: str) -> dict[str, Any]:
        if self._llm is not None:
            result = self._llm_grade(question, user_answer)
            if result is not None:
                return result
        return self._rule_grade(question, user_answer)

    def _rule_grade(self, question: dict[str, Any], user_answer: str) -> dict[str, Any]:
        """基于规则的批改逻辑（LLM 不可用时的降级方案）。"""
        correct_answer = str(question.get("correct_answer", "") or "")
        answer_clean = (user_answer or "").strip()

        if not answer_clean:
            return {"is_correct": False, "score": 0, "feedback": "未提供答案，请补充作答。"}

        if not correct_answer:
            return {"is_correct": None, "score": None, "feedback": "参考答案暂无，需人工批改。"}

        correct_clean = correct_answer.strip()

        # 精确匹配
        if answer_clean == correct_clean:
            return {"is_correct": True, "score": 100, "feedback": "回答正确！"}

        # 大小写不敏感
        if answer_clean.lower() == correct_clean.lower():
            return {"is_correct": True, "score": 100, "feedback": "回答正确！"}

        # 包含匹配（答案包含参考答案）
        if correct_clean in answer_clean:
            return {"is_correct": True, "score": 90, "feedback": "回答基本正确，已包含核心答案。"}

        # 关键词重叠率
        correct_words = set(re.findall(r"[\w\u4e00-\u9fff]+", correct_clean))
        answer_words = set(re.findall(r"[\w\u4e00-\u9fff]+", answer_clean))
        if correct_words:
            overlap = len(correct_words & answer_words)
            ratio = overlap / len(correct_words)
            if ratio >= 0.5:
                score = int(ratio * 80)
                return {
                    "is_correct": False,
                    "score": score,
                    "feedback": f"部分正确，关键词覆盖率 {ratio:.0%}，请补充完整。",
                }

        return {
            "is_correct": False,
            "score": 0,
            "feedback": f"回答不正确。参考答案为：{correct_answer}。",
        }

    def _llm_grade(
        self, question: dict[str, Any], user_answer: str
    ) -> Optional[dict[str, Any]]:
        """LLM 批改（可选增强）；失败时返回 None 让规则降级接管。

        使用 JSON 格式输出，支持语义等价答案识别和部分得分。
        """
        content = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        question_type = question.get("question_type", "")
        prompt = (
            "你是严谨公正的老师，请批改学生答案。\n"
            f"题型：{question_type or '未知题型'}\n"
            f"题目：{content}\n"
            f"参考答案：{correct_answer}\n"
            f"学生答案：{user_answer}\n\n"
            "请以 JSON 格式返回批改结果，不要包含任何其他内容：\n"
            '{"is_correct": true/false, "score": 0-100, "feedback": "详细批改意见"}\n\n'
            "评分规则：\n"
            "- is_correct 为 true 表示答案正确或语义等价，false 表示有明显错误\n"
            "- score 为 0-100 的整数，支持部分得分（答对要点可得部分分）\n"
            "- 语义等价的答案（如同义词、等价表达）应判为正确\n"
            "- feedback 需包含：评分理由、错误点分析（如有）、改进建议"
        )
        try:
            resp = self._llm.invoke(prompt)
            text = getattr(resp, "content", str(resp)).strip()
            # Try JSON parsing with multiple strategies for robustness
            parsed = _try_parse_json(text)
            if parsed is not None:
                is_correct_val = parsed.get("is_correct")
                # JSON booleans come as Python bool; also handle string fallback
                if isinstance(is_correct_val, str):
                    is_correct_val = is_correct_val.lower() in ("true", "是", "正确")
                score_val = parsed.get("score")
                if score_val is not None:
                    try:
                        score_val = int(score_val)
                    except (TypeError, ValueError):
                        score_val = None
                return {
                    "is_correct": bool(is_correct_val) if is_correct_val is not None else None,
                    "score": score_val,
                    "feedback": str(parsed.get("feedback", "")),
                }
            # Fallback to line-based parsing
            result: dict[str, Any] = {"is_correct": None, "score": None, "feedback": ""}
            for line in text.splitlines():
                if line.startswith("是否正确"):
                    val = line.split("：", 1)[-1].strip()
                    result["is_correct"] = val in ("是", "正确", "true", "True")
                elif line.startswith("得分"):
                    m = re.search(r"\d+", line)
                    if m:
                        result["score"] = int(m.group())
                elif line.startswith("批改意见"):
                    result["feedback"] = line.split("：", 1)[-1].strip()
            if not result["feedback"]:
                result["feedback"] = text
            return result
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("LLM grade failed: %s", exc)
            return None

    def _explain(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
        knowledge_context: list[dict[str, Any]],
        dynamic_context: list[dict[str, Any]],
    ) -> str:
        if self._llm is not None:
            result = self._llm_explain(question, grade_result, knowledge_context, dynamic_context)
            if result:
                return result
        return self._rule_explain(question, grade_result, knowledge_context, dynamic_context)

    def _rule_explain(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
        knowledge_context: list[dict[str, Any]],
        dynamic_context: list[dict[str, Any]],
    ) -> str:
        """基于规则的解析生成，结合 analysis 字段和知识点分层。"""
        parts: list[str] = []

        # 批改结果摘要
        feedback = grade_result.get("feedback", "")
        score = grade_result.get("score")
        if score is not None:
            parts.append(f"【批改结果】得分：{score}分。{feedback}")
        elif feedback:
            parts.append(f"【批改结果】{feedback}")

        # 题目解析（analysis 字段）
        analysis = question.get("analysis", "")
        if analysis:
            parts.append(f"【解析】{analysis}")

        # 知识点分层
        kp = question.get("knowledge_points", [])
        if kp:
            parts.append("【涉及知识点】" + "、".join(kp))

        # FAISS 结构化知识库参考
        if knowledge_context:
            snippets = [
                r.get("content", "")[:120]
                for r in knowledge_context[:2]
                if r.get("content")
            ]
            if snippets:
                parts.append("【相关题目参考】\n" + "\n".join(f"- {s}…" for s in snippets))

        # Chroma 动态知识库参考（用户笔记）
        if dynamic_context:
            notes = [
                r.get("document", "")[:120]
                for r in dynamic_context[:2]
                if r.get("document")
            ]
            if notes:
                parts.append("【相关笔记参考】\n" + "\n".join(f"- {n}…" for n in notes))

        if not parts:
            parts.append("【解析】本题已记录，建议复习相关知识点。")

        return "\n\n".join(parts)

    def _llm_explain(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
        knowledge_context: list[dict[str, Any]],
        dynamic_context: list[dict[str, Any]],
    ) -> Optional[str]:
        """LLM 详细解析（可选增强）；失败时返回 None 让规则降级接管。"""
        content = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        analysis = question.get("analysis", "")
        feedback = grade_result.get("feedback", "")
        score = grade_result.get("score")

        ctx_parts: list[str] = []
        if knowledge_context:
            snippets = [
                r.get("content", "")[:200]
                for r in knowledge_context[:3]
                if r.get("content")
            ]
            if snippets:
                ctx_parts.append("相关题目：\n" + "\n".join(snippets))
        if dynamic_context:
            notes = [
                r.get("document", "")[:200]
                for r in dynamic_context[:3]
                if r.get("document")
            ]
            if notes:
                ctx_parts.append("相关笔记：\n" + "\n".join(notes))
        ctx_str = "\n\n".join(ctx_parts)

        prompt = (
            "你是专业辅导老师，请为以下题目给出详细解析和学习建议。\n\n"
            f"题目：{content}\n"
            f"参考答案：{correct_answer}\n"
            f"题目解析：{analysis}\n"
            f"批改意见：{feedback}（得分：{score}）\n"
            + (f"\n参考资料：\n{ctx_str}\n" if ctx_str else "")
            + "\n请给出：\n1. 详细解题思路\n2. 关键知识点\n3. 易错点提醒\n4. 学习建议"
        )
        try:
            resp = self._llm.invoke(prompt)
            return getattr(resp, "content", str(resp)).strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("LLM explain failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Student Agent
# ---------------------------------------------------------------------------


class StudentAgent:
    """
    Student Agent：根据批改结果和解析生成追问，模拟学生的自查行为。

    Args:
        llm: 可选 LangChain LLM 实例；不传则使用规则降级。
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    # --- LangGraph 节点 ---

    def generate_followup(self, state: QuizState) -> QuizState:
        """追问生成节点：根据批改结果和解析生成有针对性的追问。"""
        question = state.get("current_question") or {}
        grade_result = state.get("grade_result") or {}
        explanation = state.get("explanation", "")

        followups = self._gen_followup(question, grade_result, explanation)
        return {**state, "followup_questions": followups}

    # --- 内部方法 ---

    def _gen_followup(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
        explanation: str,
    ) -> list[str]:
        if self._llm is not None:
            result = self._llm_followup(question, grade_result, explanation)
            if result:
                return result
        return self._rule_followup(question, grade_result)

    def _rule_followup(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
    ) -> list[str]:
        """基于规则的追问生成（LLM 不可用时的降级方案）。"""
        is_correct = grade_result.get("is_correct")
        score = grade_result.get("score")
        subject = question.get("subject", "本学科")
        kp_list = question.get("knowledge_points", [])
        kp_str = "、".join(kp_list[:2]) if kp_list else "相关知识点"

        if is_correct is False or (isinstance(score, int) and score < 60):
            return [
                f"请问{kp_str}的核心概念是什么？",
                f"能否再出一道关于{kp_str}的练习题？",
                f"这道{subject}题的完整解题步骤有哪些？",
            ]
        if is_correct is True:
            return [
                "这道题有没有其他解法？",
                f"能否出一道涉及{kp_str}的综合题？",
                "相关的易错题型有哪些？",
            ]
        return [
            f"我对{kp_str}还不太理解，能详细解释吗？",
            "这道题与哪些知识点相关？",
        ]

    def _llm_followup(
        self,
        question: dict[str, Any],
        grade_result: dict[str, Any],
        explanation: str,
    ) -> Optional[list[str]]:
        """LLM 追问生成（可选增强）；失败时返回 None 让规则降级接管。"""
        content = question.get("content", "")
        is_correct = grade_result.get("is_correct")
        status = "正确" if is_correct is True else ("错误" if is_correct is False else "部分正确")
        prompt = (
            "作为学生，请根据老师的解析生成2-3个追问问题，帮助深入理解。\n\n"
            f"题目：{content}\n"
            f"本次结果：{status}\n"
            f"老师解析：{explanation[:500] if explanation else '暂无'}\n\n"
            "请每行输出一个追问，不加序号和前缀。"
        )
        try:
            resp = self._llm.invoke(prompt)
            text = getattr(resp, "content", str(resp)).strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return lines[:3] if lines else None
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("LLM followup failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Quiz Graph 工厂
# ---------------------------------------------------------------------------


def create_quiz_graph(
    llm: Any = None,
    faiss_search_fn: Any = None,
    chroma_manager: Any = None,
) -> Any:
    """
    构建并编译 Quiz Agent 的 LangGraph 工作流。

    Graph 结构：
        START
          │
        retrieve_context  ← 调 FAISS/Chroma（可选）
          │
        grade_answer      ← Teacher：判题批改
          │
        explain           ← Teacher：详细解析 + 历史记录
          │
        student_followup  ← Student：追问生成
          │
        END

    Args:
        llm: 可选 LangChain LLM，不传则规则降级。
        faiss_search_fn: 可选 FAISS 检索函数 (query, top_k) -> list[dict]。
        chroma_manager: 可选 ChromaManager 实例。

    Returns:
        编译后的 CompiledGraph 对象。
    """
    teacher = TeacherAgent(llm=llm, faiss_search_fn=faiss_search_fn, chroma_manager=chroma_manager)
    student = StudentAgent(llm=llm)

    graph: StateGraph = StateGraph(QuizState)

    graph.add_node("retrieve_context", teacher.retrieve_context)
    graph.add_node("grade_answer", teacher.grade_answer)
    graph.add_node("explain", teacher.explain)
    graph.add_node("student_followup", student.generate_followup)

    graph.add_edge(START, "retrieve_context")
    graph.add_edge("retrieve_context", "grade_answer")
    graph.add_edge("grade_answer", "explain")
    graph.add_edge("explain", "student_followup")
    graph.add_edge("student_followup", END)

    return graph.compile()


def create_quiz_node(
    llm: Any = None,
    faiss_search_fn: Any = None,
    chroma_manager: Any = None,
) -> Any:
    """
    创建兼容 RouterState 的 Quiz 节点函数，供 Router Agent 集成使用。

    编译一个内嵌的 Quiz 子图，以 RouterState 字典为输入，
    运行完整的 retrieve → grade → explain → followup 流程后，
    将更新后的消息列表写回 RouterState。

    Returns:
        可直接用于 LangGraph add_node() 的节点函数。
    """
    compiled = create_quiz_graph(
        llm=llm,
        faiss_search_fn=faiss_search_fn,
        chroma_manager=chroma_manager,
    )

    def _quiz_node(state: dict[str, Any]) -> dict[str, Any]:
        quiz_state: QuizState = {
            "messages": list(state.get("messages", [])),
            "raw_input": state.get("raw_input", ""),
            "mode": state.get("mode", "quiz"),
            "sub_mode": state.get("sub_mode"),
            "params": dict(state.get("params", {})),
            "intent_confidence": state.get("intent_confidence", 0.0),
            "session_history": list(state.get("session_history", [])),
            "multimodal_attachments": list(state.get("multimodal_attachments", [])),
            "current_question": state.get("current_question"),
            "user_answer": state.get("user_answer"),
            "grade_result": state.get("grade_result"),
            "explanation": state.get("explanation"),
            "followup_questions": list(state.get("followup_questions", [])),
            "quiz_history": list(state.get("quiz_history", [])),
            "knowledge_context": list(state.get("knowledge_context", [])),
            "dynamic_context": list(state.get("dynamic_context", [])),
        }
        result: QuizState = compiled.invoke(quiz_state)
        return {**state, "messages": result["messages"]}

    _quiz_node.__name__ = "quiz"
    return _quiz_node


# ---------------------------------------------------------------------------
# 便捷调用接口
# ---------------------------------------------------------------------------


def run_quiz(
    user_input: str,
    *,
    llm: Any = None,
    faiss_search_fn: Any = None,
    chroma_manager: Any = None,
    current_question: Optional[dict[str, Any]] = None,
    user_answer: Optional[str] = None,
    messages: Optional[list[dict[str, str]]] = None,
    quiz_history: Optional[list[dict[str, Any]]] = None,
    session_history: Optional[list[dict[str, Any]]] = None,
    params: Optional[dict[str, Any]] = None,
    multimodal_attachments: Optional[list[dict[str, Any]]] = None,
) -> QuizState:
    """
    单次调用 Quiz Agent，返回更新后的状态。

    Args:
        user_input: 当前用户输入（通常为用户答案）。
        llm: 可选 LangChain LLM。
        faiss_search_fn: 可选 FAISS 检索函数 (query, top_k) -> list[dict]。
        chroma_manager: 可选 ChromaManager 实例。
        current_question: 当前题目 dict，含 content/correct_answer/analysis 等字段。
        user_answer: 明确指定的用户答案；默认同 user_input。
        messages: 历史消息列表。
        quiz_history: 历史刷题记录（多轮交互传入）。
        session_history: 历史会话模式记录。
        params: 路由参数（subject/difficulty 等）。
        multimodal_attachments: 多模态附件预留接口。

    Returns:
        更新后的 QuizState，含 grade_result / explanation / followup_questions /
        quiz_history 等字段。
    """
    compiled = create_quiz_graph(
        llm=llm,
        faiss_search_fn=faiss_search_fn,
        chroma_manager=chroma_manager,
    )

    initial: QuizState = {
        "messages": list(messages or [{"role": "user", "content": user_input}]),
        "raw_input": user_input,
        "mode": "quiz",
        "sub_mode": None,
        "params": dict(params or {}),
        "intent_confidence": 1.0,
        "session_history": list(session_history or []),
        "multimodal_attachments": list(multimodal_attachments or []),
        "current_question": current_question,
        "user_answer": user_answer or user_input,
        "grade_result": None,
        "explanation": None,
        "followup_questions": [],
        "quiz_history": list(quiz_history or []),
        "knowledge_context": [],
        "dynamic_context": [],
    }

    result: QuizState = compiled.invoke(initial)
    return result
