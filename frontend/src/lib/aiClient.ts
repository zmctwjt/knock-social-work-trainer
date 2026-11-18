/**
 * 叩门 · AI 客户端
 *
 * 浏览器不直连大模型：智谱开放平台不返回 CORS 头，密钥也不能进前端产物。
 * 所有请求都发往本项目自带的 Node 服务（server/）的 /api/ai/*，
 * 由它同源转发给 GLM-4.7-Flash。解压后跑一条命令就能用上 AI。
 *
 * 三条纪律：
 *   1. 任何链路失败都返回 null / 原样兜底，绝不抛给页面
 *   2. 每条链路都记录 failReason，设置页能如实显示"为什么没走通"
 *   3. 危机内容不进入本层（由 useSession 在调用前拦截）
 */
import type { AIResult, Intent, DimensionKey, StageKey, DebriefReport } from '../types.ts';

/* ══════════ 配置与状态 ══════════ */

/** 留空 = 同源 /api（推荐）。跨机部署时可在设置页改。 */
let AI_BASE = (import.meta.env?.VITE_AI_BASE as string | undefined) || '';
let enabled = true;
/** 默认预算略大于服务端的 45s —— 让服务端先降级，而不是客户端先掐断 */
let timeoutMs = 60_000;
/** 意图补判只是锦上添花：规则层已经给出初判，不值得让整轮对话等 45 秒 */
const INTENT_BUDGET_MS = 15_000;

export type AiMode = 'rule' | 'hybrid' | 'ai';

export interface AiStatus {
  /** 服务可达 且 密钥已配置 */
  ready: boolean;
  /** 顶栏徽标文字 */
  label: string;
  /** 一句话说明 */
  detail: string;
  /** 实际生效的模型名 */
  model: string;
  /** 本次探测耗时 */
  latencyMs: number;
  /** 最近一次失败原因，空串表示无 */
  lastError: string;
  checkedAt: number;
}

let status: AiStatus = {
  ready: false,
  label: '规则模式',
  detail: '尚未检测 AI 服务',
  model: '',
  latencyMs: 0,
  lastError: '',
  checkedAt: 0,
};

const listeners = new Set<(s: AiStatus) => void>();

export function onAiStatus(fn: (s: AiStatus) => void): () => void {
  listeners.add(fn);
  fn(status);
  return () => listeners.delete(fn);
}

function emit(next: Partial<AiStatus>) {
  status = { ...status, ...next, checkedAt: Date.now() };
  for (const fn of listeners) fn(status);
}

export function aiStatus(): AiStatus {
  return status;
}

export function setAiBase(url: string): void {
  AI_BASE = url.trim().replace(/\/+$/, '');
}

export function getAiBase(): string {
  return AI_BASE;
}

export function setAiEnabled(v: boolean): void {
  enabled = v;
  if (!v) emit({ ready: false, label: '规则模式', detail: 'AI 已手动关闭' });
}

export function isAiEnabled(): boolean {
  return enabled;
}

export function setAiTimeout(ms: number): void {
  timeoutMs = Math.max(5_000, Math.min(120_000, ms));
}

/* ══════════ 底层请求 ══════════ */

function url(path: string): string {
  const base = AI_BASE || '';
  return `${base}/api${path}`;
}

interface ApiError { code?: string; message?: string }

/**
 * 单次调用失败**不能**把全局状态打成「规则模式」。
 *
 * ready 只代表「health 探针是否连得上」，是连通性；
 * 一次超时/解析失败只说明这一轮模型不给力，下一轮仍然值得试。
 * 早期版本在失败时直接 emit({ready:false})，结果是一次 45s 超时之后
 * 整场训练（含阶段评分与复盘）全部降级 —— 这正是"AI 已接入"名不副实的原因。
 */
function noteFailure(reason: string): void {
  emit({ lastError: reason });
  scheduleReprobe();
}

let reprobeTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleReprobe(): void {
  if (reprobeTimer) return;
  reprobeTimer = setTimeout(() => {
    reprobeTimer = null;
    void probeAi();
  }, 5000);
}

