from flask import Flask, render_template, jsonify, request
import pymysql
import random
import sys
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

def get_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='123456',
        database='exam_questions',
        charset='utf8mb4'
    )

# API：获取科目列表
@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    return jsonify([
        {'id': 'politics', 'name': '政治', 'icon': '🏛️'},
        {'id': 'math', 'name': '数学', 'icon': '📐'},
        {'id': 'english', 'name': '英语', 'icon': '📚'},
    ])

# API：获取科目的题型列表
@app.route('/api/subject/<subject>/types', methods=['GET'])
def get_subject_types(subject):
    types_map = {
        'politics': [
            {'id': 'single', 'name': '单选题', 'view': 'v_politics_single', 'count': 208},
            {'id': 'multiple', 'name': '多选题', 'view': 'v_politics_multiple', 'count': 221},
            {'id': 'analysis', 'name': '材料分析', 'view': 'v_politics_analysis', 'count': 20},
        ],
        'math': [
            {'id': 'single', 'name': '单选题', 'view': 'v_math_single', 'count': 896},
            {'id': 'blank', 'name': '填空题', 'view': 'v_math_blank', 'count': 761},
            {'id': 'subjective', 'name': '解答题', 'view': 'v_math_subjective', 'count': 1211},
        ],
        'english': [
            {'id': 'cloze', 'name': '完形填空', 'view': 'v_english_cloze', 'count': 36},
            {'id': 'reading', 'name': '阅读理解', 'view': 'v_english_reading', 'count': 656},
            {'id': 'new_type', 'name': '新题型', 'view': 'v_english_new_type', 'count': 104},
            {'id': 'trans', 'name': '翻译', 'view': 'v_english_trans', 'count': 36},
            {'id': 'writing_small', 'name': '小作文', 'view': 'v_english_writing_small', 'count': 36},
            {'id': 'writing_large', 'name': '大作文', 'view': 'v_english_writing_large', 'count': 36},
        ],
    }
    return jsonify(types_map.get(subject, []))


@app.route('/api/years/<subject>', methods=['GET'])
def get_years(subject):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if subject == 'politics':
            cursor.execute("SELECT DISTINCT year FROM questions_politics WHERE year IS NOT NULL ORDER BY year DESC")
            years = [int(r[0]) for r in cursor.fetchall()]
        elif subject == 'english':
            cursor.execute("SELECT DISTINCT year FROM questions_english WHERE year IS NOT NULL ORDER BY year DESC")
            years = [int(r[0]) for r in cursor.fetchall()]
        elif subject == 'math':
            cursor.execute("""
                SELECT DISTINCT CAST(LEFT(p.paper_title, 4) AS UNSIGNED) AS y
                FROM questions_math qm
                JOIN papers p ON p.id = qm.paper_id
                WHERE LEFT(p.paper_title, 4) REGEXP '^[0-9]{4}$'
                ORDER BY y DESC
            """)
            years = [int(r[0]) for r in cursor.fetchall() if r[0]]
        else:
            years = []
        cursor.close()
        conn.close()
        return jsonify(years)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API：获取题目
