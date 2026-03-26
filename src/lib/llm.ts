// LLM abstraction layer
// 브라우저: WebLLM (MLC), Transformers.js (HuggingFace ONNX)
// 로컬 서버: Ollama (FastAPI 프록시)

export type ProviderType = 'webllm' | 'transformers' | 'ollama';
export type ModelKind = 'browser' | 'local';

export interface ModelConfig {
  id: string;
  label: string;
  provider: ProviderType;
  kind: ModelKind;
  isFree: boolean;
  license: string;
  description: string;
  webllmId?: string;     // WebLLM 전용
  hfModelId?: string;    // Transformers.js 전용
  ollamaModel?: string;  // Ollama 전용 (e.g. "qwen:4b")
}

export const MODELS: ModelConfig[] = [
  // ── 브라우저 · Transformers.js (HuggingFace ONNX) ─────────────────────────
  // API 키 불필요, 첫 실행 시 브라우저에 다운로드 → IndexedDB 캐시
  {
    id: 'qwen2.5-0.5b',
    label: 'Qwen2.5 0.5B',
    provider: 'transformers',
    kind: 'browser',
    isFree: true,
    license: 'Apache 2.0',
    description: '~390 MB · WebGPU · 초경량',
    hfModelId: 'onnx-community/Qwen2.5-0.5B-Instruct',
  },
  {
    id: 'qwen2.5-1.5b',
    label: 'Qwen2.5 1.5B',
    provider: 'transformers',
    kind: 'browser',
    isFree: true,
    license: 'Apache 2.0',
    description: '~900 MB · WebGPU · 균형',
    hfModelId: 'onnx-community/Qwen2.5-1.5B-Instruct',
  },
  // ── 브라우저 · WebLLM (MLC 양자화) ───────────────────────────────────────
  {
    id: 'qwen2.5-3b-mlc',
    label: 'Qwen2.5 3B',
    provider: 'webllm',
    kind: 'browser',
    isFree: true,
    license: 'Apache 2.0',
    description: '~2 GB · WebGPU · 고품질',
    webllmId: 'Qwen2.5-3B-Instruct-q4f16_1-MLC',
  },
  {
    id: 'qwen2.5-7b-mlc',
    label: 'Qwen2.5 7B',
    provider: 'webllm',
    kind: 'browser',
    isFree: true,
    license: 'Apache 2.0',
    description: '~4 GB · WebGPU · 온디바이스 최강',
    webllmId: 'Qwen2.5-7B-Instruct-q4f16_1-MLC',
  },
  {
    id: 'mistral-7b-mlc',
    label: 'Mistral 7B v0.3',
    provider: 'webllm',
    kind: 'browser',
    isFree: true,
    license: 'Apache 2.0',
    description: '~4 GB · WebGPU · Mistral 온디바이스',
    webllmId: 'Mistral-7B-Instruct-v0.3-q4f16_1-MLC',
  },
  // ── 로컬 Ollama ────────────────────────────────────────────────────────────
  // FastAPI 프록시 (localhost:8000) → Ollama (localhost:11434)
  // `ollama run <model>` 으로 사전 다운로드 필요
  {
    id: 'ollama-qwen-4b',
    label: 'Qwen 4B',
    provider: 'ollama',
    kind: 'local',
    isFree: true,
    license: 'Apache 2.0',
    description: 'Ollama · qwen:4b · ~2.3 GB',
    ollamaModel: 'qwen:4b',
  },
  {
    id: 'ollama-qwen2.5-7b',
    label: 'Qwen2.5 7B',
    provider: 'ollama',
    kind: 'local',
    isFree: true,
    license: 'Apache 2.0',
    description: 'Ollama · qwen2.5:7b · ~4.7 GB',
    ollamaModel: 'qwen2.5:7b',
  },
  {
    id: 'ollama-qwen2.5-14b',
    label: 'Qwen2.5 14B',
    provider: 'ollama',
    kind: 'local',
    isFree: true,
    license: 'Apache 2.0',
    description: 'Ollama · qwen2.5:14b · ~9 GB',
    ollamaModel: 'qwen2.5:14b',
  },
  {
    id: 'ollama-mistral-7b',
    label: 'Mistral 7B',
    provider: 'ollama',
    kind: 'local',
    isFree: true,
    license: 'Apache 2.0',
    description: 'Ollama · mistral:7b · ~4.1 GB',
    ollamaModel: 'mistral:7b',
  },
  {
    id: 'ollama-mistral-nemo',
    label: 'Mistral Nemo 12B',
    provider: 'ollama',
    kind: 'local',
    isFree: true,
    license: 'Apache 2.0',
    description: 'Ollama · mistral-nemo · ~7.1 GB',
    ollamaModel: 'mistral-nemo',
  },
];

