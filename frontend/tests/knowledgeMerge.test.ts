/**
 * 知识库合并逻辑的单元测试（纯函数，不起服务）。
 *
 * 用 tsx 直接跑 node 断言，不引入测试框架依赖（本项目约定不新增
 * 前端测试依赖）。断言失败会抛错，进程退出码非 0，可被 CI 捕获。
 *
 * 运行：cd frontend && node node_modules/tsx/dist/cli.mjs tests/knowledgeMerge.test.ts
 */
import assert from 'node:assert/strict';
import { mergeKnowledge } from '../src/lib/knowledgeMerge.ts';

const STATIC_SKILLS = [
  {
    id: 'T-01', title: '共情三层次', body: '静态正文',
    dimension: 'empathy', source: '公告第 426 号 · 6.1.1',
    practice: { scenarioId: 'W-01' },
  },
  {
    id: 'T-02', title: '毒性正能量陷阱', body: '静态正文二',
    dimension: 'advice', source: '公告第 426 号 · 6.1.3',
    practice: { scenarioId: 'L-02' },
  },
];
const STATIC_ETHICS = [
  { code: '4.2.1', title: '接纳', quote: '接纳不等于认同', explanation: '解释文本' },
];

let passed = 0;
function check(name: string, fn: () => void) {
  fn();
  passed += 1;
  console.log(`  [PASS] ${name}`);
}

// ① 数据库不可用：整体回落静态数据，知识库仍可用
check('数据库不可用时回落静态数据', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, null);
  assert.equal(m.skills.length, 2);
  assert.equal(m.ethics.length, 1);
  assert.equal(m.skills[0].text, '静态正文');
  assert.equal(m.skills[0].fromDb, false);
});

// ② 数据库为准：同 id 用库里的标题与正文，元数据仍取静态
check('同 id 时数据库内容覆盖静态', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, [
    { id: 'T-01', title: '库里标题', category: '共情',
      summary: '摘要', content: '库里正文', tags: [], stage: 1 },
  ]);
  const t1 = m.skills.find((c) => c.id === 'T-01')!;
  assert.equal(t1.title, '库里标题', '标题应取数据库');
  assert.equal(t1.text, '库里正文', '正文应取数据库');
  assert.equal(t1.dimension, 'empathy', '元数据应保留静态文件的维度');
  assert.equal(t1.source, '公告第 426 号 · 6.1.1');
  assert.equal(t1.practiceScenarioId, 'W-01');
  assert.equal(t1.fromDb, true);
});

// ③ 数据库独有：管理端新建的卡要出现
check('管理端新建的卡追加到列表', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, [
    { id: 'T-99', title: '管理端新卡', category: '技巧',
      summary: '摘要', content: '新卡正文', tags: [], stage: null },
  ]);
  const t99 = m.skills.find((c) => c.id === 'T-99');
  assert.ok(t99, '管理端新建的卡必须出现在列表里');
  assert.equal(t99!.text, '新卡正文');
  assert.deepEqual(m.dbOnlyIds.sort(), ['T-99']);
});

// ④ 静态里有但库里没有：保留展示，并记录漂移
check('静态独有卡仍展示且记录漂移', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, [
    { id: 'T-01', title: '库里标题', category: '共情',
      summary: '', content: '库里正文', tags: [], stage: 1 },
  ]);
  assert.equal(m.skills.length, 2, '静态独有的 T-02 不能丢');
  assert.deepEqual(m.staticOnlyIds, ['T-02']);
});

// ⑤ 伦理页：静态基线 + 数据库里 category=伦理 的卡
check('伦理守则合并数据库伦理卡', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, [
    { id: 'E-01', title: '保密例外', category: '伦理',
      summary: '摘要', content: '伦理正文', tags: [], stage: 2 },
  ]);
  assert.ok(m.ethics.some((e) => e.id === 'E-01'), '数据库伦理卡应出现在伦理页');
  assert.ok(m.ethics.some((e) => e.id === '4.2.1'), '静态伦理守则不能丢');
  assert.equal(
    m.skills.some((c) => c.id === 'E-01'), false,
    '伦理卡不应混进技巧列表',
  );
});

// ⑥ 库里标题为空时回落静态标题（避免管理端误存空串导致白卡）
check('库中空白字段回落静态值', () => {
  const m = mergeKnowledge(STATIC_SKILLS, STATIC_ETHICS, [
    { id: 'T-01', title: '  ', category: '共情',
      summary: '', content: '', tags: [], stage: 1 },
  ]);
  const t1 = m.skills.find((c) => c.id === 'T-01')!;
  assert.equal(t1.title, '共情三层次', '空标题应回落静态标题');
  assert.equal(t1.text, '静态正文', '空正文应回落静态正文');
});

console.log(`\n✅ 知识库合并逻辑 ${passed}/6 通过`);
