# 实用视图完整指南 v2.0

**最后更新**: 2026-03-31  
**状态**: ✅ 所有 12 个视图已创建、验证、就绪

---

## 📊 总体统计

✅ **3,703 道题目** | ✅ **4,221 条可查询数据** | ✅ **12 个实用视图**

| 科目 | 政治 | 数学 | 英语 | **总计** |
|------|------|------|------|---------|
| 题目数 | 439 | 2,868 | 396 | **3,703** |
| 小问/选项 | 449 | 2,868 | 904 | **4,221** |
| 视图数 | 3 | 3 | 6 | **12** |

---

## 🏛️ 政治题库 (3 个视图，449 条数据)

### v_politics_single - 单选题 (208 道)

**字段**: `id`, `year`, `stem`, `optionA`, `optionB`, `optionC`, `optionD`, `answer`

```sql
SELECT id, year, stem, optionA, optionB, optionC, optionD, answer 
FROM v_politics_single LIMIT 3;
```

**使用示例**:
```sql
-- 查看 2024 年的政治单选题
SELECT * FROM v_politics_single WHERE year = '2024' LIMIT 10;

-- 查看答案
SELECT id, answer FROM v_politics_single WHERE id BETWEEN 1 AND 20;
```

---

### v_politics_multiple - 多选题 (221 道)

**字段**: `id`, `year`, `stem`, `optionA`, `optionB`, `optionC`, `optionD`, `answer`

```sql
SELECT id, year, stem, optionA, optionB, optionC, optionD, answer 
FROM v_politics_multiple LIMIT 3;
```

**使用示例**:
```sql
-- 随机练习 10 道多选题
SELECT id, stem, optionA, optionB, optionC, optionD, answer 
FROM v_politics_multiple ORDER BY RAND() LIMIT 10;
```

---

### v_politics_analysis - 材料分析题 (10 题，20 小问)

**字段**: `id`, `year`, `material`, `sub_num`, `sub_question`, `answer`

```sql
-- 查看某题的所有小问
SELECT id, year, material, sub_num, sub_question, answer 
FROM v_politics_analysis WHERE id = 34 ORDER BY sub_num;
```

**数据样例**:
```
id | year | material | sub_num | sub_question | answer
34 | 2023 | 材料文本... | 1 | (1) 分析... | 需要从...
34 | 2023 | 材料文本... | 2 | (2) 论述... | 人民代表大会...
```

---

## 📐 数学题库 (3 个视图，2,868 条数据)

### v_math_single - 单选题 (896 道)

**字段**: `id`, `math_type`, `stem`, `optionA`, `optionB`, `optionC`, `optionD`

```sql
SELECT id, math_type, stem, optionA, optionB, optionC, optionD 
FROM v_math_single LIMIT 3;
```

**使用示例**:
```sql
-- 查看数学二的单选题
SELECT * FROM v_math_single WHERE math_type = '数二' LIMIT 10;

-- 随机抽取 20 题
SELECT * FROM v_math_single ORDER BY RAND() LIMIT 20;
```

---

### v_math_blank - 填空题 (761 道)

**字段**: `id`, `math_type`, `stem`, `answer`

```sql
SELECT id, math_type, stem, answer 
FROM v_math_blank LIMIT 3;
```

**⚠️ 注意**: 答案字段为 NULL（源数据缺失）

---

### v_math_subjective - 解答题 (1,211 道)

**字段**: `id`, `math_type`, `stem`, `answer`, `analysis`

```sql
SELECT id, math_type, stem, answer, analysis 
FROM v_math_subjective LIMIT 3;
```

**⚠️ 注意**: 答案字段为 NULL（源数据缺失）；解析字段已有

---

## 📚 英语题库 (6 个视图，904 条数据)

### v_english_cloze - 完形填空 (36 篇)

**字段**: `id`, `year`, `article`

```sql
SELECT id, year, article FROM v_english_cloze LIMIT 2;
```

