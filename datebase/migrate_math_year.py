#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为 questions_math 添加 year 字段并从 papers.paper_title 回填。

同时在 knowledge_base.db 中创建统一检索视图 v_all_questions，
整合政治、英语、数学三科题目的基础信息与年份。

用法：
    python datebase/migrate_math_year.py [DB_PATH]

DB_PATH 默认为脚本同目录的 knowledge_base.db。
"""

import re
import sqlite3
import sys
from pathlib import Path


def _extract_year(title: str) -> int | None:
    """从试卷标题中提取4位年份数字（1900–2099）。"""
    if not title:
        return None
    m = re.search(r"((?:19|20)\d{2})", title)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2099:
            return y
    return None


def migrate(db_path: str) -> None:
    """执行迁移：添加 year 列、回填数据、创建统一视图。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # ------------------------------------------------------------------
        # 1. 为 questions_math 添加 year 列（幂等，已有则跳过）
        # ------------------------------------------------------------------
        existing_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(questions_math)")
        }
        if "year" not in existing_cols:
            conn.execute("ALTER TABLE questions_math ADD COLUMN year INTEGER")
            print("✓ questions_math.year 列已添加")
        else:
            print("  questions_math.year 列已存在，跳过添加")

        # ------------------------------------------------------------------
        # 2. 从 papers.paper_title 回填 year（仅更新 NULL 行）
        # ------------------------------------------------------------------
        rows = conn.execute(
            "SELECT qm.id, p.paper_title "
            "FROM questions_math qm "
            "JOIN papers p ON p.id = qm.paper_id "
            "WHERE qm.year IS NULL"
        ).fetchall()

        updated = 0
        for row in rows:
            year = _extract_year(row["paper_title"] or "")
            if year:
                conn.execute(
                    "UPDATE questions_math SET year = ? WHERE id = ?",
                    (year, row["id"]),
                )
                updated += 1

        conn.commit()
        print(f"✓ questions_math.year 回填完成，更新 {updated} 行")

        # ------------------------------------------------------------------
        # 3. 创建（或重建）统一检索视图 v_all_questions
        # ------------------------------------------------------------------
        conn.execute("DROP VIEW IF EXISTS v_all_questions")
        conn.execute(
            """
            CREATE VIEW v_all_questions AS
            SELECT
                id,
                'politics'  AS subject,
                year,
                question_type,
                stem        AS content
            FROM questions_politics
            UNION ALL
            SELECT
                id,
                'math'      AS subject,
                year,
                question_type,
                stem        AS content
            FROM questions_math
            UNION ALL
            SELECT
                id,
                'english'   AS subject,
                year,
                question_type,
                content
            FROM questions_english
            """
        )
        conn.commit()
        print("✓ 统一检索视图 v_all_questions 已创建")

        # ------------------------------------------------------------------
        # 4. 简单校验
        # ------------------------------------------------------------------
        total = conn.execute("SELECT COUNT(*) FROM v_all_questions").fetchone()[0]
        math_with_year = conn.execute(
            "SELECT COUNT(*) FROM questions_math WHERE year IS NOT NULL"
        ).fetchone()[0]
        math_total = conn.execute("SELECT COUNT(*) FROM questions_math").fetchone()[0]
        print(
            f"✓ 校验：v_all_questions 共 {total} 行；"
            f"questions_math 有年份 {math_with_year}/{math_total}"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    default_db = Path(__file__).parent / "knowledge_base.db"
    db_path = sys.argv[1] if len(sys.argv) > 1 else str(default_db)
    migrate(db_path)
