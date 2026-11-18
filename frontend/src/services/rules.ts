/**
 * 本地关键词规则引擎
 *
 * 设计要点（这是平台反复做错的地方，必须按此实现）：
 * 1. 敬称归一化必须在匹配【之前】做，否则「您应该」永远命中不了「你应该」
 * 2. 规则命中即免调 AI —— 这是控秒点的核心
 * 3. 危机级永远不走 AI —— 安全内容不交给模型
 * 4. 词表只维护「你」版本，归一化负责覆盖敬称
 */

import type { Intent, RiskLevel, DimensionKey } from '../types.ts';

/* ═══════════════════════════════════════════════════════════
   一、敬称归一化
   ═══════════════════════════════════════════════════════════ */

/**
 * 生成用于匹配的归一化文本。
 * 注意：绝不能用它替换或覆盖学生原文，只用于匹配判断。
 *
 * 顺序很重要：长模式必须在短模式之前，否则「您自己」会先被「您」替换掉。
 */
export function normalize(input: string): string {
  return input
    // 「您们方」必须先于「您们」—— 否则永远不可达
    .replace(/您们方/g, '我们方')
    .replace(/您们/g, '你们')
    .replace(/您自己/g, '你自己')
    .replace(/您/g, '你')
    // 「咱们」必须先于「咱」—— 否则 咱们 → 我们们
    .replace(/咱们/g, '我们')
    .replace(/咱/g, '我们');
}

