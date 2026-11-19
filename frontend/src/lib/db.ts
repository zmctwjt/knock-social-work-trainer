/**
 * 数据访问层
 * 所有写库都在这里，页面不直接碰 supabase client
 *
 * 说明：AI 调用不再从这里注入。
 * 浏览器统一请求本项目自带的 Node 服务（server/）的 /api/ai/*，
 * 由它持有密钥并转发给 GLM-4.7-Flash —— 见 src/lib/aiClient.ts。
 * 未配置 Supabase 时，本文件所有函数都会安全返回错误对象，成绩只落本机。
 */
import { createClient } from '@supabase/supabase-js';
import type { DimensionKey, MarginNote } from '../types.ts';

const url = import.meta.env.VITE_SUPABASE_URL || '';
const key = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
// 用 startsWith 判断，避免正则里的 // 被当成结束符（踩过一次）
const HAS_DB =
  url.startsWith('https://') &&
  !url.includes('placeholder') &&
  key.length > 20 &&
  !key.includes('placeholder');

export const dbReady = HAS_DB;

export const supabase = HAS_DB
  ? createClient(url, key, { auth: { persistSession: false } })
  : null;

/**
 * 兼容旧入口：main.tsx 曾经在这里注入 AI 调用器。
 * 现在 AI 由 lib/aiClient.ts 自己完成健康检查与降级，这里只做启动探测。
 */
export function bootstrapAi(): void {
  if (HAS_DB && supabase) return; // 有云端存档时无需额外动作
  // 无云端：成绩落 localStorage，规则与 AI 均照常可用
}

/* ══════════ 类型化的表结构 ══════════ */

export interface TrainingRecord {
  id: string;
  nickname: string;
  script_id: string;
  script_name: string;
  difficulty: string;
  blindfold: boolean;
  ui_phase: number;
  score_empathy: number;
  score_question: number;
  score_advice: number;
  score_ethics: number;
  score_process: number;
  score_risk: number;
  score_total: number;
  score_source: 'rule' | 'ai' | 'blend';
  ai_used: boolean;
  duration_sec: number;
  created_at: string;
}

export interface UserStats {
  nickname: string;
  sessions: number;
  avg_total: number;
  scripts_done: number;
  avg_empathy: number;
  avg_question: number;
  avg_advice: number;
  avg_ethics: number;
  avg_process: number;
  avg_risk: number;
  weakest_score: number;
}

export interface HeatmapCell {
  day: string;
  sessions: number;
  avg_score: number;
}

/* ══════════ 写入 ══════════ */

/** 提交一次阶段训练：先写主表拿到 id，再批量写逐句点评 */
export async function saveTraining(args: {
  nickname: string;
  scriptId: string;
  scriptName: string;
  difficulty: string;
  blindfold: boolean;
  uiPhase: number;
  scores: Record<DimensionKey, number>;
  total: number;
  scoreSource: 'rule' | 'ai' | 'blend';
  aiUsed: boolean;
  durationSec: number;
  notes: MarginNote[];
}): Promise<{ recordId: string } | { error: string }> {
  const s = args.scores;

  // ★ 六维必须拆成 6 个独立字段，不能塞 JSON
  if (!supabase) return { error: '未配置数据库' };
  const { data, error } = await supabase
    .from('training_records')
    .insert({
      nickname: args.nickname,
      script_id: args.scriptId,
      script_name: args.scriptName,
      difficulty: args.difficulty,
      blindfold: args.blindfold,
      ui_phase: args.uiPhase,
      score_empathy: s.empathy,
      score_question: s.question,
      score_advice: s.advice,
      score_ethics: s.ethics,
      score_process: s.process,
      score_risk: s.risk,
      score_total: args.total,
      score_source: args.scoreSource,
      ai_used: args.aiUsed,
      duration_sec: args.durationSec,
    })
    .select('id')
    .single();

  if (error || !data) return { error: error?.message ?? '写入失败' };

  if (args.notes.length > 0) {
    const rows = args.notes.map((n) => ({
      record_id: data.id,
      turn_index: Number(n.index),
      utterance: n.utterance,
      response: n.response ?? null,
      intent: n.dimension,
      dimension: n.dimension,
      delta: n.delta,
      rule_note: n.ruleNote,
      source: n.source,
      marks: n.marks,
    }));
    const { error: e2 } = await supabase.from('training_details').insert(rows);
    if (e2) return { error: e2.message };
  }

  // 每天一条成长快照（upsert）
  const recordId = data.id;
  const today = new Date().toISOString().slice(0, 10);
  if (!supabase) return { recordId };
  await supabase.from('proficiency').upsert(
    {
      nickname: args.nickname,
      snapshot_date: today,
      score_empathy: s.empathy,
      score_question: s.question,
      score_advice: s.advice,
      score_ethics: s.ethics,
      score_process: s.process,
      score_risk: s.risk,
      score_total: args.total,
    },
    { onConflict: 'nickname,snapshot_date' },
  );

  return { recordId: data.id };
}

