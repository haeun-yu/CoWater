"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { getAgentsApiUrl, getCoreApiUrl } from "@/lib/publicUrl";
import { useAlertStore } from "@/stores/alertStore";
import { useAgentStore } from "@/stores/agentStore";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platformStore";
import type { AlertStatus, CommandResponse, CommandRole } from "@/types";

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<{
    0: { transcript: string };
    isFinal?: boolean;
  }>;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike;
}

interface ParsedCommandPreview {
  intent: string;
  summary: string;
  required_role: CommandRole;
  target_type: string;
  target_id: string;
  arguments: Record<string, unknown>;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  timestamp: Date;
  error?: boolean;
  pending?: boolean;
  // 명령어 미리보기 전용 필드
  commandPreview?: ParsedCommandPreview;
  commandOriginalText?: string;
  commandSource?: "text" | "voice";
  commandStatus?: "pending" | "confirmed" | "cancelled" | "executed" | "failed";
  commandResult?: string;
  commandBlockedReason?: string;
}

const QUICK_PROMPTS = [
  "현재 상황을 요약해줘",
  "가장 위험한 경보를 설명해줘",
  "지금 어떤 조치가 필요해?",
  "선박 충돌 위험이 있어?",
];

const ROLE_ORDER = { viewer: 0, operator: 1, admin: 2 } as const;

