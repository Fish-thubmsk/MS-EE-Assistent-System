# 考研智能辅导系统 API 测试手册

> **测试地址**：[http://127.0.0.1:8000/docs#/](http://127.0.0.1:8000/docs#/)  
> **交互文档（ReDoc）**：[http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)  
> **OpenAPI JSON**：[http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

---

## 目录

1. [快速启动](#快速启动)
2. [全局说明](#全局说明)
3. [健康检查（health）](#1-健康检查-health)
4. [用户认证（auth）](#2-用户认证-auth)
   - 4.1 [用户注册](#21-post-apiauthregister--用户注册)
   - 4.2 [用户登录](#22-post-apiauthlogin--用户登录)
   - 4.3 [获取当前用户信息](#23-get-apiauthme--获取当前用户信息)
5. [笔记管理（notes）](#3-笔记管理-notes)
   - 5.1 [新增/更新笔记（文本）](#31-post-notes--新增或更新笔记文本)
   - 5.2 [从文件新增笔记](#32-post-notesfile--从文件新增笔记)
   - 5.3 [删除笔记](#33-delete-notesdoc_id--删除笔记)
   - 5.4 [向量检索笔记](#34-get-notesquery--向量相似度检索)
   - 5.5 [获取笔记总数](#35-get-notescount--获取笔记总数)
6. [聊天路由（chat）](#4-聊天路由-chat)
   - 6.1 [意图识别与路由](#41-post-chatroute--意图识别与路由)
7. [学习诊断（diagnosis）](#5-学习诊断-diagnosis)
   - 7.1 [运行诊断](#51-post-diagnosisrun--运行学习诊断)
   - 7.2 [Mock 诊断演示](#52-get-diagnosismock--mock-诊断演示)
8. [RAG 问答（answer）](#6-rag-问答-answer)
   - 8.1 [同步问答](#61-post-apianswer--rag-同步问答)
   - 8.2 [SSE 流式问答](#62-post-apianswerstream--sse-流式问答)
   - 8.3 [Mock 问答演示](#63-get-apianswermock--mock-问答演示)
9. [刷题练习（practice）](#7-刷题练习-practice)
   - 9.1 [获取科目列表](#71-get-apipracticesubjects--获取科目列表)
   - 9.2 [获取题型列表](#72-get-apipracticetypessubject--获取题型列表)
   - 9.3 [获取年份列表](#73-get-apipracticeyearssubject--获取年份列表)
   - 9.4 [随机获取题目](#74-get-apipracticequestion--随机获取题目)
   - 9.5 [提交答案并批改](#75-post-apipractice--提交答案并批改)
   - 9.6 [SSE 流式批改](#76-post-apipracticestream--sse-流式批改)
10. [错误码说明](#错误码说明)
11. [完整测试流程示例](#完整测试流程示例)

---

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制 .env.example 并填写）
cp .env.example .env
# 编辑 .env，至少填写 SILICONFLOW_API_KEY 和 LLM_MODEL

# 3. 启动后端服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 4. 浏览器打开 Swagger UI
# http://127.0.0.1:8000/docs#/
```

---

## 全局说明

| 项目 | 说明 |
|------|------|
| Base URL | `http://127.0.0.1:8000` |
| 数据格式 | JSON（`Content-Type: application/json`） |
| 认证方式 | Bearer Token（JWT），在 `/docs` 页面右上角点击 **Authorize** 输入 `Bearer <token>` |
| 流式响应 | 部分接口支持 SSE（Server-Sent Events），Swagger UI 不直接显示流式内容，建议用 `curl` 测试 |

### 如何在 Swagger UI 中使用 JWT 认证

1. 先调用 `POST /api/auth/login` 或 `POST /api/auth/register`，复制响应中的 `access_token`。
2. 点击页面右上角 **Authorize 🔒** 按钮。
3. 在弹窗的 **Value** 栏中输入 `Bearer <你的token>`，例如：`Bearer eyJhbGciOiJI...`
4. 点击 **Authorize** → **Close**，后续带锁标记（🔒）的接口将自动携带 Token。

---

## 1. 健康检查 (health)

### 1.1 `GET /` — 根路由健康检查

**用途**：确认服务是否正常运行。

**请求参数**：无

**响应示例**：

```json
{
  "status": "ok"
}
```

**Swagger 测试步骤**：
1. 在 `/docs` 页面找到 `GET /` 接口（`health` 标签）。
2. 点击 **Try it out** → **Execute**。
3. 预期响应状态码：`200`，响应体：`{"status": "ok"}`。

---

### 1.2 `GET /health` — 详细健康检查

**用途**：返回服务版本和运行状态，适合运维监控。

**请求参数**：无

**响应示例**：

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

**Swagger 测试步骤**：
1. 找到 `GET /health` 接口（`health` 标签）。
2. 点击 **Try it out** → **Execute**。
3. 预期响应：`200`，包含 `status` 和 `version` 字段。

---

## 2. 用户认证 (auth)

### 2.1 `POST /api/auth/register` — 用户注册

**用途**：注册新用户，注册成功后直接返回 JWT Token，无需再次登录。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名（3–50 字符） |
| `password` | string | ✅ | 密码（至少 6 位） |
| `display_name` | string | ❌ | 昵称（最多 100 字符） |
| `email` | string | ❌ | 邮箱地址 |

**请求体示例**：

```json
{
  "username": "testuser",
  "password": "test123456",
  "display_name": "测试用户",
  "email": "test@example.com"
}
```

**响应示例**（`201 Created`）：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": 1,
  "username": "testuser",
  "display_name": "测试用户"
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `409 Conflict` | 用户名已存在 |
| `422 Unprocessable Entity` | 请求参数校验失败（如密码太短） |

**Swagger 测试步骤**：
1. 展开 `POST /api/auth/register`。
2. 点击 **Try it out**，在请求体中填入上方示例 JSON。
3. 点击 **Execute**。
4. 预期响应状态码 `201`，复制 `access_token` 备用。

---

### 2.2 `POST /api/auth/login` — 用户登录

**用途**：使用用户名 + 密码登录，返回 JWT Token（默认有效期 24 小时）。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `password` | string | ✅ | 密码 |

**请求体示例**：

```json
{
  "username": "testuser",
  "password": "test123456"
}
```

**响应示例**（`200 OK`）：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": 1,
  "username": "testuser",
  "display_name": "测试用户"
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `401 Unauthorized` | 用户名或密码错误 |

**Swagger 测试步骤**：
1. 展开 `POST /api/auth/login`。
2. 点击 **Try it out**，填入用户名和密码。
3. 点击 **Execute**，复制返回的 `access_token`。
4. 点击页面顶部 **Authorize 🔒**，输入 `Bearer <token>` 完成认证。

---

### 2.3 `GET /api/auth/me` — 获取当前用户信息

**用途**：返回当前已认证用户的基本信息。**需要 JWT Token。**

**请求参数**：无（通过请求头携带 Token）

**响应示例**（`200 OK`）：

```json
{
  "user_id": 1,
  "username": "testuser",
  "display_name": "测试用户",
  "email": "test@example.com",
  "created_at": "2024-01-01T12:00:00Z"
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `401 Unauthorized` | 未携带 Token 或 Token 无效/过期 |
| `404 Not Found` | 用户不存在 |

**Swagger 测试步骤**：
1. 确保已通过 **Authorize** 设置了 Bearer Token（见[全局说明](#全局说明)）。
2. 展开 `GET /api/auth/me`。
3. 点击 **Try it out** → **Execute**。
4. 预期响应 `200`，包含当前用户信息。

---

## 3. 笔记管理 (notes)

> 笔记存储在 ChromaDB 向量数据库中，支持语义检索。

### 3.1 `POST /notes/` — 新增或更新笔记（文本）

**用途**：将笔记文本向量化并存入 ChromaDB，若 `doc_id` 已存在则更新。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | ✅ | Markdown 格式笔记内容 |
| `doc_id` | string | ❌ | 文档 ID（不填则自动生成） |
| `metadata` | object | ❌ | 附加元数据，如 `{"subject": "数学", "type": "note"}` |

**请求体示例**：

```json
{
  "content": "# 极限的定义\n\n设函数 f(x) 在 x₀ 的某个去心邻域内有定义，若对任意 ε > 0，存在 δ > 0，使得当 0 < |x - x₀| < δ 时，|f(x) - L| < ε，则称 L 为 f(x) 在 x₀ 处的极限。",
  "doc_id": "math_limit_001",
  "metadata": {
    "subject": "数学",
    "type": "note",
    "chapter": "第一章 极限"
  }
}
```

**响应示例**（`200 OK`）：

```json
{
  "doc_id": "math_limit_001",
  "message": "笔记已成功存入 ChromaDB"
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `400 Bad Request` | 内容为空或格式错误 |
| `500 Internal Server Error` | 向量化或存储失败（通常是 ChromaDB 未初始化或 Embedding API 不可用） |

**Swagger 测试步骤**：
1. 展开 `POST /notes/`。
2. 点击 **Try it out**，在请求体中填入示例 JSON。
3. 点击 **Execute**，预期返回 `200` 及 `doc_id`。

---

### 3.2 `POST /notes/file` — 从文件新增笔记

**用途**：读取服务器上的 `.md` 文件，向量化后存入 ChromaDB。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | ✅ | Markdown 文件的绝对或相对路径 |

**请求体示例**：

```json
{
  "file_path": "mock_notes/math_note.md"
}
```

**响应示例**（`200 OK`）：

```json
{
  "doc_id": "math_note",
  "message": "文件 mock_notes/math_note.md 已存入 ChromaDB"
}
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `404 Not Found` | 文件不存在 |
| `400 Bad Request` | 文件内容为空或格式错误 |
| `500 Internal Server Error` | 处理失败 |

**Swagger 测试步骤**：
1. 展开 `POST /notes/file`。
2. 点击 **Try it out**，填入文件路径（需要是服务器上存在的文件路径，如项目中 `mock_notes/` 目录下的文件）。
3. 点击 **Execute**。

---

### 3.3 `DELETE /notes/{doc_id}` — 删除笔记

**用途**：删除 ChromaDB 中指定 `doc_id` 的笔记。

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `doc_id` | string | ✅ | 要删除的文档唯一 ID |

**响应示例**（`200 OK`）：

```json
{
  "message": "笔记 math_limit_001 已删除"
}
```

**Swagger 测试步骤**：
1. 展开 `DELETE /notes/{doc_id}`。
2. 点击 **Try it out**，在 `doc_id` 参数框填入要删除的 ID（如 `math_limit_001`）。
3. 点击 **Execute**，预期返回 `200`。

---

### 3.4 `GET /notes/query` — 向量相似度检索

**用途**：根据查询文本进行向量语义检索，支持按学科和类型过滤。

**查询参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `q` | string | ✅ | — | 查询文本 |
| `n` | int | ❌ | `5` | 返回结果数量（1–50） |
| `subject` | string | ❌ | — | 按学科过滤，如 `数学`、`政治`、`英语` |
| `type` | string | ❌ | — | 按笔记类型过滤：`note` 或 `wrong` |

**请求示例（URL）**：

```
GET /notes/query?q=极限的定义&n=3&subject=数学
```

**响应示例**（`200 OK`）：

```json
{
  "results": [
    {
      "id": "math_limit_001",
      "document": "# 极限的定义\n\n设函数 f(x) 在 x₀ 的某个去心邻域内有定义...",
      "metadata": {
        "subject": "数学",
        "type": "note",
        "chapter": "第一章 极限"
      },
      "distance": 0.1234
    }
  ]
}
```

**Swagger 测试步骤**：
1. 展开 `GET /notes/query`。
2. 点击 **Try it out**。
3. 在 `q` 参数中填入查询文本，如 `极限`；可选填 `n`、`subject`、`type`。
4. 点击 **Execute**，查看语义检索结果。

> **注意**：`distance` 越小表示越相似（余弦距离）。

---

### 3.5 `GET /notes/count` — 获取笔记总数

**用途**：返回 ChromaDB 中当前存储的笔记总数。

**请求参数**：无

**响应示例**（`200 OK`）：

```json
{
  "count": 42
}
```

**Swagger 测试步骤**：
1. 展开 `GET /notes/count`。
2. 点击 **Try it out** → **Execute**。
3. 预期返回 `200`，包含 `count` 字段。

---

## 4. 聊天路由 (chat)

### 4.1 `POST /chat/route` — 意图识别与路由

**用途**：接收用户输入，识别意图（quiz/qa/diagnosis）并返回路由结果。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_input` | string | ✅ | 当前用户输入文本 |
| `messages` | array | ❌ | 历史对话消息列表（`[{"role": "user/assistant", "content": "..."}]`） |
| `session_history` | array | ❌ | 历史会话模式记录（用于跨轮次模式切换） |
| `multimodal_attachments` | array | ❌ | 多模态附件（预留接口） |

**请求体示例 1（刷题意图）**：

```json
{
  "user_input": "我想做几道数学真题练练手",
  "messages": [],
  "session_history": []
}
```

**请求体示例 2（问答意图）**：

```json
{
  "user_input": "帮我解释一下什么是矩阵的秩",
  "messages": [
    {"role": "user", "content": "我想了解线性代数"},
    {"role": "assistant", "content": "线性代数是数学的一个分支..."}
  ],
  "session_history": []
}
```

**请求体示例 3（诊断意图）**：

```json
{
  "user_input": "分析一下我最近的薄弱知识点",
  "messages": [],
  "session_history": []
}
```

**响应示例**（`200 OK`）：

```json
{
  "mode": "quiz",
  "sub_mode": null,
  "params": {
    "subject": "数学"
  },
  "intent_confidence": 0.92,
  "messages": [
    {"role": "user", "content": "我想做几道数学真题练练手"}
  ],
  "session_history": [
    {"mode": "quiz", "timestamp": "..."}
  ],
  "mode_description": "刷题模式：追问、批改、讲解"
}
```

**mode 枚举值说明**：

| mode | 说明 |
|------|------|
| `quiz` | 刷题模式（追问 / 批改 / 讲解） |
| `qa` | 问答模式（知识点查询 / 概念解释） |
| `diagnosis` | 诊断模式（学习轨迹 / 弱项分析） |
| `unknown` | 未识别到明确意图 |

**Swagger 测试步骤**：
1. 展开 `POST /chat/route`。
2. 点击 **Try it out**，填入示例 JSON（三种意图都可以测试）。
3. 点击 **Execute**，观察 `mode` 和 `intent_confidence` 字段。

---

## 5. 学习诊断 (diagnosis)

### 5.1 `POST /diagnosis/run` — 运行学习诊断

**用途**：分析用户做题历史，识别薄弱知识点，生成个性化推荐与诊断报告。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_id` | string | ❌ | `"user_001"` | 用户 ID |
| `subject` | string | ❌ | — | 限定分析学科（`数学`/`政治`/`英语`） |
| `history_records` | array | ❌ | `[]` | 做题历史记录（空则自动从数据库或 mock 数据读取） |
| `weak_threshold` | float | ❌ | `0.6` | 薄弱点准确率阈值（低于此值视为薄弱，范围 0.0–1.0） |
| `recommend_per_point` | int | ❌ | `3` | 每个薄弱点推荐题目数（1–10） |

**history_records 单条格式**：

```json
{
  "question_id": 101,
  "subject": "数学",
  "knowledge_point": "极限",
  "is_correct": false,
  "difficulty": "medium",
  "answered_at": "2024-01-15T10:30:00"
}
```

**请求体示例（传入历史记录）**：

```json
{
  "user_id": "student_001",
  "subject": "数学",
  "history_records": [
    {
      "question_id": 1,
      "subject": "数学",
      "knowledge_point": "极限",
      "is_correct": false,
      "difficulty": "medium"
    },
    {
      "question_id": 2,
      "subject": "数学",
      "knowledge_point": "极限",
      "is_correct": false,
      "difficulty": "easy"
    },
    {
      "question_id": 3,
      "subject": "数学",
      "knowledge_point": "导数",
      "is_correct": true,
      "difficulty": "medium"
    }
  ],
  "weak_threshold": 0.6,
  "recommend_per_point": 3
}
```

**请求体示例（空历史，使用 mock 数据）**：

```json
{
  "user_id": "user_001",
  "history_records": []
}
```

**响应示例**（`200 OK`）：

```json
{
  "user_id": "student_001",
  "subject": "数学",
  "weak_points": [
    {
      "knowledge_point": "极限",
      "subject": "数学",
      "accuracy": 0.0,
      "total_attempts": 2,
      "priority": "high"
    }
  ],
  "recommended_questions": [
    {
      "id": 5,
      "subject": "数学",
      "knowledge_point": "极限",
      "content": "计算极限 lim(x→0) sinx/x",
      "difficulty_level": "easy",
      "correct_answer": "1"
    }
  ],
  "recommended_notes": [],
  "report": "## 学习诊断报告\n\n### 薄弱知识点分析\n\n您在「极限」方面的准确率为 0.0%，建议重点复习..."
}
```

**Swagger 测试步骤**：
1. 展开 `POST /diagnosis/run`。
2. 点击 **Try it out**，可以先用空的 `history_records` 测试（自动使用 mock 数据）。
3. 点击 **Execute**，查看 `weak_points`、`recommended_questions`、`report` 字段。

---

### 5.2 `GET /diagnosis/mock` — Mock 诊断演示

**用途**：使用内置 mock 用户数据（`user_001`）快速体验学习诊断，无需传参。

**请求参数**：无

**响应示例**（`200 OK`）：

```json
{
  "user_id": "user_001",
  "subject": null,
  "weak_points": [...],
  "recommended_questions": [...],
  "recommended_notes": [...],
  "report": "## 学习诊断报告\n\n..."
}
```

**Swagger 测试步骤**：
1. 展开 `GET /diagnosis/mock`。
2. 点击 **Try it out** → **Execute**。
3. 直接查看诊断结果，无需填写任何参数。

---

## 6. RAG 问答 (answer)

### 6.1 `POST /api/answer` — RAG 同步问答

**用途**：通过 RAG 流程（FAISS 知识库检索 + ChromaDB 笔记检索 + LLM 生成）返回完整答案。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_input` | string | ✅ | — | 用户问题 |
| `messages` | array | ❌ | `[]` | 历史对话消息列表（`[{"role": "...", "content": "..."}]`） |
| `params` | object | ❌ | `{}` | 路由参数（如 `{"subject": "数学", "year": 2023}`） |
| `use_faiss` | boolean | ❌ | `true` | 是否检索 FAISS 静态知识库 |
| `use_chroma` | boolean | ❌ | `false` | 是否检索 Chroma 动态笔记库 |
| `use_rrf` | boolean | ❌ | `false` | 是否启用 RRF 融合 |
| `rrf_k` | int | ❌ | `60` | RRF 融合参数（1–200） |
| `use_rerank` | boolean | ❌ | `false` | 是否启用重排模型 |
| `rerank_model` | string | ❌ | `Pro/BAAI/bge-reranker-v2-m3` | 重排模型名称 |
| `rerank_top_n` | int | ❌ | `5` | 参与重排的候选数量（1–20） |
| `n_faiss_results` | int | ❌ | `5` | FAISS 返回结果数（1–20） |
| `n_chroma_results` | int | ❌ | `3` | Chroma 返回结果数（1–10） |
| `chroma_filter` | object | ❌ | `null` | Chroma 元数据过滤（如 `{"subject": "数学"}`） |

**请求体示例（基础问答）**：

```json
{
  "user_input": "什么是导数的几何意义？",
  "use_faiss": true,
  "use_chroma": false
}
```

**请求体示例（融合个人笔记）**：

```json
{
  "user_input": "马克思主义哲学的基本原理是什么？",
  "use_faiss": true,
  "use_chroma": true,
  "use_rrf": true,
  "rrf_k": 60,
  "use_rerank": true,
  "rerank_model": "Pro/BAAI/bge-reranker-v2-m3",
  "rerank_top_n": 5,
  "chroma_filter": {"subject": "政治"},
  "n_chroma_results": 3
}
```

**请求体示例（带历史对话）**：

```json
{
  "user_input": "那它在物理学中有什么应用？",
  "messages": [
    {"role": "user", "content": "什么是导数？"},
    {"role": "assistant", "content": "导数是函数在某点处的瞬时变化率..."}
  ],
  "use_faiss": true,
  "use_chroma": false
}
```

**响应示例**（`200 OK`）：

```json
{
  "answer": "导数的几何意义是曲线在该点处切线的斜率 [1]。\n\n设函数 y=f(x) 的图像上有一点 P(x₀, f(x₀))，导数 f'(x₀) 就是曲线在点 P 处的切线斜率。",
  "citations": [
    {
      "index": 1,
      "source": "高等数学知识库",
      "doc_id": "math_derivative_001",
      "content_snippet": "导数 f'(x₀) 表示函数在点 x₀ 处的瞬时变化率，几何上是切线斜率...",
      "metadata": {"subject": "数学", "type": "note"}
    }
  ],
  "recommendations": [
    {
      "doc_id": "math_derivative_002",
      "content_snippet": "导数应用：极值问题、单调性判断...",
      "subject": "数学",
      "year": "2022",
      "score": 0.87
    }
  ],
  "messages": [
    {"role": "user", "content": "什么是导数的几何意义？"},
    {"role": "assistant", "content": "导数的几何意义是曲线在该点处切线的斜率..."}
  ]
}
```

> **注意**：若未配置 `SILICONFLOW_API_KEY`，系统将降级为基于检索结果的模板答案，`answer` 字段会说明这是降级模式。

**Swagger 测试步骤**：
1. 展开 `POST /api/answer`。
2. 点击 **Try it out**，填入请求体。
3. 点击 **Execute**，等待响应（可能耗时 5–30 秒，取决于 LLM API 响应速度）。
4. 查看 `answer`（答案）、`citations`（引用溯源）、`recommendations`（推荐题目）。

---

### 6.2 `POST /api/answer/stream` — SSE 流式问答

**用途**：以 Server-Sent Events（SSE）方式逐 token 流式返回 LLM 生成内容。

**请求体**：与 `POST /api/answer` 相同。

**SSE 事件类型说明**：

| 事件 | data 格式 | 说明 |
|------|-----------|------|
| `event: token` | `{"token": "..."}` | 单个 token 或文本片段 |
| `event: done` | `{"status": "done"}` | 生成完毕 |
| `event: error` | `{"error": "..."}` | 发生错误 |

> **注意**：Swagger UI 不适合测试 SSE 流式接口，推荐使用 `curl` 命令：

**curl 测试命令**：

```bash
curl -N -X POST "http://127.0.0.1:8000/api/answer/stream" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "什么是矩阵的行列式？", "use_faiss": true}' \
  --no-buffer
```

**预期输出**（SSE 流）：

```
event: token
data: {"token": "行"}

event: token
data: {"token": "列"}

event: token
data: {"token": "式"}

...

event: done
data: {"status": "done"}
```

**Swagger 测试步骤**：
1. 展开 `POST /api/answer/stream`。
2. 点击 **Try it out**，填入与同步问答相同的请求体。
3. 点击 **Execute**（Swagger UI 会显示原始 SSE 文本，但不会逐步显示流式效果）。
4. 建议改用上方 `curl` 命令查看真实流式效果。

---

### 6.3 `GET /api/answer/mock` — Mock 问答演示

**用途**：使用内置 mock 数据（问题：「什么是极限？」）快速体验问答，无需任何配置。

**请求参数**：无

**响应示例**（`200 OK`）：

```json
{
  "answer": "极限是微积分的核心概念...",
  "citations": [],
  "recommendations": [],
  "messages": [
    {"role": "user", "content": "什么是极限？"},
    {"role": "assistant", "content": "极限是微积分的核心概念..."}
  ]
}
```

**Swagger 测试步骤**：
1. 展开 `GET /api/answer/mock`。
2. 点击 **Try it out** → **Execute**。
3. 无需配置 API Key，直接查看问答结果。

---

### 6.4 `POST /api/answer/test/retrieval` — 检索重排测试

**用途**：专门用于测试检索与重排链路，返回重排前/后的候选顺序，方便比较：
- 仅 FAISS
- 仅 Chroma
- FAISS + Chroma
- FAISS + Chroma + Rerank

**请求体**：与 `POST /api/answer` 相同。

**请求体示例（启用重排）**：

```json
{
  "user_input": "导数的几何意义是什么？",
  "use_faiss": true,
  "use_chroma": true,
  "use_rerank": true,
  "rerank_model": "Pro/BAAI/bge-reranker-v2-m3",
  "rerank_top_n": 5
}
```

**响应关键字段**：
- `before_rerank`: 重排前顺序
- `after_rerank`: 重排后顺序

**Swagger 测试步骤**：
1. 展开 `POST /api/answer/test/retrieval`。
2. 点击 **Try it out**，填入请求体。
3. 分别切换 `use_faiss/use_chroma/use_rerank`，对比 `before_rerank` 与 `after_rerank`。

---

### 6.5 `POST /api/answer/test/fusion` — 融合策略测试（新增）

**用途**：比较默认融合（按 score 排序）和 RRF 融合的结果差异。

**请求体示例**：

```json
{
  "user_input": "导数的几何意义是什么？",
  "use_faiss": true,
  "use_chroma": true,
  "rrf_k": 60
}
```

**响应关键字段**：
- `default_fusion`: 默认融合结果
- `rrf_fusion`: RRF 融合结果

---

## 7. 刷题练习 (practice)

### 7.1 `GET /api/practice/subjects` — 获取科目列表

**用途**：返回支持的考研科目列表。

**请求参数**：无

**响应示例**（`200 OK`）：

```json
[
  {"id": "politics", "name": "政治", "icon": "🏛️"},
  {"id": "math",     "name": "数学", "icon": "📐"},
  {"id": "english",  "name": "英语", "icon": "📚"}
]
```

**Swagger 测试步骤**：
1. 展开 `GET /api/practice/subjects`。
2. 点击 **Try it out** → **Execute**。
3. 预期返回三个科目对象。

---

### 7.2 `GET /api/practice/types/{subject}` — 获取题型列表

**用途**：返回指定科目支持的题型列表。

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `subject` | string | ✅ | 科目 ID：`politics`、`math`、`english` |

**响应示例（politics）**：

```json
[
  {"id": "单选题", "name": "单选题"},
  {"id": "多选题", "name": "多选题"},
  {"id": "材料分析题", "name": "材料分析题"}
]
```

**响应示例（math）**：

```json
[
  {"id": "single_choice", "name": "单选题"},
  {"id": "fill_blank",    "name": "填空题"},
  {"id": "subjective",    "name": "解答题"}
]
```

**响应示例（english）**：

```json
[
  {"id": "cloze",         "name": "完形填空"},
  {"id": "reading",       "name": "阅读理解"},
  {"id": "new_type",      "name": "新题型"},
  {"id": "translation",   "name": "翻译"},
  {"id": "writing_small", "name": "小作文"},
  {"id": "writing_large", "name": "大作文"}
]
```

**错误响应**：

| 状态码 | 说明 |
|--------|------|
| `404 Not Found` | 科目 ID 不存在 |

**Swagger 测试步骤**：
1. 展开 `GET /api/practice/types/{subject}`。
2. 点击 **Try it out**，在 `subject` 中分别填入 `politics`、`math`、`english` 进行测试。
3. 点击 **Execute**，查看对应题型列表。

---

### 7.3 `GET /api/practice/years/{subject}` — 获取年份列表

**用途**：返回指定科目在数据库中有数据的年份列表（降序排列）。

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `subject` | string | ✅ | 科目 ID：`politics`、`math`、`english` |

**响应示例**（`200 OK`）：

```json
[2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016]
```

**Swagger 测试步骤**：
1. 展开 `GET /api/practice/years/{subject}`。
2. 点击 **Try it out**，填入科目 ID（如 `math`）。
3. 点击 **Execute**，查看可用年份列表。

---

### 7.4 `GET /api/practice/question` — 随机获取题目

**用途**：从知识库数据库随机抽取一道题目，支持按科目、题型、年份筛选。若数据库不可用则降级为 mock 题目。

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `subject` | string | ❌ | 科目 ID：`politics`、`math`、`english`（不传则随机） |
| `question_type` | string | ❌ | 题型 ID（与科目对应，参考 7.2 节） |
| `year` | int | ❌ | 年份（如 `2022`），不传则全库随机 |

**请求示例（URL）**：

```
# 获取任意题目
GET /api/practice/question

# 获取政治单选题
GET /api/practice/question?subject=politics&question_type=单选题

# 获取 2022 年数学单选题
GET /api/practice/question?subject=math&question_type=single_choice&year=2022

# 获取英语阅读理解题
GET /api/practice/question?subject=english&question_type=reading
```

**响应示例（政治单选题）**（`200 OK`）：

```json
{
  "id": 1023,
  "subject": "政治",
  "year": 2022,
  "question_type": "单选题",
  "content": "下列关于马克思主义哲学的论述，正确的是（  ）",
  "options": {
    "A": "物质决定意识，意识对物质具有反作用",
    "B": "意识是物质的派生物，不具有主观能动性",
    "C": "物质和意识是完全独立的两种实体",
    "D": "意识可以脱离物质而独立存在"
  },
  "correct_answer": "A",
  "analysis": "马克思主义哲学认为，物质决定意识，意识是物质的反映，同时意识对物质具有能动的反作用。",
  "passage_text": null,
  "knowledge_points": [],
  "sub_questions": []
}
```

**响应示例（英语阅读题）**（`200 OK`）：

```json
{
  "id": 5601,
  "subject": "英语",
  "year": 2021,
  "question_type": "阅读理解",
  "content": "第 1 题",
  "options": {
    "A": "It is a sign of social inequality.",
    "B": "It has changed people's reading habits.",
    "C": "It will eventually disappear.",
    "D": "It reflects people's curiosity."
  },
  "correct_answer": "B",
  "analysis": "文章第二段提到...",
  "passage_text": "The COVID-19 pandemic has dramatically altered...",
  "knowledge_points": [],
  "sub_questions": []
}
```

**Swagger 测试步骤**：
1. 展开 `GET /api/practice/question`。
2. 点击 **Try it out**。
3. 可尝试以下几种组合：
   - 不填任何参数（随机任意题）
   - `subject=politics` + `question_type=单选题`
   - `subject=math` + `question_type=single_choice` + `year=2022`
   - `subject=english` + `question_type=reading`
4. 点击 **Execute**，观察返回题目的结构。

---

### 7.5 `POST /api/practice` — 提交答案并批改

**用途**：提交用户答案，运行 Quiz Agent 批改，返回判断结果、解析和追问建议。支持 LLM 智能批改和规则批改两种模式。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_id` | string | ❌ | `"guest"` | 用户 ID（用于保存答题记录） |
| `user_input` | string | ✅ | — | 用户答案或输入文本 |
| `current_question` | object | ❌ | mock 题 | 当前题目（含 `content`、`correct_answer`、`analysis`、`knowledge_points` 等字段） |
| `user_answer` | string | ❌ | — | 明确指定的用户答案（不传则取 `user_input`） |
| `messages` | array | ❌ | `[]` | 历史对话消息 |
| `quiz_history` | array | ❌ | `[]` | 历史刷题记录 |
| `params` | object | ❌ | `{}` | 路由参数（如 `{"subject": "数学"}`） |

**请求体示例（选择题提交）**：

```json
{
  "user_id": "student_001",
  "user_input": "A",
  "user_answer": "A",
  "current_question": {
    "id": 1023,
    "subject": "政治",
    "year": 2022,
    "question_type": "单选题",
    "content": "下列关于马克思主义哲学的论述，正确的是（  ）",
    "options": {
      "A": "物质决定意识，意识对物质具有反作用",
      "B": "意识是物质的派生物，不具有主观能动性",
      "C": "物质和意识是完全独立的两种实体",
      "D": "意识可以脱离物质而独立存在"
    },
    "correct_answer": "A",
    "analysis": "马克思主义哲学认为，物质决定意识...",
    "knowledge_points": ["唯物论", "意识与物质的关系"]
  },
  "messages": [],
  "quiz_history": []
}
```

**请求体示例（最简化测试，不传题目，使用 mock 题）**：

```json
{
  "user_input": "B",
  "user_answer": "B"
}
```

**响应示例**（`200 OK`）：

```json
{
  "grade_result": {
    "is_correct": true,
    "score": 100,
    "feedback": "回答正确！A 选项准确描述了唯物辩证法的基本观点。"
  },
  "explanation": "## 解析\n\n马克思主义哲学的基本立场是唯物主义。物质是第一性的，意识是第二性的，物质决定意识。但同时，意识对物质具有能动的反作用，这体现了辩证唯物主义的核心观点。\n\nB、C、D 选项分别存在以下错误：\n- B：意识确实具有主观能动性\n- C：物质和意识不是完全独立的\n- D：意识不能脱离物质存在",
  "followup_questions": [
    "意识的能动作用体现在哪些方面？",
    "什么是矛盾的对立统一规律？"
  ],
  "messages": [
    {"role": "user", "content": "A"},
    {"role": "assistant", "content": "回答正确！A 选项准确描述了唯物辩证法的基本观点。"}
  ],
  "quiz_history": [
    {
      "question_id": 1023,
      "subject": "政治",
      "is_correct": true,
      "user_answer": "A",
      "timestamp": "2024-01-15T10:30:00"
    }
  ]
}
```

**Swagger 测试步骤**：
1. **第一步**：先调用 `GET /api/practice/question` 获取一道题，复制完整的题目 JSON。
2. **第二步**：展开 `POST /api/practice`，点击 **Try it out**。
3. 将第一步获取的题目作为 `current_question` 填入请求体，并填写自己的答案。
4. 点击 **Execute**，查看批改结果、解析和追问建议。

---

### 7.6 `POST /api/practice/stream` — SSE 流式批改

**用途**：先同步运行 Quiz Agent 批改，然后以 SSE 流式返回解析文字（打字机效果）。

**请求体**：与 `POST /api/practice` 相同。

**SSE 事件类型说明**：

| 事件 | data 格式 | 说明 |
|------|-----------|------|
| `event: meta` | `{"grade_result": {...}, "followup_questions": [...]}` | 首帧，携带批改结果摘要 |
| `event: token` | `{"token": "..."}` | 解析文字逐字符 |
| `event: done` | `{"status": "done"}` | 流式结束 |

**curl 测试命令**：

```bash
curl -N -X POST "http://127.0.0.1:8000/api/practice/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "A",
    "user_answer": "A",
    "current_question": {
      "id": 1,
      "subject": "数学",
      "content": "求极限 lim(x→0) sinx/x",
      "correct_answer": "1",
      "analysis": "利用等价无穷小替换，sinx ~ x (x→0)，所以极限为 1",
      "knowledge_points": ["极限", "等价无穷小"]
    }
  }' \
  --no-buffer
```

**预期输出**（SSE 流）：

```
event: meta
data: {"grade_result": {"is_correct": true, "score": 100, "feedback": "回答正确！"}, "followup_questions": ["..."] }

event: token
data: {"token": "解"}

event: token
data: {"token": "析"}

...

event: done
data: {"status": "done"}
```

**Swagger 测试步骤**：
1. 展开 `POST /api/practice/stream`。
2. 点击 **Try it out**，填入与 `POST /api/practice` 相同的请求体。
3. 点击 **Execute**（Swagger 显示原始 SSE 文本）。
4. 建议用 `curl` 命令查看真实流式效果。

---

## 错误码说明

| HTTP 状态码 | 说明 | 常见原因 |
|------------|------|---------|
| `200 OK` | 请求成功 | — |
| `201 Created` | 资源创建成功 | 注册新用户 |
| `400 Bad Request` | 请求参数错误 | 缺少必填字段、格式不正确 |
| `401 Unauthorized` | 未认证或认证失败 | Token 未提供、已过期或签名错误 |
| `404 Not Found` | 资源不存在 | 用户不存在、文件未找到、科目 ID 错误 |
| `409 Conflict` | 资源冲突 | 注册时用户名已存在 |
| `422 Unprocessable Entity` | 参数校验失败 | 字段类型错误、长度超限、值超出范围 |
| `500 Internal Server Error` | 服务内部错误 | 数据库不可用、LLM API 调用失败、向量化失败 |

---

## 完整测试流程示例

下面是一个从注册到完整刷题的端到端测试流程，可在 Swagger UI 中逐步执行：

### Step 1：注册账号

```json
POST /api/auth/register
{
  "username": "exam_student",
  "password": "studyhard2024",
  "display_name": "考研人",
  "email": "student@exam.com"
}
```

复制返回的 `access_token`，点击 **Authorize** 输入 `Bearer <token>`。

---

### Step 2：确认登录状态

```
GET /api/auth/me
```

预期返回当前用户信息。

---

### Step 3：存入一条笔记

```json
POST /notes/
{
  "content": "# 等价无穷小\n\n当 x→0 时：\n- sinx ~ x\n- tanx ~ x\n- arcsinx ~ x\n- 1-cosx ~ x²/2\n- eˣ-1 ~ x\n- ln(1+x) ~ x",
  "doc_id": "math_infinitesimal",
  "metadata": {"subject": "数学", "type": "note", "topic": "极限"}
}
```

---

### Step 4：检索笔记

```
GET /notes/query?q=极限计算技巧&subject=数学&n=3
```

预期返回刚才存入的笔记（distance 较小）。

---

### Step 5：问答（融合笔记）

```json
POST /api/answer
{
  "user_input": "当 x 趋近于 0 时，常用的等价无穷小有哪些？",
  "use_faiss": true,
  "use_chroma": true,
  "chroma_filter": {"subject": "数学"}
}
```

预期答案中引用了 Step 3 存入的笔记内容。

---

### Step 6：获取一道数学题

```
GET /api/practice/question?subject=math&question_type=single_choice&year=2022
```

记录返回的完整题目 JSON。

---

### Step 7：提交答案

```json
POST /api/practice
{
  "user_id": "exam_student",
  "user_input": "A",
  "user_answer": "A",
  "current_question": { /* 上一步返回的题目 JSON */ }
}
```

查看 `grade_result`（是否正确）、`explanation`（解析）、`followup_questions`（追问建议）。

---

### Step 8：运行学习诊断

```json
POST /diagnosis/run
{
  "user_id": "exam_student",
  "subject": "数学",
  "history_records": [],
  "weak_threshold": 0.6,
  "recommend_per_point": 3
}
```

查看 `weak_points`（薄弱点）、`recommended_questions`（推荐题）、`report`（完整诊断报告）。

---

### Step 9：清理测试笔记

```
DELETE /notes/math_infinitesimal
```

---

## 附录：常用测试数据

### 数学 mock 请求体（可直接复制）

```json
{
  "user_input": "A",
  "user_answer": "A",
  "current_question": {
    "id": 1,
    "subject": "数学",
    "year": 2020,
    "question_type": "单选题",
    "content": "设函数 f(x) = x² + 2x + 1，则 f'(1) = （ ）",
    "options": {
      "A": "4",
      "B": "2",
      "C": "1",
      "D": "0"
    },
    "correct_answer": "A",
    "analysis": "f'(x) = 2x + 2，f'(1) = 2×1 + 2 = 4",
    "knowledge_points": ["导数", "多项式求导"]
  }
}
```

### 诊断 mock 请求体（含历史记录）

```json
{
  "user_id": "demo_user",
  "history_records": [
    {"question_id": 1, "subject": "数学", "knowledge_point": "极限", "is_correct": false},
    {"question_id": 2, "subject": "数学", "knowledge_point": "极限", "is_correct": false},
    {"question_id": 3, "subject": "数学", "knowledge_point": "极限", "is_correct": true},
    {"question_id": 4, "subject": "数学", "knowledge_point": "导数", "is_correct": true},
    {"question_id": 5, "subject": "数学", "knowledge_point": "导数", "is_correct": true},
    {"question_id": 6, "subject": "政治", "knowledge_point": "唯物论", "is_correct": false},
    {"question_id": 7, "subject": "政治", "knowledge_point": "唯物论", "is_correct": false}
  ],
  "weak_threshold": 0.6,
  "recommend_per_point": 2
}
```

---

*文档版本：v1.0 | 最后更新：2026-04-08*
