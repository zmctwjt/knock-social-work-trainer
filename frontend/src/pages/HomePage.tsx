/**
 * HomePage —— 数据统计、目录入口
 *
 * 结构与 class 名完全沿用 docs/预览/叩门-设计示例.html，视觉零改动。
 * 逻辑接在 src/services 与 src/hooks 上。
 *
 * ★ 页面上的统计数字全部来自当前账号的真实记录与代码常量：
 *   写死字面量会在改内容后与成长中心 / 关于页互相打脸。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useMyRecords, useStore } from '../store/store.tsx';
import { DIMENSIONS } from '../services/scoring.ts';
import { SCENARIOS, getScenario } from '../data/scenarios.ts';

export default function HomePage() {
  const nav = useNavigate();
  const { session } = useStore();
  const recs = useMyRecords();
  const n = recs.length;

  /* ── 四个统计卡：全部由当前账号的记录现算 ─────────── */
  const avgTotal = n > 0 ? Math.round(recs.reduce((s, r) => s + r.total, 0) / n) : null;
  const covered = new Set(recs.map((r) => r.scriptId)).size;
  /* 记录按时间倒序（store.addRecord 前插），trend > 0 表示比上次高 */
  const trend = n >= 2 ? recs[0].total - recs[1].total : null;
  const dimAvg = DIMENSIONS.map((d) => ({
    key: d.key,
    name: d.name,
    score: n > 0 ? Math.round(recs.reduce((s, r) => s + (r.scores[d.key] ?? 0), 0) / n) : 0,
  }));
  const weak = n > 0 ? dimAvg.reduce((a, b) => (b.score < a.score ? b : a)) : null;

  /* ── 今日案卷：接着上次练的角色，没有记录就 W-01 ─── */
  const resumeId = session?.scriptId ?? recs[0]?.scriptId ?? SCENARIOS[0].id;
  const today = getScenario(resumeId) ?? SCENARIOS[0];
  const caseNo = SCENARIOS.indexOf(today) + 1;
  const now = new Date();
  const dateStr =
    String(now.getMonth() + 1).padStart(2, '0') + ' / ' +
    String(now.getDate()).padStart(2, '0');

  return (
    <div className="screen is-on">
  
    <div className="hero">
      <div className="hero-l">
        <div className="kicker">民政部《社会工作方法 个案工作》· 6.1.1 会谈技巧训练系统</div>
        <h1>把每一次面谈，<br />当作一份<em>待校样的稿子</em>。</h1>
        <p className="lede">
          AI 扮演 {SCENARIOS.length} 类真实服务对象，你说一句，它当场告诉你这句话
          <b>共情到位了，还是越界评判了</b>。<br />
          六个评分维度全部锚定方法条款，每条判定都指得出依据。
        </p>
        <div className="hero-cta">
          <button className="btn-primary" type="button"onClick={() => nav('/cases')}>开始今天的训练</button>
          <button className="btn-ghost" type="button"onClick={() => nav('/about')}>查看六维评分依据</button>
        </div>
      </div>
  
      <aside className="today" aria-label="今日案卷">
        <div className="today-h">
          <span className="k">
            今日案卷 · {caseNo > 0 ? `Case ${String(caseNo).padStart(2, '0')}` : today.id}
          </span>
          <span className="d">{dateStr}</span>
        </div>
        <div className="today-b">
          <div className="subj">{today.name} · {today.age} 岁</div>
          <p className="sub">{today.archetype}。{today.brief}</p>
          <div className="hero-cta" style={{'marginTop':'0'}}>
            <button className="btn-primary" type="button" style={{'padding':'11px 22px','minHeight':'44px','fontSize':'13px'}}onClick={() => nav('/training/' + resumeId)}>进入面谈室</button>
            <button className="btn-ghost" type="button" style={{'padding':'11px 18px','minHeight':'44px','fontSize':'13px'}}onClick={() => nav('/cases')}>换一位</button>
          </div>
        </div>
        <div className="today-meta" style={{'padding':'var(--s3) var(--s4)','borderTop':'1px solid var(--rule)'}}>
          <div><div className="k">难度</div><div className="n">{today.difficulty}<span style={{'fontSize':'12px','color':'var(--ink-3)'}}>/5</span></div></div>
          <div><div className="k">预计时长</div><div className="n">18<span style={{'fontSize':'12px','color':'var(--ink-3)'}}>分钟</span></div></div>
          <div>
            <div className="k">敏感级</div>
            <div className="n" style={today.sensitiveTag === '无' ? undefined : { color: 'var(--warn)' }}>
              {today.sensitiveTag === '无' ? '无' : '关注'}
            </div>
          </div>
        </div>
      </aside>
    </div>
  
    <div className="statline">
      <div className="stat">
        <div className="k">累计训练</div><div className="n">{n}</div>
        <div className="d">
          {n > 0 ? `次 · 覆盖 ${covered} 个剧本` : '点「开始今天的训练」写入第一条'}
        </div>
      </div>
      <div className="stat">
        <div className="k">平均综合分</div><div className="n">{avgTotal ?? '—'}</div>
        <div className="d">
          {n === 0 ? '有记录后自动计算'
            : trend === null ? '首条记录 · 已入库'
            : trend > 0 ? `较上次 ↑ +${trend}`
            : trend < 0 ? `较上次 ↓ ${trend}`
            : '较上次 持平'}
        </div>
      </div>
      <div className="stat">
        <div className="k">最薄弱维度</div>
        <div className={'n' + (weak ? ' warn' : '')}>{weak ? weak.score : '—'}</div>
        <div className="d">{weak ? weak.name : '有记录后自动定位六维短板'}</div>
      </div>
      <div className="stat">
        <div className="k">待复盘</div><div className="n">{n}</div>
        <div className="d">
          {n > 0 ? `已完成 ${n} 份逐句点评` : '完成一次训练即可回看逐句点评'}
        </div>
      </div>
    </div>
  
    <div className="toc">
      <div className="toc-h">训练目录 · Contents</div>
      <div className="toc-row" onClick={() => nav('/training/' + resumeId)} role="button" tabIndex={0}>
        <div className="no">01</div>
        <div>
          <h3>六维实时评分与逐句点评</h3>
          <p>每说完一句，系统当场标注这句话命中了哪个维度、加分还是扣分、依据是哪条规则。</p>
        </div>
        <div className="aside">{DIMENSIONS.length} 维度 · 民政部个案工作标准</div>
      </div>
      <div className="toc-row" onClick={() => nav('/about')} role="button" tabIndex={0}>
        <div className="no">02</div>
        <div>
          <h3>三级风险分级</h3>
          <p>把「无望感表达」与「自伤意念」分开处理。前者引导探索，后者本地硬规则拦截——这是新手社工最容易犯错的地方。</p>
        </div>
        <div className="aside">🟡 关注级 / 🔴 危机级</div>
      </div>
      <div className="toc-row" onClick={() => nav('/cases')} role="button" tabIndex={0}>
        <div className="no">03</div>
        <div>
          <h3>阻抗不是不配合</h3>
          <p>{SCENARIOS.length} 个剧本刻意设计了客气回避、情绪拉同盟、高冷淡漠、对同情敏感、逞强否认、否认与反复淡化六种阻抗形态，每种配一条可判定规则。</p>
        </div>
        <div className="aside">{SCENARIOS.length} 剧本 · 5 种阻抗</div>
      </div>
      <div className="toc-row" onClick={() => nav('/review')} role="button" tabIndex={0}>
        <div className="no">04</div>
        <div>
          <h3>复盘报告与标准示范对照</h3>
          <p>训练结束生成报告，并把你的每一句与专家示范逐句并列——差在哪一两个字上，一目了然。</p>
        </div>
        <div className="aside">AI 生成 · 失败降级模板</div>
      </div>
    </div>
  
    </div>
  );
}
