FROM python:3.11-slim

WORKDIR /app/backend

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY pyproject.toml .
COPY . .
RUN pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir

EXPOSE 8000
CMD ["python", "main.py"]
