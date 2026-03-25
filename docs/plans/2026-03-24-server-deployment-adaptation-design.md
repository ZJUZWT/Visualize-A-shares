# Server Deployment Adaptation Design

> 编写日期：2026-03-24
> 范围：补齐可发布的生产部署骨架，包括容器构建、环境变量模板、Nginx 反向代理、持久化卷、健康检查与可选 Cloudflare Tunnel。

---

## 1. 背景

当前仓库虽然已经有：

- 根目录 `docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `DEPLOYMENT.md`

但这些都还是“开发可跑”级别，而不是“生产可发”级别：

1. 前端 Docker 直接跑 `npm run dev`
2. Compose 没有生产反向代理层
3. 没有 SSL / 域名接入骨架
4. 没有命名卷持久化规划
5. `.env.example` 偏开发，不是生产模板
6. 前端多个模块默认 API 地址仍回退到 `http://localhost:8000`
7. 后端 `config.py` 的 server 配置目前不是从环境变量读取

如果现在直接上线，最容易出现的问题不是“服务起不来”，而是：

- 浏览器在生产环境仍请求 `localhost:8000`
- Nginx 没有 `/api` 代理和 SSE 转发设置
- 容器重建后 DuckDB / ChromaDB 数据路径不清晰
- 没有统一的健康检查与自动重启策略

---

## 2. 目标

本模块完成后，应具备：

1. 前后端都能以 production 模式构建镜像
2. 通过 Docker Compose 启动一套可发布骨架：
   - `frontend`
   - `backend`
   - `nginx`
   - `cloudflared`（可选 profile）
3. 数据、日志和证书目录有明确持久化路径
4. 前端默认使用同源 `/api` 或显式环境变量，而不是硬编码 `localhost`
5. 后端端口 / reload / CORS 可由环境变量控制
6. 有 `.env.production` 模板与更新后的部署文档

---

## 3. 非目标

本轮不做：

- 自动申请 Let’s Encrypt 证书
- systemd 单机安装脚本
- Kubernetes / Helm
- Redis 正式接入
- 蓝绿发布 / 灰度发布
- 全量 CI/CD 发布流水线

这一轮只做“单机生产部署骨架 + 可选 Tunnel”的最小完整解。

---

## 4. 方案对比

### 方案 A：只修 Dockerfile，保留现有 compose

优点：

- 改动最少
- 容器能生产构建

缺点：

- 没有 Nginx 和 SSL 层
- 浏览器 API 地址问题仍然脆弱
- 不能算真正“服务器发布适配”

不采用。

### 方案 B：生产 Compose + Nginx + 同源 API + 可选 Cloudflare Tunnel

优点：

- 部署方式清晰
- 适合 VPS / 轻量云场景
- 可以解决前端 API 地址、SSE 代理、持久化和健康检查
- Cloudflare Tunnel 可选，不强依赖公网 IP

缺点：

- 需要同时修改 Docker、Compose、前端 API base 和后端配置

推荐采用。

### 方案 C：直接上 k8s / ingress / secret manager

优点：

- 长期上限更高

缺点：

- 与当前项目规模明显不匹配
- 运维负担大

不采用。

---

## 5. 核心设计

### 5.1 容器拓扑

生产部署结构：

```text
Internet / Cloudflare
        ↓
      Nginx :80/:443
      ├── /      → frontend:3000
      └── /api   → backend:8000
```

可选：

```text
cloudflared tunnel → nginx
```

这意味着浏览器默认访问同源：

- 页面：`https://your-domain/`
- API：`https://your-domain/api/...`

从而避免前端在生产环境直连 `localhost:8000`。

### 5.2 前端 API Base 策略

统一原则：

- 优先读 `NEXT_PUBLIC_API_BASE`
- 未配置时默认使用空字符串 `""`
- 即相对路径 `/api/...`

这样：

- 本地开发仍可通过显式环境变量或 Next rewrite 访问后端
- 生产环境默认走同源 Nginx 代理

