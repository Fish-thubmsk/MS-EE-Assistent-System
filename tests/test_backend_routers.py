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

无需真实 LLM API Key，所有 LLM 相关调用均通过 mock 或降级路径验证。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app


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
