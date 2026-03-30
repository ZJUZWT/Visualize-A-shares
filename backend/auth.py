"""
用户认证模块 — 密码哈希 + JWT + DuckDB users 表

三级降级认证:
1. Authorization: Bearer <jwt> → decode 取 sub
2. X-User-Id header → 直通（MCP 兼容）
3. 都没有 → "anonymous"
"""

import os
import re
import secrets
import time
from typing import Optional

import jwt
from fastapi import Header, HTTPException
from loguru import logger
from passlib.context import CryptContext

from config import DATA_DIR

# ─── 密码哈希 ─────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── JWT 配置 ──────────────────────────────────────────
JWT_SECRET_FILE = DATA_DIR / ".jwt_secret"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7


def _load_jwt_secret() -> str:
    """优先读环境变量 → 其次读文件 → 自动生成并持久化"""
    # 1. 环境变量
    env_secret = os.environ.get("AUTH_JWT_SECRET")
    if env_secret:
        return env_secret

    # 2. 文件
    if JWT_SECRET_FILE.exists():
        secret = JWT_SECRET_FILE.read_text().strip()
        if secret:
            return secret

    # 3. 自动生成
    secret = secrets.token_hex(32)
    try:
        JWT_SECRET_FILE.write_text(secret)
        logger.info("🔑 JWT secret 已自动生成并持久化到 data/.jwt_secret")
    except Exception as e:
        logger.warning(f"⚠️ JWT secret 持久化失败: {e}，将仅在内存中使用")
    return secret


JWT_SECRET = _load_jwt_secret()


def create_jwt(user_id: str) -> str:
    """签发 JWT，默认 7 天过期"""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + JWT_EXPIRE_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> str:
    """解码 JWT，返回 user_id。过期或无效抛 401"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效的 token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 token")


# ─── DuckDB users 表 ──────────────────────────────────

def _get_store():
    """获取 DataEngine 的 DuckDB store（复用已有连接，避免文件锁冲突）"""
    from engine.data import get_data_engine
    return get_data_engine().store


def ensure_users_table() -> None:
    """幂等建表，启动时调用"""
    store = _get_store()
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       VARCHAR PRIMARY KEY,
            password_hash VARCHAR NOT NULL,
            display_name  VARCHAR,
            created_at    TIMESTAMP DEFAULT current_timestamp,
            last_login_at TIMESTAMP
        )
    """)
    logger.info("   Users 表: 已就绪")


# ─── 用户 CRUD ────────────────────────────────────────

def get_user(user_id: str) -> Optional[dict]:
    """获取用户信息，不存在返回 None"""
    store = _get_store()
    row = store._conn.execute(
        "SELECT user_id, password_hash, display_name, created_at, last_login_at "
        "FROM users WHERE user_id = ?",
        [user_id],
    ).fetchone()
    if not row:
        return None
    return {
        "user_id": row[0],
        "password_hash": row[1],
        "display_name": row[2],
        "created_at": row[3],
        "last_login_at": row[4],
    }


def create_user(user_id: str, password: str, display_name: Optional[str] = None) -> dict:
    """创建用户，返回用户信息（不含 password_hash）"""
    password_hash = pwd_context.hash(password)
    store = _get_store()
    store._conn.execute(
        "INSERT INTO users (user_id, password_hash, display_name) VALUES (?, ?, ?)",
        [user_id, password_hash, display_name or user_id],
    )
    return {
        "user_id": user_id,
        "display_name": display_name or user_id,
    }


def list_users() -> list[dict]:
    """列出所有用户（不含 password_hash）"""
    store = _get_store()
    rows = store._conn.execute(
        "SELECT user_id, display_name, created_at, last_login_at "
        "FROM users ORDER BY last_login_at DESC NULLS LAST, created_at DESC"
    ).fetchall()
    return [
        {
            "user_id": r[0],
            "display_name": r[1],
            "created_at": r[2].isoformat() if r[2] else None,
            "last_login_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def update_last_login(user_id: str) -> None:
    """更新最后登录时间"""
    store = _get_store()
    store._conn.execute(
        "UPDATE users SET last_login_at = current_timestamp WHERE user_id = ?",
        [user_id],
    )


# ─── FastAPI 依赖 — 三级降级认证 ─────────────────────

async def get_current_user(
    authorization: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> str:
    """从请求 header 中提取用户标识

    三级降级:
    1. Authorization: Bearer <jwt> → decode 取 sub
    2. X-User-Id header → 直通（MCP 兼容）
    3. 都没有 → "anonymous"
    """
    # 1. JWT Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return decode_jwt(token)

    # 2. X-User-Id header（MCP 兼容）
    user_id = x_user_id.strip()
    if user_id:
        if not re.match(r'^[\w\u4e00-\u9fff]{1,32}$', user_id):
            raise HTTPException(status_code=400, detail="无效的用户名格式")
        return user_id

    # 3. 匿名
    return "anonymous"