@app.route('/api/question/<subject>/<qtype>', methods=['GET'])
def get_question(subject, qtype):
    limit = request.args.get('limit', 1, type=int)
    year = request.args.get('year', '').strip()
    if limit < 1:
        limit = 1
    if limit > 20:
        limit = 20

    query_map = {
        ('politics', 'single'): """
            SELECT
                qp.id,
                qp.year,
                qp.stem,
                qp.correct_answer AS answer,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD
            FROM questions_politics qp
            LEFT JOIN sub_questions sq ON sq.question_id = qp.id AND sq.subject_type = 'politics'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'politics'
            WHERE qp.question_type = '单选题'
            GROUP BY qp.id, qp.year, qp.stem, qp.correct_answer
        """,
        ('politics', 'multiple'): """
            SELECT
                qp.id,
                qp.year,
                qp.stem,
                qp.correct_answer AS answer,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD
            FROM questions_politics qp
            LEFT JOIN sub_questions sq ON sq.question_id = qp.id AND sq.subject_type = 'politics'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'politics'
            WHERE qp.question_type = '多选题'
            GROUP BY qp.id, qp.year, qp.stem, qp.correct_answer
        """,
        ('politics', 'analysis'): """
            SELECT
                qp.id,
                qp.year,
                qp.stem AS material,
                sq.id AS sub_q_id,
                sq.stem AS sub_question,
                sq.answer
            FROM questions_politics qp
            JOIN sub_questions sq ON sq.question_id = qp.id AND sq.subject_type = 'politics'
            WHERE qp.question_type = '材料分析题'
        """,
        ('math', 'single'): """
            SELECT
                qm.id,
                s.subject_name AS math_type,
                CASE
                    WHEN LEFT(p.paper_title, 4) REGEXP '^[0-9]{4}$' THEN CAST(LEFT(p.paper_title, 4) AS UNSIGNED)
                    ELSE NULL
                END AS year,
                qm.stem,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD,
                sq.answer
            FROM questions_math qm
            LEFT JOIN papers p ON p.id = qm.paper_id
            LEFT JOIN subjects s ON s.subject_code = p.subject_code
            LEFT JOIN sub_questions sq ON sq.question_id = qm.id AND sq.subject_type = 'math'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'math'
            WHERE qm.question_type = 'single_choice'
            GROUP BY qm.id, s.subject_name, qm.stem, sq.answer
        """,
        ('math', 'blank'): """
            SELECT
                qm.id,
                s.subject_name AS math_type,
                CASE
                    WHEN LEFT(p.paper_title, 4) REGEXP '^[0-9]{4}$' THEN CAST(LEFT(p.paper_title, 4) AS UNSIGNED)
                    ELSE NULL
                END AS year,
                qm.stem,
                sq.answer
            FROM questions_math qm
            LEFT JOIN papers p ON p.id = qm.paper_id
            LEFT JOIN subjects s ON s.subject_code = p.subject_code
            LEFT JOIN sub_questions sq ON sq.question_id = qm.id AND sq.subject_type = 'math'
            WHERE qm.question_type = 'fill_blank'
        """,
        ('math', 'subjective'): """
            SELECT
                qm.id,
                s.subject_name AS math_type,
                CASE
                    WHEN LEFT(p.paper_title, 4) REGEXP '^[0-9]{4}$' THEN CAST(LEFT(p.paper_title, 4) AS UNSIGNED)
                    ELSE NULL
                END AS year,
                qm.stem,
                sq.answer,
                sq.analysis
            FROM questions_math qm
            LEFT JOIN papers p ON p.id = qm.paper_id
            LEFT JOIN subjects s ON s.subject_code = p.subject_code
            LEFT JOIN sub_questions sq ON sq.question_id = qm.id AND sq.subject_type = 'math'
            WHERE qm.question_type = 'subjective'
        """,
        ('english', 'cloze'): """
            SELECT
                qe.id,
                qe.year,
                qe.content AS article,
                sq.id AS sub_q_id,
                sq.sub_question_number AS item_no,
                sq.answer,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD
            FROM questions_english qe
            JOIN sub_questions sq ON sq.question_id = qe.id AND sq.subject_type = 'english'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'english'
            WHERE qe.question_number = 1
            GROUP BY qe.id, qe.year, qe.content, sq.id, sq.sub_question_number, sq.answer
        """,
        ('english', 'reading'): """
            SELECT
                qe.id,
                qe.year,
                qe.question_number,
                qe.content AS article,
                sq.id AS sub_q_id,
                sq.sub_question_number AS item_no,
                sq.stem AS question,
                sq.answer,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD
            FROM questions_english qe
            JOIN sub_questions sq ON sq.question_id = qe.id AND sq.subject_type = 'english'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'english'
            WHERE qe.question_number BETWEEN 2 AND 5
            GROUP BY qe.id, qe.year, qe.question_number, qe.content, sq.id, sq.sub_question_number, sq.stem, sq.answer
        """,
        ('english', 'new_type'): """
            SELECT
                qe.id,
                qe.year,
                qe.question_number,
                qe.content AS article,
                sq.id AS sub_q_id,
                sq.sub_question_number AS item_no,
                sq.stem AS question,
                sq.answer,
                MAX(CASE WHEN o.option_key = 'A' THEN o.option_text END) AS optionA,
                MAX(CASE WHEN o.option_key = 'B' THEN o.option_text END) AS optionB,
                MAX(CASE WHEN o.option_key = 'C' THEN o.option_text END) AS optionC,
                MAX(CASE WHEN o.option_key = 'D' THEN o.option_text END) AS optionD
            FROM questions_english qe
            JOIN sub_questions sq ON sq.question_id = qe.id AND sq.subject_type = 'english'
            LEFT JOIN options o ON o.sub_question_id = sq.id AND o.subject_type = 'english'
            WHERE qe.question_number = 6
            GROUP BY qe.id, qe.year, qe.question_number, qe.content, sq.id, sq.sub_question_number, sq.stem, sq.answer
        """,
        ('english', 'trans'): """
            SELECT id, year, content AS english_text
            FROM questions_english
            WHERE question_number = 7
        """,
        ('english', 'writing_small'): """
            SELECT id, year, content AS prompt
            FROM questions_english
            WHERE question_number = 8
        """,
        ('english', 'writing_large'): """
            SELECT id, year, content AS prompt
            FROM questions_english
            WHERE question_number = 9
        """
    }

    base_query = query_map.get((subject, qtype))
    if not base_query:
        return jsonify({'error': 'Invalid subject or type'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        filtered_query = f"SELECT * FROM ({base_query}) t"
        params = []
        if year and year.isdigit():
            filtered_query += " WHERE t.year = %s"
            params.append(int(year))

        # 获取总数
        cursor.execute(f"SELECT COUNT(*) as count FROM ({filtered_query}) c", tuple(params))
        total = cursor.fetchone()['count']

        # 随机获取题目（完整题干，不截断）
        offset = random.randint(0, max(0, total - limit))
        query_params = tuple(params + [limit, offset])
        cursor.execute(f"{filtered_query} LIMIT %s OFFSET %s", query_params)
        questions = cursor.fetchall()
        
        # 处理NULL值和DECIMAL
        for q in questions:
            for key in q:
                if q[key] is None:
                    q[key] = ''
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'questions': questions,
            'total': total,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 主页
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
