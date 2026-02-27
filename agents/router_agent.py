"""
Router Agent — LangGraph 意图识别与路由

负责识别用户输入的意图，将请求路由到对应模式：
  - quiz      : 刷题模式（追问 / 批改 / 讲解）
  - qa        : 问答模式（知识点 / 概念 / 融合个人笔记）
  - diagnosis : 诊断模式（学习轨迹 / 弱项分析）

支持：
  * 关键词规则 + LLM 双层识别（LLM 不可用时自动降级为关键词规则）
  * 从输入中提取学科、难度、年份、知识点等参数
  * 独立 session 历史，支持跨轮次模式切换
  * 多模态附件预留接口（images / files 字段）
  * 可扩展模式注册表，方便日后新增子模式
"""

from __future__ import annotations

import re
import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# 枚举：主模式 & 子模式
# ---------------------------------------------------------------------------


class Mode(str, Enum):
    """三种核心主模式。"""

    QUIZ = "quiz"            # 刷题模式
    QA = "qa"                # 问答模式
    DIAGNOSIS = "diagnosis"  # 诊断模式
    UNKNOWN = "unknown"      # 未识别


class QuizSubMode(str, Enum):
    """刷题模式子分类。"""

    FOLLOW_UP = "follow_up"        # 追问
    GRADING = "grading"            # 批改
    EXPLANATION = "explanation"    # 讲解


class QASubMode(str, Enum):
    """问答模式子分类。"""

    KNOWLEDGE = "knowledge"     # 知识点查询
    CONCEPT = "concept"         # 概念解释
    WITH_NOTES = "with_notes"   # 融合个人笔记


class DiagnosisSubMode(str, Enum):
    """诊断模式子分类。"""

    TRAJECTORY = "trajectory"          # 学习轨迹
    WEAK_ANALYSIS = "weak_analysis"    # 弱项分析


# ---------------------------------------------------------------------------
# 可扩展模式注册表
# ---------------------------------------------------------------------------

# 每个条目：{ "mode": Mode, "sub_modes": list[str], "description": str }
MODE_REGISTRY: dict[str, dict[str, Any]] = {
    Mode.QUIZ.value: {
        "mode": Mode.QUIZ.value,
        "sub_modes": [sm.value for sm in QuizSubMode],
        "description": "刷题辅导：追问、批改、讲解",
    },
    Mode.QA.value: {
        "mode": Mode.QA.value,
        "sub_modes": [sm.value for sm in QASubMode],
        "description": "知识问答：知识点、概念、融合笔记",
    },
    Mode.DIAGNOSIS.value: {
        "mode": Mode.DIAGNOSIS.value,
        "sub_modes": [sm.value for sm in DiagnosisSubMode],
        "description": "学习诊断：学习轨迹分析、弱项推荐",
    },
}


def register_mode(
    key: str,
    sub_modes: list[str],
    description: str = "",
) -> None:
    """向注册表动态添加新模式（供日后扩展使用）。"""
    MODE_REGISTRY[key] = {
        "mode": key,
        "sub_modes": sub_modes,
        "description": description,
    }


# ---------------------------------------------------------------------------
# 关键词规则库
# ---------------------------------------------------------------------------

_QUIZ_KEYWORDS = re.compile(
    r"(做题|刷题|练习|题目|解题|判断题|选择题|计算题|推导|证明"
    r"|批改|改错|对不对|错了|讲解|解析|追问|下一题|再来一题"
    r"|第\s*\d+\s*题|题\s*\d+)",
    re.IGNORECASE,
)

_QA_KEYWORDS = re.compile(
    r"(什么是|什么叫|解释一下|定义|概念|原理|怎么理解|为什么"
    r"|如何|怎样|怎么|笔记|知识点|总结|归纳|介绍|说明)",
    re.IGNORECASE,
)

_DIAGNOSIS_KEYWORDS = re.compile(
    r"(诊断|分析|薄弱|弱点|弱项|错题率|学习情况|学习进度"
    r"|学习轨迹|学情|提升建议|哪里不足|提高|改进|复习计划)",
    re.IGNORECASE,
)

