#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考研题库数据库构建脚本

从 参考/JSON汇总/ 下的三个 JSON 数据源，构建规范化的 SQLite 知识库
knowledge_base.db，替换旧的单表设计。

新架构 (7 张表):
  subjects          - 数学科目 (math1 / math2 / math3)
  papers            - 数学试卷
  questions_math    - 数学题目
  questions_politics- 政治题目
  questions_english - 英语文章/大题
  sub_questions     - 跨科目统一小问表
  options           - 跨科目统一选项表

加上原有的:
  quiz_records      - 用户做题记录 (保持不变)

用法:
  python datebase/build_knowledge_base.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_JSON_ROOT = _REPO_ROOT / "参考" / "JSON汇总"
_DB_PATH = _SCRIPT_DIR / "knowledge_base.db"


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 数学科目
CREATE TABLE IF NOT EXISTS subjects (
    subject_code TEXT PRIMARY KEY,
    subject_name TEXT NOT NULL
);

-- 数学试卷
CREATE TABLE IF NOT EXISTS papers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT NOT NULL REFERENCES subjects(subject_code),
    paper_no     INTEGER NOT NULL,
    paper_title  TEXT,
    UNIQUE(subject_code, paper_no)
);

-- 数学题目
CREATE TABLE IF NOT EXISTS questions_math (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id      INTEGER NOT NULL REFERENCES papers(id),
    question_no   INTEGER NOT NULL,
    question_type TEXT,
    stem          TEXT NOT NULL
);

-- 政治题目
CREATE TABLE IF NOT EXISTS questions_politics (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id    INTEGER,
    year           INTEGER NOT NULL,
    question_type  TEXT NOT NULL,
    stem           TEXT NOT NULL,
    correct_answer TEXT,
    analysis       TEXT,
    difficulty     INTEGER,
    score          REAL
);

-- 英语文章/大题
CREATE TABLE IF NOT EXISTS questions_english (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    question_number INTEGER,
    question_type   TEXT NOT NULL,
    content         TEXT NOT NULL,
    translation     TEXT
);

-- 统一小问表
CREATE TABLE IF NOT EXISTS sub_questions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type        TEXT NOT NULL CHECK(subject_type IN ('politics','english','math')),
    question_id         INTEGER NOT NULL,
    question_number     INTEGER,
    sub_question_number INTEGER,
    stem                TEXT,
    answer              TEXT,
    analysis            TEXT
);
CREATE INDEX IF NOT EXISTS idx_sq_subject ON sub_questions(subject_type);
CREATE INDEX IF NOT EXISTS idx_sq_question ON sub_questions(question_id);

-- 统一选项表
CREATE TABLE IF NOT EXISTS options (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type    TEXT NOT NULL CHECK(subject_type IN ('politics','english','math')),
    sub_question_id INTEGER NOT NULL REFERENCES sub_questions(id) ON DELETE CASCADE,
    option_key      TEXT NOT NULL,
    option_text     TEXT NOT NULL,
    UNIQUE(sub_question_id, option_key)
);
CREATE INDEX IF NOT EXISTS idx_opt_sub_q ON options(sub_question_id);

-- 用户做题记录 (保持与旧版兼容)
CREATE TABLE IF NOT EXISTS quiz_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL,
    question_id    INTEGER,
    subject        TEXT,
    knowledge_point TEXT,
    is_correct     INTEGER,
    answered_at    TEXT
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_year_from_title(title: str, fallback: int = 2024) -> int:
    m = re.search(r"(20\d{2})", title)
    return int(m.group(1)) if m else fallback


# ---------------------------------------------------------------------------
# Import functions
# ---------------------------------------------------------------------------

