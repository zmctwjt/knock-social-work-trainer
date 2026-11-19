/**
 * 对话引擎 —— 台词选择、节点推进、情绪值状态机
 *
 * 三条不可违背的规则：
 * 1. 服务对象的每一句回复必须来自台词库，禁止 AI 生成或字符串拼接
 * 2. 台词选择优先级：话题对照表 > 意图是否推进 > 轮次顺序
 * 3. 判定为评判/建议过早/离题/封闭提问时，节点不推进
 */

import type { Intent, StageKey, Variant, Scenario, DialogueNode } from '../types.ts';
import {
  TREES,
  getTree,
  DEFENSE_LINES,
  AZHEN_DETAIL_AVOID,
  isScriptLine,
} from '../data/dialogueTree.ts';
import { normalize, matchLocalRules, type MatchResult } from './rules.ts';

/* ═══════════════════════════════════════════════════════════
   一、情绪值与变体
   ═══════════════════════════════════════════════════════════ */

export const EMOTION_MIN = 0;
export const EMOTION_MAX = 100;

/** 按情绪值选择台词变体 */
export function selectVariant(emotion: number): Variant {
  if (emotion < 30) return 'A'; // 回避、防备
  if (emotion < 70) return 'B'; // 平实、试探
  return 'C'; // 打开、愿意说
}

export function emotionLabel(emotion: number): string {
  if (emotion < 30) return '抵触';
  if (emotion < 70) return '观望';
  return '开放';
}

export function clampEmotion(v: number): number {
  return Math.max(EMOTION_MIN, Math.min(EMOTION_MAX, v));
}

/* ═══════════════════════════════════════════════════════════
   二、话题对照表
   优先级高于轮次：学生问什么，服务对象就答什么
   ═══════════════════════════════════════════════════════════ */

/** 学生消息中的关键词 → 目标节点 id（合并后：一个关键词可指向多位角色的节点） */
export const TOPIC_TABLE: Record<string, string[]> = {
  // 王阿姨 · 阶段一
  '吃': ['W-04'],
  '饭': ['W-04'],
  '做菜': ['W-04'],
  '三餐': ['W-04'],
  '睡': ['W-05'],
  '失眠': ['W-05'],
  '睡不着': ['W-05'],
  '几点睡': ['W-05'],
  '儿子': ['W-08'],
  '孩子': ['W-08'],
  '家人': ['W-08'],
  '亲戚': ['W-08'],
  '国外': ['W-08'],
  '外地': ['W-08'],
  '邻居': ['W-08'],
  '朋友': ['W-08'],
  '来往': ['W-08'],
  '一个人': ['W-03'],
  '孤单': ['W-03'],
  '寂寞': ['W-03'],
  '没人': ['W-03'],
  '活着没意思': ['W-06'],
  '没意思': ['W-06'],
  '没盼头': ['W-06'],
  '没指望': ['W-06'],
  '绝望': ['W-06'],
  // 王阿姨 · 阶段二
  '社区': ['W-11'],
  '活动': ['W-11'],
  '中心': ['W-11'],
  '出门': ['W-11'],
  '需要': ['W-09'],
  '想要': ['W-09'],
  '希望': ['W-09'],
  '怕': ['W-13'],
  '担心': ['W-13'],
  '不好意思': ['W-13'],
  '顾虑': ['W-13'],
  '陪': ['W-12'],
  '一起': ['W-12'],
  // 王阿姨 · 阶段三
  '下次': ['W-15'],
  '以后': ['W-15'],
  '还会': ['W-15'],
  '再来': ['W-15'],
  // 李女士
  '抚养费': ['L-02'],
  '顶嘴': ['L-04'],
  '成绩': ['L-04'],
  // 小陈
  '游戏': ['C-02'],
  '上学': ['C-03'],
  '学校': ['C-03'],
  '打架': ['C-04'],
  '转学': ['C-05'],
  '换学校': ['C-05'],
  // 赵先生
  '可怜': ['Z-02'],
  '可惜': ['Z-02'],
  '不容易': ['Z-02'],
  '坚强': ['Z-02'],
  '工作': ['Z-04'],
  '面试': ['Z-04'],
  '招聘': ['Z-04'],
  // 刘哥
  '厂': ['U-03'],
  '失业': ['U-03'],
  '老婆': ['U-04'],
  // 阿珍
  '保密': ['A-02'],
  '不说出去': ['A-02'],
  '吵架': ['A-04'],
  '矛盾': ['A-04'],
};

