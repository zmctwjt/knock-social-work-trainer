/**
 * 六维评分引擎
 *
 * 核心公式：综合分 = 规则底分 × 0.4 + AI 评分 × 0.6
 * 这个配比的意义：即使 AI 完全不可用，规则底分仍能给出有专业依据的分数。
 */

import type {
  DimensionKey,
  DimensionMeta,
  MarginNote,
  Intent,
  ProofMark,
  Speaker,
  ChatMessage,
} from '../types.ts';
import { matchLocalRules, isToxicPositivity } from './rules.ts';

/* ═══════════════════════════════════════════════════════════
   一、六维定义（全部锚定国标条款）
   ═══════════════════════════════════════════════════════════ */

export const DIMENSIONS: DimensionMeta[] = [
  {
    key: 'empathy',
    name: '同感与倾听',
    weight: 25,
    source: '公告第 426 号 · 6.1.1 支持性技巧',
    criteria:
      '积极倾听、专注、鼓励、同感。能否准确接住服务对象的情绪并让对方感到被理解。' +
      '空泛的共情（例如只说"我理解"而不接任何具体内容）不得高于 50 分。',
  },
  {
    key: 'question',
    name: '提问与对焦',
    weight: 20,
    source: '公告第 426 号 · 6.1.2 引领性技巧',
    criteria:
      '提问、澄清、对焦、摘要。能否用开放式提问打开话题，并把散乱的话题收拢到焦点上。连续使用封闭式提问应扣分。',
  },
  {
    key: 'advice',
    name: '信息提供与建议',
    weight: 15,
    source: '公告第 426 号 · 6.1.3 影响性技巧',
    criteria:
      '信息提供、自我披露、建议、忠告、对质。能否在合适时机给出信息与选项而不越界下命令。出现"你必须/你应该"直接扣分。',
  },
  {
    key: 'ethics',
    name: '伦理原则',
    weight: 20,
    source: '公告第 426 号 · 4.2.4–4.2.7 接纳·非评判·自决·保密',
    criteria:
      '接纳、非评判、自决、保密。是否做到不评价不指责、不替服务对象做决定、不泄露信息。只要出现评判或说教，本维度不得高于 60 分。',
  },
  {
    key: 'process',
    name: '过程完整性',
    weight: 10,
    source: '公告第 426 号 · 6.1 个案服务过程',
    criteria:
      '接案、预估、计划、介入、评估、结案。是否走完从建立关系到结束约定的完整过程，结束时是否有总结与约定。',
  },
  {
    key: 'risk',
    name: '风险识别与转介',
    weight: 10,
    source: '公告第 426 号 · 6.8.3 转介规范',
    criteria:
      '能否识别「无望感表达」与「自伤意念」的差别，并按规范提出转介。' +
      '对话中出现过无望感表达而学生未识别其含义时，本维度不得高于 60 分。',
  },
];

/** 雷达图用的短名 —— 全名太长（如「风险识别与转介」）会在六边形边上撞在一起 */
export const DIMENSION_SHORT: Record<DimensionKey, string> = {
  empathy: '同感倾听',
  question: '提问对焦',
  advice: '信息建议',
  ethics: '伦理原则',
  process: '过程完整',
  risk: '风险转介',
};

export const DIMENSION_MAP: Record<DimensionKey, DimensionMeta> = DIMENSIONS.reduce(
  (acc, d) => ({ ...acc, [d.key]: d }),
  {} as Record<DimensionKey, DimensionMeta>
);

/** 意图 → 主影响维度 */
export const INTENT_TO_DIMENSION: Record<Intent, DimensionKey> = {
  共情: 'empathy',
  开放提问: 'question',
  封闭提问: 'question',
  评判: 'ethics',
  建议过早: 'advice',
  沉默陪伴: 'empathy',
  离题: 'empathy',
  危机: 'ethics',
};

/* ═══════════════════════════════════════════════════════════
   二、规则底分
   ═══════════════════════════════════════════════════════════ */

export interface RuleScoreInput {
  /** 全部学生发言及其对应的服务对象回应。危机轮请调用方剔除（危机不计分） */
  utterances: { text: string; response?: string }[];
  /** 无望感表达是否出现过 */
  hopelessDetected: boolean;
  /** 无望感是否被识别（学生有探索动作） */
  hopelessRecognized: boolean;
  /** 阶段总数 */
  totalStages: number;
  /** 已完成阶段数 */
  completedStages: number;
  /** 累计分值调整 */
  scoreAdjust: Record<DimensionKey, number>;
  /** 可选的统计覆盖；不传则从 utterances 内部统计 */
  judgeCount?: number;
  vagueEmpathyCount?: number;
}