**说明**: 
- 题号 1：完形填空（无选项，仅文章）
- 可用于生成填空练习

---

### v_english_reading - 阅读理解 (656 小问)

**字段**: `id`, `year`, `question_number`, `article`, `sub_q_id`, `question`, `optionA`, `optionB`, `optionC`, `optionD`

```sql
-- 查看某篇文章的所有小问
SELECT year, article, question, optionA, optionB, optionC, optionD 
FROM v_english_reading WHERE id = 1;
```

**说明**:
- 题号 2-5：阅读理解（有选项）
- 104 篇文章，656 个小问

---

### v_english_new_type - 新题型 (104 小问)

**字段**: `id`, `year`, `article`, `sub_q_id`, `question`, `optionA`, `optionB`, `optionC`, `optionD`

```sql
SELECT id, year, article, question, optionA, optionB 
FROM v_english_new_type LIMIT 5;
```

**说明**: 题号 6：新题型（有选项）

---

### v_english_trans - 翻译题 (36 篇)

**字段**: `id`, `year`, `english_text`

```sql
SELECT id, year, english_text FROM v_english_trans LIMIT 3;
```

**说明**: 题号 7：翻译（无选项，仅英文原文）

---

### v_english_writing_small - 小作文 (36 篇)

**字段**: `id`, `year`, `prompt`

```sql
SELECT id, year, prompt FROM v_english_writing_small LIMIT 3;
```

**说明**: 题号 8：小作文（无选项，仅写作提示）

---

### v_english_writing_large - 大作文 (36 篇)

**字段**: `id`, `year`, `prompt`

```sql
SELECT id, year, prompt FROM v_english_writing_large LIMIT 3;
```

**说明**: 题号 9：大作文（无选项，仅写作提示）

---

## 🚀 常用查询快速指南

### 1️⃣ 浏览题目

```sql
-- 浏览最新的政治题
SELECT id, year, stem, optionA, optionB, optionC, optionD 
FROM v_politics_single 
WHERE year = '2024' 
LIMIT 10;

-- 浏览数学题（按科目）
SELECT id, math_type, stem 
FROM v_math_single 
WHERE math_type = '数一' 
LIMIT 10;

-- 浏览英语阅读题
SELECT id, year, article, question 
FROM v_english_reading 
LIMIT 5;
```

### 2️⃣ 制作练习卷

```sql
-- 随机抽取 25 道政治题
SELECT id, stem, optionA, optionB, optionC, optionD 
FROM v_politics_single 
ORDER BY RAND() LIMIT 25;

-- 随机抽取数学题混合卷（单选 10 题 + 填空 10 题）
(SELECT id, '单选' as type, stem FROM v_math_single ORDER BY RAND() LIMIT 10)
UNION ALL
(SELECT id, '填空', stem FROM v_math_blank ORDER BY RAND() LIMIT 10);

-- 随机抽取英语文章 5 篇（来自不同题型）
SELECT DISTINCT id FROM v_english_reading ORDER BY RAND() LIMIT 5;
```

### 3️⃣ 查看答案

```sql
-- 政治答案卡
SELECT id, answer FROM v_politics_single WHERE id BETWEEN 1 AND 30;

-- 数学填空题答案
SELECT id, stem, answer FROM v_math_blank LIMIT 20;

-- 政治分析题完整答案
SELECT id, material, sub_num, sub_question, answer 
FROM v_politics_analysis 
WHERE id = 34 
ORDER BY sub_num;
```

### 4️⃣ 数据统计

