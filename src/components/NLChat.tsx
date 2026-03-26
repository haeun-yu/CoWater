import { useEffect, useRef, useState } from 'react';
import type { CpaAlert } from '../lib/cpa';
import type { Vessel } from '../types';
import {
  MODELS,
  type ModelConfig,
  type WebLLMProgress,
  loadWebLLM,
  loadTransformers,
  isBrowserModelLoaded,
  checkOllamaModel,
  pullOllamaModel,
  runInference,
} from '../lib/llm';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  ms?: number;
  model?: string;
}

interface MarineEvent { severity: string; message: string; type: string; }

interface NLChatProps {
  vessels: Vessel[];
  cpaAlerts: CpaAlert[];
  events: MarineEvent[];
}

// ── Context builder ────────────────────────────────────────────────────────────

function buildSystemPrompt(vessels: Vessel[], cpaAlerts: CpaAlert[], events: MarineEvent[]): string {
  const now = new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
  const vesselLines = vessels.map(v =>
    `• ${v.name} (${v.vesselType}, ${v.length}m${v.hazardousCargo ? ', ⚠위험물' : ''}): ` +
    `${v.latitude.toFixed(4)}°N ${v.longitude.toFixed(4)}°E | ` +
    `SOG ${v.sog.toFixed(1)}kn COG ${v.cog.toFixed(0)}° | ${v.navigationStatus} | →${v.destination}`
  ).join('\n');

  const alertLines = cpaAlerts.length > 0
    ? cpaAlerts.map(a => `• ${a.nameA} ↔ ${a.nameB}: CPA ${a.cpa.toFixed(2)}해리 TCPA ${a.tcpa.toFixed(1)}분 [${a.severity === 'danger' ? '위험' : '주의'}]`).join('\n')
    : '• 현재 충돌 경보 없음';

  const eventLines = events.length > 0
    ? events.slice(0, 8).map(e => `• [${e.type}] ${e.message}`).join('\n')
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

// ── Constants ──────────────────────────────────────────────────────────────────

const SUGGESTIONS = [
  '위험물 운반 중인 선박은?',
  '현재 충돌 위험이 가장 높은 선박은?',
  '정박 중인 선박 목록 알려줘',
  '가장 빠르게 이동 중인 선박은?',
  '부산항으로 입항 중인 선박은?',
  '현재 해역 상황을 요약해줘',
];

const TIMEOUT_MS = 90_000;

// ── Sub-components ─────────────────────────────────────────────────────────────

function ProviderBadge({ model }: { model: ModelConfig }) {
  // 브라우저 = API 키 불필요, 진짜 무료
  // isFree API = 무료 할당량 있는 서버 (HF/Groq/Gemini) — 토큰 소진됨
  // !isFree = 유료 API
  const color =
    model.kind === 'local'
      ? 'nlc-badge--local'
      : model.kind === 'browser'
      ? 'nlc-badge--browser'
      : 'nlc-badge--paid';
  const label =
    model.kind === 'local' ? 'Ollama' : model.kind === 'browser' ? '브라우저' : '유료';
  const title =
    model.kind === 'local'
      ? 'API 키 불필요 · 로컬 Ollama 실행'
      : model.kind === 'browser'
      ? 'API 키 불필요 · 브라우저 로컬 실행'
      : '유료 API · API 키 필요';
  return <span className={`nlc-badge ${color}`} title={title}>{label}</span>;
}

function ModelItem({ m, selected, onSelect }: { m: ModelConfig; selected: string; onSelect: (id: string) => void }) {
  return (
    <button className={`nlc-model-item${m.id === selected ? ' selected' : ''}`} onClick={() => onSelect(m.id)}>
      <div className="nlc-model-item-top">
        <ProviderBadge model={m} />
        <span>{m.label}</span>
        <span className="nlc-license-tag">{m.license}</span>
      </div>
      <div className="nlc-model-item-desc">{m.description}</div>
    </button>
  );
}

// ── Download screen (replaces messages area) ───────────────────────────────────

function DownloadScreen({ model, progress, onStart, onCancel }: {
  model: ModelConfig;
  progress: WebLLMProgress;
  onStart: () => void;
  onCancel: () => void;
}) {
  const isLoading = progress.status === 'loading';
  const isChecking = isLoading && progress.msg === '모델 확인 중...';
  const sizePart = model.description.split('·').find(s => s.includes('GB') || s.includes('MB'))?.trim() ?? model.description.split('·')[0].trim();
  const hint = model.kind === 'local'
    ? 'Ollama가 모델을 로컬에 다운로드합니다 (한 번만)'
    : '다운로드 후 브라우저 IndexedDB에 캐시됩니다';

  return (
    <div className="nlc-download-screen">
      <div className="nlc-download-icon">⬇</div>
      <p className="nlc-download-title">{model.label}</p>
      <p className="nlc-download-meta">{model.license} · {sizePart}</p>
      <p className="nlc-download-hint">{hint}</p>

      {isChecking && (
        <div className="nlc-dl-progress">
          <div className="nlc-dl-bar-track"><div className="nlc-dl-bar-fill" style={{ width: '100%', opacity: 0.4 }} /></div>
          <div className="nlc-dl-stats"><span className="nlc-dl-msg">설치 여부 확인 중...</span></div>
        </div>
      )}

      {!isLoading && progress.status !== 'error' && (
        <div className="nlc-download-actions">
          <button className="nlc-btn nlc-btn-primary" onClick={onStart}>다운로드 시작</button>
          <button className="nlc-btn nlc-btn-ghost" onClick={onCancel}>모델 변경</button>
        </div>
      )}

      {isLoading && (
        <div className="nlc-dl-progress">
          <div className="nlc-dl-bar-track">
            <div className="nlc-dl-bar-fill" style={{ width: `${progress.pct}%` }} />
          </div>
          <div className="nlc-dl-stats">
            <span className="nlc-dl-pct">{progress.pct}%</span>
            <span className="nlc-dl-msg">{progress.msg}</span>
          </div>
        </div>
      )}

      {progress.status === 'error' && (
        <div className="nlc-dl-error">
          <p>⚠ {progress.msg}</p>
          <div className="nlc-download-actions">
            <button className="nlc-btn nlc-btn-primary" onClick={onStart}>재시도</button>
            <button className="nlc-btn nlc-btn-ghost" onClick={onCancel}>모델 변경</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Suggestions screen ─────────────────────────────────────────────────────────

function SuggestionsScreen({ onSend, disabled }: { onSend: (s: string) => void; disabled: boolean }) {
  return (
    <div className="nlc-suggestions">
      <p className="nlc-suggestions-title">질문 예시를 클릭하거나 직접 입력하세요</p>
      {SUGGESTIONS.map(s => (
        <button
          key={s}
          className="nlc-suggestion-chip"
          onClick={() => onSend(s)}
          disabled={disabled}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function NLChat({ vessels, cpaAlerts, events }: NLChatProps) {
  const [open, setOpen]               = useState(false);
  const [selectedId, setSelectedId]   = useState<string>(MODELS[0].id);
  const [messages, setMessages]       = useState<ChatMessage[]>([]);
  const [input, setInput]             = useState('');
  const [loading, setLoading]         = useState(false);
  const [elapsed, setElapsed]         = useState(0);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [wllmProgress, setWllmProgress]  = useState<WebLLMProgress>({ status: 'idle', pct: 0, msg: '' });

  const messagesEndRef  = useRef<HTMLDivElement>(null);
  const inputRef        = useRef<HTMLInputElement>(null);
  const abortRef        = useRef<AbortController | null>(null);
  const elapsedTimerRef = useRef<number | null>(null);

  const model = MODELS.find(m => m.id === selectedId) ?? MODELS[0];

  // ── 모델 변경 처리 ────────────────────────────────────────────────────────
  const selectModel = (id: string) => {
    const newModel = MODELS.find(m => m.id === id) ?? MODELS[0];
    setSelectedId(id);
    setShowModelMenu(false);
    setMessages([]);

    if (newModel.kind === 'browser') {
      if (isBrowserModelLoaded(newModel)) {
        setWllmProgress({ status: 'ready', pct: 100, msg: '캐시에서 로드됨' });
      } else {
        setWllmProgress({ status: 'idle', pct: 0, msg: '' });
      }
    } else if (newModel.kind === 'local' && newModel.ollamaModel) {
      // Ollama: 설치 여부 비동기 확인
      setWllmProgress({ status: 'loading', pct: 0, msg: '모델 확인 중...' });
      checkOllamaModel(newModel.ollamaModel).then(installed => {
        if (installed) {
          setWllmProgress({ status: 'ready', pct: 100, msg: '설치됨' });
        } else {
          setWllmProgress({ status: 'idle', pct: 0, msg: '' });
        }
      });
    }
  };

  // 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 패널 열릴 때 input 포커스
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  // ── 다운로드 ───────────────────────────────────────────────────────────────
  const startDownload = async () => {
    setWllmProgress({ status: 'loading', pct: 0, msg: '초기화 중...' });
    try {
      if (model.provider === 'transformers') {
        await loadTransformers(model, setWllmProgress);
      } else if (model.provider === 'ollama' && model.ollamaModel) {
        await pullOllamaModel(model.ollamaModel, setWllmProgress);
      } else {
        await loadWebLLM(model, setWllmProgress);
      }
    } catch (e) {
      setWllmProgress({ status: 'error', pct: 0, msg: e instanceof Error ? e.message : '로드 실패' });
    }
  };

  const cancelDownload = () => {
    // Ollama 모델(첫 번째 local 모델)로 전환
    const fallback = MODELS.find(m => m.kind === 'local') ?? MODELS[0];
    selectModel(fallback.id);
  };

  // ── 경과 시간 타이머 ──────────────────────────────────────────────────────
  const stopLoading = () => {
    setLoading(false);
    setElapsed(0);
    if (elapsedTimerRef.current) { clearInterval(elapsedTimerRef.current); elapsedTimerRef.current = null; }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    stopLoading();
    setMessages(prev => [...prev, { id: `e-${Date.now()}`, role: 'error', text: '요청을 취소했습니다.' }]);
  };

  // ── 메시지 전송 ───────────────────────────────────────────────────────────
  const handleSend = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');

    // 브라우저 모델이 아직 로드 안됨 → 무시 (다운로드 화면에서 처리)
    if (model.kind === 'browser' && wllmProgress.status !== 'ready') return;

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', text: msg };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    setElapsed(0);

    const startMs = Date.now();
    elapsedTimerRef.current = window.setInterval(() => setElapsed(Math.floor((Date.now() - startMs) / 1000)), 500);

    const systemPrompt = buildSystemPrompt(vessels, cpaAlerts, events);
    const history = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-10)
      .map(m => ({ role: m.role as 'user' | 'assistant', content: m.text }));

    // ── 콘솔 로그: 실제 전달 프롬프트 ──────────────────────────────────────
    console.group(`%c[AI Prompt] ${model.label}`, 'color:#14c6e8;font-weight:bold');
    console.log('%cSystem Prompt:', 'color:#f59e0b;font-weight:bold', systemPrompt);
    if (history.length > 0) console.log('%cHistory:', 'color:#a78bfa', history);
    console.log('%cUser Message:', 'color:#10b981;font-weight:bold', msg);
    console.groupEnd();

    const abort = new AbortController();
    abortRef.current = abort;
    const timeoutId = window.setTimeout(() => abort.abort(), TIMEOUT_MS);

    const result = await runInference({ model, systemPrompt, history, message: msg, signal: abort.signal });

    clearTimeout(timeoutId);
    stopLoading();

    if (result.ok) {
      console.log(`%c[AI Response] ${model.label} — ${result.ms}ms`, 'color:#10b981', result.text);
      setMessages(prev => [...prev, { id: `a-${Date.now()}`, role: 'assistant', text: result.text, ms: result.ms, model: model.label }]);
    } else {
      const isTimeout = result.error.includes('aborted') || result.error.includes('abort');
      const errText = isTimeout ? `응답 시간 초과 (${TIMEOUT_MS / 1000}초). API 키를 확인하거나 다른 모델을 시도해보세요.` : result.error;
      console.error(`%c[AI Error] ${model.label}`, 'color:#ff5c5c', result.error);
      setMessages(prev => [...prev, { id: `e-${Date.now()}`, role: 'error', text: errText }]);
    }
  };

  // ── 화면 상태 계산 ─────────────────────────────────────────────────────────
  // browser: WebGPU 모델 다운로드 필요 / local: Ollama pull 필요
  const showDownloadScreen = wllmProgress.status !== 'ready';
  const showSuggestions = !showDownloadScreen && messages.length === 0 && !loading;
  const canSend = !loading && !showDownloadScreen;

  const browserModels = MODELS.filter(m => m.provider === 'transformers');
  const webllmModels  = MODELS.filter(m => m.provider === 'webllm');
  const ollamaModels  = MODELS.filter(m => m.provider === 'ollama');

  return (
    <>
      {/* FAB */}
      <button className={`nlc-fab${open ? ' nlc-fab--open' : ''}`} onClick={() => setOpen(v => !v)} title="AI 어시스턴트">
        {open ? '✕' : '💬'}
      </button>

      {open && (
        <div className="nlc-panel">

          {/* ── 헤더 ──────────────────────────────────────────────────── */}
          <div className="nlc-header">
            <span className="nlc-title">🤖 해양 AI 어시스턴트</span>
            <button className="nlc-close" onClick={() => setOpen(false)}>✕</button>
          </div>

          {/* ── 모델 선택 ──────────────────────────────────────────────── */}
          <div className="nlc-model-row">
            <div className="nlc-model-trigger-wrap">
              <button className="nlc-model-trigger" onClick={() => setShowModelMenu(v => !v)}>
                <ProviderBadge model={model} />
                <span className="nlc-model-name">{model.label}</span>
                <span className="nlc-model-desc">{model.description}</span>
                <span className="nlc-chevron">{showModelMenu ? '▲' : '▼'}</span>
              </button>

              {showModelMenu && (
                <div className="nlc-model-menu">
                  <div className="nlc-model-group-label">🖥 로컬 Ollama (FastAPI 프록시 · API 키 불필요)</div>
                  {ollamaModels.map(m => <ModelItem key={m.id} m={m} selected={selectedId} onSelect={selectModel} />)}
                  <div className="nlc-model-group-label">🌐 브라우저 · HuggingFace ONNX (API 키 불필요)</div>
                  {browserModels.map(m => <ModelItem key={m.id} m={m} selected={selectedId} onSelect={selectModel} />)}
                  <div className="nlc-model-group-label">🌐 브라우저 · WebLLM MLC (API 키 불필요)</div>
                  {webllmModels.map(m => <ModelItem key={m.id} m={m} selected={selectedId} onSelect={selectModel} />)}
                </div>
              )}
            </div>

            {/* Ollama 모델 안내 */}
            {model.kind === 'local' && (
              <div className="nlc-key-hint" style={{ padding: '6px 0 2px' }}>
                FastAPI: localhost:8000 · Ollama: localhost:11434
              </div>
            )}

            {/* 브라우저 모델 로드 완료 표시 */}
            {model.kind === 'browser' && wllmProgress.status === 'ready' && (
              <div className="nlc-ready-badge">✓ {wllmProgress.msg}</div>
            )}
          </div>

          {/* ── 메인 콘텐츠 영역 ─────────────────────────────────────────
               3가지 상태 중 하나만 표시:
               1. 다운로드 화면  (browser 모델 + not ready)
               2. 제안 화면      (메시지 없음 + ready/api)
               3. 대화 화면      (메시지 있음)
          ─────────────────────────────────────────────────────────────── */}
          <div className="nlc-messages">

            {showDownloadScreen && (
              <DownloadScreen
                model={model}
                progress={wllmProgress}
                onStart={startDownload}
                onCancel={cancelDownload}
              />
            )}

            {showSuggestions && (
              <SuggestionsScreen onSend={handleSend} disabled={false} />
            )}

            {!showDownloadScreen && messages.map(msg => (
              <div key={msg.id} className={`nlc-msg nlc-msg--${msg.role}`}>
                {msg.role === 'user' && (
                  <div className="nlc-msg-bubble nlc-msg-bubble--user">{msg.text}</div>
                )}
                {msg.role === 'assistant' && (
                  <>
                    <div className="nlc-msg-bubble nlc-msg-bubble--assistant">{msg.text}</div>
                    <div className="nlc-msg-meta">{msg.model} · {msg.ms != null ? `${(msg.ms / 1000).toFixed(1)}s` : ''}</div>
                  </>
                )}
                {msg.role === 'error' && (
                  <div className="nlc-msg-bubble nlc-msg-bubble--error">⚠ {msg.text}</div>
                )}
              </div>
            ))}

            {loading && !showDownloadScreen && (
              <div className="nlc-msg nlc-msg--assistant">
                <div className="nlc-msg-bubble nlc-msg-bubble--assistant nlc-thinking">
                  <span className="nlc-dot" /><span className="nlc-dot" /><span className="nlc-dot" />
                  <em className="nlc-thinking-time">{elapsed}s</em>
                  <button className="nlc-cancel-inline" onClick={handleCancel} title="취소">✕</button>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ── 입력 바 ───────────────────────────────────────────────── */}
          <div className="nlc-input-row">
            {showDownloadScreen ? (
              <div className="nlc-need-key">모델을 먼저 다운로드해주세요</div>
            ) : (
              <>
                <input
                  ref={inputRef}
                  className="nlc-input"
                  placeholder={loading ? '답변 생성 중...' : '해역 현황에 대해 질문하세요'}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  disabled={!canSend}
                />
                <button className="nlc-send" onClick={() => handleSend()} disabled={!canSend || !input.trim()}>↑</button>
              </>
            )}
          </div>

        </div>
      )}
    </>
  );
}