// ── WebLLM singleton ──────────────────────────────────────────────────────────

export type WebLLMStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface WebLLMProgress {
  status: WebLLMStatus;
  pct: number;
  msg: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _webllmEngine: any = null;
let _webllmLoadedId: string | null = null;

export async function loadWebLLM(
  model: ModelConfig,
  onProgress: (p: WebLLMProgress) => void
): Promise<void> {
  if (!model.webllmId) throw new Error('Not a WebLLM model');
  if (_webllmEngine && _webllmLoadedId === model.webllmId) {
    onProgress({ status: 'ready', pct: 100, msg: '준비됨' });
    return;
  }
  if (_webllmEngine) {
    try { await _webllmEngine.unload(); } catch { /* ignore */ }
    _webllmEngine = null;
    _webllmLoadedId = null;
  }
  onProgress({ status: 'loading', pct: 0, msg: '모델 로딩 중...' });
  const { CreateMLCEngine } = await import('@mlc-ai/web-llm');
  _webllmEngine = await CreateMLCEngine(model.webllmId, {
    initProgressCallback: (info: { progress: number; text: string }) => {
      const pct = Math.round((info.progress ?? 0) * 100);
      onProgress({ status: 'loading', pct, msg: info.text ?? `${pct}%` });
    },
  });
  _webllmLoadedId = model.webllmId;
  onProgress({ status: 'ready', pct: 100, msg: '준비됨' });
}

// ── Transformers.js singleton ─────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _tfPipeline: any = null;
let _tfLoadedId: string | null = null;

export async function loadTransformers(
  model: ModelConfig,
  onProgress: (p: WebLLMProgress) => void
): Promise<void> {
  if (!model.hfModelId) throw new Error('Not a Transformers.js model');
  if (_tfPipeline && _tfLoadedId === model.hfModelId) {
    onProgress({ status: 'ready', pct: 100, msg: '준비됨' });
    return;
  }
  _tfPipeline = null;
  _tfLoadedId = null;
  onProgress({ status: 'loading', pct: 0, msg: '모델 초기화 중...' });

  const { pipeline, env } = await import('@huggingface/transformers');
  env.useBrowserCache = true;
  env.allowLocalModels = false;

  const hasWebGPU = typeof navigator !== 'undefined' && 'gpu' in navigator;
  const device = hasWebGPU ? 'webgpu' : 'wasm';
  const dtype = hasWebGPU ? 'q4f16' : 'fp32';

  onProgress({ status: 'loading', pct: 0, msg: `${device.toUpperCase()} 모드로 로드 중...` });

  _tfPipeline = await pipeline('text-generation', model.hfModelId, {
    device: device as never,
    dtype: dtype as never,
    progress_callback: (info: { status: string; progress?: number; loaded?: number; total?: number; file?: string }) => {
      const shortFile = (info.file ?? '').split('/').pop() ?? '';
      if (info.status === 'progress') {
        const pct = Math.round(info.progress ?? 0);
        const loaded = info.loaded != null ? (info.loaded / 1024 / 1024).toFixed(1) : null;
        const total  = info.total  != null ? (info.total  / 1024 / 1024).toFixed(1) : null;
        const sizeStr = loaded && total ? ` (${loaded}/${total} MB)` : '';
        onProgress({ status: 'loading', pct, msg: `${shortFile}${sizeStr} — ${pct}%` });
      } else if (info.status === 'initiate') {
        onProgress({ status: 'loading', pct: 0, msg: `${shortFile} 다운로드 준비 중...` });
      } else if (info.status === 'download') {
        onProgress({ status: 'loading', pct: 0, msg: `${shortFile} 다운로드 중...` });
      } else if (info.status === 'done') {
        onProgress({ status: 'loading', pct: 100, msg: `${shortFile} 완료` });
      }
    },
  });
  _tfLoadedId = model.hfModelId;
  onProgress({ status: 'ready', pct: 100, msg: `${device.toUpperCase()} 준비 완료` });
}

export function isBrowserModelLoaded(model: ModelConfig): boolean {
  if (model.provider === 'webllm') return _webllmLoadedId === model.webllmId;
  if (model.provider === 'transformers') return _tfLoadedId === model.hfModelId;
  return false;
}

// ── Ollama 모델 설치 확인 + 다운로드 ─────────────────────────────────────────

export async function checkOllamaModel(ollamaModel: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/models`);
    if (!res.ok) return false;
    const data = await res.json() as { models: string[] };
    return data.models.includes(ollamaModel);
  } catch {
    return false;
  }
}

export async function pullOllamaModel(
  ollamaModel: string,
  onProgress: (p: WebLLMProgress) => void,
  signal?: AbortSignal
): Promise<void> {
  onProgress({ status: 'loading', pct: 0, msg: '다운로드 시작...' });

  // 1. 백그라운드 태스크 시작 (브라우저 연결과 독립적으로 진행)
  const startRes = await fetch(`${API_BASE}/api/pull/${encodeURIComponent(ollamaModel)}`, {
    method: 'POST',
    signal,
  });
  if (!startRes.ok) throw new Error(`Pull 시작 실패: HTTP ${startRes.status}`);

  // 2. 진행률 폴링 (500ms마다)
  while (true) {
    if (signal?.aborted) throw new Error('취소됨');
    await new Promise(r => setTimeout(r, 500));

    const res = await fetch(
      `${API_BASE}/api/pull/progress/${encodeURIComponent(ollamaModel)}`,
      { signal }
    );
    if (!res.ok) continue;

    const data = await res.json() as {
      status: string; pct: number; msg: string; done: boolean; error: string;
    };

    if (data.status === 'error') throw new Error(data.error || '다운로드 오류');

    const label =
      data.status === 'pulling'    ? `다운로드 중 — ${data.msg}` :
      data.status === 'verifying'  ? `검증 중...` :
      data.status === 'success'    ? '완료' :
      data.msg || data.status;

    onProgress({ status: 'loading', pct: data.pct, msg: label });

    if (data.done) {
      onProgress({ status: 'ready', pct: 100, msg: '다운로드 완료' });
      return;
    }
  }
}

// ── Inference ─────────────────────────────────────────────────────────────────

export interface InferenceRequest {
  model: ModelConfig;
  systemPrompt: string;
  history: { role: 'user' | 'assistant'; content: string }[];
  message: string;
  signal?: AbortSignal;
}

export type InferenceResult =
  | { ok: true; text: string; ms: number }
  | { ok: false; error: string };

// Vite dev: /api → localhost:8000 (프록시)
// Production: 동일 오리진의 /api
const API_BASE = '';

export async function runInference(req: InferenceRequest): Promise<InferenceResult> {
  const t0 = Date.now();
  try {
    const messages = [
      ...req.history,
      { role: 'user' as const, content: req.message },
    ];

    // ── Transformers.js (HuggingFace ONNX, 브라우저) ─────────────────
    if (req.model.provider === 'transformers') {
      if (!_tfPipeline) throw new Error('모델이 아직 로드되지 않았습니다');
      const sysPrompt = req.systemPrompt.length > 800
        ? req.systemPrompt.slice(0, 800) + '\n...(생략)'
        : req.systemPrompt;
      const input = [
        { role: 'system', content: sysPrompt },
        ...messages.slice(-3),
      ];
      let tokenCount = 0;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const out: any = await _tfPipeline(input, {
        max_new_tokens: 256,
        do_sample: true,
        temperature: 0.3,
        repetition_penalty: 1.1,
        callback_function: (_beams: unknown[]) => {
          tokenCount++;
          if (tokenCount % 5 === 0) {
            console.log(`%c[AI Gen] ${tokenCount} tokens...`, 'color:#a78bfa');
          }
        },
      });
      console.log(`%c[AI Gen] done — ${tokenCount} tokens total`, 'color:#10b981');
      const generated = Array.isArray(out) ? out[0]?.generated_text : out?.generated_text;
      const text = Array.isArray(generated)
        ? (generated.at(-1)?.content ?? '')
        : String(generated ?? '');
      return { ok: true, text, ms: Date.now() - t0 };
    }

    // ── WebLLM (브라우저) ─────────────────────────────────────────────
    if (req.model.provider === 'webllm') {
      if (!_webllmEngine) throw new Error('모델이 아직 로드되지 않았습니다');
      const resp = await _webllmEngine.chat.completions.create({
        messages: [{ role: 'system', content: req.systemPrompt }, ...messages],
        temperature: 0.3,
        max_tokens: 768,
      });
      return { ok: true, text: resp.choices[0].message.content ?? '', ms: Date.now() - t0 };
    }

    // ── Ollama (로컬 FastAPI 프록시) ──────────────────────────────────
    if (req.model.provider === 'ollama') {
      if (!req.model.ollamaModel) throw new Error('ollamaModel이 설정되지 않았습니다');
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        signal: req.signal,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: req.model.ollamaModel,
          messages: [
            { role: 'system', content: req.systemPrompt },
            ...messages,
          ],
          temperature: 0.3,
          max_tokens: 1024,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { text: string };
      return { ok: true, text: data.text, ms: Date.now() - t0 };
    }

    throw new Error('지원하지 않는 provider입니다');
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}
