import { useEffect, useRef, useState } from 'react';
import type { CpaAlert } from '../lib/cpa';
import type { Vessel } from '../types';
import {
  MODELS,
  type ModelConfig,
  type WebLLMProgress,
  loadWebLLM,
  runInference,
} from '../lib/llm';

// ── Types ────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  ms?: number;
  model?: string;
}

interface MarineEvent {
  severity: string;
  message: string;
  type: string;
}

interface NLChatProps {
  vessels: Vessel[];
  cpaAlerts: CpaAlert[];
  events: MarineEvent[];
}

// ── Context builder ──────────────────────────────────────────────────────────

function buildSystemPrompt(
  vessels: Vessel[],
  cpaAlerts: CpaAlert[],
  events: MarineEvent[]
): string {
  const now = new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
  const vesselLines = vessels
    .map(v =>
      `• ${v.name} (${v.vesselType}, ${v.length}m${v.hazardousCargo ? ', ⚠위험물' : ''}): ` +
      `${v.latitude.toFixed(4)}°N ${v.longitude.toFixed(4)}°E | ` +
      `SOG ${v.sog.toFixed(1)}kn COG ${v.cog.toFixed(0)}° | ${v.navigationStatus} | →${v.destination}`
    )
    .join('\n');

  const alertLines =
    cpaAlerts.length > 0
      ? cpaAlerts
          .map(
            a =>
              `• ${a.nameA} ↔ ${a.nameB}: CPA ${a.cpa.toFixed(2)}해리 TCPA ${a.tcpa.toFixed(1)}분 [${a.severity === 'danger' ? '위험' : '주의'}]`
          )
          .join('\n')
      : '• 현재 충돌 경보 없음';

  const eventLines =
    events.length > 0
      ? events
          .slice(0, 8)
          .map(e => `• [${e.type}] ${e.message}`)
          .join('\n')
      : '• 최근 이벤트 없음';

  return `당신은 해양 관제 AI 어시스턴트입니다.
현재 관제 시스템의 실시간 데이터를 기반으로 운항 관제사의 질문에 정확하고 간결하게 한국어로 답변하세요.
반드시 아래 데이터만 사용하여 사실에 근거한 답변을 하고, 데이터에 없는 내용은 "데이터 없음"이라고 답하세요.

현재 시각: ${now} (KST)
관제 해역: 부산 외항 및 대한해협

## 선박 현황 (총 ${vessels.length}척)
${vesselLines}

## 활성 충돌 경보 (CPA/TCPA)
${alertLines}

## 최근 이벤트
${eventLines}`;
}

// ── Suggestion chips ─────────────────────────────────────────────────────────

const SUGGESTIONS = [
  '위험물 운반 중인 선박은?',
  '현재 충돌 위험이 가장 높은 선박은?',
  '정박 중인 선박 목록 알려줘',
  '가장 빠르게 이동 중인 선박은?',
  '부산항으로 입항 중인 선박은?',
  '현재 해역 상황을 요약해줘',
];

// ── Sub-components ───────────────────────────────────────────────────────────

function ProviderBadge({ model }: { model: ModelConfig }) {
  const color =
    model.kind === 'browser' ? 'nlc-badge--browser' : model.isFree ? 'nlc-badge--free' : 'nlc-badge--paid';
  const label = model.kind === 'browser' ? '브라우저' : model.isFree ? '무료' : '유료';
  return <span className={`nlc-badge ${color}`}>{label}</span>;
}

function DownloadWarning({ model, onConfirm, onCancel }: {
  model: ModelConfig;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="nlc-download-warn">
      <p className="nlc-download-title">⬇ 모델 다운로드 필요</p>
      <p className="nlc-download-desc">
        <strong>{model.label}</strong> 모델을 브라우저에 다운로드합니다.
        <br />
        크기: ~{model.description.split('·')[0].trim()}
        <br />
        다운로드 후 IndexedDB에 캐시되어 재사용됩니다.
      </p>
      <div className="nlc-download-actions">
        <button className="nlc-btn nlc-btn-primary" onClick={onConfirm}>다운로드 시작</button>
        <button className="nlc-btn nlc-btn-ghost" onClick={onCancel}>취소</button>
      </div>
    </div>
  );
}

