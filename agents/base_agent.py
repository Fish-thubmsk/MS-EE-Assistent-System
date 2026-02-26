"""
Base Agent
==========
Abstract base class that every concrete agent inherits from.  Each agent
shares access to both knowledge bases and is given a callable LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from knowledge_base.static_kb import StaticKnowledgeBase
from knowledge_base.dynamic_kb import DynamicKnowledgeBase
from models.schemas import AgentRequest, AgentResponse, SearchResult


class BaseAgent(ABC):
    """Shared infrastructure for all agent modes."""

    mode_name: str = "base"

    def __init__(
        self,
        llm: BaseChatModel,
        static_kb: StaticKnowledgeBase,
        dynamic_kb: DynamicKnowledgeBase,
    ) -> None:
        self._llm = llm
        self._static_kb = static_kb
        self._dynamic_kb = dynamic_kb

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent and return a structured response."""
        sources = self._retrieve(request)
        context = self._build_context(sources)
        messages = self._build_messages(request, context)
        ai_msg = self._llm.invoke(messages)
        answer = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
        return AgentResponse(
            mode=request.mode,
            answer=answer,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # Hooks that subclasses override
    # ------------------------------------------------------------------

    def _retrieve(self, request: AgentRequest) -> List[SearchResult]:
        """Retrieve relevant documents from both knowledge bases."""
        query = request.query
        if request.subject:
            query = f"{request.subject} {query}"
        return self._static_kb.search(query)

    @abstractmethod
    def _system_prompt(self, request: AgentRequest) -> str:
        """Return the system prompt for this agent mode."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, sources: List[SearchResult]) -> str:
        if not sources:
            return ""
        snippets = [f"[{i+1}] {s.document.content}" for i, s in enumerate(sources)]
        return "\n\n".join(snippets)

    def _build_messages(self, request: AgentRequest, context: str) -> list:
        system_content = self._system_prompt(request)
        if context:
            system_content += f"\n\n以下是相关知识库内容，请参考：\n{context}"
        messages: list = [SystemMessage(content=system_content)]
        for turn in request.history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=request.query))
        return messages
