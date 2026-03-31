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

---

# 🗄️ 完整数据库设计方案（重构）

## 架构总览

系统采用 **双库分离** 策略，将只读的知识库数据与可写的用户行为数据完全分开：

```
knowledge_base.db   ← 只读（题库/知识点）
userdata.db         ← 读写（用户行为/学习记录）
chroma_userdata/    ← 向量数据库（ChromaDB，笔记/错题语义搜索）
```

---

## 一、knowledge_base.db — 知识库（只读）

> 路径：`datebase/knowledge_base.db`  
> ORM：原始 sqlite3（只读查询，不需要 ORM）  
> 访问模块：`agents/diagnosis_agent.py`、`backend/routers/practice.py`

### 已有表

| 表名 | 行数 | 用途 |
|------|------|------|
| `questions` | 2,052 | 题目（三科真题） |
| `passages` | 143 | 英语阅读文章 |
| `knowledge_point_hierarchy` | - | 知识点层级分类（subject/level/parent_id） |
| `question_knowledge_points` | - | 题目 ↔ 知识点多对多关联 |

### 涉及此库的 API 操作

| API | 操作 | 说明 |
|-----|------|------|
| `GET /api/practice/question` | SELECT | 按学科/题型随机抽题 |
| `POST /api/practice` | — | 题目内容由前端传入，不再查库 |
| `POST /diagnosis/run` | SELECT | 按知识点推荐题目 |
| `POST /api/answer` | SELECT（FAISS） | 向量相似度召回题目 |

---

## 二、userdata.db — 用户行为库（读写）

> 路径：`userdata.db`（项目根目录，可通过 `USERDATA_DB_PATH` 环境变量覆盖）  
> ORM：SQLAlchemy 2.x（`backend/database/models.py`）  
> 管理模块：`backend/database/db_manager.py`

### 表 1：users — 用户档案

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT UNIQUE | 业务层唯一 ID（如 "user_001"） |
| display_name | TEXT | 展示名（可选） |
| created_at | DATETIME | 注册时间 |
| updated_at | DATETIME | 最后更新时间 |

### 表 2：quiz_records — 做题历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户业务 ID |
| question_id | INTEGER | 对应 knowledge_base.db.questions.id |
| subject | TEXT | 学科（数学/政治/英语） |
| knowledge_point | TEXT | 主要知识点 |
| is_correct | BOOLEAN | 是否答对（NULL=主观题待判断） |
| difficulty | TEXT | 题目难度 |
| time_spent_seconds | INTEGER | 作答耗时（可选） |
| answered_at | DATETIME | 作答时间 |

### 表 3：chat_sessions — 会话历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| session_id | TEXT UNIQUE | 前端生成的唯一会话 ID |
| user_id | TEXT | 所属用户 |
| mode | TEXT | 会话模式（qa/quiz/diagnosis） |
| subject | TEXT | 学科范围（可选） |
| messages_json | TEXT | 完整消息列表 JSON（可选存档） |
| created_at | DATETIME | 会话开始时间 |
| updated_at | DATETIME | 最后活跃时间 |

### 表 4：diagnosis_reports — 诊断报告

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 所属用户 |
| subject | TEXT | 诊断学科范围（NULL=全科） |
| weak_points_json | TEXT | 薄弱知识点列表（JSON） |
| recommended_questions_json | TEXT | 推荐题目列表（JSON） |
| recommended_notes_json | TEXT | 推荐笔记列表（JSON） |
| report_text | TEXT | 完整诊断报告文本 |
| weak_threshold | FLOAT | 薄弱点阈值 |
| created_at | DATETIME | 报告生成时间 |

### 涉及此库的 API 操作

| API | 操作 | 说明 |
|-----|------|------|
| `POST /api/practice` | INSERT quiz_records | 每次答题后自动写入 |
| `POST /diagnosis/run` | SELECT quiz_records + INSERT diagnosis_reports | 读历史 → 诊断 → 存报告 |
| `GET /api/users/{id}` | SELECT/INSERT users | 获取或创建用户 |
| `GET /api/users/{id}/history` | SELECT quiz_records | 查询做题历史 |
| `GET /api/users/{id}/stats` | SELECT quiz_records | 统计答题正确率 |
| `GET /api/users/{id}/sessions` | SELECT chat_sessions | 查询历史会话列表 |
| `POST /api/users/{id}/sessions` | INSERT/UPDATE chat_sessions | 创建或更新会话存档 |
| `GET /api/users/{id}/diagnosis` | SELECT diagnosis_reports | 查询历史诊断报告 |

---

## 三、ChromaDB — 向量知识库（笔记/错题）

> 路径：`chroma_userdata/`（可通过 `CHROMA_PERSIST_DIRECTORY` 配置）  
> 管理模块：`knowledge_base/chroma_manager.py`  
> Embedding 模型：`BAAI/bge-m3`（SiliconFlow）

### 集合：`notes`（默认）

每个文档的 metadata 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| subject | TEXT | 学科 |
| type | TEXT | 文档类型（note=笔记 / wrong=错题） |
| date | TEXT | 日期 |

### 涉及 ChromaDB 的 API 操作

| API | 操作 | 说明 |
|-----|------|------|
| `POST /notes/` | upsert | 添加/更新笔记向量 |
| `POST /notes/file` | upsert | 从 Markdown 文件导入笔记 |
| `GET /notes/query` | query | 语义相似度搜索 |
| `DELETE /notes/{id}` | delete | 删除笔记 |
| `POST /api/answer` | query | RAG 检索相关笔记 |
| `POST /diagnosis/run` | query | 推荐相关笔记 |

---

## 四、完整操作汇总（所有需要数据库的场景）

| # | 场景 | 读库 | 写库 |
|---|------|------|------|
| 1 | 随机抽题（刷题模式） | knowledge_base.db | — |
| 2 | 提交答案并批改 | — | userdata.db (quiz_records) |
| 3 | SSE 流式批改 | — | userdata.db (quiz_records) |
| 4 | 查询用户做题历史 | userdata.db | — |
| 5 | 查询用户做题统计 | userdata.db | — |
| 6 | 问答 RAG 召回 | knowledge_base.db + ChromaDB | — |
| 7 | 学习诊断 | userdata.db + knowledge_base.db + ChromaDB | userdata.db (diagnosis_reports) |
| 8 | 查询历史诊断报告 | userdata.db | — |
| 9 | 添加个人笔记 | — | ChromaDB |
| 10 | 语义搜索笔记 | ChromaDB | — |
| 11 | 创建/更新会话存档 | — | userdata.db (chat_sessions) |
| 12 | 查询历史会话 | userdata.db | — |

---

## 五、新增 API 概览

以下为本次重构新增的用户数据相关 API（前缀 `/api/users`）：

```
GET  /api/users/{user_id}               获取用户信息（不存在则自动创建）
GET  /api/users/{user_id}/history       做题历史（支持按学科/数量过滤）
GET  /api/users/{user_id}/stats         做题统计摘要（总数/正确率/学科分布）
GET  /api/users/{user_id}/sessions      历史会话列表
POST /api/users/{user_id}/sessions      创建或更新会话记录
GET  /api/users/{user_id}/diagnosis     历史诊断报告列表
```

---

**最后更新** 2026-03-31  
**工具** GitHub Copilot Coding Agent
