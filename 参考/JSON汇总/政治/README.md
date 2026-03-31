# 政治题库数据库设计

**版本**: 2.0 (规范化版本)  
**最后更新**: 2026-03-31  
**状态**: ✅ 生产就绪

---

## 📊 数据规模

| 指标 | 统计 |
|------|------|
| **总题数** | 439 道 |
| **单选题** | 208 道 |
| **多选题** | 221 道 |
| **材料分析题** | 10 道 |
| **年份范围** | 2013-2025 (13 年) |
| **小问总数** | 449 个 |
| **选项总数** | 1,716 个 |

---

## 🏗️ 数据库结构 (3 表)

### 1️⃣ questions_politics (题目表)

439 道题目，按类型分为：
- **单选题**: 208 道 (每题 4 选项)
- **多选题**: 221 道 (每题 4 选项)
- **材料分析题**: 10 道 (无选项，3-5 小问)

**关键字段:**
- `year`: 考试年份 (2013-2025)
- `question_type`: 题型 ('单选题' / '多选题' / '材料分析题')
- `stem`: 题干内容
- `correct_answer`: 答案 (A/B/C/D，材料题为 NULL)
- `analysis`: 详细解析

### 2️⃣ sub_questions (统一小问表)

所有科目共用的小问表，政治部分：
- **单选题小问**: 208 行 (1小问/题)
- **多选题小问**: 221 行 (1小问/题)
- **材料分析题小问**: ~20 行 (3-5小问/题)
- **总计**: 449 行

**关键字段:**
- `subject_type`: 'politics' (统一表，支持多科目)
- `question_id`: 指向 questions_politics
- `sub_question_number`: 小问编号 (材料题有值，选择题为 NULL)
- `answer`: 答案内容

### 3️⃣ options (统一选项表)

所有科目共用的选项表，政治部分：
- **单选题选项**: 832 个 (208 × 4)
- **多选题选项**: 884 个 (221 × 4)
- **总计**: 1,716 个

**关键字段:**
- `subject_type`: 'politics' (统一表，支持多科目)
- `sub_question_id`: 指向 sub_questions
- `option_key`: 选项字母 (A/B/C/D)
- `option_text`: 选项内容

---

## 📖 使用示例

### 查询单选题及选项

```sql
SELECT 
    qp.id, qp.year, qp.stem,
    GROUP_CONCAT(CONCAT(o.option_key, ': ', o.option_text) SEPARATOR ' | ') as options,
    qp.correct_answer
FROM questions_politics qp
JOIN sub_questions sq ON qp.id = sq.question_id
JOIN options o ON sq.id = o.sub_question_id
WHERE qp.id = 1
GROUP BY qp.id;
```

### 按年份统计题型分布

```sql
SELECT year, question_type, COUNT(*) as count
FROM questions_politics
GROUP BY year, question_type
ORDER BY year DESC;
```

### 获取材料分析题的所有小问

```sql
SELECT sq.sub_question_number, sq.stem, sq.answer, sq.analysis
FROM questions_politics qp
JOIN sub_questions sq ON qp.id = sq.question_id
WHERE qp.id = 34 AND qp.question_type = '材料分析题'
ORDER BY sq.sub_question_number;
```

---

## 📋 JSON 源数据

**文件**: `题库_结构化精简_全量去重.json`

**结构**:
```json
{
  "years": [
    {
      "year": 2025,
      "sections": [
        {
          "questionType": "单选题",
          "questions": [
            {
              "id": 1,
              "typeName": "单选题",
              "stem": "题干...",
              "options": ["A选项", "B选项", "C选项", "D选项"],
              "answer": "C",
              "analysis": "解析..."
            }
          ]
        }
      ]
    }
  ]
}
```

---

## ✅ 数据完整性

```
✓ 总题数: 439
✓ 总小问: 449
✓ 总选项: 1,716
✓ 孤立记录: 0
✓ 外键完整性: 100%
✓ 年份覆盖: 2013-2025 (完整)
✓ 数据完整性: 99%
```

---

## 🚀 快速开始

### 1. 导入数据

```bash
python import_all_data_v3.py
```

### 2. 验证导入

```bash
python verify_final.py
```

### 3. 运行测试

```bash
python test_query_all_subjects.py
```

---

## 📝 常见问题

**Q: 为什么使用 3 个表而不是 1 个表?**  
A: 为了实现数据库第一范式(1NF)，避免 JSON 存储不规范的问题。3 个表设计支持多科目统一查询。

**Q: 材料分析题没有 correct_answer?**  
A: 正确。材料分析题是主观作答，没有单一正确答案，所以 `correct_answer` 字段为 NULL。

**Q: 如何快速查询某一年的所有单选题?**  
```sql
SELECT * FROM questions_politics 
WHERE year = 2024 AND question_type = '单选题';
```

---

## 📞 更多信息

- **IMPORT_README.md** - 详细导入指南 (父目录)
- **PROJECT_SUMMARY.md** - 项目交付总结 (父目录)
- **数据库重构规划.md** - 架构设计文档 (父目录)

---

**生产就绪** ✅
