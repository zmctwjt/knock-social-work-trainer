/**
 * 12 个服务对象剧本元数据
 *
 * ⚠️ 本文件由 build_v17.py 从 personas.ts 自动生成，请勿手改。
 * 角色的人设、阻抗形态、说话风格在 personas.ts，这里只放元信息。
 */

import type { Scenario } from '../types.ts';
import { isServerScenario, lookupScenario } from './scenarioRegistry.ts';

export const SCENARIOS: Scenario[] = [
  {
    id: 'W-01',
    name: '王阿姨',
    age: 68,
    gender: '女',
    archetype: '空巢老人',
    difficulty: 2,
    sensitiveTag: '含轻度无望感表达',
    brief: '老伴去世三年，独子在外省工作。主诉：睡眠差、反复表达"活着没意思"。',
    initialEmotion: 45,
    nodeCount: 16,
  },
  {
    id: 'L-02',
    name: '李女士',
    age: 35,
    gender: '女',
    archetype: '单亲母亲',
    difficulty: 3,
    sensitiveTag: '无',
    brief: '离婚两年，独自抚养 8 岁儿子。主诉：经济压力、亲子冲突、前夫拖欠抚养费。',
    initialEmotion: 50,
    nodeCount: 16,
  },
  {
    id: 'C-03',
    name: '小陈',
    age: 15,
    gender: '男',
    archetype: '厌学青少年',
    difficulty: 4,
    sensitiveTag: '无',
    brief: '初二休学在家，每天打游戏到凌晨。与父母冲突加剧。应答极短，常只回单字。',
    initialEmotion: 30,
    nodeCount: 16,
  },
  {
    id: 'Z-04',
    name: '赵先生',
    age: 42,
    gender: '男',
    archetype: '肢体残障',
    difficulty: 4,
    sensitiveTag: '含敏感议题',
    brief: '工伤后轮椅出行，求职受挫。对"同情"极度敏感，一句"你真不容易"就会关闭对话。',
    initialEmotion: 35,
    nodeCount: 16,
  },
  {
    id: 'U-05',
    name: '刘哥',
    age: 48,
    gender: '男',
    archetype: '失业中年',
    difficulty: 3,
    sensitiveTag: '无',
    brief: '原机械厂技术工人，厂子倒闭半年。嘴上说"我自己能解决"，实际很难。自尊心受损。',
    initialEmotion: 40,
    nodeCount: 16,
  },
  {
    id: 'A-06',
    name: '阿珍',
    age: 30,
    gender: '女',
    archetype: '家暴受暴者',
    difficulty: 5,
    sensitiveTag: '含敏感议题',
    brief: '反复说"也没那么严重""他也是偶尔"。否认与反复淡化是典型反应，不是不配合。',
    initialEmotion: 35,
    nodeCount: 16,
  },
  {
    id: 'G-07',
    name: '王奶奶',
    age: 81,
    gender: '女',
    archetype: '失能老人家庭照护者',
    difficulty: 3,
    sensitiveTag: '无',
    brief: '照顾失能母亲半年，主诉"我快撑不住了"。长期照护者最容易被忽略的一类。',
    initialEmotion: 40,
    nodeCount: 16,
  },
  {
    id: 'M-08',
    name: '马同学',
    age: 19,
    gender: '女',
    archetype: '青少年厌学（网络成瘾）',
    difficulty: 4,
    sensitiveTag: '无',
    brief: '大一退学，网瘾严重。与远程管理的母亲每日争吵。',
    initialEmotion: 35,
    nodeCount: 16,
  },
  {
    id: 'B-09',
    name: '老周',
    age: 62,
    gender: '男',
    archetype: '社区矫正对象',
    difficulty: 5,
    sensitiveTag: '含敏感议题',
    brief: '刑满释放半年，找工作屡次碰壁。社区社会工作师跟踪服务。',
    initialEmotion: 30,
    nodeCount: 16,
  },
  {
    id: 'F-10',
    name: '林女士',
    age: 29,
    gender: '女',
    archetype: '移民新居民',
    difficulty: 3,
    sensitiveTag: '无',
    brief: '来自四川，在本地工作五年。普通话不流利，社工上门时她反复说"我听得懂"。',
    initialEmotion: 45,
    nodeCount: 16,
  },
  {
    id: 'S-11',
    name: '老陈',
    age: 55,
    gender: '男',
    archetype: '退役军人',
    difficulty: 4,
    sensitiveTag: '无',
    brief: '退役十年，单位改制后转岗不顺。反复说"我挺好的"，回避退役身份。',
    initialEmotion: 40,
    nodeCount: 16,
  },
  {
    id: 'H-12',
    name: '小雨',
    age: 22,
    gender: '女',
    archetype: '在校心理求助者',
    difficulty: 2,
    sensitiveTag: '含轻度无望感表达',
    brief: '大三在读，因失眠与注意力问题求助。典型的"最小化自己问题"表达。',
    initialEmotion: 48,
    nodeCount: 16,
  }
];

export function getScenario(id: string): Scenario | undefined {
  const hit = SCENARIOS.find((s) => s.id === id);
  if (hit) return hit;
  // 教师/管理员在「案例管理」里自建的角色：查服务端注册表。
  // 绝不静默回退到别的内置角色 —— 那会让新角色说着别人的台词。
  const server = lookupScenario(id);
  if (!server) return undefined;
  return {
    id: server.id,
    name: server.name,
    age: server.age,
    gender: server.gender,
    archetype: server.archetype,
    difficulty: server.difficulty,
    difficultyLabel: '',
    resistance: '',
    sensitiveTag: server.sensitive_tag ?? '无',
    brief: server.brief,
    initialEmotion: 45,
    nodeCount: 0,
    systemPrompt: '',
  } as unknown as Scenario;
}

/** 判断 id 是否为已知剧本（内置或自定义）—— 路由守卫用 */
export function isKnownScenario(id: string): boolean {
  return SCENARIOS.some((s) => s.id === id) || isServerScenario(id);
}

/** 阻抗形态速查（讲解用） */
export const RESISTANCE_PATTERNS = [
  { key: 'polite-avoidance', name: '客气回避', tell: '"我挺好的""不用管我"' },
  { key: 'alliance-seeking', name: '情绪拉同盟', tell: '"你说他是不是太不是人了？"' },
  { key: 'high-coldness', name: '高冷淡漠', tell: '连续三轮以上只回单字' },
  { key: 'pity-sensitive', name: '对同情敏感', tell: '"可怜""可惜""你真不容易"' },
  { key: 'tough-denial', name: '逞强式否认', tell: '"我自己能解决""不用了"' },
  { key: 'denial-denial', name: '否认与反复淡化', tell: '"也没那么严重""他也是偶尔"' },
  { key: 'caregiver-burnout', name: '照护者耗竭', tell: '报喜不报忧，长期睡不好' },
  { key: 'stigma-avoidance', name: '污名回避', tell: '怕被贴标签，先问"你们是来检查的吗"' },
  { key: 'language-barrier', name: '语言与身份壁垒', tell: '"我听得懂的""我晓得"' },
];