export function computeRuleScore(input: RuleScoreInput): Record<DimensionKey, number> {
  const adjust = input.scoreAdjust || ({} as Record<DimensionKey, number>);
  const raw: Record<DimensionKey, number> = {
    empathy: 60,
    question: 60,
    advice: 60,
    ethics: 70,
    process: 60,
    risk: 60,
  };

  let judgeSeen = false;
  let vagueEmpathy = 0;

  for (const u of input.utterances || []) {
    const m = matchLocalRules(u.text);

    // 🔴 危机轮不计分：只走危机处置流程（crisis.ts），不进入评分
    if (m.riskLevel === 'suicidal') continue;

    if (m.riskLevel === 'hopelessness' && isToxicPositivity(u.text)) {
      raw.empathy -= 12;
    }

    if (m.intent === '评判' || m.intent === '建议过早') judgeSeen = true;
    if (m.intent === '共情') {
      const bare = u.text.replace(/[\s，。！？、；：""''（）,.!?]/g, '');
      if (bare.length <= 6) vagueEmpathy++;
    }

    for (const [k, v] of Object.entries(m.effects.scoreDeltas) as [DimensionKey, number][]) {
      raw[k] += v;
    }
  }

  const judgeCount = input.judgeCount ?? (judgeSeen ? 1 : 0);
  const vagueCount = input.vagueEmpathyCount ?? vagueEmpathy;

  // ── 硬规则封顶（原来是注释里写着、代码里没做）────────────────
  // 出现评判/说教 → 伦理原则不得高于 60
  if (judgeCount > 0) raw.ethics = Math.min(raw.ethics, 60);
  // 连续空泛共情 → 同感与倾听不得高于 50
  if (vagueCount >= 2) raw.empathy = Math.min(raw.empathy, 50);

  if (input.hopelessDetected && !input.hopelessRecognized) {
    raw.risk = Math.min(raw.risk, 55);
  }
  if (input.hopelessDetected && input.hopelessRecognized) {
    raw.risk = Math.min(100, raw.risk + 10);
  }

  if (input.totalStages > 0) {
    raw.process = Math.round((input.completedStages / input.totalStages) * 100);
  }

  for (const [k, v] of Object.entries(adjust) as [DimensionKey, number][]) {
    raw[k] += v;
  }

  return clampAll(raw);
}

function clampAll(v: Record<DimensionKey, number>): Record<DimensionKey, number> {
  const out = {} as Record<DimensionKey, number>;
  for (const k of Object.keys(v) as DimensionKey[]) {
    out[k] = Math.max(0, Math.min(100, Math.round(v[k])));
  }
  return out;
}

/* ═══════════════════════════════════════════════════════════
   二·五、从对话还原「评分输入」
   ═══════════════════════════════════════════════════════════ */

export interface CollectedUtterances {
  /** 参与评分的发言（已剔除危机轮） */
  utterances: { text: string; response?: string }[];
  /** 学生有效发言条数 */
  workerTurns: number;
  /** 出现评判/建议过早的条数 */
  judgeCount: number;
  /** 空泛共情条数（≤6 字且判为共情） */
  vagueEmpathyCount: number;
  /** 对话里是否出现过无望感表达（取自服务对象台词 + 学生发言） */
  hopelessSeen: boolean;
  /** 学生是否识别了无望感（对含无望感的服务对象台词做了往下探索） */
  hopelessRecognized: boolean;
  /** 是否出现过危机轮 */
  crisisSeen: boolean;
}

/**
 * 把整段对话还原成评分输入。
 *
 * 两个关键约定：
 * ① **危机轮不参与评分** —— 危机走 crisis.ts 的处置流程，卡片上写的「本轮不计分」必须是真的。
 * ② 无望感线索来自**服务对象台词**，不是学生的话 —— 学生不可能说「活着没意思」，
 *    只有服务对象会。学生是否识别，看它下面那句有没有探索动作。
 */
export function collectUtterances(messages: ChatMessage[]): CollectedUtterances {
  const out: CollectedUtterances = {
    utterances: [],
    workerTurns: 0,
    judgeCount: 0,
    vagueEmpathyCount: 0,
    hopelessSeen: false,
    hopelessRecognized: false,
    crisisSeen: false,
  };

  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.speaker === 'system') continue;

    // 学生发言
    if (m.speaker === 'worker') {
      if (m.isCrisis) {
        out.crisisSeen = true;
        continue; // 危机轮不计分
      }
      const match = matchLocalRules(m.text);
      if (match.riskLevel === 'suicidal') {
        out.crisisSeen = true;
        continue;
      }
      out.workerTurns++;
      if (match.intent === '评判' || match.intent === '建议过早') out.judgeCount++;
      if (match.intent === '共情' && m.text.replace(/[\s，。！？、；：""''（）,.!?]/g, '').length <= 6) {
        out.vagueEmpathyCount++;
      }
      const next = messages[i + 1];
      out.utterances.push({
        text: m.text,
        response: next && next.speaker === 'client' ? next.text : undefined,
      });
      continue;
    }

    // 服务对象台词：无望感线索的真正来源
    if (m.speaker === 'client') {
      const r = matchLocalRules(m.text);
      if (r.riskLevel === 'hopelessness') {
        out.hopelessSeen = true;
        const next = messages[i + 1];
        if (next && next.speaker === 'worker') {
          const w = matchLocalRules(next.text);
          // 往下探索 = 开放提问 / 共情 / 沉默陪伴，都算识别到了这是需要停留的话题
          if (w.intent === '开放提问' || w.intent === '共情' || w.intent === '沉默陪伴') {
            out.hopelessRecognized = true;
          }
        }
      }
    }
  }

  return out;
}