/**
 * 后六位角色的话题关键词补充（G-07 / M-08 / B-09 / F-10 / S-11 / H-12）。
 *
 * 原表 66 个关键词只指向 W/L/C/Z/U/A 六棵树，这六位角色的命中率是 0 ——
 * 学生问「你女儿呢」，G-07 只能按轮次答「累是累点」，完全不接话题。
 * 这里按各自台词内容补关键词；同一个关键词可以指向多位角色的节点
 * （如「睡」→ G-03 / M-06 / S-07 / H-04），实际命中哪棵树由 matchTopic 的剧本参数筛。
 */
const TOPIC_TABLE_SIX: Record<string, string[]> = {
  // ── G-07 王奶奶 · 失能老人照护者 ──
  '照顾': ['G-02'],
  '母亲': ['G-02'],
  '妈妈': ['G-02', 'M-05'],
  '认不得': ['G-02'],
  '女儿': ['G-05'],
  '子女': ['G-05'],
  '上海': ['G-05'],
  '睡眠': ['G-03'],
  '睡整觉': ['G-03'],
  '晚上': ['G-03', 'S-07'],
  '累': ['G-04', 'F-05'],
  '辛苦': ['G-04', 'F-05'],
  '多久': ['G-06', 'B-07', 'H-05'],
  '吃饭': ['G-07'],
  '护工': ['G-10'],
  '家政': ['G-10'],
  '上门': ['G-10'],
  // ── M-08 马同学 · 青少年厌学（网络成瘾）──
  '退学': ['M-03'],
  '大学': ['M-03'],
  '培训': ['M-10'],
  '技能': ['M-10'],
  '电竞': ['M-10'],
  '打算': ['M-08', 'S-08'],
  '白天': ['M-06'],
  '线上': ['M-07'],
  '无畏契约': ['M-02'],
  '玩什么': ['M-02', 'C-02'],
  '平时做什么': ['M-02'],
  '网上的朋友': ['M-07'],
  '宿舍': ['M-04'],
  // ── B-09 老周 · 社区矫正对象 ──
  '记录': ['B-02'],
  '报上去': ['B-02'],
  '检查我': ['B-01'],
  '街坊': ['B-05'],
  '熟人': ['B-05'],
  '出来': ['B-07'],
  '单位': ['B-10', 'S-04'],
  '企业': ['B-10'],
  '推荐': ['B-10'],
  '介绍': ['B-10'],
  '了解': ['B-11', 'S-11'],
  '手艺': ['B-08'],
  // ── F-10 林女士 · 移民新居民 ──
  '老家': ['F-02'],
  '哪里': ['F-02'],
  '来多久': ['F-02'],
  '四川': ['F-02'],
  '普通话': ['F-01'],
  '娃': ['F-03', 'F-10'],
  '带娃': ['F-03'],
  '超市': ['F-04'],
  '上班': ['F-04'],
  '理货': ['F-04'],
  '做什么': ['F-04', 'S-03'],
  '房子': ['F-07'],
  '租房': ['F-07'],
  // ── S-11 老陈 · 退役军人 ──
  '部队': ['S-02'],
  '当兵': ['S-02'],
  '停车场': ['S-03'],
  '看车': ['S-03'],
  '改制': ['S-04'],
  '下岗': ['S-04'],
  '心里': ['S-05'],
  '难受': ['S-05'],
  '感觉': ['S-05'],
  '老兵': ['S-10'],
  '志愿': ['S-10'],
  // ── H-12 小雨 · 在校心理求助者 ──
  '状态': ['H-03'],
  '状态往下': ['H-03'],
  '学习': ['H-06'],
  '上课': ['H-06'],
  '注意力': ['H-06'],
  '咨询': ['H-10'],
  '医生': ['H-10'],
  '检查': ['H-10'],
  '预约': ['H-11'],
  '作息': ['H-04'],
  '想太多': ['H-07'],
};

// 合并进同一张话题表：共享关键词（「睡」「孩子」「下次」…）把各角色的节点并列，
// 用 matchTopic 的 scenarioId 参数筛出本剧本真正存在的那一个。
// 合并前先记下主线关键词：不给 scenarioId 时（smoke_test / 旧调用方）
// 只认主线表，保持「饭 → W-04」这类历史行为不变。
const TOPIC_KEYS_BASE = Object.keys(TOPIC_TABLE).sort((a, b) => b.length - a.length);

for (const [k, ids] of Object.entries(TOPIC_TABLE_SIX)) {
  TOPIC_TABLE[k] = [...(TOPIC_TABLE[k] ?? []), ...ids];
}

