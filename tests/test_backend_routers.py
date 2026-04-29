"""
后端新增 API 端点单元测试

测试范围：
  - GET  /health
  - GET  /api/practice/question
  - POST /api/practice
  - POST /api/answer
  - GET  /api/answer/mock
  - POST /api/answer/stream  (SSE 流式)
  - POST /api/practice/stream (SSE 流式)
  - POST /api/auth/register   用户注册
  - POST /api/auth/login      用户登录
  - GET  /api/auth/me         获取当前用户
  - POST /notes/              新增笔记
  - POST /notes/file          从文件新增笔记
  - DELETE /notes/{doc_id}    删除笔记
  - GET  /notes/query         向量相似度检索
  - GET  /notes/count         笔记总数

无需真实 LLM API Key，所有 LLM 相关调用均通过 mock 或降级路径验证。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from backend.config import Settings, get_settings
from backend.main import app
from backend.routers.answer import get_optional_chroma_manager
from backend.routers.notes import get_manager


# ---------------------------------------------------------------------------
# 测试用 Settings 覆盖（不读取 .env，避免 CI 环境依赖）
# ---------------------------------------------------------------------------


def _test_settings() -> Settings:
    return Settings(
        siliconflow_api_key="",
        llm_model="deepseek-ai/DeepSeek-R1",
        llm_base_url="https://api.siliconflow.cn/v1",
        cors_origins=["*"],
        jwt_secret_key="test-secret-key-for-unit-tests-only-do-not-use",
    )


app.dependency_overrides[get_settings] = _test_settings


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


class TestHealth:
    def test_root_ok(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_detail(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ---------------------------------------------------------------------------
# /api/practice
# ---------------------------------------------------------------------------


class TestPractice:
    def test_get_mock_question(self, client: TestClient) -> None:
        resp = client.get("/api/practice/question")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "id" in data
        assert "subject" in data

    def test_practice_submit_answer(self, client: TestClient) -> None:
        # 提交一个正确答案给第一道 mock 题（极限 = 1）
        resp = client.post(
            "/api/practice",
            json={
                "user_input": "1",
                "current_question": {
                    "id": 1,
                    "subject": "数学",
                    "content": "求极限 lim(x→0) (sin x)/x 的值。",
                    "correct_answer": "1",
                    "analysis": "重要极限。",
                    "knowledge_points": ["极限", "等价无穷小"],
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "grade_result" in data
        assert data["grade_result"]["is_correct"] is True
        assert "explanation" in data
        assert "followup_questions" in data
        assert isinstance(data["followup_questions"], list)

    def test_practice_wrong_answer(self, client: TestClient) -> None:
        resp = client.post(
            "/api/practice",
            json={
                "user_input": "0",
                "current_question": {
                    "id": 1,
                    "subject": "数学",
                    "content": "求极限 lim(x→0) (sin x)/x 的值。",
                    "correct_answer": "1",
                    "analysis": "重要极限。",
                    "knowledge_points": ["极限"],
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["grade_result"]["is_correct"] is False

    def test_practice_no_question_uses_mock(self, client: TestClient) -> None:
        """不传 current_question 时，使用默认 mock 题。"""
        resp = client.post("/api/practice", json={"user_input": "1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "grade_result" in data

    def test_practice_stream_returns_sse(self, client: TestClient) -> None:
        resp = client.post(
            "/api/practice/stream",
            json={"user_input": "1"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        content = resp.text
        # 流式响应应包含 meta 事件和 done 事件
        assert "event: meta" in content
        assert "event: done" in content


# ---------------------------------------------------------------------------
# /api/answer
# ---------------------------------------------------------------------------


class TestAnswer:
    def test_answer_mock_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/answer/mock")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert isinstance(data["answer"], str)
        assert "citations" in data
        assert "recommendations" in data
        assert "messages" in data

    def test_answer_post_no_key_fallback(self, client: TestClient) -> None:
        """无 API Key 时应降级为模板答案，不报错。"""
        resp = client.post(
            "/api/answer",
            json={"user_input": "什么是极限？"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    def test_answer_stream_no_key_returns_mock_sse(self, client: TestClient) -> None:
        """无 API Key 时流式端点应返回 mock SSE 演示。"""
        resp = client.post(
            "/api/answer/stream",
            json={"user_input": "极限的定义是什么？"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        content = resp.text
        assert "event: token" in content
        assert "event: done" in content

    def test_answer_with_params(self, client: TestClient) -> None:
        resp = client.post(
            "/api/answer",
            json={
                "user_input": "微积分的基本概念",
                "params": {"subject": "数学"},
                "use_faiss": True,
                "use_chroma": False,
            },
        )
        assert resp.status_code == 200
        assert "answer" in resp.json()

    def test_answer_citations_structure(self, client: TestClient) -> None:
        resp = client.post("/api/answer", json={"user_input": "导数是什么？"})
        assert resp.status_code == 200
        data = resp.json()
        for citation in data["citations"]:
            assert "index" in citation
            assert "source" in citation
            assert "doc_id" in citation


# ---------------------------------------------------------------------------
# 配置管理
# ---------------------------------------------------------------------------


class TestConfig:
    def test_settings_defaults(self) -> None:
        s = _test_settings()
        assert s.llm_model == "deepseek-ai/DeepSeek-R1"
        assert s.embedding_model == "BAAI/bge-m3"
        assert s.llm_base_url == "https://api.siliconflow.cn/v1"
        assert s.siliconflow_api_key == ""
        assert s.log_level == "INFO"
        assert s.cors_origins == ["*"]

    def test_settings_requires_llm_model(self) -> None:
        """未设置 LLM_MODEL 时，Settings 初始化应抛出 ValidationError。"""
        import os

        from pydantic import ValidationError

        saved = os.environ.pop("LLM_MODEL", None)
        try:
            with pytest.raises(ValidationError):
                Settings(siliconflow_api_key="", _env_file=None)
        finally:
            if saved is not None:
                os.environ["LLM_MODEL"] = saved

    def test_settings_api_key_configurable(self) -> None:
        s = Settings(siliconflow_api_key="test-key-123", llm_model="deepseek-ai/DeepSeek-V3")
        assert s.siliconflow_api_key == "test-key-123"

    def test_settings_model_switchable(self) -> None:
        s = Settings(llm_model="Qwen/Qwen2.5-72B-Instruct")
        assert s.llm_model == "Qwen/Qwen2.5-72B-Instruct"


# ---------------------------------------------------------------------------
# /api/auth  ── 认证端点
# ---------------------------------------------------------------------------


class TestAuth:
    """测试 JWT 注册、登录和 /me 端点。"""

    _test_user = {
        "username": f"testuser_{__import__('os').getpid()}",
        "password": "testpass123",
        "display_name": "测试用户",
    }

    def test_register_success(self, client: TestClient) -> None:
        resp = client.post("/api/auth/register", json=self._test_user)
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == self._test_user["username"]
        assert data["display_name"] == self._test_user["display_name"]
        assert isinstance(data["user_id"], int)

    def test_register_duplicate_username(self, client: TestClient) -> None:
        """重复注册同一用户名应返回 409。"""
        resp = client.post("/api/auth/register", json=self._test_user)
        assert resp.status_code == 409
        assert "已存在" in resp.json()["detail"]

    def test_login_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/login",
            json={
                "username": self._test_user["username"],
                "password": self._test_user["password"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == self._test_user["username"]

    def test_login_wrong_password(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/login",
            json={"username": self._test_user["username"], "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/login",
            json={"username": "no_such_user_xyz", "password": "abc123"},
        )
        assert resp.status_code == 401

    def test_me_requires_token(self, client: TestClient) -> None:
        """未携带 Token 时 /me 应返回 401。"""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_valid_token(self, client: TestClient) -> None:
        # 先登录，拿 token
        login_resp = client.post(
            "/api/auth/login",
            json={
                "username": self._test_user["username"],
                "password": self._test_user["password"],
            },
        )
        token = login_resp.json()["access_token"]

        me_resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["username"] == self._test_user["username"]
        assert data["display_name"] == self._test_user["display_name"]
        assert isinstance(data["user_id"], int)

    def test_me_with_invalid_token(self, client: TestClient) -> None:
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401

    def test_demo_user_login(self, client: TestClient) -> None:
        """演示用户 user_001 应能用 exam2024 登录。"""
        resp = client.post(
            "/api/auth/login",
            json={"username": "user_001", "password": "exam2024"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# 笔记管理（notes）— 使用 mock ChromaManager
# ---------------------------------------------------------------------------


def _make_mock_manager() -> MagicMock:
    """构造一个符合 ChromaManager 接口的 MagicMock。"""
    mgr = MagicMock()
    mgr.add_note.return_value = "abcdef1234567890abcdef1234567890"
    mgr.add_note_from_file.return_value = "fedcba0987654321fedcba0987654321"
    mgr.delete_note.return_value = None
    mgr.count.return_value = 2
    mgr.query.return_value = [
        {
            "id": "note_001",
            "document": "极限是微积分的基础概念",
            "metadata": {"subject": "数学", "type": "note"},
            "distance": 0.12,
        }
    ]
    return mgr


class TestNotes:
    """测试 /notes/ 端点（ChromaDB 交互通过 mock ChromaManager 注入）。"""

    @pytest.fixture(autouse=True)
    def inject_mock_manager(self) -> None:
        """在每个测试中用 MagicMock 替换 ChromaManager 依赖。"""
        mock_mgr = _make_mock_manager()
        app.dependency_overrides[get_manager] = lambda: mock_mgr
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_manager, None)

    @pytest.fixture()
    def client(self) -> TestClient:
        return TestClient(app)

    def test_add_note_success(self, client: TestClient) -> None:
        """POST /notes/ 应返回 doc_id 和成功消息。"""
        resp = client.post(
            "/notes/",
            json={"content": "极限是微积分的基础概念。", "metadata": {"subject": "数学"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "doc_id" in data
        assert "message" in data
        assert isinstance(data["doc_id"], str)

    def test_add_note_with_doc_id(self, client: TestClient) -> None:
        """POST /notes/ 指定 doc_id 时，响应中应返回该 doc_id。"""
        mock_mgr = _make_mock_manager()
        mock_mgr.add_note.return_value = "my-custom-doc-id"
        app.dependency_overrides[get_manager] = lambda: mock_mgr

        resp = client.post(
            "/notes/",
            json={"content": "笔记内容", "doc_id": "my-custom-doc-id"},
        )
        assert resp.status_code == 200
        assert resp.json()["doc_id"] == "my-custom-doc-id"

    def test_add_note_missing_content_returns_422(self, client: TestClient) -> None:
        """POST /notes/ 缺少 content 字段时应返回 422。"""
        resp = client.post("/notes/", json={"metadata": {"subject": "数学"}})
        assert resp.status_code == 422

    def test_add_note_from_file_success(self, client: TestClient) -> None:
        """POST /notes/file 应返回 doc_id 和成功消息。"""
        resp = client.post(
            "/notes/file",
            json={"file_path": "mock_notes/math_note.md"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "doc_id" in data
        assert "message" in data

    def test_add_note_from_file_not_found(self, client: TestClient) -> None:
        """POST /notes/file 文件不存在时应返回 404。"""
        mock_mgr = _make_mock_manager()
        mock_mgr.add_note_from_file.side_effect = FileNotFoundError("文件不存在")
        app.dependency_overrides[get_manager] = lambda: mock_mgr

        resp = client.post(
            "/notes/file",
            json={"file_path": "/nonexistent/path.md"},
        )
        assert resp.status_code == 404

    def test_add_note_from_file_embedding_failure(self, client: TestClient) -> None:
        """POST /notes/file 向量化失败时应返回 500。"""
        mock_mgr = _make_mock_manager()
        mock_mgr.add_note_from_file.side_effect = ValueError("API Key 未配置")
        app.dependency_overrides[get_manager] = lambda: mock_mgr

        resp = client.post(
            "/notes/file",
            json={"file_path": "some_note.md"},
        )
        assert resp.status_code == 400

    def test_delete_note_success(self, client: TestClient) -> None:
        """DELETE /notes/{doc_id} 应返回成功消息。"""
        resp = client.delete("/notes/abcdef1234567890abcdef1234567890")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "abcdef1234567890abcdef1234567890" in data["message"]

    def test_delete_note_failure(self, client: TestClient) -> None:
        """DELETE /notes/{doc_id} 失败时应返回 500。"""
        mock_mgr = _make_mock_manager()
        mock_mgr.delete_note.side_effect = RuntimeError("ChromaDB 删除失败")
        app.dependency_overrides[get_manager] = lambda: mock_mgr

        resp = client.delete("/notes/nonexistent-id")
        assert resp.status_code == 500

    def test_query_notes_success(self, client: TestClient) -> None:
        """GET /notes/query 应返回检索结果列表。"""
        resp = client.get("/notes/query?q=极限的定义&n=3")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) == 1
        item = data["results"][0]
        assert "id" in item
        assert "document" in item
        assert "metadata" in item
        assert "distance" in item

    def test_query_notes_with_subject_filter(self, client: TestClient) -> None:
        """GET /notes/query 支持按 subject 参数过滤。"""
        resp = client.get("/notes/query?q=导数&n=5&subject=数学")
        assert resp.status_code == 200
        assert "results" in resp.json()

    def test_query_notes_with_type_filter(self, client: TestClient) -> None:
        """GET /notes/query 支持按 type 参数过滤。"""
        resp = client.get("/notes/query?q=错题&n=5&type=wrong")
        assert resp.status_code == 200
        assert "results" in resp.json()

    def test_query_notes_missing_q_returns_422(self, client: TestClient) -> None:
        """GET /notes/query 缺少 q 参数时应返回 422。"""
        resp = client.get("/notes/query?n=5")
        assert resp.status_code == 422

    def test_query_notes_embedding_failure(self, client: TestClient) -> None:
        """GET /notes/query 向量化失败时应返回 400（ValueError → 400）。"""
        mock_mgr = _make_mock_manager()
        mock_mgr.query.side_effect = ValueError("API Key 未配置")
        app.dependency_overrides[get_manager] = lambda: mock_mgr

        resp = client.get("/notes/query?q=测试查询")
        assert resp.status_code == 400

    def test_count_notes_success(self, client: TestClient) -> None:
        """GET /notes/count 应返回集合中的笔记数量。"""
        resp = client.get("/notes/count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert data["count"] == 2


# ---------------------------------------------------------------------------
# /api/answer with use_chroma=True
# ---------------------------------------------------------------------------


class TestAnswerWithChroma:
    """验证 use_chroma=True 时 ChromaManager 被正确传递给 RAG 流程。"""

    @pytest.fixture(autouse=True)
    def inject_mock_manager(self) -> None:
        """用 MagicMock 替换答案端点的 ChromaManager 依赖。"""
        mock_mgr = _make_mock_manager()
        app.dependency_overrides[get_optional_chroma_manager] = lambda: mock_mgr
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_optional_chroma_manager, None)

    @pytest.fixture()
    def client(self) -> TestClient:
        return TestClient(app)

    def test_answer_with_chroma_enabled(self, client: TestClient) -> None:
        """use_chroma=True 时端点应正常返回，不报错。"""
        resp = client.post(
            "/api/answer",
            json={
                "user_input": "极限的定义是什么？",
                "use_faiss": False,
                "use_chroma": True,
                "n_chroma_results": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0
        assert "citations" in data
        assert "recommendations" in data
        assert "messages" in data

    def test_answer_chroma_results_appear_in_citations(self, client: TestClient) -> None:
        """use_chroma=True 时，Chroma 检索结果应出现在 citations 中。"""
        resp = client.post(
            "/api/answer",
            json={
                "user_input": "极限计算",
                "use_faiss": False,
                "use_chroma": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # 答案中应包含 Chroma 笔记结果（至少有 1 条引用）
        assert len(data["citations"]) >= 1
        sources = [c["source"] for c in data["citations"]]
        assert "chroma" in sources

    def test_answer_chroma_with_filter(self, client: TestClient) -> None:
        """use_chroma=True 带 chroma_filter 时应正常工作。"""
        resp = client.post(
            "/api/answer",
            json={
                "user_input": "数学极限",
                "use_faiss": False,
                "use_chroma": True,
                "chroma_filter": {"subject": "数学"},
            },
        )
        assert resp.status_code == 200
        assert "answer" in resp.json()


# ---------------------------------------------------------------------------
# 数学年份字段 & 统一检索视图测试
# ---------------------------------------------------------------------------


import sqlite3
from pathlib import Path


def _make_test_db(db_path: str) -> None:
    """创建一个最小化的测试用 knowledge_base.db，包含三科样例数据。"""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE subjects (
            subject_code TEXT PRIMARY KEY,
            subject_name TEXT NOT NULL
        );
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT NOT NULL,
            paper_no INTEGER NOT NULL,
            paper_title TEXT
        );
        CREATE TABLE questions_math (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            question_no INTEGER NOT NULL,
            question_type TEXT,
            stem TEXT NOT NULL
        );
        CREATE TABLE questions_politics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            year INTEGER NOT NULL,
            question_type TEXT NOT NULL,
            stem TEXT NOT NULL,
            correct_answer TEXT,
            analysis TEXT,
            difficulty INTEGER,
            score REAL
        );
        CREATE TABLE questions_english (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            question_number INTEGER,
            question_type TEXT NOT NULL,
            content TEXT NOT NULL,
            translation TEXT
        );
        CREATE TABLE sub_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            question_number INTEGER,
            sub_question_number INTEGER,
            stem TEXT,
            answer TEXT,
            analysis TEXT
        );
        CREATE TABLE options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL,
            sub_question_id INTEGER NOT NULL,
            option_key TEXT NOT NULL,
            option_text TEXT NOT NULL
        );

        INSERT INTO subjects VALUES ('math1', '数学(一)');
        INSERT INTO papers VALUES (1, 'math1', 1, '2020年全国硕士研究生招生统一考试数学试题(数一)');
        INSERT INTO papers VALUES (2, 'math1', 2, '2021年全国硕士研究生招生统一考试数学试题(数一)');
        INSERT INTO questions_math VALUES (1, 1, 1, 'single_choice', '2020年题干');
        INSERT INTO questions_math VALUES (2, 2, 1, 'single_choice', '2021年题干');
        INSERT INTO questions_math VALUES (3, 1, 2, 'fill_blank', '2020年填空题');
        INSERT INTO questions_politics VALUES (1, 101, 2020, '单选题', '政治单选题题干', 'A', '解析', 1, 1.0);
        INSERT INTO questions_politics VALUES (2, 102, 2021, '单选题', '政治2021题干', 'B', '解析', 1, 1.0);
        INSERT INTO questions_english VALUES (1, 2020, 2, 'reading', '英语文章内容', NULL);
        INSERT INTO questions_english VALUES (2, 2021, 2, 'reading', '2021英语文章', NULL);

        INSERT INTO sub_questions (subject_type, question_id, stem, answer) VALUES ('math', 1, NULL, 'A');
        INSERT INTO sub_questions (subject_type, question_id, stem, answer) VALUES ('math', 2, NULL, 'B');
        INSERT INTO sub_questions (subject_type, question_id, stem, answer) VALUES ('math', 3, NULL, NULL);
        INSERT INTO options (subject_type, sub_question_id, option_key, option_text) VALUES ('math', 1, 'A', '选项A');
        INSERT INTO options (subject_type, sub_question_id, option_key, option_text) VALUES ('math', 1, 'B', '选项B');
        """
    )
    conn.commit()
    conn.close()


