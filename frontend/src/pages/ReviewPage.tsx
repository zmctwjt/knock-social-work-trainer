/**
 * ReviewPage —— 与专家示范对照
 *
 * 结构与 class 名完全沿用 docs/预览/叩门-设计示例.html，视觉零改动。
 * 逻辑接在 src/services 与 src/hooks 上。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { getScenario } from '../data/scenarios.ts';
import { DIMENSIONS } from '../services/scoring.ts';
import { matchFlaw, deltaLabel } from '../data/expertDemo.ts';
import { SKILL_CARDS } from '../data/knowledge.ts';
import { loadDebrief } from '../lib/debriefStore.ts';

/** 从 session.notes 生成逐句对照行 */
function buildCompare(notes: { utterance: string; dimension: string; delta: number }[]) {
  const out: { mine: string; demo: ReturnType<typeof matchFlaw> }[] = [];
  for (const n of notes) {
    const d = matchFlaw(n.utterance);
    if (d) out.push({ mine: n.utterance, demo: d });
  }
  // 至少给两条有代表性的（优先挑有扣分的）
  if (out.length === 0) return [];
  const sorted = [...out].sort((a, b) => (a.demo?.delta ?? 0) - (b.demo?.delta ?? 0));
  return sorted.slice(0, 6);
}