async function post<T>(
  path: string,
  body: unknown,
  opts: { timeoutMs?: number } = {},
): Promise<AIResult<T>> {
  if (!enabled) {
    return { ok: false, data: null, failReason: 'AI 已关闭（设置页）' };
  }

  const budget = opts.timeoutMs ?? timeoutMs;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), budget);
  try {
    const res = await fetch(url(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });

    let payload: unknown = null;
    try { payload = await res.json(); } catch { /* 非 JSON 响应 */ }

    const obj = (payload || {}) as Record<string, unknown>;

    if (!res.ok) {
      const err = (obj.error || {}) as ApiError;
      const reason = err.message || `HTTP ${res.status}`;
      noteFailure(reason);
      return { ok: false, data: null, failReason: reason };
    }

    if (obj.ok === false) {
      const err = (obj.error || {}) as ApiError;
      const reason = err.message || '服务端拒绝了本次请求';
      noteFailure(reason);
      return { ok: false, data: null, failReason: reason };
    }

    // 成功即恢复
    if (status.lastError) emit({ lastError: '' });
    return { ok: true, data: payload as T };
  } catch (e) {
    const reason = e instanceof Error
      ? (e.name === 'AbortError' ? `本轮模型超时（${Math.round(budget / 1000)}s），已用规则结果` : e.message)
      : String(e);
    noteFailure(reason);
    return { ok: false, data: null, failReason: reason };
  } finally {
    clearTimeout(timer);
  }
}

/* ══════════ 健康检查 ══════════ */

export interface AiHealth {
  ok: boolean;
  ai: {
    configured: boolean;
    model: string;
    fallback: string[];
    thinking: string;
    timeoutMs: number;
  };
  usage?: {
    calls: number; ok: number; failed: number;
    tokensIn: number; tokensOut: number;
    byFn: Record<string, number>;
    remainingToday: number; dailyCap: number;
    lastModel: string; lastError: string;
  };
}

export async function probeAi(): Promise<AiStatus> {
  const t0 = Date.now();
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12_000);
    let res: Response;
    try {
      res = await fetch(url('/health'), { signal: ctrl.signal });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) throw new Error(`健康检查返回 HTTP ${res.status}`);
    const data = (await res.json()) as AiHealth;
    const ms = Date.now() - t0;

    if (!data.ai?.configured) {
      emit({
        ready: false, label: '规则模式', model: data.ai?.model || '',
        latencyMs: ms, lastError: '服务端未配置 GLM_API_KEY',
        detail: '服务已启动但缺少密钥 —— 前往 server/.env 填入',
      });
      return status;
    }
    emit({
      ready: true,
      label: 'AI 已接入',
      detail: `${data.ai.model} · 服务端代理 · ${ms}ms`,
      model: data.ai.model,
      latencyMs: ms,
      lastError: '',
    });
    return status;
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    emit({
      ready: false, label: '规则模式', latencyMs: Date.now() - t0,
      lastError: reason,
      detail: '未检测到 AI 服务 —— 执行 npm run serve 启动，或继续用规则模式',
    });
    return status;
  }
}

/* ══════════ 链路 A · 意图分类 ══════════ */

const INTENT_ENUM: Intent[] = [
  '共情', '开放提问', '封闭提问', '评判',
  '建议过早', '沉默陪伴', '离题', '危机',
];

export interface IntentInput {
  input: string;
  stage: StageKey;
  name: string;
  age: number;
  identity: string;
  brief: string;
  /** 规则层的初判，给模型做参考 */
  ruleHint?: Intent;
}

export async function classifyIntent(
  args: IntentInput,
  fallback: Intent,
): Promise<{ intent: Intent; usedAI: boolean; model?: string; failReason?: string }> {
  if (!status.ready) return { intent: fallback, usedAI: false };

  const r = await post<{ intent: string | null; model: string }>('/ai/intent', {
    input: args.input,
    stage: args.stage,
    name: args.name,
    age: args.age,
    identity: args.identity,
    brief: args.brief,
    ruleHint: args.ruleHint || fallback,
  }, { timeoutMs: INTENT_BUDGET_MS });

  if (!r.ok || !r.data) {
    return { intent: fallback, usedAI: false, failReason: r.failReason };
  }

  const raw = r.data.intent;
  if (typeof raw !== 'string') {
    return { intent: fallback, usedAI: false, failReason: '模型未给出合法意图' };
  }
  const k = INTENT_ENUM.find((i) => i === raw);
  if (!k) return { intent: fallback, usedAI: false, failReason: `未知意图「${raw}」` };
  return { intent: k, usedAI: true, model: r.data.model };
}

/* ══════════ 链路 B · AI 实时扮演 ══════════ */

export interface PersonaArgs {
  systemPrompt: string;
  forbidden: string[];
  difficultyLabel: string;
  difficultyRule: string;
  emotion: number;
  voiceByEmotion: string;
  history: { role: 'worker' | 'client'; text: string }[];
  /** 角色自己最近说过的台词，提示模型不要重复 */
  saidLines?: string[];
  /** 当前阶段 1/2/3 */
  phase?: number;
}

