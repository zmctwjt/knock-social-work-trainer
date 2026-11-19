/**
 * 03 面谈训练（核心页）
 *
 * 三条 AI 模式在这一页可切换，答辩时能现场对比：
 *   规则模式   —— 零调用、零延迟
 *   混合模式   —— 台词走预置库，AI 只做长尾意图 + 阶段评分 + 复盘
 *   全 AI 模式 —— 台词也由当前配置的模型按人设实时生成
 *
 * 危机级内容由本地规则拦截，不进模型、不计分，并要求用户确认后才恢复输入。
 */
import { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession, useAiStatus, type Difficulty, type AiMode } from '../hooks/useSession.ts';
import { SCENARIOS, getScenario } from '../data/scenarios.ts';
import {
  DIMENSIONS, computeRuleScore, weightedTotal, findWeakness, collectUtterances, mergeScores,
} from '../services/scoring.ts';
import { buildSuggestion, hopelessnessHint, buildCrisisCard } from '../services/crisis.ts';
import { saveTraining, loadSettingsLocal } from '../lib/db.ts';
import { gradeStage, generateDebrief, aiStatus, probeAi } from '../lib/aiClient.ts';
import { saveDebrief } from '../lib/debriefStore.ts';
import { useStore } from '../store/store.tsx';
import type { DimensionKey, DebriefReport } from '../types.ts';

/* 快捷话术按难度分档 —— 简单给满，挑战不给 */
const QUICK_ALL = [
  '您好，我来看看您。', '您平时吃饭是自己做吗？', '一个人过日子，夜里确实难熬。',
  '我理解你现在一个人撑着很辛苦。', '我理解。', '您应该多出去走走。',
  '我在这儿听着，不着急。', '我不想活了', '那您当时是怎么熬过来的？',
];
const QUICK_BY_DIFF: Record<Difficulty, string[]> = {
  简单实习: QUICK_ALL,
  标准实训: QUICK_ALL.slice(0, 7),
  挑战督导: [],
};

const AI_MODES: { key: AiMode; label: string; hint: string }[] = [
  { key: 'rule', label: '规则模式', hint: '零调用、零延迟；全部判定来自本地 162 条规则' },
  { key: 'hybrid', label: '混合模式', hint: '台词走预置库，AI 负责长尾意图补判与阶段六维评分' },
  // hint 在渲染时用实际模型名替换，避免换模型后文案与实际不符
  { key: 'ai', label: '全 AI 模式', hint: '服务对象台词由 {MODEL} 按人设实时生成' },
];

function gradeOf(v: number) {
  return v >= 75 ? 'good' : v >= 60 ? 'mid' : 'bad';
}

