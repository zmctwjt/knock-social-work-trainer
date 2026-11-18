/**
 * SettlePage —— 逐句点评
 *
 * 结构与 class 名完全沿用 docs/预览/叩门-设计示例.html，视觉零改动。
 * 逻辑接在 src/services 与 src/hooks 上。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { getScenario } from '../data/scenarios.ts';
import { DIMENSIONS, WEAKNESS_ADVICE } from '../services/scoring.ts';
import type { ProofMark } from '../types.ts';

/** UI 三段 → 阶段名（与复盘页的「三阶段」口径一致） */
const PHASE_TITLE: Record<number, string> = {
  1: '建立关系与问题探索',
  2: '评估与计划',
  3: '介入与结案',
};


/** 用 ProofMark 的 start/end 切分原文，给命中的片段加样式 */
function renderMarked(text: string, marks: ProofMark[]): React.ReactNode {
  if (!marks || marks.length === 0) return text;
  const sorted = [...marks].filter((m) => m.end > m.start).sort((a, b) => a.start - b.start);
  const out: React.ReactNode[] = [];
  let pos = 0;
  sorted.forEach((m, i) => {
    if (m.start > pos) out.push(text.slice(pos, m.start));
    const cls = m.kind === 'add' ? 'add' : m.kind === 'del' ? 'del' : 'proof-mark';
    out.push(<span key={i} className={cls}>{text.slice(m.start, m.end)}</span>);
    pos = Math.max(pos, m.end);
  });
  if (pos < text.length) out.push(text.slice(pos));
  return out;
}

export default function SettlePage() {
  const { session, records, account } = useStore();
  const last = session?.lastResult;
  const sc = session ? getScenario(session.scriptId) : null;
  const nav = useNavigate();

  /* ── 本阶段最弱项：只用真实分数，取不到就整块不渲染 ──
     ① 本次阶段有真实发言 → 用 last.scores
     ② 直接打开结算页、没有进行中的会话 → 回退到最近一条训练记录
     ③ 0 次发言 / 没有任何记录 → 不显示建议（不编造） */
  const myRecs = account ? records.filter((r) => r.nickname === account.nickname) : [];
  const basis =
    last && (session?.notes.length ?? 0) > 0 ? last.scores
    : !session && myRecs.length > 0 ? myRecs[0].scores
    : null;
  const weakReport = (() => {
    const b = basis;
    if (!b) return null;
    const dim = DIMENSIONS.reduce((m, d) => (b[d.key] < b[m.key] ? d : m), DIMENSIONS[0]);
    return { name: dim.name, score: b[dim.key], advice: WEAKNESS_ADVICE[dim.key] };
  })();
  const phase = session?.phase ?? 1;

  return (
    <div className="screen is-on">
      <div className="card" style={{ marginBottom: 18, animationDelay: "0ms" }}>
        {last ? (
          <>
            <div className="h"><span>本次训练</span><b>{sc?.name ?? session?.scriptId} · {session?.difficulty}</b></div>
            <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
              <div><div style={{ fontFamily: "var(--mono)", fontSize: 34, color: "var(--green)" }}>{last.total}</div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>综合分</div></div>
              {DIMENSIONS.map((d) => (
                <div key={d.key}><div style={{ fontFamily: "var(--mono)", fontSize: 22 }}>{last.scores[d.key]}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)" }}>{d.name}</div></div>
              ))}
            </div>
            <p style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--rule)" }}>
              最弱项：<b>{DIMENSIONS.find((d) => d.key === last.weakDim)?.name} {last.weakScore}</b>
              　总共 {session?.notes.length ?? 0} 条逐句记录
            </p>
          </>
        ) : (
          <div className="kb-empty">还没有本次训练数据。请先在「面谈训练」页说几句，再点「提交本阶段」。</div>
        )}
      </div>

  
    <div className="settle-head">
      <div>
        <div className="k">阶段结算 · Stage {phase} of 3</div>
        <h2>{PHASE_TITLE[phase] ?? PHASE_TITLE[1]} · 本阶段小结</h2>
      </div>
      <div className="settle-score">
        <div className="n">{last ? last.total : 0}</div>
        <div className="d">{last ? (last.total >= 70 ? "▲ 本阶段表现良好" : last.total >= 60 ? "▲ 达到基本要求" : "▲ 需重点改进") : "尚无数据"}</div>
      </div>
    </div>
  
    <div className="settle-cols">
      <div>
        <div className="panel-h">逐句点评 · Margin Notes（{session?.notes.length ?? 0} 条记录）</div>
        <div className="margin-list">
          {(!session?.notes || session.notes.length === 0) && (
            <div className="kb-empty">
              本次还没有逐句记录。回到「面谈训练」说几句，再点「提交本阶段」。
            </div>
          )}
          {session?.notes.map((n) => {
            const isMe = n.speaker === 'worker';
            const dim = DIMENSIONS.find((d) => d.key === n.dimension);
            const plus = n.delta > 0;
            return (
              <div className="mrow" key={n.index}>
                <span className="no">{n.index}</span>
                <div>
                  <span className="who">{isMe ? '你' : (sc?.name ?? '服务对象')}</span>
                  <p className="said">{renderMarked(n.utterance, n.marks)}</p>
                  {n.response && (
                    <p className="replied">→ {n.response}</p>
                  )}
                  <div className="verdict">
                    <span className={plus ? 'pf pass' : 'pf'}>{plus ? '▲ 有效' : '▲ 需复核'}</span>
                    {dim && <span className="tag-dim">{dim.name}</span>}
                    <span className="src">{n.ruleNote}{n.source ? ' · ' + n.source : ''}</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span className={'delta-pill ' + (plus ? 'plus' : 'minus')}>
                    {plus ? '+' : ''}{n.delta}
                  </span>
                </div>
              </div>
            );
          })}
        
  
        </div>
      </div>
    </div>
  
    {weakReport && (
      <div className="rblock bad" style={{'marginTop':'var(--s6)'}}>
        <div className="k">本阶段最弱项 · 建议动作</div>
        <h3>{weakReport.name}　{weakReport.score} 分</h3>
        <p>{weakReport.advice.advice}</p>
        <p>
          <b>建议：</b>
          {weakReport.advice.scenario === weakReport.advice.node
            ? `回到 ${weakReport.advice.scenario} 重练这一段，`
            : `回到 ${weakReport.advice.scenario} 的 ${weakReport.advice.node} 节点重练，`}
          并对照技巧卡《{weakReport.advice.card}》。
        </p>
      </div>
    )}
  
          <div style={{ marginTop: 32, paddingTop: 22, borderTop: "1px solid var(--rule)",
                    display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button className="btn-primary" type="button" onClick={() => nav('/review')}>
          查看复盘报告
        </button>
        <button className="btn-ghost" type="button" onClick={() => nav('/cases')}>
          换一位服务对象
        </button>
      </div>
</div>
  );
}