/** 含后六位角色的全量关键词，按长度倒序（「睡不着」必须先于「睡」） */
const TOPIC_KEYS_ALL = Object.keys(TOPIC_TABLE).sort((a, b) => b.length - a.length);

/**
 * 话题对照表查找。
 *
 * @param input      学生原话
 * @param scenarioId 当前剧本。给了就只返回**该剧本树里真实存在**的节点：
 *                   ① 先扫树内各节点自带的 topic 标注（角色自己的关键词最准）
 *                   ② 再扫全局话题表，跳过属于别的角色的节点
 *                   不给则保持旧行为（全局表长词优先），供 smoke_test 直接调用。
 * @returns 命中的目标节点 id，未命中返回 null
 */
export function matchTopic(input: string, scenarioId?: string): string | null {
  const text = normalize(input);
  const tree = scenarioId ? getTree(scenarioId) : null;

  // ① 树内 topic 标注（G/M/B/F/S/H 六棵树的节点本来就有 topic，只是过去没人用）
  if (tree) {
    const fromTree = matchTreeTopic(text, tree);
    if (fromTree) return fromTree;
  }

  // ② 全局话题表：长词优先，给剧本时只认本树存在的节点
  const keys = tree ? TOPIC_KEYS_ALL : TOPIC_KEYS_BASE;
  for (const k of keys) {
    if (!text.includes(k)) continue;
    for (const id of TOPIC_TABLE[k]) {
      if (!tree || tree.some((n) => n.id === id)) return id;
    }
  }
  return null;
}

/**
 * 树内 topic 里大量出现「怎么样 / 最近 / 什么时候」这类泛化疑问词，
 * 它们几乎每棵树都有。若让泛化词和「注意力」「护工」同样权重，
 * 「最近注意力怎么样」会先命中「怎么样」而答成状态总览。
 * 因此排序时：具体词优先 > 长词优先 > 节点顺序稳定。
 */
const GENERIC_TOPIC = new Set([
  '怎么样', '最近', '什么时候', '哪里', '做什么', '想', '先', '试', '看',
]);

/** 在剧本台词树的 topic 标注里找最合适的一个 */
function matchTreeTopic(text: string, tree: DialogueNode[]): string | null {
  const pairs: { keyword: string; id: string }[] = [];
  for (const node of tree) {
    if (!node.topic || node.topic.length === 0) continue;
    for (const keyword of node.topic) pairs.push({ keyword, id: node.id });
  }
  const generic = (k: string) => (GENERIC_TOPIC.has(k) ? 1 : 0);
  pairs.sort((a, b) => {
    if (generic(a.keyword) !== generic(b.keyword)) return generic(a.keyword) - generic(b.keyword);
    return b.keyword.length - a.keyword.length;
  });
  for (const p of pairs) if (text.includes(p.keyword)) return p.id;
  return null;
}

/* ═══════════════════════════════════════════════════════════
   三、意图与节点推进
   ═══════════════════════════════════════════════════════════ */

/** 这些意图推进对话节点（其余意图一律不推进） */
const ADVANCING: Intent[] = ['共情', '开放提问', '沉默陪伴'];

/** 判定某意图是否推进节点。原来还并排维护了一份 NON_ADVANCING，
 *  但没有任何读者、且与 ADVANCING 反向重复，删掉避免改一处漏一处。 */
export function shouldAdvance(intent: Intent): boolean {
  return ADVANCING.includes(intent);
}

/* ═══════════════════════════════════════════════════════════
   四、阿珍专属：追问细节检测
   ⚠️ 这是社工实务的专业要求：不追问暴力细节
   ═══════════════════════════════════════════════════════════ */

const DETAIL_PROBE_WORDS = ['具体', '怎么打', '伤在哪', '受伤', '淤青', '报警了吗', '验伤'];

function isDetailProbe(input: string): boolean {
  const text = normalize(input);
  return DETAIL_PROBE_WORDS.some((w) => text.includes(w));
}

/* ═══════════════════════════════════════════════════════════
   五、核心：生成服务对象的回复
   ═══════════════════════════════════════════════════════════ */

export interface ReplyResult {
  /** 服务对象说的话 —— 保证来自台词库 */
  text: string;
  /** 命中的节点 */
  nodeId: string;
  /** 台词来源，用于自检 */
  fromScriptLibrary: boolean;
  /** 是否追加了防御性台词 */
  hasDefense: boolean;
  /** 本轮是否推进了节点 */
  advanced: boolean;
  /** 是否需要调用 AI（规则未覆盖时为 true） */
  needIntentFromAI: boolean;
  /** 本地规则判定结果 */
  localMatch: MatchResult;
  /** 是否属于风险轮次 */
  isCrisis: boolean;
}

