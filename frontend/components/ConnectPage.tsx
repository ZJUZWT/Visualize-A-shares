"use client";

import { useState, useEffect } from "react";
import { useConnectionStore } from "@/stores/useConnectionStore";
import type { UserInfo } from "@/stores/useConnectionStore";
import {
  Mountain,
  Loader2,
  AlertCircle,
  Unplug,
  UserPlus,
  ArrowLeft,
  LogIn,
  UserCircle2,
  Ghost,
} from "lucide-react";

// ─── 样式常量 ────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  fontSize: 14,
  background: "var(--bg-primary)",
  color: "var(--text-primary)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  outline: "none",
  transition: "border-color 0.15s",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 500,
  color: "var(--text-secondary)",
};

function PrimaryButton({
  onClick,
  disabled,
  loading: isLoading,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || isLoading}
      style={{
        width: "100%",
        padding: "10px 0",
        fontSize: 14,
        fontWeight: 600,
        color: "#fff",
        background: disabled || isLoading ? "var(--text-tertiary)" : "var(--accent)",
        border: "none",
        borderRadius: 8,
        cursor: disabled || isLoading ? "not-allowed" : "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        transition: "background 0.15s",
      }}
      onMouseEnter={(e) => {
        if (!disabled && !isLoading)
          (e.target as HTMLButtonElement).style.background = "var(--accent-hover)";
      }}
      onMouseLeave={(e) => {
        if (!disabled && !isLoading)
          (e.target as HTMLButtonElement).style.background = "var(--accent)";
      }}
    >
      {isLoading ? (
        <>
          <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
          处理中...
        </>
      ) : (
        children
      )}
    </button>
  );
}

function BackLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "none",
        border: "none",
        color: "var(--text-secondary)",
        fontSize: 13,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: 4,
        padding: 0,
        marginTop: 4,
      }}
    >
      <ArrowLeft size={14} />
      {children}
    </button>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      style={{
        width: "100%",
        padding: "10px 14px",
        fontSize: 13,
        color: "#EF4444",
        background: "rgba(239, 68, 68, 0.08)",
        border: "1px solid rgba(239, 68, 68, 0.2)",
        borderRadius: 8,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <AlertCircle size={16} style={{ flexShrink: 0 }} />
      {message}
    </div>
  );
}

// ─── 相对时间 ────────────────────────────────────────

function relativeTime(isoStr: string | null): string {
  if (!isoStr) return "从未登录";
  const diff = Date.now() - new Date(isoStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return `${Math.floor(days / 30)}个月前`;
}

// ─── 步骤组件 ────────────────────────────────────────

function StepUrl() {
  const { connectServer, loading, error, serverUrl } = useConnectionStore();
  const [url, setUrl] = useState("");

  useEffect(() => {
    if (serverUrl) setUrl(serverUrl);
  }, [serverUrl]);

  function handleConnect() {
    if (url.trim()) connectServer(url.trim());
  }

  return (
    <>
      <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0, textAlign: "center" }}>
        连接到后端服务器
      </p>

      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
        <label style={labelStyle}>服务器地址</label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !loading && handleConnect()}
          placeholder="http://your-server:8000"
          disabled={loading}
          style={{
            ...inputStyle,
            fontFamily: "'JetBrains Mono', monospace",
          }}
          onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
        />
      </div>

      <PrimaryButton onClick={handleConnect} disabled={!url.trim()} loading={loading}>
        <Unplug size={16} />
        连接
      </PrimaryButton>

      {error && <ErrorBanner message={error} />}
    </>
  );
}

function UserCard({ user, onClick }: { user: UserInfo; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: "1 1 calc(50% - 6px)",
        minWidth: 130,
        padding: "16px 12px",
        background: "var(--bg-primary)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        transition: "border-color 0.15s, box-shadow 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)";
        (e.currentTarget as HTMLButtonElement).style.boxShadow =
          "0 0 0 1px var(--accent)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
      }}
    >
      <UserCircle2 size={28} style={{ color: "var(--accent)" }} />
      <span
        style={{
          fontSize: 14,
          fontWeight: 600,
          color: "var(--text-primary)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          maxWidth: "100%",
        }}
      >
        {user.display_name || user.user_id}
      </span>
      <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
        {relativeTime(user.last_login_at)}
      </span>
    </button>
  );
}