# 子模式细分关键词
_QUIZ_FOLLOW_UP_KW = re.compile(r"(追问|继续|再问|接着|上一题|刚才)", re.IGNORECASE)
_QUIZ_GRADING_KW = re.compile(r"(批改|改一下|对不对|错了吗|判断|打分|评分)", re.IGNORECASE)
_QUIZ_EXPLANATION_KW = re.compile(r"(讲解|解析|为什么这样|思路|方法|步骤)", re.IGNORECASE)

_QA_WITH_NOTES_KW = re.compile(r"(笔记|我的记录|我记的|结合|参考我)", re.IGNORECASE)
_QA_CONCEPT_KW = re.compile(r"(概念|定义|什么是|什么叫|解释)", re.IGNORECASE)

_DIAGNOSIS_WEAK_KW = re.compile(r"(薄弱|弱点|弱项|错题|不足|提升|改进)", re.IGNORECASE)

# 参数提取
_SUBJECT_PATTERN = re.compile(
    r"(数学|英语|政治|专业课|物理|化学|生物|历史|地理|语文|计算机|经济)",
    re.IGNORECASE,
)
_DIFFICULTY_PATTERN = re.compile(r"(简单|容易|中等|偏难|难|困难|高难度)", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"(20\d{2}|19\d{2})年?", re.IGNORECASE)
_KNOWLEDGE_POINT_PATTERN = re.compile(
    r"(?:关于|有关|考察|考的是|涉及到?)\s*([^\s，,。！？!?]{2,15})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LangGraph 状态定义
# ---------------------------------------------------------------------------


class RouterParams(TypedDict, total=False):
    """从用户输入中提取的模式相关参数。"""

    subject: Optional[str]          # 学科
    difficulty: Optional[str]       # 难度
    year: Optional[str]             # 年份
    knowledge_point: Optional[str]  # 知识点
    sub_mode: Optional[str]         # 子模式


class RouterState(TypedDict):
    """Router Agent 的完整 LangGraph 状态。"""

    # 当前轮次
    messages: list[dict[str, str]]           # [{"role": "user"|"assistant", "content": "..."}]
    raw_input: str                           # 当前用户原始输入
    mode: str                                # 路由到的主模式
    sub_mode: Optional[str]                  # 路由到的子模式
    params: RouterParams                     # 提取的参数
    intent_confidence: float                 # 意图置信度 0.0–1.0

    # 会话级
    session_history: list[dict[str, Any]]    # 历史轮次快照，用于模式切换

    # 多模态预留接口
    multimodal_attachments: list[dict[str, Any]]  # e.g. [{"type": "image", "url": "..."}]


# ---------------------------------------------------------------------------
# 意图识别 & 参数提取
# ---------------------------------------------------------------------------


def _keyword_classify(text: str) -> tuple[str, Optional[str], float]:
    """
    基于关键词规则识别主模式与子模式。

    Returns:
        (mode, sub_mode, confidence)
    """
    quiz_hits = len(_QUIZ_KEYWORDS.findall(text))
    qa_hits = len(_QA_KEYWORDS.findall(text))
    diagnosis_hits = len(_DIAGNOSIS_KEYWORDS.findall(text))

    total = quiz_hits + qa_hits + diagnosis_hits
    if total == 0:
        return Mode.UNKNOWN, None, 0.0

    scores = {
        Mode.QUIZ: quiz_hits,
        Mode.QA: qa_hits,
        Mode.DIAGNOSIS: diagnosis_hits,
    }
    best_mode = max(scores, key=scores.__getitem__)
    confidence = round(scores[best_mode] / total, 2)

    sub_mode = _detect_sub_mode(text, best_mode)
    return best_mode, sub_mode, confidence


def _detect_sub_mode(text: str, mode: str) -> Optional[str]:
    """根据主模式进一步识别子模式。"""
    if mode == Mode.QUIZ:
        if _QUIZ_FOLLOW_UP_KW.search(text):
            return QuizSubMode.FOLLOW_UP
        if _QUIZ_GRADING_KW.search(text):
            return QuizSubMode.GRADING
        if _QUIZ_EXPLANATION_KW.search(text):
            return QuizSubMode.EXPLANATION
        return QuizSubMode.EXPLANATION  # 默认子模式
    if mode == Mode.QA:
        if _QA_WITH_NOTES_KW.search(text):
            return QASubMode.WITH_NOTES
        if _QA_CONCEPT_KW.search(text):
            return QASubMode.CONCEPT
        return QASubMode.KNOWLEDGE  # 默认子模式
    if mode == Mode.DIAGNOSIS:
        if _DIAGNOSIS_WEAK_KW.search(text):
            return DiagnosisSubMode.WEAK_ANALYSIS
        return DiagnosisSubMode.TRAJECTORY  # 默认子模式
    return None


def _extract_params(text: str) -> RouterParams:
    """从原始文本中提取学科、难度、年份、知识点。"""
    params: RouterParams = {}

    m = _SUBJECT_PATTERN.search(text)
    if m:
        params["subject"] = m.group(1)

    m = _DIFFICULTY_PATTERN.search(text)
    if m:
        params["difficulty"] = m.group(1)

    m = _YEAR_PATTERN.search(text)
    if m:
        params["year"] = m.group(1)

    m = _KNOWLEDGE_POINT_PATTERN.search(text)
    if m:
        params["knowledge_point"] = m.group(1)

    return params


# ---------------------------------------------------------------------------
# LLM 意图分类（可选增强，不可用时自动降级）
# ---------------------------------------------------------------------------

# Prompt 模板
_INTENT_PROMPT_TEMPLATE = """你是一个意图识别助手，帮助识别用户想要进入哪种学习模式。

模式说明：
- quiz（刷题模式）：用户想要做题、练习、批改或讲解题目
- qa（问答模式）：用户想了解某个知识点、概念，或查阅笔记
- diagnosis（诊断模式）：用户想了解自己的学习情况、薄弱项或获得学习建议

仅回答以下之一（小写英文）：quiz / qa / diagnosis / unknown

用户输入：{user_input}
意图："""


def _llm_classify(
    text: str,
    llm: Any,
) -> tuple[str, float]:
    """
    调用 LLM 进行意图分类（可选）。
    返回 (mode, confidence)；失败时返回 (unknown, 0.0)。
    """
    try:
        prompt = _INTENT_PROMPT_TEMPLATE.format(user_input=text)
        response = llm.invoke(prompt)
        # 兼容 langchain Message 对象和普通字符串
        content = getattr(response, "content", str(response)).strip().lower()
        for mode in (Mode.QUIZ, Mode.QA, Mode.DIAGNOSIS):
            if mode.value in content:
                return mode.value, 0.9
    except Exception as exc:  # pylint: disable=broad-except
            logger.debug("LLM intent classification failed: %s", exc)
    return Mode.UNKNOWN, 0.0


# ---------------------------------------------------------------------------
# Router Agent（LangGraph 节点函数）
# ---------------------------------------------------------------------------


class RouterAgent:
    """
    LangGraph Router Agent。

    可选接受一个 LangChain LLM 实例用于增强识别；
    若未提供或调用失败，自动降级为关键词规则识别。
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    # --- LangGraph 节点：意图识别 ---

    def recognize_intent(self, state: RouterState) -> RouterState:
        """解析当前用户输入，更新 mode / sub_mode / params / confidence。"""
        text = state["raw_input"]

        # 1. 关键词规则识别
        kw_mode, kw_sub, kw_conf = _keyword_classify(text)

        # 2. LLM 辅助识别（置信度更高时覆盖关键词结果）
        if self._llm is not None:
            llm_mode, llm_conf = _llm_classify(text, self._llm)
            if llm_conf > kw_conf:
                mode, confidence = llm_mode, llm_conf
                sub_mode = _detect_sub_mode(text, mode)
            else:
                mode, sub_mode, confidence = kw_mode, kw_sub, kw_conf
        else:
            mode, sub_mode, confidence = kw_mode, kw_sub, kw_conf

        # 3. 参数提取
        params = _extract_params(text)
        if sub_mode:
            params["sub_mode"] = sub_mode

        # 4. 更新会话历史快照（保存上一轮的模式）
        history = list(state.get("session_history", []))
        if state.get("mode") and state["mode"] != Mode.UNKNOWN:
            history.append(
                {
                    "mode": state["mode"],
                    "sub_mode": state.get("sub_mode"),
                    "params": state.get("params", {}),
                }
            )

        return {
            **state,
            "mode": mode,
            "sub_mode": sub_mode,
            "params": params,
            "intent_confidence": confidence,
            "session_history": history,
        }

    # --- LangGraph 节点：路由决策 ---

    @staticmethod
    def route(state: RouterState) -> str:
        """
        条件边函数：返回下一节点名称。
        当前实现直接将 mode 作为节点名称；
        未识别时路由到 "unknown"。
        """
        return state["mode"]


# ---------------------------------------------------------------------------
# Graph 工厂
# ---------------------------------------------------------------------------


def _stub_node(mode: str):
    """占位节点（后续替换为真实 Agent）。"""

    def _node(state: RouterState) -> RouterState:
        # 将 assistant 的占位回复追加到消息列表
        messages = list(state.get("messages", []))
        messages.append(
            {
                "role": "assistant",
                "content": f"[{mode} 模式已激活，参数：{state.get('params', {})}]",
            }
        )
        return {**state, "messages": messages}

    _node.__name__ = f"stub_{mode}"
    return _node


def create_router_graph(llm: Any = None) -> Any:
    """
    构建并编译 Router Agent 的 LangGraph 工作流。

    Graph 结构：
        START
          │
        recognize_intent
          │
        ┌─┴──────────────────────────────┐
        quiz         qa         diagnosis  unknown
        │            │              │         │
        END          END           END       END

    Args:
        llm: 可选的 LangChain LLM 实例，用于增强意图识别。

    Returns:
        编译后的 CompiledGraph 对象。
    """
    agent = RouterAgent(llm=llm)

    graph = StateGraph(RouterState)

    # 核心节点
    graph.add_node("recognize_intent", agent.recognize_intent)

    # 各模式占位节点（后续替换为真实工作流）
    for mode in (Mode.QUIZ, Mode.QA, Mode.DIAGNOSIS, Mode.UNKNOWN):
        graph.add_node(mode.value, _stub_node(mode.value))

    # 边
    graph.add_edge(START, "recognize_intent")
    graph.add_conditional_edges(
        "recognize_intent",
        RouterAgent.route,
        {
            Mode.QUIZ.value: Mode.QUIZ.value,
            Mode.QA.value: Mode.QA.value,
            Mode.DIAGNOSIS.value: Mode.DIAGNOSIS.value,
            Mode.UNKNOWN.value: Mode.UNKNOWN.value,
        },
    )

    for mode in (Mode.QUIZ, Mode.QA, Mode.DIAGNOSIS, Mode.UNKNOWN):
        graph.add_edge(mode.value, END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 便捷调用接口
# ---------------------------------------------------------------------------


def run_router(
    user_input: str,
    *,
    llm: Any = None,
    messages: Optional[list[dict[str, str]]] = None,
    session_history: Optional[list[dict[str, Any]]] = None,
    multimodal_attachments: Optional[list[dict[str, Any]]] = None,
) -> RouterState:
    """
    单次调用 Router Agent，返回更新后的状态。

    Args:
        user_input: 当前用户输入文本。
        llm: 可选 LangChain LLM，用于增强识别。
        messages: 历史消息列表。
        session_history: 历史会话模式记录。
        multimodal_attachments: 多模态附件（图片等）预留。

    Returns:
        更新后的 RouterState。
    """
    compiled = create_router_graph(llm=llm)

    initial: RouterState = {
        "messages": list(messages or [{"role": "user", "content": user_input}]),
        "raw_input": user_input,
        "mode": Mode.UNKNOWN.value,
        "sub_mode": None,
        "params": {},
        "intent_confidence": 0.0,
        "session_history": list(session_history or []),
        "multimodal_attachments": list(multimodal_attachments or []),
    }

    result: RouterState = compiled.invoke(initial)
    return result
