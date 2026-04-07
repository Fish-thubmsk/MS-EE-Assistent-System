"""
诊断模式 Agent — LangGraph 学习诊断工作流

分析用户做题/笔记/错题等行为数据，定位知识薄弱点，生成个性化改进建议及题目推荐。

工作流：
    START
      │
    load_history        ← 优先从 quiz_records 表读取真实做题历史，无数据时 fallback 到 mock JSON
      │
    analyze_weak_points ← Analyzer 子 Agent：统计各知识点准确率，评定薄弱点
      │
    recommend_resources ← Recommender 子 Agent：从 SQLite 题库 + Chroma 笔记推荐资源
      │
    generate_report     ← 汇总并生成结构化学习诊断报告
      │
    END

支持：
  * 真实用户做题记录（通过 /api/practice 提交后持久化到 quiz_records 表）
  * 完全基于 mock 数据运行（DB 无记录时自动 fallback）
  * 薄弱点阈值、推荐数量可配置
  * 可替换为真实用户数据对接（run_diagnosis 接受自定义 history_records）
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量  (env-var overrideable; fall back to CWD-relative defaults)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", os.getcwd()))
# knowledge_base.db — 只读题库（politics/math/english 题目）
_DB_PATH = Path(
    os.path.abspath(
        os.environ.get(
            "KNOWLEDGE_DB_PATH",
            str(_REPO_ROOT / "datebase" / "knowledge_base.db"),
        )
    )
)
# userdata.db — 可读写用户数据（quiz_records 等）
_USERDATA_DB_PATH = Path(
    os.path.abspath(
        os.environ.get(
            "USERDATA_DB_PATH",
            str(_REPO_ROOT / "datebase" / "userdata.db"),
        )
    )
)
_MOCK_HISTORY_PATH = Path(
    os.path.abspath(
        os.environ.get(
            "MOCK_HISTORY_PATH",
            str(_REPO_ROOT / "mock_notes" / "mock_user_history.json"),
        )
    )
)

# 薄弱点判定阈值（准确率低于此值视为薄弱）
WEAK_THRESHOLD: float = 0.6
# 每个薄弱点推荐题目数
RECOMMEND_PER_POINT: int = 3

# ---------------------------------------------------------------------------
# LangGraph 状态定义
# ---------------------------------------------------------------------------


class KnowledgePointStat(TypedDict):
    """单个知识点统计数据。"""

    total: int        # 总作答次数
    correct: int      # 正确次数
    accuracy: float   # 准确率 0.0–1.0


class WeakPoint(TypedDict):
    """薄弱知识点条目。"""

    knowledge_point: str   # 知识点名称
    subject: str           # 所属学科
    accuracy: float        # 准确率
    total_attempts: int    # 总作答次数
    priority: str          # 优先级：高 / 中 / 低


class RecommendedQuestion(TypedDict):
    """推荐题目条目。"""

    id: int
    subject: str
    knowledge_point: str
    content: str
    difficulty_level: Optional[str]
    correct_answer: Optional[str]


class RecommendedNote(TypedDict):
    """推荐笔记/错题条目。"""

    doc_id: str
    subject: str
    content_snippet: str
    note_type: str   # note / wrong


class DiagnosisState(TypedDict):
    """诊断 Agent 的完整 LangGraph 状态。"""

    # 输入
    user_id: str
    subject: Optional[str]             # 可选：限定学科范围

    # 加载阶段
    history_records: list[dict[str, Any]]   # [{question_id, subject, knowledge_point, is_correct, ...}]

    # 分析阶段
    knowledge_stats: dict[str, KnowledgePointStat]  # key = "subject::knowledge_point"
    weak_points: list[WeakPoint]

    # 推荐阶段
    recommended_questions: list[RecommendedQuestion]
    recommended_notes: list[RecommendedNote]

    # 最终报告
    report: str


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _load_db_history(
    user_id: str,
    subject: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    从 userdata.db 的 quiz_records 表读取用户真实做题历史。

    Args:
        user_id: 用户 ID（字符串，对应 user_id_str 列）。
        subject: 可选学科过滤。
        db_path: SQLite 数据库路径（默认使用 _USERDATA_DB_PATH）。

    Returns:
        做题记录列表，表不存在或无记录时返回空列表。
    """
    path = Path(db_path) if db_path else _USERDATA_DB_PATH
    if not path.exists():
        return []
    try:
        # `conditions` contains only hardcoded literal SQL fragments; user values are
        # always bound via parameterised placeholders (`params`) to prevent SQL injection.
        conditions = ["user_id_str = ?"]
        params: list[Any] = [user_id]
        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        where = " AND ".join(conditions)
        with sqlite3.connect(str(path)) as conn:
            cursor = conn.execute(
                f"SELECT question_id, subject, knowledge_point, is_correct, created_at"
                f" FROM quiz_records WHERE {where}",
                params,
            )
            rows = cursor.fetchall()
        return [
            {
                "question_id": r[0],
                "subject": r[1],
                "knowledge_point": r[2],
                "is_correct": bool(r[3]),
                "answered_at": r[4],
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.warning("Failed to load quiz records from DB: %s", exc)
        return []


def _load_mock_history(
    user_id: str,
    subject: Optional[str] = None,
    history_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    从 mock JSON 文件读取用户做题历史。

    Args:
        user_id: 用户 ID（目前 mock 文件仅含单个用户，直接读取）。
        subject: 可选学科过滤。
        history_path: 自定义 JSON 路径（测试时传入临时文件）。

    Returns:
        做题记录列表。
    """
    path = Path(history_path) if history_path else _MOCK_HISTORY_PATH
    if not path.exists():
        logger.warning("Mock history file not found: %s", path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = data.get("records", [])
    if subject:
        records = [r for r in records if r.get("subject") == subject]
    return records


def _compute_knowledge_stats(
    records: list[dict[str, Any]],
) -> dict[str, KnowledgePointStat]:
    """
    按知识点统计答题准确率。

    Returns:
        {"{subject}::{knowledge_point}": KnowledgePointStat}
    """
    stats: dict[str, dict[str, int]] = {}
    for rec in records:
        subject = rec.get("subject", "未知")
        kp = rec.get("knowledge_point", "未知")
        key = f"{subject}::{kp}"
        if key not in stats:
            stats[key] = {"total": 0, "correct": 0}
        stats[key]["total"] += 1
        if rec.get("is_correct"):
            stats[key]["correct"] += 1

    result: dict[str, KnowledgePointStat] = {}
    for key, s in stats.items():
        total = s["total"]
        correct = s["correct"]
        result[key] = KnowledgePointStat(
            total=total,
            correct=correct,
            accuracy=round(correct / total, 4) if total > 0 else 0.0,
        )
    return result


def _identify_weak_points(
    knowledge_stats: dict[str, KnowledgePointStat],
    threshold: float = WEAK_THRESHOLD,
) -> list[WeakPoint]:
    """
    根据准确率阈值识别薄弱知识点，按准确率升序排列。

    优先级规则：
      - 准确率 < 0.4  → 高
      - 0.4 ≤ 准确率 < threshold → 中
      - ≥ threshold  → 低（不计入薄弱点）
    """
    weak: list[WeakPoint] = []
    for key, stat in knowledge_stats.items():
        if stat["accuracy"] >= threshold:
            continue
        parts = key.split("::", 1)
        subject = parts[0] if len(parts) == 2 else "未知"
        kp = parts[1] if len(parts) == 2 else key
        if stat["accuracy"] < 0.4:
            priority = "高"
        else:
            priority = "中"
        weak.append(
            WeakPoint(
                knowledge_point=kp,
                subject=subject,
                accuracy=stat["accuracy"],
                total_attempts=stat["total"],
                priority=priority,
            )
        )
    weak.sort(key=lambda w: (w["accuracy"], -w["total_attempts"]))
    return weak


def _query_questions_by_knowledge_point(
    knowledge_point: str,
    subject: str,
    n: int = RECOMMEND_PER_POINT,
    db_path: Optional[str] = None,
) -> list[RecommendedQuestion]:
    """
    从 SQLite 按知识点关键词搜索相关题目（适配新 7-表规范化 schema）。

    Falls back gracefully if the DB is missing or the query returns nothing.
    """
    path = str(db_path) if db_path else str(_DB_PATH)
    if not os.path.exists(path):
        return []

    # Map UI subject names to table / query logic
    subject_map = {
        "政治": "politics",
        "数学": "math",
        "英语": "english",
    }
    subject_key = subject_map.get(subject, subject.lower())

    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()

        if subject_key == "politics":
            cursor.execute(
                """
                SELECT qp.id, '政治' AS subj, qp.stem, qp.correct_answer
                FROM questions_politics qp
                WHERE qp.stem LIKE ?
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (f"%{knowledge_point}%", n),
            )
        elif subject_key == "math":
            cursor.execute(
                """
                SELECT qm.id, '数学' AS subj, qm.stem, NULL AS correct_answer
                FROM questions_math qm
                WHERE qm.stem LIKE ?
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (f"%{knowledge_point}%", n),
            )
        elif subject_key == "english":
            cursor.execute(
                """
                SELECT qe.id, '英语' AS subj, qe.content, NULL AS correct_answer
                FROM questions_english qe
                WHERE qe.content LIKE ?
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (f"%{knowledge_point}%", n),
            )
        else:
            conn.close()
            return []

        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("DB query failed: %s", exc)
        return []

    results: list[RecommendedQuestion] = []
    for row in rows:
        results.append(
            RecommendedQuestion(
                id=row[0],
                subject=row[1],
                knowledge_point=knowledge_point,
                content=(row[2] or "")[:200],
                difficulty_level=None,
                correct_answer=row[3],
            )
        )
    return results


def _query_notes_by_subject(
    subject: str,
    n: int = 2,
    mock_notes_dir: Optional[str] = None,
) -> list[RecommendedNote]:
    """
    从 mock_notes 目录中读取与学科相关的笔记/错题文件。

    不依赖 Chroma embedding API，直接按 subject frontmatter 过滤。
    """
    import re

    notes_dir = Path(mock_notes_dir) if mock_notes_dir else (_REPO_ROOT / "mock_notes")
    if not notes_dir.exists():
        return []

    results: list[RecommendedNote] = []
    for md_file in sorted(notes_dir.glob("*.md")):
        if len(results) >= n:
            break
        content = md_file.read_text(encoding="utf-8")
        # 解析 frontmatter 中的 subject
        subject_match = re.search(r"^subject:\s*(.+)$", content, re.MULTILINE)
        if not subject_match:
            continue
        file_subject = subject_match.group(1).strip()
        if file_subject != subject:
            continue
        type_match = re.search(r"^type:\s*(.+)$", content, re.MULTILINE)
        note_type = type_match.group(1).strip() if type_match else "note"
        # 取正文片段（去掉 frontmatter）
        body_start = content.find("---\n", 4)
        body = content[body_start + 4:] if body_start != -1 else content
        snippet = body.strip()[:200].replace("\n", " ")
        results.append(
            RecommendedNote(
                doc_id=md_file.stem,
                subject=file_subject,
                content_snippet=snippet,
                note_type=note_type,
            )
        )
    return results


def _generate_report_text(state: DiagnosisState) -> str:
    """根据分析与推荐结果生成结构化学习诊断报告文本。"""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("📊 学习诊断报告")
    lines.append("=" * 60)
    lines.append(f"用户：{state['user_id']}")
    subject_scope = state.get("subject") or "全科"
    lines.append(f"分析范围：{subject_scope}")
    lines.append("")

    # 1. 掌握程度总结
    lines.append("【当前掌握程度总结】")
    stats = state.get("knowledge_stats", {})
    if stats:
        for key, s in sorted(stats.items()):
            acc_str = f"{s['accuracy'] * 100:.1f}%"
            flag = "✅" if s["accuracy"] >= WEAK_THRESHOLD else "⚠️"
            lines.append(f"  {flag} {key}：准确率 {acc_str}（{s['correct']}/{s['total']}）")
    else:
        lines.append("  暂无数据")
    lines.append("")

    # 2. 薄弱点列表
    lines.append("【知识薄弱点列表】")
    weak_points = state.get("weak_points", [])
    if weak_points:
        for wp in weak_points:
            acc_str = f"{wp['accuracy'] * 100:.1f}%"
            lines.append(
                f"  🔴 [{wp['priority']}优先] {wp['subject']} - {wp['knowledge_point']}："
                f"准确率 {acc_str}（{wp['total_attempts']} 次）"
            )
    else:
        lines.append("  👍 未发现明显薄弱点，继续保持！")
    lines.append("")

    # 3. 学习建议 + 推荐题目
    lines.append("【针对性学习建议与推荐题目】")
    questions = state.get("recommended_questions", [])
    notes = state.get("recommended_notes", [])
    if not questions and not notes:
        lines.append("  暂无推荐内容")
    else:
        if questions:
            lines.append("  📝 推荐练习题：")
            for q in questions:
                snippet = q["content"][:80].replace("\n", " ")
                diff = f"[{q['difficulty_level']}]" if q.get("difficulty_level") else ""
                lines.append(f"    • (ID={q['id']}) {q['subject']} {diff} {snippet}…")
        if notes:
            lines.append("  📖 推荐参考笔记/错题：")
            for n in notes:
                lines.append(f"    • [{n['note_type']}] {n['subject']} — {n['content_snippet']}…")
    lines.append("")
    lines.append("=" * 60)
    lines.append("建议：针对高优先级薄弱点，每日专项练习 3–5 道相关题目，")
    lines.append("结合错题笔记反复复习，逐步提升准确率至 70% 以上。")
    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LangGraph 节点函数
# ---------------------------------------------------------------------------


class DiagnosisAgent:
    """
    学习诊断 Agent。

    Attributes:
        weak_threshold: 薄弱点判定准确率阈值（默认 0.6）。
        recommend_per_point: 每个薄弱点推荐题目数（默认 3）。
        db_path: SQLite 题库路径（测试时可覆盖）。
        mock_notes_dir: mock 笔记目录路径（测试时可覆盖）。
        history_path: mock 用户历史 JSON 路径（测试时可覆盖）。
    """

    def __init__(
        self,
        weak_threshold: float = WEAK_THRESHOLD,
        recommend_per_point: int = RECOMMEND_PER_POINT,
        db_path: Optional[str] = None,
        mock_notes_dir: Optional[str] = None,
        history_path: Optional[str] = None,
    ) -> None:
        self.weak_threshold = weak_threshold
        self.recommend_per_point = recommend_per_point
        self.db_path = db_path
        self.mock_notes_dir = mock_notes_dir
        self.history_path = history_path

    # --- 节点 1：加载历史 ---

    def load_history(self, state: DiagnosisState) -> DiagnosisState:
        """读取用户做题历史记录（优先从 DB 读取，无数据时 fallback 到 mock），并按学科过滤。"""
        subject = state.get("subject")
        if state.get("history_records"):
            # 已注入 history_records，仅做学科过滤
            records = state["history_records"]
            if subject:
                records = [r for r in records if r.get("subject") == subject]
            return {**state, "history_records": records}

        # 优先从 quiz_records 表读取真实记录
        records = _load_db_history(
            user_id=state["user_id"],
            subject=subject,
            db_path=self.db_path,
        )

        # DB 无数据时 fallback 到 mock
        if not records:
            records = _load_mock_history(
                user_id=state["user_id"],
                subject=subject,
                history_path=self.history_path,
            )
        return {**state, "history_records": records}

    # --- 节点 2：Analyzer 子 Agent —— 分析薄弱点 ---

    def analyze_weak_points(self, state: DiagnosisState) -> DiagnosisState:
        """
        统计各知识点答题准确率，识别薄弱点。

        Analyzer 子 Agent 职责：
          - 汇总 history_records 中各知识点的作答情况
          - 计算准确率并与阈值比较
          - 输出排序后的 weak_points 列表
        """
        records = state.get("history_records", [])
        knowledge_stats = _compute_knowledge_stats(records)
        weak_points = _identify_weak_points(knowledge_stats, self.weak_threshold)
        return {**state, "knowledge_stats": knowledge_stats, "weak_points": weak_points}

    # --- 节点 3：Recommender 子 Agent —— 推荐资源 ---

    def recommend_resources(self, state: DiagnosisState) -> DiagnosisState:
        """
        基于薄弱知识点，从题库（SQLite）和笔记（mock_notes）推荐学习资源。

        Recommender 子 Agent 职责：
          - 遍历 weak_points，按优先级推荐题目
          - 为相关学科推荐笔记/错题
        """
        weak_points = state.get("weak_points", [])
        all_questions: list[RecommendedQuestion] = []
        seen_ids: set[int] = set()

        for wp in weak_points:
            qs = _query_questions_by_knowledge_point(
                knowledge_point=wp["knowledge_point"],
                subject=wp["subject"],
                n=self.recommend_per_point,
                db_path=self.db_path,
            )
            for q in qs:
                if q["id"] not in seen_ids:
                    all_questions.append(q)
                    seen_ids.add(q["id"])

        # 按涉及学科推荐笔记
        subjects_covered = {wp["subject"] for wp in weak_points}
        all_notes: list[RecommendedNote] = []
        for subj in sorted(subjects_covered):
            notes = _query_notes_by_subject(
                subject=subj,
                n=2,
                mock_notes_dir=self.mock_notes_dir,
            )
            all_notes.extend(notes)

        return {
            **state,
            "recommended_questions": all_questions,
            "recommended_notes": all_notes,
        }

    # --- 节点 4：生成报告 ---

    @staticmethod
    def generate_report(state: DiagnosisState) -> DiagnosisState:
        """汇总分析和推荐结果，生成结构化学习诊断报告。"""
        report = _generate_report_text(state)
        return {**state, "report": report}


# ---------------------------------------------------------------------------
# Graph 工厂
# ---------------------------------------------------------------------------


def create_diagnosis_graph(
    weak_threshold: float = WEAK_THRESHOLD,
    recommend_per_point: int = RECOMMEND_PER_POINT,
    db_path: Optional[str] = None,
    mock_notes_dir: Optional[str] = None,
    history_path: Optional[str] = None,
) -> Any:
    """
    构建并编译诊断 Agent 的 LangGraph 工作流。

    Graph 结构：
        START
          │
        load_history
          │
        analyze_weak_points
          │
        recommend_resources
          │
        generate_report
          │
        END

    Args:
        weak_threshold:      薄弱点准确率阈值（默认 0.6）。
        recommend_per_point: 每个薄弱点推荐题目数（默认 3）。
        db_path:             SQLite 题库路径（测试时传入临时 DB）。
        mock_notes_dir:      mock 笔记目录路径。
        history_path:        mock 用户历史 JSON 路径。

    Returns:
        编译后的 CompiledGraph 对象。
    """
    agent = DiagnosisAgent(
        weak_threshold=weak_threshold,
        recommend_per_point=recommend_per_point,
        db_path=db_path,
        mock_notes_dir=mock_notes_dir,
        history_path=history_path,
    )

    graph = StateGraph(DiagnosisState)

    graph.add_node("load_history", agent.load_history)
    graph.add_node("analyze_weak_points", agent.analyze_weak_points)
    graph.add_node("recommend_resources", agent.recommend_resources)
    graph.add_node("generate_report", agent.generate_report)

    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "analyze_weak_points")
    graph.add_edge("analyze_weak_points", "recommend_resources")
    graph.add_edge("recommend_resources", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 便捷调用接口
# ---------------------------------------------------------------------------


def run_diagnosis(
    user_id: str = "user_001",
    *,
    subject: Optional[str] = None,
    history_records: Optional[list[dict[str, Any]]] = None,
    weak_threshold: float = WEAK_THRESHOLD,
    recommend_per_point: int = RECOMMEND_PER_POINT,
    db_path: Optional[str] = None,
    mock_notes_dir: Optional[str] = None,
    history_path: Optional[str] = None,
) -> DiagnosisState:
    """
    运行完整学习诊断流程，返回最终状态（含诊断报告）。

    Args:
        user_id:             用户 ID。
        subject:             可选学科范围限定。
        history_records:     直接传入做题历史（不从文件读取）。
        weak_threshold:      薄弱点准确率阈值。
        recommend_per_point: 每薄弱点推荐题目数。
        db_path:             SQLite 题库路径（测试时可覆盖）。
        mock_notes_dir:      mock 笔记目录路径。
        history_path:        mock 用户历史 JSON 路径。

    Returns:
        最终 DiagnosisState，包含 report、weak_points、recommended_questions 等字段。
    """
    compiled = create_diagnosis_graph(
        weak_threshold=weak_threshold,
        recommend_per_point=recommend_per_point,
        db_path=db_path,
        mock_notes_dir=mock_notes_dir,
        history_path=history_path,
    )

    initial: DiagnosisState = {
        "user_id": user_id,
        "subject": subject,
        "history_records": list(history_records) if history_records else [],
        "knowledge_stats": {},
        "weak_points": [],
        "recommended_questions": [],
        "recommended_notes": [],
        "report": "",
    }

    result: DiagnosisState = compiled.invoke(initial)
    return result
