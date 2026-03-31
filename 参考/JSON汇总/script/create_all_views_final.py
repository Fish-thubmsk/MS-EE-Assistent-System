import pymysql
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = pymysql.connect(
    host='localhost',
    user='root',
    password='123456',
    database='exam_questions',
    charset='utf8mb4'
)

cursor = conn.cursor()

print("\n按照题号创建英语视图...\n")

# 1. 英语完形填空 (question_number = 1)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_cloze")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_cloze AS
    SELECT 
        id, year, SUBSTRING(content, 1, 400) as article
    FROM questions_english
    WHERE question_number = 1
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_cloze")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_cloze - 英语完形填空 (题号1) [{count}]")
except Exception as e:
    print(f"❌ 完形填空: {str(e)[:60]}")

# 2. 英语阅读理解 (question_number 2-5)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_reading")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_reading AS
    SELECT 
        qe.id, qe.year, qe.question_number, SUBSTRING(qe.content, 1, 500) as article,
        sq.id as sub_q_id, SUBSTRING(sq.stem, 1, 120) as question,
        MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) as optionA,
        MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) as optionB,
        MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) as optionC,
        MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) as optionD
    FROM questions_english qe
    JOIN sub_questions sq ON qe.id = sq.question_id AND sq.subject_type = 'english'
    LEFT JOIN options o ON sq.id = o.sub_question_id
    WHERE qe.question_number BETWEEN 2 AND 5
    GROUP BY sq.id
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_reading")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_reading - 英语阅读理解 (题号2-5) [{count}]")
except Exception as e:
    print(f"❌ 阅读理解: {str(e)[:60]}")

# 3. 英语新题型 (question_number = 6)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_new_type")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_new_type AS
    SELECT 
        qe.id, qe.year, SUBSTRING(qe.content, 1, 400) as article,
        sq.id as sub_q_id, SUBSTRING(sq.stem, 1, 120) as question,
        MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) as optionA,
        MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) as optionB,
        MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) as optionC,
        MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) as optionD
    FROM questions_english qe
    LEFT JOIN sub_questions sq ON qe.id = sq.question_id AND sq.subject_type = 'english'
    LEFT JOIN options o ON sq.id = o.sub_question_id
    WHERE qe.question_number = 6
    GROUP BY qe.id, sq.id
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_new_type")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_new_type - 英语新题型 (题号6) [{count}]")
except Exception as e:
    print(f"❌ 新题型: {str(e)[:60]}")

# 4. 英语翻译 (question_number = 7)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_trans")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_trans AS
    SELECT 
        id, year, SUBSTRING(content, 1, 400) as english_text
    FROM questions_english
    WHERE question_number = 7
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_trans")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_trans - 英语翻译 (题号7) [{count}]")
except Exception as e:
    print(f"❌ 翻译: {str(e)[:60]}")

# 5. 英语小作文 (question_number = 8)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_writing_small")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_writing_small AS
    SELECT 
        id, year, SUBSTRING(content, 1, 400) as prompt
    FROM questions_english
    WHERE question_number = 8
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_writing_small")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_writing_small - 英语小作文 (题号8) [{count}]")
except Exception as e:
    print(f"❌ 小作文: {str(e)[:60]}")

# 6. 英语大作文 (question_number = 9)
try:
    cursor.execute("DROP VIEW IF EXISTS v_english_writing_large")
    conn.commit()
    cursor.execute("""
    CREATE VIEW v_english_writing_large AS
    SELECT 
        id, year, SUBSTRING(content, 1, 400) as prompt
    FROM questions_english
    WHERE question_number = 9
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM v_english_writing_large")
    count = cursor.fetchone()[0]
    print(f"✅ v_english_writing_large - 英语大作文 (题号9) [{count}]")
except Exception as e:
    print(f"❌ 大作文: {str(e)[:60]}")

print("\n" + "="*85)
print("✅ 所有视图最终统计")
print("="*85 + "\n")

# 最终验证所有视图
views = [
    ('v_politics_single', '🏛️  政治单选题'),
    ('v_politics_multiple', '🏛️  政治多选题'),
    ('v_politics_analysis', '🏛️  政治材料分析题'),
    ('v_math_single', '📐 数学单选题'),
    ('v_math_blank', '📐 数学填空题'),
    ('v_math_subjective', '📐 数学解答题'),
    ('v_english_cloze', '📚 英语完形填空'),
    ('v_english_reading', '📚 英语阅读理解'),
    ('v_english_new_type', '📚 英语新题型'),
    ('v_english_trans', '📚 英语翻译'),
    ('v_english_writing_small', '📚 英语小作文'),
    ('v_english_writing_large', '📚 英语大作文'),
]

print(f"{'视图名':<30} {'说明':<25} {'数据量':>12}")
print("-" * 85)

total = 0
for view_name, desc in views:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {view_name}")
        count = cursor.fetchone()[0]
        print(f"{view_name:<30} {desc:<25} {count:>12,}")
        total += count
    except Exception as e:
        print(f"{view_name:<30} {desc:<25} ❌ 错误")

print("-" * 85)
print(f"{'合计':<30} {'':<25} {total:>12,}")

print("\n" + "="*85)
print("🎯 推荐快速查询")
print("="*85 + "\n")

examples = {
    '政治单选题': 'SELECT id, year, stem, optionA FROM v_politics_single LIMIT 3;',
    '数学单选题': 'SELECT id, math_type, stem, optionA FROM v_math_single LIMIT 3;',
    '英语完形填空': 'SELECT id, year, article FROM v_english_cloze LIMIT 2;',
    '英语阅读理解': 'SELECT id, year, article, question FROM v_english_reading LIMIT 3;',
    '英语翻译': 'SELECT id, year, english_text FROM v_english_trans LIMIT 2;',
    '英语小作文': 'SELECT id, year, prompt FROM v_english_writing_small LIMIT 2;',
    '英语大作文': 'SELECT id, year, prompt FROM v_english_writing_large LIMIT 2;',
}

for title, sql in examples.items():
    print(f"📌 {title}")
    print(f"   {sql}\n")

conn.close()
