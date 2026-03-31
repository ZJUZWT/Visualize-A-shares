FROM python:3.11-slim AS builder

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 第一层：只复制依赖声明，安装依赖
# pyproject.toml 不变则命中 Docker 缓存，不会重下 torch 等大包
COPY pyproject.toml .

# 先装构建工具，再提取 dependencies 并安装（不需要源码）
RUN pip install --upgrade pip hatchling \
    && pip install --prefix=/install \
       $(python -c "
import tomllib, pathlib
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
print(' '.join(d['project']['dependencies']))
") \
       --no-cache-dir \
       -i https://pypi.tuna.tsinghua.edu.cn/simple


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
