"""
诊断 Agent 单元测试

完全使用 mock / 临时数据，不依赖外部 API Key，
涵盖以下组件：
  - _compute_knowledge_stats
  - _identify_weak_points
  - _query_questions_by_knowledge_point
  - _query_notes_by_subject
  - DiagnosisAgent 各节点
  - create_diagnosis_graph / run_diagnosis 端到端流程
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from agents.diagnosis_agent import (
    WEAK_THRESHOLD,
    DiagnosisAgent,
    DiagnosisState,
    _compute_knowledge_stats,
    _identify_weak_points,
    _query_notes_by_subject,
    _query_questions_by_knowledge_point,
    create_diagnosis_graph,
    run_diagnosis,
)


# ---------------------------------------------------------------------------
# 共用 Mock 数据
# ---------------------------------------------------------------------------

_MOCK_RECORDS = [
    {"question_id": 1, "subject": "数学", "knowledge_point": "极限", "is_correct": False},
    {"question_id": 2, "subject": "数学", "knowledge_point": "极限", "is_correct": False},
    {"question_id": 3, "subject": "数学", "knowledge_point": "极限", "is_correct": True},
    {"question_id": 4, "subject": "数学", "knowledge_point": "导数", "is_correct": True},
    {"question_id": 5, "subject": "数学", "knowledge_point": "导数", "is_correct": True},
    {"question_id": 6, "subject": "政治", "knowledge_point": "马克思主义", "is_correct": False},
    {"question_id": 7, "subject": "政治", "knowledge_point": "马克思主义", "is_correct": False},
    {"question_id": 8, "subject": "政治", "knowledge_point": "马克思主义", "is_correct": False},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> str:
    """创建临时 SQLite 题库，含少量 mock 题目。"""
    db = str(tmp_path / "test_kb.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY,
            subject TEXT,
            content TEXT,
            knowledge_structure TEXT,
            difficulty_level TEXT,
            correct_answer TEXT,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    rows = [
        (1, "数学", "极限的定义与计算方法", '{"primary": "极限"}', "中等", "A"),
        (2, "数学", "导数计算练习题", '{"primary": "导数"}', "中等", "B"),
        (3, "数学", "极限综合练习", '{"primary": "极限"}', "困难", "C"),
        (4, "政治", "马克思主义基本原理", '{"primary": "马克思主义"}', "中等", "A"),
    ]
    conn.executemany(
        "INSERT INTO questions(id, subject, content, knowledge_structure, difficulty_level, correct_answer) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def tmp_history_json(tmp_path: Path) -> str:
    """创建临时用户历史 JSON 文件。"""
    path = tmp_path / "mock_user_history.json"
    data = {"user_id": "test_user", "records": _MOCK_RECORDS}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture()
def tmp_notes_dir(tmp_path: Path) -> str:
    """创建临时 mock 笔记目录，含两个 Markdown 文件。"""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "math_note.md").write_text(
        "---\nsubject: 数学\ntype: note\n---\n\n# 极限笔记\n极限是微积分的基础。",
        encoding="utf-8",
    )
    (notes_dir / "politics_wrong.md").write_text(
        "---\nsubject: 政治\ntype: wrong\n---\n\n# 错题：马克思主义\n常见错误示例。",
        encoding="utf-8",
    )
    return str(notes_dir)


@pytest.fixture()
def base_state() -> DiagnosisState:
    """返回基础初始状态（使用 mock records）。"""
    return DiagnosisState(
        user_id="test_user",
        subject=None,
        history_records=list(_MOCK_RECORDS),
        knowledge_stats={},
        weak_points=[],
        recommended_questions=[],
        recommended_notes=[],
        report="",
    )


# ---------------------------------------------------------------------------
# _compute_knowledge_stats
# ---------------------------------------------------------------------------


class TestComputeKnowledgeStats:
    def test_basic_accuracy(self) -> None:
        records = [
            {"subject": "数学", "knowledge_point": "极限", "is_correct": True},
            {"subject": "数学", "knowledge_point": "极限", "is_correct": False},
        ]
        stats = _compute_knowledge_stats(records)
        key = "数学::极限"
        assert key in stats
        assert stats[key]["total"] == 2
        assert stats[key]["correct"] == 1
        assert stats[key]["accuracy"] == 0.5

    def test_perfect_accuracy(self) -> None:
        records = [
            {"subject": "英语", "knowledge_point": "阅读", "is_correct": True},
            {"subject": "英语", "knowledge_point": "阅读", "is_correct": True},
        ]
        stats = _compute_knowledge_stats(records)
        assert stats["英语::阅读"]["accuracy"] == 1.0

    def test_zero_accuracy(self) -> None:
        records = [
            {"subject": "数学", "knowledge_point": "积分", "is_correct": False},
            {"subject": "数学", "knowledge_point": "积分", "is_correct": False},
        ]
        stats = _compute_knowledge_stats(records)
        assert stats["数学::积分"]["accuracy"] == 0.0

    def test_empty_records(self) -> None:
        assert _compute_knowledge_stats([]) == {}

    def test_multiple_subjects(self) -> None:
        stats = _compute_knowledge_stats(_MOCK_RECORDS)
        assert "数学::极限" in stats
        assert "数学::导数" in stats
        assert "政治::马克思主义" in stats


# ---------------------------------------------------------------------------
# _identify_weak_points
# ---------------------------------------------------------------------------


class TestIdentifyWeakPoints:
    def test_below_threshold_is_weak(self) -> None:
        stats = {"数学::极限": {"total": 3, "correct": 1, "accuracy": 0.333}}
        weak = _identify_weak_points(stats, threshold=0.6)
        assert len(weak) == 1
        assert weak[0]["knowledge_point"] == "极限"

    def test_above_threshold_not_weak(self) -> None:
        stats = {"数学::导数": {"total": 2, "correct": 2, "accuracy": 1.0}}
        weak = _identify_weak_points(stats, threshold=0.6)
        assert len(weak) == 0

    def test_priority_high(self) -> None:
        stats = {"政治::马克思主义": {"total": 3, "correct": 0, "accuracy": 0.0}}
        weak = _identify_weak_points(stats, threshold=0.6)
        assert weak[0]["priority"] == "高"

    def test_priority_medium(self) -> None:
        stats = {"政治::唯物论": {"total": 5, "correct": 2, "accuracy": 0.4}}
        weak = _identify_weak_points(stats, threshold=0.6)
        assert weak[0]["priority"] == "中"

    def test_sorted_by_accuracy_ascending(self) -> None:
        stats = {
            "数学::积分": {"total": 5, "correct": 2, "accuracy": 0.4},
            "数学::极限": {"total": 3, "correct": 0, "accuracy": 0.0},
        }
        weak = _identify_weak_points(stats, threshold=0.6)
        assert weak[0]["knowledge_point"] == "极限"  # 0.0 < 0.4

    def test_subject_and_kp_parsed_correctly(self) -> None:
        stats = {"英语::写作": {"total": 3, "correct": 1, "accuracy": 0.333}}
        weak = _identify_weak_points(stats, threshold=0.6)
        assert weak[0]["subject"] == "英语"
        assert weak[0]["knowledge_point"] == "写作"


# ---------------------------------------------------------------------------
# _query_questions_by_knowledge_point
# ---------------------------------------------------------------------------


class TestQueryQuestions:
    def test_returns_matching_questions(self, tmp_db: str) -> None:
        results = _query_questions_by_knowledge_point("极限", "数学", n=5, db_path=tmp_db)
        assert len(results) >= 1
        assert all(r["subject"] == "数学" for r in results)

    def test_respects_n_limit(self, tmp_db: str) -> None:
        results = _query_questions_by_knowledge_point("极限", "数学", n=1, db_path=tmp_db)
        assert len(results) <= 1

    def test_missing_db_returns_empty(self) -> None:
        results = _query_questions_by_knowledge_point("极限", "数学", db_path="/nonexistent/path.db")
        assert results == []

    def test_result_fields(self, tmp_db: str) -> None:
        results = _query_questions_by_knowledge_point("极限", "数学", n=1, db_path=tmp_db)
        if results:
            r = results[0]
            for field in ("id", "subject", "knowledge_point", "content"):
                assert field in r


# ---------------------------------------------------------------------------
# _query_notes_by_subject
# ---------------------------------------------------------------------------


class TestQueryNotes:
    def test_returns_math_notes(self, tmp_notes_dir: str) -> None:
        results = _query_notes_by_subject("数学", n=5, mock_notes_dir=tmp_notes_dir)
        assert len(results) >= 1
        assert all(r["subject"] == "数学" for r in results)

    def test_returns_politics_notes(self, tmp_notes_dir: str) -> None:
        results = _query_notes_by_subject("政治", n=5, mock_notes_dir=tmp_notes_dir)
        assert len(results) >= 1

    def test_respects_n_limit(self, tmp_notes_dir: str) -> None:
        results = _query_notes_by_subject("数学", n=1, mock_notes_dir=tmp_notes_dir)
        assert len(results) <= 1

    def test_missing_dir_returns_empty(self) -> None:
        results = _query_notes_by_subject("数学", mock_notes_dir="/nonexistent/dir")
        assert results == []

    def test_note_fields(self, tmp_notes_dir: str) -> None:
        results = _query_notes_by_subject("数学", n=1, mock_notes_dir=tmp_notes_dir)
        if results:
            r = results[0]
            for field in ("doc_id", "subject", "content_snippet", "note_type"):
                assert field in r


# ---------------------------------------------------------------------------
# DiagnosisAgent 节点
# ---------------------------------------------------------------------------


class TestDiagnosisAgentNodes:
    def _make_agent(self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str) -> DiagnosisAgent:
        return DiagnosisAgent(
            weak_threshold=0.6,
            recommend_per_point=2,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
            history_path=tmp_history_json,
        )

    def test_load_history_from_file(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        state = DiagnosisState(
            user_id="test_user",
            subject=None,
            history_records=[],
            knowledge_stats={},
            weak_points=[],
            recommended_questions=[],
            recommended_notes=[],
            report="",
        )
        result = agent.load_history(state)
        assert len(result["history_records"]) > 0

    def test_load_history_skips_if_already_loaded(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        state = DiagnosisState(
            user_id="test_user",
            subject=None,
            history_records=list(_MOCK_RECORDS),
            knowledge_stats={},
            weak_points=[],
            recommended_questions=[],
            recommended_notes=[],
            report="",
        )
        result = agent.load_history(state)
        # 未过滤时记录数量不变
        assert len(result["history_records"]) == len(_MOCK_RECORDS)

    def test_analyze_weak_points_node(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str, base_state: DiagnosisState
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        result = agent.analyze_weak_points(base_state)
        assert "knowledge_stats" in result
        assert len(result["knowledge_stats"]) > 0
        assert "weak_points" in result

    def test_weak_points_detected(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str, base_state: DiagnosisState
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        result = agent.analyze_weak_points(base_state)
        # 政治::马克思主义 全错 → 一定是薄弱点
        weak_kps = [wp["knowledge_point"] for wp in result["weak_points"]]
        assert "马克思主义" in weak_kps

    def test_recommend_resources_node(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str, base_state: DiagnosisState
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        analyzed = agent.analyze_weak_points(base_state)
        result = agent.recommend_resources(analyzed)
        # 至少有笔记推荐（notes 目录存在）
        assert "recommended_notes" in result
        assert "recommended_questions" in result

    def test_generate_report_node(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str, base_state: DiagnosisState
    ) -> None:
        agent = self._make_agent(tmp_db, tmp_notes_dir, tmp_history_json)
        analyzed = agent.analyze_weak_points(base_state)
        recommended = agent.recommend_resources(analyzed)
        result = agent.generate_report(recommended)
        assert result["report"] != ""
        assert "学习诊断报告" in result["report"]
        assert "薄弱点" in result["report"]


# ---------------------------------------------------------------------------
# LangGraph 端到端流程
# ---------------------------------------------------------------------------


class TestDiagnosisGraph:
    def test_graph_compiles(self) -> None:
        graph = create_diagnosis_graph()
        assert graph is not None

    def test_run_diagnosis_with_mock_records(
        self, tmp_db: str, tmp_notes_dir: str
    ) -> None:
        result = run_diagnosis(
            user_id="test_user",
            history_records=_MOCK_RECORDS,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert result["user_id"] == "test_user"
        assert len(result["knowledge_stats"]) > 0
        assert isinstance(result["weak_points"], list)
        assert isinstance(result["recommended_questions"], list)
        assert isinstance(result["recommended_notes"], list)
        assert result["report"] != ""

    def test_run_diagnosis_with_history_file(
        self, tmp_db: str, tmp_notes_dir: str, tmp_history_json: str
    ) -> None:
        result = run_diagnosis(
            user_id="test_user",
            history_path=tmp_history_json,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert len(result["history_records"]) > 0
        assert result["report"] != ""

    def test_report_contains_key_sections(
        self, tmp_db: str, tmp_notes_dir: str
    ) -> None:
        result = run_diagnosis(
            user_id="test_user",
            history_records=_MOCK_RECORDS,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert "掌握程度" in result["report"]
        assert "薄弱点" in result["report"]
        assert "学习建议" in result["report"]

    def test_subject_filter(self, tmp_db: str, tmp_notes_dir: str) -> None:
        """仅分析数学学科时，政治知识点不应出现在 knowledge_stats 中。"""
        result = run_diagnosis(
            user_id="test_user",
            subject="数学",
            history_records=_MOCK_RECORDS,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert all("政治" not in k for k in result["knowledge_stats"])

    def test_no_weak_points_when_all_correct(
        self, tmp_db: str, tmp_notes_dir: str
    ) -> None:
        perfect_records = [
            {"question_id": i, "subject": "数学", "knowledge_point": "积分", "is_correct": True}
            for i in range(5)
        ]
        result = run_diagnosis(
            user_id="test_user",
            history_records=perfect_records,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert result["weak_points"] == []

    def test_custom_weak_threshold(
        self, tmp_db: str, tmp_notes_dir: str
    ) -> None:
        """使用更高阈值时，更多知识点被标记为薄弱。"""
        result_low = run_diagnosis(
            user_id="test_user",
            history_records=_MOCK_RECORDS,
            weak_threshold=0.5,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        result_high = run_diagnosis(
            user_id="test_user",
            history_records=_MOCK_RECORDS,
            weak_threshold=0.9,
            db_path=tmp_db,
            mock_notes_dir=tmp_notes_dir,
        )
        assert len(result_high["weak_points"]) >= len(result_low["weak_points"])

    def test_run_with_default_mock_data(self) -> None:
        """直接使用内置 mock 历史文件（不传 history_records）。"""
        result = run_diagnosis(user_id="user_001")
        # 内置 mock 数据中有薄弱点
        assert len(result["history_records"]) > 0
        assert result["report"] != ""
