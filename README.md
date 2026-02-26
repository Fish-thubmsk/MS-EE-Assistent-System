# AI 考研辅助系统

> 采用**动静分离的双知识库架构** + **多模式 Agent 工作流**，为考研学生提供智能问答、学习辅导、练习出题和备考规划服务。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI 应用层                            │
│   POST /agent/chat  ·  GET/POST /kb/notes  ·  GET /kb/qa-records│
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────▼────────────┐
              │    AgentWorkflow (路由)    │
              │  根据 mode 分发到对应 Agent │
              └──┬──────┬──────┬────┬───┘
                 │      │      │    │
         ┌───────┘  ┌───┘  ┌──┘  ┌─┘
         ▼          ▼      ▼     ▼
      QAAgent  StudyAgent  PracticeAgent  PlanningAgent
      (问答)    (学习)        (练习)          (规划)
         │          │          │              │
         └──────────┴──────────┴──────────────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
    ┌─────▼──────┐              ┌───────▼──────┐
    │ 静态知识库  │              │  动态知识库   │
    │  (FAISS)   │              │  (SQLite)    │
    │            │              │              │
    │ 预处理的考研 │              │ 用户笔记      │
    │ 知识文档    │              │ 问答历史      │
    │ (只读/离线  │              │ 学习记录      │
    │  更新)     │              │ (实时读写)    │
    └────────────┘              └──────────────┘
```

### 动静分离的双知识库

| 知识库 | 存储技术 | 内容 | 更新策略 |
|--------|---------|------|---------|
| **静态知识库** | FAISS 向量索引 | 考研教材、历年真题、知识点总结 | 离线构建，定期更新 |
| **动态知识库** | SQLite 关系型数据库 | 用户笔记、问答历史、学习记录 | 实时读写 |

### 多模式 Agent 工作流

| 模式 | 标识 | 功能 |
|------|------|------|
| **问答模式** | `qa` | 基于 RAG 的考研知识问答 |
| **学习模式** | `study` | 结构化概念讲解（定义→公式→例题→注意事项） |
| **练习模式** | `practice` | 出题 & 批改（智能识别学生是否在提交答案） |
| **规划模式** | `planning` | 生成个性化备考计划 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env   # 然后填写 OPENAI_API_KEY 等配置
```

或直接设置环境变量：

```bash
export OPENAI_API_KEY=sk-...
export LLM_MODEL=gpt-4o
```

### 3. 启动服务

```bash
uvicorn main:app --reload
```

服务启动后访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看交互式 API 文档。

---

## API 使用示例

### 问答模式

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "qa",
    "query": "什么是导数的定义？",
    "subject": "数学"
  }'
```

### 学习模式

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "study",
    "query": "线性代数中的特征值与特征向量",
    "subject": "数学"
  }'
```

### 练习模式 – 出题

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "practice",
    "query": "极限与连续",
    "subject": "数学"
  }'
```

### 练习模式 – 提交答案

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "practice",
    "query": "我的答案：极限是当自变量趋近某值时函数值的趋向。",
    "subject": "数学"
  }'
```

### 规划模式

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "planning",
    "query": "目标院校985，考试日期12月底，数学基础较弱，每天可学习6小时，请制定备考计划。"
  }'
```

### 向静态知识库导入文档

```bash
curl -X POST http://localhost:8000/kb/documents \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {"content": "极限的定义：...", "metadata": {"subject": "数学", "source": "高等数学第七版"}},
      {"content": "导数的定义：...", "metadata": {"subject": "数学"}}
    ],
    "save": true
  }'
```

---

## 项目结构

```
.
├── config.py                  # 配置（支持 .env）
├── main.py                    # FastAPI 应用入口
├── requirements.txt
├── knowledge_base/
│   ├── static_kb.py           # 静态知识库（FAISS）
│   └── dynamic_kb.py          # 动态知识库（SQLite）
├── agents/
│   ├── __init__.py            # AgentWorkflow 路由器
│   ├── base_agent.py          # 抽象基类（RAG + 消息构建）
│   ├── qa_agent.py            # 问答模式
│   ├── study_agent.py         # 学习模式
│   ├── practice_agent.py      # 练习模式
│   └── planning_agent.py      # 规划模式
├── models/
│   └── schemas.py             # Pydantic 数据模型
├── tests/
│   ├── test_knowledge_base.py
│   └── test_agents.py
└── data/                      # 运行时数据目录（git 忽略）
    ├── static_kb/             # FAISS 索引
    └── dynamic_kb.db          # SQLite 数据库
```

---

## 运行测试

```bash
pytest tests/ -v
```

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OPENAI_API_KEY` | `""` | OpenAI / 兼容 API 密钥 |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | API 基础 URL（支持国内代理） |
| `LLM_MODEL` | `gpt-3.5-turbo` | 使用的 LLM 模型 |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 本地 Embedding 模型 |
| `STATIC_KB_PATH` | `data/static_kb` | FAISS 索引持久化路径 |
| `DYNAMIC_KB_DB_URL` | `sqlite:///data/dynamic_kb.db` | 动态 KB 数据库连接字符串 |
| `TOP_K` | `4` | RAG 检索返回的文档数 |
