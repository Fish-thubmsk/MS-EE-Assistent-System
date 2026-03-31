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

print("\n" + "="*90)
print("📊 数据库视图完成验证报告")
print("="*90 + "\n")

# 验证所有视图
views_info = [
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

print("✅ 视图状态检查\n")
print(f"{'视图名':<30} {'说明':<20} {'状态':<8} {'数据量':>10}")
print("-" * 90)

total = 0
errors = []

for view_name, desc in views_info:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {view_name}")
        count = cursor.fetchone()[0]
        status = "✅" if count > 0 else "⚠️"
        print(f"{view_name:<30} {desc:<20} {status:<8} {count:>10,}")
        total += count
    except Exception as e:
        print(f"{view_name:<30} {desc:<20} {'❌':<8} {'错误':>10}")
        errors.append((view_name, str(e)[:50]))

print("-" * 90)
print(f"{'总计':<30} {'':<20} {'':<8} {total:>10,}")

print("\n" + "="*90)
print("📋 数据分布统计")
print("="*90 + "\n")

stats = {
    '政治': [
        ('v_politics_single', '单选题'),
        ('v_politics_multiple', '多选题'),
        ('v_politics_analysis', '材料分析'),
    ],
    '数学': [
        ('v_math_single', '单选题'),
        ('v_math_blank', '填空题'),
        ('v_math_subjective', '解答题'),
    ],
    '英语': [
        ('v_english_cloze', '完形填空'),
        ('v_english_reading', '阅读理解'),
        ('v_english_new_type', '新题型'),
        ('v_english_trans', '翻译'),
        ('v_english_writing_small', '小作文'),
        ('v_english_writing_large', '大作文'),
    ]
}

for subject, views in stats.items():
    subject_total = 0
    print(f"📌 {subject}")
    for view_name, type_name in views:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {view_name}")
            count = cursor.fetchone()[0]
            subject_total += count
            print(f"   • {type_name:<20} {count:>6,} 条")
        except:
            pass
    print(f"   {'─' * 30}")
    print(f"   {'小计':<20} {subject_total:>6,} 条\n")

print("="*90)
print("✨ 快速测试查询")
print("="*90 + "\n")

# 运行几个样本查询
tests = [
    ('政治单选', 'SELECT id, year, stem FROM v_politics_single LIMIT 2'),
    ('数学单选', 'SELECT id, math_type, stem FROM v_math_single LIMIT 2'),
    ('英语阅读', 'SELECT id, year, question FROM v_english_reading LIMIT 2'),
]

for test_name, sql in tests:
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        print(f"✅ {test_name}: {len(rows)} 行数据\n")
    except Exception as e:
        print(f"❌ {test_name}: {str(e)[:60]}\n")

print("="*90)
print("📚 推荐查询命令")
print("="*90 + "\n")

recommendations = """
# 1. 浏览政治单选题
SELECT id, year, stem, optionA, optionB, optionC, optionD, answer 
FROM v_politics_single LIMIT 10;

# 2. 浏览数学单选题（按科目）
SELECT id, math_type, stem FROM v_math_single 
WHERE math_type = '数一' LIMIT 10;

# 3. 查看英语阅读题目和选项
SELECT id, year, article, question, optionA, optionB, optionC, optionD 
FROM v_english_reading LIMIT 5;

# 4. 随机抽题 20 道
SELECT * FROM v_politics_single ORDER BY RAND() LIMIT 20;

# 5. 统计各科目题数
SELECT 'Politics', COUNT(*) FROM v_politics_single
UNION ALL SELECT 'Math', COUNT(*) FROM v_math_single
UNION ALL SELECT 'English', COUNT(*) FROM v_english_reading;
"""

print(recommendations)

print("="*90)
if errors:
    print(f"⚠️  发现 {len(errors)} 个错误:")
    for view, error in errors:
        print(f"   • {view}: {error}")
else:
    print("✅ 所有视图检查完毕，无错误")
print("="*90 + "\n")

conn.close()
