/**
 * 引擎冒烟测试 —— 直接 import 真实的 TS 模块
 *
 * 运行：npm run test:engine（tsx 剥离类型，Node 18+ 即可）
 * 测的就是要交付的那份代码，不是编译产物。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { matchLocalRules, normalize, isToxicPositivity, effectsForIntent } from './services/rules.ts';
import { generateReply, selectVariant, matchTopic, selfCheck } from './services/dialogueEngine.ts';
import { isScriptLine } from './data/dialogueTree.ts';
import { DIMENSIONS, weightedTotal, computeRuleScore, mergeScores } from './services/scoring.ts';
import { SCENARIOS } from './data/scenarios.ts';
import { PERSONAS, DIFFICULTY_RULES, buildSystemPrompt } from './data/personas.ts';
import { SKILL_CARDS, ETHICS, RESISTANCE_NOTES } from './data/knowledge.ts';
import { TREES } from './data/dialogueTree.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const readSrc = (p: string) => fs.readFileSync(path.join(HERE, p), 'utf8');

let pass = 0, fail = 0;
const t = (name: string, cond: boolean, got?: unknown) => {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (got !== undefined ? '  → ' + JSON.stringify(got) : '')); }
};

const SC = { id: 'W-01', name: '王阿姨', age: 68, difficulty: 2 } as never;

/* ══════════ 0. 数据完整性 ══════════ */
console.log('=== 0. 数据完整性 ===');
const rulesSrc = readSrc('services/rules.ts');
const tables = ['EMPATHY_WORDS', 'OPEN_QUESTION_WORDS', 'CLOSED_QUESTION_SUFFIX', 'JUDGE_WORDS',
  'PREMATURE_ADVICE_WORDS', 'SILENCE_ACCOMPANY_WORDS', 'OFF_TOPIC_WORDS',
  'CRISIS_WORDS', 'HOPELESSNESS_WORDS'] as const;
