# -----------------------------------------------------------------------
# 考研智能辅导系统 — 后端 Dockerfile
# 多阶段构建：builder 安装依赖，runtime 运行服务
# -----------------------------------------------------------------------

# ---------- builder ----------
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装系统依赖（faiss-cpu 需要 libgomp）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

WORKDIR /app

# 仅复制运行时所需系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制源码
COPY . .

# 非 root 用户运行
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 对外暴露端口
EXPOSE 8000

# 启动命令（生产环境可调整 workers 数）
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
