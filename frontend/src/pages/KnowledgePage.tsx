/**
 * 07 知识库 —— 19 张技巧卡 + 12 条伦理守则
 *
 * 任务书要求「支持按案例与关键词检索」，因此提供三类筛选：
 * 关键词（标题/正文/条款来源）、案例（该卡对应哪类服务对象）、维度（六维能力）。
 * 三者可叠加，命中数实时显示。
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { DIMENSIONS } from '../services/scoring.ts';
import { SCENARIOS } from '../data/scenarios.ts';

export default function KnowledgePage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<'skill' | 'ethic'>('skill');
  const [q, setQ] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [dimension, setDimension] = useState('');

  const kw = q.trim();
  const dimName = (k: string) => DIMENSIONS.find((d) => d.key === k)?.name ?? k;

  /** 找到某卡对应案例的姓名，用于卡片上显示"适用案例" */
  const scenarioName = (id?: string) =>
    id ? (SCENARIOS.find((s) => s.id === id)?.name ?? id) : '';

  const skills = useMemo(() => SKILL_CARDS.filter((c) => {
    if (kw && !c.title.includes(kw) && !c.body.includes(kw) && !c.source.includes(kw)) {
      return false;
    }
    // 案例筛选：卡片的 practice.scenarioId 与所选案例一致
    if (scenarioId && c.practice?.scenarioId !== scenarioId) return false;
    if (dimension && c.dimension !== dimension) return false;
    return true;
  }), [kw, scenarioId, dimension]);

  const ethics = useMemo(() => ETHICS.filter(
    (e) => !kw
      || e.title.includes(kw)
      || e.quote.includes(kw)
      || (e.explanation || '').includes(kw),
  ), [kw]);

  const total = SKILL_CARDS.length + ETHICS.length;
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
          {SKILL_CARDS.length} 条面谈技巧 · {ETHICS.length} 条伦理守则 · 共 {total} 张卡
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

      <div className="kb-tabs" role="tablist" aria-label="知识库分类">
        <button className="kb-tab" role="tab" aria-selected={tab === 'skill'}
          onClick={() => setTab('skill')}>
          面谈技巧卡（{skills.length}）
        </button>
        <button className="kb-tab" role="tab" aria-selected={tab === 'ethic'}
          onClick={() => setTab('ethic')}>
          伦理守则速查（{ethics.length}）
        </button>
      </div>

      {tab === 'skill' && (
        <div className="kb-panel on">
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
                <p>{c.body}</p>
                <div className="kcard-foot">
                  <span className="tag">{dimName(c.dimension)}</span>
                  <span className="src">{c.source}</span>
                  <button
                    className="linkd"
                    type="button"
                    onClick={() => nav('/training/' + c.practice.scenarioId)}
                  >
                    去练习 →
                  </button>
                </div>
                {c.practice?.scenarioId && (
                  <div className="kcard-case">
                    适用案例：{scenarioName(c.practice.scenarioId)}
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {tab === 'ethic' && (
        <div className="kb-panel on">
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
              <article className="ethic" key={e.code + e.title}
                style={{ animationDelay: (i * 50) + 'ms' }}>
                <div className="k">{e.code}</div>
                <h3>{e.title}</h3>
                <blockquote className="quote">{e.quote}</blockquote>
                <p>{e.explanation}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