/** 去空白与标点，用于枚举值解析 */
export function stripPunctuation(input: string): string {
  return input.replace(/[\s，。！？、；：""''（）【】,.!?;:'"()[\]<>《》—…·]/g, '');
}

/* ═══════════════════════════════════════════════════════════
   二、词表定义
   ═══════════════════════════════════════════════════════════ */

export interface RuleHit {
  intent: Intent;
  dimension: DimensionKey;
  /** 情绪值增减 */
  emotionDelta: number;
  /** 分数增减 */
  scoreDelta: number;
  /** 命中说明，写进逐句点评 */
  note: string;
  /** 国标出处 */
  source: string;
  /** 权重（保留词表原序，用 1 表示命中，保留数组顺序仅为可读性） */
  weight?: number;
}

/** 共情词表 —— 命中即共情意图 */
export const EMPATHY_WORDS: string[] = [
  '我理解', '我能理解', '我能感受到', '听起来你', '感觉你',
  '我理解你现在', '你一个人撑着', '你这些年不容易', '你已经撑了很久',
  '辛苦你了', '这确实很难', '换了我也会', '这让人很难受',
  '你有这样的感觉是正常的', '会这么想很正常', '这确实不是你的错',
];

/** 开放式提问词表 */
export const OPEN_QUESTION_WORDS: string[] = [
  '什么', '什么时候', '怎么样', '怎么想', '怎么看',
  '怎么', '如何', '后来呢', '然后呢', '能说说',
  '多说说', '聊聊', '讲讲', '展开说说', '举个例子',
  '那段时间', '当时', '具体是', '后来发生', '从什么时候开始',
  '你说的这个', '能具体说说',
];

/** 封闭式提问的判定特征 */
export const CLOSED_QUESTION_SUFFIX: string[] = ['吗', '吧', '对吧', '是不是', '有没有', '好不好'];

/**
 * 评判词表 —— 违反非评判原则（公告第 426 号 · 4.2.5）
 *
 * ⚠️ 不要收录「你怎么」这种子串：它是「你怎么看/你怎么想」的公共前缀，
 *    而后者恰恰是最标准的开放式提问。只收录完整评判句式。
 */
export const JUDGE_WORDS: string[] = [
  '你应该', '你必须', '你不该', '你怎么能', '你怎么回事', '你这个人',
  '你这样不行', '你太天真了', '你听我的没错', '你这是错的', '这样不对',
  '你太过分了', '都是你的问题', '你这是逃避', '你就是不想面对',
  '这有什么', '这算什么', '想开点', '别想太多', '多大点事',
  '不至于', '你也太矫情了', '孝顺', '不孝', '女人就该', '男人都这样',
  '一个巴掌拍不响', '你自己也有责任', '你就是想太多', '有什么好难过的',
];

/** 建议过早词表 */
export const PREMATURE_ADVICE_WORDS: string[] = [
  '你应该去', '你最好去', '我建议你', '你要不要考虑', '你必须面对',
  '你不用管了', '没什么大不了', '你要坚强', '忍一忍就过去了',
  '建议你去', '劝你', '你应该早点', '你最好马上', '你先别问了',
  '你就应该', '听我的没错', '我比你懂',
];

/** 沉默陪伴词表 */
export const SILENCE_ACCOMPANY_WORDS: string[] = [
  '我在这儿听着', '我在这里', '不着急', '慢慢说', '想好了再说',
  '不说话也可以', '没关系', '你先歇会儿', '什么时候想说了就说',
];

/** 离题词表 */
export const OFF_TOPIC_WORDS: string[] = [
  '我先去上个厕所', '我要去洗手间', '今天星期几', '现在几点了',
  '外面下雨了吗', '你几岁', '你叫什么名字', '你今年多大',
  '你是真人吗', '你是不是机器人', '帮我查一下', '换个话题',
  '我不想聊了', '我饿了', '帮我倒杯水', '你有微信吗',
];

/**
 * 危机级词表 —— 🔴 最高优先级，命中即本地硬拦截，绝不调用 AI。
 *
 * ⚠️ 注意：「活着没意思」「没盼头」**不在本表**，
 *    它们属于无望感表达（RiskLevel.hopelessness），处理方式完全不同。
 */
export const CRISIS_WORDS: string[] = [
  // 自杀意念
  '自杀', '想死', '不想活', '死了算了', '活不下去', '结束生命',
  '了结自己', '一了百了', '活着没意义不如死', '不如死了',
  // 自伤行为
  '割腕', '割手', '跳楼', '跳河', '上吊', '吞药',
  '吃药自杀', '划伤自己', '伤害自己',
  // 被害陈述
  '打死我', '要杀我', '掐我脖子', '他打我', '拿刀',
  '把我推下去', '打我',
  // 极端绝望
  '我不配活着', '反正也没人在乎我死活', '死了更好',
];

/**
 * 「打我」类词的致电语境左邻词：
 *   「你可以打我电话」「给我打电话」「让他打我手机」都是联系方式，不是被害陈述。
 * 命中时看关键词左侧是否以这些词收尾，或右侧是否紧跟号码类词。
 */
const DIALING_LEFT = ['可以', '可', '能', '给', '帮', '替', '让', '请', '麻烦', '打', '用'];
const DIALING_RIGHT = ['电话', '手机', '号码', '手机号', '微信', '座机'];

/** 「拿刀」类词的烹饪语境右邻字：「拿刀切菜」「拿刀剁馅」「拿刀削皮」不是威胁 */
const CUTTING_RIGHT = /^[切剁削]/;

/**
 * 危机词的边界感知匹配。
 *
 * 为什么不能用裸 `includes`：
 *   「你可以打我电话」含「打我」→ 被判 suicidal，学生一句正常的联系约定就被误伤；
 *   「拿刀切菜」含「拿刀」→ 同样误伤。
 * 判定权在上下文，不在子串。
 */
export function findCrisisHits(rawInput: string): string[] {
  const text = normalize(rawInput);
  const out: string[] = [];
  for (const w of CRISIS_WORDS) {
    let from = 0;
    for (;;) {
      const idx = text.indexOf(w, from);
      if (idx < 0) break;
      const left = text.slice(0, idx);
      const right = text.slice(idx + w.length);
      const dialing =
        w.includes('打我') &&
        (DIALING_RIGHT.some((r) => right.startsWith(r)) ||
          DIALING_LEFT.some((l) => left.endsWith(l)));
      const cutting = w.includes('刀') && CUTTING_RIGHT.test(right);
      if (!dialing && !cutting) {
        out.push(w);
        break; // 该词已确认命中，不再找下一次出现
      }
      from = idx + 1;
    }
  }
  return out;
}

/**
 * 无望感词表 —— 🟡 关注级。
 * 这些表达容易被误判为危机，但社工专业要求把它当作「可探索的临床线索」而非需要堵住的危险。
 *
 * ⚠️ 不要收录「随便/都行/无所谓/习惯了/没用」这类中性高频词：
 *    「随便聊聊」「都行」「习惯了这样」是日常口语，判成无望感会让评分全线误扣。
 */
export const HOPELESSNESS_WORDS: string[] = [
  '活着没意思', '没意思', '没盼头', '没指望', '看不到头', '看不到希望',
  '没劲', '没希望', '我这种人', '我这老太婆', '拖累', '活够了',
  '就这样过呗', '反正也一样', '熬日子', '等死', '白活了',
];

/* ═══════════════════════════════════════════════════════════
   三、判定顺序（顺序即优先级，不可调整）
   ═══════════════════════════════════════════════════════════ */

/**
 * 判定顺序（就写在 matchLocalRules 的注释编号里，不再另存一份数组）：
 *
 *   1. 危机级 —— 最高优先，绝不调 AI
 *   2. 评判
 *   3. 建议过早
 *   4. 离题        ← 必须排在开放式/封闭式提问之前
 *   5. 沉默陪伴
 *   6. 共情
 *   7. 开放式提问
 *   8. 封闭式提问（特征式判定）
 *
 * ⚠️ 离题必须在提问之前：「你叫什么名字」含「什么」，
 *    「外面下雨了吗」含「吗」，先判提问会全部误分类成提问意图。
 *    （原 CHECK_ORDER 数组已删除：它没有任何读者，改一处漏一处反而误导。）
 */

export interface MatchResult {
  intent: Intent;
  /** 是否命中了风险词 */
  riskLevel: RiskLevel;
  /** 命中的词（用于界面标注） */
  hitWords: string[];
  /** 该意图对应的评分动作 */
  effects: {
    emotionDelta: number;
    scoreDeltas: Partial<Record<DimensionKey, number>>;
    note: string;
    source: string;
  };
  /** 该轮是否需要调用 AI —— 规则命中即为 false */
  shouldCallAI: boolean;
}

const NO_EFFECT: MatchResult['effects'] = {
  emotionDelta: 0,
  scoreDeltas: {},
  note: '',
  source: '',
};

/**
 * 八类意图的标准评分动作 —— 规则层与 effectsForIntent 共用同一张表。
 * 口径：共情加分、评判扣 ethics、危机扣 ethics+risk 侧最重的 ethics，
 * 与 matchLocalRules 各分支的返回值逐字一致，从源头上杜绝「两套账」。
 */
const INTENT_EFFECTS: Record<Intent, MatchResult['effects']> = {
  共情: {
    emotionDelta: +8,
    scoreDeltas: { empathy: +8 },
    note: '准确接住并传达了服务对象的感受',
    source: '公告第 426 号 · 6.1.1 同感',
  },
  开放提问: {
    emotionDelta: +5,
    scoreDeltas: { question: +8 },
    note: '开放式提问有助于展开话题',
    source: '公告第 426 号 · 6.1.2 提问',
  },
  封闭提问: {
    emotionDelta: -3,
    scoreDeltas: { question: -3 },
    note: '封闭式提问压缩了对方的表达空间',
    source: '公告第 426 号 · 6.1.2 提问',
  },
  评判: {
    emotionDelta: -8,
    scoreDeltas: { ethics: -8 },
    note: '命中「说教训导」或评判表达，违反非评判原则',
    source: '公告第 426 号 · 4.2.5 非评判原则',
  },
  建议过早: {
    emotionDelta: -5,
    scoreDeltas: { advice: -8 },
    note: '在尚未充分了解情况时给出方案，违反「对情况和需要了解评估后」的要求',
    source: '公告第 426 号 · 6.1.3 影响性技巧',
  },
  沉默陪伴: {
    emotionDelta: +6,
    scoreDeltas: { empathy: +6 },
    note: '服务对象沉默时给出空间，符合「专注」技巧',
    source: '公告第 426 号 · 6.1.1 专注',
  },
  离题: {
    emotionDelta: -5,
    scoreDeltas: {},
    note: '未接住服务对象当前的话，六维分数不变',
    source: '',
  },
  危机: {
    emotionDelta: -10,
    scoreDeltas: { ethics: -12 },
    note: '命中危机词，由本地硬规则拦截，不调用模型',
    source: '公告第 426 号 · 6.8.3',
  },
};

/** 复制一份意图评分动作，避免调用方改到共享表 */
function cloneEffect(e: MatchResult['effects']): MatchResult['effects'] {
  return {
    emotionDelta: e.emotionDelta,
    scoreDeltas: { ...e.scoreDeltas },
    note: e.note,
    source: e.source,
  };
}

/**
 * 按意图返回标准评分动作 —— 供「AI 补判覆盖 intent」后重新计分。
 *
 * 背景：matchLocalRules 未覆盖时会返回占位意图 + 空 effects，
 * 调用方（useSession）用 AI 结果覆盖 intent 后若不换 effects，
 * 模型判出的「评判」「危机」就会零扣分 —— 这是评分不对称的根因。
 *
 * 返回结构与 matchLocalRules(...).effects 完全一致：
 * `{ emotionDelta, scoreDeltas, note, source }`，且数值来自同一张表。
 *
 * ⚠️ 唯一的例外是「空泛共情」：那需要读原文才能判，只能由 matchLocalRules
 *    走 isVagueEmpathy 处理，本函数返回的是具体共情的口径。
 */
export function effectsForIntent(intent: Intent): MatchResult['effects'] {
  const base = INTENT_EFFECTS[intent];
  return base ? cloneEffect(base) : cloneEffect(NO_EFFECT);
}

/**
 * 核心：本地规则判定。
 *
 * @param rawInput 学生原始输入（不做任何清洗）
 * @returns 判定结果。**返回 null 表示规则库未覆盖，应交给 AI 分类。**
 */
export function matchLocalRules(rawInput: string): MatchResult {
  const text = normalize(rawInput);

  // ── 1. 危机级：最高优先，本地硬拦截（边界感知，见 findCrisisHits）──
  const crisisHit = findCrisisHits(text);
  if (crisisHit.length > 0) {
    return {
      intent: '危机',
      riskLevel: 'suicidal',
      hitWords: crisisHit,
      effects: cloneEffect(INTENT_EFFECTS['危机']),
      shouldCallAI: false,
    };
  }

  // ── 2. 评判 ──
  const judgeHit = findHits(text, JUDGE_WORDS);
  if (judgeHit.length > 0) {
    return {
      intent: '评判',
      riskLevel: checkHopelessness(text),
      hitWords: judgeHit,
      effects: cloneEffect(INTENT_EFFECTS['评判']),
      shouldCallAI: false,
    };
  }

  // ── 3. 建议过早 ──
  const prematureHit = findHits(text, PREMATURE_ADVICE_WORDS);
  if (prematureHit.length > 0) {
    return {
      intent: '建议过早',
      riskLevel: checkHopelessness(text),
      hitWords: prematureHit,
      effects: cloneEffect(INTENT_EFFECTS['建议过早']),
      shouldCallAI: false,
    };
  }

  // ── 4. 离题（必须排在提问判定之前）──
  const offTopicHit = findHits(text, OFF_TOPIC_WORDS);
  if (offTopicHit.length > 0) {
    return {
      intent: '离题',
      riskLevel: checkHopelessness(text),
      hitWords: offTopicHit,
      effects: cloneEffect(INTENT_EFFECTS['离题']),
      shouldCallAI: false,
    };
  }

  // ── 5. 沉默陪伴 ──
  // ⚠️ 这里不能直接 return riskLevel:'none'：
  //    「没关系，活着没意思」是「安抚 + 无望感」的复合句，先命中「没关系」，
  //    若不再查风险，最重要的临床线索就被沉默陪伴吞掉了。
  const silenceHit = findHits(text, SILENCE_ACCOMPANY_WORDS);
  if (silenceHit.length > 0) {
    return {
      intent: '沉默陪伴',
      riskLevel: checkHopelessness(text),
      hitWords: silenceHit,
      effects: cloneEffect(INTENT_EFFECTS['沉默陪伴']),
      shouldCallAI: false,
    };
  }

  // ── 6. 共情 ──
  const empathyHit = findHits(text, EMPATHY_WORDS);
  if (empathyHit.length > 0) {
    // 空泛共情检测：「我理解」后 15 字内没有具体内容 → 减半
    const isVague = isVagueEmpathy(text, empathyHit[0]);
    const base = INTENT_EFFECTS['共情'];
    const delta = isVague ? +4 : base.emotionDelta;
    return {
      intent: '共情',
      riskLevel: checkHopelessness(text),
      hitWords: empathyHit,
      effects: {
        ...cloneEffect(base),
        emotionDelta: delta,
        scoreDeltas: { empathy: delta },
        note: isVague
          ? '空泛共情，后文未具体化。标准要求「理解准确并将其传达」'
          : base.note,
      },
      shouldCallAI: false,
    };
  }

  // ── 7. 开放式提问 ──
  const openHit = findHits(text, OPEN_QUESTION_WORDS);
  if (openHit.length > 0) {
    return {
      intent: '开放提问',
      riskLevel: checkHopelessness(text),
      hitWords: openHit,
      effects: cloneEffect(INTENT_EFFECTS['开放提问']),
      shouldCallAI: false,
    };
  }

  // ── 8. 封闭式提问（特征式）──
  const closedHit = findHits(text, CLOSED_QUESTION_SUFFIX);
  if (closedHit.length > 0) {
    return {
      intent: '封闭提问',
      riskLevel: checkHopelessness(text),
      hitWords: closedHit,
      effects: cloneEffect(INTENT_EFFECTS['封闭提问']),
      shouldCallAI: false,
    };
  }

  // ── 9. 空输入视为沉默陪伴 ──
  if (text.trim().length === 0) {
    return {
      intent: '沉默陪伴',
      riskLevel: 'none',
      hitWords: [],
      effects: {
        ...cloneEffect(INTENT_EFFECTS['沉默陪伴']),
        note: '本轮未发言，给予沉默空间',
      },
      shouldCallAI: false,
    };
  }

  // ── 规则库未覆盖 ──
  // 只有走到这里才允许调用 AI 分类。
  // ⚠️ 若这句话同时含无望感词，风险等级必须透传给 AI 结果。
  // 调用方拿到 AI 意图后，必须同时调用 effectsForIntent(aiIntent) 换分值口径。
  return {
    intent: '共情', // 占位：调用方拿到 AI 意图后必须换成真实意图 + 对应分值
    riskLevel: checkHopelessness(text),
    hitWords: [],
    // 故意给空分值：规则层既然没看懂这句话，就不该凭"占位意图"给它加分。
    // 但 note/source 必须写清楚，否则界面会出现一条「共情 +0」且理由空白的记录。
    effects: {
      ...cloneEffect(NO_EFFECT),
      note: '这句话未命中本地规则库，已交由语义层判定',
      source: '规则未覆盖 · 由 AI 补判',
    },
    shouldCallAI: true,
  };
}

/* ═══════════════════════════════════════════════════════════
   四、辅助函数
   ═══════════════════════════════════════════════════════════ */

function findHits(text: string, words: string[]): string[] {
  const hits: string[] = [];
  for (const w of words) {
    if (text.includes(w)) hits.push(w);
  }
  return hits;
}

/**
 * 空泛共情检测。
 *
 * 「我理解」本身是合格表达，但后面不接具体内容就是空泛。
 * 判据：共情词后 15 个字符内没有出现任何情感词或情境词。
 */
const CONCRETE_MARKERS = [
  '时候', '那天', '心里', '难受', '辛苦', '不容易', '一个人',
  '撑着', '熬', '怕', '担心', '难', '累', '孤独', '寂寞', '空',
];

function isVagueEmpathy(text: string, empathyWord: string): boolean {
  const idx = text.indexOf(empathyWord);
  if (idx < 0) return false;
  const tail = text.slice(idx + empathyWord.length, idx + empathyWord.length + 15);
  if (tail.trim().length === 0) return true;
  return !CONCRETE_MARKERS.some((m) => tail.includes(m));
}

/**
 * 无望感检测 —— 🟡 关注级。
 *
 * 这是本项目最重要的专业设计之一：
 * 「活着没意思」**不是**危机，「不想活」才是。
 * 两者处理方式完全不同：
 *   无望感 → 引导探索，不拦截（甚至加分）
 *   危机   → 硬拦截，不调 AI
 */
export function checkHopelessness(text: string): RiskLevel {
  const normalized = normalize(text);
  const hits = findHits(normalized, HOPELESSNESS_WORDS);
  if (hits.length > 0) return 'hopelessness';
  // 🔴 危机级的判定不在这里 —— 它必须先于一切（含本函数），
  //    由 matchLocalRules 第 1 步 / crisis.classifyRisk 调 findCrisisHits 完成。
  //    原来这里有一句 `if (findHits(CRISIS_WORDS)) return 'suicidal';`
  //    在 matchLocalRules 内部永远不可达（危机已提前 return），只会误导读者，已删除。
  return 'none';
}

/**
 * 无望感表达后的「毒性正能量」检测。
 *
 * 规则层不能对无望感表达说「别这么想/想开点/您要乐观」——
 * 这会把可探索的信号关掉，比不回应更糟。
 */
export const TOXIC_POSITIVITY_WORDS: string[] = [
  '别想太多', '想开点', '你要乐观', '开心点', '别难过', '没什么大不了',
  '你要坚强', '看开些', '会好起来的',
];

export function isToxicPositivity(rawInput: string): boolean {
  const text = normalize(rawInput);
  return findHits(text, TOXIC_POSITIVITY_WORDS).length > 0;
}

/** 统计词表总条数，用于「关于与声明」页展示 */
export function countRuleWords(): number {
  return (
    EMPATHY_WORDS.length +
    OPEN_QUESTION_WORDS.length +
    CLOSED_QUESTION_SUFFIX.length +
    JUDGE_WORDS.length +
    PREMATURE_ADVICE_WORDS.length +
    SILENCE_ACCOMPANY_WORDS.length +
    OFF_TOPIC_WORDS.length +
    CRISIS_WORDS.length +
    HOPELESSNESS_WORDS.length
  );
}

/** 为「关于与声明」页提供词表明细 */
export function describeRuleTables(): { name: string; count: number; purpose: string }[] {
  return [
    { name: '共情词表', count: EMPATHY_WORDS.length, purpose: '识别接住情绪的表达，区分具体共情与空泛共情' },
    { name: '开放式提问词表', count: OPEN_QUESTION_WORDS.length, purpose: '识别引导展开的提问' },
    { name: '封闭式提问特征表', count: CLOSED_QUESTION_SUFFIX.length, purpose: '识别压缩表达空间的是非题' },
    { name: '评判词黑名单', count: JUDGE_WORDS.length, purpose: '拦截违反非评判原则的说教表达' },
    { name: '建议过早词表', count: PREMATURE_ADVICE_WORDS.length, purpose: '拦截未充分了解就给方案的越界' },
    { name: '沉默陪伴词表', count: SILENCE_ACCOMPANY_WORDS.length, purpose: '识别愿意等待、不催促的回应' },
    { name: '离题词表', count: OFF_TOPIC_WORDS.length, purpose: '识别未接住对方话题的内容' },
    { name: '危机级词表', count: CRISIS_WORDS.length, purpose: '自伤意念硬拦截，永不调用模型' },
    { name: '无望感词表', count: HOPELESSNESS_WORDS.length, purpose: '关注级信号，引导探索而非拦截' },
  ];
}