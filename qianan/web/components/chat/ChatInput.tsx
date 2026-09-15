"use client";

/**
 * 千岸 QianAn — 底部输入框（WorkBuddy 风格）
 *
 * 单一容器：顶部工具栏（附件/图片按钮）+ 中间 textarea + 底栏（提示 + 发送按钮在框内右下角）。
 * Enter 发送 / Shift+Enter 换行。Loading 时发送按钮变为停止。
 */

import { useRef, useCallback, useEffect, useState } from "react";
import { Paperclip, Image as ImageIcon, ArrowUp, Square, X } from "lucide-react";

interface ChatInputProps {
  inputValue: string;
  isLoading: boolean;
  onChange: (value: string) => void;
  onSend: (message: string, images?: string[]) => void;
  onStop: () => void;
}

const MAX_ROWS = 6;
const LINE_HEIGHT = 22;

export function ChatInput({
  inputValue,
  isLoading,
  onChange,
  onSend,
  onStop,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingImages, setPendingImages] = useState<string[]>([]);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = LINE_HEIGHT * MAX_ROWS;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    autoResize();
  }, [inputValue, autoResize]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    const trimmed = inputValue.trim();
    if ((!trimmed && pendingImages.length === 0) || isLoading) return;
    onSend(trimmed, pendingImages.length > 0 ? pendingImages : undefined);
    setPendingImages([]);
  };

  // 文件选择
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () => {
        setPendingImages((prev) => [...prev, reader.result as string]);
      };
      reader.readAsDataURL(file);
    }
    // 重置 input 允许重复选择同一文件
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // 拖拽上传
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () => {
        setPendingImages((prev) => [...prev, reader.result as string]);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  // 粘贴图片
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (!file) continue;
        const reader = new FileReader();
        reader.onload = () => {
          setPendingImages((prev) => [...prev, reader.result as string]);
        };
        reader.readAsDataURL(file);
      }
    }
  };

  return (
    <div
      className="px-4 pb-5 pt-3 bg-gray-900"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className="max-w-3xl mx-auto">
        {/* 待发送图片预览 */}
        {pendingImages.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {pendingImages.map((img, i) => (
              <div key={i} className="relative group">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img}
                  alt={`待发送 ${i + 1}`}
                  className="w-16 h-16 object-cover rounded-lg border border-gray-700"
                />
                <button
                  onClick={() => setPendingImages((prev) => prev.filter((_, idx) => idx !== i))}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-gray-600 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 输入容器：统一一个框 — WorkBuddy 风格布局 */}
        <div className="bg-gray-800 rounded-2xl border border-gray-700 shadow-lg overflow-hidden focus-within:border-gray-500 transition-colors">
          {/* 顶部工具栏 */}
          <div className="flex items-center gap-0.5 px-2 pt-1.5">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors"
              title="上传图片"
            >
              <ImageIcon size={18} />
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors"
              title="添加附件"
            >
              <Paperclip size={18} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>

          {/* 输入区域 */}
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="描述这次要上的商品，或拖入图片、粘贴链接（一个会话 = 一次上新任务）"
            rows={1}
            disabled={isLoading}
            className="w-full border-none outline-none resize-none bg-transparent text-gray-100 placeholder-gray-500 px-4 py-2 leading-relaxed disabled:opacity-60"
            style={{ minHeight: LINE_HEIGHT, maxHeight: LINE_HEIGHT * MAX_ROWS }}
          />

          {/* 底栏：提示 + 发送按钮（在框内右下角） */}
          <div className="flex items-center justify-between px-3 pb-2 pt-1">
            <span className="text-[10px] text-gray-600 select-none">
              Enter 发送 · Shift+Enter 换行 · 一个会话完成一次上新
            </span>
            {isLoading ? (
              <button
                onClick={onStop}
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
                title="停止"
              >
                <Square size={14} className="fill-current" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!inputValue.trim() && pendingImages.length === 0}
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition-colors disabled:opacity-20 disabled:cursor-not-allowed disabled:hover:bg-violet-600"
                title="发送"
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
