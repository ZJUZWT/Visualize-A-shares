FROM python:3.11-slim AS builder

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY . .
RUN pip install --upgrade pip \
    && pip install --prefix=/install . --no-cache-dir \
       -i https://pypi.tuna.tsinghua.edu.cn/simple


FROM python:3.11-slim AS runtime

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

# 运行时数据和日志目录（由 docker-compose volumes 挂载）
RUN mkdir -p /app/data /app/backend/logs

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