function ProgressBar({ progress }: { progress: WebLLMProgress }) {
  return (
    <div className="nlc-progress-wrap">
      <div className="nlc-progress-bar" style={{ width: `${progress.pct}%` }} />
      <p className="nlc-progress-msg">{progress.msg}</p>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function NLChat({ vessels, cpaAlerts, events }: NLChatProps) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string>(MODELS[0].id);
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [wllmProgress, setWllmProgress] = useState<WebLLMProgress>({ status: 'idle', pct: 0, msg: '' });
  const [showDownloadWarn, setShowDownloadWarn] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const model = MODELS.find(m => m.id === selectedId) ?? MODELS[0];

  // Load API key from localStorage when model changes
  useEffect(() => {
    if (model.kind === 'api' && model.provider) {
      const stored = localStorage.getItem(`nlc-key-${model.provider}`);
      setApiKey(stored ?? '');
    }
  }, [model.id, model.kind, model.provider]);

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  const saveApiKey = (key: string) => {
    setApiKey(key);
    if (key) localStorage.setItem(`nlc-key-${model.provider}`, key);
  };

  const selectModel = (id: string) => {
    setSelectedId(id);
    setShowModelMenu(false);
    setMessages([]);
    setWllmProgress({ status: 'idle', pct: 0, msg: '' });
  };

  const historyForInference = messages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(-10)
    .map(m => ({ role: m.role as 'user' | 'assistant', content: m.text }));

  const handleSend = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', text: msg };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    // Browser model: check if loaded
    if (model.kind === 'browser' && wllmProgress.status !== 'ready') {
      setShowDownloadWarn(true);
      setLoading(false);
      return;
    }

    const result = await runInference({
      model,
      systemPrompt: buildSystemPrompt(vessels, cpaAlerts, events),
      history: historyForInference,
      message: msg,
      apiKey: model.kind === 'api' ? apiKey : undefined,
    });

    setLoading(false);
    if (result.ok) {
      setMessages(prev => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', text: result.text, ms: result.ms, model: model.label },
      ]);
    } else {
      setMessages(prev => [
        ...prev,
        { id: `e-${Date.now()}`, role: 'error', text: result.error },
      ]);
    }
  };

  const startDownload = async () => {
    setShowDownloadWarn(false);
    setWllmProgress({ status: 'loading', pct: 0, msg: '초기화 중...' });
    try {
      await loadWebLLM(model, setWllmProgress);
    } catch (e) {
      setWllmProgress({ status: 'error', pct: 0, msg: e instanceof Error ? e.message : '로드 실패' });
    }
  };

  const needsKey = model.kind === 'api' && !apiKey;

  const browserModels = MODELS.filter(m => m.kind === 'browser');
  const apiModels = MODELS.filter(m => m.kind === 'api');

  return (
    <>
      {/* Floating toggle button */}
      <button
        className={`nlc-fab${open ? ' nlc-fab--open' : ''}`}
        onClick={() => setOpen(v => !v)}
        title="AI 어시스턴트"
        aria-label="AI 어시스턴트 열기"
      >
        {open ? '✕' : '💬'}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="nlc-panel">
          {/* Header */}
          <div className="nlc-header">
            <span className="nlc-title">🤖 해양 AI 어시스턴트</span>
            <button className="nlc-close" onClick={() => setOpen(false)} aria-label="닫기">✕</button>
          </div>

          {/* Model selector */}
          <div className="nlc-model-row">
            <div className="nlc-model-trigger-wrap">
              <button
                className="nlc-model-trigger"
                onClick={() => setShowModelMenu(v => !v)}
              >
                <ProviderBadge model={model} />
                <span className="nlc-model-name">{model.label}</span>
                <span className="nlc-model-desc">{model.description}</span>
                <span className="nlc-chevron">{showModelMenu ? '▲' : '▼'}</span>
              </button>

              {showModelMenu && (
                <div className="nlc-model-menu">
                  <div className="nlc-model-group-label">🌐 브라우저 (무료 · 프라이버시)</div>
                  {browserModels.map(m => (
                    <button
                      key={m.id}
                      className={`nlc-model-item${m.id === selectedId ? ' selected' : ''}`}
                      onClick={() => selectModel(m.id)}
                    >
                      <div className="nlc-model-item-top">
                        <ProviderBadge model={m} />
                        <span>{m.label}</span>
                      </div>
                      <div className="nlc-model-item-desc">{m.description}</div>
                    </button>
                  ))}
                  <div className="nlc-model-group-label">☁ 서버 API</div>
                  {apiModels.map(m => (
                    <button
                      key={m.id}
                      className={`nlc-model-item${m.id === selectedId ? ' selected' : ''}`}
                      onClick={() => selectModel(m.id)}
                    >
                      <div className="nlc-model-item-top">
                        <ProviderBadge model={m} />
                        <span>{m.label}</span>
                      </div>
                      <div className="nlc-model-item-desc">{m.description}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* API key input */}
            {model.kind === 'api' && (
              <div className="nlc-key-row">
                <div className="nlc-key-input-wrap">
                  <input
                    type={showKey ? 'text' : 'password'}
                    className="nlc-key-input"
                    placeholder={model.keyPlaceholder ?? 'API Key'}
                    value={apiKey}
                    onChange={e => saveApiKey(e.target.value)}
                  />
                  <button
                    className="nlc-key-eye"
                    onClick={() => setShowKey(v => !v)}
                    type="button"
                    title={showKey ? '숨기기' : '보기'}
                  >
                    {showKey ? '🙈' : '👁'}
                  </button>
                </div>
                {model.keyHint && (
                  <span className="nlc-key-hint">{model.keyLabel} · {model.keyHint}</span>
                )}
              </div>
            )}

            {/* WebLLM progress */}
            {model.kind === 'browser' && wllmProgress.status === 'loading' && (
              <ProgressBar progress={wllmProgress} />
            )}
            {model.kind === 'browser' && wllmProgress.status === 'ready' && (
              <div className="nlc-ready-badge">✓ 모델 로드 완료</div>
            )}
            {model.kind === 'browser' && wllmProgress.status === 'error' && (
              <div className="nlc-error-badge">✕ {wllmProgress.msg}</div>
            )}
          </div>

          {/* Download warning modal */}
          {showDownloadWarn && (
            <DownloadWarning
              model={model}
              onConfirm={startDownload}
              onCancel={() => setShowDownloadWarn(false)}
            />
          )}

          {/* Messages */}
          <div className="nlc-messages">
            {messages.length === 0 && !showDownloadWarn && (
              <div className="nlc-suggestions">
                <p className="nlc-suggestions-title">질문 예시</p>
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    className="nlc-suggestion-chip"
                    onClick={() => handleSend(s)}
                    disabled={loading || needsKey}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map(msg => (
              <div key={msg.id} className={`nlc-msg nlc-msg--${msg.role}`}>
                {msg.role === 'user' && <div className="nlc-msg-bubble nlc-msg-bubble--user">{msg.text}</div>}
                {msg.role === 'assistant' && (
                  <>
                    <div className="nlc-msg-bubble nlc-msg-bubble--assistant">{msg.text}</div>
                    <div className="nlc-msg-meta">
                      {msg.model} · {msg.ms != null ? `${(msg.ms / 1000).toFixed(1)}s` : ''}
                    </div>
                  </>
                )}
                {msg.role === 'error' && (
                  <div className="nlc-msg-bubble nlc-msg-bubble--error">⚠ {msg.text}</div>
                )}
              </div>
            ))}

            {loading && (
              <div className="nlc-msg nlc-msg--assistant">
                <div className="nlc-msg-bubble nlc-msg-bubble--assistant nlc-thinking">
                  <span /><span /><span />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="nlc-input-row">
            {needsKey && (
              <div className="nlc-need-key">API 키를 먼저 입력하세요</div>
            )}
            {!needsKey && (
              <>
                <input
                  ref={inputRef}
                  className="nlc-input"
                  placeholder={loading ? '답변 생성 중...' : '해역 현황에 대해 질문하세요'}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  disabled={loading}
                />
                <button
                  className="nlc-send"
                  onClick={() => handleSend()}
                  disabled={loading || !input.trim()}
                  aria-label="전송"
                >
                  ↑
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
