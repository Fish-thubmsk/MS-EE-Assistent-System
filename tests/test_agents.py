"""
Tests for the multi-mode Agent workflow.

All LLM calls are mocked so the tests run without an API key.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.messages import AIMessage

from agents import AgentWorkflow
from agents.practice_agent import PracticeAgent
from knowledge_base.static_kb import StaticKnowledgeBase
from knowledge_base.dynamic_kb import DynamicKnowledgeBase
from models.schemas import AgentMode, AgentRequest, Document


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def static_kb(tmp_path):
    kb = StaticKnowledgeBase(
        kb_path=str(tmp_path / "static"),
        embeddings=FakeEmbeddings(size=384),
    )
    kb.add_documents([
        Document(content="导数表示函数在某点的瞬时变化率。", metadata={"subject": "数学"}),
        Document(content="考研英语作文需要积累模板句型。", metadata={"subject": "英语"}),
    ])
    return kb


@pytest.fixture
def dynamic_kb(tmp_path):
    return DynamicKnowledgeBase(db_url=f"sqlite:///{tmp_path}/dynamic.db")


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="这是一个测试回答。")
    return llm


@pytest.fixture
def workflow(mock_llm, static_kb, dynamic_kb):
    return AgentWorkflow(llm=mock_llm, static_kb=static_kb, dynamic_kb=dynamic_kb)


# ---------------------------------------------------------------------------
# AgentWorkflow routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", list(AgentMode))
def test_workflow_routes_all_modes(workflow, mode):
    request = AgentRequest(mode=mode, query="测试问题", subject="数学")
    response = workflow.run(request)
    assert response.mode == mode
    assert isinstance(response.answer, str)
    assert len(response.answer) > 0


def test_workflow_persists_qa_record(workflow, dynamic_kb):
    request = AgentRequest(mode=AgentMode.QA, query="什么是极限？", subject="数学")
    workflow.run(request)
    records = dynamic_kb.get_qa_records(subject="数学")
    assert any(r.question == "什么是极限？" for r in records)


def test_workflow_returns_sources_for_qa(workflow):
    request = AgentRequest(mode=AgentMode.QA, query="导数定义", subject="数学")
    response = workflow.run(request)
    # sources come from static KB retrieval
    assert isinstance(response.sources, list)


def test_workflow_planning_has_no_sources(workflow):
    """Planning agent skips retrieval so sources should be empty."""
    request = AgentRequest(mode=AgentMode.PLANNING, query="制定三个月学习计划")
    response = workflow.run(request)
    assert response.sources == []


# ---------------------------------------------------------------------------
# Practice agent – system prompt switching
# ---------------------------------------------------------------------------

def test_practice_agent_detects_answer(mock_llm, static_kb, dynamic_kb):
    agent = PracticeAgent(mock_llm, static_kb, dynamic_kb)
    request = AgentRequest(mode=AgentMode.PRACTICE, query="我的答案：极限是无穷小量的比值。")
    prompt = agent._system_prompt(request)
    assert "评估" in prompt or "阅卷" in prompt


def test_practice_agent_generates_question(mock_llm, static_kb, dynamic_kb):
    agent = PracticeAgent(mock_llm, static_kb, dynamic_kb)
    request = AgentRequest(mode=AgentMode.PRACTICE, query="微积分极限")
    prompt = agent._system_prompt(request)
    assert "出题" in prompt or "练习题" in prompt


# ---------------------------------------------------------------------------
# Base agent – context and history building
# ---------------------------------------------------------------------------

def test_agent_includes_history_in_messages(workflow, mock_llm):
    history = [
        {"role": "user", "content": "什么是导数？"},
        {"role": "assistant", "content": "导数是函数变化率..."},
    ]
    request = AgentRequest(
        mode=AgentMode.STUDY, query="请举例说明", history=history
    )
    workflow.run(request)
    call_args = mock_llm.invoke.call_args[0][0]
    # Should have system + 2 history + 1 user = 4 messages
    assert len(call_args) == 4