/* ══════════ 读取（全部走视图，不在前端算）══════════ */

export async function fetchStats(nickname: string): Promise<UserStats | null> {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from('v_user_stats')
    .select('*')
    .eq('nickname', nickname)
    .maybeSingle();
  if (error) return null;
  return (data as UserStats) ?? null;
}

export async function fetchHeatmap(
  nickname: string,
  days = 126,
): Promise<HeatmapCell[]> {
  const since = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  if (!supabase) return [];
  const { data } = await supabase
    .from('v_training_heatmap')
    .select('*')
    .eq('nickname', nickname)
    .gte('day', since)
    .order('day');
  return (data as HeatmapCell[]) ?? [];
}

export async function fetchProficiency(nickname: string) {
  if (!supabase) return [];
  if (!supabase) return [];
  const { data } = await supabase
    .from('proficiency')
    .select('*')
    .eq('nickname', nickname)
    .order('snapshot_date');
  return data ?? [];
}

/* ══════════ 草稿（防误关丢数据）══════════ */

export async function saveDraft(args: {
  nickname: string;
  scriptId: string;
  difficulty: string;
  blindfold: boolean;
  emotion: number;
  turn: number;
  messages: unknown[];
}) {
  if (!supabase) return;
  await supabase.from('session_record').upsert(
    {
      nickname: args.nickname,
      script_id: args.scriptId,
      difficulty: args.difficulty,
      blindfold: args.blindfold,
      emotion: args.emotion,
      turn: args.turn,
      messages: args.messages,
      updated_at: new Date().toISOString(),
    },
    { onConflict: 'id' },
  );
}

export async function loadDraft(nickname: string, scriptId: string) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('session_record')
    .select('*')
    .eq('nickname', nickname)
    .eq('script_id', scriptId)
    .order('updated_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  return data ?? null;
}

export async function clearDraft(nickname: string, scriptId: string) {
  if (!supabase) return;
  await supabase
    .from('session_record')
    .delete()
    .eq('nickname', nickname)
    .eq('script_id', scriptId);
}

/* ══════════════════════════════════════════════════════════════
   以下为 002 迁移配套的读取与设置接口
   未配置数据库时全部安全降级（返回空 / null），不抛错
   ══════════════════════════════════════════════════════════════ */

/** 训练历史（最近 N 条） */
export async function fetchHistory(nickname: string, limit = 20) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('training_records')
    .select('*')
    .eq('nickname', nickname)
    .order('created_at', { ascending: false })
    .limit(limit);
  return data ?? [];
}

/** 六维平均（雷达图数据源） */
export async function fetchDimensionAvg(nickname: string) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('v_dimension_avg')
    .select('*')
    .eq('nickname', nickname);
  return data ?? [];
}

/** 剧本完成度 */
export async function fetchScriptProgress(nickname: string) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('v_script_progress')
    .select('*')
    .eq('nickname', nickname)
    .order('times', { ascending: false });
  return data ?? [];
}

