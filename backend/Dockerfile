# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 第一层：只复制依赖声明
COPY pyproject.toml .

# 安装依赖 — 使用 BuildKit cache mount 持久化 pip 下载缓存
# 即使 pyproject.toml 改了（加新依赖），已有的包（torch 等）直接从缓存装，不重新下载
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); open('/tmp/reqs.txt','w').write('\n'.join(d['project']['dependencies']))" \
    && pip install --prefix=/install -r /tmp/reqs.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


FROM python:3.11-slim AS runtime

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 第二层：复制已装好的依赖（改代码不会触发这层重建）
COPY --from=builder /install /usr/local

# 第三层：复制代码
COPY . .

# 运行时数据和日志目录（由 docker-compose volumes 挂载）
RUN mkdir -p /app/data /app/backend/logs

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
