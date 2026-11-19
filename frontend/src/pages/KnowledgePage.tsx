/**
 * 07 知识库 —— 技巧卡 + 伦理守则 + 判定词表
 *
 * 任务书要求「支持按案例与关键词检索」，因此提供三类筛选：
 * 关键词（标题/正文/条款来源）、案例（该卡对应哪类服务对象）、维度（六维能力）。
 * 三者可叠加，命中数实时显示。
 *
 * 判定词表来自 `/api/v1/rule-words`：任务书要求学员能
 * "查阅技巧卡、伦理守则与判定词表"，管理端那份只给维护者看数量，
 * 学员要看具体词条才知道哪些表达会被判为评判、建议过早。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { DIMENSIONS } from '../services/scoring.ts';
import { SCENARIOS } from '../data/scenarios.ts';
import { useTabKeys } from '../lib/useTabKeys.ts';
import { apiGet } from '../lib/authClient.ts';
import { mergeKnowledge, type DbCard } from '../lib/knowledgeMerge.ts';

/** 判定词表分组（/api/v1/rule-words 返回结构） */
interface WordGroup {
  group: string;
  label: string;
  words: string[];
  count: number;
  protected: boolean;
}

export default function KnowledgePage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<'skill' | 'ethic' | 'word'>('skill');
  // 三个标签，按 WAI-ARIA tabs 模式支持方向键切换
  const onTabKeyDown = useTabKeys(
    [
      { key: 'skill' as const },
      { key: 'ethic' as const },
      { key: 'word' as const },
    ],
    tab,
    setTab,
  );
  const [q, setQ] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [dimension, setDimension] = useState('');
  const [dbCards, setDbCards] = useState<DbCard[] | null>(null);

  // 管理端维护的技巧卡在数据库里；拉不到就回落静态文件，知识库仍可用
  useEffect(() => {
    void apiGet<{ items: DbCard[] }>('/api/v1/knowledge/cards').then((r) => {
      setDbCards(r?.items ?? null);
    });
  }, []);

  // 判定词表（公开只读接口）：任务书要求学员能"查阅技巧卡、伦理守则与判定词表"
  const [wordbook, setWordbook] = useState<WordGroup[] | null>(null);
  useEffect(() => {
    void apiGet<{ groups: WordGroup[] }>('/api/v1/rule-words').then((r) => {
      setWordbook(r?.groups ?? null);
    });
  }, []);
  const wordTotal = (wordbook ?? []).reduce((n, g) => n + g.count, 0);

  // 数据库为准 + 静态补元数据（详见 lib/knowledgeMerge.ts 顶部说明）
  const merged = useMemo(
    () => mergeKnowledge(SKILL_CARDS, ETHICS, dbCards),
    [dbCards],
  );

  const kw = q.trim();
  const dimName = (k?: string) => (k ? (DIMENSIONS.find((d) => d.key === k)?.name ?? k) : '');

  /** 找到某卡对应案例的姓名，用于卡片上显示"适用案例" */
  const scenarioName = (id?: string) =>
    id ? (SCENARIOS.find((s) => s.id === id)?.name ?? id) : '';

  const skills = useMemo(() => merged.skills.filter((c) => {
    if (kw
      && !c.title.includes(kw)
      && !c.text.includes(kw)
      && !(c.source || '').includes(kw)
      && !(c.category || '').includes(kw)) {
      return false;
    }
    if (scenarioId && c.practiceScenarioId !== scenarioId) return false;
    if (dimension && c.dimension !== dimension) return false;
    return true;
  }), [merged, kw, scenarioId, dimension]);

  const ethics = useMemo(() => merged.ethics.filter(
    (e) => !kw || e.title.includes(kw) || e.text.includes(kw),
  ), [merged, kw]);

  const dbOnly = new Set(merged.dbOnlyIds);
  const total = merged.skills.length + merged.ethics.length;
  const hasFilter = Boolean(kw || scenarioId || dimension);
  const hits = skills.length + ethics.length;

  /** 一键清空全部筛选 */
  const reset = () => {
    setQ('');
    setScenarioId('');
    setDimension('');
  };

  return (
    <div className="screen is-on">
      <div className="kb-head">
        <div className="k">知识库 · Knowledge Base</div>
        <h2>
          {merged.skills.length} 条面谈技巧 · {merged.ethics.length} 条伦理守则 · {wordTotal} 条判定词 · 共 {total + wordTotal} 项
        </h2>
      </div>

      <div className="kb-search">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索技巧卡、伦理守则、国标条款…"
          aria-label="搜索知识库"
        />
        <span className="cnt">
          {hasFilter ? `${hits} 条命中` : `${total} 张卡 · ${wordTotal} 条词`}
        </span>
      </div>

      {/* 任务书要求的「按案例检索」+ 六维筛选 */}
      <div className="kb-filters" role="group" aria-label="知识库筛选">
        <label>
          <span>适用案例</span>
          <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
            <option value="">全部案例</option>
            {SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>{s.id} {s.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>能力维度</span>
          <select value={dimension} onChange={(e) => setDimension(e.target.value)}>
            <option value="">全部维度</option>
            {DIMENSIONS.map((d) => (
              <option key={d.key} value={d.key}>{d.name}</option>
            ))}
          </select>
        </label>
        {hasFilter && (
          <button className="kb-reset" type="button" onClick={reset}>
            清空筛选
          </button>
        )}
      </div>

      <div className="kb-tabs" role="tablist" aria-label="知识库分类"
        onKeyDown={onTabKeyDown}>
        <button className="kb-tab" role="tab" id="tab-skill"
          aria-controls="panel-kb" aria-selected={tab === 'skill'}
          tabIndex={tab === 'skill' ? 0 : -1}
          onClick={() => setTab('skill')}>
          面谈技巧卡（{skills.length}）
        </button>
        <button className="kb-tab" role="tab" id="tab-ethic"
          aria-controls="panel-kb" aria-selected={tab === 'ethic'}
          tabIndex={tab === 'ethic' ? 0 : -1}
          onClick={() => setTab('ethic')}>
          伦理守则速查（{ethics.length}）
        </button>
        <button className="kb-tab" role="tab" id="tab-word"
          aria-controls="panel-kb" aria-selected={tab === 'word'}
          tabIndex={tab === 'word' ? 0 : -1}
          onClick={() => setTab('word')}>
          判定词表（{wordTotal}）
        </button>
      </div>

      {tab === 'skill' && (
        <div className="kb-panel on" role="tabpanel" id="panel-kb"
          aria-labelledby="tab-skill">
          <div className="kb-grid">
            {skills.length === 0 && (
              <div className="kb-empty">
                没有匹配的技巧卡
                {hasFilter && (
                  <> · <button className="linkd" type="button" onClick={reset}>
                    清空筛选
                  </button></>
                )}
              </div>
            )}
            {skills.map((c, i) => (
              <article className="kcard" key={c.id}
                style={{ animationDelay: (i * 45) + 'ms' }}>
                <div className="kcard-top">
                  <span className="kcard-no">{c.id}</span>
                  <h3>{c.title}</h3>
                </div>
                <p>{c.text}</p>
                <div className="kcard-foot">
                  {c.dimension
                    ? <span className="tag">{dimName(c.dimension)}</span>
                    : c.category && <span className="tag">{c.category}</span>}
                  {c.source && <span className="src">{c.source}</span>}
                  {c.practiceScenarioId && (
                    <button
                      className="linkd"
                      type="button"
                      onClick={() => nav('/training/' + c.practiceScenarioId)}
                    >
                      去练习 →
                    </button>
                  )}
                  {dbOnly.has(c.id) && <span className="src">管理端新增</span>}
                </div>
                {c.practiceScenarioId && (
                  <div className="kcard-case">
                    适用案例：{scenarioName(c.practiceScenarioId)}
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {tab === 'word' && (
        <div className="kb-panel on" role="tabpanel" id="panel-kb"
          aria-labelledby="tab-word">
          <div className="kb-empty" style={{ marginBottom: 14 }}>
            系统判定用词以教材条款为依据。左列为正常表达（同感、提问、陪伴），
            右列为需要警惕的表达（评判、建议过早、毒性积极）。
            危机级与无望感两组是安全边界，其基线词不可被禁用。
          </div>
          {!wordbook && <div className="kb-empty">加载中…</div>}
          {wordbook?.map((g) => (
            <div key={g.group} className="wb-panel" style={{ marginBottom: 12 }}>
              <div className="wb-panel-h">
                <span>{g.label}</span>
                <span className="hint">
                  {g.count} 条{g.protected ? ' · 安全边界，基线不可禁用' : ''}
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '10px 0' }}>
                {g.words.map((w) => (
                  <span
                    key={w}
                    className="tag"
                    style={g.protected ? {
                      borderColor: 'var(--proof)', color: 'var(--proof)',
                    } : undefined}
                  >
                    {w}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'ethic' && (
        <div className="kb-panel on" role="tabpanel" id="panel-kb"
          aria-labelledby="tab-ethic">
          <div className="ethic-grid">
            {ethics.length === 0 && (
              <div className="kb-empty">
                没有匹配的伦理守则
                {kw && (
                  <> · <button className="linkd" type="button" onClick={reset}>
                    清空筛选
                  </button></>
                )}
              </div>
            )}
            {ethics.map((e, i) => (
              <article className="ethic" key={e.id + e.title}
                style={{ animationDelay: (i * 50) + 'ms' }}>
                <div className="k">
                  {e.id}
                  {dbOnly.has(e.id) && ' · 管理端新增'}
                </div>
                <h3>{e.title}</h3>
                <p style={{ whiteSpace: 'pre-line' }}>{e.text}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
