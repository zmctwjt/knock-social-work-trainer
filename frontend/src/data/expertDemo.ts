/**
 * 专家示范对照库
 *
 * 用途：复盘页「你的回应 vs 专家示范」逐句对照。
 *
 * 关键设计：示范**不是固定文案**，而是按学生实际说出的那句话匹配 ——
 * 说了评判，就给"如何把评判转成探索"；说了空泛共情，就给"如何具体化"。
 * 所以每条示范都必须能被 `matchFlaw()` 从学生原话里判定出来。
 */
import type { DimensionKey } from '../types.ts';
import { normalize } from '../services/rules.ts';

export type FlawKind =
  | 'judge'          // 评判
  | 'vagueEmpathy'   // 空泛共情
  | 'closedQuestion' // 封闭提问
  | 'prematureAdvice'// 建议过早
  | 'judgementOfSelf'// 替对方下判断
  | 'blank'          // 冷场/未接住
  | 'toxic'          // 毒性正能量
  | 'good';          // 做得对（正向示范）

export interface DemoLine {
  flaw: FlawKind;
  /** 命中的关键词（用于从学生原话判定） */
  keywords: string[];
  /** 学生典型说法（用于在界面上标注"你说了类似这句"） */
  studentSays: string;
  /** 专家示范 */
  expert: string;
  /** 为什么这样更好 */
  why: string;
  /** 依据条款 */
  source: string;
  /** 对应维度 */
  dimension: DimensionKey;
  /** 分值影响 */
  delta: number;
}

export const EXPERT_DEMOS: DemoLine[] = [
  {
    flaw: 'judge',
    keywords: ['你应该', '你必须', '你应该多', '你得', '你不能', '你总是', '你就是'],
    studentSays: '您应该多出去走走。',
    expert: '您觉得怎么调整会舒服一些？',
    why: '「你应该」是替对方做判断。改成开放式提问，同样的关切，但决定权还在她手里——这是「服务对象自决原则」4.2.6。',
    source: '公告第 426 号 · 4.2.6',
    dimension: 'ethics',
    delta: -8,
  },
  {
    flaw: 'vagueEmpathy',
    keywords: ['我理解', '我明白', '我能体会', '我知道你的感受', '换我我也'],
    studentSays: '我理解。',
    expert: '一个人撑着，白天忙完了晚上也睡不着——最难受的是哪种时候？',
    why: '空泛共情只能得 4 分，因为没有任何可验证的具体点。补上从她话里抓到的细节，情感才被"接住"。',
    source: '公告第 426 号 · 6.1.1',
    dimension: 'empathy',
    delta: 4,
  },
  {
    flaw: 'closedQuestion',
    keywords: ['是不是', '对吧', '好吧', '好不好', '有没有', '行吗'],
    studentSays: '您是不是也觉得很难？',
    expert: '最难的是哪一部分？',
    why: '封闭提问只能用"是/不是"回答，会把话头关掉。开放式提问才能引出具体叙事，这是「支持性技巧」6.1.1 的核心。',
    source: '公告第 426 号 · 6.1.1',
    dimension: 'question',
    delta: 3,
  },
  {
    flaw: 'prematureAdvice',
    keywords: ['我建议', '你应该去找', '你可以试试', '我推荐', '最好去', '要不你'],
    studentSays: '我建议你去找社区问问。',
    expert: '有两条路我比较熟：社区可以上门服务，也可以先做个评估。你想先了解哪一个？',
    why: '直接给方案等于替对方决定。「给信息 + 让对方选」既提供了支持，又守住了 4.2.6 的自决原则。',
    source: '公告第 426 号 · 4.2.6',
    dimension: 'advice',
    delta: -6,
  },
  {
    flaw: 'judgementOfSelf',
    keywords: ['你怎么能', '这有什么', '换成我', '谁受得了', '你就是想', '你就是'],
    studentSays: '你怎么能忍这么久？',
    expert: '（停顿）……您等了很久了。',
    why: '「怎么能忍」是在指责她的处境，会让她立刻退出关系。先接住事实，再等她决定要不要往下说。',
    source: '公告第 426 号 · 4.2.5',
    dimension: 'ethics',
    delta: -8,
  },
  {
    flaw: 'toxic',
    keywords: ['别想太多', '想开点', '您要乐观', '没什么大不了', '要想开'],
    studentSays: '别想太多，想开点。',
    expert: '（沉默三秒）……您在担心什么？',
    why: '「别想太多」会把可探索的信号直接关掉。正确做法是先允许沉默，再等她自己说出口。',
    source: '公告第 426 号 · 6.1.1',
    dimension: 'empathy',
    delta: -12,
  },
  {
    flaw: 'blank',
    keywords: [],
    studentSays: '（服务对象说完一段后，社工没有接话）',
    expert: '（保持沉默，等她继续）……您刚才说到儿子不常回来。',
    why: '冷场不一定是失败。有时候沉默是给对方整理情绪的时间，但要有意识地"接住最后半句"。',
    source: '公告第 426 号 · 6.1.1',
    dimension: 'empathy',
    delta: 0,
  },
  {
    flaw: 'good',
    keywords: ['我理解你现在', '一个人撑着', '您当时是怎么', '那您', '听起来'],
    studentSays: '我理解你现在一个人撑着很辛苦。',
    expert: '（这就是标准做法）',
    why: '共情 + 具体化 + 留空间三件事同时做到了。共情里有她自己的话，末尾没有封闭，能引出更多。',
    source: '公告第 426 号 · 6.1.1',
    dimension: 'empathy',
    delta: 8,
  },
];

/** 从学生原话判定属于哪一类；判不出返回 null */
export function matchFlaw(text: string): DemoLine | null {
  if (!text || !text.trim()) return EXPERT_DEMOS.find((d) => d.flaw === 'blank')!;
  // ★ 必须归一化敬称：rules.ts 的词表里是「你应该」，
  //   但学生常说「您应该」——不做这一步，评判类会漏判。
  const norm = normalize(text);

  // ★ 顺序很重要：先判正向的具体化共情。
  //   「我理解你现在一个人撑着很辛苦」同时含「我理解」（空泛）
  //   和「一个人撑着」（具体），必须让具体的赢。
  if (/一个人撑着|很辛苦|你当时|你觉得|听起来/.test(norm)) {
    return EXPERT_DEMOS.find((d) => d.flaw === 'good')!;
  }
  for (const d of EXPERT_DEMOS) {
    if (d.flaw === 'blank') continue;
    if (d.keywords.some((k) => norm.includes(k))) return d;
  }
  return null;
}

/** 供结算页使用：把一句话的 delta 换算成可读标签 */
export function deltaLabel(delta: number): string {
  if (delta >= 8) return '有效';
  if (delta > 0) return '略有效';
  if (delta === 0) return '中性';
  if (delta > -8) return '需改进';
  return '需复核';
}