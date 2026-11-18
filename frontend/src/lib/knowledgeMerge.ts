/**
 * 知识库数据合并
 *
 * 背景：知识库此前只读前端静态文件 `data/knowledge.ts`，而管理端
 * 「内容维护 → 技巧卡」维护的是数据库里的卡。两边同 id 但内容不同，
 * 结果是**管理端改的内容学生永远看不到**——这是个真实缺陷。
 *
 * 合并策略（与项目既有的「基线在代码 + 数据库覆盖」一致，
 * 参见 rule_word_service / script_line_service）：
 * - 数据库为准：id 相同时用数据库的标题与正文，管理端改动立即生效
 * - 静态文件补元数据：dimension / source / practice 这些管理端不管，
 *   但训练页与筛选要用，继续从静态文件取
 * - 数据库独有：管理端新建的卡（静态文件里没有）追加展示，元数据留空
 * - 数据库读不到：整体回落到静态文件，知识库仍可用（同词表降级思路）
 */

export interface StaticSkillCard {
  id: string;
  title: string;
  body: string;
  dimension: string;
  source: string;
  practice: { scenarioId: string };
}

export interface StaticEthic {
  code: string;
  title: string;
  quote: string;
  explanation?: string;
}

/** 后端 /api/v1/knowledge/cards 返回的条目 */
export interface DbCard {
  id: string;
  title: string;
  category: string;
  summary: string;
  content: string;
  tags?: string[];
  stage?: number | null;
}

/** 页面展示用的统一结构 */
export interface DisplayCard {
  id: string;
  title: string;
  text: string;
  category: string;
  /** 六维键，来自静态元数据；数据库独有卡为空 */
  dimension?: string;
  /** 条款来源，来自静态元数据；数据库独有卡为空 */
  source?: string;
  /** 练习入口用的案例 id；数据库独有卡为空 */
  practiceScenarioId?: string;
  /** 该卡是否来自数据库（用于界面上标注「管理端维护」） */
  fromDb: boolean;
}

export interface MergedKnowledge {
  skills: DisplayCard[];
  ethics: DisplayCard[];
  /** 静态文件里有、数据库里没有的 id（提示同步漂移） */
  staticOnlyIds: string[];
  /** 数据库里有、静态文件里没有的 id（管理端新建） */
  dbOnlyIds: string[];
}

function norm(text: string | undefined | null): string {
  return (text ?? '').trim();
}

export function mergeKnowledge(
  staticSkills: StaticSkillCard[],
  staticEthics: StaticEthic[],
  dbCards: DbCard[] | null,
): MergedKnowledge {
  // 数据库不可用：整体回落静态数据，知识库照常可用
  if (!dbCards) {
    return {
      skills: staticSkills.map((c) => ({
        id: c.id,
        title: c.title,
        text: c.body,
        category: '',
        dimension: c.dimension,
        source: c.source,
        practiceScenarioId: c.practice?.scenarioId,
        fromDb: false,
      })),
      ethics: staticEthics.map((e) => ({
        id: e.code,
        title: e.title,
        text: [e.quote, e.explanation].filter(Boolean).join('\n\n'),
        category: '伦理',
        fromDb: false,
      })),
      staticOnlyIds: staticSkills.map((c) => c.id),
      dbOnlyIds: [],
    };
  }

  const dbById = new Map(dbCards.map((c) => [c.id, c]));
  const staticIds = new Set(staticSkills.map((c) => c.id));

  const skills: DisplayCard[] = staticSkills.map((c) => {
    const db = dbById.get(c.id);
    if (!db) {
      return {
        id: c.id,
        title: c.title,
        text: c.body,
        category: '',
        dimension: c.dimension,
        source: c.source,
        practiceScenarioId: c.practice?.scenarioId,
        fromDb: false,
      };
    }
    // 数据库为准：标题与正文用库里的；元数据仍取静态文件
    return {
      id: c.id,
      title: norm(db.title) || c.title,
      text: norm(db.content) || norm(db.summary) || c.body,
      category: db.category,
      dimension: c.dimension,
      source: c.source,
      practiceScenarioId: c.practice?.scenarioId,
      fromDb: true,
    };
  });

  // 管理端新建的卡（静态文件里没有）追加到技巧列表
  const dbOnly = dbCards.filter((c) => !staticIds.has(c.id) && c.category !== '伦理');
  for (const db of dbOnly) {
    skills.push({
      id: db.id,
      title: norm(db.title) || db.id,
      text: norm(db.content) || norm(db.summary),
      category: db.category,
      fromDb: true,
    });
  }

  // 伦理守则：静态基线 + 数据库里 category=伦理 的卡
  const ethics: DisplayCard[] = staticEthics.map((e) => ({
    id: e.code,
    title: e.title,
    text: [e.quote, e.explanation].filter(Boolean).join('\n\n'),
    category: '伦理',
    fromDb: false,
  }));
  for (const db of dbCards) {
    if (db.category !== '伦理') continue;
    ethics.push({
      id: db.id,
      title: norm(db.title) || db.id,
      text: norm(db.content) || norm(db.summary),
      category: '伦理',
      fromDb: true,
    });
  }

  return {
    skills,
    ethics,
    staticOnlyIds: staticSkills
      .filter((c) => !dbById.has(c.id))
      .map((c) => c.id),
    dbOnlyIds: dbCards.filter((c) => !staticIds.has(c.id)).map((c) => c.id),
  };
}
