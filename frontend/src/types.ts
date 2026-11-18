/**
 * 叩门 · 社工个案面谈 AI 陪练舱
 * 类型契约 —— 所有模块的基础，平台的 UI 层必须从这里 import
 *
 * 设计原则：本文件不依赖 React，可独立测试与移植
 */

/* ═══════════════════════════════════════════════════════════
   一、基础枚举
   ═══════════════════════════════════════════════════════════ */

/** 学生意图八类（民政部公告第 426 号 · 6.1 会谈技巧体系） */
export type Intent =
  | '共情' // 接住了服务对象的情绪
  | '开放提问' // 用开放式提问引导展开
  | '封闭提问' // 只能回答是/否的问题
  | '评判' // 评价、指责、说教
  | '建议过早' // 未充分了解就给方案
  | '沉默陪伴' // 愿意等待、不催促
  | '离题' // 与当前话题无关
  | '危机'; // 涉及自伤或他伤 —— 唯一不走 AI 的类别

/** 三级风险分级（本项目最核心的专业设计） */
export type RiskLevel =
  | 'none' // 🟢 无
  | 'hopelessness' // 🟡 关注级：无望感表达，需引导探索，**不拦截**
  | 'suicidal'; // 🔴 危机级：自伤意念，本地硬规则拦截，**不调 AI**

/** 台词情绪变体 —— 由当前情绪值决定 */
export type Variant = 'A' | 'B' | 'C';

/** 消息角色 */
export type Speaker = 'client' | 'worker' | 'system';

/** 消息内的校样标记类型（视觉语言的语义标识，不依赖具体渲染） */
export type ProofMarkKind = 'add' | 'del' | 'caret' | 'margin';

/* ═══════════════════════════════════════════════════════════
   二、六维评分
   ═══════════════════════════════════════════════════════════ */

/** 六个维度的固定 key，顺序即展示顺序 */
export type DimensionKey =
  | 'empathy' // 同感与倾听 25
  | 'question' // 提问与对焦 20
  | 'advice' // 信息提供与建议 15
  | 'ethics' // 伦理原则 20
  | 'process' // 过程完整性 10
  | 'risk'; // 风险识别与转介 10

export interface DimensionMeta {
  key: DimensionKey;
  name: string;
  weight: number;
  /** 国标条款出处，写进界面与 PDF */
  source: string;
  /** 该维度的判定要点，喂给 AI 用 */
  criteria: string;
}

export interface DimensionScore {
  key: DimensionKey;
  /** 0-100 */
  score: number;
  /** 一句理由，不超过 30 字 */
  reason: string;
  /** 该分数由 AI 给出还是规则底平 */
  source: 'ai' | 'rule';
}

/* ═══════════════════════════════════════════════════════════
   三、对话
   ═══════════════════════════════════════════════════════════ */

/** 面谈阶段（内容层 5 阶段，UI 层合并为 3 段） */
export type StageKey = 'rapport' | 'explore' | 'assess' | 'link' | 'close';

export const STAGE_LABELS: Record<StageKey, string> = {
  rapport: '建立关系',
  explore: '问题探索',
  assess: '需求评估',
  link: '资源链接',
  close: '结束约定',
};

/** UI 层的三段（对应 UIPhase 1/2/3） */
export type UIPhase = 1 | 2 | 3;

/** 台词节点：一个节点 × 三个情绪变体 */
export interface DialogueNode {
  /** 节点编号，如 W-06 */
  id: string;
  /** 所属阶段 */
  stage: StageKey;
  /** 触发该节点的建议关键词，用于「话题对照表」 */
  topic?: string[];
  /** 三个情绪变体：A 回避(≤29) / B 平实(30-69) / C 打开(≥70) */
  lines: Record<Variant, string>;
  /** 教学设计意图，不进界面，供答辩与 PDF 使用 */
  intent?: string;
}

/** 剧本元信息 */
export interface Scenario {
  /** 主键 W-01 */
  id: string;
  name: string;
  age: number;
  gender: '男' | '女';
  archetype: string;
  /** 难度 1-5 */
  difficulty: number;
  sensitiveTag: '无' | '含轻度无望感表达' | '含敏感议题';
  brief: string;
  /** 初始情绪值 40-50 */
  initialEmotion: number;
  /** 完整对话树节点数（仅统计用） */
  nodeCount: number;
}