/** 热力图：按日聚合 */
export async function fetchHeatmapRows(nickname: string) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('v_heatmap')
    .select('*')
    .eq('nickname', nickname)
    .order('day', { ascending: true });
  return data ?? [];
}

/** 单次训练的逐句明细 */
export async function fetchDetails(recordId: string) {
  if (!supabase) return [];
  const { data } = await supabase
    .from('training_details')
    .select('*')
    .eq('record_id', recordId)
    .order('turn_index', { ascending: true });
  return data ?? [];
}

/* ── 用户设置 ────────────────────────────────────────────── */

export interface UserSettings {
  default_difficulty: '简单实习' | '标准实训' | '挑战督导';
  blindfold_default: boolean;
  ai_enabled: boolean;
  /** 训练页的初始 AI 参与度 */
  ai_mode: 'rule' | 'hybrid' | 'ai';
  show_basis: boolean;
  auto_settle: boolean;
  custom_scripts: unknown[];
}

const DEFAULT_SETTINGS: UserSettings = {
  default_difficulty: '标准实训',
  blindfold_default: false,
  ai_enabled: true,
  ai_mode: 'ai',
  show_basis: true,
  auto_settle: true,
  custom_scripts: [],
};

const K_SET = 'knock.settings';

export function loadSettingsLocal(): UserSettings {
  try {
    const v = localStorage.getItem(K_SET);
    return v ? { ...DEFAULT_SETTINGS, ...JSON.parse(v) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettingsLocal(s: Partial<UserSettings>): UserSettings {
  const next = { ...loadSettingsLocal(), ...s };
  localStorage.setItem(K_SET, JSON.stringify(next));
  if (supabase) {
    void supabase
      .from('user_settings')
      .upsert({ ...next, nickname: currentNick(), updated_at: new Date().toISOString() });
  }
  return next;
}

function currentNick(): string {
  try {
    const a = JSON.parse(localStorage.getItem('knock.currentAccount') ?? 'null');
    return a?.nickname ?? '';
  } catch {
    return '';
  }
}

export async function loadSettings(nickname: string): Promise<UserSettings> {
  if (!supabase) return loadSettingsLocal();
  const { data } = await supabase
    .from('user_settings')
    .select('*')
    .eq('nickname', nickname)
    .maybeSingle();
  if (!data) return loadSettingsLocal();
  const next: UserSettings = {
    default_difficulty: data.default_difficulty ?? '标准实训',
    blindfold_default: data.blindfold_default ?? false,
    ai_enabled: data.ai_enabled ?? true,
    ai_mode: data.ai_mode ?? 'hybrid',
    show_basis: data.show_basis ?? true,
    auto_settle: data.auto_settle ?? true,
    custom_scripts: data.custom_scripts ?? [],
  };
  localStorage.setItem(K_SET, JSON.stringify(next));
  return next;
}

/* ── 数据导出与清除 ─────────────────────────────────────── */

/** 导出训练记录为 CSV（答辩/写报告用） */
export function exportCsv(nickname: string, rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return '';
  const head = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    head.join(','),
    ...rows.map((r) => head.map((h) => esc(r[h])).join(',')),
  ];
  // BOM 让 Excel 正确识别 UTF-8
  return '' + lines.join('\r\n');
}

export function downloadText(filename: string, content: string, mime = 'text/csv') {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** 清空当前账号的所有本地数据 */
export async function purgeLocal(): Promise<void> {
  const keys = [
    'knock.records', 'knock.settings', 'knock.draft',
    'knock.sessions', 'knock.heat', 'knock.debriefs', 'knock.nick', 'knock.tourDone',
  ];
  keys.forEach((k) => localStorage.removeItem(k));
  // 按账号存的会话也一并清掉
  try {
    const drop: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('knock.session.')) drop.push(k);
    }
    drop.forEach((k) => localStorage.removeItem(k));
  } catch { /* 忽略 */ }
}