function StepUserSelect() {
  const { users, selectUser, goToRegister, enterAnonymous, backToUrl, error } =
    useConnectionStore();

  return (
    <>
      <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0, textAlign: "center" }}>
        选择用户
      </p>

      {/* 用户卡片网格 */}
      {users.length > 0 && (
        <div
          style={{
            width: "100%",
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          {users.map((user) => (
            <UserCard
              key={user.user_id}
              user={user}
              onClick={() => selectUser(user.user_id)}
            />
          ))}
        </div>
      )}

      {/* 创建新用户按钮 */}
      <button
        onClick={goToRegister}
        style={{
          width: "100%",
          padding: "10px 0",
          fontSize: 14,
          fontWeight: 500,
          color: "var(--accent)",
          background: "var(--accent-light)",
          border: "1px dashed var(--accent)",
          borderRadius: 8,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          transition: "background 0.15s",
        }}
      >
        <UserPlus size={16} />
        创建新用户
      </button>

      {/* 匿名进入 */}
      <button
        onClick={enterAnonymous}
        style={{
          background: "none",
          border: "none",
          color: "var(--text-tertiary)",
          fontSize: 13,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          padding: 0,
        }}
      >
        <Ghost size={14} />
        以匿名身份进入
      </button>

      <BackLink onClick={backToUrl}>返回</BackLink>

      {error && <ErrorBanner message={error} />}
    </>
  );
}

function StepLogin() {
  const { selectedUser, login, loading, error, backToUserSelect, users } = useConnectionStore();
  const [password, setPassword] = useState("");

  // 找到选中用户的 display_name
  const userInfo = users.find((u) => u.user_id === selectedUser);
  const displayLabel = userInfo?.display_name || selectedUser || "";

  async function handleLogin() {
    if (selectedUser && password) {
      await login(selectedUser, password);
    }
  }

  return (
    <>
      <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0, textAlign: "center" }}>
        登录: <strong style={{ color: "var(--text-primary)" }}>{displayLabel}</strong>
      </p>

      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
        <label style={labelStyle}>密码</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !loading && handleLogin()}
          placeholder="输入密码"
          disabled={loading}
          autoFocus
          style={inputStyle}
          onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
        />
      </div>

      <PrimaryButton onClick={handleLogin} disabled={!password} loading={loading}>
        <LogIn size={16} />
        登录
      </PrimaryButton>

      <BackLink onClick={backToUserSelect}>返回选择用户</BackLink>

      {error && <ErrorBanner message={error} />}
    </>
  );
}

function StepRegister() {
  const { register, loading, error, backToUserSelect } = useConnectionStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState("");

  function handleRegister() {
    setLocalError("");
    if (!username.trim()) {
      setLocalError("用户名不能为空");
      return;
    }
    if (password.length < 4) {
      setLocalError("密码至少 4 位");
      return;
    }
    if (password !== confirmPassword) {
      setLocalError("两次输入的密码不一致");
      return;
    }
    register(username.trim(), password);
  }

  const displayError = localError || error;

  return (
    <>
      <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: 0, textAlign: "center" }}>
        创建新用户
      </p>

      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={labelStyle}>用户名</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="alice"
            disabled={loading}
            autoFocus
            style={inputStyle}
            onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={labelStyle}>密码</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 4 位"
            disabled={loading}
            style={inputStyle}
            onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={labelStyle}>确认密码</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && handleRegister()}
            placeholder="再次输入密码"
            disabled={loading}
            style={inputStyle}
            onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
          />
        </div>
      </div>

      <PrimaryButton
        onClick={handleRegister}
        disabled={!username.trim() || !password || !confirmPassword}
        loading={loading}
      >
        <UserPlus size={16} />
        注册
      </PrimaryButton>

      <BackLink onClick={backToUserSelect}>返回选择用户</BackLink>

      {displayError && <ErrorBanner message={displayError} />}
    </>
  );
}

// ─── 主组件 ──────────────────────────────────────────

export default function ConnectPage() {
  const { authStep } = useConnectionStore();

  function renderStep() {
    switch (authStep) {
      case "url":
        return <StepUrl />;
      case "user_select":
        return <StepUserSelect />;
      case "login":
        return <StepLogin />;
      case "register":
        return <StepRegister />;
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-primary)",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
          borderRadius: 16,
          padding: 40,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 24,
        }}
      >
        {/* Logo + 标题 */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: "var(--accent-light)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Mountain size={28} style={{ color: "var(--accent)" }} />
          </div>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            StockScape
          </h1>
        </div>

        {renderStep()}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