export interface DefenseLine {
  text: string;
  variant: Variant;
  /** 教学意图 */
  intent: string;
}

/* ═══════════════════════════════════════════════════════════
   四、消息与逐句点评
   ═══════════════════════════════════════════════════════════ */

export interface ProofMark {
  kind: ProofMarkKind;
  /** 在原文中的起止下标，用于渲染时切分 */
  start: number;
  end: number;
  /** 该标记关联的维度 */
  dimension?: DimensionKey;
}

export interface ChatMessage {
  id: string;
  speaker: Speaker;
  /** 渲染用文本；原文可能已按 ProofMark 切分 */
  text: string;
  /** 若为防御性追加消息，标签显示「服务对象 · 情绪反应」 */
  isDefense?: boolean;
  /** 危机轮次标记（红框） */
  isCrisis?: boolean;
  /** 命中的校样标记 */
  marks?: ProofMark[];
  /** 若为 AI 建议而非台词库原句 —— 正常情况下永远为 false，用于自检 */
  fromScriptLibrary: boolean;
  createdAt: number;
}

/** 逐句点评 —— 结算页的核心内容 */
export interface MarginNote {
  /** 句序，如 '03' */
  index: string;
  speaker: Speaker;
  /** 学生原话 */
  utterance: string;
  /** 服务对象的回应（若有） */
  response?: string;
  /** 命中的维度 */
  dimension: DimensionKey;
  /** 分值增减，正为加分负为扣分 */
  delta: number;
  /** 触发的规则说明 */
  ruleNote: string;
  /** 国标出处 */
  source: string;
  marks: ProofMark[];
}

/* ═══════════════════════════════════════════════════════════
   五、会话状态
   ═══════════════════════════════════════════════════════════ */

export interface SessionState {
  sessionId: string;
  nickname: string;
  scenarioId: string;
  difficulty: '简单实习' | '标准实训' | '挑战督导';
  /** 无剧透模式：分数打码 */
  blindfold: boolean;
  uiPhase: UIPhase;
  stage: StageKey;
  /** 情绪值 0-100 */
  emotion: number;
  /** 对话轮次（从 1 开始） */
  turn: number;
  /** 本阶段内出现评判的次数，用于「建议过早」特判 */
  judgeCount: number;
  /** 累积的分值调整（用于规则底分） */
  scoreAdjust: Record<DimensionKey, number>;
  startedAt: number;
  /** 已提交过的阶段 */
  submittedPhases: UIPhase[];
}

export interface TrainingRecord {
  recordId: string;
  nickname: string;
  scriptId: string;
  scriptName: string;
  difficulty: string;
  blindfold: boolean;
  stageNo: number;
  scoreEmpathy: number;
  scoreQuestion: number;
  scoreAdvice: number;
  scoreEthics: number;
  scoreProcess: number;
  scoreRisk: number;
  scoreTotal: number;
  durationSec: number;
  createdAt: string;
}

/* ═══════════════════════════════════════════════════════════
   六、AI 链路
   ═══════════════════════════════════════════════════════════ */

export interface AIResult<T> {
  ok: boolean;
  data: T | null;
  /** 失败原因，用于界面降级标注 */
  failReason?: string;
}

export interface AIUsage {
  chain: 'intent' | 'stageGrade' | 'debrief';
  usedAI: boolean;
  /** 本次是否消耗了秒点 */
  consumedCredit: boolean;
}

export interface DebriefReport {
  /** 三段：做得好 / 需改进 / 下一步 */
  strength: string;
  improvement: string;
  nextStep: string;
  /** 由 AI 生成还是模板降级 */
  source: 'ai' | 'template';
}

export interface CrisisCardContent {
  level: RiskLevel;
  title: string;
  principles: string[];
  hotlines: { code: string; label: string }[];
  citation: string;
  disclaimer: string;
}

/* ═══════════════════════════════════════════════════════════
   七、无剧透模式
   ═══════════════════════════════════════════════════════════ */

/** 开启无剧透时，界面把分数替换成灰块 */
export const BLINDFOLD_MASK = '•••';