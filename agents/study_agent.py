"""
Study Agent  (学习模式)
=======================
Explains concepts in depth with structured guidance (key points, examples,
common pitfalls) to help the student build a solid understanding.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from models.schemas import AgentRequest


class StudyAgent(BaseAgent):
    mode_name = "study"

    def _system_prompt(self, request: AgentRequest) -> str:
        subject = request.subject or "考研科目"
        return (
            f"你是一位耐心的考研{subject}辅导老师。\n"
            "当学生提出一个概念或知识点时，请按以下结构详细讲解：\n"
            "1. 核心定义与基本原理\n"
            "2. 重要公式或规则（如有）\n"
            "3. 典型例题与解题思路\n"
            "4. 常见错误与注意事项\n"
            "5. 与其他知识点的联系\n"
            "语言清晰易懂，适合备考学生阅读。请使用中文回答。"
        )
