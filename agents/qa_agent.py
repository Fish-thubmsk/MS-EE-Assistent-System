"""
Q&A Agent  (问答模式)
====================
Directly answers subject-matter questions using RAG over the knowledge bases.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from models.schemas import AgentRequest


class QAAgent(BaseAgent):
    mode_name = "qa"

    def _system_prompt(self, request: AgentRequest) -> str:
        subject = request.subject or "考研相关科目"
        return (
            f"你是一位专业的考研辅导老师，专注于{subject}。\n"
            "请根据问题以及提供的知识库内容，给出准确、简洁的解答。\n"
            "如果知识库中没有相关内容，请依据你的专业知识作答，并说明信息来源。\n"
            "请使用中文回答。"
        )
