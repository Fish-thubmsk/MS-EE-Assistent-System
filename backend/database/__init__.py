"""
用户数据库模块

提供 SQLAlchemy ORM 模型与数据库初始化工具，管理 userdata.db 中的用户数据表：
  - users            用户账号管理
  - quiz_records     答题记录
  - diagnosis_reports 诊断报告
"""

from backend.database.db_manager import get_engine, get_userdata_db_path, init_db
from backend.database.models import Base, DiagnosisReport, QuizRecord, User

__all__ = [
    "Base",
    "User",
    "QuizRecord",
    "DiagnosisReport",
    "init_db",
    "get_engine",
    "get_userdata_db_path",
]