/**
 * 生成服务对象对一轮学生发言的回应。
 *
 * @param scenario 当前剧本
 * @param turn     当前轮次（从 1 开始）
 * @param emotion  当前情绪值
 * @param input    学生原始输入
 * @param match    本地规则判定结果
 * @param opts     可选：`stage` 显式指定当前面谈阶段，用于「未命中话题表」时的回退。
 *                 分阶段推进的调用方（turn 会按阶段重置）传它才能保证回退到本阶段，
 *                 不传则退回按 turn 推断。
 */
export function generateReply(
  scenario: Scenario,
  turn: number,
  emotion: number,
  input: string,
  match: MatchResult,
  opts?: { stage?: StageKey }
): ReplyResult {
  const tree = getTree(scenario.id);
  if (!tree || tree.length === 0) {
    // 理论上不会走到这里（getTree 已保证非空），留一道保险
    return {
      text: '……', nodeId: 'X-01',
      fromScriptLibrary: true, hasDefense: false, advanced: false,
      needIntentFromAI: false,
      localMatch: matchLocalRules(''),
      isCrisis: false,
    };
  }
  const variant = selectVariant(emotion);
  const intent = match.intent;

  // ── 危机级：不生成任何台词，由界面显示危机卡 ──
  if (match.riskLevel === 'suicidal' || intent === '危机') {
    return {
      text: '',
      nodeId: '',
      fromScriptLibrary: true,
      hasDefense: false,
      advanced: false,
      needIntentFromAI: false,
      localMatch: match,
      isCrisis: true,
    };
  }

  // ── 阿珍：追问细节时回避，不推进 ──
  if (scenario.id === 'A-06' && isDetailProbe(input)) {
    return {
      text: AZHEN_DETAIL_AVOID[variant],
      nodeId: 'A-04',
      fromScriptLibrary: true,
      hasDefense: false,
      advanced: false,
      needIntentFromAI: false,
      localMatch: match,
      isCrisis: false,
    };
  }

  // ── 评判 / 建议过早：当前节点台词 + 追加防御性台词 ──
  if (intent === '评判' || intent === '建议过早') {
    const node = nodeAt(tree, turn);
    const defensePool = DEFENSE_LINES.map((d) => d.text);
    const defense = defensePool[Math.min(Math.floor(emotion / 35), 2)];
    return {
      text: `${node.lines[variant]} ${defense}`,
      nodeId: node.id,
      fromScriptLibrary: true,
      hasDefense: true,
      advanced: false,
      needIntentFromAI: false,
      localMatch: match,
      isCrisis: false,
    };
  }

  // ── 离题：不推进，回当前节点的较防御变体 ──
  if (intent === '离题') {
    const node = nodeAt(tree, turn);
    return {
      text: node.lines[emotion < 70 ? 'A' : variant],
      nodeId: node.id,
      fromScriptLibrary: true,
      hasDefense: false,
      advanced: false,
      needIntentFromAI: false,
      localMatch: match,
      isCrisis: false,
    };
  }

  // ── 话题对照表优先（带剧本筛选，并限制越级跳）──
  const topicNodeId = matchTopic(input, scenario.id);
  if (topicNodeId) {
    const targetIdx = tree.findIndex((n) => n.id === topicNodeId);
    if (targetIdx >= 0) {
      const topicNode = tree[capReachableIndex(targetIdx, turn, tree.length)];
      return {
        text: topicNode.lines[variant],
        nodeId: topicNode.id,
        fromScriptLibrary: true,
        hasDefense: false,
        advanced: true,
        needIntentFromAI: false,
        localMatch: match,
        isCrisis: false,
      };
    }
  }

  // ── 未命中话题表：回退到「当前 stage 的合适节点」，而不是永远从第一个节点起算 ──
  const advanced = shouldAdvance(intent);
  const node = stageFallbackNode(tree, turn, advanced, opts?.stage);
  return {
    text: node.lines[variant],
    nodeId: node.id,
    fromScriptLibrary: true,
    hasDefense: false,
    advanced,
    needIntentFromAI: false,
    localMatch: match,
    isCrisis: false,
  };
}

function nodeAt(tree: DialogueNode[], turn: number): DialogueNode {
  const idx = Math.max(0, Math.min(turn - 1, tree.length - 1));
  return tree[idx];
}