def import_politics(conn: sqlite3.Connection) -> int:
    politics_file = _JSON_ROOT / "政治" / "题库_结构化精简_全量去重.json"
    if not politics_file.exists():
        print(f"  ⚠️  政治数据文件不存在：{politics_file}")
        return 0

    data = json.loads(politics_file.read_text(encoding="utf-8"))
    cur = conn.cursor()
    count = 0

    for year_data in data.get("years", []):
        year = int(year_data["year"])
        for section in year_data.get("sections", []):
            question_type = section.get("questionType", "")
            for question in section.get("questions", []):
                original_id = question.get("originalId") or question.get("id")
                stem = question.get("stem", "")
                correct_answer = question.get("answer") or None
                # Normalize empty strings to None
                if correct_answer == "":
                    correct_answer = None
                analysis = question.get("analysis") or None
                difficulty = question.get("difficulty")
                score = question.get("score")

                cur.execute(
                    """
                    INSERT INTO questions_politics
                        (original_id, year, question_type, stem, correct_answer, analysis, difficulty, score)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (original_id, year, question_type, stem, correct_answer, analysis, difficulty, score),
                )
                politics_q_id = cur.lastrowid
                count += 1

                if question_type == "材料分析题":
                    for sub_q in question.get("subQuestions", []):
                        sub_stem = sub_q.get("stem", "")
                        sub_answer = sub_q.get("answer") or None
                        sub_analysis = sub_q.get("analysis") or None
                        sub_number = sub_q.get("id") or sub_q.get("number")
                        cur.execute(
                            """
                            INSERT INTO sub_questions
                                (subject_type, question_id, sub_question_number, stem, answer, analysis)
                            VALUES ('politics',?,?,?,?,?)
                            """,
                            (politics_q_id, sub_number, sub_stem, sub_answer, sub_analysis),
                        )
                else:
                    # Single/multi choice: one sub_question row per question
                    cur.execute(
                        """
                        INSERT INTO sub_questions
                            (subject_type, question_id, stem, answer, analysis)
                        VALUES ('politics',?,NULL,?,?)
                        """,
                        (politics_q_id, correct_answer, analysis),
                    )
                    sub_q_id = cur.lastrowid
                    # Options: original data is a list ["A文本","B文本",...]
                    options_raw = question.get("options", [])
                    if isinstance(options_raw, list):
                        for idx, opt_text in enumerate(options_raw):
                            opt_key = chr(65 + idx)  # A, B, C, D …
                            cur.execute(
                                """
                                INSERT INTO options (subject_type, sub_question_id, option_key, option_text)
                                VALUES ('politics',?,?,?)
                                """,
                                (sub_q_id, opt_key, str(opt_text)),
                            )
                    elif isinstance(options_raw, dict):
                        for opt_key, opt_text in options_raw.items():
                            cur.execute(
                                """
                                INSERT INTO options (subject_type, sub_question_id, option_key, option_text)
                                VALUES ('politics',?,?,?)
                                """,
                                (sub_q_id, opt_key, str(opt_text)),
                            )

    conn.commit()
    return count


def import_english(conn: sqlite3.Connection) -> int:
    english_files = [
        _JSON_ROOT / "英语" / "exams_E_1.json",
        _JSON_ROOT / "英语" / "exams_E_2.json",
    ]
    cur = conn.cursor()
    count = 0

    for ef in english_files:
        if not ef.exists():
            print(f"  ⚠️  英语数据文件不存在：{ef.name}")
            continue

        data = json.loads(ef.read_text(encoding="utf-8"))
        exam_list = data if isinstance(data, list) else [data]

        for exam in exam_list:
            title = exam.get("title", "")
            year = _extract_year_from_title(title)

            for question in exam.get("questions", []):
                question_number = question.get("question_number")
                question_type = question.get("type", "")
                article = question.get("article", "")
                translation = question.get("article_translation", "") or None

                cur.execute(
                    """
                    INSERT INTO questions_english
                        (year, question_number, question_type, content, translation)
                    VALUES (?,?,?,?,?)
                    """,
                    (year, question_number, question_type, article, translation),
                )
                eng_q_id = cur.lastrowid
                count += 1

                for sub_q in question.get("sub_questions", []):
                    sub_number = sub_q.get("sub_question_number")
                    answer = sub_q.get("answer") or None
                    analysis = sub_q.get("analysis") or None

                    cur.execute(
                        """
                        INSERT INTO sub_questions
                            (subject_type, question_id, question_number, sub_question_number, stem, answer, analysis)
                        VALUES ('english',?,?,?,NULL,?,?)
                        """,
                        (eng_q_id, question_number, sub_number, answer, analysis),
                    )
                    sub_q_id = cur.lastrowid

                    options_raw = sub_q.get("options", {})
                    if isinstance(options_raw, dict):
                        for opt_key, opt_text in options_raw.items():
                            cur.execute(
                                """
                                INSERT INTO options (subject_type, sub_question_id, option_key, option_text)
                                VALUES ('english',?,?,?)
                                """,
                                (sub_q_id, opt_key, str(opt_text)),
                            )

    conn.commit()
    return count


def import_math(conn: sqlite3.Connection) -> int:
    math_files = [
        ("math1", "数学(一)", _JSON_ROOT / "数学" / "kmath_questions1_final.json"),
        ("math2", "数学(二)", _JSON_ROOT / "数学" / "kmath_questions2_final.json"),
        ("math3", "数学(三)", _JSON_ROOT / "数学" / "kmath_questions3_final.json"),
    ]
    cur = conn.cursor()
    count = 0

    # Seed subjects
    for subject_code, subject_name, _ in math_files:
        cur.execute(
            "INSERT OR IGNORE INTO subjects (subject_code, subject_name) VALUES (?,?)",
            (subject_code, subject_name),
        )

    for subject_code, _, math_file in math_files:
        if not math_file.exists():
            print(f"  ⚠️  数学数据文件不存在：{math_file.name}")
            continue

        data = json.loads(math_file.read_text(encoding="utf-8"))
        papers_list = data.get("papers", [])

        for paper_idx, paper_data in enumerate(papers_list):
            paper_title = paper_data.get("paper_title", "")
            paper_no = paper_idx + 1

            cur.execute(
                """
                INSERT OR IGNORE INTO papers (subject_code, paper_no, paper_title)
                VALUES (?,?,?)
                """,
                (subject_code, paper_no, paper_title),
            )
            # Fetch the paper id (handles both INSERT and already-existing)
            cur.execute(
                "SELECT id FROM papers WHERE subject_code=? AND paper_no=?",
                (subject_code, paper_no),
            )
            paper_id = cur.fetchone()[0]

            for question in paper_data.get("questions", []):
                question_no = int(question.get("question_id", 0))
                question_type = question.get("question_type", "")
                stem = question.get("stem", "")

                cur.execute(
                    """
                    INSERT INTO questions_math (paper_id, question_no, question_type, stem)
                    VALUES (?,?,?,?)
                    """,
                    (paper_id, question_no, question_type, stem),
                )
                math_q_id = cur.lastrowid
                count += 1

                # One sub_question wrapper per math question
                cur.execute(
                    """
                    INSERT INTO sub_questions (subject_type, question_id, stem, answer)
                    VALUES ('math',?,NULL,NULL)
                    """,
                    (math_q_id,),
                )
                sub_q_id = cur.lastrowid

                options_raw = question.get("options", {})
                if isinstance(options_raw, dict):
                    for opt_key, opt_text in options_raw.items():
                        cur.execute(
                            """
                            INSERT INTO options (subject_type, sub_question_id, option_key, option_text)
                            VALUES ('math',?,?,?)
                            """,
                            (sub_q_id, opt_key, str(opt_text)),
                        )

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Remove old DB so we start fresh
    if _DB_PATH.exists():
        _DB_PATH.unlink()
        print(f"删除旧数据库: {_DB_PATH}")

    print(f"创建新数据库: {_DB_PATH}")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.executescript(_DDL)
    conn.commit()

    print("\n正在导入政治题目…")
    n_pol = import_politics(conn)
    print(f"  ✓ 政治：{n_pol} 题")

    print("\n正在导入英语题目…")
    n_eng = import_english(conn)
    print(f"  ✓ 英语：{n_eng} 文章/大题")

    print("\n正在导入数学题目…")
    n_math = import_math(conn)
    print(f"  ✓ 数学：{n_math} 题")

    # Summary
    cur = conn.cursor()
    tables = [
        "subjects", "papers", "questions_math",
        "questions_politics", "questions_english",
        "sub_questions", "options",
    ]
    print("\n=== 数据库统计 ===")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]} 行")

    conn.close()
    print("\n✅ 数据库构建完成！")


if __name__ == "__main__":
    main()
