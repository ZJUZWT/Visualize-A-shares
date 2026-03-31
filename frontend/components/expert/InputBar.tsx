"use client";

import { useState, useRef, useCallback } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { ArrowUp, Square, Download, BrainCircuit, MessageSquareMore, FileBarChart, Image as ImageIcon, X } from "lucide-react";

interface InputBarProps {
  onExport?: () => void;
}

/** 将 File 转为 base64 data URI */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/** 从 ClipboardEvent 或 DataTransfer 中提取图片文件 */
function extractImageFiles(items: DataTransferItemList | undefined): File[] {
  if (!items) return [];
  const files: File[] = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return files;
}

export function InputBar({ onExport }: InputBarProps) {
  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const {
    sendMessage, stopStreaming, status, error, activeExpert,
    profiles, chatHistories, deepThink, toggleDeepThink,
    useClarification, toggleClarification,
    useTradePlan, toggleTradePlan,
    pendingClarifications,
  } = useExpertStore();
  const isThinking = status === "thinking";
  const pendingClarification = pendingClarifications[activeExpert];
  const isBusy = isThinking || !!pendingClarification;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const profile = profiles.find((p) => p.type === activeExpert);
  const color = profile?.color ?? "#60A5FA";
  const hasMessages = (chatHistories[activeExpert] ?? []).length > 0;

  const handleSend = async () => {
    if ((!input.trim() && pendingImages.length === 0) || isBusy) return;
    const msg = input || (pendingImages.length > 0 ? "请看图片" : "");
    const imgs = pendingImages.length > 0 ? [...pendingImages] : undefined;
    setInput("");
    setPendingImages([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessage(msg, imgs);
  };

  const handleStop = () => {
    stopStreaming();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 输入法正在组合中（如拼音选词、日文假名确认），Enter 交给 IME 处理，不触发发送
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (isThinking) {
        handleStop();
      } else if (!pendingClarification) {
        handleSend();
      }
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  };

  /** 处理粘贴事件 — 拦截图片 */
  const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
    const imageFiles = extractImageFiles(e.clipboardData?.items);
    if (imageFiles.length === 0) return; // 不是图片，走默认文本粘贴
    e.preventDefault(); // 阻止图片作为文本粘贴
    try {
      const newImages = await Promise.all(imageFiles.map(fileToBase64));
      setPendingImages((prev) => [...prev, ...newImages].slice(0, 4)); // 最多 4 张
    } catch (err) {
      console.error("图片粘贴失败:", err);
    }
  }, []);

  /** 文件选择器 */
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    try {
      const newImages = await Promise.all(files.map(fileToBase64));
      setPendingImages((prev) => [...prev, ...newImages].slice(0, 4));
    } catch (err) {
      console.error("图片选择失败:", err);
    }
    // 清空 input 以便重复选同一文件
    e.target.value = "";
  }, []);

  const removeImage = useCallback((index: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  return (
    <div className="px-6 pb-4 pt-2 shrink-0">
      {error && (
        <div className="mb-2 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* 图片预览区 */}
      {pendingImages.length > 0 && (
        <div className="mb-2 flex gap-2 flex-wrap">
          {pendingImages.map((img, i) => (
            <div key={i} className="relative group">
              <img
                src={img}
                alt={`待发送图片 ${i + 1}`}
                className="h-16 w-16 rounded-lg object-cover border border-[var(--border)]"
              />
              <button
                onClick={() => removeImage(i)}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-[var(--bg-primary)] border border-[var(--border)]
                           flex items-center justify-center text-[var(--text-tertiary)] hover:text-red-500
                           opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className="flex items-end gap-2 px-4 py-3 rounded-2xl border border-[var(--border)]
                    bg-[var(--bg-secondary)] shadow-[var(--shadow-sm)]
                    focus-within:shadow-[var(--shadow-md)]
                    transition-all duration-150"
        style={
          {
            "--input-focus-color": color,
          } as React.CSSProperties
        }
      >
        {/* 导出按钮 */}
        {hasMessages && !isThinking && onExport && (
          <button
            onClick={onExport}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]
                       hover:bg-[var(--bg-primary)] transition-all duration-150"
            title="导出对话"
          >
            <Download size={14} />
          </button>
        )}

        {/* 图片上传按钮 */}
        <button
          onClick={() => fileInputRef.current?.click()}
          className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                     text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]
                     hover:bg-[var(--bg-primary)] transition-all duration-150"
          title="上传图片（也可直接粘贴截图）"
        >
          <ImageIcon size={14} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleFileSelect}
        />

        {/* 深度思考开关 */}
        <button
          onClick={toggleDeepThink}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${deepThink
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={deepThink ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={deepThink ? "深度思考已开启：AI 会多轮查询数据后再回答" : "点击开启深度思考：AI 可以看一步查一步，分析更深入"}
        >
          <BrainCircuit size={13} />
          <span>深度</span>
        </button>

        {/* 澄清开关 */}
        <button
          onClick={toggleClarification}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${useClarification
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={useClarification ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={useClarification ? "澄清已开启：AI 会先确认分析方向" : "点击开启澄清：AI 先询问再分析，更精准"}
        >
          <MessageSquareMore size={13} />
          <span>澄清</span>
        </button>

        {/* 策略卡片开关 */}
        <button
          onClick={toggleTradePlan}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${useTradePlan
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={useTradePlan ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={useTradePlan ? "策略卡片已开启：AI 会在分析具体股票时生成交易计划" : "点击开启策略卡片：AI 分析具体股票时可生成交易计划"}
        >
          <FileBarChart size={13} />
          <span>策略</span>
        </button>

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={
            isThinking
              ? "AI 正在思考… 按 Enter 或点击按钮停止"
              : pendingClarification
              ? "请先选择上方的分析方向，然后继续生成"
              : `向${profile?.name ?? "专家"}提问… (Enter 发送，Shift+Enter 换行，可粘贴图片)`
          }
          rows={1}
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)]
                     placeholder:text-[var(--text-tertiary)] resize-none outline-none
                     leading-relaxed"
          style={{ minHeight: 24, maxHeight: 160 }}
          disabled={!!pendingClarification}
          onFocus={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = color;
          }}
          onBlur={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = "";
          }}
        />

        {/* 思考中：始终显示停止按钮（不管输入框是否有内容） */}
        {isThinking ? (
          <button
            onClick={handleStop}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       transition-all duration-150 text-white bg-red-500 hover:bg-red-600"
          >
            <Square size={13} className="fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={(!input.trim() && pendingImages.length === 0) || !!pendingClarification}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       transition-all duration-150 text-white
                       disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              backgroundColor: (!input.trim() && pendingImages.length === 0) ? "var(--border)" : color,
            }}
          >
            <ArrowUp size={15} strokeWidth={2.5} />
          </button>
        )}
      </div>
      <p className="text-center text-[10px] text-[var(--text-tertiary)] mt-2">
        {pendingClarification && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            请选择一个分析方向
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {deepThink && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <BrainCircuit size={10} />
            深度思考
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {useClarification && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <MessageSquareMore size={10} />
            澄清
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {useTradePlan && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <FileBarChart size={10} />
            策略卡片
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {activeExpert === "rag"
          ? "投资顾问会主动查询行情数据，并在对话中更新自己的认知"
          : `${profile?.name ?? "专家"}会调用引擎工具获取数据并生成分析`}
      </p>
    </div>
  );
}
