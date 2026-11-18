/**
 * 07 知识库 —— 19 张技巧卡 + 12 条伦理守则
 * 结构与 class 名来自 docs/预览/叩门-设计示例.html
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { DIMENSIONS } from '../services/scoring.ts';

export default function KnowledgePage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<'skill' | 'ethic'>('skill');
  const [q, setQ] = useState('');

  const kw = q.trim();
  const dimName = (k: string) => DIMENSIONS.find((d) => d.key === k)?.name ?? k;

  const skills = SKILL_CARDS.filter(
    (c) => !kw || c.title.includes(kw) || c.body.includes(kw) || c.source.includes(kw),
  );
  const ethics = ETHICS.filter(
    (e) => !kw || e.title.includes(kw) || e.quote.includes(kw) || (e.explanation || '').includes(kw),
  );

  const total = SKILL_CARDS.length + ETHICS.length;

  return (
    <div className="screen is-on">
      <div className="kb-head">
        <div className="k">知识库 · Knowledge Base</div>
        <h2>{SKILL_CARDS.length} 条面谈技巧 · {ETHICS.length} 条伦理守则 · 共 {total} 张卡</h2>
      </div>

      <div className="kb-search">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="搜索技巧卡、伦理守则、国标条款…" aria-label="搜索知识库" />
        <span className="cnt">{kw ? skills.length + ethics.length + ' 条命中' : total + ' 张卡'}</span>
      </div>

      <div className="kb-tabs" role="tablist" aria-label="知识库分类">
        <button className="kb-tab" role="tab" aria-selected={tab === 'skill'}
          onClick={() => setTab('skill')}>面谈技巧卡</button>
        <button className="kb-tab" role="tab" aria-selected={tab === 'ethic'}
          onClick={() => setTab('ethic')}>伦理守则速查</button>
      </div>

      {tab === 'skill' && (
        <div className="kb-panel on">
          <div className="kb-grid">
            {skills.length === 0 && <div className="kb-empty">没有匹配的技巧卡</div>}
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
                  <button className="linkd" type="button" onClick={() => nav('/training/' + c.practice.scenarioId)}>
                    去练习 →
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}

      {tab === 'ethic' && (
        <div className="kb-panel on">
          <div className="ethic-grid">
            {ethics.length === 0 && <div className="kb-empty">没有匹配的伦理守则</div>}
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
