/**
 * 三级风险分级 —— 本项目最重要的专业设计
 *
 * 核心区分：
 *   🟢 无
 *   🟡 关注级（无望感表达）：「活着没意思」「没盼头」——需引导探索，**不拦截**
 *   🔴 危机级（自伤意念）：「不想活」「自杀」——本地硬拦截，**永不调用模型**
 *
 * 为什么这么分？
 * 社工专业要求把无望感表达当作「可探索的临床线索」，而不是需要立刻堵住的危险。
 * 新手最常见的错误是对无望感说「别这么想、您要乐观」——这属于"毒性正能量"，
 * 会把信号关掉，比不回应更糟。
 */

import type { RiskLevel, CrisisCardContent } from '../types.ts';
import {
  normalize,
  findCrisisHits,
  HOPELESSNESS_WORDS,
  isToxicPositivity,
} from './rules.ts';

function hits(text: string, words: string[]): string[] {
  return words.filter((w) => text.includes(w));
}

export function classifyRisk(rawInput: string): RiskLevel {
  const text = normalize(rawInput);
  // ★ 必须走 findCrisisHits 的边界判定：
  //   「你可以打我电话」「拿刀切菜」不能被当成自杀/他伤陈述（crisis.ts 与 rules.ts 同一口径）
  if (findCrisisHits(text).length > 0) return 'suicidal';
  if (hits(text, HOPELESSNESS_WORDS).length > 0) return 'hopelessness';
  return 'none';
}

/* ═══════════════════════════════════════════════════════════
   一、🟡 关注级：无望感表达的处理
   ═══════════════════════════════════════════════════════════ */

/**
 * 无望感表达后的处置建议。
 * @returns 界面提示条文案；非关注级返回 null
 */
export function hopelessnessHint(rawInput: string): string | null {
  if (classifyRisk(rawInput) !== 'hopelessness') return null;
  if (isToxicPositivity(rawInput)) {
    return (
      '注意：这属于「毒性正能量」回应。标准要求「理解准确并将其传达给服务对象」，' +
      '而不是用乐观覆盖她的感受。正确动作是往下探索——这种感觉是从什么时候开始的？'
    );
  }
  return (
    '这是无望感表达，按三级风险分级属🟡关注级，不触发危机拦截。' +
    '建议往下探索具体感受，不要急于安抚或转移话题。'
  );
}

/** 该表达应被 AI 建议卡如何引导 */
export function recommendedDirection(rawInput: string): string {
  if (isToxicPositivity(rawInput)) return 'downward'; // 往下探索
  if (classifyRisk(rawInput) === 'hopelessness') return 'downward';
  return 'neutral';
}

/* ═══════════════════════════════════════════════════════════
   二、🔴 危机级：硬拦截卡片
   ═══════════════════════════════════════════════════════════ */

/**
 * 生成《危机干预提示卡》内容。
 *
 * ⚠️ 合规要求：
 *   1. 卡上出现的号码必须是真实可用的，**不得编造**
 *   2. 本卡只提供处置指引，不做安全评估结论
 *   3. 命中后由界面暂停对话输入，直到用户点「我知道了」
 */
export function buildCrisisCard(
  rawInput: string,
  _isFamilyViolence = false,
): CrisisCardContent | null {
  if (classifyRisk(rawInput) !== 'suicidal') return null;

  return {
    level: 'suicidal',
    title: '已暂停本次训练 · 本轮不计分',
    principles: [
      '如果这是真实情境，请这样做：',
      '1. 不要单独处理，立即联系你的专业督导。',
      '2. 如实记录：时间、对话内容、你的观察。',
      '3. 不要承诺保密——安全例外优先于保密原则。',
      '4. 不离开，保持在场的姿态，等待专业人员介入。',
      '5. 不要独自做安全评估结论。',
    ],
    hotlines: [
      { code: '12356', label: '全国统一心理援助热线 · 24 小时 · 免费 · 精神科医师与心理治疗师接听' },
      { code: '110', label: '报警' },
      { code: '120', label: '急救' },
    ],
    citation:
      '依据：国家卫生健康委《关于应用"12356"全国统一心理援助热线电话号码的通知》（国卫医政函〔2024〕259 号）。',
    disclaimer:
      '本作品是沟通训练工具，不做安全评估，也不承担危机处理职能。' +
      '校内支持渠道请在使用前自行填写，此处不预置未经核实的号码。',
  };
}

