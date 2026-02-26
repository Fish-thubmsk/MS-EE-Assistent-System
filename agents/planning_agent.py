"""
Planning Agent  (规划模式)
==========================
Creates a personalised study plan based on the student's target exam date,
weak subjects, and daily available study hours.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from models.schemas import AgentRequest


class PlanningAgent(BaseAgent):
    mode_name = "planning"

    def _retrieve(self, request: AgentRequest):
        # Planning is mostly generative; retrieval is less useful here.
        return []

    def _system_prompt(self, request: AgentRequest) -> str:
        return (
            "你是一位经验丰富的考研备考规划师。\n"
            "根据学生提供的信息（目标院校、考试日期、薄弱科目、每日可用学习时长等），\n"
            "制定一份详细、可执行的备考计划：\n"
            "1. 整体时间安排（按阶段划分：基础、强化、冲刺、模拟）\n"
            "2. 每个科目的周计划安排\n"
            "3. 推荐参考书目与学习资源\n"
            "4. 注意事项与备考建议\n"
            "计划应具体到每周甚至每天的任务，便于执行。请使用中文回答。"
        )