export default function ReviewPage() {
  const { session } = useStore();
  const nav = useNavigate();
  const last = session?.lastResult;

  /* ★ 没有本次训练数据 → 整页空状态。
     以前这种情况照常渲染「本次没有拿到加分的句子」「六维里有 0 分」，
     等于在编造结论，使用者一眼就能看出是假报告。 */
  if (!last) {
    return (
      <div className="screen is-on">
        <div className="report-head">
          <div className="k">复盘报告 · Debrief</div>
          <h2>还没有可复盘的记录</h2>
        </div>
        <div className="card" style={{ maxWidth: 560, padding: '34px 30px' }}>
          <p style={{ fontFamily: 'var(--serif)', fontSize: 19, lineHeight: 1.65, marginBottom: 14 }}>
            先完成一次面谈，这份报告才有东西可写。
          </p>
          <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--ink-2)', marginBottom: 20 }}>
            复盘页会把你说的每一句与专家示范并列，并给出三段结论：做得好、需要改进、下一步练什么。
            <b>没有记录时，这里不编造结论。</b>
          </p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button className="btn-primary" type="button"
              onClick={() => nav('/training/' + (session?.scriptId ?? 'W-01'))}>
              去面谈训练
            </button>
            <button className="btn-ghost" type="button" onClick={() => nav('/settle')}>
              去阶段结算
            </button>
          </div>
        </div>
      </div>
    );
  }

  const sc = session ? getScenario(session.scriptId) : null;
  const notes = session?.notes ?? [];
  const cmp = buildCompare(notes);

  /* 三段复盘：从真实数据推，不用写死的文案 */
  const good = notes.filter((n) => n.delta > 0);
  const bad = notes.filter((n) => n.delta < 0).sort((a, b) => a.delta - b.delta);
  const weak = last ? DIMENSIONS.find((d) => d.key === last.weakDim) : null;
  const weakTip = weak
    ? SKILL_CARDS.find((c) => c.dimension === weak.key)
    : null;
  const debrief = loadDebrief();
  const debriefBlocks: [string, string][] = debrief
    ? [['做得好', debrief.strength], ['需要改进', debrief.improvement], ['下一步练什么', debrief.nextStep]]
    : [];
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

  
    <div className="report-head">
      <div className="k">复盘报告 · Debrief</div>
      <h2>{sc ? `${sc.name} · ${session?.phase === 3 ? '完整面谈' : `阶段 ${session?.phase ?? 1} 面谈`}` : '复盘报告'}</h2>
    </div>
    <div className="report-meta">
      <div>难度 <b>{session?.difficulty ?? '—'}</b></div>
      <div>对话轮次 <b>{notes.length}</b></div>
      <div>综合分 <b>{last?.total ?? '—'}</b></div>
      <div>有效发言 <b>{good.length} 条</b></div>
      <div>需改进 <b>{bad.length} 条</b></div>
    </div>

    {/* ★ AI 复盘：提交阶段时生成，失败则已回落模板（模型名取实际返回值） */}
    {debriefBlocks.length > 0 && (
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="h">
          <span>督导复盘</span>
          <b>{debrief?.source === 'ai' ? `${debrief?.model || 'AI'} 生成` : '规则模板（AI 未启用）'}</b>
        </div>
        {debriefBlocks.map(([label, text]) => (
          <div key={label} style={{ marginTop: 12 }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.12em',
              color: 'var(--ink-3)', marginBottom: 4 }}>
              {label}
            </div>
            <p style={{ fontSize: 13.5, lineHeight: 1.95, whiteSpace: 'pre-wrap' }}>{text}</p>
          </div>
        ))}
      </div>
    )}
  
    <div className="report-body">
            <div className="rblock good">
        <div className="k">Strengths · 做得好</div>
        {good.length > 0 ? (
          <>
            <h3>有 {good.length} 句是有效的</h3>
            {good.slice(0, 2).map((n) => (
              <p key={n.index}>
                你说「<b>{n.utterance}</b>」拿到 <b>+{n.delta}</b>，
                {DIMENSIONS.find((d) => d.key === n.dimension)?.name}加分——
                {n.ruleNote}{n.source ? `（${n.source}）` : ''}。
              </p>
            ))}
            {good.length > 2 && <p className="dim">另有 {good.length - 2} 句同样有效，见下方逐句对照。</p>}
          </>
        ) : (
          <>
            <h3>本次没有拿到加分的句子</h3>
            <p>这不代表你不行——六维里有 <b>{last?.total ?? 0}</b> 分，
              说明流程走完了、规则也命中了，只是没踩中加分项。</p>
            <p>建议下次先从<b>复述确认</b>开始：「您刚才说的那件事，也就是说……对吗？」
              这句最容易拿到 +8，而且零风险。</p>
          </>
        )}
      </div>

      <div className="rblock bad">
        <div className="k">Gaps · 需要改进</div>
        {bad.length > 0 ? (
          <>
            <h3>{bad.length} 句被扣分，最严重的一句扣 {Math.abs(bad[0].delta)}</h3>
            {bad.slice(0, 2).map((n) => {
              const d = matchFlaw(n.utterance);
              return (
                <p key={n.index}>
                  你说「<b>{n.utterance}</b>」扣 <b>{Math.abs(n.delta)}</b>。
                  {d ? d.why : '这句没有命中正向规则，也没触犯黑名单——它只是没带来推进。'}
                </p>
              );
            })}
            <p className="src">
              {weak && <>最弱维度是<b>{weak.name}（{last?.scores[weak.key]}）</b>。
                {weakTip && <>技巧卡《{weakTip.title}》讲的就是这个：{weakTip.body.slice(0, 46)}…</>}
                </>}
            </p>
          </>
        ) : (
          <>
            <h3>本次没有被扣分的句子</h3>
            <p>六维里有 <b>{last?.total ?? 0}</b> 分，没有一条踩到黑名单。
              下一步可以试着提高难度，或者练<b>阶段完整性</b>——
              目前流程只到「建立关系」，还没走完「预估→计划→介入→评估→结案」。</p>
          </>
        )}
      </div>

      <div className="rblock">
        <div className="k">Next · 下一步练什么</div>
        <h3>
          {weak
            ? `重练「${weak.name}」这一项`
            : '先把一次面谈完整走完三个阶段'}
        </h3>
        <p>
          {weakTip
            ? <>技巧卡《<b>{weakTip.title}</b>》：{weakTip.body}
                {weakTip.source && <span className="src">（{weakTip.source}）</span>}</>
            : <>本作品每个剧本分三个阶段（建立关系与问题探索 → 评估与计划 → 介入与结案）。
                你只完成了第一个阶段，结算页的「过程完整性」会一直偏低。
                把「提交本阶段」点满三次，才能看到完整流程的评分。</>}
        </p>
        {bad.length > 0 && (
          <p>
            具体动作：把下面对照里的<b>专家示范</b>抄一遍，下次遇到同样的场景直接用。
            刻意练习一句话，比读十篇理论有用。
          </p>
        )}
      </div>

    <div className="demo-compare">
      <div className="panel-h">
        逐句对照 · 你的回应 vs 专家示范
        {cmp.length > 0 && <span className="cmp-cnt"> 本次共 {notes.length} 句，列出 {cmp.length} 句</span>}
      </div>

      {cmp.length === 0 && (
        <div className="kb-empty">
          本次没有可对照的发言。回到「面谈训练」说几句，再点「提交本阶段」。
        </div>
      )}

      {cmp.map((row, i) => {
        const d = row.demo!;
        const dim = DIMENSIONS.find((x) => x.key === d.dimension);
        return (
          <div className="cmp" key={i} style={{ animationDelay: (i * 60) + 'ms' }}>
            <div className="cmp-col mine">
              <div className="ch">
                <span className="ch-no">{String(i + 1).padStart(2, '0')}</span>
                你的回应
                <span className={'ch-delta ' + (d.delta > 0 ? 'plus' : d.delta < 0 ? 'minus' : 'flat')}>
                  {deltaLabel(d.delta)} {d.delta > 0 ? '+' : ''}{d.delta || ''}
                </span>
              </div>
              <div className="cmp-line">
                <span className="n">你说</span><span>「{row.mine}」</span>
              </div>
              <div className="cmp-flaw">
                问题：{d.studentSays.startsWith('（') ? '这一轮没接住对方' : d.studentSays}
                {dim && <span className="tag-dim">{dim.name}</span>}
              </div>
            </div>

            <div className="cmp-col ref">
              <div className="ch">专家示范</div>
              <div className="cmp-line">
                <span className="n">示范</span><span>{d.expert}</span>
              </div>
              <div className="cmp-why">{d.why}</div>
              <div className="cmp-src">{d.source}</div>
            </div>
          </div>
        );
      })}
    </div>
    </div>
    </div>
  );
}
