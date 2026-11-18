/**
 * 复盘报告暂存
 *
 * 提交阶段时生成（可能是 AI 生成，也可能回落模板），复盘页按记录 id 读回。
 * 单独放一个模块，避免为了加一个字段去改 store 的会话契约。
 */
import type { DebriefReport } from '../types.ts';

const KEY = 'knock.debriefs';
const MAX = 60;

type Store = Record<string, DebriefReport & { at: number; nickname?: string }>;

function readAll(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function writeAll(v: Store): void {
  try {
    const keys = Object.keys(v);
    if (keys.length > MAX) {
      const keep = keys
        .sort((a, b) => (v[b].at || 0) - (v[a].at || 0))
        .slice(0, MAX);
      const next: Store = {};
      for (const k of keep) next[k] = v[k];
      v = next;
    }
    localStorage.setItem(KEY, JSON.stringify(v));
  } catch {
    /* 配额满时静默放弃 —— 复盘页会回落模板 */
  }
}

export function saveDebrief(recordId: string, report: DebriefReport): void {
  const all = readAll();
  all[recordId] = { ...report, at: Date.now() };
  all.last = { ...report, at: Date.now() };
  writeAll(all);
}

export function loadDebrief(recordId?: string): DebriefReport | null {
  const all = readAll();
  const hit = (recordId && all[recordId]) || all.last;
  if (!hit) return null;
  return {
    strength: hit.strength,
    improvement: hit.improvement,
    nextStep: hit.nextStep,
    source: hit.source,
  };
}

export function clearDebriefs(): void {
  try { localStorage.removeItem(KEY); } catch { /* 忽略 */ }
}