```sql
-- 各科目题数统计
SELECT 
    'Politics' as subject,
    (SELECT COUNT(*) FROM v_politics_single) + 
    (SELECT COUNT(*) FROM v_politics_multiple) + 
    (SELECT COUNT(*) FROM v_politics_analysis) as count
UNION ALL
SELECT 'Math', COUNT(*) FROM (
    SELECT * FROM v_math_single 
    UNION ALL 
    SELECT id, math_type, stem FROM v_math_blank 
    UNION ALL 
    SELECT id, math_type, stem FROM v_math_subjective) t
UNION ALL
SELECT 'English', COUNT(*) FROM (
    SELECT id FROM v_english_cloze 
    UNION ALL 
    SELECT id FROM v_english_reading 
    UNION ALL 
    SELECT id FROM v_english_new_type 
    UNION ALL 
    SELECT id FROM v_english_trans 
    UNION ALL 
    SELECT id FROM v_english_writing_small 
    UNION ALL 
    SELECT id FROM v_english_writing_large) t;

-- 数学题型分布
SELECT math_type, COUNT(*) as count 
FROM v_math_single 
GROUP BY math_type;

-- 年份分布
SELECT year, COUNT(*) as count 
FROM v_politics_single 
GROUP BY year 
ORDER BY year;
```

---

## ⚡ 性能优化建议

✅ **推荐做法**

```sql
-- 1. 使用 LIMIT 避免加载全表
SELECT * FROM v_politics_single LIMIT 100;

-- 2. 按索引字段过滤（year, math_type 有索引）
SELECT * FROM v_politics_single WHERE year = '2024' LIMIT 50;

-- 3. 分页查询大数据集
SELECT * FROM v_math_single LIMIT 20 OFFSET 0;    -- 第 1 页
SELECT * FROM v_math_single LIMIT 20 OFFSET 20;   -- 第 2 页
```

❌ **避免做法**

```sql
-- 1. 不加 LIMIT（可能加载全表 3,700+ 行）
SELECT * FROM v_politics_single;

-- 2. 在索引字段上使用函数（放弃索引）
SELECT * FROM v_politics_single WHERE YEAR(year) = 2024;

-- 3. RAND() 在大表上很慢
SELECT * FROM v_math_single ORDER BY RAND() LIMIT 10;

-- 4. 复杂 JOIN（当可以用单表查询时）
SELECT * FROM v_politics_single p 
JOIN other_table o ON p.id = o.id;
```

---

## 🔍 常见问题

**Q: 为什么数学答案都是 NULL？**  
A: 源 JSON 数据中没有答案字段，仅含解析。这是已知限制，后期可以手工补充。

**Q: 英语视图的题号（question_number）是什么意思？**  
A: 
- 1 = 完形填空（v_english_cloze）
- 2-5 = 阅读理解（v_english_reading）
- 6 = 新题型（v_english_new_type）
- 7 = 翻译（v_english_trans）
- 8 = 小作文（v_english_writing_small）
- 9 = 大作文（v_english_writing_large）

**Q: 如何导出视图数据为 CSV？**  
A:
```bash
# 使用 MySQL 命令行导出
mysql -u root -p exam_questions -e \
  "SELECT * FROM v_politics_single" > politics.csv

# 或使用 SELECT INTO OUTFILE
SELECT * FROM v_politics_single 
INTO OUTFILE '/tmp/politics.csv' 
FIELDS TERMINATED BY ',' 
LINES TERMINATED BY '\n';
```

**Q: 视图可以修改或删除吗？**  
A: 视图是只读的，无法直接修改。可以删除视图并重建，但修改源数据表后，视图自动更新。

**Q: 可以创建自定义视图吗？**  
A: 可以！示例：
```sql
-- 创建 2024 年所有科目的题目视图
CREATE VIEW v_all_2024 AS
SELECT id, '政治' as subject, stem FROM v_politics_single WHERE year = '2024'
UNION ALL
SELECT id, '数学', stem FROM v_math_single WHERE id IN (...)
UNION ALL
SELECT id, '英语', article FROM v_english_cloze WHERE year = '2024';
```

**Q: sub_q_id 是什么？**  
A: 小问的数据库内部 ID，用于关联答案和选项。在视图查询时通常不需要使用。

