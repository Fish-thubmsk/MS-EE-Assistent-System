# 英语题库数据库设计

**版本**: 2.0 (规范化版本)  
**最后更新**: 2026-03-31  
**状态**: ✅ 生产就绪

---

## 📊 数据规模

| 指标 | 统计 |
|------|------|
| **文章数** | 144 篇 |
| **小问数** | 645 道 |
| **年份范围** | 2010-2024 (15 年) |
| **题型** | 完型填空、阅读理解、新题型、翻译、写作 |
| **选项总数** | 2,087 个 |

---

## 🏗️ 数据库结构 (3 表)

### 1️⃣ questions_english (文章表)

144 篇文章，来自不同年份的真题。

**关键字段:**
- `year`: 考试年份 (2010-2024)
- `exam_type`: 英语(一) / 英语(二)
- `question_number`: 试卷中第几题 (1-9)
- `question_type`: 题型 (完型填空、阅读理解、新题型、翻译、小作文、大作文)
- `stem`: 题干或文章内容
- `answer`: 答案 (填空题为 NULL，见于 sub_questions)

**设计特点:**
- 避免文章内容重复存储 (同一篇文章可能对应 5-20 个小问)
- 文章内容存在 `stem` 字段 (最多 10,000+ 字符)

### 2️⃣ sub_questions (统一小问表)

所有科目共用的小问表，英语部分：
- **小问数**: 645 道
- **支持科目**: 英语(一)、英语(二)

**关键字段:**
- `subject_type`: 'english' (统一表，支持多科目)
- `question_id`: 指向 questions_english
- `answer`: 答案内容
- `analysis`: 解析 (部分题目可能为空)

### 3️⃣ options (统一选项表)

所有科目共用的选项表，英语部分：
- **选项数**: 2,087 个
- **主要用于**: 阅读理解、新题型的单选题

**关键字段:**
- `subject_type`: 'english' (统一表，支持多科目)
- `sub_question_id`: 指向 sub_questions
- `option_key`: A/B/C/D
- `option_text`: 选项内容

---

## 📖 使用示例

### 查询某年份的所有文章

```sql
SELECT id, question_number, question_type, SUBSTR(stem, 1, 100) as preview
FROM questions_english
WHERE year = 2024
ORDER BY question_number;
```

### 获取文章的所有小问

```sql
SELECT sq.id, sq.answer
FROM questions_english qe
JOIN sub_questions sq ON qe.id = sq.question_id
WHERE qe.id = 1
ORDER BY sq.id;
```

### 查询某个小问的选项

```sql
SELECT option_key, option_text
FROM options o
WHERE o.sub_question_id = 1
ORDER BY option_key;
```

### 按题型统计分布

```sql
SELECT question_type, COUNT(*) as count
FROM questions_english
GROUP BY question_type
ORDER BY count DESC;
```

---

## 📋 JSON 源数据

**文件**: `exams_E_1.json` (英语一) + `exams_E_2.json` (英语二)

**结构**:
```json
{
  "exams": [
    {
      "title": "2024 English (I)",
      "questions": [
        {
          "number": 1,
          "type": "Reading Comprehension",
          "article": "文章内容...",
          "questions": [
            {
              "stem": "小问内容...",
              "options": ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"],
              "answer": "A"
            }
          ]
        }
      ]
    }
  ]
}
```

---

## ⚡ 特点和设计决策

### 1. 为什么分成 2 个表?

**问题**: 一篇文章可能对应 5-20 个小问
- 如果全部放在一个表，每行都要重复存储 10,000+ 字符的文章内容
- 导致表大小膨胀，查询性能下降

**解决**: 分成两个表
- `questions_english`: 存文章（144 行）
- `sub_questions`: 存小问（645 行）
- 这样文章只存一次，节省空间

### 2. 为什么 stem 有时为空？

**情况**: 对于完型填空、阅读理解等
- 题干（小问）实际上包含在文章内容中
- 所以 `stem` 字段为空 (NULL)
- 小问的内容见于 `sub_questions.stem`

### 3. 为什么选项和小问分开？

**原因**: 
- 不是所有小问都有选项 (翻译题、写作题没有选项)
- 分开存储更灵活，满足 1NF 规范
- 支持 0-4 个选项的灵活组合

---

## ✅ 数据完整性

```
✓ 文章数: 144
✓ 小问数: 645
✓ 选项数: 2,087
✓ 孤立记录: 1 (article_id=198 无对应小问，数据源问题)
✓ 外键完整性: 99%
✓ 年份覆盖: 2010-2024 (完整)
```

**已知问题**:
- 英语文章 ID 198 没有对应的小问 (数据源问题，影响极小)

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

**Q: 为什么有些文章的 stem 是空的？**  
A: 对于阅读理解、完型填空等题型，题干包含在文章内容中，不需要额外的 stem 字段。小问的内容存在 `sub_questions.stem` 中。

**Q: 如何查询某道小问的答案和选项？**  
```sql
SELECT 
    sq.answer,
    GROUP_CONCAT(CONCAT(o.option_key, '. ', o.option_text) SEPARATOR '\n') as options
FROM sub_questions sq
LEFT JOIN options o ON sq.id = o.sub_question_id
WHERE sq.id = 1
GROUP BY sq.id;
```

**Q: 为什么有些小问没有选项？**  
A: 翻译题、写作题等没有选项，只有题干和答案。

---

## 📞 更多信息

- **IMPORT_README.md** - 详细导入指南 (父目录)
- **PROJECT_SUMMARY.md** - 项目交付总结 (父目录)
- **数据库重构规划.md** - 架构设计文档 (父目录)

---

**生产就绪** ✅
