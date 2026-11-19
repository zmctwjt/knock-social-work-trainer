/**
 * 07 知识库 —— 19 张技巧卡 + 12 条伦理守则
 *
 * 任务书要求「支持按案例与关键词检索」，因此提供三类筛选：
 * 关键词（标题/正文/条款来源）、案例（该卡对应哪类服务对象）、维度（六维能力）。
 * 三者可叠加，命中数实时显示。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { DIMENSIONS } from '../services/scoring.ts';
import { SCENARIOS } from '../data/scenarios.ts';
import { useTabKeys } from '../lib/useTabKeys.ts';
import { apiGet } from '../lib/authClient.ts';
import { mergeKnowledge, type DbCard } from '../lib/knowledgeMerge.ts';

export default function KnowledgePage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<'skill' | 'ethic'>('skill');
  // 知识库只有两个标签，仍按 WAI-ARIA tabs 模式支持方向键切换
  const onTabKeyDown = useTabKeys(
    [{ key: 'skill' as const }, { key: 'ethic' as const }],
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
          {merged.skills.length} 条面谈技巧 · {merged.ethics.length} 条伦理守则 · 共 {total} 张卡
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
          {hasFilter ? `${hits} 条命中` : `${total} 张卡`}
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