/* ═══════════════════════════════════════════════════════════
   三、综合分
   ═══════════════════════════════════════════════════════════ */

const DIM_KEYS: DimensionKey[] = ['empathy', 'question', 'advice', 'ethics', 'process', 'risk'];

/** 把任意输入收敛成 0-100 的有限数；NaN / undefined / 越界一律兜回 fallback */
function safeScore(v: unknown, fallback = 0): number {
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export function weightedTotal(scores: Record<DimensionKey, number>): number {
  let total = 0;
  for (const d of DIMENSIONS) {
    total += safeScore(scores?.[d.key], 0) * (d.weight / 100);
  }
  return Math.max(0, Math.min(100, Math.round(total)));
}

/**
 * 综合分 = 规则底分 × 0.4 + AI 评分 × 0.6
 *
 * 这是本作品的立论公式，因此必须有真实的可达路径：
 * AI 缺项、NaN、越界时整条 AI 分作废，只用规则底分 —— 而不是拼出半张表。
 */
export function mergeScores(
  rule: Record<DimensionKey, number>,
  ai: Record<DimensionKey, number> | null,
  ratio = { rule: 0.4, ai: 0.6 },
): { scores: Record<DimensionKey, number>; usedAI: boolean; missing: DimensionKey[] } {
  const ruleSafe = {} as Record<DimensionKey, number>;
  for (const k of DIM_KEYS) ruleSafe[k] = safeScore(rule?.[k], 60);

  if (!ai) return { scores: ruleSafe, usedAI: false, missing: DIM_KEYS.slice() };

  const missing: DimensionKey[] = [];
  const aiSafe = {} as Record<DimensionKey, number>;
  for (const k of DIM_KEYS) {
    const v = ai[k];
    const n = typeof v === 'number' ? v : Number(v);
    if (!Number.isFinite(n)) {
      missing.push(k);
      aiSafe[k] = ruleSafe[k];
    } else {
      aiSafe[k] = Math.max(0, Math.min(100, Math.round(n)));
    }
  }

  // 任意一维缺失就整条降级，避免「四分之一的 AI 分」这种不可解释的中间态
  if (missing.length > 0) {
    return { scores: ruleSafe, usedAI: false, missing };
  }

  const merged = {} as Record<DimensionKey, number>;
  for (const k of DIM_KEYS) {
    merged[k] = safeScore(ruleSafe[k] * ratio.rule + aiSafe[k] * ratio.ai, ruleSafe[k]);
  }
  return { scores: merged, usedAI: true, missing: [] };
}

/* ═══════════════════════════════════════════════════════════
   四、逐句点评
   ═══════════════════════════════════════════════════════════ */

export interface NoteInput {
  index: number;
  speaker: Speaker;
  utterance: string;
  response?: string;
}

export function buildMarginNotes(notes: NoteInput[]): MarginNote[] {
  return notes.map((n) => {
    const m = matchLocalRules(n.utterance);
    const dimKey = INTENT_TO_DIMENSION[m.intent];
    const delta = Object.values(m.effects.scoreDeltas).reduce(
      (s: number, v: number | undefined) => s + (v ?? 0),
      0
    );
    return {
      index: String(n.index).padStart(2, '0'),
      speaker: n.speaker,
      utterance: n.utterance,
      response: n.response,
      dimension: dimKey,
      delta,
      ruleNote: m.effects.note,
      source: m.effects.source,
      marks: buildMarks(n.utterance, m.intent, m.hitWords),
    };
  });
}

/** 无望感线索词 —— 与 rules.ts 的 HOPELESSNESS_WORDS 保持同一口径（去掉中性高频词） */
const HOPELESS_MARKS = [
  '活着没意思', '活着没什么意思', '没盼头', '没指望', '看不到头', '活够了',
  '没什么意思', '没意义', '熬日子', '等死',
];

/**
 * 生成校样标记 —— 本产品的视觉记忆点。
 * · 删除线 = 扣分　· 绿色下划线 = 加分　· 红色 ▲ = 需人工复核的判断点
 *
 * ⚠️ 下标必须落在**原文**上：normalize() 会把「咱」扩写成「我们」使长度变化，
 *    直接拿归一化下标画线会整体偏位。因此在原文中找不到的词宁可跳过，
 *    也不要画出错位的下划线。
 */
export function buildMarks(text: string, intent: Intent, hitWords: string[]): ProofMark[] {
  const marks: ProofMark[] = [];
  const t = text;
  const seen = new Set<string>();

  // 危机与评判同属扣分侧，用删除线；共情/提问等用绿色加分线
  const isBad = intent === '评判' || intent === '建议过早' || intent === '危机';

  for (const w of hitWords || []) {
    if (!w || w.length < 2) continue;
    let idx = t.indexOf(w);
    // 归一化改写过原文（如 您→你）时，退化到原文里的近似匹配，找不到就不标
    if (idx < 0) continue;
    const key = `${idx}:${w.length}`;
    if (seen.has(key)) continue;
    seen.add(key);
    marks.push({ kind: isBad ? 'del' : 'add', start: idx, end: idx + w.length });
  }

  // 无望感线索：这是需要学生「识别并往下探索」的判断点，用 caret + margin 标注
  if (intent !== '危机') {
    for (const w of HOPELESS_MARKS) {
      const idx = t.indexOf(w);
      if (idx < 0) continue;
      marks.push({ kind: 'caret', start: idx, end: idx + w.length });
      marks.push({ kind: 'margin', start: idx, end: idx });
      break;
    }
  }

  return marks;
}

/* ═══════════════════════════════════════════════════════════
   五、薄弱项定位与推荐
   ═══════════════════════════════════════════════════════════ */

export interface WeaknessReport {
  dimension: DimensionKey;
  name: string;
  score: number;
  recommendScenario: string;
  recommendNode: string;
  recommendCard: string;
  advice: string;
}

export const WEAKNESS_ADVICE: Record<
  DimensionKey,
  { scenario: string; node: string; card: string; advice: string }
> = {
  empathy: {
    scenario: 'W-01',
    node: 'W-07',
    card: 'T-01 共情三层次',
    advice:
      '你在她说出无望感表达之后正确地选择了往下探索，这一步做对了。' +
      '但要注意区分具体共情与空泛共情——只说「我理解」而不接具体内容，会被判为空泛。',
  },
  question: {
    scenario: 'C-03',
    node: 'C-01',
    card: 'T-03 开放式提问八句式',
    advice:
      '本次出现封闭式提问。封闭式提问只能得到「是/不是」的答案，会压缩服务对象的表达空间。' +
      '建议改成「当时发生了什么？」这类开放式问法。',
  },
  advice: {
    scenario: 'L-02',
    node: 'L-03',
    card: 'T-17 给建议 vs 下命令',
    advice:
      '国标 6.1.3 明确要求：建议必须在「对情况和需要了解评估后」提出。' +
      '你有多次在还没充分了解情况时就给出方案。',
  },
  ethics: {
    scenario: 'A-06',
    node: 'A-03',
    card: 'T-10 避免「同盟」陷阱',
    advice:
      '本次出现了评判或说教表达，违反非评判原则（4.2.5）。' +
      '另外在阿珍剧本中要特别注意：不要追问细节，也不要替她做决定——决定权在她。',
  },
  process: {
    scenario: 'U-05',
    node: 'U-05',
    card: 'T-13 结束的技巧',
    advice:
      '面谈结束时缺少总结与约定。实务中需要提前告知结案时间，并留一个具体的跟进安排。',
  },
  risk: {
    scenario: 'W-01',
    node: 'W-07',
    card: 'T-19 转介四步',
    advice:
      '对话中出现了「活着没意思」这类无望感表达，但你没有识别出它的临床含义。' +
      '要点：它属🟡关注级，需要往下探索，而不是🔴危机级需要拦截——两者处理方式完全不同。',
  },
};

export function findWeakness(scores: Record<DimensionKey, number>): WeaknessReport {
  let worst: DimensionKey = 'risk';
  let worstScore = 101;
  for (const d of DIMENSIONS) {
    if (scores[d.key] < worstScore) {
      worstScore = scores[d.key];
      worst = d.key;
    }
  }
  const a = WEAKNESS_ADVICE[worst];
  return {
    dimension: worst,
    name: DIMENSION_MAP[worst].name,
    score: worstScore,
    recommendScenario: a.scenario,
    recommendNode: a.node,
    recommendCard: a.card,
    advice: a.advice,
  };
}

/* ═══════════════════════════════════════════════════════════
   六、无剧透模式的展示映射
   ═══════════════════════════════════════════════════════════ */

export function displayScore(score: number, blindfold: boolean): string {
  return blindfold ? '•••' : String(score);
}

export function barOpacity(blindfold: boolean): number {
  return blindfold ? 0.16 : 1;
}