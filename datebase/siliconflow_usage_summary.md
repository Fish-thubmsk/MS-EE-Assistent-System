# SiliconFlow API 使用方法总结

## 概述
本项目使用 **SiliconFlow** API 提供的深度学习模型（主要是 DeepSeek 系列）进行考研数学试卷的分析处理。

---

## 核心配置

### 1. API 基本配置

```python
from openai import OpenAI  # 使用官方 OpenAI 库

CONFIG = {
    "API_KEY": "sk-xxxxx...",  # SiliconFlow API 密钥
    "BASE_URL": "https://api.siliconflow.cn/v1",  # SiliconFlow API 端点
    "MODEL_NAME": "deepseek-ai/DeepSeek-V3",  # 模型名称
}

# 初始化客户端
client = OpenAI(
    api_key=CONFIG["API_KEY"],
    base_url=CONFIG["BASE_URL"]
)
```

### 2. 可用模型

本项目使用的模型：
- **`deepseek-ai/DeepSeek-V3`** - 文本处理模型（推荐，速度快）
- **`deepseek-ai/DeepSeek-V3.1`** - 文本处理模型（更新版本）
- **`Qwen/Qwen3-VL-235B-A22B-Instruct`** - 多模态视觉模型（图片 OCR）

---

## 使用方式

### 方式一：纯文本 API 调用（最常用）

#### 基础调用

```python
response = client.chat.completions.create(
    model=CONFIG["MODEL_NAME"],
    messages=[
        {"role": "user", "content": "你的提示词"}
    ]
)

result = response.choices[0].message.content
```

#### 强制 JSON 输出

```python
response = client.chat.completions.create(
    model=CONFIG["MODEL_NAME"],
    messages=[
        {"role": "user", "content": "请返回JSON格式的分析结果..."}
    ],
    response_format={"type": "json_object"}  # 强制 JSON 输出
)

analysis_json = json.loads(response.choices[0].message.content)
```

**关键参数说明：**
- `response_format={"type": "json_object"}` - 强制模型返回有效的 JSON 对象
- 这大幅提高了 JSON 解析的成功率

---

### 方式二：视觉多模态 API（图片处理）

#### 图片转 Base64

```python
import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
```

#### 发送图片进行 OCR

```python
base64_image = image_to_base64("path/to/image.png")

response = client.chat.completions.create(
    model="Qwen/Qwen3-VL-235B-A22B-Instruct",  # 多模态模型
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请分析这张试卷..."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    response_format={"type": "json_object"},
    max_tokens=4096,
    temperature=0.0  # OCR 用 0.0，确定性输出
)

result = json.loads(response.choices[0].message.content)
```

---

## 实际应用案例

### 案例 1：单题分析（ana.py）

**目标**：分析每道数学题的知识点、题型、难度等

```python
def call_ai_api(client, question_block):
    """调用 SiliconFlow 分析单道题"""
    question_json_str = json.dumps(question_block, indent=4, ensure_ascii=False)
    prompt_text = PROMPT_A.format(question_json_string=question_json_str)
    
    chat_completion = client.chat.completions.create(
        model=CONFIG["MODEL_NAME"],
        messages=[{"role": "user", "content": prompt_text}],
        response_format={"type": "json_object"}  # 强制 JSON
    )
    
    ai_generated_content = chat_completion.choices[0].message.content
    analysis_json = json.loads(ai_generated_content)
    return analysis_json
```

**输出示例**：
```json
{
  "primary_knowledge_point": "极限的定义和计算",
  "secondary_knowledge_points": ["洛必达法则", "泰勒展开"],
  "question_type": "极限计算题",
  "methodology_and_tricks": "识别不定式类型，选择合适的方法",
  "common_pitfalls": "忽略函数的定义域",
  "computational_workload": "中"
}
```

---

### 案例 2：试卷总结（sum.py）

**目标**：对已分析的整张试卷进行宏观总结

```python
def call_summary_api(client, exam_data):
    """调用 SiliconFlow 生成试卷总结"""
    exam_json_str = json.dumps(exam_data, indent=4, ensure_ascii=False)
    prompt_text = PROMPT_B.format(ANALYZED_EXAM_JSON=exam_json_str)
    
    chat_completion = client.chat.completions.create(
        model=CONFIG["MODEL_NAME"],
        messages=[{"role": "user", "content": prompt_text}],
        response_format={"type": "json_object"}
    )
    
    summary_json = json.loads(chat_completion.choices[0].message.content)
    return summary_json
```

---

### 案例 3：图片 OCR（code/run_ocr.py）

**目标**：将试卷图片转换为 JSON 格式的题目数据

```python
def call_vision_api(client, image_path):
    """调用视觉 API 进行 OCR"""
    base64_image = image_to_base64(image_path)
    
    chat_completion = client.chat.completions.create(
        model="Qwen/Qwen3-VL-235B-A22B-Instruct",  # 多模态模型
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": AI_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=4096,
        temperature=0.0
    )
    
    response_text = chat_completion.choices[0].message.content
    return json.loads(response_text)
```