需要收敛当前前端中混用的：

- `NEXT_PUBLIC_API_BASE`
- `NEXT_PUBLIC_API_URL`
- `"http://localhost:8000"`

### 5.3 后端环境变量策略

沿用现有 `llm/config.py` 的做法，补充 `config.py` 对 `.env` 和环境变量的读取。

本轮至少支持：

- `SERVER_HOST`
- `SERVER_PORT`
- `SERVER_RELOAD`
- `CORS_ORIGINS`
- `CHROMADB_PERSIST_DIR`
- `RAG_PERSIST_DIR`

这样 `.env.production` 才能真正影响运行时。

### 5.4 Docker 构建策略

后端：

- 用 multi-stage
- 在 builder 安装依赖
- runtime 只保留运行所需内容
- 默认执行 `uvicorn main:app --host 0.0.0.0 --port 8000`

前端：

- 用 multi-stage
- `npm ci`
- `npm run build`
- runtime 用 `npm run start`

不做 Next standalone 特化，优先保持当前项目兼容性。

### 5.5 持久化目录

生产 compose 中持久化：

- `./data:/app/data`
- `./logs:/app/logs`
- `./deploy/ssl:/etc/nginx/ssl:ro`
- `./deploy/cloudflared:/etc/cloudflared:ro`

后端已有：

- DuckDB
- ChromaDB
- `expert_kg.json`

这些都在 `data/` 下，直接整目录持久化即可。

### 5.6 Nginx 配置

新增独立 `deploy/nginx/nginx.conf`，包含：

- `server_name`
- `client_max_body_size`
- gzip
- `/` 转发到前端
- `/api/` 转发到后端
- SSE / WebSocket 所需的：
  - `proxy_http_version 1.1`
  - `proxy_buffering off`
  - `Connection ""`
  - `Upgrade` / `Connection upgrade`

SSL 采用“挂载现有证书”的方式，不自动申请证书。

### 5.7 Compose 分层

建议保留开发 compose 简洁性，同时新增生产专用 compose：

- `docker-compose.yml`
  - 维持开发快速启动
- `docker-compose.prod.yml`
  - 用于生产部署

生产 compose 中加：

- `restart: unless-stopped`
- 健康检查
- Nginx 依赖 backend/frontend
- `cloudflared` 作为 profile，例如 `profiles: ["tunnel"]`

### 5.8 Cloudflare Tunnel

不强制启用，但提供现成骨架：

- `deploy/cloudflared/config.yml.example`
- `docker-compose.prod.yml` 中可选 service

这样用户可以：

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d
```

---

## 6. 修改文件

基础设施：

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`
- 新增 `docker-compose.prod.yml`
- 新增 `deploy/nginx/nginx.conf`
- 新增 `deploy/cloudflared/config.yml.example`
- 新增 `.env.production.example`

配置：

- `backend/config.py`

前端：

- 新增 `frontend/lib/api-base.ts`
- 修改所有直接回退 `localhost:8000` 的调用点

文档：

- `README.md`
- `DEPLOYMENT.md`

---

## 7. 完成定义

本模块被视为完成的标准：

1. 前后端 Dockerfile 都是 production 可运行形态
2. 有独立生产 compose 文件
3. Nginx 反向代理和 SSE 转发已配置
4. `.env.production.example` 已补齐
5. 前端默认不再把生产 API 指向 `localhost:8000`
6. 后端关键 server 配置可由环境变量控制
7. 文档包含本地 / 生产 / 可选 Tunnel 的启动方式

---

## 8. 结论

这轮的本质不是“多几个部署文件”，而是把项目从“本地开发工程”抬到“可以放上服务器”的状态。

推荐实现方式是：

- 生产镜像
- 同源 API
- Nginx 代理
- 可选 Cloudflare Tunnel
- 环境变量真正生效

这套骨架够用、够稳，也和当前仓库规模匹配。
