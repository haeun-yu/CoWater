"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";

const AGENTS_URL = process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:7701";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  timestamp: Date;
  error?: boolean;
}

// 상황 요약 빠른 질문 템플릿
const QUICK_PROMPTS = [
  "현재 상황을 요약해줘",
  "가장 위험한 경보를 설명해줘",
  "지금 어떤 조치가 필요해?",
  "선박 충돌 위험이 있어?",
];

export default function ChatDrawer() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isPending, startTransition] = useTransition();
  const [isLoading, setIsLoading] = useState(false);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const alerts = useAlertStore((s) => s.alerts);
  const platforms = usePlatformStore((s) => s.platforms);
  const selectedId = usePlatformStore((s) => s.selectedId);

  const criticalCount = alerts.filter((a) => a.status === "new" && a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.status === "new" && a.severity === "warning").length;
  const platformCount = Object.keys(platforms).length;
  const selectedPlatform = selectedId ? platforms[selectedId] : null;

  // 현재 LLM 모델 조회
  useEffect(() => {
    fetch(`${AGENTS_URL}/agents/chat-agent`)
      .then((r) => r.json())
      .then((d) => { if (d.model_name) setCurrentModel(d.model_name); })
      .catch(() => {});
  }, []);

  // 드로어 열릴 때 입력창 포커스
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  // 새 메시지 시 스크롤
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Escape 키로 닫기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // 어시스턴트 메시지 플레이스홀더 먼저 추가 (스트리밍 중 내용 채워짐)
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", timestamp: new Date() },
    ]);

    try {
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${AGENTS_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          history,
          focus_platform_ids: selectedId ? [selectedId] : null,
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let model: string | undefined;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        for (const line of text.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + data.chunk }
                    : m,
                ),
              );
            }
            if (data.done) {
              model = data.model;
            }
          } catch {
            // 파싱 실패한 청크 무시
          }
        }
      }

      // 모델명 업데이트
      if (model) {
        setCurrentModel(model);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, model } : m)),
        );
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "에이전트 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하십시오.",
                error: true,
              }
            : m,
        ),
      );
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      startTransition(() => { sendMessage(input); });
    }
  }

  return (
    <>
      {/* ── 플로팅 버튼 ────────────────────────────────────────────────────────── */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={`fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all ${
          open
            ? "bg-ocean-700 text-white"
            : "bg-ocean-600 hover:bg-ocean-500 text-white"
        } ${criticalCount > 0 && !open ? "ring-2 ring-red-500 ring-offset-2 ring-offset-slate-950" : ""}`}
        title={open ? "챗봇 닫기" : "AI 보좌관 열기"}
      >
        {open ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M2 2l14 14M16 2L2 16" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
        )}
        {/* 긴급 경보 배지 */}
        {criticalCount > 0 && !open && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {criticalCount}
          </span>
        )}
      </button>

      {/* ── 드로어 패널 ────────────────────────────────────────────────────────── */}
      <div
        className={`fixed right-0 top-11 bottom-0 z-40 w-[380px] bg-slate-950 border-l border-slate-800 flex flex-col shadow-2xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* 헤더 */}
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-white">AI 보좌관</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-ocean-800/60 text-ocean-300 border border-ocean-700/40">
                CoWater Assistant
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[11px] text-slate-500">현재 상황 기반 실시간 해양 운항 지원</span>
              {currentModel && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60 font-mono">
                  {currentModel}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="text-[10px] px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-red-300 hover:border-red-500/50"
              >
                초기화
              </button>
            )}
          </div>
        </div>

        {/* 상황 요약 바 */}
        <div className="px-4 py-2.5 border-b border-slate-800/60 flex items-center gap-3 text-[11px] flex-shrink-0 bg-slate-900/40">
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            <span className="font-mono text-white">{platformCount}</span>척
          </div>
          {criticalCount > 0 && (
            <div className="flex items-center gap-1 text-red-400 font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              위험 {criticalCount}건
            </div>
          )}
          {warningCount > 0 && (
            <div className="flex items-center gap-1 text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              주의 {warningCount}건
            </div>
          )}
          {criticalCount === 0 && warningCount === 0 && (
            <span className="text-slate-500">활성 경보 없음</span>
          )}
          {selectedPlatform && (
            <>
              <span className="text-slate-700">·</span>
              <span className="text-ocean-400">
                선택:{" "}
                <span className="text-ocean-200 font-mono">
                  {selectedPlatform.name ?? selectedId}
                </span>
              </span>
            </>
          )}
        </div>

        {/* 메시지 영역 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-4">
              {/* 인트로 메시지 */}
              <div className="flex gap-2.5">
                <div className="w-7 h-7 rounded-full bg-ocean-700 flex items-center justify-center flex-shrink-0 text-sm">
                  ⬡
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-lg rounded-tl-none px-3.5 py-2.5 max-w-[290px]">
                  <p className="text-sm text-slate-200 leading-relaxed">
                    안녕하세요. 현재 해양 상황을 실시간으로 파악하고 있습니다.
                    상황 요약이나 대처 방법에 대해 무엇이든 물어보세요.
                  </p>
                  <span className="text-[10px] text-slate-600 mt-1 block">AI 보좌관</span>
                </div>
              </div>

              {/* 빠른 질문 */}
              <div className="pl-9 space-y-1.5">
                <p className="text-[11px] text-slate-500 mb-2">빠른 질문</p>
                {QUICK_PROMPTS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="block w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-800 hover:border-ocean-700 text-slate-400 hover:text-ocean-300 hover:bg-ocean-900/30 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} msg={msg} />
          ))}

          {/* 타이핑 인디케이터 */}
          {isLoading && (
            <div className="flex gap-2.5">
              <div className="w-7 h-7 rounded-full bg-ocean-700 flex items-center justify-center flex-shrink-0 text-sm">
                ⬡
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg rounded-tl-none px-3.5 py-3 flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* 입력 영역 */}
        <div className="px-4 py-3 border-t border-slate-800 flex-shrink-0">
          {selectedPlatform && (
            <div className="mb-2 text-[10px] text-ocean-500 flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ocean-500" />
              컨텍스트: {selectedPlatform.name ?? selectedId} 선박 정보 포함
            </div>
          )}
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="상황 요약, 대처 방법, 질문... (Enter로 전송)"
              rows={2}
              disabled={isLoading}
              className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-900 text-sm text-slate-200 placeholder-slate-600 px-3 py-2.5 focus:outline-none focus:border-ocean-600 disabled:opacity-50 leading-relaxed"
            />
            <button
              onClick={() => startTransition(() => { sendMessage(input); })}
              disabled={isLoading || !input.trim()}
              className="w-10 h-10 rounded-lg bg-ocean-600 hover:bg-ocean-500 disabled:bg-slate-800 disabled:text-slate-600 text-white flex items-center justify-center transition-colors flex-shrink-0"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" />
              </svg>
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-slate-600">
            Shift+Enter 줄바꿈 · Enter 전송
          </p>
        </div>
      </div>

      {/* 드로어 열릴 때 배경 오버레이 (선택) */}
      {open && (
        <div
          className="fixed inset-0 z-30"
          onClick={() => setOpen(false)}
        />
      )}
    </>
  );
}

// ── 개별 메시지 컴포넌트 ──────────────────────────────────────────────────────

function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end gap-2.5">
        <div className="bg-ocean-700 rounded-lg rounded-tr-none px-3.5 py-2.5 max-w-[290px]">
          <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">{msg.content}</p>
          <span className="text-[10px] text-ocean-300/70 mt-1 block text-right">
            {formatTime(msg.timestamp)}
          </span>
        </div>
        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 text-xs text-slate-300">
          ▲
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5">
      <div className="w-7 h-7 rounded-full bg-ocean-700 flex items-center justify-center flex-shrink-0 text-sm">
        ⬡
      </div>
      <div
        className={`rounded-lg rounded-tl-none px-3.5 py-2.5 max-w-[290px] border ${
          msg.error
            ? "bg-red-950/30 border-red-800/40"
            : "bg-slate-900 border-slate-800"
        }`}
      >
        <p
          className={`text-sm leading-relaxed whitespace-pre-wrap ${
            msg.error ? "text-red-300" : "text-slate-200"
          }`}
        >
          {msg.content}
        </p>
        <div className="flex items-center justify-between mt-1.5 gap-2">
          {msg.model && (
            <span className="text-[10px] text-slate-600 font-mono truncate">
              {msg.model}
            </span>
          )}
          <span className="text-[10px] text-slate-600 ml-auto flex-shrink-0">
            {formatTime(msg.timestamp)}
          </span>
        </div>
      </div>
    </div>
  );
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}