**输出格式**：
```json
[
  {
    "question_number": "一、1.",
    "question_body": "设函数...",
    "options": {
      "A": "...",
      "B": "...",
      "C": "...",
      "D": "..."
    }
  }
]
```

---

## 高级特性

### 1. 速率控制

```python
CONFIG = {
    "REQUEST_DELAY_SECONDS": 0.5  # 请求间隔（秒）
}

# 使用
time.sleep(CONFIG["REQUEST_DELAY_SECONDS"])

# RPM 计算：60 / 延迟秒数 = RPM
# 例：延迟 0.5 秒 → 120 RPM
```

### 2. 异步并发请求

```python
from openai import AsyncOpenAI

async_client = AsyncOpenAI(
    api_key=CONFIG["API_KEY"],
    base_url=CONFIG["BASE_URL"]
)

# 并发调用多个请求
tasks = [analyze_question_async(q) for q in questions]
results = await asyncio.gather(*tasks)
```

### 3. 错误处理和重试

```python
def call_ai_api_with_retry(client, question_block, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=CONFIG["MODEL_NAME"],
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            else:
                print(f"[错误] 最终失败：{e}")
                return None
```

---

## 批处理最佳实践

### 1. 文件批量处理

```python
def process_all_exams(client, input_dir, output_dir):
    exam_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    
    for filename in exam_files:
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)
        
        with open(input_path, 'r', encoding='utf-8') as f:
            exam_data = json.load(f)
        
        # 处理
        result = call_ai_api(client, exam_data)
        
        # 保存
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
```

### 2. 进度跟踪

```python
for index, filename in enumerate(exam_files):
    print(f"处理 [{index + 1}/{len(exam_files)}]：{filename}")
    # 处理逻辑
```

### 3. 中间文件保存（断点续传）

```python
# 定期保存中间结果
if (index + 1) % 10 == 0:
    with open('checkpoint.json', 'w') as f:
        json.dump(results_so_far, f)
```

---

## 常见问题

### Q1：JSON 解析失败怎么办？

**A：** 可能原因和解决方案：

```python
try:
    result_text = response.choices[0].message.content.strip()
    
    # 移除 markdown 包装
    if result_text.startswith('```json'):
        result_text = result_text[7:]
    if result_text.startswith('```'):
        result_text = result_text[3:]
    if result_text.endswith('```'):
        result_text = result_text[:-3]
    
    result = json.loads(result_text.strip())
except json.JSONDecodeError as e:
    print(f"JSON 解析失败：{e}")
    return None
```

### Q2：如何优化速度？

**A：** 使用异步并发：

```python
# 使用 AsyncOpenAI 替代同步 OpenAI
# 并设置合理的并发数
MAX_CONCURRENT = 10  # 根据 API 限额调整
```

### Q3：如何处理 API 限额问题？

**A：** 实现速率限制和退避策略：

```python
if response.status_code == 429:  # 限额错误
    time.sleep(10)  # 等待
    # 重试
```

---

## 所有使用文件总结

| 文件 | 功能 | 模型 |
|------|------|------|
| `ana.py` | 单题分析（知识点、题型、难度） | DeepSeek-V3.1 |
| `sum.py` | 试卷总结（整卷分析、模块权重、推荐） | DeepSeek-V3.1 |
| `phase1_demo.py` | 演示版：前3份试卷分析 | DeepSeek-V3 |
| `phase1_question_analyzer.py` | 完整版：全部试卷逐题分析 | DeepSeek-V3 |
| `phase2_normalizer.py` | 题型规范化（合并相似题型） | DeepSeek-V3 |
| `code/run_ocr.py` | 图片 OCR：将试卷图片转换为 JSON | Qwen3-VL-235B |
| `final_output/scripts/思路分析和重点归纳.py` | 生成解题思路和模块重点总结 | DeepSeek-V3 |
| `final_output/scripts/思路分析_并发版.py` | 并发版思路分析（更快） | DeepSeek-V3 |
| `final_output/scripts/phase1_question_analyzer_v2.py` | v2 版本逐题分析 | DeepSeek-V3 |

---

## 总结

**SiliconFlow API 的核心要点：**

1. ✅ 使用 `OpenAI` 库（兼容 OpenAI 接口）
2. ✅ 配置 `api_key` 和 `base_url` 指向 SiliconFlow
3. ✅ 使用 `response_format={"type": "json_object"}` 强制 JSON 输出
4. ✅ 多模态模型用于图片处理（Qwen/Qwen3）
5. ✅ 合理的速率控制（0.5-2 秒延迟）
6. ✅ 正确处理 JSON 解析和错误
7. ✅ 对批量任务使用异步并发