/** 返回 null = 不可用，调用方保留预置台词 */
export async function aiActAsPersona(args: PersonaArgs): Promise<{
  text: string | null; model?: string; ms?: number; failReason?: string;
}> {
  if (!status.ready) return { text: null, failReason: '未接入 AI' };
  const r = await post<{ text: string | null; model: string; ms: number }>('/ai/persona', args);
  if (!r.ok || !r.data) return { text: null, failReason: r.failReason };
  if (!r.data.text) return { text: null, model: r.data.model, failReason: '今日额度或解析失败' };
  return { text: r.data.text, model: r.data.model, ms: r.data.ms };
}

/* ══════════ 链路 C · 六维评分 ══════════ */

export interface GradeArgs {
  dialogue: string;
  crisisSeen: boolean;
  stats: {
    workerTurns: number;
    judgeCount: number;
    hopelessSeen: boolean;
    hopelessRecognized: boolean;
    crisisSeen: boolean;
  };
}

export async function gradeStage(args: GradeArgs): Promise<{
  scores: Record<DimensionKey, number> | null;
  reasons: Partial<Record<DimensionKey, string>>;
  usedAI: boolean;
  model?: string;
  ms?: number;
  failReason?: string;
}> {
  // 危机内容永不进入模型（安全边界）
  if (args.crisisSeen) {
    return { scores: null, reasons: {}, usedAI: false, failReason: '本阶段出现危机内容，按规则跳过模型' };
  }
  if (!status.ready) {
    return { scores: null, reasons: {}, usedAI: false, failReason: '未接入 AI，使用规则底分' };
  }

  const r = await post<{
    scores: Record<string, { score: number; reason: string }> | null;
    model: string; ms: number;
  }>('/ai/score', {
    dialogue: args.dialogue,
    stats: args.stats,
  });

  if (!r.ok || !r.data || !r.data.scores) {
    return { scores: null, reasons: {}, usedAI: false, failReason: r.failReason || '模型未给出完整六维' };
  }

  const scores = {} as Record<DimensionKey, number>;
  const reasons: Partial<Record<DimensionKey, string>> = {};
  const keys: DimensionKey[] = ['empathy', 'question', 'advice', 'ethics', 'process', 'risk'];
  for (const k of keys) {
    const item = r.data.scores[k];
    if (!item || typeof item.score !== 'number') {
      return { scores: null, reasons: {}, usedAI: false, failReason: `缺少维度 ${k}` };
    }
    // 模型偶尔会给 0 / 100 这类极端值，与"基线 60 上下浮动"的口径不符。
    // 这里做一次柔性收敛：把 0–100 压到 35–95，再由 mergeScores 与规则底分融合。
    scores[k] = Math.max(35, Math.min(95, Math.round(item.score)));
    reasons[k] = item.reason;
  }
  return { scores, reasons, usedAI: true, model: r.data.model, ms: r.data.ms };
}

/* ══════════ 链路 D · 复盘报告 ══════════ */

export async function generateDebrief(args: {
  nickname: string;
  name: string;
  age: number;
  identity: string;
  scores: Record<DimensionKey, number>;
  hitRules: string[];
  template: DebriefReport;
}): Promise<DebriefReport> {
  if (!status.ready) return args.template;

  const r = await post<{
    report: { strength: string; improvement: string; nextStep: string } | null;
    model: string;
  }>('/ai/debrief', {
    nickname: args.nickname,
    name: args.name,
    age: args.age,
    identity: args.identity,
    scores: args.scores,
    hitRules: args.hitRules,
  });

  if (!r.ok || !r.data || !r.data.report) return args.template;

  const p = r.data.report;
  if (!p.strength || !p.improvement || !p.nextStep) return args.template;

  return {
    strength: p.strength,
    improvement: p.improvement,
    nextStep: p.nextStep,
    source: 'ai',
  };
}

/* ══════════ 用量与自检（设置页用） ══════════ */

export async function fetchUsage(): Promise<AiHealth | null> {
  try {
    const res = await fetch(url('/health'), { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as AiHealth;
  } catch {
    return null;
  }
}

export async function selftest(): Promise<{ ok: boolean; model?: string; sample?: string; ms?: number; detail?: string }> {
  try {
    const res = await fetch(url('/selftest'), { method: 'POST' });
    return await res.json();
  } catch (e) {
    return { ok: false, detail: e instanceof Error ? e.message : String(e) };
  }
}

/* ══════════ 启动引导 ══════════ */
/** main.tsx 在渲染前调用一次；失败不影响应用启动 */
export function bootstrapAi(): void {
  void probeAi();
}
