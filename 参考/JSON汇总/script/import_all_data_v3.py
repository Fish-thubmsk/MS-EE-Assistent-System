#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考研题库数据导入脚本 v3 - 完整重构版
使用 PyMySQL，按照新的规范化设计导入所有数据

新设计：
- 7 个表：sub_questions, options, questions_politics, questions_english, 
          questions_math, papers, subjects
- 统一的 sub_questions 和 options 表存储所有科目的小问和选项
"""

import json
import pymysql
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 修复 Windows 编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'charset': 'utf8mb4'
}

BASE_PATH = Path(__file__).parent

class ImportManager:
    def __init__(self):
        self.conn = None
        self.cursor = None
        # 用于追踪导入数据
        self.stats = {
            'questions_politics': 0,
            'questions_english': 0,
            'questions_math': 0,
            'sub_questions': 0,
            'options': 0,
        }
    
    def get_connection(self, database=None):
        """获取 MySQL 连接"""
        config = MYSQL_CONFIG.copy()
        if database:
            config['db'] = database
        return pymysql.connect(**config)
    
    def create_tables(self):
        """创建所有表"""
        print("\n6. 创建表结构...\n")
        
        # 政治题目表
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions_politics (
            id INT PRIMARY KEY AUTO_INCREMENT,
            original_id INT UNIQUE NOT NULL COMMENT '原始ID',
            year INT NOT NULL COMMENT '考试年份',
            question_type VARCHAR(20) NOT NULL COMMENT '题型（单选题/多选题/材料分析题）',
            stem LONGTEXT NOT NULL COMMENT '题干',
            correct_answer VARCHAR(10) COMMENT '正确答案（仅单选/多选用）',
            analysis LONGTEXT COMMENT '解析',
            difficulty INT COMMENT '难度',
            score DECIMAL(5,2) COMMENT '分值',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_year (year),
            KEY idx_type (question_type),
            KEY idx_original (original_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='政治题目表'
        """)
        print("✓ questions_politics 表创建")
        
        # 英语文章表（重命名自 articles_english）
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions_english (
            id INT PRIMARY KEY AUTO_INCREMENT,
            year INT NOT NULL COMMENT '考试年份',
            question_number INT COMMENT '题号（1-9）',
            question_type VARCHAR(30) NOT NULL COMMENT '题型',
            content LONGTEXT NOT NULL COMMENT '文章或题目内容',
            translation LONGTEXT COMMENT '翻译',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_year (year),
            KEY idx_type (question_type),
            KEY idx_question_number (question_number)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='英语文章表'
        """)
        print("✓ questions_english 表创建")
        
        # 统一小问表
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS sub_questions (
            id INT PRIMARY KEY AUTO_INCREMENT,
            subject_type ENUM('politics', 'english', 'math') NOT NULL COMMENT '科目类型',
            question_id INT NOT NULL COMMENT '题目ID',
            question_number INT COMMENT '题号',
            sub_question_number INT COMMENT '小问号',
            stem LONGTEXT COMMENT '题干（英语为NULL）',
            answer LONGTEXT COMMENT '答案',
            analysis LONGTEXT COMMENT '解析',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_subject (subject_type),
            KEY idx_question (question_id),
            KEY idx_sub_number (sub_question_number)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一小问表'
        """)
        print("✓ sub_questions 表创建")
        
        # 统一选项表
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS options (
            id INT PRIMARY KEY AUTO_INCREMENT,
            subject_type ENUM('politics', 'english', 'math') NOT NULL COMMENT '科目类型',
            sub_question_id INT NOT NULL COMMENT '小问ID',
            option_key VARCHAR(10) NOT NULL COMMENT '选项键（A/B/C/D）',
            option_text LONGTEXT NOT NULL COMMENT '选项文本',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sub_question_id) REFERENCES sub_questions(id) ON DELETE CASCADE,
            UNIQUE KEY unique_option (sub_question_id, option_key),
            KEY idx_sub_question (sub_question_id),
            KEY idx_subject (subject_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一选项表'
        """)
        print("✓ options 表创建")
        
        # 数学科目表
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            subject_code VARCHAR(10) PRIMARY KEY COMMENT '科目代码',
            subject_name VARCHAR(50) NOT NULL COMMENT '科目名称',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数学科目表'
        """)
        print("✓ subjects 表创建")
        
        # 数学试卷表
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INT PRIMARY KEY AUTO_INCREMENT,
            subject_code VARCHAR(10) NOT NULL COMMENT '科目代码',
            paper_no INT NOT NULL COMMENT '试卷号',
            paper_title VARCHAR(255) COMMENT '试卷标题',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_code) REFERENCES subjects(subject_code),
            UNIQUE KEY unique_paper (subject_code, paper_no),
            KEY idx_subject (subject_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数学试卷表'
        """)
        print("✓ papers 表创建")
        
        # 数学题目表（重命名自 questions）
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions_math (
            id INT PRIMARY KEY AUTO_INCREMENT,
            paper_id INT NOT NULL COMMENT '试卷ID',
            question_no INT NOT NULL COMMENT '题号',
            question_type VARCHAR(50) COMMENT '题型',
            stem LONGTEXT NOT NULL COMMENT '题干',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (paper_id) REFERENCES papers(id),
            KEY idx_paper (paper_id),
            KEY idx_type (question_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数学题目表'
        """)
        print("✓ questions_math 表创建")
        
        self.conn.commit()
        print("\n✓ 所有表创建成功！")
    
    def import_politics(self):
        """导入政治数据"""
        print("\n7. 导入政治数据...\n")
        
        politics_file = BASE_PATH / "政治" / "题库_结构化精简_全量去重.json"
        with open(politics_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for year_data in data['years']:
            year = year_data['year']
            for section in year_data['sections']:
                question_type = section['questionType']
                for question in section['questions']:
                    # 插入题目到 questions_politics
                    original_id = question.get('originalId', question['id'])
                    stem = question['stem']
                    correct_answer = question.get('answer')
                    analysis = question.get('analysis', '')
                    difficulty = question.get('difficulty')
                    score = question.get('score')
                    
                    self.cursor.execute("""
                    INSERT INTO questions_politics 
                    (original_id, year, question_type, stem, correct_answer, analysis, difficulty, score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (original_id, year, question_type, stem, correct_answer, analysis, difficulty, score))
                    
                    politics_q_id = self.cursor.lastrowid
                    self.stats['questions_politics'] += 1
                    
                    # 处理小问和选项
                    if question_type == '材料分析题':
                        # 材料分析题有子问
                        for sub_q in question.get('subQuestions', []):
                            sub_stem = sub_q['stem']
                            sub_answer = sub_q.get('answer', '')
                            sub_analysis = sub_q.get('analysis', '')
                            sub_number = sub_q.get('id', sub_q.get('number'))
                            
                            self.cursor.execute("""
                            INSERT INTO sub_questions 
                            (subject_type, question_id, sub_question_number, stem, answer, analysis)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """, ('politics', politics_q_id, sub_number, sub_stem, sub_answer, sub_analysis))
                            
                            self.stats['sub_questions'] += 1
                    else:
                        # 单选/多选题在 sub_questions 中只有 1 行
                        self.cursor.execute("""
                        INSERT INTO sub_questions 
                        (subject_type, question_id, stem, answer, analysis)
                        VALUES (%s, %s, %s, %s, %s)
                        """, ('politics', politics_q_id, None, correct_answer, analysis))
                        
                        sub_q_id = self.cursor.lastrowid
                        self.stats['sub_questions'] += 1
                        
                        # 插入选项
                        options = question['options']
                        for idx, option_text in enumerate(options):
                            option_key = chr(65 + idx)  # A, B, C, D, ...
                            self.cursor.execute("""
                            INSERT INTO options 
                            (subject_type, sub_question_id, option_key, option_text)
                            VALUES (%s, %s, %s, %s)
                            """, ('politics', sub_q_id, option_key, option_text))
                            self.stats['options'] += 1
        
        self.conn.commit()
        print(f"✓ 政治数据导入完成：{self.stats['questions_politics']} 题目、{self.stats['sub_questions']} 小问")
    
    def import_english(self):
        """导入英语数据"""
        print("\n8. 导入英语数据...\n")
        
        # 处理两个英语文件
        english_files = [
            BASE_PATH / "英语" / "exams_E_1.json",
            BASE_PATH / "英语" / "exams_E_2.json"
        ]
        
        for english_file in english_files:
            if not english_file.exists():
                print(f"  ⚠️  文件不存在：{english_file.name}，跳过")
                continue
            
            with open(english_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 英语数据是数组，每个元素是一年的考试
            exam_list = data if isinstance(data, list) else [data]
            
            for exam in exam_list:
                title = exam.get('title', '')
                # 从标题提取年份
                year = 2024
                try:
                    if '年' in title:
                        year_str = title.split('年')[0]
                        # 尝试提取最后4位数字
                        import re
                        match = re.search(r'(\d{4})', year_str)
                        if match:
                            year = int(match.group(1))
                except:
                    pass
                
                for question in exam.get('questions', []):
                    question_number = question.get('question_number')
                    question_type = question.get('type', '')
                    article = question.get('article', '')
                    translation = question.get('article_translation', '')
                    
                    # 插入到 questions_english
                    self.cursor.execute("""
                    INSERT INTO questions_english 
                    (year, question_number, question_type, content, translation)
                    VALUES (%s, %s, %s, %s, %s)
                    """, (year, question_number, question_type, article, translation))
                    
                    english_q_id = self.cursor.lastrowid
                    self.stats['questions_english'] += 1
                    
                    # 插入子问
                    for sub_q in question.get('sub_questions', []):
                        sub_number = sub_q.get('sub_question_number')
                        answer = sub_q.get('answer', '')
                        analysis = sub_q.get('analysis', '')
                        
                        self.cursor.execute("""
                        INSERT INTO sub_questions 
                        (subject_type, question_id, question_number, sub_question_number, stem, answer, analysis)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, ('english', english_q_id, question_number, sub_number, None, answer, analysis))
                        
                        sub_q_id = self.cursor.lastrowid
                        self.stats['sub_questions'] += 1
                        
                        # 插入选项
                        options = sub_q.get('options', {})
                        if isinstance(options, dict):
                            for option_key, option_text in options.items():
                                self.cursor.execute("""
                                INSERT INTO options 
                                (subject_type, sub_question_id, option_key, option_text)
                                VALUES (%s, %s, %s, %s)
                                """, ('english', sub_q_id, option_key, option_text))
                                self.stats['options'] += 1
        
        self.conn.commit()
        print(f"✓ 英语数据导入完成：{self.stats['questions_english']} 文章")
    
    def import_math(self):
        """导入数学数据"""
        print("\n9. 导入数学数据...\n")
        
        # 先插入科目
        subjects = [
            ('math1', '数学(一)'),
            ('math2', '数学(二)'),
            ('math3', '数学(三)')
        ]
        for subject_code, subject_name in subjects:
            try:
                self.cursor.execute("""
                INSERT INTO subjects (subject_code, subject_name)
                VALUES (%s, %s)
                """, (subject_code, subject_name))
            except pymysql.err.IntegrityError:
                # 如果已存在则跳过
                pass
        self.conn.commit()
        
        # 处理三个数学文件
        math_files = [
            ('math1', BASE_PATH / "数学" / "kmath_questions1_final.json"),
            ('math2', BASE_PATH / "数学" / "kmath_questions2_final.json"),
            ('math3', BASE_PATH / "数学" / "kmath_questions3_final.json")
        ]
        
        for subject_code, math_file in math_files:
            if not math_file.exists():
                print(f"  ⚠️  文件不存在：{math_file.name}，跳过")
                continue
            
            with open(math_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for paper_data in data.get('papers', []):
                paper_title = paper_data.get('paper_title', '')
                
                # 插入试卷
                # 提取试卷号 - 通常是从标题中
                paper_no = 0
                try:
                    # 尝试从标题提取年份或编号
                    if '第' in paper_title:
                        parts = paper_title.split('第')[1].split('套')
                        paper_no = int(parts[0])
                    else:
                        paper_no = data['papers'].index(paper_data) + 1
                except:
                    paper_no = data['papers'].index(paper_data) + 1
                
                self.cursor.execute("""
                INSERT INTO papers (subject_code, paper_no, paper_title)
                VALUES (%s, %s, %s)
                """, (subject_code, paper_no, paper_title))
                
                paper_id = self.cursor.lastrowid
                
                # 插入题目
                for question in paper_data.get('questions', []):
                    question_no = int(question.get('question_id', 0))
                    question_type = question.get('question_type', '')
                    stem = question.get('stem', '')
                    
                    self.cursor.execute("""
                    INSERT INTO questions_math (paper_id, question_no, question_type, stem)
                    VALUES (%s, %s, %s, %s)
                    """, (paper_id, question_no, question_type, stem))
                    
                    math_q_id = self.cursor.lastrowid
                    self.stats['questions_math'] += 1
                    
                    # 插入子问（包装题目）
                    self.cursor.execute("""
                    INSERT INTO sub_questions (subject_type, question_id, stem, answer)
                    VALUES (%s, %s, %s, %s)
                    """, ('math', math_q_id, None, None))
                    
                    sub_q_id = self.cursor.lastrowid
                    self.stats['sub_questions'] += 1
                    
                    # 插入选项
                    options = question.get('options', {})
                    if isinstance(options, dict):
                        for option_key, option_text in options.items():
                            self.cursor.execute("""
                            INSERT INTO options (subject_type, sub_question_id, option_key, option_text)
                            VALUES (%s, %s, %s, %s)
                            """, ('math', sub_q_id, option_key, option_text))
                            self.stats['options'] += 1
        
        self.conn.commit()
        print(f"✓ 数学数据导入完成：{self.stats['questions_math']} 题目")
    
    def verify_data(self):
        """验证数据完整性"""
        print("\n10. 数据验证...\n")
        
        # 检查各表数据量
        tables = [
            'questions_politics',
            'questions_english',
            'questions_math',
            'sub_questions',
            'options'
        ]
        
        total_rows = 0
        for table in tables:
            self.cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            result = self.cursor.fetchone()
            count = result[0] if result else 0
            total_rows += count
            print(f"  ✓ {table}: {count} 行")
        
        print(f"\n  总计：{total_rows} 行")
        
        # 检查外键引用完整性
        print("\n  检查外键完整性...")
        self.cursor.execute("""
        SELECT COUNT(*) FROM options 
        WHERE sub_question_id NOT IN (SELECT id FROM sub_questions)
        """)
        orphaned = self.cursor.fetchone()[0]
        print(f"  ✓ 孤立选项：{orphaned} 条")
        
        return True
    
    def run(self):
        """执行完整导入流程"""
        try:
            print("=" * 70)
            print("考研题库 MySQL 导入脚本 v3 - 完整重构版")
            print("=" * 70)
            
            # 连接 MySQL
            print("\n1. 连接 MySQL...")
            self.conn = self.get_connection()
            self.cursor = self.conn.cursor()
            print("✓ 连接成功")
            
            # 删除旧数据库
            print("\n2. 清理旧数据库...")
            self.cursor.execute("DROP DATABASE IF EXISTS exam_questions")
            self.conn.commit()
            print("✓ 旧数据库已删除")
            
            # 创建数据库
            print("\n3. 创建数据库...")
            self.cursor.execute("""
            CREATE DATABASE IF NOT EXISTS exam_questions 
            CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            self.conn.commit()
            self.cursor.close()
            self.conn.close()
            print("✓ 数据库创建成功")
            
            # 重新连接
            print("\n4. 连接到 exam_questions...")
            self.conn = self.get_connection('exam_questions')
            self.cursor = self.conn.cursor()
            print("✓ 连接成功")
            
            # 创建表
            self.create_tables()
            
            # 导入数据
            print("\n" + "=" * 70)
            print("导入数据")
            print("=" * 70)
            
            self.import_politics()
            self.import_english()
            self.import_math()
            
            # 验证
            self.verify_data()
            
            print("\n" + "=" * 70)
            print("✓ 导入完成！")
            print("=" * 70)
            print(f"\n总体统计：")
            print(f"  - 政治题目：{self.stats['questions_politics']}")
            print(f"  - 英语文章：{self.stats['questions_english']}")
            print(f"  - 数学题目：{self.stats['questions_math']}")
            print(f"  - 小问总数：{self.stats['sub_questions']}")
            print(f"  - 选项总数：{self.stats['options']}")
            
        except Exception as e:
            print(f"\n✗ 错误：{e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.conn:
                self.cursor.close()
                self.conn.close()

if __name__ == '__main__':
    manager = ImportManager()
    manager.run()