**Q: 如何查看视图的 SQL 定义？**  
A:
```sql
SHOW CREATE VIEW v_politics_single\G
DESCRIBE v_politics_single;
```

---

## 📞 快速参考卡

| 需求 | SQL 命令 |
|------|---------|
| 查看政治单选 | `SELECT * FROM v_politics_single LIMIT 10;` |
| 查看政治多选 | `SELECT * FROM v_politics_multiple LIMIT 10;` |
| 查看政治分析 | `SELECT * FROM v_politics_analysis WHERE id = 1;` |
| 查看数学单选 | `SELECT * FROM v_math_single WHERE math_type = '数一' LIMIT 10;` |
| 查看数学填空 | `SELECT * FROM v_math_blank LIMIT 10;` |
| 查看数学解答 | `SELECT * FROM v_math_subjective LIMIT 10;` |
| 查看英语完形 | `SELECT * FROM v_english_cloze LIMIT 5;` |
| 查看英语阅读 | `SELECT * FROM v_english_reading LIMIT 5;` |
| 查看英语翻译 | `SELECT * FROM v_english_trans LIMIT 5;` |
| 随机抽题 10 道 | `SELECT * FROM v_politics_single ORDER BY RAND() LIMIT 10;` |
| 统计视图行数 | `SELECT COUNT(*) FROM v_politics_single;` |
| 列出所有视图 | `SHOW TABLES LIKE 'v_%';` |

---

## 📋 完整视图清单

| 视图名 | 科目 | 类型 | 数据量 |
|--------|------|------|--------|
| v_politics_single | 政治 | 单选题 | 208 |
| v_politics_multiple | 政治 | 多选题 | 221 |
| v_politics_analysis | 政治 | 材料分析 | 20 |
| v_math_single | 数学 | 单选题 | 896 |
| v_math_blank | 数学 | 填空题 | 761 |
| v_math_subjective | 数学 | 解答题 | 1,211 |
| v_english_cloze | 英语 | 完形填空 | 36 |
| v_english_reading | 英语 | 阅读理解 | 656 |
| v_english_new_type | 英语 | 新题型 | 104 |
| v_english_trans | 英语 | 翻译 | 36 |
| v_english_writing_small | 英语 | 小作文 | 36 |
| v_english_writing_large | 英语 | 大作文 | 36 |
| **总计** | **3 科** | **12 视图** | **4,221** |

---

## ✅ 状态检查

运行以下命令验证所有视图就绪：

```sql
-- 检查所有视图
SHOW TABLES LIKE 'v_%';

-- 验证数据量
SELECT 
    'v_politics_single' as view_name, COUNT(*) FROM v_politics_single
UNION ALL
SELECT 'v_politics_multiple', COUNT(*) FROM v_politics_multiple
UNION ALL
SELECT 'v_politics_analysis', COUNT(*) FROM v_politics_analysis
UNION ALL
SELECT 'v_math_single', COUNT(*) FROM v_math_single
UNION ALL
SELECT 'v_math_blank', COUNT(*) FROM v_math_blank
UNION ALL
SELECT 'v_math_subjective', COUNT(*) FROM v_math_subjective
UNION ALL
SELECT 'v_english_cloze', COUNT(*) FROM v_english_cloze
UNION ALL
SELECT 'v_english_reading', COUNT(*) FROM v_english_reading
UNION ALL
SELECT 'v_english_new_type', COUNT(*) FROM v_english_new_type
UNION ALL
SELECT 'v_english_trans', COUNT(*) FROM v_english_trans
UNION ALL
SELECT 'v_english_writing_small', COUNT(*) FROM v_english_writing_small
UNION ALL
SELECT 'v_english_writing_large', COUNT(*) FROM v_english_writing_large;
```

---

**✅ 生产就绪** | **🚀 所有 12 个视图已激活** | **📊 4,221 条数据可用**

最后更新: 2026-03-31