const countOf = (n: string) => {
  const m = rulesSrc.match(new RegExp(`const ${n}[^=]*=\\s*\\[([\\s\\S]*?)\\]\\s*;`));
  return m ? (m[1].match(/'/g) || []).length / 2 : 0;
};
t('9 张词表全部非空', tables.every((n) => countOf(n) > 0),
  tables.filter((n) => !countOf(n)));
t('词条总数 ≥ 160', tables.reduce((a, n) => a + countOf(n), 0) >= 160,
  tables.reduce((a, n) => a + countOf(n), 0));
t('角色 12 个', SCENARIOS.length === 12, SCENARIOS.length);
t('persona 12 份且都有系统提示词',
  PERSONAS.length === 12 && PERSONAS.every((p) => p.systemPrompt.length > 200),
  PERSONAS.filter((p) => p.systemPrompt.length <= 200).map((p) => p.id));
t('三档难度规则齐全', Object.keys(DIFFICULTY_RULES).length === 3);
t('buildSystemPrompt 能拼出完整提示词',
  buildSystemPrompt('W-01', '挑战督导', 25).includes('抵触'));
t('台词节点 ≥ 46', Object.values(TREES).reduce((a, b) => a + b.length, 0) >= 46,
  Object.values(TREES).reduce((a, b) => a + b.length, 0));
t('技巧卡 19 张', SKILL_CARDS.length === 19, SKILL_CARDS.length);
t('伦理守则 12 条', ETHICS.length === 12, ETHICS.length);
t('阻抗形态 6 种', RESISTANCE_NOTES.length === 6, RESISTANCE_NOTES.length);
t('六维权重合计 100', DIMENSIONS.reduce((a, d) => a + d.weight, 0) === 100);
t('六维均锚定 公告第 426 号', DIMENSIONS.every((d) => d.source.includes('426')));
t('AI 链路不做业务重试', !/\bretry\b/i.test(readSrc('lib/aiClient.ts')));
t('AI 超时留有推理余量（≥30s）', /timeoutMs\s*=\s*(\d[\d_]*)/.test(readSrc('lib/aiClient.ts'))
  && Number((readSrc('lib/aiClient.ts').match(/timeoutMs\s*=\s*(\d[\d_]*)/) || [])[1].replace(/_/g, '')) >= 30000);
t('服务端显式关闭 thinking', readSrc('../server/glm.mjs').includes("type: 'disabled'"));
t('服务端配置主模型 glm-4.7-flash', readSrc('../server/glm.mjs').includes('glm-4.7-flash'));
t('前端不持有真实密钥', !readSrc('lib/aiClient.ts').includes('Bearer '));

/* ══════════ 1. 敬称归一化 ══════════ */
console.log('\n=== 1. 敬称归一化 ===');
t('「您应该」命中评判（词表只有「你应该」）',
  matchLocalRules('您应该多出去走走').intent === '评判',
  matchLocalRules('您应该多出去走走').intent);
t('「你应该」命中评判', matchLocalRules('你应该多出去走走').intent === '评判');
t('归一化正确', normalize('您自己') === '你自己');

/* ══════════ 2. 离题优先于提问 ══════════ */
console.log('\n=== 2. 离题优先于提问 ===');
t('「你叫什么名字」判离题（含"什么"）',
  matchLocalRules('你叫什么名字').intent === '离题');
t('「外面下雨了吗」判离题（含"吗"）',
  matchLocalRules('外面下雨了吗').intent === '离题');

/* ══════════ 3. 三级风险分级 ══════════ */
console.log('\n=== 3. 三级风险分级 ===');
t('「我不想活了」= 危机级',
  matchLocalRules('我不想活了').riskLevel === 'suicidal');
t('「活着没意思」= 关注级（非危机）',
  matchLocalRules('活着没意思').riskLevel === 'hopelessness');
t('危机级不调 AI', matchLocalRules('我不想活了').shouldCallAI === false);
t('「别想太多」= 毒性正能量', isToxicPositivity('别想太多') === true);

/* ══════════ 4. 八类意图 ══════════ */
console.log('\n=== 4. 八类意图判定 ===');
const INTENTS: [string, string][] = [
  ['我理解你现在一个人撑着很辛苦', '共情'], ['我理解。', '共情'],
  ['那您当时是怎么熬过来的', '开放提问'], ['您是不是也觉得', '封闭提问'],
  ['你应该多出去走走', '评判'], ['我建议你', '建议过早'],
  ['我在这儿听着', '沉默陪伴'], ['我先去上个厕所', '离题'],
  ['我不想活了', '危机'],
];
INTENTS.forEach(([inp, exp]) => {
  t(`「${inp}」→ ${exp}`, matchLocalRules(inp).intent === exp, matchLocalRules(inp).intent);
});

/* ══════════ 5. 规则未覆盖 → 需调 AI ══════════ */
console.log('\n=== 5. 规则未覆盖 → 需调 AI ===');
t('自由表达判为需调 AI', matchLocalRules('夜晚的风有点凉').shouldCallAI === true);

/* ══════════ 6. 话题表 ══════════ */
console.log('\n=== 6. 话题表命中 ===');
([['您平时吃饭是自己做吗？', 'W-04'], ['那您晚上睡得好吗？', 'W-05'],
  ['儿子在外地也帮不上什么忙吧。', 'W-08'], ['社区活动中心在哪', 'W-11'],
  ['您需要什么帮助吗', 'W-09']] as [string, string][]).forEach(([inp, node]) => {
  t(`「${inp.slice(0, 10)}…」→ ${node}`, matchTopic(inp) === node, matchTopic(inp));
});

/* ══════════ 7. 台词白名单 ══════════ */
console.log('\n=== 7. 台词必须来自台词库 ===');
const m7 = matchLocalRules('一个人过日子，夜里确实难熬');
const r7 = generateReply(SC, 3, 55, '一个人过日子，夜里确实难熬', m7);
t('生成台词通过白名单校验', isScriptLine(r7.text, 'W-01') === true, r7.text);
t('话题表命中 W-03（孤单）', r7.nodeId === 'W-03', r7.nodeId);
console.log('        ' + r7.text);

/* ══════════ 8. 情绪值决定变体 ══════════ */
console.log('\n=== 8. 情绪值决定台词变体 ===');
([['25', 'A'], ['50', 'B'], ['80', 'C']] as [string, string][]).forEach(([e, v]) => {
  t(`情绪值 ${e} → 变体 ${v}`, selectVariant(+e) === v);
});
const lo = generateReply(SC, 3, 25, '我理解', matchLocalRules('我理解'));
const hi = generateReply(SC, 3, 80, '我理解', matchLocalRules('我理解'));
t('低/高情绪台词不同', lo.text !== hi.text);
console.log('        25分：' + lo.text);
console.log('        80分：' + hi.text);

/* ══════════ 9. 评判 → 防御台词 ══════════ */
console.log('\n=== 9. 评判 → 防御台词 + 节点不推进 ===');
const r9 = generateReply(SC, 3, 50, '您应该多出去走走', matchLocalRules('您应该多出去走走'));
t('标记为防御台词', r9.hasDefense === true, r9);
t('节点不推进', r9.advanced === false);
t('防御台词通过白名单', isScriptLine(r9.text, 'W-01') === true, r9.text);
console.log('        ' + r9.text);

/* ══════════ 10. 评分链路 ══════════ */
console.log('\n=== 10. 六维评分链路 ===');
const sc = computeRuleScore({
  utterances: [{ text: '我理解你现在一个人撑着很辛苦' }, { text: '您应该多出去走走' }],
  hopelessDetected: false, hopelessRecognized: false,
  totalStages: 3, completedStages: 1,
  scoreAdjust: { empathy: 0, question: 0, advice: 0, ethics: 0, process: 0, risk: 0 },
});
t('评判句拉低伦理原则', sc.ethics < 70, sc.ethics);
t('共情句拉高同感', sc.empathy > 60, sc.empathy);
const total = weightedTotal(sc);
t('综合分在 0-100 之间', total >= 0 && total <= 100, total);
console.log('        ' + DIMENSIONS.map((d) => `${d.name} ${sc[d.key]}`).join('  '));
console.log(`        综合分 ${total}`);

/* ══════════ 11. 回归断言（本轮修复的 6 个误判） ══════════ */
console.log('\n=== 11. 回归断言 ===');

// 11-1 危机词边界：「打我电话」是致电语境，不是危机
t('「你可以打我电话」不判危机', matchLocalRules('你可以打我电话').riskLevel === 'none',
  matchLocalRules('你可以打我电话').riskLevel);
t('「拿刀切菜」不判危机', matchLocalRules('拿刀切菜').riskLevel === 'none',
  matchLocalRules('拿刀切菜').riskLevel);
t('「他打我」仍是危机', matchLocalRules('他打我').riskLevel === 'suicidal',
  matchLocalRules('他打我').riskLevel);

// 11-2 「你怎么…」是标准的开放式追问，不是评判
t('「你怎么看这件事？」判开放提问', matchLocalRules('你怎么看这件事？').intent === '开放提问',
  matchLocalRules('你怎么看这件事？').intent);
t('「你怎么能这样」仍是评判', matchLocalRules('你怎么能这样').intent === '评判',
  matchLocalRules('你怎么能这样').intent);

// 11-3 沉默陪伴不能吞掉无望感
t('「没关系，活着没意思」保留无望感信号',
  matchLocalRules('没关系，活着没意思').riskLevel === 'hopelessness',
  matchLocalRules('没关系，活着没意思').riskLevel);
t('「随便聊聊」不判无望感', matchLocalRules('随便聊聊').riskLevel !== 'hopelessness',
  matchLocalRules('随便聊聊').riskLevel);

// 11-4 AI 覆盖意图后必须带上同口径分值，否则 AI 判出的评判零扣分
t('effectsForIntent(评判) 扣伦理',
  (effectsForIntent('评判').scoreDeltas.ethics ?? 0) < 0,
  effectsForIntent('评判').scoreDeltas);
t('effectsForIntent 与规则层同口径',
  effectsForIntent('共情').emotionDelta === matchLocalRules('我理解您现在的难处').effects.emotionDelta);

// 11-5 AI 六维缺项 / NaN 必须整条降级，不能拼出半张表
const mergeOk = mergeScores(
  { empathy: 60, question: 60, advice: 60, ethics: 60, process: 60, risk: 60 }, null);
t('AI 为空 → 只用规则底分', mergeOk.usedAI === false && mergeOk.scores.empathy === 60);
const mergeBad = mergeScores(
  { empathy: 60, question: 60, advice: 60, ethics: 60, process: 60, risk: 60 },
  { empathy: 80, question: NaN as unknown as number, advice: 80, ethics: 80, process: 80, risk: 80 });
t('AI 有 NaN → 整条降级', mergeBad.usedAI === false && mergeBad.missing.includes('question'),
  mergeBad.missing);
t('weightedTotal 空对象不返回 NaN', Number.isFinite(weightedTotal({} as never)));

// 11-6 危机轮不计分：含危机词的发言不进规则底分
const withCrisis = computeRuleScore({
  utterances: [{ text: '我不想活了' }],
  hopelessDetected: false, hopelessRecognized: false,
  totalStages: 3, completedStages: 1,
  scoreAdjust: { empathy: 0, question: 0, advice: 0, ethics: 0, process: 0, risk: 0 },
});
t('危机轮不进六维底分', withCrisis.ethics === 70 && withCrisis.risk === 60, withCrisis);

/* ══════════ 12. 台词自检 ══════════ */
console.log('\n=== 12. 12 个剧本台词自检 ===');
const self = selfCheck();
const selfBad = self.filter((r) => !r.ok);
t('selfCheck 覆盖 12 个剧本', self.length === 12, self.length);
t('selfCheck 全绿', selfBad.length === 0, selfBad.map((r) => r.scenarioId));
t('纯标点台词通过白名单', isScriptLine('……', 'W-01') === true);

console.log('\n' + '='.repeat(46));
console.log(`通过 ${pass} / ${pass + fail}` + (fail ? `　✗ 有 ${fail} 项失败` : '　全部通过 ✓'));
process.exit(fail ? 1 : 0);