export default function TrainingPage({ scenarioId, onExit }: {
  scenarioId: string; onExit: () => void;
}) {
  const nav = useNavigate();
  const { account, addRecord, patchSession, session, startSession } = useStore();
  const nick = account?.nickname || '同学';
  const diff = (sessionStorage.getItem('knock.diff') as Difficulty) || '标准实训';
  const restorable =
    session && session.scriptId === scenarioId && session.messages.length > 0
      ? { ...session, difficulty: session.difficulty as Difficulty }
      : null;

  const {
    state, send, setState, advancePhase, acknowledgeCrisis, setAiMode, setDifficulty, reset,
  } = useSession(
    scenarioId,
    nick,
    restorable,
    (snap) => {
      patchSession({ scriptId: scenarioId, difficulty: diff, ...snap });
    },
  );

  const ai = useAiStatus();
  const settings = loadSettingsLocal();
  const showBasis = settings.show_basis !== false;
  const [input, setInput] = useState('');
  const [swapOpen, setSwapOpen] = useState(false);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestHidden, setSuggestHidden] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  /** busy 持续时间（秒），用于让"正在生成"有进度感 */
  const [busySec, setBusySec] = useState(0);
  const [submitNote, setSubmitNote] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const sc = getScenario(scenarioId);

  useEffect(() => {
    setDifficulty(diff);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diff]);

  /* busy 计时：模型响应 2–16 秒，界面上要让用户看到"还在跑、跑了多久" */
  useEffect(() => {
    if (!state.busy) { setBusySec(0); return; }
    const t0 = Date.now();
    setBusySec(0);
    const iv = setInterval(() => {
      setBusySec(Math.round((Date.now() - t0) / 1000));
    }, 500);
    return () => clearInterval(iv);
  }, [state.busy]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;  }, [state.messages.length, state.busy]);

  useEffect(() => {
    if (!session || session.scriptId !== scenarioId) startSession(scenarioId, diff);
  }, [session, scenarioId, diff, startSession]);

  /* 本阶段发言 → 规则底分（危机轮已由 collectUtterances 剔除） */
  const collected = useMemo(
    () => collectUtterances(state.messages.slice(state.stageStart)),
    [state.messages, state.stageStart],
  );

  const ruleScores = useMemo(
    () => computeRuleScore({
      utterances: collected.utterances,
      hopelessDetected: collected.hopelessSeen,
      hopelessRecognized: collected.hopelessRecognized,
      totalStages: 3,
      completedStages: state.phase,
      scoreAdjust: state.adjust,
      judgeCount: collected.judgeCount,
      vagueEmpathyCount: collected.vagueEmpathyCount,
    }),
    [collected, state.phase, state.adjust],
  );

  const total = weightedTotal(ruleScores);
  const weak = findWeakness(ruleScores);
  const lastW = useMemo(() => {
    for (let i = state.messages.length - 1; i >= 0; i--) {
      if (state.messages[i].speaker === 'worker') return state.messages[i].text;
    }
    return '';
  }, [state.messages]);
  const sug = buildSuggestion(state.emotion, state.judgeCount, state.hopelessSeen, lastW);
  const showSuggest = !suggestHidden;
  const hint = lastW ? hopelessnessHint(lastW) : null;
  const crisisOpen = state.crisisBlocked;

  async function onSend() {
    const t = input.trim();
    if (!t || state.busy || state.crisisBlocked) return;
    setInput('');
    await send(t);
  }

  async function onSubmit() {
    if (!sc || submitting) return;
    if (collected.workerTurns === 0) {
      setSubmitNote('本阶段还没有发言，先和对方说一两句再提交。');
      return;
    }
    setSubmitting(true);
    setSubmitNote('');

    try {
      /* ① AI 六维评分（规则模式 / 危机轮 / 未接入时自动跳过） */
      let aiScores: Record<DimensionKey, number> | null = null;
      let aiNote = '';
      if (state.aiMode !== 'rule' && aiStatus().ready) {
        setSubmitNote('督导正在阅卷…');
        const transcript = state.messages
          .slice(state.stageStart)
          .filter((m) => m.speaker !== 'system' && !m.isCrisis)
          .map((m) => `${m.speaker === 'worker' ? '社工' : '服务对象'}：${m.text}`)
          .join('\n');

        const g = await gradeStage({
          dialogue: transcript,
          crisisSeen: collected.crisisSeen,
          stats: {
            workerTurns: collected.workerTurns,
            judgeCount: collected.judgeCount,
            hopelessSeen: collected.hopelessSeen,
            hopelessRecognized: collected.hopelessRecognized,
            crisisSeen: collected.crisisSeen,
          },
        });
        if (g.scores) {
          aiScores = g.scores;
          aiNote = `AI 六维已计入（${g.model || 'GLM'}，${g.ms ?? '—'}ms）`;
        } else {
          aiNote = `规则底分单独计分（${g.failReason || 'AI 未返回完整六维'}）`;
        }
      } else if (state.aiMode === 'rule') {
        aiNote = '规则模式：综合分 100% 来自规则底分';
      }

      /* ② 综合分 = 规则 × 0.4 + AI × 0.6 */
      const merged = mergeScores(ruleScores, aiScores);
      const finalTotal = weightedTotal(merged.scores);
      const w = findWeakness(merged.scores);

      /* ③ 复盘报告（AI 优先，失败回落模板） */
      const template: DebriefReport = {
        strength: `本次「${DIMENSIONS.find((d) => d.key === w.dimension)?.name || ''}」是相对最弱项（${merged.scores[w.dimension]} 分）。`,
        improvement: w.advice,
        nextStep: `1. 优先重练「${w.name}」相关节点，把分数提到 75 以上。\n2. 完成下一次训练后对比同一维度的变化。`,
        source: 'template',
      };
      let debrief = template;
      if (state.aiMode !== 'rule' && aiStatus().ready && !collected.crisisSeen) {
        setSubmitNote('正在生成复盘报告…');
        debrief = await generateDebrief({
          nickname: nick,
          name: sc.name,
          age: sc.age,
          identity: sc.archetype,
          scores: merged.scores,
          hitRules: state.notes.map((n) => `第${n.index}句 ${n.ruleNote}`),
          template,
        });
      }

      /* ④ 落库 */
      const rec = addRecord({
        scriptId: sc.id,
        scriptName: sc.name,
        archetype: sc.archetype,
        difficulty: diff,
        blindfold: state.blindfold,
        uiPhase: state.phase,
        scores: merged.scores,
        total: finalTotal,
        aiUsed: merged.usedAI,
        durationSec: 0,
        notes: state.notes,
        transcript: state.messages
          .filter((m) => m.speaker !== 'system')
          .map((m) => ({
            role: (m.speaker === 'worker' ? 'worker' : 'client') as 'worker' | 'client',
            text: m.text,
          })),
      });

      if (rec?.id) saveDebrief(rec.id, debrief);
      if (!rec) saveDebrief('last', debrief);

      patchSession({
        scriptId: sc.id,
        difficulty: diff,
        lastResult: {
          scores: merged.scores,
          total: finalTotal,
          weakDim: w.dimension,
          weakScore: merged.scores[w.dimension],
        },
        notes: state.notes,
        phase: state.phase,
      });

      await saveTraining({
        nickname: nick,
        scriptId: sc.id,
        scriptName: sc.name,
        difficulty: diff,
        blindfold: state.blindfold,
        uiPhase: state.phase,
        scores: merged.scores,
        total: finalTotal,
        scoreSource: merged.usedAI ? 'blend' : 'rule',
        aiUsed: merged.usedAI,
        durationSec: 0,
        notes: state.notes,
      });

      advancePhase();
      setSubmitNote(aiNote);
      // 设置页「提交后自动进入结算页」开关在这里生效（原来只写进 localStorage 没人读）
      if (loadSettingsLocal().auto_settle !== false) nav('/settle');
    } catch (e) {
      setSubmitNote(`提交失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  }

  /* 自定义角色被删后的兜底 —— 不能白屏 */
  if (!sc) {
    return (
      <div className="screen is-on training-view">
        <div className="frame">
          <main className="col-mid">
            <section className="casefile">
              <div className="casefile-head">
                <div className="casefile-id">
                  <div className="k">Casefile · 未找到</div>
                  <h2>该服务对象不在剧本库里</h2>
                  <p>可能是自定义角色已被删除，或链接里的编号有误。</p>
                </div>
              </div>
            </section>
            <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
              <button className="btn-primary" type="button" onClick={onExit}>回到服务对象列表</button>
              <button className="btn-ghost" type="button" onClick={() => nav('/')}>回首页</button>
            </div>
          </main>
        </div>
      </div>
    );
  }

  const quick = QUICK_BY_DIFF[state.difficulty] ?? QUICK_ALL;
  const crisis = crisisOpen ? (buildCrisisCard(lastW) || CRISIS_FALLBACK) : null;

  return (
    <div className="screen is-on training-view">
      <div className="frame">
        <nav className="rail" aria-label="主导航">
          <button className="rail-item" type="button" onClick={onExit}>
            <span className="no">01</span><span className="lb">选择</span><span className="bar" />
          </button>
          <button className="rail-item" type="button" aria-current="page">
            <span className="no">02</span><span className="lb">训练</span><span className="bar" />
          </button>
          <button className="rail-item" type="button" onClick={() => nav('/settle')}>
            <span className="no">03</span><span className="lb">结算</span><span className="bar" />
          </button>
          <button className="rail-item" type="button" onClick={() => nav('/growth')}>
            <span className="no">04</span><span className="lb">成长</span><span className="bar" />
          </button>
        </nav>

        <main className="col-mid">
          <section className="casefile">
            <div className="casefile-head">
              <div className="avatar">
                <span className="ring" />
                <span className="disc">{sc.name[0]}</span>
              </div>
              <div className="casefile-id">
                <div className="k">Casefile · {sc.id}</div>
                <h2>{sc.name} <span className="meta">{sc.age} 岁 · {sc.gender} · {sc.archetype}</span></h2>
                <p>{sc.brief}</p>
              </div>
            </div>
            <div className="casefile-foot">
              <span className="tag">难度 {sc.difficulty}/5</span>
              <span className="tag">{state.difficulty}</span>
              {sc.sensitiveTag !== '无' && <span className="tag proof">{sc.sensitiveTag}</span>}
              <span className="tag">保密原则已告知</span>
              <span className="tag">{AI_MODES.find((m) => m.key === state.aiMode)?.label}</span>
            </div>
          </section>

          <section className="script" aria-label="面谈逐字稿">
            <div className="script-head">
              <span className="k">Transcript · 逐字稿</span>
              <span className="n">{nick} · 第 {state.turn} 轮</span>
            </div>
            <div className="script-log" ref={logRef} role="log" aria-live="polite" aria-relevant="additions">
              {state.messages.length === 0 && (
                <div className="script-empty">
                  还没有对话。点下面的快捷话术，或直接输入。
                </div>
              )}
              {state.messages.map((m) => (
                <div
                  key={m.id}
                  className={'turn ' + (m.speaker === 'worker' ? 'me' : m.speaker === 'system' ? 'sys' : 'them')}
                >
                  <span className="ln">
                    {m.speaker === 'system' ? '系统'
                      : m.speaker === 'worker' ? '社工 · 你'
                        : m.isDefense ? '服务对象 · 情绪反应' : '服务对象'}
                  </span>
                  <div className={'line' + (m.isDefense ? ' warn' : '') + (m.isCrisis ? ' fail' : '')}>
                    <span className="who">
                      {m.speaker === 'worker' ? '你' : m.speaker === 'system' ? '系统' : sc.name}
                    </span>
                    {m.text}
                  </div>
                </div>
              ))}
              {state.busy && (
                <div className="turn them">
                  <span className="ln">··</span>
                  <div className="line">
                    <span className="typing"><i /><i /><i /></span>
                    {/* 模型响应 2–16 秒，必须让用户知道在等什么、等了多久 */}
                    <span style={{
                      fontSize: 11.5, marginLeft: 10, color: 'var(--ink-4)',
                      fontFamily: 'var(--mono)', letterSpacing: '.06em',
                    }}>
                      {busySec >= 12
                        ? `模型仍在生成…已 ${busySec}s（免费档高峰期较慢，可切「规则模式」即时响应）`
                        : busySec >= 4
                          ? `正在生成回应…${busySec}s`
                          : '正在生成回应…'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* ── 危机干预卡：确认后才恢复输入 ── */}
          {crisisOpen && (
            <aside className="editor-note" role="alertdialog" aria-label="危机级提示">
              <span className="mark">危机级</span>
              <div className="body">
                <b>{crisis?.title || '已暂停本次训练 · 本轮不计分'}</b>
                <ol style={{ margin: '10px 0 10px 18px', padding: 0, lineHeight: 1.9 }}>
                  {(crisis?.principles || []).map((p) => <li key={p}>{p}</li>)}
                </ol>
                <div style={{ fontSize: 12.5 }}>
                  可核实资源：
                  {(crisis?.hotlines || []).map((h) => `${h.code} ${h.label}`).join(' · ')}
                </div>
                <div style={{ fontSize: 12.5, marginTop: 6, opacity: 0.75 }}>
                  {crisis?.citation}
                </div>
                <button
                  className="btn-primary"
                  type="button"
                  style={{ marginTop: 12 }}
                  onClick={acknowledgeCrisis}
                >
                  我知道了，继续训练
                </button>
              </div>
            </aside>
          )}
          {hint && !crisisOpen && (
            <aside className="editor-note">
              <span className="mark">临床批注</span>
              <div className="body">{hint}</div>
            </aside>
          )}

          {/* AI 建议卡：可折叠、可关闭，内容随最近一句变化 */}
          {showSuggest && (
            <div className="ai-suggest">
              <div className="ah" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="pulse" />
                <span style={{ flex: 1 }}>{sug.title}</span>
                <button
                  type="button"
                  onClick={() => setSuggestOpen((v) => !v)}
                  aria-expanded={suggestOpen}
                  title={suggestOpen ? '收起建议' : '展开建议'}
                  style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 11.5, color: 'inherit', opacity: 0.7 }}
                >
                  {suggestOpen ? '收起' : '展开'}
                </button>
                <button
                  type="button"
                  onClick={() => setSuggestHidden(true)}
                  aria-label="关闭建议卡"
                  title="本阶段不再显示"
                  style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 15, lineHeight: 1, color: 'inherit', opacity: 0.55 }}
                >
                  ×
                </button>
              </div>
              {suggestOpen && (
                <>
                  <p className="aq">「{sug.quote}」</p>
                  <p className="aw"><span className="k">判断依据</span>{sug.basis}</p>
                  <div className="awb">
                    <button className="btn-primary" type="button" onClick={() => setInput(sug.quote)}>
                      用这句
                    </button>
                    <button className="btn-ghost" type="button" onClick={() => setInput('')}>
                      不用，我自己来
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
          {!showSuggest && (
            <button
              type="button"
              onClick={() => { setSuggestHidden(false); setSuggestOpen(true); }}
              style={{
                margin: '10px 0 0', padding: '6px 12px', fontSize: 11.5,
                background: 'none', border: '1px dashed var(--rule-strong)',
                color: 'var(--ink-3)', cursor: 'pointer', borderRadius: 2,
              }}
            >
              + 显示 AI 建议
            </button>
          )}

          <div className="composer">
            <div className="quick" role="group" aria-label="快捷话术">
              {quick.map((q) => (
                <button key={q} type="button" disabled={crisisOpen} onClick={() => setInput(q)}>{q}</button>
              ))}
              {quick.length === 0 && (
                <span style={{ fontSize: 12.5, opacity: 0.65 }}>
                  挑战督导不给快捷话术 —— 请自己组织语言。
                </span>
              )}
            </div>
            <div className="composer-row">
              <input
                className="composer-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) onSend();
                }}
                disabled={crisisOpen || state.busy}
                placeholder={crisisOpen ? '危机级内容已拦截，请先确认处置流程…' : '以社工的身份说一句话…'}
                aria-label="输入你的回应"
              />
              <button className="send" type="button" onClick={onSend}
                disabled={state.busy || crisisOpen} aria-label="发送">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                  <path d="M3 9h11M9.5 4.5 14 9l-4.5 4.5" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              </button>
            </div>
          </div>
        </main>

        <aside className="col-proof" aria-label="六维校样边注">
          <div className="proof-head"><span className="k">Proof Margin · 校样边注</span></div>
          <div className="score">{state.blindfold ? '•••' : total}</div>
          <div className="delta">
            {state.blindfold
              ? '无剧透模式已开启'
              : `本阶段 ${state.notes.length} 条发言已逐句判分`}
          </div>

          <ul className="checklist">
            {DIMENSIONS.map((d) => {
              const v = ruleScores[d.key];
              return (
                <li key={d.key}>
                  <div className="check-top">
                    <span className="check-name">
                      {d.name} <span className="w">· {d.weight}%</span>
                    </span>
                    <span className="check-num">{state.blindfold ? '•••' : v}</span>
                  </div>
                  <div className="bar">
                    <span
                      className={'g ' + gradeOf(v)}
                      style={{ width: (state.blindfold ? 0 : v) + '%' }}
                    />
                  </div>
                  {/* 设置页「点评显示条款依据」开关在这里生效 */}
                  {showBasis && <div className="check-src">{d.source}</div>}
                </li>
              );
            })}
          </ul>

          {/* ── 未连通时的强制提示：绝不能让用户以为 AI 在跑 ── */}
          {!ai.ready && (
            <div
              role="alert"
              style={{
                marginTop: 12, padding: '10px 12px',
                border: '1px solid var(--warn, #b8860b)',
                borderLeft: '3px solid var(--warn, #b8860b)',
                background: 'var(--warn-wash, #fdf6e3)',
                color: '#6B4A12', fontSize: 12, lineHeight: 1.75,
              }}
            >
              <b>AI 服务未连通，当前台词来自预置库。</b>
              <br />
              原因：{ai.lastError || ai.detail || '无法访问 /api/health'}
              <br />
              请先运行 <code style={{ background: 'rgba(0,0,0,.06)', padding: '1px 4px' }}>start.bat</code>
              （或 <code style={{ background: 'rgba(0,0,0,.06)', padding: '1px 4px' }}>node server/index.mjs</code>），
              然后点下面的按钮重新检测。
              <br />
              <button
                type="button"
                onClick={() => void probeAi()}
                style={{
                  marginTop: 8, padding: '5px 12px', fontSize: 12, cursor: 'pointer',
                  border: '1px solid var(--warn, #b8860b)', background: 'transparent',
                  color: '#6B4A12', borderRadius: 2,
                }}
              >
                重新检测 AI 服务
              </button>
            </div>
          )}

          {/* ── AI 模式切换 ── */}
          <div style={{ marginTop: 18, borderTop: '1px solid var(--rule)', paddingTop: 14 }}>
            <div className="k" style={{ marginBottom: 8 }}>AI 参与度</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {AI_MODES.map((m) => {
                const on = state.aiMode === m.key;
                // ★ 未连通且不是规则模式时，不能让按钮保持"选中"的实心高亮
                const degraded = !ai.ready && m.key !== 'rule';
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => setAiMode(m.key)}
                    aria-pressed={on}
                    title={degraded && on ? '该模式需要 AI 服务，当前未连通，已自动回落' : m.hint}
                    style={{
                      flex: '1 1 auto',
                      padding: '6px 8px',
                      fontSize: 12,
                      cursor: 'pointer',
                      borderRadius: 2,
                      border: '1px ' + (degraded && on ? 'dashed' : 'solid') + ' '
                        + (on ? (degraded ? 'var(--warn, #b8860b)' : 'var(--ink)') : 'var(--rule)'),
                      background: on && !degraded ? 'var(--ink)' : 'transparent',
                      color: on
                        ? (degraded ? 'var(--warn, #b8860b)' : 'var(--paper)')
                        : 'var(--ink-2)',
                    }}
                  >
                    {m.label}
                    {degraded && on ? ' ⚠' : ''}
                  </button>
                );
              })}
            </div>
            <p style={{ fontSize: 11.5, lineHeight: 1.7, marginTop: 8, color: 'var(--ink-3)' }}>
              {AI_MODES.find((m) => m.key === state.aiMode)?.hint}
            </p>
            <p style={{
              fontSize: 11.5, lineHeight: 1.7,
              color: ai.ready ? 'var(--ink-3)' : 'var(--warn, #9a5b2a)',
            }}>
              {ai.ready
                ? `已连通 ${ai.model || 'GLM'} · ${ai.latencyMs}ms`
                : `未连通 · ${ai.lastError || '服务没在跑'}`}
            </p>
            {state.aiLast?.note && (
              <p style={{ fontSize: 11, marginTop: 6, color: 'var(--ink-4)' }}>
                {state.aiLast.used ? '◆ 本轮台词：' : '· 本轮台词：'}{state.aiLast.note}
              </p>
            )}
          </div>

          <button className="nsf" type="button" aria-pressed={state.blindfold}
            onClick={() => setState((s) => ({ ...s, blindfold: !s.blindfold }))}>
            <span className="sw" />
            <span className="tx">
              <b>无剧透模式</b>
              <span>不显示分数，专注在对话本身</span>
            </span>
          </button>

          <div className="stages">
            {[1, 2, 3].map((p) => (
              <span key={p}
                className={'sd ' + (p === state.phase ? 'now' : p < state.phase ? 'on' : '')} />
            ))}
            <span className="lb">阶段 {state.phase} / 3</span>
          </div>

          <button className="submit" type="button" onClick={onSubmit} disabled={submitting || state.busy}>
            {submitting ? '督导正在阅卷…' : '提交本阶段'}
          </button>
          {submitNote && (
            <p style={{ fontSize: 11.5, lineHeight: 1.7, marginTop: 8, color: 'var(--ink-3)' }}>
              {submitNote}
            </p>
          )}

          <div className="legend">
            <span className="k">图例 · 校样标记</span>
            <p><span className="del">删除线</span> = 扣分项，命中黑名单规则</p>
            <p><span className="add">绿色下划线</span> = 加分项，命中正向规则</p>
            <p className="src"><b>依据：</b>民政部《社会工作方法 个案工作》（民政部公告第 426 号）</p>
          </div>

          <div className="weak-box">
            <div className="k">本阶段最弱项</div>
            <div className="wn">
              {DIMENSIONS.find((d) => d.key === weak.dimension)?.name} {ruleScores[weak.dimension]}
            </div>
            <p className="wa">{weak.advice}</p>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            <button
              className="btn-ghost"
              type="button"
              style={{ flex: 1, fontSize: 12 }}
              onClick={() => { reset(); setSubmitNote('已清空本轮对话与评分'); }}
            >
              重开本轮
            </button>
          </div>

          <div className="other-cases">
            <button className="oc-toggle" type="button" aria-expanded={swapOpen}
              onClick={() => setSwapOpen((v) => !v)}>
              {swapOpen ? '收起' : '换一位服务对象'}
              <span className="arw">{swapOpen ? '▲' : '▼'}</span>
            </button>
            {swapOpen && (
              <div className="oc-list">
                {SCENARIOS.map((x) => (
                  <button key={x.id} type="button"
                    className={'oc' + (x.id === sc.id ? ' cur' : '')}
                    disabled={x.id === sc.id}
                    onClick={() => {
                      if (state.messages.length > 0 &&
                        !window.confirm('换角色会清空当前对话进度与本次评分，确定继续？')) return;
                      setSwapOpen(false);
                      nav('/training/' + x.id);
                    }}>
                    <span className="oc-id">{x.id}</span>
                    <span className="oc-nm">{x.name}</span>
                    <span className="oc-mt">{x.archetype}</span>
                    <span className="oc-dots">
                      {[1, 2, 3, 4, 5].map((k) => (
                        <i key={k} className={k <= x.difficulty ? 'on' : ''} />
                      ))}
                    </span>
                    {x.id === sc.id && <span className="oc-cur">当前</span>}
                  </button>
                ))}
              </div>
            )}
            <p className="oc-note">换角色会清空当前对话进度与本次评分。</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

/* 危机卡兜底：正常情况下 buildCrisisCard() 一定会给出内容，
   这里只防「学生最后一句已被后续消息覆盖」这种极窄窗口 */
const CRISIS_FALLBACK = {
  title: '已暂停本次训练 · 本轮不计分',
  principles: [
    '如果这是真实情境，请这样做：',
    '1. 不要单独处理，立即联系你的专业督导。',
    '2. 如实记录：时间、对话内容、你的观察。',
    '3. 不要承诺保密 —— 安全例外优先于保密原则。',
    '4. 不离开，保持在场的姿态，等待专业人员介入。',
    '5. 不要独自做安全评估结论。',
  ],
  hotlines: [
    { code: '12356', label: '全国统一心理援助热线 · 24 小时 · 免费' },
    { code: '110', label: '报警' },
    { code: '120', label: '急救' },
  ],
  citation: '依据：国家卫生健康委《关于应用"12356"全国统一心理援助热线电话号码的通知》（国卫医政函〔2024〕259 号）。',
};
