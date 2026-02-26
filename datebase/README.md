# 📚 考研题库 - 知识库

## 🎉 数据库已就绪

完全规范化的SQLite数据库，包含考研政治、数学、英语全套题目和文章。

---

## 📊 数据库统计

```
✅ 政治：    495 条题目
✅ 数学：    850 条题目  
✅ 英语：    707 条题目 + 143 篇文章
━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 总计：  2,052 条题目
📄 文章：    143 篇
📍 知识点：  支持层级分类
```

---

## 📂 文件位置

- **数据库**：`knowledge_base.db` — SQLite数据库文件（当前目录）

---

## 🚀 快速使用

### Python 查询示例

```python
import sqlite3
import json

conn = sqlite3.connect(r'knowledge_base.db')
cursor = conn.cursor()

# 查询2024年数学题目
cursor.execute("""
    SELECT question_number, question_type, substr(content, 1, 100)
    FROM questions
    WHERE subject='数学' AND year=2024
    LIMIT 5
""")
for row in cursor.fetchall():
    print(row)

# 查询特定知识点的题目
cursor.execute("""
    SELECT q.id, q.question_number, q.subject
    FROM questions q
    JOIN question_knowledge_points qkp ON q.id = qkp.question_id
    JOIN knowledge_point_hierarchy kph ON qkp.knowledge_point_id = kph.id
    WHERE kph.point_name LIKE '%中国特色社会主义%'
    LIMIT 10
""")

# 查询英语文章及其题目
cursor.execute("""
    SELECT p.passage_title, COUNT(q.id) as question_count
    FROM passages p
    LEFT JOIN questions q ON p.id = q.passage_id
    GROUP BY p.id
    ORDER BY passage_title
""")

conn.close()
```

---

## 📋 数据库表结构

### `questions` 表（题目）
| 字段 | 类型 | 说明 |
|-----|------|------|
| id | INTEGER | 主键 |
| subject | TEXT | 学科（政治/数学/英语） |
| year | INTEGER | 年份 |
| question_number | TEXT | 题号 |
| question_type | TEXT | 题型 |
| content | TEXT | 题目文本 |
| options | JSON | 选项 {A:..., B:..., C:..., D:...} |
| correct_answer | TEXT | 正确答案 |
| analysis | TEXT | 解析/解题 |
| knowledge_structure | JSON | 知识点信息 |
| source | TEXT | 题目来源 |
| passage_id | INT | 关联文章ID（英语题目） |
| parent_id | INT | 父题ID（嵌套题目） |
| statistics | JSON | 答题统计数据 |
| difficulty_level | TEXT | 难度等级 |
| vector_id | TEXT | 向量库ID（预留） |
| is_active | BOOLEAN | 是否有效 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### `passages` 表（英语文章）
| 字段 | 类型 | 说明 |
|-----|------|------|
| id | INTEGER | 主键 |
| year | INTEGER | 年份 |
| passage_number | INT | 文章序号 |
| passage_title | TEXT | 文章标题 |
| passage_text | TEXT | 完整文章内容 |
| translation | TEXT | 中文翻译 |
| word_count | INT | 单词数 |
| num_questions | INT | 关联题目数 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### `knowledge_point_hierarchy` 表（知识点树）
| 字段 | 类型 | 说明 |
|-----|------|------|
| id | INTEGER | 主键 |
| subject | TEXT | 学科 |
| point_name | TEXT | 知识点名称 |
| point_code | TEXT | 知识点编码 |
| level | INT | 层级（1=一级，2=二级...） |
| parent_id | INT | 父级知识点ID |
| description | TEXT | 描述 |
| created_at | TIMESTAMP | 创建时间 |

### `question_knowledge_points` 表（题目-知识点关联）
| 字段 | 类型 | 说明 |
|-----|------|------|
| id | INTEGER | 主键 |
| question_id | INT | 题目ID |
| knowledge_point_id | INT | 知识点ID |
| relationship_type | TEXT | 关联类型 |

---

## 💡 核心特性

✅ **灵活扩展的Schema**
- 支持题目的多种属性（难度、来源、统计数据）
- 文章表补充翻译和字数统计
- 层级化知识点体系

✅ **完整的关联体系**
- 题目 ↔ 文章关联（英语）
- 题目 ↔ 知识点多对多关联
- 知识点层级结构

✅ **性能优化**
- 关键索引支持快速查询 (<100ms)
- JSON字段存储灵活数据
- 支持按学科、年份、题型精确过滤

✅ **向量准备**
- 预留 `vector_id` 字段
- 可无缝集成FAISS/Chroma等向量库

✅ **便捷管理**
- 时间戳字段自动追踪变更
- `is_active` 字段支持逻辑删除

---

## 🔧 数据清洗处理

已应用的处理：
- ✅ 规范化三个学科的数据格式
- ✅ 建立题目与文章的关联
- ✅ 提取并结构化知识点信息
- ✅ 解析题目答题统计数据
- ✅ 添加难度等级评估

---

## 🎯 应用场景

这个数据库可支持：
- 📌 **智能题库系统** — 按学科、年份、知识点精确查询
- 🤖 **个性化推荐** — 基于知识点和难度推荐相关题目
- 📊 **学习分析** — 追踪用户掌握的知识点覆盖范围
- 🔍 **向量搜索** — 集成向量库实现相似题目查询
- 📈 **考试预测** — 基于历年真题分析常考知识点

---

## 📞 常用查询

### 统计信息
```python
# 各科题目数量
cursor.execute('SELECT subject, COUNT(*) FROM questions GROUP BY subject')

# 各年份题目数
cursor.execute('SELECT year, COUNT(*) FROM questions GROUP BY year ORDER BY year')

# 英语文章统计
cursor.execute('SELECT COUNT(*) FROM passages')
```

### 高级查询

```python
# 查询特定难度的题目
cursor.execute("SELECT * FROM questions WHERE difficulty_level='困难' LIMIT 10")

# 查询有解析的题目
cursor.execute("SELECT * FROM questions WHERE analysis IS NOT NULL LIMIT 10")

# 按知识点聚合
cursor.execute("""
    SELECT kph.point_name, COUNT(*) as count
    FROM question_knowledge_points qkp
    JOIN knowledge_point_hierarchy kph ON qkp.knowledge_point_id = kph.id
    GROUP BY qkp.knowledge_point_id
    ORDER BY count DESC
""")
```

---

## 🎁 下一步

现在你可以：
1. ✅ 构建题库查询API
2. ✅ 实现个性化推荐系统
3. ✅ 集成向量搜索能力
4. ✅ 开发学习分析系统
5. ✅ 创建知识点掌握评估

---

**最后更新** 2026-02-26  
**工具** GitHub Copilot CLI
