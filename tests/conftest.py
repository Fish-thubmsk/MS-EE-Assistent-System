"""pytest 配置：在任何测试模块导入前设置必要的环境变量，避免 CI 环境缺失配置导致失败。"""

import os

# LLM_MODEL 是必填项（无默认值）；在 CI 中注入一个占位值供模块级初始化使用。
# 实际 LLM 调用在测试中均通过 mock 或降级路径绕过，此值不会被真正调用。
os.environ.setdefault("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
