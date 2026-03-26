// LLM abstraction layer — supports browser (WebGPU/WebLLM) and API providers

export type ProviderType = 'webllm' | 'anthropic' | 'gemini' | 'groq';
export type ModelKind = 'browser' | 'api';

export interface ModelConfig {
  id: string;
  label: string;
  provider: ProviderType;
  kind: ModelKind;
  isFree: boolean;
  description: string;
  webllmId?: string;
  apiModel?: string;
  keyLabel?: string;
  keyPlaceholder?: string;
  keyHint?: string;
}

export const MODELS: ModelConfig[] = [
  // ── 브라우저 (무료, 프라이버시 보호) ─────────────────────────────
  {
    id: 'phi-3.5-mini',
    label: 'Phi-3.5 Mini',
    provider: 'webllm',
    kind: 'browser',
    isFree: true,
    description: '2.2 GB · WebGPU · 빠름',
    webllmId: 'Phi-3.5-mini-instruct-q4f16_1-MLC',
  },
  {
    id: 'llama-3.2-3b',
    label: 'Llama 3.2 3B',
    provider: 'webllm',
    kind: 'browser',
    isFree: true,
    description: '2.0 GB · WebGPU · 균형',
    webllmId: 'Llama-3.2-3B-Instruct-q4f16_1-MLC',
  },
  // ── 서버 API (무료 티어 포함) ─────────────────────────────────────
  {
    id: 'groq-llama',
    label: 'Llama 3.1 8B',
    provider: 'groq',
    kind: 'api',
    isFree: true,
    description: 'Groq · 무료 티어 · 초고속',
    apiModel: 'llama-3.1-8b-instant',
    keyLabel: 'Groq API Key',
    keyPlaceholder: 'gsk_...',
    keyHint: 'console.groq.com',
  },
  {
    id: 'gemini-flash',
    label: 'Gemini 1.5 Flash',
    provider: 'gemini',
    kind: 'api',
    isFree: true,
    description: 'Google · 무료 할당량 포함',
    apiModel: 'gemini-1.5-flash',
    keyLabel: 'Google AI API Key',
    keyPlaceholder: 'AIza...',
    keyHint: 'aistudio.google.com',
  },
  // ── 서버 API (유료) ───────────────────────────────────────────────
  {
    id: 'claude-haiku',
    label: 'Claude Haiku 4.5',
    provider: 'anthropic',
    kind: 'api',
    isFree: false,
    description: 'Anthropic · 유료 · 빠름',
    apiModel: 'claude-haiku-4-5-20251001',
    keyLabel: 'Anthropic API Key',
    keyPlaceholder: 'sk-ant-...',
    keyHint: 'console.anthropic.com',
  },
  {
    id: 'claude-sonnet',
    label: 'Claude Sonnet 4.6',
    provider: 'anthropic',
    kind: 'api',
    isFree: false,
    description: 'Anthropic · 유료 · 최고 품질',
    apiModel: 'claude-sonnet-4-6',
    keyLabel: 'Anthropic API Key',
    keyPlaceholder: 'sk-ant-...',
    keyHint: 'console.anthropic.com',
  },
];

// ── WebLLM singleton ─────────────────────────────────────────────────────────

export type WebLLMStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface WebLLMProgress {
  status: WebLLMStatus;
  pct: number;
  msg: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _engine: any = null;
let _loadedId: string | null = null;

export async function loadWebLLM(
  model: ModelConfig,
  onProgress: (p: WebLLMProgress) => void
): Promise<void> {
  if (!model.webllmId) throw new Error('Not a WebLLM model');
  if (_engine && _loadedId === model.webllmId) {
    onProgress({ status: 'ready', pct: 100, msg: '준비됨' });
    return;
  }

  // Unload previous model
  if (_engine) {
    try { await _engine.unload(); } catch { /* ignore */ }
    _engine = null;
    _loadedId = null;
  }

  onProgress({ status: 'loading', pct: 0, msg: '모델 로딩 중...' });

  const { CreateMLCEngine } = await import('@mlc-ai/web-llm');
  _engine = await CreateMLCEngine(model.webllmId, {
    initProgressCallback: (info: { progress: number; text: string }) => {
      const pct = Math.round((info.progress ?? 0) * 100);
      onProgress({ status: 'loading', pct, msg: info.text ?? `${pct}%` });
    },
  });
  _loadedId = model.webllmId;
  onProgress({ status: 'ready', pct: 100, msg: '준비됨' });
}

// ── Inference ────────────────────────────────────────────────────────────────

export interface InferenceRequest {
  model: ModelConfig;
  systemPrompt: string;
  history: { role: 'user' | 'assistant'; content: string }[];
  message: string;
  apiKey?: string;
}

export type InferenceResult =
  | { ok: true; text: string; ms: number }
  | { ok: false; error: string };

export async function runInference(req: InferenceRequest): Promise<InferenceResult> {
  const t0 = Date.now();
  try {
    const messages = [
      ...req.history,
      { role: 'user' as const, content: req.message },
    ];

    // ── Browser (WebLLM) ────────────────────────────────────────────
    if (req.model.kind === 'browser') {
      if (!_engine) throw new Error('모델이 아직 로드되지 않았습니다');
      const resp = await _engine.chat.completions.create({
        messages: [{ role: 'system', content: req.systemPrompt }, ...messages],
        temperature: 0.3,
        max_tokens: 768,
      });
      return { ok: true, text: resp.choices[0].message.content ?? '', ms: Date.now() - t0 };
    }

    // ── Anthropic ───────────────────────────────────────────────────
    if (req.model.provider === 'anthropic') {
      if (!req.apiKey) throw new Error('API 키를 입력해주세요');
      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'x-api-key': req.apiKey,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-allow-browser': 'true',
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model: req.model.apiModel,
          max_tokens: 1024,
          system: req.systemPrompt,
          messages,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { content: { text: string }[] };
      return { ok: true, text: data.content[0].text, ms: Date.now() - t0 };
    }

    // ── Google Gemini ───────────────────────────────────────────────
    if (req.model.provider === 'gemini') {
      if (!req.apiKey) throw new Error('API 키를 입력해주세요');
      const contents = messages.map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }],
      }));
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${req.model.apiModel}:generateContent?key=${req.apiKey}`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            systemInstruction: { parts: [{ text: req.systemPrompt }] },
            contents,
            generationConfig: { maxOutputTokens: 1024, temperature: 0.3 },
          }),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { candidates: { content: { parts: { text: string }[] } }[] };
      return { ok: true, text: data.candidates[0].content.parts[0].text, ms: Date.now() - t0 };
    }

    // ── Groq (OpenAI-compatible) ────────────────────────────────────
    if (req.model.provider === 'groq') {
      if (!req.apiKey) throw new Error('API 키를 입력해주세요');
      const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${req.apiKey}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model: req.model.apiModel,
          messages: [{ role: 'system', content: req.systemPrompt }, ...messages],
          max_tokens: 1024,
          temperature: 0.3,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { choices: { message: { content: string } }[] };
      return { ok: true, text: data.choices[0].message.content, ms: Date.now() - t0 };
    }

    throw new Error('지원하지 않는 프로바이더');
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : '알 수 없는 오류' };
  }
}
