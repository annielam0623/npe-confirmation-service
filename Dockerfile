# NPE Confirmation Service — Dockerfile
# 用途：把现有 FastAPI 代码容器化，用于 AWS ECS。
# 入口与 railway.toml 一致：uvicorn main:app（main.py 在根目录）。
# Python 版本与 .python-version 一致：3.11。

FROM python:3.11-slim

# 不写 .pyc、日志实时输出（容器里看 log 更顺）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先只 copy 依赖清单并安装 —— 利用 Docker 层缓存：
# 只要 requirements.txt 不变，重建时这一层不会重跑，构建快很多。
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 再 copy 全部代码（.dockerignore 已排除 .git / __pycache__ 等）
COPY . .

# 容器内监听端口。ECS/本地用固定 8080；
# 如果运行环境注入了 $PORT（如 Railway），下面的启动命令会优先用它。
ENV PORT=8080
EXPOSE 8080

# 启动命令 —— 照搬 Railway 那条，但把 $PORT 处理成「有就用、没有默认 8080」，
# 避免 ECS 上 $PORT 为空导致 uvicorn 起不来。
# 用 shell 形式（不带 JSON 数组）才能让 ${PORT:-8080} 这种变量展开生效。
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