/* ═══════════════════════════════════════════════════════════
   三、AI 建议卡的四种内容（按情绪值与评判次数切换）
   ═══════════════════════════════════════════════════════════ */

export interface SuggestionCard {
  title: string;
  quote: string;
  basis: string;
}

export function buildSuggestion(
  emotion: number,
  judgeCount: number,
  hopelessDetected: boolean,
  lastUtterance = '',
): SuggestionCard {
  const last = lastUtterance.trim();

  // ① 说教/命令口吻 → 立刻纠偏（优先级最高）
  if (/(你应该|你必须|你不该|别想太多|这有什么|没必要)/.test(last)) {
    return {
      title: '建议 · 刚才那句有说教味',
      quote: '您是想让我帮您拿个主意，还是先听您说说？',
      basis:
        '刚才的话里带了「应该 / 必须」，属于替对方做决定（公告第 426 号 · 4.2.5 非评判原则）。' +
        '把选择权交回去，比直接给方案更容易让对方开口。',
    };
  }

  // ② 空泛共情 → 给出具体化示范
  if (last.length <= 6 && /理解|明白|懂/.test(last)) {
    return {
      title: '建议 · 共情可以再具体一点',
      quote: '您说一个人过日子，最难的是哪一段？',
      basis:
        '只说「我理解」而不接任何具体内容，会判为空泛共情（该维度不得高于 50 分）。' +
        '把对方刚说的处境复述一遍，再问一个具体的点。',
    };
  }

  // ③ 已经在追问 → 顺着往下走深一层
  if (last.length > 6 && /(吗|呢|什么|怎么|说说)/.test(last)) {
    return {
      title: '建议 · 顺着这个点再深一层',
      quote: '那时候，您心里是什么感觉？',
      basis:
        '刚才那句已经是开放式提问，做对了。再往下可以从「事情」走到「感受」，' +
        '这是问题探索阶段的核心动作（公告第 426 号 · 6.1.2 引领性技巧）。',
    };
  }

  // ④ 评判累计 3 次 → 纠偏优先
  if (judgeCount >= 3) {
    return {
      title: '建议 · 出现说教倾向',
      quote: '我理解您现在最想让他做点什么。',
      basis:
        '本阶段已累计 3 次命中评判词表（4.2.5 非评判原则）。' +
        '先把决定权交回给对方，再谈做法。',
    };
  }

  if (emotion < 35) {
    return {
      title: '建议 · 对抗中，先给空间',
      quote: '没关系的，我下周再来。',
      basis: `情绪值已降至 ${emotion}，低于 35。按 T-05「沉默的力量」此刻不要推进话题，给一个不丢面子的台阶比追问更有效。`,
    };
  }

  if (emotion <= 60) {
    if (hopelessDetected) {
      return {
        title: '建议 · 观望中，可以往下问',
        quote: '那这种感觉，是从什么时候开始有的？',
        basis:
          '服务对象已表达无望感但未正面回答。' +
          '改用「开始有」降低压力，把话题停在对方愿意接的地方。',
      };
    }
    return {
      title: '建议 · 观望中，先接住再说',
      quote: '您刚才说的这些，听着挺沉的。',
      basis:
        `当前情绪值 ${emotion}，仍在观望区间。按 T-08「从抱怨里找需求」，` +
        '先把情绪接住，再往具体的事上收。',
    };
  }

  return {
    title: '建议 · 开放中，可以深入',
    quote: '那时候你一个人，是怎么过来的？',
    basis:
      `当前情绪值 ${emotion}，服务对象已建立信任。按 T-07「复述与澄清」，` +
      '可以从时间线切入，追问那段时间的应对方式。',
  };
}