class TestMathYearField:
    """测试数学题年份字段、按年份抽题和统一检索视图。"""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> str:
        """在临时目录创建测试数据库，运行迁移脚本后返回路径。"""
        path = str(tmp_path / "knowledge_base.db")
        _make_test_db(path)

        # 运行迁移脚本
        from datebase.migrate_math_year import migrate
        migrate(path)
        return path

    def test_migration_adds_year_column(self, db_path: str) -> None:
        """迁移后 questions_math 应有 year 列。"""
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(questions_math)")}
        conn.close()
        assert "year" in cols

    def test_migration_backfills_year(self, db_path: str) -> None:
        """迁移后 year 应从 paper_title 正确回填。"""
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT stem, year FROM questions_math ORDER BY id"
        ).fetchall()
        conn.close()
        # 第1、3题来自 2020 年试卷；第2题来自 2021 年试卷
        assert rows[0][1] == 2020, f"期望2020，实际{rows[0][1]}"
        assert rows[1][1] == 2021, f"期望2021，实际{rows[1][1]}"
        assert rows[2][1] == 2020, f"期望2020，实际{rows[2][1]}"

    def test_migration_creates_unified_view(self, db_path: str) -> None:
        """迁移后 v_all_questions 视图应包含三科数据。"""
        conn = sqlite3.connect(db_path)
        views = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        assert "v_all_questions" in views

        subjects = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT subject FROM v_all_questions"
            )
        }
        conn.close()
        assert subjects == {"math", "politics", "english"}

    def test_unified_view_year_column(self, db_path: str) -> None:
        """v_all_questions 中数学题应有正确的年份。"""
        conn = sqlite3.connect(db_path)
        math_rows = conn.execute(
            "SELECT year FROM v_all_questions WHERE subject='math' ORDER BY id"
        ).fetchall()
        conn.close()
        years = [r[0] for r in math_rows]
        assert 2020 in years
        assert 2021 in years

    def test_years_endpoint_math_uses_year_column(self, client: TestClient, db_path: str) -> None:
        """GET /api/practice/years/math 应直接从 questions_math.year 查询。"""
        import backend.routers.practice as practice_mod

        original = practice_mod._DB_PATH
        try:
            practice_mod._DB_PATH = Path(db_path)
            resp = client.get("/api/practice/years/math")
            assert resp.status_code == 200
            years = resp.json()
            assert isinstance(years, list)
            assert 2020 in years
            assert 2021 in years
        finally:
            practice_mod._DB_PATH = original

    def test_question_endpoint_math_year_filter(self, client: TestClient, db_path: str) -> None:
        """GET /api/practice/question?subject=math&year=2020 应只返回2020年题目。"""
        import backend.routers.practice as practice_mod

        original = practice_mod._DB_PATH
        try:
            practice_mod._DB_PATH = Path(db_path)
            resp = client.get("/api/practice/question?subject=math&question_type=single_choice&year=2020")
            assert resp.status_code == 200
            data = resp.json()
            assert data["year"] == 2020
        finally:
            practice_mod._DB_PATH = original

    def test_question_math_year_field_present(self, client: TestClient, db_path: str) -> None:
        """GET /api/practice/question?subject=math 返回的题目应包含 year 字段。"""
        import backend.routers.practice as practice_mod

        original = practice_mod._DB_PATH
        try:
            practice_mod._DB_PATH = Path(db_path)
            resp = client.get("/api/practice/question?subject=math&question_type=single_choice")
            assert resp.status_code == 200
            data = resp.json()
            assert "year" in data
            assert data["year"] in (2020, 2021)
        finally:
            practice_mod._DB_PATH = original

    def test_migration_idempotent(self, db_path: str) -> None:
        """迁移脚本可重复执行而不报错（幂等性）。"""
        from datebase.migrate_math_year import migrate
        migrate(db_path)  # 第二次运行
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(questions_math)")}
        conn.close()
        assert "year" in cols