/**
 * 话题跳转的可达上限：目标节点序号不得超过 turn + 3（下标 turn + 2）。
 *
 * 为什么需要：命中话题表就能任意跳，turn=1 说一句「下次」会直达 W-15 结案，
 * 一次面谈被一句话跳到收尾。超出时取最近的可达节点（turn + 2 位置）。
 */
function capReachableIndex(targetIdx: number, turn: number, treeLength: number): number {
  const maxIdx = Math.min(treeLength - 1, Math.max(0, turn + 2));
  return Math.min(targetIdx, maxIdx);
}

/**
 * 未命中话题表时的回退 —— 取「当前 stage 的合适节点」。
 *
 * 原实现是 tree[turn+1]（纯下标推进）。问题在于 turn 是**轮次**不是**节点游标**：
 * 阶段切换时调用方会把 turn 重置为 1，下标推进就把人拉回建立关系阶段的第一句，
 * 于是「不管聊到哪都像重新开场」。这里按 stage 定位：先在本阶段内往后走，
 * 本阶段走完再顺延到下一阶段首节点。
 *
 * @param stageOverride 调用方若知道当前阶段（如分阶段推进的 UI），可直接指定；
 *                      不传则从 turn 对应的节点推。
 */
function stageFallbackNode(
  tree: DialogueNode[],
  turn: number,
  allowAdvance: boolean,
  stageOverride?: StageKey,
): DialogueNode {
  const current = nodeAt(tree, turn);
  const curIdx = tree.indexOf(current);
  const stage = stageOverride ?? current.stage;

  if (stageOverride && stageOverride !== current.stage) {
    // 明确指定了别的阶段：直接取该阶段首/末节点
    const inStage = tree.filter((n) => n.stage === stage);
    if (inStage.length > 0) return allowAdvance ? inStage[0] : inStage[inStage.length - 1];
    return current;
  }

  const stageNodes: { n: DialogueNode; i: number }[] = [];
  tree.forEach((n, i) => {
    if (n.stage === stage) stageNodes.push({ n, i });
  });
  if (stageNodes.length === 0) return current;

  if (!allowAdvance) {
    // 不推进：停在 stage 内不晚于当前节点的最后一句
    const atOrBefore = stageNodes.filter((x) => x.i <= curIdx);
    return (atOrBefore[atOrBefore.length - 1] ?? stageNodes[0]).n;
  }

  // 推进：优先本阶段内的下一个节点
  const ahead = stageNodes.find((x) => x.i > curIdx);
  if (ahead) return ahead.n;

  // 本阶段已到末尾 → 进入下一阶段的首个节点
  const next = tree.find((n, i) => i > curIdx && n.stage !== stage);
  return next ?? stageNodes[stageNodes.length - 1].n;
}

/* ═══════════════════════════════════════════════════════════
   六、自检：确保输出确实来自台词库
   ═══════════════════════════════════════════════════════════ */

/**
 * 上线前的自检函数。建议在开发模式下对全部剧本跑一遍，
 * 验证 generateReply 的任何输入组合都不会产出台词库之外的文本。
 */
export function selfCheck(): { scenarioId: string; ok: boolean; bad: string[] }[] {
  const results: { scenarioId: string; ok: boolean; bad: string[] }[] = [];
  for (const sid of Object.keys(TREES)) {
    const bad: string[] = [];
    const probes = [
      '我理解', '您理解', '我理解你现在很辛苦', '我理解该怎么做',
      '您是不是也觉得这个事没那么简单', '我理解但是我觉得你应该去看看',
      '我先去上个厕所', '我在这儿听着', '一个人过日子夜里确实难熬',
      '睡不着', '儿子在外地', '活着没意思', '需要帮助', '社区活动',
      '下次还来', '你叫什么名字', '外面下雨了吗', '',
    ];
    for (const p of probes) {
      const m = matchLocalRules(p);
      const sc = { id: sid } as Scenario;
      for (const emotion of [20, 50, 80]) {
        const r = generateReply(sc, 3, emotion, p, m);
        // ⚠️ 必须校验整句，不能只取 split(' ')[0]：
        //    评判/建议过早会在节点台词后追加「 防御台词」，
        //    只查前半句等于放过了真正可能出问题的那半句。
        //    isScriptLine 内部已按「 」切分并逐段比对白名单。
        if (r.text && !isScriptLine(r.text, sid)) {
          bad.push(`emotion=${emotion} input="${p}" → "${r.text}"`);
        }
      }
    }
    results.push({ scenarioId: sid, ok: bad.length === 0, bad });
  }
  return results;
}