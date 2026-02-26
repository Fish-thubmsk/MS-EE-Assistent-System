"""
Practice Agent  (练习模式)
==========================
Generates practice questions and evaluates student answers.

When the query looks like a student's answer, the agent evaluates it against
the stored question; otherwise it generates a new practice question.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from models.schemas import AgentRequest


_ANSWER_PREFIXES = ("我的答案", "答：", "答:", "answer:", "我认为", "解：")


class PracticeAgent(BaseAgent):
    mode_name = "practice"

    def _system_prompt(self, request: AgentRequest) -> str:
        subject = request.subject or "考研科目"
        is_answer = any(
            request.query.lower().startswith(p.lower())
            for p in _ANSWER_PREFIXES
        )
        if is_answer:
            return (
                f"你是一位严格但友善的考研{subject}阅卷老师。\n"
                "请评估学生的答案：\n"
                "1. 指出答案的正确之处\n"
                "2. 指出错误或遗漏，并给出正确内容\n"
                "3. 给出满分10分的评分及简要评语\n"
                "请使用中文回答。"
            )
        return (
            f"你是一位考研{subject}出题老师。\n"
            "请根据学生指定的知识点或主题，出一道高质量的练习题：\n"
            "- 题目类型可以是选择题、填空题或简答题\n"
            "- 给出题目后，在【参考答案】标签下附上详细解析\n"
            "请使用中文。"
        )
