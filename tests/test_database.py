"""
数据库模块单元测试

覆盖范围：
  - DatabaseManager 的 CRUD 操作（User / QuizRecord / ChatSession / DiagnosisReport）
  - /api/users/* 各端点
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.database.db_manager import DatabaseManager, get_db_manager
from backend.main import app


# ---------------------------------------------------------------------------
# 测试用 Settings 覆盖
# ---------------------------------------------------------------------------


def _test_settings() -> Settings:
    return Settings(
        siliconflow_api_key="",
        llm_model="deepseek-ai/DeepSeek-V3",
        cors_origins=["*"],
        userdata_db_path=":memory:",  # 测试时使用内存数据库
    )


app.dependency_overrides[get_settings] = _test_settings


# ---------------------------------------------------------------------------
# DatabaseManager fixture（每个测试用独立内存 DB）
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> DatabaseManager:
    """返回一个全新的内存数据库管理器，每个测试独立隔离。"""
    return DatabaseManager("sqlite:///:memory:")


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


class TestUserCRUD:
    def test_get_or_create_new_user(self, db: DatabaseManager) -> None:
        user = db.get_or_create_user("alice")
        assert user.user_id == "alice"
        assert user.id is not None

    def test_get_or_create_existing_user(self, db: DatabaseManager) -> None:
        db.get_or_create_user("bob")
        user2 = db.get_or_create_user("bob")
        assert user2.user_id == "bob"
        # 同一用户不会重复创建
        assert db.get_user("bob") is not None

    def test_get_user_not_found(self, db: DatabaseManager) -> None:
        assert db.get_user("nonexistent") is None

    def test_get_user_found(self, db: DatabaseManager) -> None:
        db.get_or_create_user("charlie")
        user = db.get_user("charlie")
        assert user is not None
        assert user.user_id == "charlie"


# ---------------------------------------------------------------------------
# QuizRecord CRUD
# ---------------------------------------------------------------------------


class TestQuizRecordCRUD:
    def test_save_and_retrieve(self, db: DatabaseManager) -> None:
        question = {
            "id": 42,
            "subject": "数学",
            "knowledge_points": ["极限与连续"],
        }
        db.save_quiz_record("alice", question, is_correct=True)
        records = db.get_quiz_records("alice")
        assert len(records) == 1
        assert records[0]["question_id"] == 42
        assert records[0]["subject"] == "数学"
        assert records[0]["knowledge_point"] == "极限与连续"
        assert records[0]["is_correct"] is True

    def test_save_incorrect(self, db: DatabaseManager) -> None:
        db.save_quiz_record("alice", {"id": 1, "subject": "政治"}, is_correct=False)
        records = db.get_quiz_records("alice")
        assert records[0]["is_correct"] is False

    def test_save_none_correct(self, db: DatabaseManager) -> None:
        db.save_quiz_record("alice", {"id": 1, "subject": "英语"}, is_correct=None)
        records = db.get_quiz_records("alice")
        assert records[0]["is_correct"] is None

    def test_subject_filter(self, db: DatabaseManager) -> None:
        db.save_quiz_record("alice", {"id": 1, "subject": "数学"}, is_correct=True)
        db.save_quiz_record("alice", {"id": 2, "subject": "政治"}, is_correct=False)
        math_records = db.get_quiz_records("alice", subject="数学")
        assert len(math_records) == 1
        assert math_records[0]["subject"] == "数学"

    def test_limit_respected(self, db: DatabaseManager) -> None:
        for i in range(10):
            db.save_quiz_record("alice", {"id": i, "subject": "数学"}, is_correct=True)
        records = db.get_quiz_records("alice", limit=5)
        assert len(records) == 5

    def test_with_difficulty(self, db: DatabaseManager) -> None:
        db.save_quiz_record(
            "alice",
            {"id": 1, "subject": "数学"},
            is_correct=True,
            difficulty="困难",
        )
        records = db.get_quiz_records("alice")
        assert records[0]["difficulty"] == "困难"


# ---------------------------------------------------------------------------
# Quiz Stats
# ---------------------------------------------------------------------------


class TestQuizStats:
    def test_empty_stats(self, db: DatabaseManager) -> None:
        stats = db.get_quiz_stats("nobody")
        assert stats["total"] == 0
        assert stats["correct"] == 0
        assert stats["by_subject"] == {}

    def test_stats_calculation(self, db: DatabaseManager) -> None:
        db.save_quiz_record("alice", {"id": 1, "subject": "数学"}, is_correct=True)
        db.save_quiz_record("alice", {"id": 2, "subject": "数学"}, is_correct=False)
        db.save_quiz_record("alice", {"id": 3, "subject": "政治"}, is_correct=True)
        stats = db.get_quiz_stats("alice")
        assert stats["total"] == 3
        assert stats["correct"] == 2
        assert stats["by_subject"]["数学"]["total"] == 2
        assert stats["by_subject"]["数学"]["correct"] == 1
        assert stats["by_subject"]["政治"]["total"] == 1
        assert stats["by_subject"]["政治"]["correct"] == 1


# ---------------------------------------------------------------------------
# ChatSession CRUD
# ---------------------------------------------------------------------------


class TestChatSessionCRUD:
    def test_create_session(self, db: DatabaseManager) -> None:
        session = db.upsert_chat_session("sess-001", "alice", mode="qa", subject="数学")
        assert session.session_id == "sess-001"
        assert session.mode == "qa"

    def test_update_session(self, db: DatabaseManager) -> None:
        db.upsert_chat_session("sess-001", "alice", mode="qa")
        updated = db.upsert_chat_session(
            "sess-001", "alice", mode="quiz", messages=[{"role": "user", "content": "hi"}]
        )
        assert updated.mode == "quiz"

    def test_get_sessions(self, db: DatabaseManager) -> None:
        db.upsert_chat_session("s1", "alice", mode="qa")
        db.upsert_chat_session("s2", "alice", mode="quiz")
        sessions = db.get_chat_sessions("alice")
        assert len(sessions) == 2

    def test_mode_filter(self, db: DatabaseManager) -> None:
        db.upsert_chat_session("s1", "alice", mode="qa")
        db.upsert_chat_session("s2", "alice", mode="quiz")
        qa_sessions = db.get_chat_sessions("alice", mode="qa")
        assert len(qa_sessions) == 1
        assert qa_sessions[0]["mode"] == "qa"


# ---------------------------------------------------------------------------
# DiagnosisReport CRUD
# ---------------------------------------------------------------------------


class TestDiagnosisReportCRUD:
    def test_save_and_retrieve(self, db: DatabaseManager) -> None:
        db.save_diagnosis_report(
            user_id="alice",
            subject="数学",
            weak_points=[{"knowledge_point": "极限", "accuracy": 0.3}],
            recommended_questions=[],
            recommended_notes=[],
            report_text="你在极限方面较弱",
            weak_threshold=0.6,
        )
        reports = db.get_diagnosis_reports("alice")
        assert len(reports) == 1
        assert reports[0]["subject"] == "数学"
        assert reports[0]["report_text"] == "你在极限方面较弱"
        assert reports[0]["weak_points"][0]["knowledge_point"] == "极限"

    def test_subject_filter(self, db: DatabaseManager) -> None:
        db.save_diagnosis_report("alice", "数学", [], [], [], "数学报告", 0.6)
        db.save_diagnosis_report("alice", "政治", [], [], [], "政治报告", 0.6)
        math_reports = db.get_diagnosis_reports("alice", subject="数学")
        assert len(math_reports) == 1
        assert math_reports[0]["subject"] == "数学"

    def test_limit_respected(self, db: DatabaseManager) -> None:
        for i in range(5):
            db.save_diagnosis_report("alice", None, [], [], [], f"报告{i}", 0.6)
        reports = db.get_diagnosis_reports("alice", limit=3)
        assert len(reports) == 3


# ---------------------------------------------------------------------------
# /api/users/* 接口测试（使用内存数据库）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client_with_mem_db() -> TestClient:
    """使用独立内存数据库的测试客户端。"""
    from backend.database import db_manager as _dm

    # 用内存数据库替换全局单例，确保测试隔离
    mem_db = DatabaseManager("sqlite:///:memory:")
    _dm._db_manager = mem_db
    return TestClient(app)


class TestUsersRouter:
    def test_get_or_create_user(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.get("/api/users/test_user_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "test_user_1"

    def test_get_quiz_history_empty(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.get("/api/users/empty_user/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_quiz_stats_empty(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.get("/api/users/empty_user/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["correct"] == 0

    def test_get_sessions_empty(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.get("/api/users/empty_user/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upsert_session(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.post(
            "/api/users/test_user_2/sessions",
            json={"session_id": "sess-abc", "mode": "qa", "subject": "数学"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-abc"
        assert data["mode"] == "qa"

    def test_get_sessions_after_upsert(self, client_with_mem_db: TestClient) -> None:
        client_with_mem_db.post(
            "/api/users/test_user_3/sessions",
            json={"session_id": "sess-xyz", "mode": "quiz"},
        )
        resp = client_with_mem_db.get("/api/users/test_user_3/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) >= 1
        assert sessions[0]["session_id"] == "sess-xyz"

    def test_get_diagnosis_reports_empty(self, client_with_mem_db: TestClient) -> None:
        resp = client_with_mem_db.get("/api/users/empty_user/diagnosis")
        assert resp.status_code == 200
        assert resp.json() == []