export default function ChatDrawer() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [, startTransition] = useTransition();
  const [isLoading, setIsLoading] = useState(false);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [inputSource, setInputSource] = useState<"text" | "voice">("text");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const submitLockRef = useRef(false);

  const alerts = useAlertStore((s) => s.alerts);
  const setAlertStatus = useAlertStore((s) => s.updateAlert);
  const setAgentEnabled = useAgentStore((s) => s.setEnabled);
  const setAgentLevel = useAgentStore((s) => s.setLevel);
  const sessionToken = useAuthStore((s) => s.token);
  const authStatus = useAuthStore((s) => s.status);
  const authActor = useAuthStore((s) => s.actor);
  const authRole = useAuthStore((s) => s.role);
  const platforms = usePlatformStore((s) => s.platforms);
  const selectedId = usePlatformStore((s) => s.selectedId);

  const criticalCount = alerts.filter((a) => a.status === "new" && a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.status === "new" && a.severity === "warning").length;
  const platformCount = Object.keys(platforms).length;
  const selectedPlatform = selectedId ? platforms[selectedId] : null;
  const commandAuth = authStatus === "authenticated" && authActor && authRole
    ? { status: "ready" as const, actor: authActor, role: authRole, message: `${authActor} · ${authRole} 권한 연결됨` }
    : authStatus === "checking"
      ? { status: "checking" as const, actor: null, role: null, message: "권한을 확인하는 중입니다." }
      : { status: "missing" as const, actor: null, role: null, message: "로그인이 필요합니다." };

  useEffect(() => {
    fetch(`${getAgentsApiUrl()}/agents/chat-agent`)
      .then((r) => r.json())
      .then((d) => { if (d.model_name) setCurrentModel(d.model_name); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setVoiceSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  async function sendUnified(text: string, source: "text" | "voice" = "text") {
    const trimmed = text.trim();
    if (!trimmed || isLoading || submitLockRef.current) return;

    submitLockRef.current = true;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setInputSource("text");
    setIsLoading(true);

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", timestamp: new Date(), pending: true },
    ]);

    try {
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${getAgentsApiUrl()}/chat/unified`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          history,
          focus_platform_ids: selectedId ? [selectedId] : null,
          source,
          context: selectedId ? { selected_platform_id: selectedId } : null,
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
            if (data.type === "command_preview") {
              const preview = data.parsed as ParsedCommandPreview;
              const blockedReason = getCommandBlockedReason(preview.required_role);
              // 명령어 인식 — 확인 대기 카드로 교체
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: "",
                        pending: false,
                        commandPreview: data.parsed as ParsedCommandPreview,
                        commandOriginalText: trimmed,
                        commandSource: source,
                        commandStatus: "pending",
                        commandBlockedReason: blockedReason ?? undefined,
                      }
                    : m,
                ),
              );
            } else if (data.type === "chunk" && data.chunk) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + data.chunk, pending: false }
                    : m,
                ),
              );
            } else if (data.type === "done") {
              model = data.model;
            }
          } catch {
            // 파싱 실패한 청크 무시
          }
        }
      }

      if (model) {
        setCurrentModel(model);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, model } : m)),
        );
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "에이전트 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하십시오.",
                error: true,
                pending: false,
              }
            : m,
        ),
      );
    } finally {
      submitLockRef.current = false;
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  async function executeConfirmedCommand(msgId: string) {
    const msg = messages.find((m) => m.id === msgId);
    if (!msg?.commandPreview || !msg.commandOriginalText) return;

    if (!sessionToken?.trim()) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                commandStatus: "failed",
                commandResult: "로그인이 필요합니다. 로그인 후 명령을 실행하세요.",
              }
            : m,
        ),
      );
      return;
    }

    const blockedReason = getCommandBlockedReason(msg.commandPreview.required_role);
    if (blockedReason) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                commandStatus: "failed",
                commandBlockedReason: blockedReason ?? undefined,
                commandResult: blockedReason,
              }
            : m,
        ),
      );
      return;
    }

    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, commandStatus: "confirmed" } : m)),
    );

    try {
      const res = await fetch(`${getCoreApiUrl()}/commands`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionToken.trim()}`,
        },
        body: JSON.stringify({
          text: msg.commandOriginalText,
          source: msg.commandSource ?? "text",
          context: selectedId ? { selected_platform_id: selectedId } : null,
        }),
      });

      const payload = await res.json();
      if (!res.ok) {
        const detail = typeof payload?.detail === "string" ? payload.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      const command = payload as CommandResponse;
      const parts = [`명령 실행 완료`, `요약: ${command.parsed.summary}`, `주체: ${command.actor}`];
      if (command.result?.kind === "alert") {
        const alert = command.result.alert as { alert_id?: string; status?: AlertStatus } | undefined;
        if (alert?.status) parts.push(`경보 상태: ${alert.status}`);
        if (alert?.alert_id && alert.status) {
          setAlertStatus({ alert_id: alert.alert_id, status: alert.status });
        }
      } else if (command.result?.kind === "agent") {
        const r = command.result.response as Record<string, unknown> | undefined;
        if (r?.enabled !== undefined) parts.push(`활성화: ${String(r.enabled)}`);
        if (r?.level) parts.push(`레벨: ${String(r.level)}`);
        if (command.result.agent_id && typeof r?.enabled === "boolean") {
          setAgentEnabled(String(command.result.agent_id), r.enabled);
        }
        if (
          command.result.agent_id &&
          (r?.level === "L1" || r?.level === "L2" || r?.level === "L3")
        ) {
          setAgentLevel(String(command.result.agent_id), r.level);
        }
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, commandStatus: "executed", commandResult: parts.join(" · ") }
            : m,
        ),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "명령 실행 중 오류가 발생했습니다.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, commandStatus: "failed", commandResult: message }
            : m,
        ),
      );
    }
  }

  function cancelCommand(msgId: string) {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, commandStatus: "cancelled" } : m,
      ),
    );
  }

  function startVoiceCapture() {
    if (typeof window === "undefined") return;
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition || isListening) return;

    const recognition = new Recognition();
    recognition.lang = "ko-KR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      if (!transcript) return;
      setInput(transcript);
      setInputSource("voice");
      setTimeout(() => inputRef.current?.focus(), 50);
    };
    recognition.onerror = () => {
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    setIsListening(true);
    recognition.start();
  }

  function getCommandBlockedReason(requiredRole: CommandRole): string | null {
    if (commandAuth.status !== "ready" || !commandAuth.role) {
      return "명령 실행 권한 확인이 필요합니다. 먼저 토큰을 연결하세요.";
    }

    const actualRole: CommandRole = commandAuth.role;

    if (ROLE_ORDER[actualRole] < ROLE_ORDER[requiredRole]) {
      return `${requiredRole} 권한이 필요합니다. 현재 권한: ${actualRole}`;
    }

    return null;
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      startTransition(() => sendUnified(input, inputSource));
    }
  }

  return (
    <>
      {/* ── 플로팅 버튼 ────────────────────────────────────────────────────────── */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className={`fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all bg-ocean-600 hover:bg-ocean-500 text-white ${criticalCount > 0 ? "ring-2 ring-red-500 ring-offset-2 ring-offset-slate-950" : ""}`}
          title="AI 보좌관 열기"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
          {criticalCount > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
              {criticalCount}
            </span>
          )}
        </button>
      )}

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
              <span className="text-[11px] text-slate-500">대화·명령 통합 입력</span>
              {currentModel && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60 font-mono">
                  {currentModel}
                </span>
              )}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-[10px]">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${commandAuth.status === "ready" ? "bg-green-400" : commandAuth.status === "checking" ? "bg-amber-400 animate-pulse" : "bg-slate-600"}`} />
              <span className={commandAuth.status === "ready" ? "text-green-300" : "text-slate-500"}>
                {commandAuth.message}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => (window.location.href = "/login")}
              title="권한 로그인"
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                commandAuth.status === "ready"
                  ? "border-amber-700/50 text-amber-400 hover:border-amber-500"
                  : "border-slate-700 text-slate-500 hover:text-slate-300"
              }`}
            >
              ⚙
            </button>
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="text-[10px] px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-red-300 hover:border-red-500/50"
              >
                초기화
              </button>
            )}
            <button
              onClick={() => setOpen(false)}
              title="보좌관 닫기"
              className="w-8 h-8 rounded-lg border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 hover:bg-slate-900 transition-colors flex items-center justify-center"
            >
              <svg width="14" height="14" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2.3">
                <path d="M2 2l14 14M16 2L2 16" />
              </svg>
            </button>
          </div>
        </div>

        {/* 상황 요약 바 */}
        <div className="px-4 py-2 border-b border-slate-800/60 flex items-center gap-3 text-[11px] flex-shrink-0 bg-slate-900/40">
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
              <div className="flex gap-2.5">
                <div className="w-7 h-7 rounded-full bg-ocean-700 flex items-center justify-center flex-shrink-0 text-sm">
                  ⬡
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-lg rounded-tl-none px-3.5 py-2.5 max-w-[290px]">
                  <p className="text-sm text-slate-200 leading-relaxed">
                    안녕하세요. 현재 해양 상황을 실시간으로 파악하고 있습니다.
                    질문이나 명령을 자유롭게 입력하세요. 명령어가 감지되면 확인 후 실행됩니다.
                  </p>
                  <span className="text-[10px] text-slate-600 mt-1 block">AI 보좌관</span>
                </div>
              </div>
              <div className="pl-9 space-y-1.5">
                <p className="text-[11px] text-slate-500 mb-2">빠른 질문</p>
                {QUICK_PROMPTS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendUnified(q)}
                    disabled={isLoading}
                    className="block w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-800 hover:border-ocean-700 text-slate-400 hover:text-ocean-300 hover:bg-ocean-900/30 transition-colors disabled:opacity-50 disabled:hover:border-slate-800 disabled:hover:text-slate-400 disabled:hover:bg-transparent"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              msg={msg}
              onConfirm={() => executeConfirmedCommand(msg.id)}
              onCancel={() => cancelCommand(msg.id)}
            />
          ))}

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
          {inputSource === "voice" && (
            <div className="mb-1.5 text-[10px] text-amber-400 flex items-center gap-1">
              <span>🎤</span>
              <span>음성 전사 입력 — 검토 후 전송하세요</span>
            </div>
          )}
          {isLoading && (
            <div className="mb-1.5 text-[10px] text-ocean-300 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-ocean-400 animate-pulse" />
              <span>질문 전송됨 · 응답이 올 때까지 추가 전송이 잠시 잠깁니다</span>
            </div>
          )}
          {commandAuth.status !== "ready" && (
            <div className="mb-1.5 text-[10px] text-slate-500 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
              <span>일반 대화는 사용 가능하지만 명령 실행은 권한 연결 후 활성화됩니다</span>
            </div>
          )}
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setInputSource("text");
              }}
              onKeyDown={handleKeyDown}
              placeholder="질문 또는 명령 입력... 명령어는 자동 감지 후 확인됩니다"
              rows={2}
              disabled={isLoading}
              className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-900 text-sm text-slate-200 placeholder-slate-600 px-3 py-2.5 focus:outline-none focus:border-ocean-600 disabled:opacity-50 leading-relaxed"
            />
            {voiceSupported && (
              <button
                onClick={startVoiceCapture}
                disabled={isLoading || isListening}
                className={`w-10 h-10 rounded-lg border flex items-center justify-center transition-colors flex-shrink-0 ${
                  isListening
                    ? "border-red-500 bg-red-950 text-red-300 animate-pulse"
                    : "border-slate-700 bg-slate-900 text-slate-400 hover:text-ocean-300 hover:border-ocean-700"
                } disabled:opacity-50`}
                title={isListening ? "음성 인식 중..." : "음성 입력"}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 3a3 3 0 013 3v6a3 3 0 11-6 0V6a3 3 0 013-3z" />
                  <path d="M19 11a7 7 0 01-14 0M12 18v3M8 21h8" />
                </svg>
              </button>
            )}
            <button
              onClick={() => startTransition(() => sendUnified(input, inputSource))}
              disabled={isLoading || !input.trim()}
               className="min-w-[72px] h-10 rounded-lg bg-ocean-600 hover:bg-ocean-500 disabled:bg-slate-800 disabled:text-slate-500 text-white flex items-center justify-center transition-colors flex-shrink-0 px-3"
               title={isLoading ? "응답을 기다리는 중" : "메시지 전송"}
            >
              {isLoading ? (
                <span className="text-xs font-semibold">대기 중</span>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" />
                </svg>
              )}
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-slate-600">
            Shift+Enter 줄바꿈 · Enter 전송 · 명령어 감지 시 확인 후 실행
          </p>
        </div>
      </div>

      {open && (
        <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
      )}
    </>
  );
}

// ── 개별 메시지 컴포넌트 ──────────────────────────────────────────────────────

function ChatMessage({
  msg,
  onConfirm,
  onCancel,
}: {
  msg: Message;
  onConfirm: () => void;
  onCancel: () => void;
}) {
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

  // 명령어 미리보기 카드
  if (msg.commandPreview) {
    const status = msg.commandStatus;
    const preview = msg.commandPreview;

    const roleColor =
      preview.required_role === "admin"
        ? "text-red-300"
        : preview.required_role === "operator"
          ? "text-amber-300"
          : "text-slate-300";

    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-amber-700 flex items-center justify-center flex-shrink-0 text-sm">
          ⌘
        </div>
        <div className="rounded-xl rounded-tl-none border border-amber-800/50 bg-amber-950/20 px-4 py-3 max-w-[320px] w-full shadow-[0_12px_30px_rgba(120,53,15,0.18)]">
          <p className="text-[10px] font-semibold text-amber-300 uppercase tracking-wide mb-2">
            명령어 감지됨
          </p>
          <p className="text-sm text-slate-200 leading-snug mb-1">{preview.summary}</p>
          <div className="flex items-center gap-2 text-[10px] mt-1.5 mb-3">
            <span className="text-slate-500">intent:</span>
            <span className="font-mono text-slate-400">{preview.intent}</span>
            <span className="text-slate-600">·</span>
            <span className="text-slate-500">권한:</span>
            <span className={`font-semibold ${roleColor}`}>{preview.required_role}</span>
          </div>

          {status === "pending" && (
            msg.commandBlockedReason ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-400">
                {msg.commandBlockedReason}
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={onConfirm}
                  className="flex-1 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-slate-950 text-xs font-semibold transition-colors"
                >
                  실행
                </button>
                <button
                  onClick={onCancel}
                  className="flex-1 py-1.5 rounded border border-slate-700 text-slate-400 hover:text-slate-200 text-xs transition-colors"
                >
                  취소
                </button>
              </div>
            )
          )}

          {status === "confirmed" && (
            <p className="text-[11px] text-amber-400 animate-pulse">실행 중...</p>
          )}

          {status === "executed" && (
            <div>
              <span className="text-[10px] text-green-400 font-semibold">✓ 완료</span>
              {msg.commandResult && (
                <p className="text-[11px] text-slate-400 mt-0.5">{msg.commandResult}</p>
              )}
            </div>
          )}

          {status === "failed" && (
            <div>
              <span className="text-[10px] text-red-400 font-semibold">✗ 실패</span>
              {msg.commandResult && (
                <p className="text-[11px] text-red-300/80 mt-0.5">{msg.commandResult}</p>
              )}
            </div>
          )}

          {status === "cancelled" && (
            <p className="text-[10px] text-slate-600">취소됨</p>
          )}

          <span className="text-[10px] text-slate-600 mt-2 block">
            {formatTime(msg.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  // 일반 AI 응답
  return (
    <div className="flex gap-2.5">
      <div className="w-7 h-7 rounded-full bg-ocean-700 flex items-center justify-center flex-shrink-0 text-sm">
        ⬡
      </div>
      <div
        className={`rounded-xl rounded-tl-none px-4 py-3 max-w-[320px] border shadow-[0_14px_34px_rgba(15,23,42,0.32)] ${
          msg.error
            ? "bg-red-950/30 border-red-800/40"
            : "bg-slate-900 border-slate-800"
        }`}
      >
        {msg.pending && !msg.content ? (
          <div>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-ocean-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
            <p className="mt-2 text-[11px] text-ocean-300">응답 작성 중</p>
          </div>
        ) : (
          <div className={`space-y-2 ${msg.error ? "text-red-300" : "text-slate-100"}`}>
            {renderAssistantContent(msg.content, Boolean(msg.error))}
          </div>
        )}
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

function renderAssistantContent(content: string, isError: boolean) {
  const textClass = isError ? "text-red-300" : "text-slate-100";
  const normalizedContent = content
    .replace(/^보좌관\s*:\s*/gm, "")
    .replace(/([가-힣]):(?=[^\s\n])/g, "$1: ")
    .replace(/([A-Za-z0-9])([가-힣])/g, "$1 $2")
    .replace(/([가-힣])([A-Za-z0-9])/g, "$1 $2")
    .replace(/([가-힣])\(/g, "$1 (")
    .replace(/\)([가-힣])/g, ") $1")
    .replace(/([.!?])(?=[^\s\n])/g, "$1\n\n")
    .replace(/([다요죠니다]\.)\s*/g, "$1\n\n")
    .replace(/(\d+\.)\s*(?=[가-힣A-Za-z])/g, "$1 ")
    .replace(/([•-])\s*(?=[가-힣A-Za-z])/g, "$1 ")
    .replace(/\n{3,}/g, "\n\n");

  return normalizedContent
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block, index) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      const isList = lines.every((line) => /^([-•]|\d+\.)\s/.test(line));

      if (isList) {
        return (
          <ul key={`${block}-${index}`} className={`space-y-1.5 text-sm leading-6 ${textClass}`}>
            {lines.map((line, lineIndex) => (
              <li key={`${line}-${lineIndex}`} className="flex gap-2">
                <span className="mt-[7px] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-ocean-400" />
                <span>{line.replace(/^([-•]|\d+\.)\s/, "")}</span>
              </li>
            ))}
          </ul>
        );
      }

      return (
        <p key={`${block}-${index}`} className={`text-sm leading-6 whitespace-pre-wrap ${textClass}`}>
          {block}
        </p>
      );
    });
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}
