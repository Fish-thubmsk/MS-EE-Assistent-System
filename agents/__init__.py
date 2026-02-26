"""
Agent factory & workflow orchestrator.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from config import settings
from knowledge_base.static_kb import StaticKnowledgeBase
from knowledge_base.dynamic_kb import DynamicKnowledgeBase
from agents.base_agent import BaseAgent
from agents.qa_agent import QAAgent
from agents.study_agent import StudyAgent
from agents.practice_agent import PracticeAgent
from agents.planning_agent import PlanningAgent
from models.schemas import AgentMode, AgentRequest, AgentResponse, QARecordCreate


_AGENT_MAP: dict[AgentMode, type[BaseAgent]] = {
    AgentMode.QA: QAAgent,
    AgentMode.STUDY: StudyAgent,
    AgentMode.PRACTICE: PracticeAgent,
    AgentMode.PLANNING: PlanningAgent,
}


class AgentWorkflow:
    """
    Multi-mode agent workflow that routes a request to the appropriate agent.

    Instances are long-lived (created once per application lifetime) and
    share the same knowledge-base handles and LLM client.
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        static_kb: StaticKnowledgeBase | None = None,
        dynamic_kb: DynamicKnowledgeBase | None = None,
    ) -> None:
        self._llm = llm or ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.openai_api_key,
            openai_api_base=settings.openai_api_base,
        )
        self._static_kb = static_kb or StaticKnowledgeBase()
        self._dynamic_kb = dynamic_kb or DynamicKnowledgeBase()

        # Instantiate all agents once; they are stateless.
        self._agents: dict[AgentMode, BaseAgent] = {
            mode: cls(self._llm, self._static_kb, self._dynamic_kb)
            for mode, cls in _AGENT_MAP.items()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, request: AgentRequest) -> AgentResponse:
        """Route *request* to the correct agent and persist the record."""
        agent = self._agents[request.mode]
        response = agent.run(request)
        # Persist to dynamic KB for review / personalisation
        self._dynamic_kb.add_qa_record(
            QARecordCreate(
                question=request.query,
                answer=response.answer,
                mode=request.mode,
                subject=request.subject,
            )
        )
        return response

    @property
    def static_kb(self) -> StaticKnowledgeBase:
        return self._static_kb

    @property
    def dynamic_kb(self) -> DynamicKnowledgeBase:
        return self._dynamic_kb
