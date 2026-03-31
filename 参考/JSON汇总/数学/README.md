# 数学题库数据库设计

**版本**: 2.0 (规范化版本)  
**最后更新**: 2026-03-31  
**状态**: ✅ 生产就绪 (答案缺失)

---

## 📊 数据规模

| 指标 | 统计 |
|------|------|
| **科目** | 数学一、数学二、数学三 |
| **试卷数** | 121 卷 |
| **题目数** | 2,868 道 |
| **小问数** | 3,629 个 |
| **选项数** | 8,039 个 |
| **年份范围** | 2007-2024 (18 年) |

---

## 🏗️ 数据库结构 (3 表)

### 1️⃣ questions_math (题目表)

2,868 道数学题，分为三类：

**单选题**: 896 道 (每题 4 选项)
- 一般来说，中等难度，基础概念考查

**填空题 (填空)**: 761 道 (部分有选项)
- 需要填空的题目，可能有多个空

**解答题 (主观)**: 1,211 道 (无标准选项)
- 需要详细解答，往往占分较高

**关键字段:**
- `subject_code`: 指向 subjects (math_1/math_2/math_3)
- `paper_id`: 指向 papers
- `question_type`: '单选题' / '填空题' / '解答题'
- `stem`: 题干内容
- `answer`: 答案 (当前全为 NULL，源数据缺失) ⚠️
- `analysis`: 解析 (有完整数据)

**数据完整性问题**:
- ⚠️ **所有 2,868 道题的 `answer` 字段都是 NULL**
  - 原因: 源 JSON 中没有答案字段
  - 影响: 无法自动批改、数据不完整
  - 建议: 后续补齐或使用 AI 生成

### 2️⃣ sub_questions (统一小问表)

所有科目共用的小问表，数学部分：
- **小问数**: 3,629 道
- **单选题小问**: 896 行 (1小问/题)
- **填空题小问**: 761 行 (1小问/题，但可能有多个空)
- **解答题小问**: ~1,972 行 (多小问/题)

**关键字段:**
- `subject_type`: 'math' (统一表，支持多科目)
- `question_id`: 指向 questions_math
- `sub_question_number`: 小问编号 (解答题有值)
- `answer`: 答案 (当前全为 NULL) ⚠️

### 3️⃣ options (统一选项表)

所有科目共用的选项表，数学部分：
- **选项数**: 8,039 个
- **单选题选项**: 3,584 个 (896 × 4)
- **填空题选项**: 4,455 个 (某些填空题有选项)

**关键字段:**
- `subject_type`: 'math' (统一表，支持多科目)
- `sub_question_id`: 指向 sub_questions
- `option_key`: A/B/C/D
- `option_text`: 选项内容

---

## 📊 科目分布

### 数学一 (40 卷，704 题)

**考查范围**: 
- 高等数学 (微积分、常微分方程、级数)
- 线性代数 (矩阵、向量空间、特征值)
- 概率论与数理统计 (分布、统计推断)

**题型**: 单选 + 填空 + 解答

### 数学二 (40 卷，701 题)

**考查范围**:
- 高等数学 (比一少概率)
- 线性代数
- 没有概率论

**题型**: 单选 + 填空 + 解答

### 数学三 (41 卷，1,463 题)

**考查范围**:
- 微积分 (偏向经济应用)
- 线性代数 (简化版本)
- 概率论与数理统计 (应用性强)

**题型**: 单选 + 填空 + 解答

---

## 📖 使用示例

### 查询数学一的所有单选题

```sql
SELECT qm.id, qm.stem, GROUP_CONCAT(CONCAT(o.option_key, '. ', o.option_text) SEPARATOR '\n') as options
FROM questions_math qm
JOIN papers p ON qm.paper_id = p.id
JOIN sub_questions sq ON qm.id = sq.question_id
LEFT JOIN options o ON sq.id = o.sub_question_id
WHERE p.subject_code = 'math_1' AND qm.question_type = '单选题'
GROUP BY qm.id
LIMIT 10;
```

### 按科目和题型统计

```sql
SELECT 
    p.subject_code,
    qm.question_type,
    COUNT(*) as count
FROM questions_math qm
JOIN papers p ON qm.paper_id = p.id
GROUP BY p.subject_code, qm.question_type
ORDER BY p.subject_code, qm.question_type;
```

### 获取某道解答题的所有小问

```sql
SELECT sq.sub_question_number, sq.stem, sq.analysis
FROM questions_math qm
JOIN sub_questions sq ON qm.id = sq.question_id
WHERE qm.id = 100
ORDER BY sq.sub_question_number;
```

### 查询某一年的所有试卷

```sql
SELECT DISTINCT id, subject_code, year
FROM papers
WHERE year = 2024
ORDER BY subject_code;
```

---

## 📋 JSON 源数据

**文件**: 
- `kmath_questions1_final.json` (数学一)
- `kmath_questions2_final.json` (数学二)
- `kmath_questions3_final.json` (数学三)

**结构示例**:
```json
{
  "papers": [
    {
      "year": 2024,
      "questions": [
        {
          "id": 1,
          "number": 1,
          "type": "single_choice",
          "stem": "题干...",
          "options": ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"],
          "answer": null,
          "analysis": "解析..."
        }
      ]
    }
  ]
}
```

---

## ⚠️ 数据完整性警告

```
✗ 答案字段: NULL (所有 2,868 题)
✓ 解析字段: 有数据
✓ 选项字段: 有数据 (单选和部分填空)
✓ 外键完整性: 100%
✓ 年份覆盖: 2007-2024 (完整)
```

### 已知问题

**问题 1: 所有答案缺失 (严重)**
- 影响: 2,868 道题
- 原因: 源 JSON 中 `answer` 字段为 null
- 解决方案:
  - [ ] 找其他数据源补齐答案
  - [ ] AI 生成答案
  - [ ] 手工编辑高优先度题目

**问题 2: 部分填空题的多空处理**
- 某些填空题有 2-3 个空，当前只存一行
- 可能需要拆分或增加子问

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

**Q: 为什么数学答案都是 NULL？**  
A: 这是源数据的问题。原始 JSON 文件中没有包含答案字段，所以导入时都是 NULL。这是使用该数据库时最大的限制。

**Q: 能否先用这个数据库，后面再补答案？**  
A: 可以。可以先用来查询题干、选项、解析，之后通过 SQL 的 UPDATE 语句补充答案字段。

**Q: 如何查询某科目的所有题目？**  
```sql
SELECT COUNT(*) as total_questions
FROM questions_math qm
JOIN papers p ON qm.paper_id = p.id
WHERE p.subject_code = 'math_1';
```

**Q: 为什么有些填空题没有选项？**  
A: 填空题通常没有标准选项，需要考生手写答案。部分填空题可能转化为选择形式，才有选项。

---

## 📞 更多信息

- **IMPORT_README.md** - 详细导入指南 (父目录)
- **PROJECT_SUMMARY.md** - 项目交付总结 (父目录)
- **数据库重构规划.md** - 架构设计文档 (父目录)

---

**⚠️ 注意**: 该数据库缺少所有数学题的答案数据。需要后续补齐。

**当前状态**: 可用，但不完整 ⚠️
