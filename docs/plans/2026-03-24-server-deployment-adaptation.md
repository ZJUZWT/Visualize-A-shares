# Server Deployment Adaptation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为项目补齐可上线的服务器发布骨架，包括生产镜像、Nginx 反代、生产 compose、环境变量模板、持久化和可选 Cloudflare Tunnel。

**Architecture:** 采用 `frontend + backend + nginx` 的生产拓扑，浏览器默认通过同源 `/api` 访问后端；前端统一 API base 解析逻辑，后端 `config.py` 从环境变量读取 server 与持久化配置。使用 `docker-compose.prod.yml` 承载生产部署，并提供可选 `cloudflared` profile。

**Tech Stack:** Docker, Docker Compose, Nginx, FastAPI, Next.js, TypeScript

---

### Task 1: Add production config contract and environment loading

**Files:**
- Modify: `backend/config.py`
- Create: `.env.production.example`
- Modify: `README.md`
- Modify: `DEPLOYMENT.md`

**Step 1: Define the failing expectation**

Document and implement that production config must be able to control:

- `SERVER_HOST`
- `SERVER_PORT`
- `SERVER_RELOAD`
- `CORS_ORIGINS`
- `CHROMADB_PERSIST_DIR`
- `RAG_PERSIST_DIR`

**Step 2: Run a focused verification**

Run: `python3 -m py_compile backend/config.py`

Expected before implementation: either missing variables or static config only.

**Step 3: Write minimal implementation**

- add env loading helper in `backend/config.py`
- add `.env.production.example`
- update deployment docs

**Step 4: Re-run verification**

Run: `python3 -m py_compile backend/config.py`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/config.py .env.production.example README.md DEPLOYMENT.md
git commit -m "feat(deploy): add production env config support"
```

### Task 2: Replace development containers with production Dockerfiles

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`

**Step 1: Define the failing expectation**

Current images are not production-safe because:

- frontend runs `npm run dev`
- backend installs and runs as a development-style image

**Step 2: Run a focused verification**

Run: `docker compose config`

Expected before implementation: config is dev-only and lacks production topology.

**Step 3: Write minimal implementation**

- backend Dockerfile: multi-stage production runtime
- frontend Dockerfile: build + start production image

**Step 4: Re-run verification**

Run: `docker compose config`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile
git commit -m "feat(deploy): switch frontend and backend images to production builds"
```

### Task 3: Add production compose, Nginx proxy, persistence and tunnel skeleton

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `deploy/nginx/nginx.conf`
- Create: `deploy/cloudflared/config.yml.example`
- Modify: `docker-compose.yml`

**Step 1: Define the failing expectation**

The project currently lacks:

- Nginx reverse proxy
- SSL mount points
- named/host persistence mapping for logs and certs
- optional Cloudflare Tunnel profile

**Step 2: Run a focused verification**

Run: `docker compose -f docker-compose.prod.yml config`

Expected before implementation: FAIL because the file does not exist.

**Step 3: Write minimal implementation**

- add prod compose
- add Nginx config for `/` and `/api`
- disable proxy buffering for SSE
- add optional `cloudflared` service profile

**Step 4: Re-run verification**

Run: `docker compose -f docker-compose.prod.yml config`

Expected: PASS

**Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml deploy/nginx/nginx.conf deploy/cloudflared/config.yml.example
git commit -m "feat(deploy): add production compose and nginx reverse proxy"
```

### Task 4: Normalize frontend API base to same-origin production behavior

**Files:**
- Create: `frontend/lib/api-base.ts`
- Modify: relevant files under `frontend/stores/`, `frontend/components/`, `frontend/app/`, `frontend/lib/`

**Step 1: Define the failing expectation**

Current frontend modules still fall back to `http://localhost:8000`, which breaks production.

**Step 2: Run a focused verification**

Run: `cd frontend && npx tsc --noEmit`

Expected before implementation: FAIL until all direct API base call sites are centralized.

**Step 3: Write minimal implementation**

- add shared helper that defaults to relative same-origin
- migrate direct fallback call sites

**Step 4: Re-run verification**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/api-base.ts frontend/stores frontend/components frontend/app frontend/lib
git commit -m "refactor(frontend): normalize production api base resolution"
```

### Task 5: Final verification and TODO alignment

**Files:**
- Modify: `TODO.md`

**Step 1: Run backend syntax verification**

Run: `python3 -m py_compile backend/config.py backend/main.py`

Expected: PASS

**Step 2: Run frontend type verification**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

**Step 3: Run compose verification**

Run: `docker compose config`

Run: `docker compose -f docker-compose.prod.yml config`

Expected: PASS

**Step 4: Update TODO**

Mark complete only if these are true:

- Docker multi-stage build
- `.env.production` template
- Nginx 反向代理 + SSL
- 数据卷持久化
- 健康检查 + 自动重启
- Cloudflare Tunnel

**Step 5: Commit**

```bash
git add TODO.md backend/config.py backend/Dockerfile frontend/Dockerfile docker-compose.yml docker-compose.prod.yml deploy/nginx/nginx.conf deploy/cloudflared/config.yml.example .env.production.example README.md DEPLOYMENT.md frontend/lib/api-base.ts
git commit -m "feat(deploy): complete server deployment adaptation module"
```
